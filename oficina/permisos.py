"""Acceso por grupo: `oficina` prepara pendientes; `supervisor` además cierra el día."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

GRUPO_OFICINA = "oficina"
GRUPO_SUPERVISOR = "supervisor"


def pertenece(usuario, *grupos: str) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=grupos).exists()


def requiere_grupo(*grupos: str):
    """Exige login y pertenecer a alguno de los grupos (los superusuarios pasan)."""

    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not pertenece(request.user, *grupos):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


requiere_oficina = requiere_grupo(GRUPO_OFICINA, GRUPO_SUPERVISOR)
requiere_supervisor = requiere_grupo(GRUPO_SUPERVISOR)
