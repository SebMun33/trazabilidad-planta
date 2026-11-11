"""Flujos de la oficina (parte A) y permisos por grupo."""

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from planta.models import Evento, TrabajoRevision
from planta.servicios import estado as est
from planta.servicios.jornada import cerrar_dia
from planta.servicios.trabajos import DatosOperacion, DatosTrabajo, crear_trabajo

pytestmark = pytest.mark.django_db


def _usuario(nombre, *grupos):
    usuario = User.objects.create_user(nombre, password="clave-de-prueba")
    for g in grupos:
        usuario.groups.add(Group.objects.get(name=g))
    return usuario


@pytest.fixture
def oficina(client):
    client.force_login(_usuario("ofi", "oficina"))
    return client


@pytest.fixture
def supervisor(client):
    client.force_login(_usuario("sup", "supervisor"))
    return client


def _post_trabajo(**extra):
    datos = {
        "plano": "X-1",
        "urgencia": "1",
        "ops-TOTAL_FORMS": "1",
        "ops-INITIAL_FORMS": "0",
        "ops-0-maquina_id": "",
        "ops-0-descripcion": "Tornear",
        "accion": "guardar",
    }
    datos.update(extra)
    return datos


# --- permisos ----------------------------------------------------------------
@pytest.mark.parametrize(
    "nombre", ["oficina:pendientes", "oficina:pedidos", "oficina:registros", "oficina:cierre"]
)
def test_anonimo_va_al_login(client, nombre):
    respuesta = client.get(reverse(nombre))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))


def test_usuario_sin_grupo_no_entra(client):
    client.force_login(_usuario("sin_grupo"))
    assert client.get(reverse("oficina:pendientes")).status_code == 403


def test_oficina_no_cierra_el_dia(oficina):
    assert oficina.get(reverse("oficina:pendientes")).status_code == 200
    assert oficina.get(reverse("oficina:cierre")).status_code == 403


def test_supervisor_ve_todo(supervisor, demo):
    for nombre in [
        "oficina:pendientes",
        "oficina:pedidos",
        "oficina:cotizaciones",
        "oficina:registros",
        "oficina:cierre",
    ]:
        assert supervisor.get(reverse(nombre)).status_code == 200, nombre


def test_login_con_usuario_y_clave(client):
    _usuario("ana", "oficina")
    respuesta = client.post(reverse("login"), {"username": "ana", "password": "clave-de-prueba"})
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("oficina:pendientes")


# --- orígenes ----------------------------------------------------------------
def test_lista_de_pedidos_y_busqueda(oficina, demo):
    respuesta = oficina.get(reverse("oficina:pedidos"))
    assert b"EJ-220/A" in respuesta.content and b"PR 15-3" in respuesta.content
    filtrada = oficina.get(reverse("oficina:pedidos"), {"q": "3002"}, HTTP_HX_REQUEST="true")
    assert b"PR 15-3" in filtrada.content and b"EJ-220/A" not in filtrada.content
    assert b"<html" not in filtrada.content  # HTMX recibe solo la tabla


def test_lista_de_cotizaciones(oficina, demo):
    respuesta = oficina.get(reverse("oficina:cotizaciones"))
    assert b"SEP-08" in respuesta.content
    assert b"2102" not in respuesta.content  # ya tiene pedido


# --- preparar desde un pedido ------------------------------------------------
def test_preparar_desde_pedido_precarga_la_ruta(oficina, demo):
    url = reverse("oficina:trabajo_nuevo") + "?origen=pedido&ref=3001-1"
    respuesta = oficina.get(url)
    assert respuesta.status_code == 200
    formset = respuesta.context["formset"]
    assert [f.initial["maquina_id"] for f in formset.forms] == [101, 103, 107]
    assert respuesta.context["form"].initial["cantidad"] == 30  # 40 pedidos - 10 entregados


def test_enviar_pedido_a_pendientes(oficina, demo):
    url = reverse("oficina:trabajo_nuevo") + "?origen=pedido&ref=3002-1"
    datos = {
        "plano": "PR 15-3",
        "cantidad": "1000",
        "urgencia": "3",
        "fecha_entrega_estimada": "2026-12-01",
        "ops-TOTAL_FORMS": "2",
        "ops-INITIAL_FORMS": "0",
        "ops-0-maquina_id": "104",
        "ops-0-descripcion": "Cortar y tornear",
        "ops-1-maquina_id": "106",
        "ops-1-descripcion": "Laminar rosca",
        "ops-1-observaciones": "Usar rodillos nuevos",
        "accion": "guardar",
    }
    respuesta = oficina.post(url, datos)
    assert respuesta.status_code == 302
    revision = TrabajoRevision.objects.get()
    assert revision.origen == "pedido" and revision.origen_ref == "3002-1"
    assert revision.pedido_id == 3002 and revision.cliente_id == 2
    assert revision.creado_por == "ofi"
    assert revision.operaciones.count() == 2

    # El renglón queda marcado y no se puede preparar dos veces.
    pedidos = oficina.get(reverse("oficina:pedidos"))
    assert "En pendientes" in pedidos.content.decode()
    otra_vez = oficina.get(url)
    assert otra_vez.status_code == 302
    assert otra_vez.url == reverse("oficina:trabajo", args=[revision.trabajo_id])


def test_agregar_operacion_no_guarda(oficina):
    url = reverse("oficina:trabajo_nuevo") + "?origen=manual"
    respuesta = oficina.post(url, _post_trabajo(accion="agregar"), HTTP_HX_REQUEST="true")
    assert respuesta.status_code == 200
    assert len(respuesta.context["formset"].forms) == 2
    assert not TrabajoRevision.objects.exists()


def test_trabajo_manual_sin_operaciones_da_error(oficina):
    url = reverse("oficina:trabajo_nuevo") + "?origen=manual"
    respuesta = oficina.post(url, _post_trabajo(**{"ops-0-descripcion": ""}))
    assert respuesta.status_code == 200
    assert "al menos una operación" in respuesta.content.decode()


def test_origen_inexistente_da_404(oficina, demo):
    url = reverse("oficina:trabajo_nuevo") + "?origen=pedido&ref=no-existe"
    assert oficina.get(url).status_code == 404


# --- detalle, revisión y retiro ----------------------------------------------
@pytest.fixture
def trabajo():
    return crear_trabajo(
        DatosTrabajo(plano="BJ-100", cliente_nombre="Cliente manual"),
        [
            DatosOperacion(maquina_id=102, descripcion="Tornear"),
            DatosOperacion(descripcion="Lavar"),
        ],
        "ofi",
    )


def test_detalle_del_trabajo(oficina, trabajo):
    respuesta = oficina.get(reverse("oficina:trabajo", args=[trabajo.trabajo_id]))
    assert respuesta.status_code == 200
    assert "0 de 2 terminadas" in respuesta.content.decode()


def test_revisar_crea_revision_y_conserva_operaciones(oficina, trabajo):
    op1, op2 = trabajo.operaciones.order_by("operacion_nro")
    url = reverse("oficina:trabajo_revisar", args=[trabajo.trabajo_id])
    datos = {
        "plano": "BJ-100",
        "urgencia": "2",
        "revision_base": "1",
        "ops-TOTAL_FORMS": "2",
        "ops-INITIAL_FORMS": "2",
        "ops-0-operacion_id": str(op1.operacion_id),
        "ops-0-maquina_id": "102",
        "ops-0-descripcion": "Tornear",
        "ops-1-operacion_id": str(op2.operacion_id),
        "ops-1-descripcion": "Lavar",
        "ops-1-DELETE": "on",
        "accion": "guardar",
    }
    assert oficina.post(url, datos).status_code == 302
    vigente = est.estado_trabajo(trabajo.trabajo_id)
    assert vigente.revision.revision == 2 and vigente.revision.urgencia == 2
    assert [o.operacion.operacion_id for o in vigente.operaciones] == [op1.operacion_id]


def test_revision_desactualizada_muestra_error(oficina, trabajo):
    (op1, op2) = trabajo.operaciones.order_by("operacion_nro")
    url = reverse("oficina:trabajo_revisar", args=[trabajo.trabajo_id])
    base = {
        "plano": "BJ-100",
        "urgencia": "1",
        "ops-TOTAL_FORMS": "1",
        "ops-INITIAL_FORMS": "1",
        "ops-0-operacion_id": str(op1.operacion_id),
        "ops-0-descripcion": "Tornear",
        "accion": "guardar",
    }
    # op2 se quita en ambos envíos; el segundo parte de la revisión 1, ya superada.
    assert oficina.post(url, {**base, "revision_base": "1"}).status_code == 302
    respuesta = oficina.post(url, {**base, "revision_base": "1"})
    assert respuesta.status_code == 200
    assert "Otra persona" in respuesta.content.decode()
    assert op2  # usado


def test_retirar_trabajo(oficina, trabajo):
    url = reverse("oficina:trabajo_retirar", args=[trabajo.trabajo_id])
    assert oficina.post(url, {"motivo": "Canceló el cliente"}).status_code == 302
    assert est.estado_trabajo(trabajo.trabajo_id).estado == est.RETIRADO
    lista = oficina.get(reverse("oficina:pendientes"))
    assert "BJ-100" not in lista.content.decode()
    retirados = oficina.get(reverse("oficina:pendientes"), {"estado": "retirado"})
    assert "BJ-100" in retirados.content.decode()


def test_retirar_exige_post(oficina, trabajo):
    url = reverse("oficina:trabajo_retirar", args=[trabajo.trabajo_id])
    assert oficina.get(url).status_code == 405


# --- registros, anulación y cierre -------------------------------------------
@pytest.fixture
def evento(trabajo, operario):
    op = trabajo.operaciones.order_by("operacion_nro").first()
    return Evento.objects.create(
        tipo="empezado",
        trabajo_id=trabajo.trabajo_id,
        operacion_id=op.operacion_id,
        maquina_id=op.maquina_id,
        operario=operario,
        ocurrido_en=timezone.now(),
        dispositivo="kiosco",
    )


def test_registros_y_anulacion(oficina, evento):
    respuesta = oficina.get(reverse("oficina:registros"))
    assert "Operario de prueba" in respuesta.content.decode()
    url = reverse("oficina:evento_anular", args=[evento.evento_id])
    assert oficina.post(url, {"motivo": "Equivocado"}).status_code == 302
    anulacion = Evento.objects.get(tipo="anulacion")
    assert anulacion.anula_evento_id == evento.evento_id
    assert anulacion.registrado_por == "ofi"
    assert anulacion.observaciones == "Equivocado"


def test_anular_no_redirige_afuera(oficina, evento):
    url = reverse("oficina:evento_anular", args=[evento.evento_id])
    respuesta = oficina.post(url, {"volver": "https://sitio-malicioso.example/"})
    assert respuesta.url == reverse("oficina:registros")


def test_no_se_anula_en_dia_cerrado(oficina, evento):
    cerrar_dia(timezone.localdate(), "sup")
    url = reverse("oficina:evento_anular", args=[evento.evento_id])
    oficina.post(url, {"motivo": "x"})
    assert not Evento.objects.filter(tipo="anulacion").exists()


def test_supervisor_cierra_y_reabre(supervisor):
    hoy = timezone.localdate().isoformat()
    url = reverse("oficina:cierre")
    assert supervisor.post(url, {"fecha": hoy, "accion": "cerrar"}).status_code == 302
    pagina = supervisor.get(url, {"fecha": hoy})
    assert pagina.context["resumen"].cerrado
    supervisor.post(url, {"fecha": hoy, "accion": "reabrir", "observaciones": "corrección"})
    assert not supervisor.get(url, {"fecha": hoy}).context["resumen"].cerrado
