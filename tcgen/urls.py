"""
Enrutamiento de la aplicación tcgen.

Define las rutas públicas para la pantalla principal, generación por streaming y descarga del CSV.
"""

from django.urls import path

from . import views
from . import views_pep

urlpatterns = [
    path("", views.home, name="tcgen_home"),
    path("generate/stream/", views.generate_stream, name="tcgen_generate_stream"),
    path("download/", views.download_csv, name="tcgen_download"),
    path("pep/", views_pep.pep_home, name="tcgen_pep_home"),
    path("pep/preview/", views_pep.pep_preview, name="tcgen_pep_preview"),
    path("pep/generate/", views_pep.pep_generate, name="tcgen_pep_generate"),
    path("analyze/", views.analyze_document, name="tcgen_analyze"),  
]