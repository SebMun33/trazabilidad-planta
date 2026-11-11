#!/usr/bin/env bash
# Aplica migraciones con el rol dueño (app_planta_owner, DATABASE_URL_OWNER).
# La app en ejecución usa app_planta, que no puede crear ni alterar tablas.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
DJANGO_DB_OWNER=1 uv run python manage.py migrate "$@"
