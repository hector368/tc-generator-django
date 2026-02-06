"""
Enrutamiento de la aplicación tcgen.

Define las rutas públicas para la pantalla principal, generación por streaming y descarga del CSV.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="tcgen_home"),
    path("generate/stream/", views.generate_stream, name="tcgen_generate_stream"),
    path("download/", views.download_csv, name="tcgen_download"),
]
