-- =============================================================================
-- Roles, esquemas y permisos de la app de planta en Postgres (Neon).
--
-- Idempotente: se puede correr las veces que haga falta.
-- Se corre con psql como dueño de la base (en Neon, `neondb_owner`):
--
--   psql "$DATABASE_URL_ADMIN" -v ON_ERROR_STOP=1 \
--        -v rol_dbt=neondb_owner \
--        -v pw_owner="$PW_APP_PLANTA_OWNER" -v pw_app="$PW_APP_PLANTA" \
--        -f ops/01_neon_planta.sql
--
-- Variables (todas opcionales):
--   rol_dbt   rol con el que corre dbt (default: neondb_owner). Debe existir.
--   pw_owner  contraseña de app_planta_owner (si se omite, no se cambia).
--   pw_app    contraseña de app_planta       (si se omite, no se cambia).
--
-- Las contraseñas nunca se escriben en este archivo.
-- =============================================================================

\set ON_ERROR_STOP on

\if :{?rol_dbt}
\else
  \set rol_dbt neondb_owner
\endif
\if :{?pw_owner}
\else
  \set pw_owner ''
\endif
\if :{?pw_app}
\else
  \set pw_app ''
\endif

-- --- Roles -------------------------------------------------------------------
-- app_planta_owner: dueño de `planta` y `planta_app`. Solo lo usan las migraciones.
-- app_planta:       rol de la app en ejecución.
SELECT format('CREATE ROLE %I LOGIN', r)
FROM unnest(ARRAY['app_planta_owner', 'app_planta']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

SELECT format('ALTER ROLE app_planta_owner PASSWORD %L', :'pw_owner') WHERE :'pw_owner' <> ''
\gexec
SELECT format('ALTER ROLE app_planta PASSWORD %L', :'pw_app') WHERE :'pw_app' <> ''
\gexec

-- Quien corre el script necesita poder actuar como el dueño para crear los
-- esquemas a su nombre y definir sus default privileges.
GRANT app_planta_owner TO CURRENT_USER;

ALTER ROLE app_planta_owner SET search_path = planta_app, planta, planta_ref;
ALTER ROLE app_planta       SET search_path = planta_app, planta, planta_ref;

SELECT format('GRANT CONNECT ON DATABASE %I TO app_planta_owner, app_planta', current_database())
\gexec

-- --- Esquemas ----------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS planta     AUTHORIZATION app_planta_owner;
CREATE SCHEMA IF NOT EXISTS planta_app AUTHORIZATION app_planta_owner;
-- `planta_ref` lo llena dbt (repo del data warehouse) con vistas.
SELECT format('CREATE SCHEMA IF NOT EXISTS planta_ref AUTHORIZATION %I', :'rol_dbt')
\gexec

COMMENT ON SCHEMA planta IS
    'Registro original de la app de planta. Solo se agregan filas (salvo el maestro de operarios).';
COMMENT ON SCHEMA planta_app IS
    'Tablas internas de Django (auth, sesiones, django_migrations).';
COMMENT ON SCHEMA planta_ref IS
    'Vistas publicadas por dbt que la app lee (pedidos, cotizaciones, rutas, máquinas).';

-- --- app_planta: permisos actuales -------------------------------------------
GRANT USAGE ON SCHEMA planta, planta_app, planta_ref TO app_planta;

-- planta: solo SELECT e INSERT. Sin UPDATE ni DELETE (las correcciones son filas nuevas).
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA planta TO app_planta;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA planta TO app_planta;

-- planta_app: CRUD completo (sesiones, usuarios, etc.).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA planta_app TO app_planta;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA planta_app TO app_planta;

-- planta_ref: solo lectura.
GRANT SELECT ON ALL TABLES IN SCHEMA planta_ref TO app_planta;

-- --- app_planta: permisos futuros (default privileges) -----------------------
ALTER DEFAULT PRIVILEGES FOR ROLE app_planta_owner IN SCHEMA planta
    GRANT SELECT, INSERT ON TABLES TO app_planta;
ALTER DEFAULT PRIVILEGES FOR ROLE app_planta_owner IN SCHEMA planta
    GRANT USAGE, SELECT ON SEQUENCES TO app_planta;

ALTER DEFAULT PRIVILEGES FOR ROLE app_planta_owner IN SCHEMA planta_app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_planta;
ALTER DEFAULT PRIVILEGES FOR ROLE app_planta_owner IN SCHEMA planta_app
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_planta;

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA planta_ref GRANT SELECT ON TABLES TO app_planta',
    :'rol_dbt')
\gexec

-- --- app_planta_owner: lectura de planta_ref -------------------------------
-- Para el seed de desarrollo y para tareas de mantenimiento que corren como dueño.
GRANT USAGE ON SCHEMA planta_ref TO app_planta_owner;
GRANT SELECT ON ALL TABLES IN SCHEMA planta_ref TO app_planta_owner;
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA planta_ref GRANT SELECT ON TABLES TO app_planta_owner',
    :'rol_dbt')
\gexec

-- --- dbt: lectura de `planta` ------------------------------------------------
SELECT format('GRANT USAGE ON SCHEMA planta TO %I', :'rol_dbt')
\gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA planta TO %I', :'rol_dbt')
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE app_planta_owner IN SCHEMA planta GRANT SELECT ON TABLES TO %I',
    :'rol_dbt')
\gexec
