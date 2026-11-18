"""Un usuario con rol Operario aparece solo como operario en el kiosco.

`planta.operario` sigue siendo la tabla que referencian los eventos (y el data
warehouse); acá se mantiene vinculada al usuario por `usuario_id`.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from planta.models import Operario

from .nombres import normalizar
from .roles import OPERARIO, rol_de

Usuario = get_user_model()


def sincronizar_operario(usuario) -> Operario | None:
    """Crea, vincula, renombra o desactiva el operario del usuario según su rol."""
    es_operario = usuario.is_active and rol_de(usuario) == OPERARIO
    operario = Operario.objects.filter(usuario_id=usuario.pk).first()
    if operario is None and es_operario:
        # Operario cargado antes de tener usuario (p. ej., desde el admin viejo).
        operario = next(
            (
                o
                for o in Operario.objects.filter(usuario_id=None)
                if normalizar(o.nombre) == normalizar(usuario.username)
            ),
            None,
        )
        if operario is not None:
            operario.usuario_id = usuario.pk
            operario.save(update_fields=["usuario_id"])
    if operario is None:
        if es_operario:
            return Operario.objects.create(nombre=usuario.username, usuario_id=usuario.pk)
        return None
    cambios = []
    if operario.nombre != usuario.username:
        operario.nombre = usuario.username
        cambios.append("nombre")
    if operario.activo != es_operario:
        operario.activo = es_operario
        cambios.append("activo")
    if cambios:
        operario.save(update_fields=cambios)
    return operario


@receiver(post_save, sender=Usuario)
def _usuario_guardado(sender, instance, raw=False, **kwargs):
    if not raw:
        sincronizar_operario(instance)


@receiver(m2m_changed, sender=Usuario.groups.through)
def _grupos_cambiados(sender, instance, action, reverse=False, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and not reverse:
        sincronizar_operario(instance)
