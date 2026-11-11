"""Lógica de dominio compartida por la oficina (parte A) y el kiosco (parte B).

Las vistas no escriben en la base directamente: llaman a estas funciones, que
validan las reglas y graban filas nuevas (nunca modifican ni borran).
"""


class ReglaDeNegocioError(Exception):
    """Una operación viola una regla del dominio. El mensaje se muestra al usuario."""
