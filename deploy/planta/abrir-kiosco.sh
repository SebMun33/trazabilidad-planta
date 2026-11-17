#!/usr/bin/env bash
# Abre Chromium en modo kiosco cuando el servidor local ya responde.
# Lo ejecuta el inicio automático de la sesión gráfica (kiosco.desktop).
set -u
URL="http://127.0.0.1:8000/kiosco/"

for _ in $(seq 1 60); do
    curl --silent --fail --output /dev/null "http://127.0.0.1:8000/salud/" && break
    sleep 2
done

# En Ubuntu, Chromium viene como snap (`chromium`) o con el nombre del paquete viejo.
NAVEGADOR="$(command -v chromium || command -v chromium-browser)"

# Sin pantallas de "restaurar sesión", traducción ni primer uso.
exec "$NAVEGADOR" --kiosk --incognito --no-first-run --noerrdialogs \
    --disable-infobars --disable-session-crashed-bubble --disable-translate \
    --password-store=basic "$URL"
