-- Usuarios y notas. Cambios solo aditivos (contrato con el data warehouse).

-- --- operario vinculado a su usuario -------------------------------------------
-- Un usuario con rol Operario aparece solo como operario (ver cuentas/senales.py).
-- Sin FK: planta.* no depende de las tablas de Django (planta_app).
ALTER TABLE planta.operario ADD COLUMN usuario_id integer UNIQUE;
COMMENT ON COLUMN planta.operario.usuario_id IS
    'Usuario de la app (planta_app.auth_user.id) con rol Operario; NULL si se cargó sin usuario.';

-- --- nota ------------------------------------------------------------------------
CREATE TABLE planta.nota (
    nota_id       uuid        PRIMARY KEY,
    trabajo_id    uuid        NOT NULL REFERENCES planta.trabajo,
    operacion_id  uuid,
    tipo          text        NOT NULL
                  CHECK (tipo IN ('observacion', 'sugerencia', 'pregunta', 'respuesta')),
    texto         text        NOT NULL CHECK (btrim(texto) <> ''),
    responde_a    uuid        REFERENCES planta.nota,
    autor         text        NOT NULL,
    operario_id   integer     REFERENCES planta.operario,
    usuario_id    integer,
    escrita_en    timestamptz NOT NULL,
    registrada_en timestamptz NOT NULL DEFAULT now(),
    dispositivo   text        NOT NULL,
    -- Una respuesta siempre apunta a la nota que responde; las demás, nunca.
    CONSTRAINT nota_respuesta_ck CHECK ((tipo = 'respuesta') = (responde_a IS NOT NULL))
);
CREATE INDEX nota_trabajo_ix ON planta.nota (trabajo_id, escrita_en);
COMMENT ON TABLE planta.nota IS
    'Observaciones, sugerencias, preguntas y respuestas sobre un trabajo u operación. Solo se agregan filas.';
COMMENT ON COLUMN planta.nota.nota_id IS
    'Generado por la app antes de grabar: el envío desde el kiosco es idempotente.';
COMMENT ON COLUMN planta.nota.autor IS 'Nombre visible de quien la escribió (operario o usuario).';
COMMENT ON COLUMN planta.nota.escrita_en IS 'Cuándo se escribió (hora del equipo).';

CREATE TRIGGER nota_solo_insert BEFORE UPDATE OR DELETE ON planta.nota
    FOR EACH ROW EXECUTE FUNCTION planta.impedir_modificacion();

-- --- permisos ----------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_planta') THEN
        GRANT UPDATE (usuario_id) ON planta.operario TO app_planta;
    END IF;
END;
$$;
