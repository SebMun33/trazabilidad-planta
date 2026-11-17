# Instalación del kiosco en la PC Ubuntu de planta

La PC de planta corre solo la parte B (kiosco). Arranca sola al prenderla:
Gunicorn escucha en `127.0.0.1:8000`, el proceso de sincronización envía los
registros a Neon y Chromium abre el kiosco en pantalla completa. Si se corta
internet, el kiosco sigue registrando y envía todo cuando vuelve la conexión
(ver `decisiones/0006-kiosco-sin-conexion.md`).

| Pieza | Archivo | Qué hace |
|---|---|---|
| `trazabilidad-kiosco.service` | `deploy/planta/systemd/` | Gunicorn con `config.settings.prod_planta` |
| `trazabilidad-sincronizacion.service` | `deploy/planta/systemd/` | `manage.py sincronizar_kiosco` (cola y copia local) |
| `trazabilidad-backup.timer` | `deploy/planta/systemd/` | Backup diario a las 21:00 (`backup.sh`), 30 días |
| `kiosco.desktop` | `deploy/planta/` | Abre Chromium en modo kiosco al iniciar la sesión |
| `planta.env.example` | `deploy/planta/` | Configuración (va a `/etc/trazabilidad-planta/planta.env`) |

Rutas: código en `/opt/trazabilidad-planta`, copia local y cola en
`/var/lib/trazabilidad-planta`, backups en `/var/backups/trazabilidad-planta`.
Los servicios corren con el usuario de sistema `trazabilidad`; la sesión gráfica,
con un usuario común (`planta`) que entra solo.

## 1. Paquetes

```bash
sudo apt update
sudo apt install -y git curl chromium-browser
```

Cliente de PostgreSQL 18 (el de Neon) para los backups, desde el repositorio
oficial de PostgreSQL:

```bash
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
sudo apt install -y postgresql-client-18
```

[uv](https://docs.astral.sh/uv/) para todo el sistema:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
```

## 2. Usuarios, carpetas y código

```bash
sudo useradd --system --home /opt/trazabilidad-planta --shell /usr/sbin/nologin trazabilidad
sudo mkdir -p /opt/trazabilidad-planta /var/lib/trazabilidad-planta \
    /var/backups/trazabilidad-planta /etc/trazabilidad-planta
sudo chown trazabilidad:trazabilidad /opt/trazabilidad-planta \
    /var/lib/trazabilidad-planta /var/backups/trazabilidad-planta
sudo chmod 750 /var/backups/trazabilidad-planta

sudo -u trazabilidad git clone https://github.com/SebMun33/trazabilidad-planta.git /opt/trazabilidad-planta
cd /opt/trazabilidad-planta
sudo -u trazabilidad env UV_PYTHON_INSTALL_DIR=/opt/trazabilidad-planta/.uv-python \
    uv sync --frozen --no-dev
```

## 3. Configuración

```bash
sudo cp deploy/planta/planta.env.example /etc/trazabilidad-planta/planta.env
sudo chown root:trazabilidad /etc/trazabilidad-planta/planta.env
sudo chmod 640 /etc/trazabilidad-planta/planta.env
sudo nano /etc/trazabilidad-planta/planta.env
```

Completar `DJANGO_SECRET_KEY` (una clave larga al azar) y `DATABASE_URL`
(conexión directa de Neon con el rol `app_planta`). Para generar la clave:

```bash
/opt/trazabilidad-planta/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Preparar la base local, los archivos estáticos y la primera copia:

```bash
cd /opt/trazabilidad-planta
correr() { sudo -u trazabilidad bash -c "set -a; . /etc/trazabilidad-planta/planta.env; set +a; $*"; }
correr .venv/bin/python manage.py migrate --database=local
correr .venv/bin/python manage.py collectstatic --noinput
correr .venv/bin/python manage.py sincronizar_kiosco --una-vez --forzar-copia
```

La última línea debe terminar sin «SIN CONEXIÓN».

## 4. Servicios

```bash
sudo cp deploy/planta/systemd/*.service deploy/planta/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trazabilidad-kiosco trazabilidad-sincronizacion trazabilidad-backup.timer
systemctl status trazabilidad-kiosco trazabilidad-sincronizacion --no-pager
curl http://127.0.0.1:8000/salud/   # debe responder: ok
```

## 5. Pantalla de kiosco

1. Crear el usuario de la sesión gráfica (sin permisos de administrador):
   `sudo adduser planta`.
2. **Configuración → Usuarios → planta → Inicio de sesión automático**.
3. Inicio automático del kiosco:

   ```bash
   sudo -u planta mkdir -p /home/planta/.config/autostart
   sudo cp deploy/planta/kiosco.desktop /home/planta/.config/autostart/
   sudo chown planta:planta /home/planta/.config/autostart/kiosco.desktop
   ```

4. En la sesión de `planta`: desactivar el bloqueo de pantalla y la suspensión
   (**Configuración → Energía / Privacidad**).
5. Reiniciar. Tiene que aparecer «¿Quién sos?» en pantalla completa.

Para salir del modo kiosco (mantenimiento): `Alt+F4`.

## 6. Actualizar a una versión nueva

```bash
cd /opt/trazabilidad-planta
sudo -u trazabilidad git pull
sudo -u trazabilidad env UV_PYTHON_INSTALL_DIR=/opt/trazabilidad-planta/.uv-python uv sync --frozen --no-dev
correr .venv/bin/python manage.py migrate --database=local
correr .venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart trazabilidad-kiosco trazabilidad-sincronizacion
```

(`correr` es la función definida en el paso 3.) Las migraciones de la base
central no se corren desde acá: ver `despliegue_oficina.md`.

## 7. Diagnóstico

| Síntoma | Qué mirar |
|---|---|
| Pantalla en blanco o «no se puede conectar» | `systemctl status trazabilidad-kiosco` y `journalctl -u trazabilidad-kiosco -n 50` |
| «N pendientes de envío» que no baja | Conexión a internet; `journalctl -u trazabilidad-sincronizacion -n 50` |
| «N con error: avisá a oficina» | Registros que la base central rechazó: `journalctl -u trazabilidad-sincronizacion` muestra el motivo |
| La lista no refleja cambios de oficina | La barra muestra la hora de la copia; con internet se renueva cada minuto mientras se usa el kiosco |
| Backups | `systemctl list-timers trazabilidad-backup.timer` y `journalctl -u trazabilidad-backup` |

Restaurar la base central desde un backup (en una base vacía o rama nueva):
`pg_restore --no-owner --dbname=<url> central_AAAA-MM-DD_HHMM.dump`.
