"""MedicionMiddleware: encabezado Server-Timing y línea de log por pedido."""

import logging

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_cada_pedido_informa_tiempos_y_consultas(client, caplog):
    client.force_login(User.objects.create_superuser("sudo", password="clave-de-prueba-larga"))
    with caplog.at_level(logging.INFO, logger="planta.middleware"):
        respuesta = client.get(reverse("oficina:pendientes"))
    assert respuesta.status_code == 200
    encabezado = respuesta["Server-Timing"]
    assert encabezado.startswith("total;dur=") and "consultas" in encabezado
    linea = next(r.getMessage() for r in caplog.records if "/oficina/pendientes/" in r.getMessage())
    assert "GET /oficina/pendientes/ 200 total=" in linea and "consultas=" in linea


def test_pedido_lento_queda_como_advertencia(client, caplog, settings):
    settings.MEDICION_LENTO_SEGUNDOS = 0
    with caplog.at_level(logging.INFO, logger="planta.middleware"):
        client.get(reverse("login"))
    assert any(
        r.levelno == logging.WARNING for r in caplog.records if r.name == "planta.middleware"
    )


def test_salud_no_se_mide_ni_toca_la_base(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        respuesta = client.get("/salud/")
    assert respuesta.status_code == 200 and "Server-Timing" not in respuesta
