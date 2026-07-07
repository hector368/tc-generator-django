"""
Servicio de extracción de información desde documentos PAP.

Este módulo ejecuta el flujo completo de extracción para el PAP:
- Extrae texto del archivo.
- Carga el prompt especializado.
- Llama a Claude.
- Convierte la respuesta en JSON.
- Valida la estructura esperada para el PEP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from core.claude_client import call_claude, get_client
from core.extractor import extract_text_from_upload
from tcgen.services.pep.json_response_parser import parse_json_response
from tcgen.services.pep.pap_schema import PapExtractionData
from tcgen.services.pep.pap_schema import validate_pap_payload
from tcgen.services.pep.prompt_loader import load_pap_prompt
from tcgen.utils.validators import validate_extracted_text


@dataclass(frozen=True)
class PapExtractionResult:
    """
    Resultado normalizado de la extracción PAP.

    Attributes:
        data: Información del PAP validada.
        usage: Métricas de tokens reportadas por Claude.
        elapsed_seconds: Tiempo total del procesamiento.
        text_chars: Cantidad de caracteres extraídos del documento.
    """

    data: PapExtractionData
    usage: dict[str, int]
    elapsed_seconds: float
    text_chars: int


def extract_pap_information(
    *,
    filename: str,
    file_bytes: bytes,
) -> PapExtractionResult:
    """
    Extrae información estructurada desde un archivo PAP.

    Args:
        filename: Nombre original del archivo PAP.
        file_bytes: Contenido binario del archivo PAP.

    Returns:
        Resultado validado con la información del PAP.

    Raises:
        ValueError: Si no se puede extraer texto o si la respuesta del
            modelo no cumple la estructura esperada.
        RuntimeError: Si falta la API key de Claude.
        FileNotFoundError: Si el prompt PAP no existe.
    """
    start_time = time.perf_counter()

    doc_text = extract_text_from_upload(filename, file_bytes)
    validation = validate_extracted_text(doc_text)
    if not validation.ok:
        raise ValueError(validation.message)

    prompt_text = load_pap_prompt()
    user_text = _build_pap_user_text(doc_text)

    client = get_client()
    raw_response, usage = call_claude(
        client=client,
        model=settings.CLAUDE_MODEL,
        system_prompt=prompt_text,
        user_text=user_text,
        max_tokens=settings.MAX_TOKENS,
    )

    payload = parse_json_response(raw_response)
    data = validate_pap_payload(payload)

    elapsed = time.perf_counter() - start_time

    return PapExtractionResult(
        data=data,
        usage=usage,
        elapsed_seconds=round(elapsed, 2),
        text_chars=len(doc_text),
    )


def _build_pap_user_text(pap_text: str) -> str:
    """
    Construye el mensaje de usuario para Claude.

    El prompt de sistema contiene las reglas de extracción. El mensaje
    de usuario solo entrega el contenido del PAP.

    Args:
        pap_text: Texto extraído del documento PAP.

    Returns:
        Texto listo para enviarse al modelo.
    """
    return (
        "Contenido del PAP:\n"
        f"{pap_text.strip()}"
    )


def build_pap_preview_payload(
    result: PapExtractionResult,
) -> dict[str, Any]:
    """
    Convierte el resultado validado a un payload serializable para UI.

    Args:
        result: Resultado de extracción PAP.

    Returns:
        Diccionario listo para JsonResponse.
    """
    return {
        "ok": True,
        "pap": result.data.model_dump(mode="json"),
        "usage": result.usage,
        "elapsed": result.elapsed_seconds,
        "text_chars": result.text_chars,
    }