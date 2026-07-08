"""
Análisis integral de documentos PDD/FDD para el generador PEP.

Este módulo envía el contenido completo del PDD/FDD a Claude para extraer
los requerimientos funcionales principales y el contexto operativo necesario
para calcular el plan de insumos de testing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from core.claude_client import call_claude, get_client
from core.extractor import extract_text_from_upload
from tcgen.services.pep.insumo_calculator import (
    recalculate_insumo_plan,
)
from tcgen.services.pep.json_response_parser import (
    parse_json_response,
)
from tcgen.services.pep.pdd_prompt_loader import (
    load_pdd_analysis_prompt,
)
from tcgen.services.pep.pdd_schema import (
    PddAnalysisData,
    validate_pdd_payload,
)
from tcgen.utils.validators import validate_extracted_text


@dataclass(frozen=True, slots=True)
class PddAnalysisResult:
    """
    Resultado completo del análisis de un PDD/FDD.
    """

    data: PddAnalysisData
    usage: dict[str, int]
    elapsed_seconds: float
    text_chars: int


def analyze_pdd_information(
    *,
    filename: str,
    file_bytes: bytes,
) -> PddAnalysisResult:
    """
    Analiza un documento PDD/FDD utilizando Claude.

    Extrae los requerimientos funcionales principales y el contexto del
    proceso. Después recalcula de forma determinística el plan de insumos.

    Args:
        filename: Nombre original del archivo PDD/FDD.
        file_bytes: Contenido binario del documento.

    Returns:
        Resultado validado del análisis PDD/FDD.

    Raises:
        ValueError: Si el documento no contiene texto válido o si la
            respuesta del modelo no cumple el contrato esperado.
    """
    started_at = time.perf_counter()

    doc_text = extract_text_from_upload(
        filename,
        file_bytes,
    )

    validation = validate_extracted_text(doc_text)
    if not validation.ok:
        raise ValueError(validation.message)

    prompt_text = load_pdd_analysis_prompt()
    user_text = _build_pdd_user_text(doc_text)

    client = get_client()

    raw_response, usage = call_claude(
        client=client,
        model=settings.CLAUDE_MODEL,
        system_prompt=prompt_text,
        user_text=user_text,
        max_tokens=settings.MAX_TOKENS,
    )

    payload = parse_json_response(raw_response)
    pdd_data = validate_pdd_payload(payload)

    pdd_data = recalculate_insumo_plan(pdd_data)

    elapsed = time.perf_counter() - started_at

    return PddAnalysisResult(
        data=pdd_data,
        usage=usage,
        elapsed_seconds=round(elapsed, 2),
        text_chars=len(doc_text),
    )

def build_pdd_preview_payload(
    result: PddAnalysisResult,
) -> dict[str, Any]:
    """
    Construye el payload serializable para la previsualización del PDD/FDD.

    Args:
        result: Resultado completo del análisis.

    Returns:
        Diccionario listo para respuesta JSON.
    """
    return {
        "ok": True,
        "pdd": result.data.model_dump(
            mode="json",
        ),
        "usage": result.usage,
        "elapsed": result.elapsed_seconds,
        "text_chars": result.text_chars,
    }


def _build_pdd_user_text(
    pdd_text: str,
) -> str:
    """
    Construye el mensaje de usuario enviado a Claude.

    Args:
        pdd_text: Texto extraído del PDD/FDD.

    Returns:
        Contenido documental enviado al modelo.
    """
    return (
        "Contenido del PDD/FDD:\n"
        + pdd_text.strip()
    )