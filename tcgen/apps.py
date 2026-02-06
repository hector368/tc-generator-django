"""
Configuración de la aplicación tcgen.

Declara la configuración base de la app para registro en Django.
"""

from django.apps import AppConfig

class TcgenConfig(AppConfig):
    """Configuración de la app tcgen."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tcgen"
    verbose_name = "TC Generator"
