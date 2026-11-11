"""Parte B (planta): PC Ubuntu en la planta, Gunicorn escucha solo en 127.0.0.1.

No hay TLS porque el tráfico no sale del equipo (Chromium en modo kiosco contra
localhost). Por eso las advertencias de `check --deploy` sobre HTTPS se silencian
de forma explícita y documentada.
"""

from .prod import *

SILENCED_SYSTEM_CHECKS = [
    "security.W004",  # SECURE_HSTS_SECONDS: sin HTTPS en localhost
    "security.W008",  # SECURE_SSL_REDIRECT
    "security.W012",  # SESSION_COOKIE_SECURE
    "security.W016",  # CSRF_COOKIE_SECURE
]
