#!/usr/bin/env bash
# Entrypoint de inicialización del contenedor postgres (solo la primera vez).
set -euo pipefail
export PGUSER="$POSTGRES_USER" PGDATABASE_APP="$POSTGRES_DB"
bash /ops/dev/inicializar_postgres_local.sh
