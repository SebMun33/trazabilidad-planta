"""Comparación de nombres de usuario sin importar mayúsculas ni tildes."""

import unicodedata


def normalizar(nombre: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", nombre or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())


def buscar_usuario(nombre: str, *, activos: bool = True):
    """Usuario cuyo nombre coincide (mayúsculas y tildes no importan), o None."""
    from django.contrib.auth import get_user_model

    buscado = normalizar(nombre)
    if not buscado:
        return None
    usuarios = get_user_model().objects.all()
    if activos:
        usuarios = usuarios.filter(is_active=True)
    # Pocos usuarios: se compara en Python para ignorar también las tildes.
    return next((u for u in usuarios if normalizar(u.username) == buscado), None)
