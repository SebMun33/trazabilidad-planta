"""Middleware de la app de planta."""

import logging

from django.db import OperationalError
from django.shortcuts import render

logger = logging.getLogger(__name__)


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
