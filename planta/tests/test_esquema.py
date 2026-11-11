"""Restricciones del esquema `planta`: se validan en la base, no solo en la app."""

import uuid

import pytest
from django.db import DataError, IntegrityError, InternalError, ProgrammingError, transaction

pytestmark = pytest.mark.django_db

TABLAS_PLANTA = [
    "operario",
    "trabajo",
    "trabajo_revision",
    "trabajo_operacion",
    "evento",
    "cierre_dia",
]


def test_tablas_en_su_esquema(sql):
    filas = dict(
        sql(
            "SELECT tablename, schemaname FROM pg_tables "
            "WHERE schemaname IN ('planta', 'planta_app')"
        )
    )
    for tabla in TABLAS_PLANTA:
        assert filas[tabla] == "planta"
    for tabla in ["django_migrations", "auth_user", "django_session"]:
        assert filas[tabla] == "planta_app"


def test_evento_valido(insertar_evento, trabajo, operario, sql):
    evento_id = insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk)
    assert sql("SELECT tipo FROM planta.evento WHERE evento_id = %s", [evento_id]) == [
        ("empezado",)
    ]


def test_tipo_de_evento_invalido(insertar_evento, trabajo, operario):
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk, tipo="borrado")


def test_anulacion_exige_evento_anulado(insertar_evento, trabajo):
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, tipo="anulacion", operacion_id=None)


def test_solo_las_anulaciones_apuntan_a_otro_evento(insertar_evento, trabajo, operario):
    original = insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk)
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk, anula_evento_id=original)


def test_evento_de_trabajo_exige_operacion_y_operario(insertar_evento, trabajo, operario):
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, operario_id=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk, operacion_id=None)


def test_un_evento_se_anula_una_sola_vez(insertar_evento, trabajo, operario):
    original = insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk)
    insertar_evento(trabajo_id=trabajo.pk, tipo="anulacion", anula_evento_id=original)
    with pytest.raises(IntegrityError), transaction.atomic():
        insertar_evento(trabajo_id=trabajo.pk, tipo="anulacion", anula_evento_id=original)


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE planta.evento SET observaciones = 'x'", "DELETE FROM planta.evento"],
)
def test_ni_el_dueno_modifica_eventos(insertar_evento, trabajo, operario, sql, sentencia):
    insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk)
    with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
        sql(sentencia)


def test_operario_se_edita_pero_no_se_borra(operario, sql):
    sql("UPDATE planta.operario SET activo = false WHERE operario_id = %s", [operario.pk])
    operario.refresh_from_db()
    assert operario.activo is False
    with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
        sql("DELETE FROM planta.operario WHERE operario_id = %s", [operario.pk])


def test_revision_alta_es_la_numero_uno(trabajo, sql):
    base = (
        "INSERT INTO planta.trabajo_revision (revision_id, trabajo_id, revision, tipo, origen,"
        " plano, creado_por) VALUES (%s, %s, %s, %s, 'manual', 'X-1', 'tests')"
    )
    sql(base, [uuid.uuid4(), trabajo.pk, 1, "alta"])
    with pytest.raises(IntegrityError), transaction.atomic():
        sql(base, [uuid.uuid4(), trabajo.pk, 2, "alta"])
    with pytest.raises(IntegrityError), transaction.atomic():
        sql(base, [uuid.uuid4(), trabajo.pk, 1, "cambio"])


def test_urgencia_fuera_de_rango(trabajo, sql):
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        sql(
            "INSERT INTO planta.trabajo_revision (revision_id, trabajo_id, revision, tipo, origen,"
            " plano, creado_por, urgencia) VALUES (%s, %s, 1, 'alta', 'manual', 'X', 't', 9)",
            [uuid.uuid4(), trabajo.pk],
        )


def test_insert_idempotente_con_on_conflict(insertar_evento, trabajo, operario, sql):
    evento_id = insertar_evento(trabajo_id=trabajo.pk, operario_id=operario.pk)
    sql(
        "INSERT INTO planta.evento (evento_id, tipo, trabajo_id, operacion_id, operario_id,"
        " ocurrido_en, dispositivo) VALUES (%s, 'empezado', %s, %s, %s, now(), 'tests')"
        " ON CONFLICT (evento_id) DO NOTHING",
        [evento_id, trabajo.pk, uuid.uuid4(), operario.pk],
    )
    assert sql("SELECT count(*) FROM planta.evento") == [(1,)]
