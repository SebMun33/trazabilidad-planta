"""URLs de la PC de planta: solo el kiosco."""

from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="kiosco:inicio"), name="inicio"),
    path("kiosco/", include("kiosco.urls")),
]
