"""Parte A: la oficina prepara la lista de pendientes y controla la jornada."""

from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from planta.models import CotizacionSinPedido, Evento, PedidoPendiente, TrabajoRevision
from planta.servicios import ReglaDeNegocioError
from planta.servicios import estado as est
from planta.servicios.jornada import (
    anular_evento,
    cerrar_dia,
    eventos_del_dia,
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
    trabajo_activo_para,
)

from .forms import MotivoForm, OperacionFormSet, TrabajoForm, opciones_maquina
from .permisos import requiere_oficina, requiere_supervisor

LIMITE_LISTADO = 200

FILTROS_ESTADO = {
    "activos": "Activos",
    est.EN_COLA: "En cola",
    est.TRABAJO_EN_PROCESO: "En proceso",
    est.TERMINADO: "Terminados en planta",
    est.RETIRADO: "Retirados",
    "todos": "Todos",
}


def _usuario(request) -> str:
    return request.user.get_username()


def _fecha_param(request, nombre="fecha") -> date:
    try:
        return date.fromisoformat(request.GET.get(nombre, ""))
    except ValueError:
        return timezone.localdate()


def _volver_seguro(request, destino: str | None, por_defecto: str) -> str:
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return por_defecto


# --- lista de pendientes -----------------------------------------------------
@requiere_oficina
def pendientes(request):
    filtro = request.GET.get("estado", "activos")
    if filtro not in FILTROS_ESTADO:
        filtro = "activos"
    texto = request.GET.get("q", "").strip()

    trabajos = est.estado_trabajos()
    if filtro == "activos":
        trabajos = [t for t in trabajos if t.activo]
    elif filtro != "todos":
        trabajos = [t for t in trabajos if t.estado == filtro]
    if texto:
        trabajos = [t for t in trabajos if texto.lower() in _texto_busqueda(t)]

    contexto = {"trabajos": trabajos, "filtro": filtro, "filtros": FILTROS_ESTADO, "q": texto}
    if request.htmx:
        return render(request, "oficina/parciales/tabla_pendientes.html", contexto)
    return render(request, "oficina/pendientes.html", contexto)


def _texto_busqueda(t: est.EstadoTrabajo) -> str:
    r = t.revision
    partes = [r.plano, r.plano_descripcion, r.cliente_nombre, r.pedido_id, r.cotizacion_id]
    return " ".join(str(p) for p in partes if p).lower()


# --- orígenes (FoxPro) -------------------------------------------------------
def _listado_origen(request, *, modelo, campos_texto, campo_numero, tabla, titulo):
    texto = request.GET.get("q", "").strip()
    qs = modelo.objects.all()
    if texto:
        filtro = Q()
        for campo in campos_texto:
            filtro |= Q(**{f"{campo}__icontains": texto})
        if texto.isdigit():
            filtro |= Q(**{campo_numero: int(texto)})
        qs = qs.filter(filtro)
    contexto = {
        "filas": list(qs[:LIMITE_LISTADO]),
        "q": texto,
        "titulo": titulo,
        "con_trabajo": est.refs_con_trabajo_activo(),
        "limite": LIMITE_LISTADO,
        "tabla": f"oficina/parciales/{tabla}",
    }
    if request.htmx:
        return render(request, contexto["tabla"], contexto)
    return render(request, "oficina/origen.html", contexto)


@requiere_oficina
def pedidos(request):
    return _listado_origen(
        request,
        modelo=PedidoPendiente,
        campos_texto=["plano", "cliente", "orden_compra", "plano_descripcion"],
        campo_numero="pedido_id",
        tabla="tabla_pedidos.html",
        titulo="Pedidos con pendiente",
    )


@requiere_oficina
def cotizaciones(request):
    return _listado_origen(
        request,
        modelo=CotizacionSinPedido,
        campos_texto=["plano", "cliente", "plano_descripcion"],
        campo_numero="cotizacion_id",
        tabla="tabla_cotizaciones.html",
        titulo="Cotizaciones sin pedido",
    )


# --- preparar trabajo (alta y revisión) --------------------------------------
def _datos_desde_origen(origen: str, ref: str | None) -> tuple[DatosTrabajo, dict]:
    """Datos iniciales según el renglón de FoxPro (se vuelven a leer en cada POST)."""
    if origen == TrabajoRevision.Origen.PEDIDO:
        fila = PedidoPendiente.objects.filter(pk=ref).first()
        if fila is None:
            raise Http404("El renglón de pedido ya no está pendiente.")
        datos = DatosTrabajo(
            plano=fila.plano,
            origen=origen,
            origen_ref=fila.pk,
            pedido_id=fila.pedido_id,
            plano_descripcion=fila.plano_descripcion,
            cliente_id=fila.cliente_id,
            cliente_nombre=fila.cliente,
            cantidad=fila.cantidad_pendiente,
        )
        return datos, {"pedido": fila}
    if origen == TrabajoRevision.Origen.COTIZACION:
        fila = CotizacionSinPedido.objects.filter(pk=ref).first()
        if fila is None:
            raise Http404("La cotización ya no está disponible.")
        datos = DatosTrabajo(
            plano=fila.plano,
            origen=origen,
            origen_ref=fila.pk,
            cotizacion_id=fila.cotizacion_id,
            plano_descripcion=fila.plano_descripcion,
            cliente_id=fila.cliente_id,
            cliente_nombre=fila.cliente,
            cantidad=fila.cantidad,
        )
        return datos, {"cotizacion": fila}
    if origen == TrabajoRevision.Origen.MANUAL:
        return DatosTrabajo(plano=""), {}
    raise Http404("Origen desconocido.")


def _datos_desde_revision(r: TrabajoRevision) -> DatosTrabajo:
    return DatosTrabajo(
        plano=r.plano,
        origen=r.origen,
        origen_ref=r.origen_ref,
        pedido_id=r.pedido_id,
        cotizacion_id=r.cotizacion_id,
        plano_descripcion=r.plano_descripcion,
        cliente_id=r.cliente_id,
        cliente_nombre=r.cliente_nombre,
        cantidad=r.cantidad,
        urgencia=r.urgencia,
        fecha_entrega_estimada=r.fecha_entrega_estimada,
        observaciones=r.observaciones,
    )


CAMPOS_FORM = [
    "plano",
    "plano_descripcion",
    "pedido_id",
    "cliente_nombre",
    "cantidad",
    "urgencia",
    "fecha_entrega_estimada",
    "observaciones",
]


def _inicial_operaciones(operaciones: list[DatosOperacion]) -> list[dict]:
    return [
        {
            "maquina_id": op.maquina_id,
            "descripcion": op.descripcion,
            "observaciones": op.observaciones,
            "operacion_id": op.operacion_id,
        }
        for op in operaciones
    ]


def _formularios(request, datos: DatosTrabajo, operaciones: list[DatosOperacion]):
    """Formulario del trabajo + formset de operaciones (con "Agregar operación")."""
    ids_maquina = [op.maquina_id for op in operaciones]
    inicial = {c: getattr(datos, c) for c in CAMPOS_FORM}
    if request.method != "POST":
        form = TrabajoForm(initial=inicial)
        formset = OperacionFormSet(
            initial=_inicial_operaciones(operaciones),
            prefix="ops",
            form_kwargs={"opciones": opciones_maquina(ids_maquina)},
        )
    else:
        post = request.POST.copy()
        if post.get("accion") == "agregar":
            post["ops-TOTAL_FORMS"] = str(int(post.get("ops-TOTAL_FORMS", 0)) + 1)
        ids_maquina += [
            int(v) for k, v in post.items() if k.endswith("-maquina_id") and v.isdigit()
        ]
        form = TrabajoForm(post, initial=inicial)
        formset = OperacionFormSet(
            post, prefix="ops", form_kwargs={"opciones": opciones_maquina(ids_maquina)}
        )
    # El número de pedido de un renglón de FoxPro no se edita: sale del origen.
    if datos.origen == TrabajoRevision.Origen.PEDIDO:
        form.fields["pedido_id"].disabled = True
        form.fields["pedido_id"].help_text = ""
    return form, formset


def _tiene_contenido(form) -> bool:
    d = form.cleaned_data
    return any(d.get(c) for c in ("maquina_id", "descripcion", "observaciones", "operacion_id"))


def _operaciones_validas(formset) -> list[DatosOperacion]:
    return [
        DatosOperacion(
            maquina_id=f.cleaned_data.get("maquina_id"),
            descripcion=f.cleaned_data.get("descripcion"),
            observaciones=f.cleaned_data.get("observaciones"),
            operacion_id=f.cleaned_data.get("operacion_id"),
        )
        for f in formset.forms
        if f.cleaned_data and not f.cleaned_data.get("DELETE") and _tiene_contenido(f)
    ]


def _aplicar_form(datos: DatosTrabajo, form) -> DatosTrabajo:
    for campo in CAMPOS_FORM:
        setattr(datos, campo, form.cleaned_data.get(campo))
    return datos


def _guardar_si_corresponde(request, form, formset, guardar):
    """Valida y llama a `guardar`. Devuelve la revisión grabada o None."""
    if request.method != "POST" or request.POST.get("accion") != "guardar":
        return None
    if not (form.is_valid() and formset.is_valid()):
        return None
    try:
        return guardar(_operaciones_validas(formset))
    except ReglaDeNegocioError as error:
        form.add_error(None, str(error))
        return None


def _render_preparar(request, contexto):
    if request.htmx and request.POST.get("accion") == "agregar":
        return render(request, "oficina/parciales/form_trabajo.html", contexto)
    return render(request, "oficina/preparar.html", contexto)


@requiere_oficina
def trabajo_nuevo(request):
    origen = request.GET.get("origen", TrabajoRevision.Origen.MANUAL)
    datos, extra = _datos_desde_origen(origen, request.GET.get("ref"))

    if datos.origen_ref and (existente := trabajo_activo_para(datos.origen_ref)):
        messages.info(request, "Ese renglón ya está en la lista de pendientes.")
        return redirect("oficina:trabajo", trabajo_id=existente.trabajo_id)

    sugerida = ruta_sugerida(datos.plano) if datos.plano else []
    form, formset = _formularios(request, datos, sugerida or [DatosOperacion()])

    revision = _guardar_si_corresponde(
        request,
        form,
        formset,
        lambda ops: crear_trabajo(_aplicar_form(datos, form), ops, _usuario(request)),
    )
    if revision:
        messages.success(request, f"Trabajo {revision.plano} agregado a pendientes.")
        return redirect("oficina:trabajo", trabajo_id=revision.trabajo_id)

    return _render_preparar(
        request,
        {
            "form": form,
            "formset": formset,
            "datos": datos,
            "titulo": "Preparar trabajo",
            "accion_url": f"{reverse('oficina:trabajo_nuevo')}?{request.GET.urlencode()}",
            "ruta_sugerida": bool(sugerida),
            **extra,
        },
    )


def _estado_o_404(trabajo_id) -> est.EstadoTrabajo:
    estado = est.estado_trabajo(trabajo_id)
    if estado is None:
        raise Http404("El trabajo no existe.")
    return estado


@requiere_oficina
def trabajo_detalle(request, trabajo_id):
    estado = _estado_o_404(trabajo_id)
    eventos = list(
        Evento.objects.filter(trabajo_id=trabajo_id)
        .select_related("operario", "anula_evento")
        .order_by("-ocurrido_en", "-registrado_en")
    )
    return render(
        request,
        "oficina/trabajo.html",
        {
            "t": estado,
            "revisiones": TrabajoRevision.objects.filter(trabajo_id=trabajo_id).order_by(
                "-revision"
            ),
            "eventos": eventos,
            "anulados": {e.anula_evento_id for e in eventos if e.anula_evento_id},
            "operaciones": {o.operacion.operacion_id: o for o in estado.operaciones},
        },
    )


@requiere_oficina
def trabajo_revisar(request, trabajo_id):
    estado = _estado_o_404(trabajo_id)
    actual = estado.revision
    if actual.tipo == TrabajoRevision.Tipo.RETIRO:
        messages.error(request, "El trabajo está retirado: no se puede revisar.")
        return redirect("oficina:trabajo", trabajo_id=trabajo_id)

    datos = _datos_desde_revision(actual)
    ops = [
        DatosOperacion(
            o.operacion.maquina_id,
            o.operacion.descripcion,
            o.operacion.observaciones,
            o.operacion.operacion_id,
        )
        for o in estado.operaciones
    ]
    form, formset = _formularios(request, datos, ops)

    def guardar(operaciones):
        try:
            base = int(request.POST.get("revision_base", actual.revision))
        except ValueError:
            base = actual.revision
        return revisar_trabajo(
            trabajo_id,
            _aplicar_form(datos, form),
            operaciones,
            _usuario(request),
            revision_base=base,
        )

    revision = _guardar_si_corresponde(request, form, formset, guardar)
    if revision:
        messages.success(request, f"Revisión {revision.revision} guardada.")
        return redirect("oficina:trabajo", trabajo_id=trabajo_id)

    return _render_preparar(
        request,
        {
            "form": form,
            "formset": formset,
            "datos": datos,
            "titulo": f"Revisar trabajo {actual.plano}",
            "accion_url": reverse("oficina:trabajo_revisar", args=[trabajo_id]),
            "revision_base": actual.revision,
            "t": estado,
            "con_registros": {
                str(o.operacion.operacion_id) for o in estado.operaciones if o.ultimo_evento
            },
        },
    )


@requiere_oficina
@require_POST
def trabajo_retirar(request, trabajo_id):
    form = MotivoForm(request.POST)
    motivo = form.cleaned_data.get("motivo") if form.is_valid() else None
    try:
        retirar_trabajo(trabajo_id, _usuario(request), motivo)
    except ReglaDeNegocioError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Trabajo retirado de la lista de pendientes.")
    return redirect("oficina:trabajo", trabajo_id=trabajo_id)


# --- registros del día y anulaciones -----------------------------------------
@requiere_oficina
def registros(request):
    fecha = _fecha_param(request)
    eventos = list(eventos_del_dia(fecha))
    revisiones = {r.trabajo_id: r for r in est.ultimas_revisiones({e.trabajo_id for e in eventos})}
    return render(
        request,
        "oficina/registros.html",
        {
            "fecha": fecha,
            "eventos": eventos,
            "resumen": resumen_dia(fecha),
            "revisiones": revisiones,
        },
    )


@requiere_oficina
@require_POST
def evento_anular(request, evento_id):
    form = MotivoForm(request.POST)
    motivo = form.cleaned_data.get("motivo") if form.is_valid() else None
    try:
        anular_evento(evento_id, _usuario(request), motivo)
    except ReglaDeNegocioError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Registro anulado.")
    return redirect(
        _volver_seguro(request, request.POST.get("volver"), reverse("oficina:registros"))
    )


# --- cierre del día (supervisor) ---------------------------------------------
@requiere_supervisor
def cierre(request):
    if request.method == "POST":
        try:
            fecha = date.fromisoformat(request.POST.get("fecha", ""))
        except ValueError:
            messages.error(request, "Fecha inválida.")
            return redirect("oficina:cierre")
        observaciones = request.POST.get("observaciones")
        try:
            if request.POST.get("accion") == "reabrir":
                reabrir_dia(fecha, _usuario(request), observaciones)
                messages.success(request, f"Día {fecha:%d/%m/%Y} reabierto.")
            else:
                cerrar_dia(fecha, _usuario(request), observaciones)
                messages.success(request, f"Día {fecha:%d/%m/%Y} cerrado.")
        except ReglaDeNegocioError as error:
            messages.error(request, str(error))
        return redirect(f"{reverse('oficina:cierre')}?fecha={fecha.isoformat()}")

    fecha = _fecha_param(request)
    return render(
        request,
        "oficina/cierre.html",
        {"fecha": fecha, "resumen": resumen_dia(fecha), "hoy": timezone.localdate()},
    )
