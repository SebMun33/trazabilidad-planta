"""Acceso al kiosco: sin contraseña, pero solo desde la misma PC de planta."""

from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden

from .sincronizacion import marcar_actividad


def solo_kiosco(vista):
    """Permite solo las IP configuradas (por defecto, 127.0.0.1 y ::1).

    En la PC de planta Gunicorn escucha en 127.0.0.1 y Chromium corre en la misma
    máquina; esta verificación es una segunda barrera por si se cambia el bind.
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if request.META.get("REMOTE_ADDR") not in settings.KIOSCO_IPS_PERMITIDAS:
            return HttpResponseForbidden("El kiosco solo se usa desde la PC de planta.")
        marcar_actividad()
        return vista(request, *args, **kwargs)

    return envoltura
