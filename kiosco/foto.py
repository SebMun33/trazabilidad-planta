"""Arma, desde la base central, la copia que el kiosco guarda localmente.

Corre en el proceso de sincronización (nunca en una pantalla del kiosco). El
resultado es JSON puro: se guarda tal cual en `kiosco.Foto`.
"""

from datetime import timedelta

from django.utils import timezone

from cuentas.prueba import operario_prueba_id
from planta.models import CierreDia, Maquina, Nota, Operario, TrabajoRevision
from planta.servicios import estado as est

# Los trabajos terminados siguen un día en la copia: así un "Terminé" se puede
# deshacer y el trabajo vuelve a aparecer sin esperar a la base central.
TERMINADOS_VISIBLES = timedelta(days=1)
DIAS_DE_CIERRE = 7


def _iso(valor):
    return valor.isoformat() if valor is not None else None


def _nota(n: Nota) -> dict:
    return {
        "nota_id": str(n.nota_id),
        "operacion_id": str(n.operacion_id) if n.operacion_id else None,
        "tipo": n.tipo,
        "texto": n.texto,
        "autor": n.autor,
        "escrita_en": _iso(n.escrita_en),
        "responde_a": str(n.responde_a_id) if n.responde_a_id else None,
    }


def _trabajo(t: est.EstadoTrabajo, notas: list) -> dict:
    r = t.revision
    return {
        "trabajo_id": str(r.trabajo_id),
        "revision": r.revision,
        "plano": r.plano,
        "plano_descripcion": r.plano_descripcion,
        "cliente": r.cliente_nombre,
        "pedido_id": r.pedido_id,
        "cotizacion_id": r.cotizacion_id,
        "cantidad": str(r.cantidad) if r.cantidad is not None else None,
        "urgencia": r.urgencia,
        "fecha_entrega_estimada": _iso(r.fecha_entrega_estimada),
        "observaciones": r.observaciones,
        "creado_en": _iso(r.creado_en),
        "operaciones": [
            {
                "operacion_id": str(op.operacion.operacion_id),
                "nro": op.operacion.operacion_nro,
                "maquina_id": op.operacion.maquina_id,
                "descripcion": op.operacion.descripcion,
                "observaciones": op.operacion.observaciones,
            }
            for op in t.operaciones
        ],
        "eventos": [
            {
                "evento_id": str(e.evento_id),
                "tipo": e.tipo,
                "operacion_id": str(e.operacion_id),
                "operario_id": e.operario_id,
                "maquina_id": e.maquina_id,
                "ocurrido_en": _iso(e.ocurrido_en),
                "registrado_en": _iso(e.registrado_en),
            }
            for e in t.eventos
        ],
        "notas": [_nota(n) for n in notas],
    }


def _dias_cerrados(hoy) -> list[str]:
    """Fechas recientes cuyo último movimiento es un cierre."""
    ultimo: dict = {}
    movimientos = CierreDia.objects.filter(fecha__gte=hoy - timedelta(days=DIAS_DE_CIERRE))
    for c in movimientos.order_by("fecha", "registrado_en"):
        ultimo[c.fecha] = c.tipo
    return sorted(f.isoformat() for f, tipo in ultimo.items() if tipo == CierreDia.Tipo.CIERRE)


def armar_foto() -> dict:
    ahora = timezone.now()
    vigentes = est.ultimas_revisiones().exclude(tipo=TrabajoRevision.Tipo.RETIRO)
    trabajos = [
        t
        for t in est.estado_trabajos([r.trabajo_id for r in vigentes])
        if t.activo
        or (
            t.estado == est.TERMINADO
            and t.ultima_actividad
            and ahora - t.ultima_actividad < TERMINADOS_VISIBLES
        )
    ]
    notas: dict = {}
    consulta = Nota.objects.filter(trabajo_id__in=[t.trabajo_id for t in trabajos])
    for nota in consulta.order_by("escrita_en", "registrada_en"):
        notas.setdefault(nota.trabajo_id, []).append(nota)
    return {
        "generada_en": ahora.isoformat(),
        "operarios": [
            {"id": o.operario_id, "nombre": o.nombre}
            for o in Operario.objects.filter(activo=True).order_by("nombre")
        ],
        "maquinas": [
            [m.maquina_id, m.nombre_corto or m.nombre]
            for m in Maquina.objects.order_by("maquina_id")
        ],
        # El operario de prueba viaja en la copia, pero el kiosco de planta lo oculta.
        "operario_prueba": operario_prueba_id(),
        "dias_cerrados": _dias_cerrados(timezone.localdate()),
        "trabajos": [_trabajo(t, notas.get(t.trabajo_id, [])) for t in trabajos],
    }
