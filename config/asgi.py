"""
Configuración ASGI para el proyecto.

Expone la variable de módulo ``application`` para servidores ASGI.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.local"),
)

application = get_asgi_application()
