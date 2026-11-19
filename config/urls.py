from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import redirect_to_login
from django.urls import include, path
from django.views.generic import RedirectView

from cuentas import views as cuentas_views

admin.site.site_header = "Trazabilidad de planta"
admin.site.site_title = "Trazabilidad de planta"
admin.site.index_title = "Administración"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="oficina:pendientes"), name="inicio"),
    path("cuentas/login/", cuentas_views.ingresar, name="login"),
    path("cuentas/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("oficina/", include("oficina.urls")),
    # El admin usa el mismo ingreso por nombre que el resto de la app.
    path(
        "admin/login/",
        lambda request: redirect_to_login(request.GET.get("next", "/admin/")),
        name="admin_ingreso",
    ),
    path("admin/", admin.site.urls),
    # En la nube el kiosco solo responde en modo prueba (superusuario); en la PC
    # de planta y en desarrollo, a la IP local. Ver kiosco/acceso.py.
    path("kiosco/", include("kiosco.urls")),
]
