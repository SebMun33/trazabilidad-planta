"""Estado de planta visto desde el kiosco y reglas para registrar.

Todo se calcula con datos locales: la última copia (`Foto`) más los eventos
registrados en el kiosco que la copia todavía no incluye. Usa las mismas reglas
de derivación de estado que la oficina (`planta.servicios.estado`).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cuentas.nombres import normalizar
from planta.models import Evento, Nota, Urgencia
from planta.servicios import ReglaDeNegocioError
from planta.servicios import estado as est

from .models import EventoPendiente, Foto, NotaPendiente
from .router import LOCAL

ACCIONES = {
    "empezado": Evento.Tipo.EMPEZADO,
    "pausado": Evento.Tipo.PAUSADO,
    "terminado": Evento.Tipo.TERMINADO,
}
VERBOS = {
    Evento.Tipo.EMPEZADO: "Empezó",
    Evento.Tipo.PAUSADO: "Pausó",
    Evento.Tipo.TERMINADO: "Terminó",
}


class RequiereConfirmacion(Exception):
    """El registro es válido pero conviene que el operario lo confirme."""


def _fecha_hora(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


@dataclass
class EventoLocal:
    evento_id: uuid.UUID
    tipo: str
    operacion_id: uuid.UUID | None
    operario_id: int | None
    maquina_id: int | None
    ocurrido_en: datetime
    registrado_en: datetime
    anula_evento_id: uuid.UUID | None = None
    pendiente: bool = False


@dataclass
class NotaLocal:
    nota_id: uuid.UUID
    operacion_id: uuid.UUID | None
    tipo: str
    texto: str
    autor: str
    escrita_en: datetime
    responde_a: uuid.UUID | None = None
    pendiente: bool = False
    respuestas: list["NotaLocal"] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        return Nota.Tipo(self.tipo).label


@dataclass
class OperacionLocal:
    operacion_id: uuid.UUID
    nro: int
    maquina_id: int | None
    maquina: str | None
    descripcion: str | None
    observaciones: str | None
    estado: str = est.PENDIENTE
    ultimo: EventoLocal | None = None
    operario_nombre: str | None = None  # quién hizo el último movimiento

    @property
    def etiqueta(self) -> str:
        return est.ETIQUETAS[self.estado]

    @property
    def abierta(self) -> bool:
        return self.estado == est.EN_PROCESO

    @property
    def operario_id(self) -> int | None:
        return self.ultimo.operario_id if self.ultimo else None


@dataclass
class TrabajoLocal:
    trabajo_id: uuid.UUID
    plano: str
    plano_descripcion: str | None
    cliente: str | None
    pedido_id: int | None
    cotizacion_id: int | None
    cantidad: Decimal | None
    urgencia: int
    fecha_entrega_estimada: date | None
    observaciones: str | None
    creado_en: datetime
    operaciones: list[OperacionLocal] = field(default_factory=list)
    notas: list[NotaLocal] = field(default_factory=list)  # hilos: nota y sus respuestas

    @property
    def estado(self) -> str:
        if self.operaciones and all(op.estado == est.TERMINADA for op in self.operaciones):
            return est.TERMINADO
        if any(op.estado != est.PENDIENTE for op in self.operaciones):
            return est.TRABAJO_EN_PROCESO
        return est.EN_COLA

    @property
    def activo(self) -> bool:
        return self.estado in (est.EN_COLA, est.TRABAJO_EN_PROCESO)

    @property
    def etiqueta(self) -> str:
        return est.ETIQUETAS[self.estado]

    @property
    def urgencia_etiqueta(self) -> str:
        return Urgencia(self.urgencia).label

    @property
    def terminadas(self) -> int:
        return sum(op.estado == est.TERMINADA for op in self.operaciones)

    @property
    def abiertas(self) -> list[OperacionLocal]:
        return [op for op in self.operaciones if op.abierta]

    def operacion(self, operacion_id) -> OperacionLocal | None:
        buscado = str(operacion_id)
        return next((op for op in self.operaciones if str(op.operacion_id) == buscado), None)

    def orden(self) -> tuple:
        return (-self.urgencia, self.fecha_entrega_estimada or date.max, self.creado_en)

    def notas_de(self, operacion_id=None) -> list[NotaLocal]:
        """Hilos de una operación (o los del trabajo en general si no se indica)."""
        buscado = str(operacion_id) if operacion_id else None
        return [
            n for n in self.notas if (str(n.operacion_id) if n.operacion_id else None) == buscado
        ]

    @property
    def preguntas_abiertas(self) -> int:
        return sum(n.tipo == Nota.Tipo.PREGUNTA and not n.respuestas for n in self.notas)


@dataclass
class PlantaLocal:
    obtenida_en: datetime
    operarios: dict[int, str]
    maquinas: dict[int, str]
    dias_cerrados: set[date]
    trabajos: list[TrabajoLocal]
    operario_prueba: int | None = None

    @property
    def activos(self) -> list[TrabajoLocal]:
        return [t for t in self.trabajos if t.activo]

    def trabajo(self, trabajo_id) -> TrabajoLocal | None:
        return next((t for t in self.trabajos if str(t.trabajo_id) == str(trabajo_id)), None)

    def dia_cerrado(self, fecha: date) -> bool:
        return fecha in self.dias_cerrados

    def operarios_visibles(self, prueba: bool = False) -> dict[int, str]:
        """En modo prueba, solo el operario de prueba; en planta, todos menos él."""
        return {i: n for i, n in self.operarios.items() if (i == self.operario_prueba) == prueba}

    def buscar_operario(self, nombre: str, prueba: bool = False) -> int | None:
        """Operario por nombre, sin importar mayúsculas ni tildes."""
        buscado = normalizar(nombre)
        if not buscado:
            return None
        visibles = self.operarios_visibles(prueba)
        return next((i for i, n in visibles.items() if normalizar(n) == buscado), None)

    def abiertas_de(self, operario_id: int) -> list[tuple[TrabajoLocal, OperacionLocal]]:
        return [
            (t, op)
            for t in self.trabajos
            for op in t.operaciones
            if op.abierta and op.operario_id == operario_id
        ]

    @property
    def copia_vieja(self) -> bool:
        limite = timedelta(seconds=settings.KIOSCO_COPIA_VIEJA_SEGUNDOS)
        return timezone.now() - self.obtenida_en > limite


def _eventos_locales(foto: Foto) -> dict[str, list[EventoLocal]]:
    """Eventos del kiosco que la copia todavía no incluye, por trabajo.

    Entran los que siguen en cola y los enviados después de pedir la copia: lo
    enviado antes ya viene en la copia (si no fue anulado desde la oficina).
    """
    por_trabajo: dict[str, list[EventoLocal]] = {}
    for p in EventoPendiente.objects.filter(rechazado_en=None).order_by("id"):
        if p.enviado_en is not None and p.enviado_en < foto.obtenida_en:
            continue
        por_trabajo.setdefault(str(p.trabajo_id), []).append(
            EventoLocal(
                evento_id=p.evento_id,
                tipo=p.tipo,
                operacion_id=p.operacion_id,
                operario_id=p.operario_id,
                maquina_id=p.maquina_id,
                ocurrido_en=p.ocurrido_en,
                registrado_en=p.creado_en,
                anula_evento_id=p.anula_evento_id,
                pendiente=p.pendiente,
            )
        )
    return por_trabajo


def _notas_locales(foto: Foto) -> dict[str, list[NotaLocal]]:
    """Notas del kiosco que la copia todavía no incluye (misma regla que los eventos)."""
    por_trabajo: dict[str, list[NotaLocal]] = {}
    for p in NotaPendiente.objects.filter(rechazado_en=None).order_by("id"):
        if p.enviado_en is not None and p.enviado_en < foto.obtenida_en:
            continue
        por_trabajo.setdefault(str(p.trabajo_id), []).append(
            NotaLocal(
                nota_id=p.nota_id,
                operacion_id=p.operacion_id,
                tipo=p.tipo,
                texto=p.texto,
                autor=p.autor,
                escrita_en=p.escrita_en,
                responde_a=p.responde_a,
                pendiente=p.pendiente,
            )
        )
    return por_trabajo


def _hilos(datos: list[dict], locales: list[NotaLocal]) -> list[NotaLocal]:
    notas = [
        NotaLocal(
            nota_id=uuid.UUID(n["nota_id"]),
            operacion_id=uuid.UUID(n["operacion_id"]) if n["operacion_id"] else None,
            tipo=n["tipo"],
            texto=n["texto"],
            autor=n["autor"],
            escrita_en=_fecha_hora(n["escrita_en"]),
            responde_a=uuid.UUID(n["responde_a"]) if n["responde_a"] else None,
        )
        for n in datos
    ]
    ids = {n.nota_id for n in notas}
    notas += [n for n in locales if n.nota_id not in ids]
    hilos = {n.nota_id: n for n in notas if n.responde_a is None}
    for n in notas:
        if n.responde_a is not None and n.responde_a in hilos:
            hilos[n.responde_a].respuestas.append(n)
    return sorted(hilos.values(), key=lambda n: n.escrita_en)


def _trabajo_local(
    datos: dict,
    locales: list[EventoLocal],
    maquinas: dict,
    operarios: dict,
    notas_locales: list[NotaLocal] | None = None,
) -> TrabajoLocal:
    eventos = [
        EventoLocal(
            evento_id=uuid.UUID(e["evento_id"]),
            tipo=e["tipo"],
            operacion_id=uuid.UUID(e["operacion_id"]),
            operario_id=e["operario_id"],
            maquina_id=e["maquina_id"],
            ocurrido_en=_fecha_hora(e["ocurrido_en"]),
            registrado_en=_fecha_hora(e["registrado_en"]),
        )
        for e in datos["eventos"]
    ]
    ids = {e.evento_id for e in eventos}
    eventos += [e for e in locales if e.evento_id not in ids]
    por_operacion = est.estado_por_operacion(est.eventos_vigentes(eventos))

    operaciones = []
    for op in datos["operaciones"]:
        operacion_id = uuid.UUID(op["operacion_id"])
        estado, ultimo = por_operacion.get(operacion_id, (est.PENDIENTE, None))
        operaciones.append(
            OperacionLocal(
                operacion_id=operacion_id,
                nro=op["nro"],
                maquina_id=op["maquina_id"],
                maquina=maquinas.get(op["maquina_id"]),
                descripcion=op["descripcion"],
                observaciones=op["observaciones"],
                estado=estado,
                ultimo=ultimo,
                operario_nombre=operarios.get(ultimo.operario_id) if ultimo else None,
            )
        )
    return TrabajoLocal(
        trabajo_id=uuid.UUID(datos["trabajo_id"]),
        plano=datos["plano"],
        plano_descripcion=datos["plano_descripcion"],
        cliente=datos["cliente"],
        pedido_id=datos["pedido_id"],
        cotizacion_id=datos["cotizacion_id"],
        cantidad=Decimal(datos["cantidad"]) if datos["cantidad"] else None,
        urgencia=datos["urgencia"],
        fecha_entrega_estimada=(
            date.fromisoformat(datos["fecha_entrega_estimada"])
            if datos["fecha_entrega_estimada"]
            else None
        ),
        observaciones=datos["observaciones"],
        creado_en=_fecha_hora(datos["creado_en"]),
        operaciones=sorted(operaciones, key=lambda o: o.nro),
        notas=_hilos(datos.get("notas", []), notas_locales or []),
    )


def cargar_planta() -> PlantaLocal | None:
    """Estado local completo, o None si todavía no hubo ninguna sincronización."""
    foto = Foto.objects.filter(id=1).first()
    if foto is None:
        return None
    datos = foto.datos
    maquinas = {m_id: nombre for m_id, nombre in datos["maquinas"]}
    operarios = {o["id"]: o["nombre"] for o in datos["operarios"]}
    locales = _eventos_locales(foto)
    notas = _notas_locales(foto)
    trabajos = [
        _trabajo_local(
            t,
            locales.get(t["trabajo_id"], []),
            maquinas,
            operarios,
            notas.get(t["trabajo_id"], []),
        )
        for t in datos["trabajos"]
    ]
    return PlantaLocal(
        obtenida_en=foto.obtenida_en,
        operarios=operarios,
        maquinas=maquinas,
        dias_cerrados={date.fromisoformat(f) for f in datos["dias_cerrados"]},
        trabajos=sorted(trabajos, key=TrabajoLocal.orden),
        operario_prueba=datos.get("operario_prueba"),
    )


# --- registrar -----------------------------------------------------------------
def registrar(
    planta: PlantaLocal,
    *,
    operario_id: int,
    trabajo_id,
    operacion_id,
    accion: str,
    maquina_id: int | None = None,
    observaciones: str = "",
    confirmado: bool = False,
    cargado_por: int | None = None,
) -> EventoPendiente:
    """Valida con el estado local y deja el evento en la cola de envío.

    `operario_id` es quien hizo el trabajo; `cargado_por`, quien lo anotó en el
    kiosco (por defecto, el mismo): cualquier operario puede anotar lo de otro.
    """
    tipo = ACCIONES.get(accion)
    if tipo is None:
        raise ReglaDeNegocioError("Acción desconocida.")
    cargado_por = cargado_por if cargado_por is not None else operario_id
    if operario_id not in planta.operarios or cargado_por not in planta.operarios:
        raise ReglaDeNegocioError("Ese operario no está activo.")
    nombre_cargador = planta.operarios[cargado_por]
    trabajo = planta.trabajo(trabajo_id)
    if trabajo is None or not trabajo.activo:
        raise ReglaDeNegocioError("Ese trabajo ya no está en la lista de pendientes.")
    op = trabajo.operacion(operacion_id)
    if op is None:
        raise ReglaDeNegocioError("Esa operación ya no forma parte del trabajo.")
    if planta.dia_cerrado(timezone.localdate()):
        raise ReglaDeNegocioError(
            "El día de hoy está cerrado. Pedile a un supervisor que lo reabra."
        )

    if tipo == Evento.Tipo.EMPEZADO:
        if op.estado == est.TERMINADA:
            raise ReglaDeNegocioError("Esa operación ya está terminada.")
        if op.abierta:
            quien = planta.operarios.get(op.operario_id, "otro operario")
            raise ReglaDeNegocioError(f"Esa operación ya está empezada ({quien}).")
        otras = [(t, o) for t, o in planta.abiertas_de(operario_id) if o is not op]
        if otras and not confirmado:
            t, o = otras[0]
            if operario_id == cargado_por:
                quien = "Tenés"
            else:
                quien = f"{planta.operarios[operario_id]} tiene"
            raise RequiereConfirmacion(
                f"{quien} abierta la operación {o.nro} de {t.plano}. ¿Empezar esta también?"
            )
    elif not op.abierta:
        raise ReglaDeNegocioError("Esa operación no está empezada: primero tocá «Empecé».")

    if maquina_id is not None and maquina_id not in planta.maquinas:
        raise ReglaDeNegocioError("Esa máquina no existe.")
    return EventoPendiente.objects.create(
        tipo=tipo,
        trabajo_id=trabajo.trabajo_id,
        operacion_id=op.operacion_id,
        maquina_id=maquina_id if maquina_id is not None else op.maquina_id,
        operario_id=operario_id,
        cargado_por_id=cargado_por,
        ocurrido_en=timezone.now(),
        observaciones=observaciones.strip(),
        registrado_por=f"kiosco: {nombre_cargador}",
    )


# --- deshacer --------------------------------------------------------------------
def _limite_deshacer() -> datetime:
    return timezone.now() - timedelta(seconds=settings.KIOSCO_DESHACER_SEGUNDOS)


def ultimo_deshacible(operario_id: int) -> EventoPendiente | None:
    """Último registro del operario que todavía se puede deshacer (60 s)."""
    propios = Q(cargado_por_id=operario_id) | Q(cargado_por_id=None, operario_id=operario_id)
    ultimo = (
        EventoPendiente.objects.filter(propios, rechazado_en=None)
        .exclude(tipo=Evento.Tipo.ANULACION)
        .order_by("-id")
        .first()
    )
    if ultimo is None or ultimo.creado_en < _limite_deshacer():
        return None
    if EventoPendiente.objects.filter(anula_evento_id=ultimo.evento_id).exists():
        return None
    return ultimo


@transaction.atomic(using=LOCAL)
def deshacer(planta: PlantaLocal, *, operario_id: int, evento_id) -> EventoPendiente:
    """Graba una anulación del registro (el original no se borra)."""
    original = ultimo_deshacible(operario_id)
    if original is None or str(original.evento_id) != str(evento_id):
        raise ReglaDeNegocioError(
            "Ya no se puede deshacer: pasó más de un minuto o no es tu último registro."
        )
    if planta.dia_cerrado(timezone.localdate()):
        raise ReglaDeNegocioError("El día de hoy está cerrado.")
    return EventoPendiente.objects.create(
        tipo=Evento.Tipo.ANULACION,
        trabajo_id=original.trabajo_id,
        operacion_id=original.operacion_id,
        operario_id=operario_id,
        cargado_por_id=operario_id,
        anula_evento_id=original.evento_id,
        ocurrido_en=timezone.now(),
        observaciones="Deshecho en el kiosco",
        registrado_por=original.registrado_por,
    )


def describir(evento: EventoPendiente, planta: PlantaLocal | None) -> str:
    """Texto corto de un registro, para el aviso de «Deshacer»."""
    verbo = VERBOS.get(evento.tipo, evento.tipo)
    trabajo = planta.trabajo(evento.trabajo_id) if planta else None
    if trabajo is None:
        return verbo
    op = trabajo.operacion(evento.operacion_id)
    nro = f" la operación {op.nro}" if op else ""
    texto = f"{verbo}{nro} de {trabajo.plano}"
    if evento.cargado_por_id and evento.operario_id != evento.cargado_por_id:
        quien = planta.operarios.get(evento.operario_id, "otro operario")
        texto += f" (por {quien})"
    return texto


# --- notas -----------------------------------------------------------------------
TIPOS_KIOSCO = (Nota.Tipo.OBSERVACION, Nota.Tipo.SUGERENCIA, Nota.Tipo.PREGUNTA)


def escribir_nota(
    planta: PlantaLocal,
    *,
    operario_id: int,
    trabajo_id,
    texto: str,
    tipo: str = Nota.Tipo.OBSERVACION,
    operacion_id=None,
    responde_a=None,
) -> NotaPendiente:
    """Deja una nota del operario en la cola de envío (también sin conexión)."""
    nombre = planta.operarios.get(operario_id)
    if nombre is None:
        raise ReglaDeNegocioError("Ese operario no está activo.")
    trabajo = planta.trabajo(trabajo_id)
    if trabajo is None:
        raise ReglaDeNegocioError("Ese trabajo ya no está en la lista de pendientes.")
    texto = (texto or "").strip()
    if not texto:
        raise ReglaDeNegocioError("La nota está vacía.")
    if len(texto) > 2000:
        raise ReglaDeNegocioError("La nota no puede superar los 2000 caracteres.")
    if responde_a:
        original = next((n for n in trabajo.notas if str(n.nota_id) == str(responde_a)), None)
        if original is None:
            raise ReglaDeNegocioError("La nota que querés responder no existe.")
        tipo, operacion_id = Nota.Tipo.RESPUESTA, original.operacion_id
    elif tipo not in TIPOS_KIOSCO:
        raise ReglaDeNegocioError("Tipo de nota desconocido.")
    if operacion_id and trabajo.operacion(operacion_id) is None:
        raise ReglaDeNegocioError("Esa operación no es de este trabajo.")
    return NotaPendiente.objects.create(
        trabajo_id=trabajo.trabajo_id,
        operacion_id=operacion_id or None,
        tipo=tipo,
        texto=texto,
        responde_a=responde_a or None,
        operario_id=operario_id,
        autor=nombre,
        escrita_en=timezone.now(),
    )
