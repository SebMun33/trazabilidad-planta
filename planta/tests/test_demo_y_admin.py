import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import OperationalError
from django.test import RequestFactory
from django.urls import reverse

from planta.middleware import BaseNoDisponibleMiddleware
from planta.models import (
    CotizacionSinPedido,
    Evento,
    Maquina,
    Operario,
    PedidoPendiente,
    Ruta,
    UltimaPublicacion,
)

pytestmark = pytest.mark.django_db


def test_seed_demo_es_idempotente():
    call_command("seed_demo")
    call_command("seed_demo")
    assert Maquina.objects.count() == 7
    assert Operario.objects.count() == 3
    # Solo renglones con pendiente > 0 y cotizaciones sin pedido.
    assert PedidoPendiente.objects.count() == 5
    assert CotizacionSinPedido.objects.count() == 2
    assert Ruta.objects.filter(plano="EJ-220/A").count() == 3
    assert UltimaPublicacion.objects.get().publicado_en is not None


@pytest.fixture
def cliente_admin(client):
    usuario = User.objects.create_superuser("admin", password="x")
    client.force_login(usuario)
    return client


def test_admin_eventos_solo_lectura(cliente_admin):
    assert cliente_admin.get(reverse("admin:planta_evento_changelist")).status_code == 200
    assert cliente_admin.get(reverse("admin:planta_evento_add")).status_code == 403
    assert not Evento.objects.exists()


def test_admin_operarios_solo_lectura(cliente_admin):
    # Los operarios se crean como usuarios con rol Operario (ver cuentas).
    operario = Operario.objects.create(nombre="Para ver")
    assert cliente_admin.get(reverse("admin:planta_operario_changelist")).status_code == 200
    assert cliente_admin.get(reverse("admin:planta_operario_add")).status_code == 403
    respuesta = cliente_admin.get(reverse("admin:planta_operario_delete", args=[operario.pk]))
    assert respuesta.status_code == 403


def test_middleware_muestra_503_si_la_base_no_responde():
    middleware = BaseNoDisponibleMiddleware(lambda r: None)
    respuesta = middleware.process_exception(RequestFactory().get("/"), OperationalError("x"))
    assert respuesta.status_code == 503
    assert "no responde" in respuesta.content.decode()


# --- despliegue ----------------------------------------------------------------
def test_salud_responde_sin_base_ni_host_valido(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        respuesta = client.get("/salud/", HTTP_HOST="interno.render")
    assert respuesta.status_code == 200 and respuesta.content == b"ok"


def test_oficina_agrega_host_de_render_y_origenes_csrf():
    # En un proceso aparte: los settings se calculan al importarse.
    import json
    import os
    import subprocess
    import sys

    entorno = {
        **os.environ,
        "RENDER_EXTERNAL_HOSTNAME": "trazabilidad.onrender.com",
        "DJANGO_ALLOWED_HOSTS": "planta.ejemplo.com.ar",
    }
    codigo = (
        "import json, config.settings.prod_oficina as s;"
        "print(json.dumps([s.ALLOWED_HOSTS, s.CSRF_TRUSTED_ORIGINS]))"
    )
    salida = subprocess.run(  # noqa: S603 - comando fijo, sin entrada externa
        [sys.executable, "-c", codigo], env=entorno, capture_output=True, text=True, check=True
    )
    hosts, origenes = json.loads(salida.stdout.strip().splitlines()[-1])
    assert hosts == ["planta.ejemplo.com.ar", "trazabilidad.onrender.com"]
    assert origenes == ["https://planta.ejemplo.com.ar", "https://trazabilidad.onrender.com"]
