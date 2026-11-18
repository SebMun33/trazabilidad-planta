"""Avisos a oficina cuando pasa algo en planta (por ahora: una nota nueva).

Está preparado para enchufar canales sin tocar el resto de la app. Cada canal
es una clase con `enviar(aviso, destinatarios)`; los activos se eligen con la
variable AVISOS_CANALES (rutas de clases separadas por coma). Por defecto solo
se registra en el log.

- `CanalRegistro`: escribe el aviso en el log (siempre seguro).
- `CanalCorreo`: manda un mail con la configuración EMAIL_URL de Django (p. ej.,
  una casilla del dominio propio).
- WhatsApp: agregar una clase con la API que se elija (WhatsApp Cloud API de
  Meta, Twilio, etc.) y sumarla a AVISOS_CANALES. Los destinatarios necesitarían
  un teléfono en su usuario.

Un canal que falla no rompe nada: se registra el error y se sigue.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass
class Aviso:
    asunto: str
    texto: str


class CanalRegistro:
    def enviar(self, aviso: Aviso, destinatarios: list) -> None:
        nombres = ", ".join(u.get_username() for u in destinatarios) or "nadie"
        logger.info("Aviso para %s: %s", nombres, aviso.asunto)


class CanalCorreo:
    def enviar(self, aviso: Aviso, destinatarios: list) -> None:
        correos = [u.email for u in destinatarios if u.email]
        if correos:
            send_mail(aviso.asunto, aviso.texto, None, correos, fail_silently=False)


def canales() -> list:
    return [import_string(ruta)() for ruta in settings.AVISOS_CANALES]


def destinatarios_oficina(excluir_usuario_id: int | None = None) -> list:
    """Usuarios activos de Oficina técnica y Staff (y el superusuario)."""
    usuarios = (
        get_user_model()
        .objects.filter(is_active=True)
        .filter(Q(groups__name__in=["oficina_tecnica", "staff"]) | Q(is_superuser=True))
        .distinct()
    )
    if excluir_usuario_id:
        usuarios = usuarios.exclude(pk=excluir_usuario_id)
    return list(usuarios)


def avisar(aviso: Aviso, destinatarios: list) -> None:
    for canal in canales():
        try:
            canal.enviar(aviso, destinatarios)
        except Exception:
            logger.exception("Falló el canal de avisos %s", type(canal).__name__)


def nota_creada(nota_id) -> None:
    from ..models import Nota, TrabajoOperacion
    from .estado import ultimas_revisiones

    nota = Nota.objects.filter(nota_id=nota_id).first()
    if nota is None:
        return
    revision = ultimas_revisiones([nota.trabajo_id]).first()
    plano = revision.plano if revision else "?"
    donde = plano
    if nota.operacion_id:
        op = (
            TrabajoOperacion.objects.filter(operacion_id=nota.operacion_id)
            .order_by("-revision__revision")
            .first()
        )
        if op:
            donde = f"{plano}, operación {op.operacion_nro}"
    aviso = Aviso(
        asunto=f"{nota.get_tipo_display()} de {nota.autor} en {donde}",
        texto=f"{nota.autor} escribió el {nota.escrita_en:%d/%m/%Y %H:%M}:\n\n{nota.texto}",
    )
    avisar(aviso, destinatarios_oficina(excluir_usuario_id=nota.usuario_id))
