"""Fixtures compartidas por los tests de todas las apps."""

import uuid
from datetime import UTC, datetime

import pytest
from django.db import connection

from planta.demo import cargar_demo
from planta.models import Operario, Trabajo


@pytest.fixture
def demo(db):
    return cargar_demo()


@pytest.fixture
def operario(db):
    return Operario.objects.create(nombre="Operario de prueba")


@pytest.fixture
def trabajo(db):
    return Trabajo.objects.create()


@pytest.fixture
def sql(db):
    """Ejecuta SQL crudo en la conexión de Django (la del dueño en tests)."""

    def ejecutar(query, params=None):
        with connection.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall() if cur.description else None

    return ejecutar


@pytest.fixture
def insertar_evento(sql):
    def insertar(**valores):
        fila = {
            "evento_id": uuid.uuid4(),
            "tipo": "empezado",
            "operacion_id": uuid.uuid4(),
            "ocurrido_en": datetime.now(UTC),
            "dispositivo": "tests",
            **valores,
        }
        columnas = ", ".join(fila)
        marcas = ", ".join(["%s"] * len(fila))
        sql(f"INSERT INTO planta.evento ({columnas}) VALUES ({marcas})", list(fila.values()))
        return fila["evento_id"]

    return insertar
