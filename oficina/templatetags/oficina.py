from django import template

register = template.Library()


@register.filter
def obtener(diccionario, clave):
    """`{{ dic|obtener:clave }}`: acceso a diccionarios con claves no literales."""
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None


@register.filter
def contiene(coleccion, valor):
    """Pertenencia comparando como texto (los UUID llegan como UUID o como str)."""
    if not coleccion or valor in (None, ""):
        return False
    return str(valor) in {str(c) for c in coleccion}
