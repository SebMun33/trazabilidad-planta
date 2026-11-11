-- Esquema `planta`: registro original de la app.
-- Lo aplica la migración planta.0001 conectada como app_planta_owner.
-- Contrato con el data warehouse: cambios solo aditivos (columnas nuevas nullable).

-- Impide UPDATE y DELETE incluso al dueño de las tablas (defensa en profundidad:
-- el rol de la app ya no tiene esos permisos).
CREATE FUNCTION planta.impedir_modificacion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'planta.%: solo se permite agregar filas (% bloqueado)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

-- --- operario ----------------------------------------------------------------
CREATE TABLE planta.operario (
    operario_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      text        NOT NULL UNIQUE CHECK (btrim(nombre) <> ''),
    activo      boolean     NOT NULL DEFAULT true,
    creado_en   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE planta.operario IS
    'Maestro de operarios de planta. Única tabla de planta que admite UPDATE (nombre, activo).';

-- --- trabajo -----------------------------------------------------------------
CREATE TABLE planta.trabajo (
    trabajo_id uuid        PRIMARY KEY,
    creado_en  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE planta.trabajo IS
    'Identidad de un trabajo pendiente (pieza a fabricar). Sus datos están en trabajo_revision.';

-- --- trabajo_revision --------------------------------------------------------
CREATE TABLE planta.trabajo_revision (
    revision_id            uuid          PRIMARY KEY,
    trabajo_id             uuid          NOT NULL REFERENCES planta.trabajo,
    revision               integer       NOT NULL CHECK (revision >= 1),
    tipo                   text          NOT NULL CHECK (tipo IN ('alta', 'cambio', 'retiro')),
    origen                 text          NOT NULL CHECK (origen IN ('pedido', 'cotizacion', 'manual')),
    origen_ref             text,
    pedido_id              integer,
    cotizacion_id          integer,
    plano                  text          NOT NULL CHECK (btrim(plano) <> ''),
    plano_descripcion      text,
    cliente_id             integer,
    cliente_nombre         text,
    cantidad               numeric(12, 2) CHECK (cantidad IS NULL OR cantidad > 0),
    urgencia               smallint      NOT NULL DEFAULT 1 CHECK (urgencia BETWEEN 1 AND 3),
    fecha_entrega_estimada date,
    observaciones          text,
    creado_por             text          NOT NULL,
    creado_en              timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (trabajo_id, revision),
    CHECK ((tipo = 'alta') = (revision = 1))
);
COMMENT ON TABLE planta.trabajo_revision IS
    'Versiones de cada trabajo (alta, cambio, retiro). La vigente es la de mayor revision.';
COMMENT ON COLUMN planta.trabajo_revision.origen_ref IS
    'Clave del renglón de origen en planta_ref (pedido_linea_id o cotizacion_linea_id).';
COMMENT ON COLUMN planta.trabajo_revision.urgencia IS '1 = normal, 2 = alta, 3 = urgente.';

-- --- trabajo_operacion -------------------------------------------------------
CREATE TABLE planta.trabajo_operacion (
    trabajo_operacion_id uuid     PRIMARY KEY,
    revision_id          uuid     NOT NULL REFERENCES planta.trabajo_revision,
    operacion_id         uuid     NOT NULL,
    operacion_nro        smallint NOT NULL CHECK (operacion_nro >= 1),
    maquina_id           integer,
    descripcion          text,
    observaciones        text,
    UNIQUE (revision_id, operacion_id),
    UNIQUE (revision_id, operacion_nro)
);
COMMENT ON TABLE planta.trabajo_operacion IS
    'Hoja de ruta de cada revisión. operacion_id es estable entre revisiones.';

-- --- evento ------------------------------------------------------------------
CREATE TABLE planta.evento (
    evento_id       uuid           PRIMARY KEY,
    tipo            text           NOT NULL
                    CHECK (tipo IN ('empezado', 'pausado', 'terminado', 'anulacion')),
    trabajo_id      uuid           NOT NULL REFERENCES planta.trabajo,
    operacion_id    uuid,
    maquina_id      integer,
    operario_id     integer        REFERENCES planta.operario,
    ocurrido_en     timestamptz    NOT NULL,
    registrado_en   timestamptz    NOT NULL DEFAULT now(),
    cantidad        numeric(12, 2) CHECK (cantidad IS NULL OR cantidad >= 0),
    observaciones   text,
    anula_evento_id uuid           REFERENCES planta.evento,
    registrado_por  text,
    dispositivo     text           NOT NULL,
    -- Una anulación siempre apunta al evento que anula; los demás tipos nunca.
    CONSTRAINT evento_anulacion_ck CHECK ((tipo = 'anulacion') = (anula_evento_id IS NOT NULL)),
    -- Los eventos de trabajo identifican operación y operario.
    CONSTRAINT evento_trabajo_ck CHECK (
        tipo = 'anulacion' OR (operacion_id IS NOT NULL AND operario_id IS NOT NULL)
    ),
    CONSTRAINT evento_no_autoanula_ck CHECK (anula_evento_id IS DISTINCT FROM evento_id)
);
-- Un evento se anula una sola vez.
CREATE UNIQUE INDEX evento_anula_evento_uq ON planta.evento (anula_evento_id)
    WHERE anula_evento_id IS NOT NULL;
CREATE INDEX evento_trabajo_operacion_ix ON planta.evento (trabajo_id, operacion_id);
CREATE INDEX evento_ocurrido_en_ix ON planta.evento (ocurrido_en);
COMMENT ON TABLE planta.evento IS
    'Eventos de planta (empezado, pausado, terminado) y anulaciones. Solo se agregan filas.';
COMMENT ON COLUMN planta.evento.evento_id IS
    'Generado por la app antes de grabar; el INSERT es idempotente (ON CONFLICT DO NOTHING).';
COMMENT ON COLUMN planta.evento.dispositivo IS 'Equipo que registró el evento (kiosco, oficina).';

-- --- cierre_dia --------------------------------------------------------------
CREATE TABLE planta.cierre_dia (
    cierre_id      uuid        PRIMARY KEY,
    fecha          date        NOT NULL,
    tipo           text        NOT NULL CHECK (tipo IN ('cierre', 'reapertura')),
    registrado_por text        NOT NULL,
    registrado_en  timestamptz NOT NULL DEFAULT now(),
    observaciones  text
);
CREATE INDEX cierre_dia_fecha_ix ON planta.cierre_dia (fecha, registrado_en);
COMMENT ON TABLE planta.cierre_dia IS
    'Cierres y reaperturas de jornada. El estado de cada fecha es su último movimiento.';

-- --- solo agregar filas ------------------------------------------------------
CREATE TRIGGER trabajo_solo_insert BEFORE UPDATE OR DELETE ON planta.trabajo
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();
CREATE TRIGGER trabajo_revision_solo_insert BEFORE UPDATE OR DELETE ON planta.trabajo_revision
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();
CREATE TRIGGER trabajo_operacion_solo_insert BEFORE UPDATE OR DELETE ON planta.trabajo_operacion
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();
CREATE TRIGGER evento_solo_insert BEFORE UPDATE OR DELETE ON planta.evento
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();
CREATE TRIGGER cierre_dia_solo_insert BEFORE UPDATE OR DELETE ON planta.cierre_dia
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();
CREATE TRIGGER operario_sin_delete BEFORE DELETE ON planta.operario
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();

-- --- permisos específicos ----------------------------------------------------
-- El resto lo heredan las tablas por default privileges (ops/01_neon_planta.sql).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_planta') THEN
        GRANT UPDATE (nombre, activo) ON planta.operario TO app_planta;
    END IF;
END;
$$;
