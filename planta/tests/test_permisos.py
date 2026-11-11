"""Permisos del rol de la app (`app_planta`) en una conexión aparte.

Los tests corren como `app_planta_owner`; acá se abre una conexión como
`app_planta` contra la misma base de tests y se verifica lo que puede y no puede
hacer. Los privilegios se chequean al planificar la sentencia, así que no hace
falta que haya filas.
"""

import os

import psycopg
import pytest
from django.db import connection
from psycopg import errors

pytestmark = pytest.mark.django_db

TABLAS_SOLO_INSERT = {
    "evento": "observaciones",
    "trabajo": "creado_en",
    "trabajo_revision": "observaciones",
    "trabajo_operacion": "observaciones",
    "cierre_dia": "observaciones",
}


@pytest.fixture
def conexion_app(db):
    clave = os.environ.get("TEST_APP_PLANTA_PASSWORD")
    if not clave:
        pytest.skip("Falta TEST_APP_PLANTA_PASSWORD")
    ajustes = connection.settings_dict
    conn = psycopg.connect(
        host=ajustes["HOST"],
        port=ajustes["PORT"] or 5432,
        dbname=ajustes["NAME"],
        user="app_planta",
        password=clave,
        options="-c search_path=planta_app,planta,planta_ref",
        connect_timeout=5,
    )
    yield conn
    conn.rollback()
    conn.close()


def _ejecutar(conn, sentencia):
    with conn.cursor() as cur:
        try:
            cur.execute(sentencia)
        finally:
            conn.rollback()


@pytest.mark.parametrize(("tabla", "columna"), TABLAS_SOLO_INSERT.items())
def test_app_no_puede_update_en_planta(conexion_app, tabla, columna):
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, f"UPDATE planta.{tabla} SET {columna} = {columna}")


@pytest.mark.parametrize("tabla", [*TABLAS_SOLO_INSERT, "operario"])
def test_app_no_puede_delete_en_planta(conexion_app, tabla):
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, f"DELETE FROM planta.{tabla}")


def test_app_no_puede_truncate_ni_crear_tablas(conexion_app):
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, "TRUNCATE planta.evento")
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, "CREATE TABLE planta.intrusa (id int)")


def test_app_inserta_y_edita_operarios(conexion_app):
    with conexion_app.cursor() as cur:
        cur.execute(
            "INSERT INTO planta.operario (nombre) VALUES ('temporal') RETURNING operario_id"
        )
        assert cur.fetchone()[0] > 0
        cur.execute("UPDATE planta.operario SET activo = false WHERE nombre = 'temporal'")
        assert cur.rowcount == 1
        cur.execute("SELECT count(*) FROM planta.evento")
    conexion_app.rollback()


def test_app_no_puede_cambiar_otras_columnas_de_operario(conexion_app):
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, "UPDATE planta.operario SET creado_en = now()")


def test_app_solo_lee_planta_ref(conexion_app):
    with conexion_app.cursor() as cur:
        cur.execute("SELECT count(*) FROM planta_ref.maquinas")
    conexion_app.rollback()
    with pytest.raises(errors.InsufficientPrivilege):
        _ejecutar(conexion_app, "CREATE VIEW planta_ref.intrusa AS SELECT 1")


def test_app_tiene_crud_en_planta_app(conexion_app):
    with conexion_app.cursor() as cur:
        cur.execute("DELETE FROM planta_app.django_session WHERE false")
        cur.execute("UPDATE planta_app.auth_group SET name = name WHERE false")
    conexion_app.rollback()
