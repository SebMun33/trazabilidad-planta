from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Trazabilidad de planta"
admin.site.site_title = "Trazabilidad de planta"
admin.site.index_title = "Administración"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="oficina:pendientes"), name="inicio"),
    path("cuentas/login/", auth_views.LoginView.as_view(), name="login"),
    path("cuentas/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("oficina/", include("oficina.urls")),
    path("admin/", admin.site.urls),
]
