# 0003 — Base compartida con el data warehouse, en Neon

- Estado: aceptada
- Fecha: 2026-11-10

## Contexto

Los pedidos, cotizaciones, clientes y hojas de ruta ya están en un data
warehouse en Neon (Postgres), cargado desde FoxPro y modelado con dbt. La app
necesita esos datos para preparar trabajos, y el warehouse va a necesitar los
eventos de planta para medir tiempos reales. Las opciones eran una base propia
para la app (con copias entre las dos) o la misma base con esquemas separados.

## Decisión

- **La misma base de Neon**, con esquemas separados
  ([0005](0005-esquemas-y-search-path.md)):
  - la app lee solo las vistas de `planta_ref`, que publica dbt (el contrato
    está en [`integracion_dw.md`](../integracion_dw.md));
  - la app escribe solo en `planta` (registro) y `planta_app` (Django);
  - dbt puede leer `planta`, pero nunca escribe ahí.
- **Roles de mínimo privilegio:** `app_planta` (en ejecución) y
  `app_planta_owner` (migraciones). Ninguno lee `raw`, `core` ni `marts`.
- **Nunca se desarrolla contra la rama principal.** Para desarrollo hay dos
  caminos:
  - Postgres 18 local en Docker, con vistas de ejemplo y datos ficticios;
  - la rama de Neon `dev-planta`, copia aislada de main, con su propio target
    de dbt.
  Los tests corren **solo** contra Postgres local: la configuración rechaza un
  host de Neon.
- Conexión directa (sin pooler), con `CONN_MAX_AGE` corto, para que Neon pueda
  suspender el cómputo cuando nadie usa la app.

## Consecuencias

- Sin sincronización entre bases: dbt cruza eventos y pedidos con un `JOIN`.
- El plan gratuito de Neon tiene 1 GB por proyecto; el registro de planta suma
  poco, pero conviene vigilar el tamaño total del warehouse.
- Un cambio en el warehouse no rompe la app mientras las vistas de
  `planta_ref` respeten el contrato.
- Si Neon no responde, la oficina no funciona; el kiosco sí, con su copia local.
