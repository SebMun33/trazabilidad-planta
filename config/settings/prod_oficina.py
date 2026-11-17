"""Parte A (oficina): desplegada en la nube (Render), accesible por HTTPS.

Ver docs/despliegue_oficina.md.
"""

import os

from .prod import *

# Render publica el servicio en <nombre>.onrender.com y avisa el host en esta
# variable; el dominio propio (p. ej. planta.midominio.com.ar) va en
# DJANGO_ALLOWED_HOSTS. Los orígenes CSRF se derivan de los hosts.
if render_host := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, render_host]
CSRF_TRUSTED_ORIGINS = [
    *CSRF_TRUSTED_ORIGINS,
    *(f"https://{h}" for h in ALLOWED_HOSTS if h and not h.startswith(".") and h != "*"),
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
# Alcanza solo a los subdominios del host de la app (*.planta.midominio), no al
# dominio principal ni a sus otros subdominios.
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "same-origin"

# No se pide inclusión en la lista de precarga HSTS de los navegadores: es
# difícil de revertir y el dominio principal lo usa otro sitio.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
