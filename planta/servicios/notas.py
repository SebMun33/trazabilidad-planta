"""Notas sobre trabajos y operaciones: observaciones, sugerencias, preguntas y respuestas.

Como todo en `planta`, una nota no se edita ni se borra. Cada una guarda quién
la escribió y cuándo. Al grabarse se avisa a oficina (ver `avisos.py`).
"""

import uuid
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Nota, Trabajo, TrabajoOperacion
from . import ReglaDeNegocioError, avisos

LARGO_MAXIMO = 2000
TIPOS_INICIALES = (Nota.Tipo.OBSERVACION, Nota.Tipo.SUGERENCIA, Nota.Tipo.PREGUNTA)


@dataclass
class HiloNota:
    """Una nota con sus respuestas, en orden."""

    nota: Nota
    respuestas: list[Nota] = field(default_factory=list)

    @property
    def pregunta_abierta(self) -> bool:
        return self.nota.tipo == Nota.Tipo.PREGUNTA and not self.respuestas


def _validar(trabajo_id, tipo, texto, operacion_id, responde_a_id) -> str:
    texto = (texto or "").strip()
    if not texto:
        raise ReglaDeNegocioError("La nota está vacía.")
    if len(texto) > LARGO_MAXIMO:
        raise ReglaDeNegocioError(f"La nota no puede superar los {LARGO_MAXIMO} caracteres.")
    if tipo not in Nota.Tipo.values:
        raise ReglaDeNegocioError("Tipo de nota desconocido.")
    if not Trabajo.objects.filter(trabajo_id=trabajo_id).exists():
        raise ReglaDeNegocioError("El trabajo no existe.")
    if (
        operacion_id
        and not TrabajoOperacion.objects.filter(
            revision__trabajo_id=trabajo_id, operacion_id=operacion_id
        ).exists()
    ):
        raise ReglaDeNegocioError("Esa operación no es de este trabajo.")
    if tipo == Nota.Tipo.RESPUESTA:
        original = Nota.objects.filter(nota_id=responde_a_id, trabajo_id=trabajo_id).first()
        if original is None:
            raise ReglaDeNegocioError("La nota que querés responder no existe.")
        if original.tipo == Nota.Tipo.RESPUESTA:
            raise ReglaDeNegocioError("Se responde a la nota original, no a una respuesta.")
    elif responde_a_id:
        raise ReglaDeNegocioError("Solo una respuesta puede referirse a otra nota.")
    return texto


@transaction.atomic
def crear_nota(
    *,
    trabajo_id,
    tipo: str,
    texto: str,
    autor: str,
    operacion_id=None,
    responde_a_id=None,
    operario_id: int | None = None,
    usuario_id: int | None = None,
    escrita_en=None,
    nota_id=None,
    dispositivo: str | None = None,
) -> Nota:
    """Graba la nota (si ya existe ese `nota_id`, la devuelve: envío idempotente)."""
    if nota_id and (existente := Nota.objects.filter(nota_id=nota_id).first()):
        return existente
    texto = _validar(trabajo_id, tipo, texto, operacion_id, responde_a_id)
    if responde_a_id and operacion_id is None:
        operacion_id = Nota.objects.get(nota_id=responde_a_id).operacion_id
    nota = Nota.objects.create(
        nota_id=nota_id or uuid.uuid4(),
        trabajo_id=trabajo_id,
        operacion_id=operacion_id,
        tipo=tipo,
        texto=texto,
        responde_a_id=responde_a_id,
        autor=autor,
        operario_id=operario_id,
        usuario_id=usuario_id,
        escrita_en=escrita_en or timezone.now(),
        dispositivo=dispositivo or settings.PLANTA_DISPOSITIVO,
    )
    transaction.on_commit(lambda: avisos.nota_creada(nota.nota_id))
    return nota


def hilos_de_trabajo(trabajo_id) -> list[HiloNota]:
    """Notas del trabajo agrupadas en hilos (nota + respuestas), de la más vieja a la más nueva."""
    hilos: dict = {}
    respuestas = []
    for nota in Nota.objects.filter(trabajo_id=trabajo_id).order_by("escrita_en", "registrada_en"):
        if nota.responde_a_id:
            respuestas.append(nota)
        else:
            hilos[nota.nota_id] = HiloNota(nota)
    for respuesta in respuestas:
        if respuesta.responde_a_id in hilos:
            hilos[respuesta.responde_a_id].respuestas.append(respuesta)
    return list(hilos.values())


def preguntas_abiertas(trabajo_ids) -> dict:
    """{trabajo_id: cantidad de preguntas sin respuesta}."""
    respondidas = set(
        Nota.objects.filter(trabajo_id__in=trabajo_ids, tipo=Nota.Tipo.RESPUESTA).values_list(
            "responde_a_id", flat=True
        )
    )
    conteo: dict = {}
    preguntas = Nota.objects.filter(trabajo_id__in=trabajo_ids, tipo=Nota.Tipo.PREGUNTA)
    for nota_id, trabajo_id in preguntas.values_list("nota_id", "trabajo_id"):
        if nota_id not in respondidas:
            conteo[trabajo_id] = conteo.get(trabajo_id, 0) + 1
    return conteo
