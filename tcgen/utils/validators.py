"""
Validadores reutilizables para entradas del generador de casos de prueba (tcgen).

Este módulo centraliza validaciones simples para:
- Archivo de prompt (existencia y contenido).
- Extensión y tamaño de archivos subidos.
- Texto extraído.
- Campo Assigned To.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

@dataclass(frozen=True)
class ValidationResult:
    """Representa el resultado de una validación para uso en endpoints y servicios."""

    ok: bool
    message: str = ""


PROMPT_RELATIVE_PATH: Final[str] = "prompt/prompt.txt"

MSG_MISSING_PROMPT: Final[str] = "Missing prompt file: prompt/prompt.txt"
MSG_EMPTY_PROMPT: Final[str] = "The prompt file is empty: prompt/prompt.txt"
MSG_NO_TEXT_EXTRACTED: Final[str] = "No text could be extracted from the document."
MSG_BAD_MAX_UPLOAD: Final[str] = "Maximum upload size is not configured correctly."
MSG_ASSIGNED_TO_REQUIRED: Final[str] = "Assigned To is required."


def validate_prompt_file(prompt_path: Path) -> ValidationResult:
    """
    Valida que el archivo de prompt exista y tenga contenido.

    Nota:
    - No valida estructura ni formato del prompt.
    - Solo valida existencia y que no esté vacío.
    """
    if not prompt_path.exists():
        return ValidationResult(False, MSG_MISSING_PROMPT)

    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        return ValidationResult(False, MSG_EMPTY_PROMPT)

    return ValidationResult(True, "")


def validate_extension(filename: str, allowed_exts: Iterable[str]) -> ValidationResult:
    """
    Valida la extensión del archivo comparando por sufijo.

    Nota:
    - La comparación es intencionalmente simple: filename.lower().endswith(ext).
    - La lista de extensiones normalmente proviene de SUPPORTED_EXTS.
    """
    filename_lower = (filename or "").lower()
    if not any(filename_lower.endswith(ext) for ext in allowed_exts):
        allowed = ", ".join(sorted(allowed_exts))
        return ValidationResult(False, f"Unsupported file type. Allowed: {allowed}")

    return ValidationResult(True, "")


def validate_size(file_size_bytes: int, max_mb: int) -> ValidationResult:
    """
    Valida que el tamaño del archivo no exceda el límite configurado.

    max_mb se interpreta como megabytes (MiB): 1024 * 1024.
    """
    safe_max_mb = int(max_mb or 0)
    max_bytes = safe_max_mb * 1024 * 1024

    if max_bytes <= 0:
        return ValidationResult(False, MSG_BAD_MAX_UPLOAD)

    if int(file_size_bytes or 0) > max_bytes:
        return ValidationResult(
            False,
            f"File too large. Maximum allowed size is {safe_max_mb} MB.",
        )

    return ValidationResult(True, "")


def validate_extracted_text(doc_text: str) -> ValidationResult:
    """
    Valida que el documento tenga texto extraíble.

    Esta validación permite fallar temprano cuando el PDF/DOCX viene vacío o es imagen.
    """
    if not (doc_text or "").strip():
        return ValidationResult(False, MSG_NO_TEXT_EXTRACTED)

    return ValidationResult(True, "")


def validate_assigned_to(assigned_to: str) -> ValidationResult:
    """
    Valida que el campo Assigned To venga informado.

    Regla:
    - Debe contener el display name exacto de Azure DevOps.
    - Solo valida presencia (no intenta validar contra ADO).
    """
    value = (assigned_to or "").replace("\r", " ").replace("\n", " ").strip()
    if not value:
        return ValidationResult(False, MSG_ASSIGNED_TO_REQUIRED)

    return ValidationResult(True, "")
