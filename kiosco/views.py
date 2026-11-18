"""Pantallas del kiosco. Solo leen y escriben la base local: nunca esperan a Neon."""

from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from planta.models import Evento, Nota
from planta.servicios import ReglaDeNegocioError

from . import local
from .acceso import solo_kiosco
from .models import EventoPendiente, NotaPendiente

TIPOS_NOTA = [(t, Nota.Tipo(t).label) for t in local.TIPOS_KIOSCO]


def _contexto(request, planta, operario_id=None, **extra) -> dict:
    contexto = {
        "planta": planta,
        "inactividad": settings.KIOSCO_INACTIVIDAD_SEGUNDOS,
        "tipos_nota": TIPOS_NOTA,
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


def _operarios(planta) -> list[tuple[int, str]]:
    return sorted(planta.operarios.items(), key=lambda par: par[1].casefold())


@solo_kiosco
def inicio(request):
    """«¿Quién sos?»: se escribe el nombre (sin contraseña) o se elige de la lista."""
    planta = local.cargar_planta()
    if planta is None:
        return render(request, "kiosco/esperando.html", _contexto(request, None))
    contexto = _contexto(request, planta, operarios=_operarios(planta))
    if request.method == "POST":
        nombre = request.POST.get("nombre", "")
        operario_id = planta.buscar_operario(nombre)
        if operario_id is not None:
            return redirect("kiosco:pendientes", operario_id)
        contexto.update(nombre=nombre, error=f"No hay ningún operario llamado «{nombre}».")
        return render(request, "kiosco/inicio.html", contexto, status=404)
    return render(request, "kiosco/inicio.html", contexto)


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
    ejecutor = request.POST.get("operario", "")
    datos = {
        "accion": accion,
        "maquina_id": int(maquina) if maquina.isdigit() else None,
        "observaciones": request.POST.get("observaciones", "")[:500],
        # Quién hizo el trabajo: por defecto, el que está en el kiosco.
        "operario_id": int(ejecutor) if ejecutor.isdigit() else operario_id,
    }
    confirmado = request.POST.get("confirmado") == "1"
    if accion == "pausado" and not confirmado:
        return _confirmar(
            request, planta, operario_id, t, op, datos, f"¿Pausar la operación {op.nro}?"
        )
    try:
        local.registrar(
            planta,
            trabajo_id=t.trabajo_id,
            operacion_id=op.operacion_id,
            confirmado=confirmado,
            cargado_por=operario_id,
            **datos,
        )
    except local.RequiereConfirmacion as aviso:
        return _confirmar(request, planta, operario_id, t, op, datos, str(aviso))
    except ReglaDeNegocioError as error:
        return _pantalla_operacion(request, planta, operario_id, t, op, error=str(error))
    return redirect("kiosco:pendientes", operario_id)


def _pantalla_operacion(request, planta, operario_id, t, op, error=None, status=None):
    contexto = _contexto(
        request,
        planta,
        operario_id,
        t=t,
        op=op,
        error=error,
        quien=op.operario_nombre if op.abierta else None,
        maquinas=sorted(planta.maquinas.items()),
        operarios=_operarios(planta),
        notas=t.notas_de(op.operacion_id),
    )
    return render(
        request, "kiosco/operacion.html", contexto, status=status or (409 if error else 200)
    )


def _confirmar(request, planta, operario_id, t, op, datos, pregunta):
    url = reverse("kiosco:operacion", args=[operario_id, t.trabajo_id, op.operacion_id])
    contexto = _contexto(
        request, planta, operario_id, t=t, op=op, datos=datos, pregunta=pregunta, url=url
    )
    return render(request, "kiosco/confirmar.html", contexto)


@require_POST
@solo_kiosco
def nota(request, operario_id, trabajo_id):
    """Observación, sugerencia, pregunta o respuesta escrita en el kiosco."""
    planta, respuesta = _planta_y_operario(operario_id)
    if respuesta:
        return respuesta
    volver = request.POST.get("volver", "")
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = reverse("kiosco:trabajo", args=[operario_id, trabajo_id])
    try:
        local.escribir_nota(
            planta,
            operario_id=operario_id,
            trabajo_id=trabajo_id,
            texto=request.POST.get("texto", ""),
            tipo=request.POST.get("tipo", Nota.Tipo.OBSERVACION),
            operacion_id=request.POST.get("operacion_id") or None,
            responde_a=request.POST.get("responde_a") or None,
        )
    except ReglaDeNegocioError as error:
        t = planta.trabajo(trabajo_id)
        if t is None:
            return redirect("kiosco:pendientes", operario_id)
        contexto = _contexto(request, planta, operario_id, t=t, error=str(error))
        return render(request, "kiosco/trabajo.html", contexto, status=409)
    return redirect(volver)


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
    sin_enviar = (
        EventoPendiente.objects.filter(enviado_en=None, rechazado_en=None).count()
        + NotaPendiente.objects.filter(enviado_en=None, rechazado_en=None).count()
    )
    rechazados = (
        EventoPendiente.objects.exclude(rechazado_en=None)
        .exclude(tipo=Evento.Tipo.ANULACION)
        .count()
        + NotaPendiente.objects.exclude(rechazado_en=None).count()
    )
    contexto = {"planta": planta, "sin_enviar": sin_enviar, "rechazados": rechazados}
    return render(request, "kiosco/parciales/estado.html", contexto)
