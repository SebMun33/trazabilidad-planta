"""Kiosco de planta: copia local, reglas, cola de envío, Deshacer y pantallas."""

import uuid
from datetime import timedelta

import pytest
from django.db import OperationalError, connections
from django.urls import reverse
from django.utils import timezone

from kiosco import local
from kiosco.models import EventoPendiente, Foto
from kiosco.sincronizacion import sincronizar
from planta.models import Evento, Operario
from planta.servicios import ReglaDeNegocioError
from planta.servicios import estado as est
from planta.servicios.jornada import anular_evento, cerrar_dia
from planta.servicios.trabajos import DatosOperacion, DatosTrabajo, crear_trabajo

pytestmark = pytest.mark.django_db(databases=["default", "local"])


@pytest.fixture
def kiosco(demo):
    """Un trabajo con dos operaciones, dos operarios y la copia local ya traída."""
    ana = Operario.objects.create(nombre="Ana")
    beto = Operario.objects.create(nombre="Beto")
    revision = crear_trabajo(
        DatosTrabajo(plano="KI-01", urgencia=3, observaciones="Cuidar las rebabas"),
        [
            DatosOperacion(maquina_id=101, descripcion="Tornear"),
            DatosOperacion(maquina_id=103, descripcion="Fresar", observaciones="Usar fresa nueva"),
        ],
        "ofi",
    )
    sincronizar(forzar_copia=True)
    ops = list(revision.operaciones.order_by("operacion_nro"))
    return {"ana": ana, "beto": beto, "revision": revision, "ops": ops}


def _registrar(k, accion, *, quien="ana", op=0, **kw):
    return local.registrar(
        local.cargar_planta(),
        operario_id=k[quien].operario_id,
        trabajo_id=k["revision"].trabajo_id,
        operacion_id=k["ops"][op].operacion_id,
        accion=accion,
        **kw,
    )


def _op_local(k, op=0):
    planta = local.cargar_planta()
    return planta.trabajo(k["revision"].trabajo_id).operacion(k["ops"][op].operacion_id)


# --- copia local ---------------------------------------------------------------
def test_copia_trae_trabajos_operarios_y_maquinas(kiosco):
    planta = local.cargar_planta()
    assert set(planta.operarios.values()) >= {"Ana", "Beto"}
    assert 101 in planta.maquinas
    t = planta.trabajo(kiosco["revision"].trabajo_id)
    assert t.plano == "KI-01" and t.urgencia == 3 and t.observaciones == "Cuidar las rebabas"
    assert [op.descripcion for op in t.operaciones] == ["Tornear", "Fresar"]
    assert t.operaciones[1].observaciones == "Usar fresa nueva"
    assert planta.activos[0] == t  # urgente primero


def test_sin_copia_el_kiosco_espera(client, db):
    assert local.cargar_planta() is None
    respuesta = client.get(reverse("kiosco:inicio"))
    assert "Esperando la primera sincronización" in respuesta.content.decode()


# --- reglas ----------------------------------------------------------------------
def test_empece_queda_en_cola_y_cambia_el_estado_local(kiosco):
    _registrar(kiosco, "empezado")
    pendiente = EventoPendiente.objects.get()
    assert pendiente.pendiente and pendiente.maquina_id == 101
    op = _op_local(kiosco)
    assert op.estado == est.EN_PROCESO and op.operario_nombre == "Ana"
    assert not Evento.objects.exists()  # todavía no se envió


def test_no_se_pausa_ni_termina_sin_empezar(kiosco):
    for accion in ("pausado", "terminado"):
        with pytest.raises(ReglaDeNegocioError, match="no está empezada"):
            _registrar(kiosco, accion)


def test_no_se_empieza_dos_veces_la_misma_operacion(kiosco):
    _registrar(kiosco, "empezado")
    with pytest.raises(ReglaDeNegocioError, match=r"ya está empezada \(Ana\)"):
        _registrar(kiosco, "empezado", quien="beto")


def test_terminada_no_se_vuelve_a_empezar(kiosco):
    _registrar(kiosco, "empezado")
    _registrar(kiosco, "terminado")
    with pytest.raises(ReglaDeNegocioError, match="ya está terminada"):
        _registrar(kiosco, "empezado")


def test_pausa_y_otro_operario_retoma(kiosco):
    _registrar(kiosco, "empezado")
    _registrar(kiosco, "pausado", observaciones="Falta material")
    assert _op_local(kiosco).estado == est.PAUSADA
    _registrar(kiosco, "empezado", quien="beto")
    assert _op_local(kiosco).operario_nombre == "Beto"


def test_avisa_si_el_operario_ya_tiene_otra_abierta(kiosco):
    _registrar(kiosco, "empezado", op=0)
    with pytest.raises(local.RequiereConfirmacion, match="operación 1 de KI-01"):
        _registrar(kiosco, "empezado", op=1)
    _registrar(kiosco, "empezado", op=1, confirmado=True)
    assert _op_local(kiosco, 1).abierta


def test_maquina_cambiada_queda_en_el_evento(kiosco):
    _registrar(kiosco, "empezado", maquina_id=105)
    assert EventoPendiente.objects.get().maquina_id == 105
    with pytest.raises(ReglaDeNegocioError, match="máquina no existe"):
        _registrar(kiosco, "empezado", op=1, maquina_id=999, confirmado=True)


def test_dia_cerrado_bloquea_los_registros(kiosco):
    cerrar_dia(timezone.localdate(), "super")
    sincronizar(forzar_copia=True)
    with pytest.raises(ReglaDeNegocioError, match="está cerrado"):
        _registrar(kiosco, "empezado")


def test_trabajo_terminado_sale_de_la_lista(kiosco):
    _registrar(kiosco, "empezado", op=0)
    _registrar(kiosco, "terminado", op=0)
    _registrar(kiosco, "empezado", op=1)
    _registrar(kiosco, "terminado", op=1)
    planta = local.cargar_planta()
    assert planta.trabajo(kiosco["revision"].trabajo_id).estado == est.TERMINADO
    assert kiosco["revision"].trabajo_id not in [t.trabajo_id for t in planta.activos]


# --- deshacer --------------------------------------------------------------------
def test_deshacer_dentro_del_minuto(kiosco):
    evento = _registrar(kiosco, "empezado")
    ana = kiosco["ana"].operario_id
    assert local.ultimo_deshacible(ana) == evento
    local.deshacer(local.cargar_planta(), operario_id=ana, evento_id=evento.evento_id)
    assert _op_local(kiosco).estado == est.PENDIENTE
    assert local.ultimo_deshacible(ana) is None
    with pytest.raises(ReglaDeNegocioError, match="Ya no se puede deshacer"):
        local.deshacer(local.cargar_planta(), operario_id=ana, evento_id=evento.evento_id)


def test_deshacer_vencido_o_de_otro_operario(kiosco):
    evento = _registrar(kiosco, "empezado")
    with pytest.raises(ReglaDeNegocioError):
        local.deshacer(
            local.cargar_planta(),
            operario_id=kiosco["beto"].operario_id,
            evento_id=evento.evento_id,
        )
    EventoPendiente.objects.update(creado_en=timezone.now() - timedelta(seconds=61))
    with pytest.raises(ReglaDeNegocioError, match="más de un minuto"):
        local.deshacer(
            local.cargar_planta(),
            operario_id=kiosco["ana"].operario_id,
            evento_id=evento.evento_id,
        )


def test_deshacer_un_terminado_devuelve_el_trabajo_a_la_lista(kiosco):
    for op in (0, 1):
        _registrar(kiosco, "empezado", op=op, confirmado=True)
        ultimo = _registrar(kiosco, "terminado", op=op)
    sincronizar(forzar_copia=True)  # la base central ya lo ve terminado
    planta = local.cargar_planta()
    local.deshacer(planta, operario_id=kiosco["ana"].operario_id, evento_id=ultimo.evento_id)
    planta = local.cargar_planta()
    assert kiosco["revision"].trabajo_id in [t.trabajo_id for t in planta.activos]


# --- sincronización ----------------------------------------------------------------
def test_envio_idempotente(kiosco):
    evento = _registrar(kiosco, "empezado")
    resultado = sincronizar()
    assert resultado.enviados == 1
    guardado = Evento.objects.get(evento_id=evento.evento_id)
    assert guardado.operario_id == kiosco["ana"].operario_id
    assert guardado.dispositivo == "tests" and guardado.registrado_por == "kiosco: Ana"
    # Reenviar el mismo evento (p. ej., se cortó antes de marcarlo) no lo duplica.
    EventoPendiente.objects.update(enviado_en=None)
    assert sincronizar().enviados == 1
    assert Evento.objects.filter(evento_id=evento.evento_id).count() == 1


def test_evento_rechazado_no_traba_la_cola(kiosco):
    EventoPendiente.objects.create(
        tipo="empezado",
        trabajo_id=uuid.uuid4(),  # no existe en la base central
        operacion_id=uuid.uuid4(),
        operario_id=kiosco["ana"].operario_id,
        ocurrido_en=timezone.now(),
        registrado_por="kiosco: Ana",
    )
    _registrar(kiosco, "empezado")
    resultado = sincronizar()
    assert (resultado.enviados, resultado.rechazados) == (1, 1)
    rechazado = EventoPendiente.objects.exclude(rechazado_en=None).get()
    assert "foreign key" in rechazado.ultimo_error.lower() or rechazado.ultimo_error


def test_sin_conexion_la_cola_espera(kiosco, monkeypatch):
    _registrar(kiosco, "empezado")

    def sin_red(*args, **kwargs):
        raise OperationalError("could not connect to server")

    monkeypatch.setattr("django.db.models.query.QuerySet.bulk_create", sin_red)
    resultado = sincronizar()
    assert resultado.sin_conexion and resultado.enviados == 0
    pendiente = EventoPendiente.objects.get()
    assert pendiente.pendiente and pendiente.intentos == 1 and "connect" in pendiente.ultimo_error
    # El kiosco sigue mostrando el estado con lo registrado.
    assert _op_local(kiosco).abierta


def test_anulacion_desde_oficina_no_reaparece_en_el_kiosco(kiosco):
    evento = _registrar(kiosco, "empezado")
    sincronizar()
    anular_evento(evento.evento_id, "ofi", "Se equivocó de trabajo")
    sincronizar(forzar_copia=True)
    assert _op_local(kiosco).estado == est.PENDIENTE


def test_copia_solo_se_renueva_mientras_se_usa(kiosco):
    Foto.objects.update(obtenida_en=timezone.now() - timedelta(hours=1))
    assert not sincronizar().copia_renovada  # nadie usó el kiosco
    from kiosco.sincronizacion import marcar_actividad

    marcar_actividad()
    assert sincronizar().copia_renovada


# --- pantallas -------------------------------------------------------------------
def test_kiosco_solo_responde_a_la_pc_local(client, kiosco):
    respuesta = client.get(reverse("kiosco:inicio"), REMOTE_ADDR="192.168.0.50")
    assert respuesta.status_code == 403
    assert client.get(reverse("kiosco:inicio")).status_code == 200


def test_flujo_completo_por_pantallas(client, kiosco):
    ana = kiosco["ana"].operario_id
    t = kiosco["revision"].trabajo_id
    op = kiosco["ops"][0].operacion_id

    inicio = client.get(reverse("kiosco:inicio")).content.decode()
    assert "Ana" in inicio and "Beto" in inicio
    lista = client.get(reverse("kiosco:pendientes", args=[ana])).content.decode()
    assert "KI-01" in lista and "Urgente" in lista and "Cuidar las rebabas" in lista
    detalle = client.get(reverse("kiosco:trabajo", args=[ana, t])).content.decode()
    assert "Tornear" in detalle and "Usar fresa nueva" in detalle

    url_op = reverse("kiosco:operacion", args=[ana, t, op])
    assert "Empecé" in client.get(url_op).content.decode()
    respuesta = client.post(url_op, {"accion": "empezado", "maquina_id": "101"})
    assert respuesta.status_code == 302
    lista = client.get(reverse("kiosco:pendientes", args=[ana])).content.decode()
    assert "Deshacer" in lista and "Empezó la operación 1 de KI-01" in lista

    # La pausa pide confirmación.
    confirmar = client.post(url_op, {"accion": "pausado", "maquina_id": "101"})
    assert confirmar.status_code == 200 and "¿Pausar la operación 1?" in confirmar.content.decode()
    assert EventoPendiente.objects.count() == 1
    client.post(url_op, {"accion": "pausado", "maquina_id": "101", "confirmado": "1"})
    assert EventoPendiente.objects.count() == 2

    estado = client.get(reverse("kiosco:estado")).content.decode()
    assert "2 pendientes de envío" in estado


def test_error_de_regla_se_muestra_en_la_pantalla(client, kiosco):
    ana = kiosco["ana"].operario_id
    url_op = reverse(
        "kiosco:operacion", args=[ana, kiosco["revision"].trabajo_id, kiosco["ops"][0].operacion_id]
    )
    respuesta = client.post(url_op, {"accion": "terminado"})
    assert respuesta.status_code == 409
    assert "no está empezada" in respuesta.content.decode()


def test_deshacer_por_pantalla(client, kiosco):
    evento = _registrar(kiosco, "empezado")
    ana = kiosco["ana"].operario_id
    respuesta = client.post(reverse("kiosco:deshacer", args=[ana, evento.evento_id]))
    assert respuesta.status_code == 302
    assert EventoPendiente.objects.filter(anula_evento_id=evento.evento_id).exists()


def test_pantallas_no_consultan_la_base_central(client, kiosco, django_assert_num_queries):
    ana = kiosco["ana"].operario_id
    t = kiosco["revision"].trabajo_id
    op = kiosco["ops"][0].operacion_id
    urls = [
        reverse("kiosco:inicio"),
        reverse("kiosco:pendientes", args=[ana]),
        reverse("kiosco:trabajo", args=[ana, t]),
        reverse("kiosco:operacion", args=[ana, t, op]),
        reverse("kiosco:estado"),
    ]
    with django_assert_num_queries(0, connection=connections["default"]):
        for url in urls:
            assert client.get(url).status_code == 200
        client.post(reverse("kiosco:operacion", args=[ana, t, op]), {"accion": "empezado"})


def test_comando_de_sincronizacion_una_vuelta(kiosco):
    from io import StringIO

    from django.core.management import call_command

    _registrar(kiosco, "empezado")
    salida = StringIO()
    call_command("sincronizar_kiosco", "--una-vez", stdout=salida)
    assert "Enviados: 1" in salida.getvalue()
    assert Evento.objects.count() == 1
