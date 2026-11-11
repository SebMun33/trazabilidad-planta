# 0005. Esquemas de Postgres, DDL explícito y `search_path`

- **Estado:** aceptada
- **Fecha:** 2026-11-10

## Contexto

La app comparte la base de Neon con el data warehouse (`raw`, `staging`, `core`,
`marts`). Necesita tres esquemas:

| Esquema      | Dueño              | Contenido                                       |
|--------------|--------------------|-------------------------------------------------|
| `planta`     | `app_planta_owner` | Registro original de la app (solo agregar filas) |
| `planta_app` | `app_planta_owner` | Tablas internas de Django                       |
| `planta_ref` | rol de dbt         | Vistas que publica dbt y la app lee             |

Django no tiene soporte nativo de esquemas. Las alternativas evaluadas:

1. `db_table = 'planta"."evento'`: truco de comillas que depende de cómo Django
   arma los identificadores; frágil y confuso.
2. Un *database router* con dos alias de conexión: duplica conexiones y
   complica las transacciones que tocan los dos esquemas.
3. **DDL explícito con `RunSQL` + modelos `managed = False` + `search_path`.**

## Decisión

Opción 3:

- La migración `planta.0001` aplica `planta/sql/0001_planta.sql`, que crea las
  tablas con nombre calificado (`planta.evento`), CHECKs, índices, comentarios y
  un trigger que impide `UPDATE`/`DELETE`. Los modelos de esas tablas son
  `managed = False` (Django solo guarda su estado).
- La conexión fija `search_path = planta_app, planta, planta_ref`. Así las tablas
  propias de Django (auth, sesiones, `django_migrations`) se crean en
  `planta_app`, y los modelos usan nombres simples.
- Las columnas de texto opcionales son `NULL` (no `''`), porque el esquema es el
  contrato con dbt y ahí `NULL` significa "sin dato".
- Dos credenciales: migraciones, seed y tests usan `app_planta_owner`
  (`DJANGO_DB_OWNER=1`); la app en ejecución usa `app_planta`.
- Los esquemas y roles los crea `ops/01_neon_planta.sql` **antes** de migrar.

## Consecuencias

- El DDL de `planta` se lee y revisa como SQL, igual que lo va a consumir dbt.
- Cambios futuros en `planta` son migraciones `RunSQL` nuevas, aditivas
  (columnas nullable), y hay que reflejarlos en el modelo a mano.
  `makemigrations --check` en CI detecta si el estado de Django quedó desfasado.
- Si se corre `migrate` sin haber aplicado `ops/01_neon_planta.sql`, falla de
  entrada (no existe `planta_app`): es intencional.
- En local y CI, el mismo script se aplica a `template1`, así la base de tests
  que crea pytest-django ya nace con esquemas, permisos y vistas de ejemplo.
