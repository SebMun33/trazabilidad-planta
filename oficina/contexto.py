from django.db import DatabaseError

from cuentas.prueba import operario_prueba_id
from cuentas.roles import etiqueta_de
from planta.models import UltimaPublicacion


def perfil(request):
    """Datos comunes de las pantallas de oficina (rol del usuario y última carga).

    Lo que cada uno puede hacer se pregunta en las plantillas con `perms.cuentas.*`.
    """
    if not request.path.startswith("/oficina/"):
        return {}
    try:
        publicacion = UltimaPublicacion.objects.first()
    except DatabaseError:
        publicacion = None
    return {
        "rol_etiqueta": etiqueta_de(request.user),
        "ultima_publicacion": publicacion.publicado_en if publicacion else None,
        # Para marcar «prueba» lo que registró el usuario «operario».
        "operario_prueba_id": operario_prueba_id(),
    }
