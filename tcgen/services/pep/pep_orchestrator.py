"""
Orquestador del flujo de generación de PEP.

Este módulo une la extracción del PAP, la extracción de requerimientos
TO-BE desde PDD/FDD, la construcción del contexto y la generación del
documento DOCX final.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from tcgen.services.pep.pap_extraction import extract_pap_information
from tcgen.services.pep.pap_schema import PapExtractionData
from tcgen.services.pep.pep_context import PepContext
from tcgen.services.pep.pep_context import build_pep_context
from tcgen.services.pep.pep_context import build_pep_context_payload
from tcgen.services.pep.pep_docx_writer import generate_pep_docx_bytes
from tcgen.services.pep.tobe_requirements import ToBeRequirementsResult
from tcgen.services.pep.tobe_requirements import extract_tobe_requirements
from tcgen.services.pep.costs import build_cost_payload


@dataclass(frozen=True)
class PepPreviewResult:
    """
    Resultado de previsualización del PEP.

    Attributes:
        context: Contexto combinado PAP + PDD/FDD.
        payload: Diccionario serializable para UI.
        usage: Métricas de tokens del análisis PAP.
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
        usage: Métricas de tokens del análisis PAP.
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

    Args:
        pap_filename: Nombre original del archivo PAP.
        pap_bytes: Contenido binario del PAP.
        pdd_filename: Nombre original del archivo PDD/FDD.
        pdd_bytes: Contenido binario del PDD/FDD.
        selected_requirements: Requerimientos seleccionados por usuario.
            Si es None, se incluyen todos.

    Returns:
        Resultado de previsualización listo para UI.
    """
    start_time = time.perf_counter()

    pap_result = extract_pap_information(
        filename=pap_filename,
        file_bytes=pap_bytes,
    )

    tobe_result = extract_tobe_requirements(
        filename=pdd_filename,
        file_bytes=pdd_bytes,
        selected_requirements=selected_requirements,
    )

    context = build_pep_context(
        pap_data=pap_result.data,
        tobe_data=tobe_result,
    )

    elapsed = time.perf_counter() - start_time
    payload = build_pep_context_payload(context)
    payload["usage"] = pap_result.usage
    payload["cost"] = build_cost_payload(pap_result.usage)
    payload["elapsed"] = round(elapsed, 2)

    return PepPreviewResult(
        context=context,
        payload=payload,
        usage=pap_result.usage,
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

    Args:
        pap_filename: Nombre original del archivo PAP.
        pap_bytes: Contenido binario del PAP.
        pdd_filename: Nombre original del archivo PDD/FDD.
        pdd_bytes: Contenido binario del PDD/FDD.
        selected_requirements: Requerimientos seleccionados por usuario.
            Si es None, se incluyen todos.

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

    docx_bytes = generate_pep_docx_bytes(preview.context)

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
    tobe_data: ToBeRequirementsResult,
) -> PepPreviewResult:
    """
    Construye preview usando datos ya validados.

    Esta función sirve para pruebas locales cuando no hay saldo de Claude
    o cuando se quiere probar el llenado DOCX con datos controlados.

    Args:
        pap_data: Datos PAP previamente validados.
        tobe_data: Requerimientos TO-BE previamente extraídos.

    Returns:
        Resultado de preview sin llamada a Claude.
    """
    context = build_pep_context(
        pap_data=pap_data,
        tobe_data=tobe_data,
    )

    payload = build_pep_context_payload(context)
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
    }

    payload["usage"] = usage
    payload["cost"] = build_cost_payload(usage)
    
    return PepPreviewResult(
        context=context,
        payload=payload,
        usage=usage,
        elapsed_seconds=0,
    )


def generate_pep_document_from_validated_data(
    *,
    pap_data: PapExtractionData,
    tobe_data: ToBeRequirementsResult,
) -> PepDocumentResult:
    """
    Genera DOCX usando datos ya validados.

    Esta función permite probar el documento final sin consumir API.

    Args:
        pap_data: Datos PAP previamente validados.
        tobe_data: Requerimientos TO-BE previamente extraídos.

    Returns:
        Resultado con el DOCX generado.
    """
    preview = build_pep_preview_from_validated_data(
        pap_data=pap_data,
        tobe_data=tobe_data,
    )

    docx_bytes = generate_pep_docx_bytes(preview.context)

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