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
    "cuentas",
    "planta",
    "oficina",
    "kiosco",
]

MIDDLEWARE = [
    "planta.middleware.SaludMiddleware",
    "planta.middleware.MedicionMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
# Reusar la conexión entre pedidos evita pagar en cada click el saludo TLS con
# Neon (en otra región que el hosting). Si Neon suspende el cómputo, la
# verificación de salud la descarta y abre otra.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=300)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Base `local` (SQLite): copia y cola del kiosco de planta, para seguir
# registrando sin conexión. Solo la usan los modelos de `kiosco` (ver router).
DATABASES["local"] = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": env("KIOSCO_DB", default=str(BASE_DIR / "kiosco.sqlite3")),
    "OPTIONS": {"timeout": 10},
}
DATABASE_ROUTERS = ["kiosco.router.KioscoRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalización ----------------------------------------------------
# Solo español de Argentina, sin importar el idioma del navegador (formato de
# números y montos: $ 93.000,00).
LANGUAGE_CODE = "es-ar"
LANGUAGES = [("es-ar", "Español (Argentina)")]
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

# Pedidos más lentos que esto se registran como advertencia (MedicionMiddleware).
MEDICION_LENTO_SEGUNDOS = env.float("MEDICION_LENTO_SEGUNDOS", default=2.0)

# --- Dominio -----------------------------------------------------------------
# Identifica qué equipo grabó cada evento (columna `evento.dispositivo`).
PLANTA_DISPOSITIVO = env("PLANTA_DISPOSITIVO", default="desarrollo")

# --- Avisos (notas nuevas, etc.) ---------------------------------------------
# Canales activos, separados por coma (ver planta/servicios/avisos.py).
AVISOS_CANALES = env.list("AVISOS_CANALES", default=["planta.servicios.avisos.CanalRegistro"])
# Correo saliente: p. ej. EMAIL_URL=smtp+tls://avisos%40midominio.com.ar:CLAVE@mail.midominio.com.ar:587
_correo = env.email_url("EMAIL_URL", default="consolemail://")
EMAIL_BACKEND = _correo["EMAIL_BACKEND"]
EMAIL_HOST = _correo.get("EMAIL_HOST", "")
EMAIL_PORT = _correo.get("EMAIL_PORT")
EMAIL_HOST_USER = _correo.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _correo.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _correo.get("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = _correo.get("EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Trazabilidad de planta <avisos@localhost>")

# --- Kiosco (parte B) ---------------------------------------------------------
# Las pantallas del kiosco no piden contraseña: solo responden a estas IP (el
# navegador de la misma PC). En la nube (oficina) el kiosco no se publica.
KIOSCO_HABILITADO = env.bool("KIOSCO_HABILITADO", default=False)
KIOSCO_IPS_PERMITIDAS = env.list("KIOSCO_IPS_PERMITIDAS", default=["127.0.0.1", "::1"])
KIOSCO_DESHACER_SEGUNDOS = 60
# Cada cuánto sincroniza el proceso de fondo y cuándo se considera vieja la copia.
KIOSCO_SINCRONIZAR_CADA = env.int("KIOSCO_SINCRONIZAR_CADA", default=5)
KIOSCO_COPIA_VIEJA_SEGUNDOS = env.int("KIOSCO_COPIA_VIEJA_SEGUNDOS", default=120)
# Mientras el kiosco se usa, la copia local se renueva cada KIOSCO_COPIA_CADA
# segundos; si nadie lo usa hace KIOSCO_ACTIVO_MINUTOS, no se consulta a Neon.
KIOSCO_COPIA_CADA = env.int("KIOSCO_COPIA_CADA", default=60)
KIOSCO_ACTIVO_MINUTOS = env.int("KIOSCO_ACTIVO_MINUTOS", default=10)
# Sin actividad, vuelve a la pantalla de elegir operario.
KIOSCO_INACTIVIDAD_SEGUNDOS = env.int("KIOSCO_INACTIVIDAD_SEGUNDOS", default=120)
