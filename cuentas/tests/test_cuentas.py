"""Roles, operario automático, ingreso por nombre y admin de usuarios."""

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.db import IntegrityError
from django.urls import reverse

from cuentas.nombres import buscar_usuario
from cuentas.roles import (
    CONTABILIDAD,
    OFICINA_TECNICA,
    OPERARIO,
    ROLES,
    STAFF,
    asignar_rol,
    rol_de,
)
from planta.models import Operario

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sin_intentos_previos():
    cache.clear()


def _usuario(nombre, rol, clave="clave-de-prueba-larga"):
    usuario = User.objects.create_user(nombre, password=clave)
    if clave is None:
        usuario.set_unusable_password()
        usuario.save()
    asignar_rol(usuario, rol)
    return usuario


# --- roles -------------------------------------------------------------------------
def test_cada_rol_tiene_su_juego_de_permisos():
    def permisos(rol):
        return set(Group.objects.get(name=rol).permissions.values_list("codename", flat=True))

    assert permisos(OPERARIO) == {"registrar_avances", "escribir_notas"}
    assert permisos(CONTABILIDAD) == {"ver_trabajos"}
    assert permisos(OFICINA_TECNICA) == {
        "ver_trabajos",
        "preparar_trabajos",
        "escribir_notas",
        "anular_registros",
        "cerrar_dia",
    }
    assert {"change_user", "ver_trabajos", "cerrar_dia"} <= permisos(STAFF)


def test_asignar_rol_deja_uno_solo_y_marca_staff():
    usuario = _usuario("rita", OFICINA_TECNICA)
    asignar_rol(usuario, STAFF)
    usuario.refresh_from_db()
    assert rol_de(usuario) == STAFF and usuario.is_staff
    assert list(usuario.groups.values_list("name", flat=True)) == [STAFF]
    asignar_rol(usuario, CONTABILIDAD)
    usuario.refresh_from_db()
    assert rol_de(usuario) == CONTABILIDAD and not usuario.is_staff


def test_nombre_unico_sin_mayusculas_en_la_base():
    User.objects.create_user("Fabian")
    with pytest.raises(IntegrityError):
        User.objects.create_user("fabian")


# --- operario automático -------------------------------------------------------------
def test_usuario_operario_aparece_como_operario():
    usuario = _usuario("Juan", OPERARIO, clave=None)
    operario = Operario.objects.get(usuario_id=usuario.pk)
    assert operario.nombre == "Juan" and operario.activo


def test_vincula_el_operario_existente_por_nombre():
    viejo = Operario.objects.create(nombre="Sebastián")
    usuario = _usuario("sebastian", OPERARIO, clave=None)
    viejo.refresh_from_db()
    assert viejo.usuario_id == usuario.pk and viejo.nombre == "sebastian"
    assert Operario.objects.count() == 1


def test_cambiar_de_rol_o_desactivar_saca_al_operario():
    usuario = _usuario("Lia", OPERARIO, clave=None)
    asignar_rol(usuario, CONTABILIDAD)
    assert not Operario.objects.get(usuario_id=usuario.pk).activo
    asignar_rol(usuario, OPERARIO)
    assert Operario.objects.get(usuario_id=usuario.pk).activo
    usuario.is_active = False
    usuario.save()
    assert not Operario.objects.get(usuario_id=usuario.pk).activo


def test_renombrar_usuario_renombra_al_operario():
    usuario = _usuario("Tito", OPERARIO, clave=None)
    usuario.username = "Tito.Gomez"
    usuario.save()
    assert Operario.objects.get(usuario_id=usuario.pk).nombre == "Tito.Gomez"


# --- ingreso por nombre ---------------------------------------------------------------
def test_buscar_usuario_ignora_mayusculas_y_tildes():
    usuario = User.objects.create_user("Martín")
    assert buscar_usuario("  MARTIN ") == usuario
    assert buscar_usuario("martín") == usuario
    assert buscar_usuario("otro") is None


def test_ingreso_con_contrasena_en_dos_pasos(client):
    _usuario("Ana", OFICINA_TECNICA)
    paso1 = client.post(reverse("login"), {"nombre": "ana"})
    assert paso1.status_code == 200
    html = paso1.content.decode()
    assert 'name="contrasena"' in html and "Hola, <strong>Ana</strong>" in html
    paso2 = client.post(reverse("login"), {"nombre": "Ana", "contrasena": "clave-de-prueba-larga"})
    assert paso2.status_code == 302 and paso2.url == reverse("oficina:pendientes")


def test_ingreso_respeta_next_seguro(client):
    _usuario("Ana", OFICINA_TECNICA)
    destino = reverse("oficina:registros")
    respuesta = client.post(
        reverse("login"),
        {"nombre": "Ana", "contrasena": "clave-de-prueba-larga", "next": destino},
    )
    assert respuesta.url == destino
    client.logout()
    ajeno = client.post(
        reverse("login"),
        {"nombre": "Ana", "contrasena": "clave-de-prueba-larga", "next": "https://malo.com/"},
    )
    assert ajeno.url == reverse("oficina:pendientes")


def test_contrasena_incorrecta_y_bloqueo(client):
    _usuario("Ana", OFICINA_TECNICA)
    for _ in range(5):
        mal = client.post(reverse("login"), {"nombre": "Ana", "contrasena": "no"})
        assert mal.status_code == 401
    bloqueado = client.post(
        reverse("login"), {"nombre": "Ana", "contrasena": "clave-de-prueba-larga"}
    )
    assert bloqueado.status_code == 429


def test_operario_sin_contrasena_no_entra_por_la_web(client):
    _usuario("Juan", OPERARIO, clave=None)
    respuesta = client.post(reverse("login"), {"nombre": "juan"})
    assert respuesta.status_code == 403
    assert "kiosco de planta" in respuesta.content.decode()
    assert "_auth_user_id" not in client.session


def test_nombre_inexistente(client):
    respuesta = client.post(reverse("login"), {"nombre": "nadie"})
    assert respuesta.status_code == 401


def test_admin_redirige_al_ingreso_por_nombre(client):
    respuesta = client.get(reverse("admin:login"))
    assert respuesta.status_code == 302 and respuesta.url.startswith(reverse("login"))


# --- admin de usuarios -----------------------------------------------------------------
@pytest.fixture
def staff(client):
    usuario = _usuario("jefa", STAFF)
    client.force_login(usuario)
    return client


def _alta(client, **datos):
    return client.post(reverse("admin:auth_user_add"), datos)


def test_alta_de_operario_sin_contrasena(staff):
    respuesta = _alta(staff, username="Pedro", rol=OPERARIO, contrasena1="", contrasena2="")
    assert respuesta.status_code == 302, respuesta.content.decode()[:2000]
    pedro = User.objects.get(username="Pedro")
    assert not pedro.has_usable_password() and rol_de(pedro) == OPERARIO
    assert Operario.objects.get(usuario_id=pedro.pk).activo


def test_rol_con_contrasena_la_exige(staff):
    respuesta = _alta(staff, username="Conta", rol=CONTABILIDAD, contrasena1="", contrasena2="")
    assert respuesta.status_code == 200
    assert "necesita contraseña" in respuesta.content.decode()
    clave = "otra-clave-bien-larga-1"
    ok = _alta(staff, username="Conta", rol=CONTABILIDAD, contrasena1=clave, contrasena2=clave)
    assert ok.status_code == 302
    conta = User.objects.get(username="Conta")
    assert conta.check_password(clave) and rol_de(conta) == CONTABILIDAD


def test_alta_rechaza_nombre_repetido_sin_mayusculas_ni_tildes(staff):
    User.objects.create_user("Martín")
    respuesta = _alta(staff, username="martin", rol=OPERARIO, contrasena1="", contrasena2="")
    assert respuesta.status_code == 200
    assert "Ya hay un usuario con ese nombre" in respuesta.content.decode()


def test_staff_no_ve_ni_edita_superusuarios(staff):
    sudo = User.objects.create_superuser("sudo", password="clave-de-prueba-larga")
    lista = staff.get(reverse("admin:auth_user_changelist")).content.decode()
    assert "sudo" not in lista
    assert staff.get(reverse("admin:auth_user_change", args=[sudo.pk])).status_code in (302, 403)
    assert staff.post(reverse("admin:auth_user_delete", args=[sudo.pk])).status_code in (302, 403)
    assert User.objects.filter(username="sudo", is_superuser=True).exists()


def test_el_rol_se_elige_de_una_lista_sin_permisos_sueltos(staff):
    html = staff.get(reverse("admin:auth_user_add")).content.decode()
    for rol in ROLES.values():
        assert rol.etiqueta in html
    assert "user_permissions" not in html and "is_superuser" not in html


def test_superusuario_edita_su_ficha_sin_rol(client):
    sudo = User.objects.create_superuser("sudo", password="clave-de-prueba-larga")
    client.force_login(sudo)
    url = reverse("admin:auth_user_change", args=[sudo.pk])
    assert client.get(url).status_code == 200
    respuesta = client.post(
        url,
        {"username": "sudo", "is_active": "on", "first_name": "Seba", "last_name": "", "email": ""},
    )
    assert respuesta.status_code == 302
    sudo.refresh_from_db()
    assert sudo.first_name == "Seba" and sudo.is_superuser
