"""Carga datos ficticios de demo. Solo para Postgres local o CI (requiere `planta_demo`)."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from planta.demo import cargar_demo


class Command(BaseCommand):
    help = "Carga máquinas, pedidos, cotizaciones, rutas y operarios FICTICIOS (solo desarrollo)."

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            cur.execute("SELECT to_regnamespace('planta_demo') IS NOT NULL")
            if not cur.fetchone()[0]:
                raise CommandError(
                    "No existe el esquema planta_demo. Este comando es solo para el Postgres "
                    "local (docker compose) o CI. Nunca se corre contra Neon."
                )
        with transaction.atomic():
            resumen = cargar_demo()
        self.stdout.write(self.style.SUCCESS(f"Datos de demo cargados: {resumen}"))
