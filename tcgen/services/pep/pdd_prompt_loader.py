"""
Carga del prompt utilizado para analizar documentos PDD/FDD.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]

PDD_ANALYSIS_PROMPT_PATH = (
    PROJECT_ROOT
    / "prompt"
    / "pdd_analysis_prompt.txt"
)


def get_pdd_analysis_prompt_path() -> Path:
    """
    Obtiene la ruta absoluta del prompt PDD/FDD.

    Returns:
        Ruta del archivo de prompt.
    """
    return PDD_ANALYSIS_PROMPT_PATH


def load_pdd_analysis_prompt() -> str:
    """
    Carga el prompt de análisis PDD/FDD.

    Returns:
        Contenido textual del prompt.

    Raises:
        FileNotFoundError: Si el prompt no existe.
        ValueError: Si el prompt está vacío.
    """
    prompt_path = get_pdd_analysis_prompt_path()

    if not prompt_path.is_file():
        raise FileNotFoundError(
            "No se encontró el prompt de análisis PDD/FDD en: "
            f"{prompt_path}"
        )

    prompt = prompt_path.read_text(
        encoding="utf-8",
    ).strip()

    if not prompt:
        raise ValueError(
            "El prompt de análisis PDD/FDD está vacío."
        )

    return prompt