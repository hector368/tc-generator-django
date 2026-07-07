"""
Parser de respuestas JSON generadas por el modelo.

Este módulo convierte la respuesta cruda del LLM en un diccionario
Python validado superficialmente antes de enviarlo al esquema Pydantic.
"""

from __future__ import annotations

import json
from typing import Any, Final


JSON_START: Final[str] = "{"
JSON_END: Final[str] = "}"
MARKDOWN_FENCE: Final[str] = "```"


def parse_json_response(raw_text: str) -> dict[str, Any]:
    """
    Convierte una respuesta cruda del modelo en un diccionario JSON.

    Args:
        raw_text: Texto devuelto por el modelo.

    Returns:
        Diccionario obtenido desde el JSON parseado.

    Raises:
        ValueError: Si la respuesta está vacía, no contiene JSON válido
            o el JSON raíz no es un objeto.
    """
    cleaned = _strip_code_fences(raw_text)

    if not cleaned:
        raise ValueError("La respuesta del modelo está vacía.")

    try:
        payload = json.loads(cleaned)
        return _ensure_dict(payload)
    except json.JSONDecodeError:
        pass

    json_text = _extract_first_json_object(cleaned)

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "La respuesta del modelo no contiene JSON válido."
        ) from exc

    return _ensure_dict(payload)


def _strip_code_fences(text: str) -> str:
    """
    Elimina fences markdown cuando el modelo devuelve ```json ... ```.

    Args:
        text: Texto crudo de entrada.

    Returns:
        Texto sin fences markdown externos.
    """
    cleaned = (text or "").strip()
    if not cleaned.startswith(MARKDOWN_FENCE):
        return cleaned

    lines = cleaned.splitlines()

    if lines:
        lines = lines[1:]

    while lines and lines[-1].strip().startswith(MARKDOWN_FENCE):
        lines.pop()

    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> str:
    """
    Extrae el primer objeto JSON balanceado encontrado en el texto.

    Respeta strings y caracteres escapados para evitar cortar el JSON
    incorrectamente cuando existan llaves dentro de cadenas.

    Args:
        text: Texto donde se buscará el primer objeto JSON.

    Returns:
        Cadena correspondiente al primer objeto JSON encontrado.

    Raises:
        ValueError: Si no se encuentra un objeto JSON balanceado.
    """
    source = text or ""
    start = source.find(JSON_START)

    if start == -1:
        raise ValueError("No se encontró inicio de objeto JSON.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(source)):
        char = source[index]

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == JSON_START:
            depth += 1
            continue

        if char == JSON_END:
            depth -= 1
            if depth == 0:
                return source[start:index + 1]

    raise ValueError("No se encontró un objeto JSON completo.")


def _ensure_dict(payload: Any) -> dict[str, Any]:
    """
    Valida que el JSON raíz sea un objeto.

    Args:
        payload: Resultado de json.loads.

    Returns:
        Payload como diccionario.

    Raises:
        ValueError: Si el JSON raíz no es un objeto.
    """
    if not isinstance(payload, dict):
        raise ValueError("El JSON raíz debe ser un objeto.")

    return payload