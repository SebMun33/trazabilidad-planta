from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "oficina"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="oficina:pendientes"), name="inicio"),
    path("pendientes/", views.pendientes, name="pendientes"),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("cotizaciones/", views.cotizaciones, name="cotizaciones"),
    path("trabajos/nuevo/", views.trabajo_nuevo, name="trabajo_nuevo"),
    path("trabajos/<uuid:trabajo_id>/", views.trabajo_detalle, name="trabajo"),
    path("trabajos/<uuid:trabajo_id>/revisar/", views.trabajo_revisar, name="trabajo_revisar"),
    path("trabajos/<uuid:trabajo_id>/retirar/", views.trabajo_retirar, name="trabajo_retirar"),
    path("registros/", views.registros, name="registros"),
    path("registros/<uuid:evento_id>/anular/", views.evento_anular, name="evento_anular"),
    path("cierre/", views.cierre, name="cierre"),
]
