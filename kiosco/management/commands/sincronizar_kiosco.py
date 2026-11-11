import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections

from kiosco.sincronizacion import sincronizar

logger = logging.getLogger("kiosco.sincronizacion")


class Command(BaseCommand):
    help = "Envía la cola del kiosco a la base central y renueva la copia local."

    def add_arguments(self, parser):
        parser.add_argument("--una-vez", action="store_true", help="Una sola vuelta y termina.")
        parser.add_argument(
            "--forzar-copia", action="store_true", help="Renovar la copia aunque no se use."
        )

    def handle(self, *args, una_vez=False, forzar_copia=False, **opciones):
        if una_vez:
            r = sincronizar(forzar_copia=forzar_copia)
            self.stdout.write(
                f"Enviados: {r.enviados} · rechazados: {r.rechazados} · "
                f"copia renovada: {'sí' if r.copia_renovada else 'no'}"
                + (" · SIN CONEXIÓN" if r.sin_conexion else "")
            )
            return

        cada = settings.KIOSCO_SINCRONIZAR_CADA
        logger.info("Sincronización del kiosco cada %s s.", cada)
        while True:
            try:
                r = sincronizar(forzar_copia=forzar_copia)
                forzar_copia = False
                if r.enviados or r.rechazados:
                    logger.info("Enviados %s, rechazados %s.", r.enviados, r.rechazados)
            except Exception:  # el proceso no se cae: reintenta en la próxima vuelta
                logger.exception("Error inesperado al sincronizar")
                connections["default"].close()
            time.sleep(cada)
