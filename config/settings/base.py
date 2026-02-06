"""
Configuración base de Django para el proyecto TC Generator.

Contiene configuraciones compartidas entre entornos (local y producción).
"""
import os
from pathlib import Path

# IDs de Rastreabilidad:
# - REQ-CONFIG-001: Configuración base del proyecto Django.
# - REQ-CONFIG-002: Gestión de variables de entorno.
# - REQ-CONFIG-003: Configuración de seguridad y límites de carga.

# Define el directorio base del proyecto.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Configuración de seguridad.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "La variable de entorno DJANGO_SECRET_KEY debe estar definida."
    )

DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS", 
    "127.0.0.1,localhost"
    ).split(",")

# Define aplicaciones instaladas.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tcgen.apps.TcgenConfig",
]

# Define middleware.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Configura el enrutamiento principal.
ROOT_URLCONF = "config.urls"

# Configura plantillas.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# Define la aplicación WSGI.
WSGI_APPLICATION = "config.wsgi.application"

# Configura base de datos (SQLite por defecto).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Define validadores de contraseña según la política de la plataforma.
AUTH_PASSWORD_VALIDATORS = []

# Configura idioma y zona horaria.
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

# Configura archivos estáticos.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Configura el tipo de PK por defecto.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Define límites de carga de archivos (25MB por defecto).
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024

# Configura parámetros del modelo.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "20000"))

# Define rutas de archivos del proyecto.
PROMPT_FILE = BASE_DIR / "prompt" / "prompt.txt"

# Define la clave de sesión para almacenar resultados.
TCGEN_SESSION_KEY_RESULT = "tcgen_result"
