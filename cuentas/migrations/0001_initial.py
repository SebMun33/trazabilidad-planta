from django.db import migrations

# Los grupos de los roles y sus permisos los crea `roles.sincronizar_roles`
# después de cada migrate. Acá solo se pasan los usuarios de los grupos viejos.
VIEJOS = ["oficina", "supervisor"]


def pasar_a_oficina_tecnica(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    nuevo, _ = Group.objects.get_or_create(name="oficina_tecnica")
    for grupo in Group.objects.filter(name__in=VIEJOS):
        for usuario in grupo.user_set.all():
            usuario.groups.add(nuevo)
        grupo.delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("planta", "0002_grupos"),
    ]

    operations = [
        migrations.CreateModel(
            name="Permisos",
            fields=[],
            options={
                "permissions": [
                    ("ver_trabajos", "Ver trabajos, estados y registros"),
                    (
                        "preparar_trabajos",
                        "Pasar trabajos a pendientes, revisarlos y retirarlos",
                    ),
                    ("registrar_avances", "Registrar avances en planta"),
                    ("escribir_notas", "Escribir observaciones, sugerencias y preguntas"),
                    ("anular_registros", "Anular registros de planta"),
                    ("cerrar_dia", "Cerrar y reabrir el día"),
                ],
                "managed": False,
                "default_permissions": (),
            },
        ),
        migrations.RunPython(pasar_a_oficina_tecnica, migrations.RunPython.noop),
        # Nombres de usuario únicos sin importar mayúsculas (el ingreso es por nombre).
        migrations.RunSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_username_sin_mayusculas_uq"
            " ON auth_user (UPPER(username));",
            "DROP INDEX IF EXISTS auth_user_username_sin_mayusculas_uq;",
        ),
    ]
