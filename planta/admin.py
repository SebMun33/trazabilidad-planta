"""Admin de Django.

Las tablas de `planta` son de solo agregar filas: en el admin se pueden ver,
pero no editar ni borrar. Las altas y correcciones se hacen desde las pantallas
de la app (que generan filas nuevas). Los operarios salen de los usuarios con rol
Operario (Cuentas → Usuarios); acá solo se consultan.
"""

from django.contrib import admin

from cuentas.prueba import operario_prueba_id

from . import models


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Operario)
class OperarioAdmin(SoloLecturaAdmin):
    list_display = ["nombre", "activo", "usuario_id", "creado_en"]
    list_filter = ["activo"]
    search_fields = ["nombre"]
    actions = None

    def get_queryset(self, request):
        operarios = super().get_queryset(request)
        if request.user.is_superuser:
            return operarios
        # El operario de prueba solo lo ve el superusuario (ver cuentas/prueba.py).
        prueba_id = operario_prueba_id()
        return operarios.exclude(operario_id=prueba_id) if prueba_id else operarios


class TrabajoOperacionInline(admin.TabularInline):
    model = models.TrabajoOperacion
    extra = 0
    can_delete = False
    fields = ["operacion_nro", "maquina_id", "descripcion", "observaciones", "operacion_id"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(models.TrabajoRevision)
class TrabajoRevisionAdmin(SoloLecturaAdmin):
    list_display = [
        "plano",
        "revision",
        "tipo",
        "origen",
        "urgencia",
        "fecha_entrega_estimada",
        "creado_por",
        "creado_en",
    ]
    list_filter = ["tipo", "origen", "urgencia"]
    search_fields = ["plano", "cliente_nombre", "pedido_id", "cotizacion_id"]
    inlines = [TrabajoOperacionInline]


@admin.register(models.Evento)
class EventoAdmin(SoloLecturaAdmin):
    list_display = ["ocurrido_en", "tipo", "operario", "maquina_id", "trabajo_id", "dispositivo"]
    list_filter = ["tipo", "dispositivo"]
    date_hierarchy = "ocurrido_en"


@admin.register(models.CierreDia)
class CierreDiaAdmin(SoloLecturaAdmin):
    list_display = ["fecha", "tipo", "registrado_por", "registrado_en"]


@admin.register(models.Nota)
class NotaAdmin(SoloLecturaAdmin):
    list_display = ["escrita_en", "tipo", "autor", "trabajo_id", "dispositivo"]
    list_filter = ["tipo", "dispositivo"]
    search_fields = ["texto", "autor"]
    date_hierarchy = "escrita_en"
