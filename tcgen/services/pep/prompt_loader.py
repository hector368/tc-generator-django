"""
Carga de prompts para el flujo de generación de PEP.

Este módulo mantiene aislada la lectura del prompt PAP para no mezclarla
con el prompt principal usado por el generador de casos de prueba.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from django.conf import settings


PAP_PROMPT_RELATIVE_PATH: Final[str] = "prompt/pap_extraction_prompt.txt"


def get_pap_prompt_path() -> Path:
    """
    Construye la ruta del prompt de extracción PAP.

    Returns:
        Ruta absoluta al archivo de prompt PAP.
    """
    base_dir = Path(settings.BASE_DIR)
    return base_dir / PAP_PROMPT_RELATIVE_PATH


def load_pap_prompt() -> str:
    """
    Carga el prompt usado para extraer información del PAP.

    Returns:
        Texto del prompt PAP.

    Raises:
        FileNotFoundError: Si el archivo de prompt no existe.
        ValueError: Si el archivo existe pero está vacío.
    """
    prompt_path = get_pap_prompt_path()

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"No se encontró el prompt PAP: {prompt_path}"
        )

    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise ValueError("El prompt PAP está vacío.")

    return prompt_text