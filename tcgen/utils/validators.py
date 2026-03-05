"""
Validadores reutilizables para entradas del generador de casos de prueba.

Este modulo centraliza las validaciones de archivo de prompt, extension
y tamaño de archivos subidos, texto extraido y campo Assigned To.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable


@dataclass(frozen=True)
class ValidationResult:
    """
    Representa el resultado de una validacion para uso en endpoints
    y servicios.

    Attributes:
        ok: Indica si la validacion fue exitosa.
        message: Mensaje descriptivo del resultado, vacio si es exitoso.
    """

    ok: bool
    message: str = ""


PROMPT_RELATIVE_PATH: Final[str] = "prompt/prompt.txt"

MSG_MISSING_PROMPT: Final[str] = "Missing prompt file: prompt/prompt.txt"
MSG_EMPTY_PROMPT: Final[str] = "The prompt file is empty: prompt/prompt.txt"
MSG_NO_TEXT_EXTRACTED: Final[str] = (
    "No text could be extracted from the document."
)
MSG_BAD_MAX_UPLOAD: Final[str] = (
    "Maximum upload size is not configured correctly."
)
MSG_ASSIGNED_TO_REQUIRED: Final[str] = "Assigned To is required."


# Valida que el archivo de prompt exista y tenga contenido util.
def validate_prompt_file(prompt_path: Path) -> ValidationResult:
    """
    No verifica la estructura ni el formato del prompt, unicamente
    comprueba que el archivo este presente y no este vacio.

    Args:
        prompt_path: Ruta al archivo de prompt a validar.

    Returns:
        ValidationResult con ok=True si el archivo existe y tiene
        contenido, o con ok=False y el mensaje de error correspondiente.
    """
    if not prompt_path.exists():
        return ValidationResult(False, MSG_MISSING_PROMPT)

    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        return ValidationResult(False, MSG_EMPTY_PROMPT)

    return ValidationResult(True, "")


# Valida que la extension del archivo este entre las permitidas.
def validate_extension(
    filename: str,
    allowed_exts: Iterable[str],
) -> ValidationResult:
    """
    La comparacion se realiza sobre el nombre en minusculas usando
    sufijos, sin analizar la estructura interna del archivo.

    Args:
        filename: Nombre del archivo a validar.
        allowed_exts: Coleccion de extensiones permitidas.

    Returns:
        ValidationResult con ok=True si la extension es valida, o con
        ok=False e indicacion de las extensiones aceptadas.
    """
    filename_lower = (filename or "").lower()
    if not any(filename_lower.endswith(ext) for ext in allowed_exts):
        allowed = ", ".join(sorted(allowed_exts))
        return ValidationResult(
            False,
            f"Unsupported file type. Allowed: {allowed}",
        )

    return ValidationResult(True, "")


# Valida que el tamaño del archivo no exceda el limite configurado.
def validate_size(file_size_bytes: int, max_mb: int) -> ValidationResult:
    """
    El parametro max_mb se interpreta como mebibytes usando el factor
    de conversion de 1024 por 1024.

    Args:
        file_size_bytes: Tamaño del archivo en bytes.
        max_mb: Limite maximo permitido en mebibytes.

    Returns:
        ValidationResult con ok=True si el tamaño es valido, o con
        ok=False si el limite no esta configurado o se excede.
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


#  Valida que el documento contenga texto extraible.
def validate_extracted_text(doc_text: str) -> ValidationResult:
    """
    Permite detectar de forma temprana documentos vacios o compuestos
    exclusivamente por imagenes antes de continuar el procesamiento.

    Args:
        doc_text: Texto extraido del documento.

    Returns:
        ValidationResult con ok=True si hay texto util, o con ok=False
        si el texto esta ausente o es unicamente espacios en blanco.
    """
    if not (doc_text or "").strip():
        return ValidationResult(False, MSG_NO_TEXT_EXTRACTED)

    return ValidationResult(True, "")


# Valida que el campo Assigned To venga informado.
def validate_assigned_to(assigned_to: str) -> ValidationResult:
    """
    Solo verifica la presencia del valor sin intentar validarlo contra
    Azure DevOps. El valor esperado es el display name exacto del usuario.

    Args:
        assigned_to: Valor del campo Assigned To a validar.

    Returns:
        ValidationResult con ok=True si el campo tiene contenido, o con
        ok=False si esta ausente o contiene solo espacios en blanco.
    """
    value = (assigned_to or "").replace("\r", " ").replace("\n", " ").strip()
    if not value:
        return ValidationResult(False, MSG_ASSIGNED_TO_REQUIRED)

    return ValidationResult(True, "")