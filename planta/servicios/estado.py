"""Estado actual de trabajos y operaciones, calculado a partir de los eventos.

No se guarda ningún estado: se deriva de la última revisión de cada trabajo y de
los eventos no anulados (ver docs/decisiones/0002-eventos-en-vez-de-estados.md).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from django.db.models import Q

from ..models import Evento, Maquina, TrabajoOperacion, TrabajoRevision, Urgencia

# Estados de una operación
PENDIENTE = "pendiente"
EN_PROCESO = "en_proceso"
PAUSADA = "pausada"
TERMINADA = "terminada"

# Estados de un trabajo
EN_COLA = "en_cola"
TRABAJO_EN_PROCESO = "en_proceso"
TERMINADO = "terminado"
RETIRADO = "retirado"

ETIQUETAS = {
    PENDIENTE: "Pendiente",
    EN_PROCESO: "En proceso",
    PAUSADA: "Pausada",
    TERMINADA: "Terminada",
    EN_COLA: "En cola",
    TERMINADO: "Terminado en planta",
    RETIRADO: "Retirado",
}

_ESTADO_POR_EVENTO = {
    Evento.Tipo.EMPEZADO: EN_PROCESO,
    Evento.Tipo.PAUSADO: PAUSADA,
    Evento.Tipo.TERMINADO: TERMINADA,
}


@dataclass
class EstadoOperacion:
    operacion: TrabajoOperacion
    estado: str = PENDIENTE
    ultimo_evento: Evento | None = None
    maquina: Maquina | None = None

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS[self.estado]

    @property
    def abierta(self) -> bool:
        """Hay un "empezado" sin pausa ni fin posterior."""
        return self.estado == EN_PROCESO


@dataclass
class EstadoTrabajo:
    revision: TrabajoRevision
    operaciones: list[EstadoOperacion] = field(default_factory=list)
    eventos: list[Evento] = field(default_factory=list)

    @property
    def trabajo_id(self) -> UUID:
        return self.revision.trabajo_id

    @property
    def estado(self) -> str:
        if self.revision.tipo == TrabajoRevision.Tipo.RETIRO:
            return RETIRADO
        if self.operaciones and all(op.estado == TERMINADA for op in self.operaciones):
            return TERMINADO
        if any(op.estado != PENDIENTE for op in self.operaciones):
            return TRABAJO_EN_PROCESO
        return EN_COLA

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS[self.estado]

    @property
    def terminadas(self) -> int:
        return sum(op.estado == TERMINADA for op in self.operaciones)

    @property
    def activo(self) -> bool:
        """Sigue en la lista de pendientes (no retirado ni terminado)."""
        return self.estado in (EN_COLA, TRABAJO_EN_PROCESO)

    @property
    def urgencia_etiqueta(self) -> str:
        return Urgencia(self.revision.urgencia).label

    @property
    def ultima_actividad(self) -> datetime | None:
        return self.eventos[-1].ocurrido_en if self.eventos else None

    def orden(self) -> tuple:
        """Más urgente primero, después la fecha estimada más próxima, después el más viejo."""
        fecha = self.revision.fecha_entrega_estimada or date.max
        return (-self.revision.urgencia, fecha, self.revision.creado_en)


def eventos_vigentes(eventos: list[Evento]) -> list[Evento]:
    """Eventos de trabajo que no fueron anulados, en orden cronológico."""
    anulados = {e.anula_evento_id for e in eventos if e.tipo == Evento.Tipo.ANULACION}
    vigentes = [
        e for e in eventos if e.tipo != Evento.Tipo.ANULACION and e.evento_id not in anulados
    ]
    return sorted(vigentes, key=lambda e: (e.ocurrido_en, e.registrado_en))


def ultimas_revisiones(trabajo_ids=None):
    """Queryset con la revisión vigente (la de mayor número) de cada trabajo."""
    qs = TrabajoRevision.objects.order_by("trabajo_id", "-revision").distinct("trabajo_id")
    if trabajo_ids is not None:
        qs = qs.filter(trabajo_id__in=trabajo_ids)
    return qs


def estado_trabajos(trabajo_ids=None, *, solo_activos: bool = False) -> list[EstadoTrabajo]:
    """Estado de los trabajos indicados (o de todos), ordenados por prioridad."""
    revisiones = list(ultimas_revisiones(trabajo_ids).prefetch_related("operaciones"))
    if not revisiones:
        return []

    ids = [r.trabajo_id for r in revisiones]
    eventos_por_trabajo: dict[UUID, list[Evento]] = defaultdict(list)
    for evento in Evento.objects.filter(trabajo_id__in=ids).select_related("operario"):
        eventos_por_trabajo[evento.trabajo_id].append(evento)

    maquinas = {m.maquina_id: m for m in Maquina.objects.all()}

    resultado = []
    for revision in revisiones:
        vigentes = eventos_vigentes(eventos_por_trabajo[revision.trabajo_id])
        ultimo_por_operacion = {e.operacion_id: e for e in vigentes}
        operaciones = []
        for op in sorted(revision.operaciones.all(), key=lambda o: o.operacion_nro):
            ultimo = ultimo_por_operacion.get(op.operacion_id)
            operaciones.append(
                EstadoOperacion(
                    operacion=op,
                    estado=_ESTADO_POR_EVENTO[ultimo.tipo] if ultimo else PENDIENTE,
                    ultimo_evento=ultimo,
                    maquina=maquinas.get(op.maquina_id),
                )
            )
        resultado.append(EstadoTrabajo(revision, operaciones, vigentes))

    if solo_activos:
        resultado = [t for t in resultado if t.activo]
    return sorted(resultado, key=EstadoTrabajo.orden)


def estado_trabajo(trabajo_id) -> EstadoTrabajo | None:
    estados = estado_trabajos([trabajo_id])
    return estados[0] if estados else None


def refs_con_trabajo_activo() -> set[str]:
    """`origen_ref` de los renglones de FoxPro que ya tienen un trabajo activo."""
    revisiones = (
        ultimas_revisiones().filter(~Q(origen_ref=None)).exclude(tipo=TrabajoRevision.Tipo.RETIRO)
    )
    ids = {r.trabajo_id: r.origen_ref for r in revisiones}
    return {ids[t.trabajo_id] for t in estado_trabajos(list(ids), solo_activos=True)}
