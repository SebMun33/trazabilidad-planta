"""Ajustes comunes a los dos despliegues productivos."""

from .base import *

DEBUG = False

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
