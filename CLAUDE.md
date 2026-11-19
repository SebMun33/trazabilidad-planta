# CLAUDE.md

Guía para trabajar en este repositorio con Claude Code.

## Qué es

App Django para una tornería:

- **Oficina** (`oficina/`, nube en Render): prepara la lista de pendientes desde
  pedidos y cotizaciones de FoxPro.
- **Kiosco** (`kiosco/`, PC Ubuntu de planta): los operarios registran avances.

Resumen y arquitectura en `README.md`; decisiones en `docs/decisiones/`.

## Reglas que no se rompen

- **Nunca conectarse a la rama `main` (producción) de Neon.** Desarrollo:
  Postgres local en Docker o la rama de Neon `dev-planta`. Los tests corren
  solo contra Postgres local (`config/settings/test.py` rechaza Neon).
- **Sin secretos en el repo.** Todo va por `.env`; se documenta en
  `.env.example`. No usar credenciales del data warehouse (`neondb_owner`):
  dbt lo corre el usuario.
- **Sin datos reales.** Seed y capturas son ficticios (`planta/demo.py`).
- **El esquema `planta` solo agrega filas** (trigger + permisos). Nada de
  `UPDATE`/`DELETE`: anulaciones, revisiones o reaperturas nuevas. Única
  excepción: `planta.operario` (nombre, activo, usuario_id).
- **Los operarios nunca ven plata.** Todo importe va detrás de
  `perms.cuentas.ver_importes`; la copia del kiosco (`kiosco/foto.py`) no
  incluye precios, costos ni importes (hay un test).
- Las vistas del kiosco **no tocan la base `default`**: solo la SQLite `local`.
  Única excepción: el modo prueba del superusuario (`cuentas/prueba.py`,
  `kiosco/acceso.py`), que sincroniza dentro del pedido. El usuario «operario»
  queda oculto para todos menos el superusuario.

## Comandos

En Windows, uv está en `%APPDATA%\Python\Python311\Scripts` (agregarlo al PATH
en Bash).

```bash
docker compose up -d --wait        # Postgres 18 local con roles, esquemas y vistas de ejemplo
uv sync
bash ops/migrar.sh                 # migrate con el rol dueño (DJANGO_DB_OWNER=1)
DJANGO_DB_OWNER=1 uv run python manage.py seed_demo
uv run pytest                      # antes de cada commit
uv run ruff format . && uv run ruff check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py runserver  # oficina en /, kiosco en /kiosco/ (solo dev)
```

## Base de datos

| Esquema | Dueño | Qué hay |
|---|---|---|
| `planta` | `app_planta_owner` | registro de la app; DDL en `planta/sql/*.sql` vía `RunSQL`, modelos `managed = False` |
| `planta_app` | `app_planta_owner` | tablas de Django |
| `planta_ref` | rol de dbt | vistas que publica dbt; la app solo lee |

- `search_path = planta_app, planta, planta_ref`.
- Runtime: rol `app_planta`. Migraciones, seed y tests: `app_planta_owner`
  (`DJANGO_DB_OWNER=1`).
- Cambios en `planta`: migración `RunSQL` nueva, aditiva, y reflejarla en
  `planta/models.py`.
- Cambios en `planta_ref`: primero `ops/dev/planta_ref_demo.sql` + modelo +
  tests acá; después el modelo dbt del warehouse. Ver `docs/integracion_dw.md`.
  Al desplegar, dbt se corre **antes** de subir la app.

## Mapa del código

- `config/settings/`: `base`, `dev`, `test`, `prod_oficina` (Render),
  `prod_planta` (kiosco, `config.urls_planta`).
- `planta/servicios/`: lógica de negocio.
  - `trabajos.py`: alta, revisión, retiro.
  - `estado.py`: estado derivado de eventos (función pura, la comparte el kiosco).
  - `jornada.py`: anulación, cierre del día.
  - `notas.py`, `avisos.py`.
- `cuentas/`: roles (`roles.py`), ingreso por nombre, admin de usuarios.
  Permisos en `cuentas.Permisos`; los grupos se sincronizan en `post_migrate`.
- `oficina/`: vistas con HTMX; decoradores de permiso en `permisos.py`.
- `kiosco/`: `local.py` (estado local), `sincronizacion.py` (cola de envío),
  comando `sincronizar_kiosco`, router de la base `local`.
- `deploy/planta/`: systemd y respaldo de la PC Ubuntu. `render.yaml`: oficina.

## Convenciones

- Interfaz, docs, commits y comentarios en **español rioplatense**
  (vos, «revisá»). Fechas `d/m/Y`, montos `$ 93.000,00` (`floatformat:"2g"`).
- **Conventional Commits** chicos (`feat(oficina): …`, `fix(kiosco): …`).
  Tests y ruff en verde antes de cada commit.
- Proponer un plan por etapas y esperar aprobación antes de cambios grandes.
- Decisiones de arquitectura nuevas: ADR en `docs/decisiones/NNNN-titulo.md`.
- Textos opcionales en `planta` son `NULL`, no `''` (contrato con dbt).
