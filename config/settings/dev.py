"""Desarrollo local (Postgres en Docker o rama de Neon `dev-planta`)."""

from .base import *

DEBUG = env.bool("DJANGO_DEBUG", default=True)

STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
