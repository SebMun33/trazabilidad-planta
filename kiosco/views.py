"""Pantallas del kiosco. Solo leen y escriben la base local: nunca esperan a Neon."""

from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from planta.models import Evento
from planta.servicios import ReglaDeNegocioError

from . import local
from .acceso import solo_kiosco
from .models import EventoPendiente


def _contexto(request, planta, operario_id=None, **extra) -> dict:
    contexto = {
        "planta": planta,
        "inactividad": settings.KIOSCO_INACTIVIDAD_SEGUNDOS,
        **extra,
    }
    if operario_id is not None:
        contexto["operario_id"] = operario_id
        contexto["operario"] = planta.operarios.get(operario_id)
        deshacible = local.ultimo_deshacible(operario_id)
        if deshacible:
            hasta = deshacible.creado_en + timedelta(seconds=settings.KIOSCO_DESHACER_SEGUNDOS)
            contexto["deshacible"] = deshacible
            contexto["deshacible_texto"] = local.describir(deshacible, planta)
            contexto["deshacible_hasta_ms"] = int(hasta.timestamp() * 1000)
    return contexto


def _planta_y_operario(operario_id):
    """(planta, respuesta): si falta algo, la respuesta redirige o informa."""
    planta = local.cargar_planta()
    if planta is None:
        return None, redirect("kiosco:inicio")
    if operario_id not in planta.operarios:
        return None, redirect("kiosco:inicio")
    return planta, None


@solo_kiosco
def inicio(request):
    planta = local.cargar_planta()
    if planta is None:
        return render(request, "kiosco/esperando.html", _contexto(request, None))
    operarios = sorted(planta.operarios.items(), key=lambda par: par[1])
    return render(request, "kiosco/inicio.html", _contexto(request, planta, operarios=operarios))


@solo_kiosco
def pendientes(request, operario_id):
    planta, respuesta = _planta_y_operario(operario_id)
    if respuesta:
        return respuesta
    return render(
        request,
        "kiosco/pendientes.html",
        _contexto(
            request,
            planta,
            operario_id,
            trabajos=planta.activos,
            mis_abiertas=planta.abiertas_de(operario_id),
            hoy_cerrado=planta.dia_cerrado(timezone.localdate()),
        ),
    )


@solo_kiosco
def trabajo(request, operario_id, trabajo_id):
    planta, respuesta = _planta_y_operario(operario_id)
    if respuesta:
        return respuesta
    t = planta.trabajo(trabajo_id)
    if t is None or not t.activo:
        return redirect("kiosco:pendientes", operario_id)
    return render(request, "kiosco/trabajo.html", _contexto(request, planta, operario_id, t=t))


@solo_kiosco
def operacion(request, operario_id, trabajo_id, operacion_id):
    planta, respuesta = _planta_y_operario(operario_id)
    if respuesta:
        return respuesta
    t = planta.trabajo(trabajo_id)
    op = t.operacion(operacion_id) if t and t.activo else None
    if op is None:
        return redirect("kiosco:pendientes", operario_id)

    if request.method != "POST":
        return _pantalla_operacion(request, planta, operario_id, t, op)

    accion = request.POST.get("accion", "")
    maquina = request.POST.get("maquina_id", "")
    datos = {
        "accion": accion,
        "maquina_id": int(maquina) if maquina.isdigit() else None,
        "observaciones": request.POST.get("observaciones", "")[:500],
    }
    confirmado = request.POST.get("confirmado") == "1"
    if accion == "pausado" and not confirmado:
        return _confirmar(
            request, planta, operario_id, t, op, datos, f"¿Pausar la operación {op.nro}?"
        )
    try:
        local.registrar(
            planta,
            operario_id=operario_id,
            trabajo_id=t.trabajo_id,
            operacion_id=op.operacion_id,
            confirmado=confirmado,
            **datos,
        )
    except local.RequiereConfirmacion as aviso:
        return _confirmar(request, planta, operario_id, t, op, datos, str(aviso))
    except ReglaDeNegocioError as error:
        return _pantalla_operacion(request, planta, operario_id, t, op, error=str(error))
    return redirect("kiosco:pendientes", operario_id)


def _pantalla_operacion(request, planta, operario_id, t, op, error=None):
    contexto = _contexto(
        request,
        planta,
        operario_id,
        t=t,
        op=op,
        error=error,
        quien=planta.operarios.get(op.operario_id) if op.abierta else None,
        maquinas=sorted(planta.maquinas.items()),
    )
    return render(request, "kiosco/operacion.html", contexto, status=409 if error else 200)


def _confirmar(request, planta, operario_id, t, op, datos, pregunta):
    url = reverse("kiosco:operacion", args=[operario_id, t.trabajo_id, op.operacion_id])
    contexto = _contexto(
        request, planta, operario_id, t=t, op=op, datos=datos, pregunta=pregunta, url=url
    )
    return render(request, "kiosco/confirmar.html", contexto)


@require_POST
@solo_kiosco
def deshacer(request, operario_id, evento_id):
    planta, respuesta = _planta_y_operario(operario_id)
    if respuesta:
        return respuesta
    try:
        local.deshacer(planta, operario_id=operario_id, evento_id=evento_id)
    except ReglaDeNegocioError as error:
        return render(
            request,
            "kiosco/pendientes.html",
            _contexto(
                request,
                planta,
                operario_id,
                trabajos=planta.activos,
                mis_abiertas=planta.abiertas_de(operario_id),
                error=str(error),
            ),
            status=409,
        )
    return redirect("kiosco:pendientes", operario_id)


@solo_kiosco
def estado(request):
    """Indicador de la barra: cola sin enviar, rechazados y antigüedad de la copia."""
    planta = local.cargar_planta()
    cola = EventoPendiente.objects.filter(enviado_en=None, rechazado_en=None)
    contexto = {
        "planta": planta,
        "sin_enviar": cola.count(),
        "rechazados": EventoPendiente.objects.exclude(rechazado_en=None)
        .exclude(tipo=Evento.Tipo.ANULACION)
        .count(),
    }
    return render(request, "kiosco/parciales/estado.html", contexto)
