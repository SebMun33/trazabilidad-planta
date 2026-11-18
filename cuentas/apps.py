from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CuentasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cuentas"
    verbose_name = "Cuentas y roles"

    def ready(self):
        from . import senales  # noqa: F401 - conecta las señales de operarios
        from .roles import sincronizar_roles

        post_migrate.connect(sincronizar_roles, sender=self)
