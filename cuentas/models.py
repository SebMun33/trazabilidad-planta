"""Permisos de la app, agrupados por categoría.

No hay tablas propias: el modelo existe solo para declarar los permisos. Cada
rol (grupo) recibe un juego fijo de estos permisos (ver `roles.py`); en el
admin se elige el rol, nunca permisos sueltos.
"""

from django.db import models


class Permisos(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("ver_trabajos", "Ver trabajos, estados y registros"),
            ("preparar_trabajos", "Pasar trabajos a pendientes, revisarlos y retirarlos"),
            ("registrar_avances", "Registrar avances en planta"),
            ("escribir_notas", "Escribir observaciones, sugerencias y preguntas"),
            ("anular_registros", "Anular registros de planta"),
            ("cerrar_dia", "Cerrar y reabrir el día"),
        ]

    def __str__(self) -> str:
        return "Permisos de la app"
