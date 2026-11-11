from django.contrib import admin
from django.urls import path

admin.site.site_header = "Trazabilidad de planta"
admin.site.site_title = "Trazabilidad de planta"
admin.site.index_title = "Administración"

urlpatterns = [
    path("admin/", admin.site.urls),
]
