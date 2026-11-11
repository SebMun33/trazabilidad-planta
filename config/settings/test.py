"""Tests: siempre contra Postgres (nunca SQLite), igual que en producción.

Usan su propia variable `TEST_DATABASE_URL` (por defecto, el Postgres local de
docker compose) y NUNCA la base de `.env`, que puede apuntar a Neon. Corren como
`app_planta_owner`, que en local/CI tiene CREATEDB para que pytest-django cree la
base de tests. Los tests de permisos abren una conexión aparte como `app_planta`.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *

_db_tests = env.db(
    "TEST_DATABASE_URL",
    default="postgres://app_planta_owner:owner_local@localhost:5432/planta",
)
if (_db_tests.get("HOST") or "").endswith("neon.tech"):
    raise ImproperlyConfigured("Los tests no se corren contra Neon: usá el Postgres local.")

DATABASES["default"] = {
    **_db_tests,
    "OPTIONS": {"options": f"-c search_path={DB_SEARCH_PATH}", "connect_timeout": 5},
    "CONN_MAX_AGE": 0,
    "CONN_HEALTH_CHECKS": False,
}

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
PLANTA_DISPOSITIVO = "tests"
