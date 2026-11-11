"""Reglas de dominio de trabajos, estado, anulaciones y cierre."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from planta.models import Evento, TrabajoRevision, Urgencia
from planta.servicios import ReglaDeNegocioError
from planta.servicios import estado as est
from planta.servicios.jornada import (
    anular_evento,
    cerrar_dia,
    dia_cerrado,
    reabrir_dia,
    resumen_dia,
)
from planta.servicios.trabajos import (
    DatosOperacion,
    DatosTrabajo,
    crear_trabajo,
    retirar_trabajo,
    revisar_trabajo,
    ruta_sugerida,
)

pytestmark = pytest.mark.django_db


def _datos(**kw):
    return DatosTrabajo(**{"plano": "BJ-100", **kw})


def _ops(n=2):
    return [DatosOperacion(maquina_id=100 + i, descripcion=f"Paso {i}") for i in range(1, n + 1)]


def _evento(revision, op, operario, tipo="empezado", minutos=0):
    return Evento.objects.create(
        tipo=tipo,
        trabajo_id=revision.trabajo_id,
        operacion_id=op.operacion_id,
        maquina_id=op.maquina_id,
        operario=operario,
        ocurrido_en=timezone.now() + timedelta(minutes=minutos),
        dispositivo="tests",
    )


# --- alta y revisiones -------------------------------------------------------
def test_ruta_sugerida_sale_de_planta_ref(demo):
    ruta = ruta_sugerida("EJ-220/A")
    assert [op.maquina_id for op in ruta] == [101, 103, 107]
    assert ruta[0].descripcion == "Desbaste y terminación"


def test_crear_trabajo_graba_revision_uno_con_operaciones():
    rev = crear_trabajo(_datos(cantidad=Decimal(10)), _ops(3), "ana")
    assert rev.revision == 1
    assert rev.tipo == TrabajoRevision.Tipo.ALTA
    assert [o.operacion_nro for o in rev.operaciones.order_by("operacion_nro")] == [1, 2, 3]
    estado = est.estado_trabajo(rev.trabajo_id)
    assert estado.estado == est.EN_COLA


def test_crear_trabajo_sin_operaciones_falla():
    with pytest.raises(ReglaDeNegocioError):
        crear_trabajo(_datos(), [], "ana")


def test_no_se_duplica_un_renglon_de_foxpro_activo():
    datos = _datos(origen="pedido", origen_ref="3001-2", pedido_id=3001)
    rev = crear_trabajo(datos, _ops(), "ana")
    with pytest.raises(ReglaDeNegocioError, match="ya está"):
        crear_trabajo(datos, _ops(), "ana")
    # Retirado, se puede volver a preparar.
    retirar_trabajo(rev.trabajo_id, "ana")
    assert crear_trabajo(datos, _ops(), "ana").revision == 1


def test_revisar_conserva_id_de_operaciones_y_numera():
    rev1 = crear_trabajo(_datos(), _ops(2), "ana")
    op1, op2 = rev1.operaciones.order_by("operacion_nro")
    nuevas = [
        DatosOperacion(maquina_id=200, descripcion="Nueva primera"),
        DatosOperacion(op2.maquina_id, "Paso 2 cambiado", None, op2.operacion_id),
        DatosOperacion(op1.maquina_id, op1.descripcion, "ojo", op1.operacion_id),
    ]
    rev2 = revisar_trabajo(
        rev1.trabajo_id, _datos(urgencia=Urgencia.URGENTE), nuevas, "beto", revision_base=1
    )
    assert rev2.revision == 2 and rev2.tipo == TrabajoRevision.Tipo.CAMBIO
    ops = list(rev2.operaciones.order_by("operacion_nro"))
    assert ops[1].operacion_id == op2.operacion_id
    assert ops[2].operacion_id == op1.operacion_id
    assert ops[0].operacion_id not in {op1.operacion_id, op2.operacion_id}
    assert est.estado_trabajo(rev1.trabajo_id).revision.urgencia == Urgencia.URGENTE


def test_revisar_rechaza_cambios_concurrentes():
    rev1 = crear_trabajo(_datos(), _ops(), "ana")
    ops = [
        DatosOperacion(o.maquina_id, o.descripcion, None, o.operacion_id)
        for o in rev1.operaciones.all()
    ]
    revisar_trabajo(rev1.trabajo_id, _datos(), ops, "ana", revision_base=1)
    with pytest.raises(ReglaDeNegocioError, match="Otra persona"):
        revisar_trabajo(rev1.trabajo_id, _datos(), ops, "beto", revision_base=1)


def test_no_se_quita_una_operacion_con_registros(operario):
    rev1 = crear_trabajo(_datos(), _ops(2), "ana")
    op1, op2 = rev1.operaciones.order_by("operacion_nro")
    _evento(rev1, op1, operario)
    with pytest.raises(ReglaDeNegocioError, match="registros"):
        revisar_trabajo(
            rev1.trabajo_id, _datos(), [DatosOperacion(operacion_id=op2.operacion_id)], "ana"
        )


def test_revisar_no_acepta_operaciones_ajenas():
    rev1 = crear_trabajo(_datos(), _ops(1), "ana")
    with pytest.raises(ReglaDeNegocioError, match="no pertenece"):
        revisar_trabajo(rev1.trabajo_id, _datos(), [DatosOperacion(operacion_id=uuid.uuid4())], "a")


def test_retirar_y_no_revisar_despues():
    rev1 = crear_trabajo(_datos(), _ops(), "ana")
    retiro = retirar_trabajo(rev1.trabajo_id, "ana", "Lo canceló el cliente")
    assert retiro.tipo == TrabajoRevision.Tipo.RETIRO
    assert est.estado_trabajo(rev1.trabajo_id).estado == est.RETIRADO
    with pytest.raises(ReglaDeNegocioError):
        retirar_trabajo(rev1.trabajo_id, "ana")
    with pytest.raises(ReglaDeNegocioError):
        revisar_trabajo(rev1.trabajo_id, _datos(), _ops(), "ana")


# --- estado derivado de eventos ----------------------------------------------
def test_estado_por_operacion_sigue_el_ultimo_evento(operario):
    rev = crear_trabajo(_datos(), _ops(2), "ana")
    op1, op2 = rev.operaciones.order_by("operacion_nro")
    _evento(rev, op1, operario, "empezado", 0)
    _evento(rev, op1, operario, "pausado", 5)
    _evento(rev, op2, operario, "empezado", 6)
    estado = est.estado_trabajo(rev.trabajo_id)
    assert [o.estado for o in estado.operaciones] == [est.PAUSADA, est.EN_PROCESO]
    assert estado.estado == est.TRABAJO_EN_PROCESO
    assert estado.terminadas == 0


def test_trabajo_terminado_cuando_todas_las_operaciones_terminan(operario):
    rev = crear_trabajo(_datos(), _ops(2), "ana")
    for i, op in enumerate(rev.operaciones.all()):
        _evento(rev, op, operario, "empezado", i * 10)
        _evento(rev, op, operario, "terminado", i * 10 + 5)
    estado = est.estado_trabajo(rev.trabajo_id)
    assert estado.estado == est.TERMINADO
    assert not estado.activo
    assert est.estado_trabajos(solo_activos=True) == []


def test_un_evento_anulado_no_cuenta(operario):
    rev = crear_trabajo(_datos(), _ops(1), "ana")
    (op,) = rev.operaciones.all()
    _evento(rev, op, operario, "empezado", 0)
    terminado = _evento(rev, op, operario, "terminado", 5)
    anular_evento(terminado.evento_id, "supervisor", "se equivocó de pieza")
    assert est.estado_trabajo(rev.trabajo_id).operaciones[0].estado == est.EN_PROCESO


def test_orden_de_la_lista_por_urgencia_y_fecha():
    hoy = date.today()
    normal = crear_trabajo(_datos(plano="A"), _ops(1), "ana")
    urgente_tarde = crear_trabajo(
        _datos(plano="B", urgencia=Urgencia.URGENTE, fecha_entrega_estimada=hoy + timedelta(9)),
        _ops(1),
        "ana",
    )
    urgente_pronto = crear_trabajo(
        _datos(plano="C", urgencia=Urgencia.URGENTE, fecha_entrega_estimada=hoy + timedelta(2)),
        _ops(1),
        "ana",
    )
    orden = [t.revision.plano for t in est.estado_trabajos()]
    assert orden == [urgente_pronto.plano, urgente_tarde.plano, normal.plano]


def test_refs_con_trabajo_activo():
    crear_trabajo(_datos(origen="pedido", origen_ref="3002-1"), _ops(1), "ana")
    retirado = crear_trabajo(_datos(origen="pedido", origen_ref="3003-1"), _ops(1), "ana")
    retirar_trabajo(retirado.trabajo_id, "ana")
    assert est.refs_con_trabajo_activo() == {"3002-1"}


# --- anulaciones y cierre ----------------------------------------------------
def test_anulacion_reglas(operario):
    rev = crear_trabajo(_datos(), _ops(1), "ana")
    (op,) = rev.operaciones.all()
    evento = _evento(rev, op, operario)
    anulacion = anular_evento(evento.evento_id, "sup", "error")
    assert anulacion.tipo == Evento.Tipo.ANULACION
    assert anulacion.anula_evento_id == evento.evento_id
    with pytest.raises(ReglaDeNegocioError, match="ya estaba anulado"):
        anular_evento(evento.evento_id, "sup")
    with pytest.raises(ReglaDeNegocioError, match="no se puede anular"):
        anular_evento(anulacion.evento_id, "sup")


def test_no_se_anula_en_un_dia_cerrado(operario):
    rev = crear_trabajo(_datos(), _ops(1), "ana")
    (op,) = rev.operaciones.all()
    evento = _evento(rev, op, operario)
    hoy = timezone.localdate()
    cerrar_dia(hoy, "sup")
    with pytest.raises(ReglaDeNegocioError, match="cerrado"):
        anular_evento(evento.evento_id, "oficina")
    reabrir_dia(hoy, "sup", "faltaba corregir un registro")
    assert anular_evento(evento.evento_id, "oficina")


def test_cierre_y_reapertura():
    hoy = timezone.localdate()
    assert not dia_cerrado(hoy)
    cerrar_dia(hoy, "sup")
    assert dia_cerrado(hoy)
    with pytest.raises(ReglaDeNegocioError, match="ya está cerrado"):
        cerrar_dia(hoy, "sup")
    with pytest.raises(ReglaDeNegocioError, match="motivo"):
        reabrir_dia(hoy, "sup", "")
    reabrir_dia(hoy, "sup", "corrección")
    assert not dia_cerrado(hoy)
    with pytest.raises(ReglaDeNegocioError, match="futuro"):
        cerrar_dia(hoy + timedelta(days=1), "sup")


def test_resumen_del_dia(operario):
    rev = crear_trabajo(_datos(), _ops(2), "ana")
    op1, op2 = rev.operaciones.order_by("operacion_nro")
    _evento(rev, op1, operario, "empezado", 0)
    e = _evento(rev, op2, operario, "empezado", 1)
    anular_evento(e.evento_id, "sup")
    resumen = resumen_dia(timezone.localdate())
    assert resumen.por_tipo["empezado"] == 1
    assert e.evento_id in resumen.anulados
    assert [op.operacion.operacion_id for _, op in resumen.abiertas] == [op1.operacion_id]
    assert not resumen.cerrado
