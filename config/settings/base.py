"""Settings comunes a todos los entornos.

Toda la configuración sensible o dependiente del entorno sale de variables de
entorno (ver `.env.example`). Los módulos `dev`, `test`, `prod_oficina` y
`prod_planta` importan este archivo y ajustan lo propio.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_htmx",
    "planta",
    "oficina",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "planta.middleware.BaseNoDisponibleMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "oficina.contexto.perfil",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos -----------------------------------------------------------
# Una sola conexión a Postgres (Neon, conexión directa con sslmode=require).
# El search_path ubica las tablas de Django en `planta_app` y deja visibles las
# tablas de dominio (`planta`) y las vistas que publica dbt (`planta_ref`).
# Ver docs/decisiones/0005-esquemas-y-search-path.md.
DB_SEARCH_PATH = "planta_app,planta,planta_ref"

# Dos credenciales: la app en ejecución usa `app_planta` (DATABASE_URL, sin
# UPDATE/DELETE en `planta`); migraciones, seed y tests usan el dueño
# `app_planta_owner` (DATABASE_URL_OWNER) activando DJANGO_DB_OWNER=1.
DB_COMO_DUENO = env.bool("DJANGO_DB_OWNER", default=False)
DATABASES = {"default": env.db("DATABASE_URL_OWNER" if DB_COMO_DUENO else "DATABASE_URL")}
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].update(
    {
        "options": f"-c search_path={DB_SEARCH_PATH}",
        # Neon suspende el cómputo inactivo: el primer connect puede tardar.
        "connect_timeout": env.int("DB_CONNECT_TIMEOUT", default=10),
    }
)
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalización ----------------------------------------------------
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

# --- Estáticos (WhiteNoise) --------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "oficina:pendientes"
LOGOUT_REDIRECT_URL = "login"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}

# --- Dominio -----------------------------------------------------------------
# Identifica qué equipo grabó cada evento (columna `evento.dispositivo`).
PLANTA_DISPOSITIVO = env("PLANTA_DISPOSITIVO", default="desarrollo")
