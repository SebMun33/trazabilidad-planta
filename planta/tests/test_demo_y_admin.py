import pytest
from django.contrib.auth.models import Group, User
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


def test_grupos_creados_por_migracion():
    assert set(Group.objects.values_list("name", flat=True)) >= {"oficina", "supervisor"}


@pytest.fixture
def cliente_admin(client):
    usuario = User.objects.create_superuser("admin", password="x")
    client.force_login(usuario)
    return client


def test_admin_eventos_solo_lectura(cliente_admin):
    assert cliente_admin.get(reverse("admin:planta_evento_changelist")).status_code == 200
    assert cliente_admin.get(reverse("admin:planta_evento_add")).status_code == 403
    assert not Evento.objects.exists()


def test_admin_operarios_editable_sin_borrar(cliente_admin):
    operario = Operario.objects.create(nombre="Para editar")
    assert cliente_admin.get(reverse("admin:planta_operario_add")).status_code == 200
    respuesta = cliente_admin.get(reverse("admin:planta_operario_delete", args=[operario.pk]))
    assert respuesta.status_code == 403


def test_middleware_muestra_503_si_la_base_no_responde():
    middleware = BaseNoDisponibleMiddleware(lambda r: None)
    respuesta = middleware.process_exception(RequestFactory().get("/"), OperationalError("x"))
    assert respuesta.status_code == 503
    assert "no responde" in respuesta.content.decode()
