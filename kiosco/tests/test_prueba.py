"""«Probar como operario»: el superusuario usa el kiosco como el usuario «operario»."""

import uuid

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from cuentas.prueba import DISPOSITIVO_PRUEBA, SESION_PRUEBA, operario_prueba_id
from cuentas.roles import OPERARIO, STAFF, asignar_rol, rol_de
from kiosco.models import EventoPendiente, Foto
from kiosco.sincronizacion import sincronizar
from planta.models import Evento, Operario
from planta.servicios import estado as est
from planta.servicios.trabajos import DatosOperacion, DatosTrabajo, crear_trabajo

pytestmark = pytest.mark.django_db(databases=["default", "local"])

CLAVE = "clave-de-prueba-larga"


@pytest.fixture
def escenario(demo):
    ana = Operario.objects.create(nombre="Ana")
    revision = crear_trabajo(
        DatosTrabajo(plano="PR-01"),
        [DatosOperacion(maquina_id=101, descripcion="Tornear")],
        "ofi",
    )
    sincronizar(forzar_copia=True)
    op = revision.operaciones.get()
    return {"ana": ana, "revision": revision, "op": op}


@pytest.fixture
def sudo(client):
    client.force_login(User.objects.create_superuser("sudo", password=CLAVE))
    return client


@pytest.fixture
def en_prueba(sudo):
    respuesta = sudo.post(reverse("oficina:prueba_entrar"))
    assert respuesta.status_code == 302
    return sudo


@pytest.fixture
def en_la_nube(settings):
    settings.KIOSCO_HABILITADO = False


def _url_op(e, operario_id):
    return reverse(
        "kiosco:operacion", args=[operario_id, e["revision"].trabajo_id, e["op"].operacion_id]
    )


# --- entrar ----------------------------------------------------------------------------
def test_entrar_crea_el_usuario_operario_sin_contrasena(escenario, en_prueba):
    usuario = User.objects.get(username="operario")
    assert not usuario.has_usable_password() and rol_de(usuario) == OPERARIO
    assert Operario.objects.get(usuario_id=usuario.pk).activo
    assert en_prueba.session[SESION_PRUEBA] is True


def test_el_kiosco_abre_directo_como_operario(escenario, en_prueba):
    respuesta = en_prueba.get(reverse("kiosco:inicio"))
    prueba_id = operario_prueba_id()
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("kiosco:pendientes", args=[prueba_id])
    lista = en_prueba.get(respuesta.url).content.decode()
    assert "Modo prueba" in lista and "PR-01" in lista


def test_solo_el_superusuario_puede_entrar(escenario, client):
    jefa = User.objects.create_user("jefa", password=CLAVE)
    asignar_rol(jefa, STAFF)
    client.force_login(jefa)
    respuesta = client.post(reverse("oficina:prueba_entrar"))
    assert respuesta.status_code == 302 and "login" in respuesta.url
    assert SESION_PRUEBA not in client.session
    assert not User.objects.filter(username="operario").exists()
    assert client.get(reverse("oficina:prueba_entrar")).status_code == 405


# --- en la nube ----------------------------------------------------------------------
def test_en_la_nube_el_kiosco_solo_responde_en_modo_prueba(escenario, client, en_la_nube):
    assert client.get(reverse("kiosco:inicio")).status_code == 403
    client.force_login(User.objects.create_superuser("sudo", password=CLAVE))
    assert client.get(reverse("kiosco:inicio")).status_code == 403  # sin activar el modo
    client.post(reverse("oficina:prueba_entrar"))
    prueba_id = operario_prueba_id()
    url = reverse("kiosco:pendientes", args=[prueba_id])
    assert client.get(url, REMOTE_ADDR="203.0.113.9").status_code == 200
    client.post(reverse("oficina:prueba_salir"))
    assert client.get(url).status_code == 403


def test_lo_registrado_llega_en_el_momento_marcado_como_prueba(escenario, en_prueba, en_la_nube):
    prueba_id = operario_prueba_id()
    url = _url_op(escenario, prueba_id)
    respuesta = en_prueba.post(url, {"accion": "empezado", "maquina_id": "101"})
    assert respuesta.status_code == 302
    evento = Evento.objects.get()
    assert evento.operario_id == prueba_id and evento.dispositivo == DISPOSITIVO_PRUEBA
    assert not EventoPendiente.objects.filter(enviado_en=None).exists()

    trabajo = en_prueba.get(reverse("oficina:trabajo", args=[escenario["revision"].trabajo_id]))
    html = trabajo.content.decode()
    assert "En proceso" in html and 'class="estado e-prueba">prueba' in html


def test_en_modo_prueba_no_se_registra_a_nombre_de_otro(escenario, en_prueba):
    ana = escenario["ana"].operario_id
    assert en_prueba.get(reverse("kiosco:pendientes", args=[ana])).status_code == 302
    prueba_id = operario_prueba_id()
    en_prueba.post(
        _url_op(escenario, prueba_id),
        {"accion": "empezado", "maquina_id": "101", "operario": str(ana)},
    )
    assert Evento.objects.get().operario_id == prueba_id


# --- oculto ----------------------------------------------------------------------------
def test_el_kiosco_de_planta_no_muestra_al_operario_de_prueba(escenario, en_prueba, client):
    prueba_id = operario_prueba_id()
    en_prueba.post(reverse("oficina:prueba_salir"))
    client.logout()
    inicio = client.get(reverse("kiosco:inicio"))
    assert inicio.status_code == 200
    assert f'value="{prueba_id}"' not in inicio.content.decode()
    assert client.post(reverse("kiosco:inicio"), {"nombre": "operario"}).status_code == 404
    pendientes = client.get(reverse("kiosco:pendientes", args=[prueba_id]))
    assert pendientes.status_code == 302 and pendientes.url == reverse("kiosco:inicio")
    ana = escenario["ana"].operario_id
    pantalla = client.get(_url_op(escenario, ana)).content.decode()
    assert "Ana" in pantalla and f'value="{prueba_id}"' not in pantalla


def test_staff_no_ve_al_usuario_de_prueba(escenario, en_prueba, client):
    usuario = User.objects.get(username="operario")
    prueba_id = operario_prueba_id()
    jefa = User.objects.create_user("jefa", password=CLAVE)
    asignar_rol(jefa, STAFF)
    client.force_login(jefa)
    lista = client.get(reverse("admin:auth_user_changelist")).content.decode()
    assert ">operario<" not in lista
    ficha = client.get(reverse("admin:auth_user_change", args=[usuario.pk]))
    assert ficha.status_code in (302, 403)
    operarios = client.get(reverse("admin:planta_operario_changelist"))
    assert operarios.status_code == 403 or f"/{prueba_id}/change/" not in operarios.content.decode()
    assert f"/{usuario.pk}/change/" not in lista
    # El superusuario sí lo ve (en_prueba y client son el mismo navegador de prueba).
    client.force_login(User.objects.get(username="sudo"))
    lista = client.get(reverse("admin:auth_user_changelist")).content.decode()
    assert f"/{usuario.pk}/change/" in lista


# --- deshacer pruebas --------------------------------------------------------------------
def test_deshacer_pruebas_anula_todo_y_el_estado_vuelve(escenario, en_prueba):
    prueba_id = operario_prueba_id()
    url = _url_op(escenario, prueba_id)
    en_prueba.post(url, {"accion": "empezado", "maquina_id": "101"})
    en_prueba.post(url, {"accion": "terminado", "maquina_id": "101"})
    real = Evento.objects.create(
        evento_id=uuid.uuid4(),
        tipo=Evento.Tipo.EMPEZADO,
        trabajo_id=escenario["revision"].trabajo_id,
        operacion_id=escenario["op"].operacion_id,
        operario_id=escenario["ana"].operario_id,
        ocurrido_en=timezone.now(),
        dispositivo="kiosco-planta",
    )
    respuesta = en_prueba.post(reverse("oficina:prueba_deshacer"))
    assert respuesta.status_code == 302
    anulados = set(
        Evento.objects.filter(tipo=Evento.Tipo.ANULACION).values_list("anula_evento_id", flat=True)
    )
    de_prueba = set(
        Evento.objects.filter(operario_id=prueba_id).values_list("evento_id", flat=True)
    )
    assert anulados == de_prueba and real.evento_id not in anulados
    # Solo queda vigente el registro real de Ana.
    t = next(x for x in est.estado_trabajos() if x.trabajo_id == escenario["revision"].trabajo_id)
    assert t.operaciones[0].ultimo_evento.evento_id == real.evento_id
    # Repetirlo no hace nada.
    en_prueba.post(reverse("oficina:prueba_deshacer"))
    assert Evento.objects.filter(tipo=Evento.Tipo.ANULACION).count() == 2


def test_deshacer_pruebas_solo_superusuario(escenario, client):
    jefa = User.objects.create_user("jefa", password=CLAVE)
    asignar_rol(jefa, STAFF)
    client.force_login(jefa)
    respuesta = client.post(reverse("oficina:prueba_deshacer"))
    assert respuesta.status_code == 302 and "login" in respuesta.url


def test_el_boton_solo_lo_ve_el_superusuario(escenario, sudo, client):
    url = reverse("oficina:pendientes")
    assert "Probar como operario" in sudo.get(url).content.decode()
    jefa = User.objects.create_user("jefa", password=CLAVE)
    asignar_rol(jefa, STAFF)
    client.force_login(jefa)
    assert "Probar como operario" not in client.get(url).content.decode()


# --- liviano ----------------------------------------------------------------------------
def test_la_copia_se_renueva_cada_30_segundos_o_al_pedirlo(escenario, en_prueba, settings):
    prueba_id = operario_prueba_id()
    url = reverse("kiosco:pendientes", args=[prueba_id])
    en_prueba.get(url)
    copia = Foto.objects.get().obtenida_en

    # Un trabajo nuevo de oficina no aparece hasta que vence la copia...
    crear_trabajo(DatosTrabajo(plano="NUEVO-9"), [DatosOperacion(descripcion="Cortar")], "ofi")
    assert "NUEVO-9" not in en_prueba.get(url).content.decode()
    assert Foto.objects.get().obtenida_en == copia

    # ...o hasta tocar «Actualizar lista».
    assert "NUEVO-9" in en_prueba.get(url + "?actualizar=1").content.decode()
    settings.KIOSCO_PRUEBA_COPIA_CADA = 0
    en_prueba.get(url)
    assert Foto.objects.get().obtenida_en > copia


def test_lo_registrado_se_ve_sin_renovar_la_copia(escenario, en_prueba):
    prueba_id = operario_prueba_id()
    en_prueba.get(reverse("kiosco:pendientes", args=[prueba_id]))
    copia = Foto.objects.get().obtenida_en
    en_prueba.post(_url_op(escenario, prueba_id), {"accion": "empezado", "maquina_id": "101"})
    pantalla = en_prueba.get(_url_op(escenario, prueba_id)).content.decode()
    assert "Terminé" in pantalla  # ya figura empezada
    assert Foto.objects.get().obtenida_en == copia
    assert Evento.objects.filter(operario_id=prueba_id).exists()  # y ya se envió
