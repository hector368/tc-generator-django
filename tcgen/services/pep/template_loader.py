"""
Carga y validación de la plantilla DOCX usada para generar el PEP.

La plantilla PEP se mantiene integrada dentro del proyecto para evitar
que el usuario tenga que subirla manualmente en cada generación.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from django.conf import settings


PEP_TEMPLATE_RELATIVE_PATH: Final[Path] = (
    Path("resources") / "pep_templates" / "pep_template.docx"
)


@dataclass(frozen=True)
class PepTemplateInfo:
    """
    Información básica de la plantilla PEP validada.

    Attributes:
        path: Ruta absoluta de la plantilla.
        filename: Nombre del archivo de plantilla.
        size_bytes: Tamaño del archivo en bytes.
    """

    path: Path
    filename: str
    size_bytes: int


def get_pep_template_path() -> Path:
    """
    Construye la ruta absoluta de la plantilla PEP integrada.

    Returns:
        Ruta absoluta hacia resources/pep_templates/pep_template.docx.
    """
    base_dir = Path(settings.BASE_DIR)
    return base_dir / PEP_TEMPLATE_RELATIVE_PATH


def validate_pep_template(
    template_path: Path | None = None,
) -> PepTemplateInfo:
    """
    Valida que la plantilla PEP exista y sea un archivo DOCX utilizable.

    Args:
        template_path: Ruta opcional para validar una plantilla específica.
            Si no se proporciona, se usa la plantilla integrada.

    Returns:
        Información básica de la plantilla validada.

    Raises:
        FileNotFoundError: Si la plantilla no existe.
        ValueError: Si la ruta no apunta a un archivo DOCX válido.
    """
    path = template_path or get_pep_template_path()

    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró la plantilla PEP: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"La ruta de plantilla PEP no es un archivo: {path}"
        )

    if path.suffix.lower() != ".docx":
        raise ValueError(
            "La plantilla PEP debe ser un archivo .docx."
        )

    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise ValueError("La plantilla PEP está vacía.")

    return PepTemplateInfo(
        path=path,
        filename=path.name,
        size_bytes=size_bytes,
    )


def read_pep_template_bytes(
    template_path: Path | None = None,
) -> bytes:
    """
    Lee la plantilla PEP como bytes.

    Args:
        template_path: Ruta opcional de plantilla.

    Returns:
        Contenido binario de la plantilla PEP validada.
    """
    template_info = validate_pep_template(template_path)
    return template_info.path.read_bytes()