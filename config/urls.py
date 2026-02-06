"""
Configuración de URLs para el proyecto TC Generator.

Define rutas principales del proyecto, incluyendo admin y la app tcgen.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("tcgen.urls")),
]
