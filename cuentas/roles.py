"""Roles de la app: cada usuario tiene uno y cada rol, un juego fijo de permisos.

| Rol              | Para qué                                                    |
|------------------|-------------------------------------------------------------|
| operario         | Registra avances y notas en el kiosco (sin contraseña)      |
| oficina_tecnica  | Prepara pendientes, revisa, anula registros y cierra el día |
| contabilidad     | Solo lectura de trabajos, estados, registros e importes     |
| staff            | Todo, admin incluido, salvo tocar superusuarios             |

El superusuario no es un rol: es la cuenta personal del dueño del sistema.
Ver docs/decisiones/0007-roles-y-acceso.md.
"""

from dataclasses import dataclass

OPERARIO = "operario"
OFICINA_TECNICA = "oficina_tecnica"
CONTABILIDAD = "contabilidad"
STAFF = "staff"
SUPERUSUARIO = "superusuario"


@dataclass(frozen=True)
class Rol:
    nombre: str
    etiqueta: str
    permisos: tuple[str, ...]  # codenames de cuentas.Permisos; staff recibe todos
    es_staff: bool = False
    usa_contrasena: bool = True


ROLES = {
    r.nombre: r
    for r in [
        Rol(
            OPERARIO,
            "Operario",
            ("registrar_avances", "escribir_notas"),
            usa_contrasena=False,
        ),
        Rol(
            OFICINA_TECNICA,
            "Oficina técnica",
            (
                "ver_trabajos",
                "preparar_trabajos",
                "escribir_notas",
                "anular_registros",
                "cerrar_dia",
                "ver_importes",
            ),
        ),
        # Los operarios nunca ven plata: no tienen `ver_importes` y el kiosco no
        # recibe ningún importe (ver kiosco/foto.py).
        Rol(CONTABILIDAD, "Contabilidad", ("ver_trabajos", "ver_importes")),
        Rol(STAFF, "Staff", (), es_staff=True),
    ]
}
OPCIONES = [(r.nombre, r.etiqueta) for r in ROLES.values()]


def sincronizar_roles(*, apps=None, using="default", **kwargs):
    """Crea los grupos de los roles y les asigna su juego de permisos.

    Corre después de cada `migrate`: si cambia un juego de permisos en el
    código, los grupos quedan al día solos.
    """
    if using != "default":
        return
    from django.contrib.auth.models import Group, Permission

    propios = Permission.objects.filter(content_type__app_label="cuentas")
    for rol in ROLES.values():
        grupo, _ = Group.objects.get_or_create(name=rol.nombre)
        if rol.es_staff:
            grupo.permissions.set(Permission.objects.all())
        else:
            grupo.permissions.set(propios.filter(codename__in=rol.permisos))


def rol_de(usuario) -> str | None:
    if not usuario.is_authenticated:
        return None
    if usuario.is_superuser:
        return SUPERUSUARIO
    nombres = set(usuario.groups.values_list("name", flat=True))
    return next((nombre for nombre in ROLES if nombre in nombres), None)


def etiqueta_de(usuario) -> str:
    rol = rol_de(usuario)
    if rol == SUPERUSUARIO:
        return "Superusuario"
    return ROLES[rol].etiqueta if rol else "Sin rol"


def asignar_rol(usuario, rol: str) -> None:
    """Deja al usuario con un único rol (grupo) y el acceso al admin que corresponde."""
    from django.contrib.auth.models import Group

    definicion = ROLES[rol]
    if usuario.is_staff != definicion.es_staff:
        usuario.is_staff = definicion.es_staff
        usuario.save(update_fields=["is_staff"])
    usuario.groups.set([Group.objects.get_or_create(name=rol)[0]])
