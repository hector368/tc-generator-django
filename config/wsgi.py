"""
Configuración WSGI para el proyecto.

Expone la variable de módulo ``application`` para servidores WSGI.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.local"),
)

application = get_wsgi_application()
