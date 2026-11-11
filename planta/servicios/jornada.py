"""Registros del día, anulaciones y cierre de jornada."""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import CierreDia, Evento
from . import ReglaDeNegocioError
from .estado import EN_PROCESO, estado_trabajos


def rango_del_dia(fecha: date) -> tuple[datetime, datetime]:
    """Inicio y fin (excluido) del día en la zona horaria de la planta."""
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    return inicio, inicio + timedelta(days=1)


def eventos_del_dia(fecha: date):
    inicio, fin = rango_del_dia(fecha)
    return (
        Evento.objects.filter(ocurrido_en__gte=inicio, ocurrido_en__lt=fin)
        .select_related("operario", "anula_evento")
        .order_by("ocurrido_en", "registrado_en")
    )


def ultimo_cierre(fecha: date) -> CierreDia | None:
    return CierreDia.objects.filter(fecha=fecha).order_by("-registrado_en").first()


def dia_cerrado(fecha: date) -> bool:
    cierre = ultimo_cierre(fecha)
    return cierre is not None and cierre.tipo == CierreDia.Tipo.CIERRE


@transaction.atomic
def anular_evento(evento_id, usuario: str, motivo: str | None = None) -> Evento:
    """Graba una anulación del evento. El evento original no se toca."""
    original = Evento.objects.filter(evento_id=evento_id).first()
    if original is None:
        raise ReglaDeNegocioError("El registro no existe.")
    if original.tipo == Evento.Tipo.ANULACION:
        raise ReglaDeNegocioError("Una anulación no se puede anular.")
    if Evento.objects.filter(anula_evento_id=original.evento_id).exists():
        raise ReglaDeNegocioError("Ese registro ya estaba anulado.")
    if dia_cerrado(timezone.localdate(original.ocurrido_en)):
        raise ReglaDeNegocioError(
            "El día de ese registro está cerrado. Un supervisor tiene que reabrirlo."
        )
    return Evento.objects.create(
        evento_id=uuid.uuid4(),
        tipo=Evento.Tipo.ANULACION,
        trabajo_id=original.trabajo_id,
        operacion_id=original.operacion_id,
        anula_evento=original,
        ocurrido_en=timezone.now(),
        observaciones=(motivo or "").strip() or None,
        registrado_por=usuario,
        dispositivo=settings.PLANTA_DISPOSITIVO,
    )


@dataclass
class ResumenDia:
    fecha: date
    por_tipo: Counter
    anulados: set
    abiertas: list  # (EstadoTrabajo, EstadoOperacion) con un "empezado" sin cerrar
    cierre: CierreDia | None

    @property
    def cerrado(self) -> bool:
        return self.cierre is not None and self.cierre.tipo == CierreDia.Tipo.CIERRE


def resumen_dia(fecha: date) -> ResumenDia:
    eventos = list(eventos_del_dia(fecha))
    anulados = {e.anula_evento_id for e in eventos if e.tipo == Evento.Tipo.ANULACION}
    # También cuentan las anulaciones grabadas otro día sobre eventos de este día.
    anulados |= set(
        Evento.objects.filter(anula_evento__in=eventos).values_list("anula_evento_id", flat=True)
    )
    por_tipo = Counter(e.tipo for e in eventos if e.evento_id not in anulados)
    abiertas = [
        (t, op)
        for t in estado_trabajos(solo_activos=True)
        for op in t.operaciones
        if op.estado == EN_PROCESO
    ]
    return ResumenDia(fecha, por_tipo, anulados, abiertas, ultimo_cierre(fecha))


@transaction.atomic
def cerrar_dia(fecha: date, usuario: str, observaciones: str | None = None) -> CierreDia:
    """El supervisor valida la jornada. Los trabajos abiertos no bloquean el cierre."""
    if fecha > timezone.localdate():
        raise ReglaDeNegocioError("No se puede cerrar un día futuro.")
    if dia_cerrado(fecha):
        raise ReglaDeNegocioError("Ese día ya está cerrado.")
    return CierreDia.objects.create(
        fecha=fecha,
        tipo=CierreDia.Tipo.CIERRE,
        registrado_por=usuario,
        observaciones=(observaciones or "").strip() or None,
    )


@transaction.atomic
def reabrir_dia(fecha: date, usuario: str, observaciones: str | None = None) -> CierreDia:
    if not dia_cerrado(fecha):
        raise ReglaDeNegocioError("Ese día no está cerrado.")
    if not (observaciones or "").strip():
        raise ReglaDeNegocioError("Indicá el motivo de la reapertura.")
    return CierreDia.objects.create(
        fecha=fecha,
        tipo=CierreDia.Tipo.REAPERTURA,
        registrado_por=usuario,
        observaciones=observaciones.strip(),
    )
