"""Acceso al kiosco.

- **Kiosco de planta:** sin contraseña, pero solo desde la misma PC (IP local).
- **Modo prueba:** el superusuario, desde la oficina, entra como el usuario
  «operario» (ver `cuentas/prueba.py`). Como en la nube no corre el proceso de
  sincronización, en este modo se sincroniza dentro del mismo pedido: la copia
  se renueva antes de mostrar y lo registrado se envía en el momento.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden

from cuentas.prueba import en_modo_prueba

from .sincronizacion import marcar_actividad, sincronizar


def solo_kiosco(vista):
    """Permite las IP configuradas (por defecto, 127.0.0.1 y ::1) o el modo prueba.

    En la PC de planta Gunicorn escucha en 127.0.0.1 y Chromium corre en la misma
    máquina; esta verificación es una segunda barrera por si se cambia el bind.
    """

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        prueba = en_modo_prueba(request)
        if not prueba and (
            not settings.KIOSCO_HABILITADO
            or request.META.get("REMOTE_ADDR") not in settings.KIOSCO_IPS_PERMITIDAS
        ):
            return HttpResponseForbidden("El kiosco solo se usa desde la PC de planta.")
        request.kiosco_prueba = prueba
        marcar_actividad()
        if prueba:
            # El indicador de estado se consulta cada pocos segundos: no fuerza la copia.
            coincidencia = request.resolver_match
            es_estado = coincidencia is not None and coincidencia.url_name == "estado"
            sincronizar(forzar_copia=not es_estado)
        respuesta = vista(request, *args, **kwargs)
        if prueba and request.method == "POST":
            sincronizar()
        return respuesta

    return envoltura
