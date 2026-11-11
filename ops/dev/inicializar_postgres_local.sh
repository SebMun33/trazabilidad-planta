#!/usr/bin/env bash
# Prepara un Postgres local (Docker o servicio de CI) igual que Neon:
# roles, esquemas, permisos y vistas de ejemplo de planta_ref.
#
# Se aplica también a `template1`, así la base de tests que crea pytest-django
# (CREATE DATABASE test_...) ya nace con esquemas, permisos y vistas.
#
# Variables: PGHOST, PGPORT, PGUSER (superusuario), PGPASSWORD, PGDATABASE_APP
# (base de desarrollo, default "planta"). Contraseñas SOLO de desarrollo local.
set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_APP="${PGDATABASE_APP:-planta}"
PW_OWNER="${PW_APP_PLANTA_OWNER:-owner_local}"
PW_APP="${PW_APP_PLANTA:-app_local}"

psql -v ON_ERROR_STOP=1 -d postgres <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbt_local') THEN
        CREATE ROLE dbt_local LOGIN PASSWORD 'dbt_local';
    END IF;
END
\$\$;
SQL

for db in template1 "$DB_APP"; do
    psql -q -d "$db" -v rol_dbt=dbt_local -v pw_owner="$PW_OWNER" -v pw_app="$PW_APP" \
         -f "$OPS_DIR/01_neon_planta.sql"
    psql -q -v ON_ERROR_STOP=1 -d "$db" -f "$OPS_DIR/dev/planta_ref_demo.sql"
done

# Solo en local: el dueño crea la base de tests de pytest-django.
psql -q -v ON_ERROR_STOP=1 -d postgres -c "ALTER ROLE app_planta_owner CREATEDB"
echo "Postgres local listo (base: $DB_APP)."
