"""Usuario «operario» para que el superusuario pruebe el kiosco.

- Se crea la primera vez que el superusuario toca «Probar como operario».
- Es un Operario sin contraseña, oculto para todos menos el superusuario: no
  aparece en el admin de los demás ni en las listas del kiosco de planta.
- Lo que registra va a la base real (solo se agregan filas). Sus eventos se
  graban con `dispositivo = 'prueba'` y se pueden anular todos juntos con
  «Deshacer pruebas».
"""

from django.conf import settings
from django.contrib.auth.models import User

from planta.models import Operario

from .roles import OPERARIO, asignar_rol, rol_de

USUARIO_PRUEBA = "operario"
DISPOSITIVO_PRUEBA = "prueba"
# Clave de sesión que activa el modo prueba del kiosco.
SESION_PRUEBA = "kiosco_prueba"


def es_usuario_prueba(usuario) -> bool:
    return usuario is not None and usuario.get_username().casefold() == USUARIO_PRUEBA


def usuario_prueba(*, crear: bool = False) -> User | None:
    usuario = User.objects.filter(username__iexact=USUARIO_PRUEBA).first()
    if usuario is None and crear:
        usuario = User(username=USUARIO_PRUEBA, first_name="Usuario de prueba")
        usuario.set_unusable_password()
        usuario.save()
    if usuario is not None and crear:
        if not usuario.is_active:
            usuario.is_active = True
            usuario.save(update_fields=["is_active"])
        if rol_de(usuario) != OPERARIO:
            asignar_rol(usuario, OPERARIO)
    return usuario


def operario_prueba_id() -> int | None:
    usuario_id = (
        User.objects.filter(username__iexact=USUARIO_PRUEBA).values_list("pk", flat=True).first()
    )
    if usuario_id is None:
        return None
    return (
        Operario.objects.filter(usuario_id=usuario_id).values_list("operario_id", flat=True).first()
    )


def en_modo_prueba(request) -> bool:
    """Superusuario con el modo prueba activado.

    Si el pedido no trae cookie de sesión, ni se mira la sesión: así el kiosco de
    planta (que nunca tiene sesión) no consulta la base central.
    """
    if settings.SESSION_COOKIE_NAME not in request.COOKIES:
        return False
    usuario = getattr(request, "user", None)
    return bool(
        usuario is not None
        and usuario.is_authenticated
        and usuario.is_superuser
        and request.session.get(SESION_PRUEBA)
    )
