"""Parte A (oficina): desplegada en la nube, accesible desde internet por HTTPS."""

from .prod import *

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "same-origin"

# No se pide inclusión en la lista de precarga HSTS de los navegadores: es
# difícil de revertir y el dominio definitivo todavía no está decidido.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
