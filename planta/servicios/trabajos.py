"""Alta, revisión y retiro de trabajos pendientes (parte A, oficina).

Cada cambio graba una revisión nueva con su hoja de ruta completa. El
`operacion_id` de una operación se conserva entre revisiones para que los
eventos registrados en planta sigan apuntando a ella.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from ..models import Evento, Ruta, Trabajo, TrabajoOperacion, TrabajoRevision, Urgencia
from . import ReglaDeNegocioError
from .estado import estado_trabajos, ultimas_revisiones


@dataclass
class DatosTrabajo:
    plano: str
    origen: str = TrabajoRevision.Origen.MANUAL
    origen_ref: str | None = None
    pedido_id: int | None = None
    cotizacion_id: int | None = None
    plano_descripcion: str | None = None
    cliente_id: int | None = None
    cliente_nombre: str | None = None
    cantidad: Decimal | None = None
    urgencia: int = Urgencia.NORMAL
    fecha_entrega_estimada: date | None = None
    observaciones: str | None = None


@dataclass
class DatosOperacion:
    maquina_id: int | None = None
    descripcion: str | None = None
    observaciones: str | None = None
    # None = operación nueva; si viene, es la misma operación de la revisión anterior.
    operacion_id: uuid.UUID | None = None


def ruta_sugerida(plano: str) -> list[DatosOperacion]:
    """Hoja de ruta estándar del plano según FoxPro (vía planta_ref.rutas)."""
    return [
        DatosOperacion(maquina_id=r.maquina_id, descripcion=r.descripcion)
        for r in Ruta.objects.filter(plano=plano).order_by("operacion_nro")
    ]


def _bloquear(trabajo_id) -> None:
    """Serializa los cambios de un mismo trabajo (el rol de la app no tiene FOR UPDATE)."""
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [str(trabajo_id)])


def _limpiar(texto: str | None) -> str | None:
    texto = (texto or "").strip()
    return texto or None


def _grabar_revision(
    trabajo: Trabajo,
    numero: int,
    tipo: str,
    datos: DatosTrabajo,
    operaciones: list[DatosOperacion],
    usuario: str,
) -> TrabajoRevision:
    plano = _limpiar(datos.plano)
    if not plano:
        raise ReglaDeNegocioError("El plano es obligatorio.")
    if datos.cantidad is not None and datos.cantidad <= 0:
        raise ReglaDeNegocioError("La cantidad tiene que ser mayor a cero.")

    revision = TrabajoRevision.objects.create(
        trabajo=trabajo,
        revision=numero,
        tipo=tipo,
        origen=datos.origen,
        origen_ref=datos.origen_ref,
        pedido_id=datos.pedido_id,
        cotizacion_id=datos.cotizacion_id,
        plano=plano,
        plano_descripcion=_limpiar(datos.plano_descripcion),
        cliente_id=datos.cliente_id,
        cliente_nombre=_limpiar(datos.cliente_nombre),
        cantidad=datos.cantidad,
        urgencia=datos.urgencia,
        fecha_entrega_estimada=datos.fecha_entrega_estimada,
        observaciones=_limpiar(datos.observaciones),
        creado_por=usuario,
    )
    TrabajoOperacion.objects.bulk_create(
        TrabajoOperacion(
            revision=revision,
            operacion_id=op.operacion_id or uuid.uuid4(),
            operacion_nro=nro,
            maquina_id=op.maquina_id,
            descripcion=_limpiar(op.descripcion),
            observaciones=_limpiar(op.observaciones),
        )
        for nro, op in enumerate(operaciones, start=1)
    )
    return revision


def trabajo_activo_para(origen_ref: str):
    """Trabajo activo (no retirado ni terminado) creado desde ese renglón de FoxPro."""
    ids = list(
        ultimas_revisiones()
        .filter(origen_ref=origen_ref)
        .exclude(tipo=TrabajoRevision.Tipo.RETIRO)
        .values_list("trabajo_id", flat=True)
    )
    activos = estado_trabajos(ids, solo_activos=True)
    return activos[0] if activos else None


@transaction.atomic
def crear_trabajo(
    datos: DatosTrabajo, operaciones: list[DatosOperacion], usuario: str
) -> TrabajoRevision:
    """Alta de un trabajo en la lista de pendientes (revisión 1)."""
    if not operaciones:
        raise ReglaDeNegocioError("El trabajo necesita al menos una operación.")
    if datos.origen_ref:
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", [datos.origen_ref])
        if trabajo_activo_para(datos.origen_ref):
            raise ReglaDeNegocioError("Ese renglón ya está en la lista de pendientes.")
    trabajo = Trabajo.objects.create()
    return _grabar_revision(trabajo, 1, TrabajoRevision.Tipo.ALTA, datos, operaciones, usuario)


def _operaciones_con_eventos(trabajo_id) -> set[uuid.UUID]:
    return set(
        Evento.objects.filter(trabajo_id=trabajo_id)
        .exclude(tipo=Evento.Tipo.ANULACION)
        .values_list("operacion_id", flat=True)
    )


@transaction.atomic
def revisar_trabajo(
    trabajo_id,
    datos: DatosTrabajo,
    operaciones: list[DatosOperacion],
    usuario: str,
    *,
    revision_base: int | None = None,
) -> TrabajoRevision:
    """Graba una revisión nueva (tipo "cambio") con los datos y la ruta completos.

    `revision_base` es la revisión que el usuario tenía abierta: si mientras
    tanto otro la cambió, se rechaza para no pisar su cambio.
    """
    _bloquear(trabajo_id)
    actual = ultimas_revisiones([trabajo_id]).first()
    if actual is None:
        raise ReglaDeNegocioError("El trabajo no existe.")
    if actual.tipo == TrabajoRevision.Tipo.RETIRO:
        raise ReglaDeNegocioError("El trabajo fue retirado de la lista de pendientes.")
    if revision_base is not None and revision_base != actual.revision:
        raise ReglaDeNegocioError(
            f"Otra persona guardó la revisión {actual.revision} mientras editabas. "
            "Volvé a abrir el trabajo para ver los cambios."
        )
    if not operaciones:
        raise ReglaDeNegocioError("El trabajo necesita al menos una operación.")

    ids_actuales = set(actual.operaciones.values_list("operacion_id", flat=True))
    ids_nuevos = {op.operacion_id for op in operaciones if op.operacion_id}
    if not ids_nuevos <= ids_actuales:
        raise ReglaDeNegocioError("Una de las operaciones no pertenece a este trabajo.")
    quitadas_con_eventos = (ids_actuales - ids_nuevos) & _operaciones_con_eventos(trabajo_id)
    if quitadas_con_eventos:
        raise ReglaDeNegocioError(
            "No se puede quitar una operación que ya tiene registros de planta."
        )

    # El origen no cambia entre revisiones.
    datos.origen = actual.origen
    datos.origen_ref = actual.origen_ref
    datos.cotizacion_id = actual.cotizacion_id
    return _grabar_revision(
        actual.trabajo,
        actual.revision + 1,
        TrabajoRevision.Tipo.CAMBIO,
        datos,
        operaciones,
        usuario,
    )


@transaction.atomic
def retirar_trabajo(trabajo_id, usuario: str, motivo: str | None = None) -> TrabajoRevision:
    """Saca el trabajo de la lista de pendientes. Queda en la historia."""
    _bloquear(trabajo_id)
    actual = ultimas_revisiones([trabajo_id]).prefetch_related("operaciones").first()
    if actual is None:
        raise ReglaDeNegocioError("El trabajo no existe.")
    if actual.tipo == TrabajoRevision.Tipo.RETIRO:
        raise ReglaDeNegocioError("El trabajo ya estaba retirado.")
    datos = DatosTrabajo(
        plano=actual.plano,
        origen=actual.origen,
        origen_ref=actual.origen_ref,
        pedido_id=actual.pedido_id,
        cotizacion_id=actual.cotizacion_id,
        plano_descripcion=actual.plano_descripcion,
        cliente_id=actual.cliente_id,
        cliente_nombre=actual.cliente_nombre,
        cantidad=actual.cantidad,
        urgencia=actual.urgencia,
        fecha_entrega_estimada=actual.fecha_entrega_estimada,
        observaciones=motivo,
    )
    operaciones = [
        DatosOperacion(o.maquina_id, o.descripcion, o.observaciones, o.operacion_id)
        for o in actual.operaciones.all()
    ]
    return _grabar_revision(
        actual.trabajo,
        actual.revision + 1,
        TrabajoRevision.Tipo.RETIRO,
        datos,
        operaciones,
        usuario,
    )
