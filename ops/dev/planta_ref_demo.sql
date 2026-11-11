-- =============================================================================
-- SOLO DESARROLLO Y TESTS. Nunca correr en Neon.
--
-- Reemplaza lo que publica dbt en `planta_ref` mientras esas vistas no existan:
-- crea tablas ficticias en `planta_demo` y vistas en `planta_ref` con la misma
-- estructura (contrato) que van a tener las vistas reales de dbt.
-- Ver docs/integracion_dw.md.
-- =============================================================================
\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS planta_demo AUTHORIZATION dbt_local;

SET ROLE dbt_local;

CREATE TABLE IF NOT EXISTS planta_demo.maquinas (
    maquina_id   integer PRIMARY KEY,
    nombre       text NOT NULL,
    nombre_corto text
);

CREATE TABLE IF NOT EXISTS planta_demo.clientes (
    cliente_id   integer PRIMARY KEY,
    razon_social text NOT NULL
);

CREATE TABLE IF NOT EXISTS planta_demo.planos (
    plano       text PRIMARY KEY,
    descripcion text
);

CREATE TABLE IF NOT EXISTS planta_demo.pedidos_lineas (
    pedido_id          integer NOT NULL,
    renglon            integer NOT NULL,
    orden_compra       text,
    fecha_pedido       date,
    cliente_id         integer,
    plano              text NOT NULL,
    cantidad_pedida    numeric(12, 2),
    cantidad_entregada numeric(12, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (pedido_id, renglon)
);

CREATE TABLE IF NOT EXISTS planta_demo.cotizaciones_lineas (
    cotizacion_id    integer NOT NULL,
    renglon          integer NOT NULL,
    fecha_cotizacion date,
    cliente_id       integer,
    plano            text NOT NULL,
    cantidad         numeric(12, 2),
    tiene_pedido     boolean NOT NULL DEFAULT false,
    PRIMARY KEY (cotizacion_id, renglon)
);

CREATE TABLE IF NOT EXISTS planta_demo.rutas (
    plano         text NOT NULL,
    operacion_nro integer NOT NULL,
    maquina_id    integer,
    descripcion   text,
    piezas_hora   numeric(12, 2),
    PRIMARY KEY (plano, operacion_nro)
);

CREATE TABLE IF NOT EXISTS planta_demo.cargas (
    carga_id serial PRIMARY KEY,
    fin      timestamptz NOT NULL DEFAULT now()
);

-- El dueño de la app (que corre tests y el seed) necesita poder cargar datos ficticios.
GRANT USAGE ON SCHEMA planta_demo TO app_planta_owner;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA planta_demo
    TO app_planta_owner;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA planta_demo TO app_planta_owner;
GRANT USAGE ON SCHEMA planta_demo TO app_planta;
GRANT SELECT ON ALL TABLES IN SCHEMA planta_demo TO app_planta;

-- --- Vistas de planta_ref (contrato con dbt) ---------------------------------
CREATE OR REPLACE VIEW planta_ref.maquinas AS
SELECT maquina_id, nombre, nombre_corto
FROM planta_demo.maquinas;

CREATE OR REPLACE VIEW planta_ref.pedidos_pendientes AS
SELECT
    format('%s-%s', l.pedido_id, l.renglon)          AS pedido_linea_id,
    l.pedido_id,
    l.orden_compra,
    l.fecha_pedido,
    l.cliente_id,
    c.razon_social                                    AS cliente,
    l.plano,
    p.descripcion                                     AS plano_descripcion,
    l.cantidad_pedida,
    l.cantidad_entregada,
    l.cantidad_pedida - l.cantidad_entregada          AS cantidad_pendiente
FROM planta_demo.pedidos_lineas l
LEFT JOIN planta_demo.clientes c USING (cliente_id)
LEFT JOIN planta_demo.planos p USING (plano)
WHERE l.cantidad_pedida - l.cantidad_entregada > 0;

CREATE OR REPLACE VIEW planta_ref.cotizaciones_sin_pedido AS
SELECT
    format('%s-%s', l.cotizacion_id, l.renglon)      AS cotizacion_linea_id,
    l.cotizacion_id,
    l.fecha_cotizacion,
    l.cliente_id,
    c.razon_social                                    AS cliente,
    l.plano,
    p.descripcion                                     AS plano_descripcion,
    l.cantidad
FROM planta_demo.cotizaciones_lineas l
LEFT JOIN planta_demo.clientes c USING (cliente_id)
LEFT JOIN planta_demo.planos p USING (plano)
WHERE NOT l.tiene_pedido;

CREATE OR REPLACE VIEW planta_ref.rutas AS
SELECT
    format('%s#%s', plano, operacion_nro)            AS ruta_id,
    plano,
    operacion_nro,
    maquina_id,
    descripcion,
    piezas_hora
FROM planta_demo.rutas;

CREATE OR REPLACE VIEW planta_ref.ultima_publicacion AS
SELECT max(fin) AS publicado_en
FROM planta_demo.cargas;

RESET ROLE;
