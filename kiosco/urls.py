from django.urls import path

from . import views

app_name = "kiosco"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("estado/", views.estado, name="estado"),
    path("<int:operario_id>/", views.pendientes, name="pendientes"),
    path("<int:operario_id>/trabajo/<uuid:trabajo_id>/", views.trabajo, name="trabajo"),
    path(
        "<int:operario_id>/trabajo/<uuid:trabajo_id>/operacion/<uuid:operacion_id>/",
        views.operacion,
        name="operacion",
    ),
    path("<int:operario_id>/deshacer/<uuid:evento_id>/", views.deshacer, name="deshacer"),
]
