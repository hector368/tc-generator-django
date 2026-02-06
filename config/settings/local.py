"""
Configuración para entorno de desarrollo local.

Extiende la configuración base y ajusta parámetros de desarrollo.
"""
from config.settings.base import *  # noqa: F401, F403

# IDs de Rastreabilidad:
# - REQ-CONFIG-004: Configuración de entorno de desarrollo.

# Habilita modo debug para desarrollo.
DEBUG = True
