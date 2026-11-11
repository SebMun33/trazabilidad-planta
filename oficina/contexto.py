from django.db import DatabaseError

from planta.models import UltimaPublicacion

from .permisos import GRUPO_OFICINA, GRUPO_SUPERVISOR, pertenece


def perfil(request):
    """Datos comunes de las pantallas de oficina (perfil del usuario y última carga)."""
    if not request.path.startswith("/oficina/"):
        return {}
    try:
        publicacion = UltimaPublicacion.objects.first()
    except DatabaseError:
        publicacion = None
    return {
        "es_oficina": pertenece(request.user, GRUPO_OFICINA, GRUPO_SUPERVISOR),
        "es_supervisor": pertenece(request.user, GRUPO_SUPERVISOR),
        "ultima_publicacion": publicacion.publicado_en if publicacion else None,
    }
