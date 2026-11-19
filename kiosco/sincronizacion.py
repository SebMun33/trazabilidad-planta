"""Sincronización del kiosco con la base central (corre en un proceso aparte).

1. Envía la cola: cada evento se inserta con su `evento_id` y `ON CONFLICT DO
   NOTHING`, así que reenviar es inofensivo (idempotente). Después, las notas
   (con su `nota_id`, también idempotente; al grabarse se avisa a oficina).
2. Renueva la copia local, solo mientras el kiosco se usa (ver `Actividad`).

Si la base central no responde, la cola queda como está y se reintenta en la
próxima vuelta; las pantallas del kiosco siguen funcionando con la copia local.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, IntegrityError, OperationalError, connections, transaction
from django.utils import timezone

from cuentas.prueba import DISPOSITIVO_PRUEBA
from planta.models import Evento
from planta.servicios import ReglaDeNegocioError
from planta.servicios.notas import crear_nota

from .foto import armar_foto
from .models import Actividad, EventoPendiente, Foto, NotaPendiente

logger = logging.getLogger(__name__)
CENTRAL = "default"


@dataclass
class Resultado:
    enviados: int = 0
    notas_enviadas: int = 0
    rechazados: int = 0
    copia_renovada: bool = False
    sin_conexion: bool = False


def _evento(p: EventoPendiente, prueba_id: int | None = None) -> Evento:
    return Evento(
        evento_id=p.evento_id,
        tipo=p.tipo,
        trabajo_id=p.trabajo_id,
        operacion_id=p.operacion_id,
        maquina_id=p.maquina_id,
        operario_id=p.operario_id,
        ocurrido_en=p.ocurrido_en,
        observaciones=p.observaciones or None,
        anula_evento_id=p.anula_evento_id,
        registrado_por=p.registrado_por,
        # Lo que registra el operario de prueba queda marcado (ver cuentas/prueba.py).
        dispositivo=(
            DISPOSITIVO_PRUEBA
            if prueba_id is not None and prueba_id in (p.operario_id, p.cargado_por_id)
            else settings.PLANTA_DISPOSITIVO
        ),
    )


def enviar_pendientes(resultado: Resultado) -> None:
    """Inserta la cola en orden. Corta en el primer error de conexión."""
    foto = Foto.objects.filter(id=1).first()
    prueba_id = foto.datos.get("operario_prueba") if foto else None
    for pendiente in EventoPendiente.objects.filter(enviado_en=None, rechazado_en=None):
        pendiente.intentos += 1
        try:
            with transaction.atomic(using=CENTRAL):
                Evento.objects.using(CENTRAL).bulk_create(
                    [_evento(pendiente, prueba_id)], ignore_conflicts=True
                )
        except OperationalError as error:
            pendiente.ultimo_error = str(error)[:500]
            pendiente.save(update_fields=["intentos", "ultimo_error"])
            resultado.sin_conexion = True
            raise
        except (IntegrityError, DatabaseError) as error:
            # La base central no lo acepta (p. ej., trabajo inexistente): no se
            # reintenta para no trabar la cola; queda a la vista en el kiosco.
            logger.error("Evento %s rechazado: %s", pendiente.evento_id, error)
            pendiente.rechazado_en = timezone.now()
            pendiente.ultimo_error = str(error)[:500]
            pendiente.save(update_fields=["intentos", "rechazado_en", "ultimo_error"])
            resultado.rechazados += 1
            continue
        pendiente.enviado_en = timezone.now()
        pendiente.ultimo_error = ""
        pendiente.save(update_fields=["intentos", "enviado_en", "ultimo_error"])
        resultado.enviados += 1


def enviar_notas(resultado: Resultado) -> None:
    """Graba las notas en orden con el servicio central (que avisa a oficina)."""
    for pendiente in NotaPendiente.objects.filter(enviado_en=None, rechazado_en=None):
        pendiente.intentos += 1
        try:
            crear_nota(
                nota_id=pendiente.nota_id,
                trabajo_id=pendiente.trabajo_id,
                operacion_id=pendiente.operacion_id,
                tipo=pendiente.tipo,
                texto=pendiente.texto,
                responde_a_id=pendiente.responde_a,
                autor=pendiente.autor,
                operario_id=pendiente.operario_id,
                escrita_en=pendiente.escrita_en,
            )
        except OperationalError as error:
            pendiente.ultimo_error = str(error)[:500]
            pendiente.save(update_fields=["intentos", "ultimo_error"])
            resultado.sin_conexion = True
            raise
        except (ReglaDeNegocioError, IntegrityError, DatabaseError) as error:
            logger.error("Nota %s rechazada: %s", pendiente.nota_id, error)
            pendiente.rechazado_en = timezone.now()
            pendiente.ultimo_error = str(error)[:500]
            pendiente.save(update_fields=["intentos", "rechazado_en", "ultimo_error"])
            resultado.rechazados += 1
            continue
        pendiente.enviado_en = timezone.now()
        pendiente.ultimo_error = ""
        pendiente.save(update_fields=["intentos", "enviado_en", "ultimo_error"])
        resultado.notas_enviadas += 1


def kiosco_en_uso() -> bool:
    actividad = Actividad.objects.filter(id=1).first()
    limite = timezone.now() - timedelta(minutes=settings.KIOSCO_ACTIVO_MINUTOS)
    return actividad is not None and actividad.ultima >= limite


def copia_vencida(segundos: int | None = None) -> bool:
    """La copia local tiene más de `segundos` (por defecto, KIOSCO_COPIA_CADA)."""
    foto = Foto.objects.filter(id=1).first()
    if foto is None:
        return True
    limite = timedelta(seconds=settings.KIOSCO_COPIA_CADA if segundos is None else segundos)
    return timezone.now() - foto.obtenida_en >= limite


def renovar_copia() -> None:
    # La hora se toma antes de consultar: lo enviado antes de este momento ya
    # está incluido en la copia (ver local._eventos_locales).
    pedida_en = timezone.now()
    datos = armar_foto()
    Foto.objects.update_or_create(id=1, defaults={"datos": datos, "obtenida_en": pedida_en})


def sincronizar(*, forzar_copia: bool = False, cerrar: bool = True) -> Resultado:
    resultado = Resultado()
    usada = False
    try:
        if EventoPendiente.objects.filter(enviado_en=None, rechazado_en=None).exists():
            usada = True
            enviar_pendientes(resultado)
        if NotaPendiente.objects.filter(enviado_en=None, rechazado_en=None).exists():
            usada = True
            enviar_notas(resultado)
        primera = not Foto.objects.filter(id=1).exists()
        if forzar_copia or primera or (kiosco_en_uso() and copia_vencida()):
            usada = True
            renovar_copia()
            resultado.copia_renovada = True
    except OperationalError as error:
        resultado.sin_conexion = True
        logger.warning("Sin conexión con la base central: %s", error)
    finally:
        conexion = connections[CENTRAL]
        if cerrar and usada and not conexion.in_atomic_block:
            # Sin conexiones abiertas, Neon puede suspender el cómputo inactivo.
            conexion.close()
    return resultado


def marcar_actividad() -> None:
    Actividad.objects.update_or_create(id=1, defaults={"ultima": timezone.now()})
