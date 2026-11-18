"""Notas (observaciones, sugerencias, preguntas y respuestas) y avisos a oficina."""

import uuid

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.db import connection

from cuentas.roles import CONTABILIDAD, OFICINA_TECNICA, OPERARIO, STAFF, asignar_rol
from planta.models import Nota
from planta.servicios import ReglaDeNegocioError, avisos
from planta.servicios.notas import crear_nota, hilos_de_trabajo, preguntas_abiertas
from planta.servicios.trabajos import DatosOperacion, DatosTrabajo, crear_trabajo

pytestmark = pytest.mark.django_db


@pytest.fixture
def revision():
    return crear_trabajo(DatosTrabajo(plano="N-1"), [DatosOperacion(descripcion="Tornear")], "ofi")


def _nota(revision, **kw):
    datos = {
        "trabajo_id": revision.trabajo_id,
        "tipo": Nota.Tipo.OBSERVACION,
        "texto": "Hay rebabas",
        "autor": "Ana",
        **kw,
    }
    return crear_nota(**datos)


def test_nota_guarda_autor_hora_y_dispositivo(revision):
    op = revision.operaciones.get()
    nota = _nota(revision, operacion_id=op.operacion_id)
    assert nota.autor == "Ana" and nota.escrita_en is not None
    assert nota.dispositivo == "tests" and nota.operacion_id == op.operacion_id


def test_validaciones(revision):
    with pytest.raises(ReglaDeNegocioError, match="vacía"):
        _nota(revision, texto="   ")
    with pytest.raises(ReglaDeNegocioError, match="no es de este trabajo"):
        _nota(revision, operacion_id=uuid.uuid4())
    with pytest.raises(ReglaDeNegocioError, match="no existe"):
        _nota(revision, tipo=Nota.Tipo.RESPUESTA, responde_a_id=uuid.uuid4())
    with pytest.raises(ReglaDeNegocioError, match="Solo una respuesta"):
        pregunta = _nota(revision, tipo=Nota.Tipo.PREGUNTA)
        _nota(revision, responde_a_id=pregunta.nota_id)


def test_hilos_y_preguntas_abiertas(revision):
    pregunta = _nota(revision, tipo=Nota.Tipo.PREGUNTA, texto="¿Qué tolerancia?")
    _nota(revision, texto="Otra cosa")
    assert preguntas_abiertas([revision.trabajo_id]) == {revision.trabajo_id: 1}
    _nota(
        revision,
        tipo=Nota.Tipo.RESPUESTA,
        responde_a_id=pregunta.nota_id,
        texto="±0,02",
        autor="Oficina",
    )
    hilos = hilos_de_trabajo(revision.trabajo_id)
    assert [h.nota.texto for h in hilos] == ["¿Qué tolerancia?", "Otra cosa"]
    assert [r.texto for r in hilos[0].respuestas] == ["±0,02"]
    assert preguntas_abiertas([revision.trabajo_id]) == {}


def test_misma_nota_dos_veces_no_se_duplica(revision):
    nota_id = uuid.uuid4()
    _nota(revision, nota_id=nota_id)
    _nota(revision, nota_id=nota_id)
    assert Nota.objects.filter(nota_id=nota_id).count() == 1


def test_notas_solo_se_agregan(revision):
    nota = _nota(revision)
    with pytest.raises(Exception, match="solo se permite agregar"), connection.cursor() as cur:
        cur.execute("UPDATE planta.nota SET texto = 'otro' WHERE nota_id = %s", [nota.nota_id])


def test_aviso_a_oficina_y_staff_por_mail(revision, settings, django_capture_on_commit_callbacks):
    settings.AVISOS_CANALES = ["planta.servicios.avisos.CanalCorreo"]
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    for nombre, rol, correo in [
        ("ofi", OFICINA_TECNICA, "ofi@ejemplo.com"),
        ("jefa", STAFF, "jefa@ejemplo.com"),
        ("conta", CONTABILIDAD, "conta@ejemplo.com"),
        ("juan", OPERARIO, "juan@ejemplo.com"),
    ]:
        usuario = User.objects.create_user(nombre, email=correo, password="clave-larga-123")
        asignar_rol(usuario, rol)
    with django_capture_on_commit_callbacks(execute=True):
        _nota(revision, tipo=Nota.Tipo.PREGUNTA, texto="¿Qué tolerancia?", autor="Juan")
    assert len(mail.outbox) == 1
    enviado = mail.outbox[0]
    assert set(enviado.to) == {"ofi@ejemplo.com", "jefa@ejemplo.com"}
    assert "Pregunta de Juan en N-1" in enviado.subject and "tolerancia" in enviado.body


def test_un_canal_que_falla_no_rompe_nada(revision, settings, django_capture_on_commit_callbacks):
    settings.AVISOS_CANALES = ["planta.tests.test_notas.CanalRoto"]
    with django_capture_on_commit_callbacks(execute=True):
        _nota(revision)
    assert Nota.objects.count() == 1


def test_quien_escribe_desde_oficina_no_se_avisa_a_si_mismo():
    usuario = User.objects.create_user("ofi", password="clave-larga-123")
    asignar_rol(usuario, OFICINA_TECNICA)
    assert usuario not in avisos.destinatarios_oficina(excluir_usuario_id=usuario.pk)
    assert usuario in avisos.destinatarios_oficina()


class CanalRoto:
    def enviar(self, aviso, destinatarios):
        raise RuntimeError("sin servicio")
