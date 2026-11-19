"""Acceso al kiosco.

- **Kiosco de planta:** sin contraseña, pero solo desde la misma PC (IP local).
- **Modo prueba:** el superusuario, desde la oficina, entra como el usuario
  «operario» (ver `cuentas/prueba.py`). Como en la nube no corre el proceso de
  sincronización, en este modo se sincroniza dentro del mismo pedido: lo
  registrado se envía en el momento, y la copia se renueva solo si tiene más de
  KIOSCO_PRUEBA_COPIA_CADA segundos o se pide con «Actualizar lista»
  (`?actualizar=1`). Lo recién registrado se ve igual, porque el estado local
  suma la cola a la copia.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden

from cuentas.prueba import en_modo_prueba

from .models import Foto
from .sincronizacion import copia_vencida, marcar_actividad, sincronizar


def _copia_con_operario_de_prueba() -> bool:
    foto = Foto.objects.filter(id=1).first()
    return foto is not None and foto.datos.get("operario_prueba") is not None


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
            # En la nube la conexión se reusa entre pedidos: no se cierra acá.
            renovar = (
                request.GET.get("actualizar") == "1"
                or copia_vencida(settings.KIOSCO_PRUEBA_COPIA_CADA)
                or not _copia_con_operario_de_prueba()
            )
            sincronizar(forzar_copia=renovar, cerrar=False)
        respuesta = vista(request, *args, **kwargs)
        if prueba and request.method == "POST":
            sincronizar(cerrar=False)
        return respuesta

    return envoltura
