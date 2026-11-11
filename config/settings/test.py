"""Tests: siempre contra Postgres (nunca SQLite), igual que en producción.

Corren como `app_planta_owner` (necesita CREATEDB en el Postgres local/CI) para
que pytest-django cree la base de tests y aplique las migraciones. Los tests de
permisos abren una conexión aparte como `app_planta`.
"""

import os

os.environ.setdefault("DJANGO_DB_OWNER", "1")

from .base import *

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
PLANTA_DISPOSITIVO = "tests"
