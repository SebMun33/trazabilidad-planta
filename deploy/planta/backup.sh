#!/usr/bin/env bash
# Backup diario de la PC de planta (lo corre trazabilidad-backup.timer).
#
# - Base central: pg_dump de los esquemas de la app (planta y planta_app), con
#   el rol app_planta (solo lectura alcanza). Neon guarda historia de pocas horas
#   en el plan Free: esta copia es la que permite volver días atrás.
# - Copia local del kiosco (SQLite): incluye la cola de eventos sin enviar.
# - Rotación: borra los archivos de más de BACKUP_DIAS días.
# - Opcional: sube los archivos del día por FTP con TLS (BACKUP_FTP_*).
set -euo pipefail

: "${DATABASE_URL:?falta DATABASE_URL}"
: "${KIOSCO_DB:?falta KIOSCO_DB}"
DESTINO="${BACKUP_DIR:-/var/backups/trazabilidad-planta}"
DIAS="${BACKUP_DIAS:-30}"
FECHA="$(date +%Y-%m-%d_%H%M)"
PYTHON=/opt/trazabilidad-planta/.venv/bin/python

umask 077
mkdir -p "$DESTINO"
archivos=()

# 1) Base central
central="$DESTINO/central_$FECHA.dump"
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges \
    --schema=planta --schema=planta_app --file="$central"
archivos+=("$central")

# 2) Copia local del kiosco (API de backup de SQLite: consistente aunque esté en uso)
if [[ -f "$KIOSCO_DB" ]]; then
    local_db="$DESTINO/kiosco_$FECHA.sqlite3"
    "$PYTHON" - "$KIOSCO_DB" "$local_db" <<'PY'
import sqlite3, sys
origen, destino = sys.argv[1], sys.argv[2]
with sqlite3.connect(origen) as o, sqlite3.connect(destino) as d:
    o.backup(d)
PY
    gzip -f "$local_db"
    archivos+=("$local_db.gz")
fi

# 3) Rotación local
find "$DESTINO" -type f \( -name 'central_*.dump' -o -name 'kiosco_*.sqlite3.gz' \) \
    -mtime +"$DIAS" -delete

# 4) Copia fuera de la planta (opcional). La clave va por stdin, no en la línea de comando.
if [[ -n "${BACKUP_FTP_HOST:-}" ]]; then
    remoto="${BACKUP_FTP_DIR:-/backups/trazabilidad-planta}"
    for archivo in "${archivos[@]}"; do
        printf 'user = "%s:%s"\n' "$BACKUP_FTP_USUARIO" "$BACKUP_FTP_CLAVE" |
            curl --silent --show-error --fail --ssl-reqd --ftp-create-dirs --config - \
                --upload-file "$archivo" "ftp://$BACKUP_FTP_HOST$remoto/"
    done
fi

echo "Backup terminado: ${archivos[*]}"
