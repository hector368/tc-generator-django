"""
Configuración para entorno de producción.

Extiende la configuración base y ajusta parámetros de producción.
"""
import os

from config.settings.base import *  # noqa: F401, F403

# Deshabilita modo debug para producción.
DEBUG = False

# Aplica banderas de seguridad solo si se habilitan explícitamente
# por variables de entorno.
# Esto evita cambiar el comportamiento actual si no configuras dichas variables.
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "0") == "1"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "0") == "1"
