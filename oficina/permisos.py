"""Acceso a las pantallas de oficina por permiso (cada rol trae su juego).

Ver cuentas/roles.py: Oficina técnica prepara, anula y cierra; Contabilidad
solo mira; Staff y el superusuario pueden todo.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def requiere_permiso(codename: str):
    """Exige login y el permiso `cuentas.<codename>`."""

    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.has_perm(f"cuentas.{codename}"):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


requiere_ver = requiere_permiso("ver_trabajos")
requiere_preparar = requiere_permiso("preparar_trabajos")
requiere_notas = requiere_permiso("escribir_notas")
requiere_anular = requiere_permiso("anular_registros")
requiere_cierre = requiere_permiso("cerrar_dia")
