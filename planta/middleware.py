"""Middleware de la app de planta."""

import logging
import time

from django.conf import settings
from django.db import OperationalError, connections
from django.http import HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


class SaludMiddleware:
    """Responde `/salud/` antes que todo lo demás, sin tocar la base.

    Lo usa el chequeo de salud del hosting: no pasa por la redirección a HTTPS
    ni por la validación de host, y no despierta a Neon.
    """

    RUTA = "/salud/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == self.RUTA:
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


class BaseNoDisponibleMiddleware:
    """Muestra un mensaje claro si la base no responde (p. ej., Neon despertando).

    Neon suspende el cómputo inactivo y la primera conexión puede tardar o fallar
    por `connect_timeout`. En lugar de un error 500 genérico, se responde 503 con
    una pantalla que se reintenta sola.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, OperationalError):
            logger.warning("Base de datos no disponible: %s", exception)
            return render(request, "planta/base_no_disponible.html", status=503)
        return None


class MedicionMiddleware:
    """Mide cada pedido: tiempo total, consultas, tiempo en la base y conexiones nuevas.

    - Agrega el encabezado `Server-Timing` (se ve en las herramientas del navegador).
    - Escribe una línea en el log; si el pedido supera `MEDICION_LENTO_SEGUNDOS`,
      como advertencia. Sirve para saber si la demora es de la app, de las
      consultas o de abrir la conexión con Neon.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        datos = {"consultas": 0, "base": 0.0}
        base = connections["default"]
        # La verificación de salud de la conexión corre antes (request_started):
        # si al terminar el pedido hay otro objeto de conexión, se abrió una nueva.
        conexion_previa = base.connection

        def contar(execute, sql, params, many, context):
            inicio = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                datos["consultas"] += 1
                datos["base"] += time.perf_counter() - inicio

        inicio = time.perf_counter()
        with base.execute_wrapper(contar):
            respuesta = self.get_response(request)
        total = time.perf_counter() - inicio

        respuesta["Server-Timing"] = (
            f"total;dur={total * 1000:.0f}, "
            f'db;dur={datos["base"] * 1000:.0f};desc="{datos["consultas"]} consultas"'
        )
        nivel = logging.WARNING if total >= settings.MEDICION_LENTO_SEGUNDOS else logging.INFO
        logger.log(
            nivel,
            "%s %s %s total=%.2fs base=%.2fs consultas=%d conexion_nueva=%s",
            request.method,
            request.path,
            respuesta.status_code,
            total,
            datos["base"],
            datos["consultas"],
            "sí" if datos["consultas"] and base.connection is not conexion_previa else "no",
        )
        return respuesta
