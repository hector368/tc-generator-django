"""
Orquestador del flujo de generación de PEP.

Este módulo coordina el análisis del PAP y PDD/FDD, construye el contexto
combinado y genera el documento DOCX final.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from tcgen.services.pep.costs import build_cost_payload
from tcgen.services.pep.pap_extraction import extract_pap_information
from tcgen.services.pep.pap_schema import PapExtractionData
from tcgen.services.pep.pdd_analysis import analyze_pdd_information
from tcgen.services.pep.pdd_schema import PddAnalysisData
from tcgen.services.pep.pep_context import (
    PepContext,
    build_pep_context,
    build_pep_context_payload,
)
from tcgen.services.pep.pep_docx_writer import generate_pep_docx_bytes


@dataclass(frozen=True)
class PepPreviewResult:
    """
    Resultado de previsualización del PEP.

    Attributes:
        context: Contexto combinado PAP + PDD/FDD.
        payload: Diccionario serializable para UI.
        usage: Métricas combinadas de las llamadas a Claude.
        elapsed_seconds: Tiempo total de previsualización.
    """

    context: PepContext
    payload: dict[str, Any]
    usage: dict[str, int]
    elapsed_seconds: float


@dataclass(frozen=True)
class PepDocumentResult:
    """
    Resultado final de generación del documento PEP.

    Attributes:
        context: Contexto usado para generar el documento.
        filename: Nombre sugerido del archivo DOCX final.
        docx_bytes: Contenido binario del documento generado.
        payload: Diccionario serializable con resumen del resultado.
        usage: Métricas combinadas de las llamadas a Claude.
        elapsed_seconds: Tiempo total del flujo.
    """

    context: PepContext
    filename: str
    docx_bytes: bytes
    payload: dict[str, Any]
    usage: dict[str, int]
    elapsed_seconds: float


def build_pep_preview(
    *,
    pap_filename: str,
    pap_bytes: bytes,
    pdd_filename: str,
    pdd_bytes: bytes,
    selected_requirements: list[int] | None = None,
) -> PepPreviewResult:
    """
    Construye la previsualización del PEP sin generar DOCX.

    Todos los requerimientos principales detectados en el PDD/FDD
    se conservan automáticamente.

    Args:
        pap_filename: Nombre original del archivo PAP.
        pap_bytes: Contenido binario del PAP.
        pdd_filename: Nombre original del archivo PDD/FDD.
        pdd_bytes: Contenido binario del PDD/FDD.
        selected_requirements: Parámetro temporal de compatibilidad con
            la interfaz anterior. No modifica los requerimientos.

    Returns:
        Resultado de previsualización listo para UI.
    """
    del selected_requirements

    start_time = time.perf_counter()

    pap_result = extract_pap_information(
        filename=pap_filename,
        file_bytes=pap_bytes,
    )

    pdd_result = analyze_pdd_information(
        filename=pdd_filename,
        file_bytes=pdd_bytes,
    )

    context = build_pep_context(
        pap_data=pap_result.data,
        pdd_data=pdd_result.data,
    )

    usage = _combine_usage(
        pap_result.usage,
        pdd_result.usage,
    )

    elapsed = time.perf_counter() - start_time

    payload = build_pep_context_payload(context)
    payload["usage"] = usage
    payload["cost"] = build_cost_payload(usage)
    payload["elapsed"] = round(elapsed, 2)

    return PepPreviewResult(
        context=context,
        payload=payload,
        usage=usage,
        elapsed_seconds=round(elapsed, 2),
    )


def generate_pep_document(
    *,
    pap_filename: str,
    pap_bytes: bytes,
    pdd_filename: str,
    pdd_bytes: bytes,
    selected_requirements: list[int] | None = None,
) -> PepDocumentResult:
    """
    Genera el documento PEP final desde PAP y PDD/FDD.

    Todos los requerimientos principales detectados se incluyen.

    Args:
        pap_filename: Nombre original del archivo PAP.
        pap_bytes: Contenido binario del PAP.
        pdd_filename: Nombre original del archivo PDD/FDD.
        pdd_bytes: Contenido binario del PDD/FDD.
        selected_requirements: Parámetro temporal de compatibilidad con
            la interfaz anterior. No modifica los requerimientos.

    Returns:
        Resultado con el DOCX generado y su metadata.
    """
    start_time = time.perf_counter()

    preview = build_pep_preview(
        pap_filename=pap_filename,
        pap_bytes=pap_bytes,
        pdd_filename=pdd_filename,
        pdd_bytes=pdd_bytes,
        selected_requirements=selected_requirements,
    )

    docx_bytes = generate_pep_docx_bytes(
        preview.context,
    )

    elapsed = time.perf_counter() - start_time

    payload = dict(preview.payload)
    payload["filename"] = preview.context.output_filename
    payload["elapsed"] = round(elapsed, 2)

    return PepDocumentResult(
        context=preview.context,
        filename=preview.context.output_filename,
        docx_bytes=docx_bytes,
        payload=payload,
        usage=preview.usage,
        elapsed_seconds=round(elapsed, 2),
    )


def build_pep_preview_from_validated_data(
    *,
    pap_data: PapExtractionData,
    pdd_data: PddAnalysisData,
) -> PepPreviewResult:
    """
    Construye preview usando datos previamente validados.

    Esta función permite realizar pruebas locales sin consumir la API.

    Args:
        pap_data: Datos PAP previamente validados.
        pdd_data: Datos PDD/FDD previamente validados.

    Returns:
        Resultado de preview sin llamadas a Claude.
    """
    context = build_pep_context(
        pap_data=pap_data,
        pdd_data=pdd_data,
    )

    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
    }

    payload = build_pep_context_payload(context)
    payload["usage"] = usage
    payload["cost"] = build_cost_payload(usage)
    payload["elapsed"] = 0

    return PepPreviewResult(
        context=context,
        payload=payload,
        usage=usage,
        elapsed_seconds=0,
    )


def generate_pep_document_from_validated_data(
    *,
    pap_data: PapExtractionData,
    pdd_data: PddAnalysisData,
) -> PepDocumentResult:
    """
    Genera el DOCX utilizando datos previamente validados.

    Esta función permite probar el documento final sin consumir la API.

    Args:
        pap_data: Datos PAP previamente validados.
        pdd_data: Datos PDD/FDD previamente validados.

    Returns:
        Resultado con el DOCX generado.
    """
    preview = build_pep_preview_from_validated_data(
        pap_data=pap_data,
        pdd_data=pdd_data,
    )

    docx_bytes = generate_pep_docx_bytes(
        preview.context,
    )

    payload = dict(preview.payload)
    payload["filename"] = preview.context.output_filename
    payload["elapsed"] = 0

    return PepDocumentResult(
        context=preview.context,
        filename=preview.context.output_filename,
        docx_bytes=docx_bytes,
        payload=payload,
        usage=preview.usage,
        elapsed_seconds=0,
    )


def _combine_usage(
    *usage_payloads: dict[str, int],
) -> dict[str, int]:
    """
    Combina las métricas de uso de múltiples llamadas al modelo.

    Args:
        usage_payloads: Métricas individuales de cada llamada.

    Returns:
        Métricas acumuladas por tipo de token.
    """
    combined_usage: dict[str, int] = {}

    for usage in usage_payloads:
        for key, value in usage.items():
            combined_usage[key] = (
                combined_usage.get(key, 0)
                + int(value)
            )

    return combined_usage