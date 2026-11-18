"""Ingreso por nombre: si el usuario tiene contraseña, recién ahí se pide.

Los usuarios sin contraseña (operarios) no entran por acá: registran desde el
kiosco de planta, que no se publica en internet (ver ADR 0007).
"""

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from .nombres import buscar_usuario, normalizar

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 15 * 60
PLANTILLA = "cuentas/ingreso.html"


def _clave_intentos(request, nombre: str) -> str:
    return f"ingreso:{request.META.get('REMOTE_ADDR', '')}:{normalizar(nombre)}"


def _bloqueado(request, nombre: str) -> bool:
    return cache.get(_clave_intentos(request, nombre), 0) >= MAX_INTENTOS


def _fallo(request, nombre: str) -> None:
    clave = _clave_intentos(request, nombre)
    cache.set(clave, cache.get(clave, 0) + 1, BLOQUEO_SEGUNDOS)


def _destino(request) -> str:
    siguiente = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return siguiente
    return settings.LOGIN_REDIRECT_URL


@sensitive_post_parameters("contrasena")
@csrf_protect
@never_cache
def ingresar(request):
    contexto = {"next": request.POST.get("next") or request.GET.get("next", "")}
    if request.method != "POST":
        return render(request, PLANTILLA, contexto)

    nombre = request.POST.get("nombre", "").strip()
    contexto["nombre"] = nombre
    if _bloqueado(request, nombre):
        contexto["error"] = "Demasiados intentos. Probá de nuevo en unos minutos."
        return render(request, PLANTILLA, contexto, status=429)

    usuario = buscar_usuario(nombre)
    if usuario is None:
        _fallo(request, nombre)
        contexto["error"] = "No encontramos ese nombre."
        return render(request, PLANTILLA, contexto, status=401)
    if not usuario.has_usable_password():
        contexto["error"] = (
            "Tu usuario no tiene contraseña: los avances se registran desde el kiosco de planta."
        )
        return render(request, PLANTILLA, contexto, status=403)

    contexto["pedir_contrasena"] = True
    contexto["nombre"] = usuario.username
    if "contrasena" not in request.POST:
        return render(request, PLANTILLA, contexto)

    autenticado = authenticate(
        request, username=usuario.username, password=request.POST.get("contrasena", "")
    )
    if autenticado is None:
        _fallo(request, nombre)
        contexto["error"] = "Contraseña incorrecta."
        return render(request, PLANTILLA, contexto, status=401)
    cache.delete(_clave_intentos(request, nombre))
    login(request, autenticado)
    return redirect(_destino(request))
