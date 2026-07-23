"""
Construcción del contexto combinado para generar el PEP.

Este módulo une la información extraída desde el PAP con el análisis
funcional y de insumos obtenido desde el PDD/FDD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tcgen.services.pep.pap_schema import PapExtractionData
from tcgen.services.pep.pdd_schema import PddAnalysisData


@dataclass(frozen=True)
class PepContext:
    """
    Contexto completo requerido para llenar la plantilla PEP.

    Attributes:
        project_id: ID final usado para el PEP.
        output_filename: Nombre sugerido para el archivo DOCX.
        pap: Datos extraídos desde el PAP.
        pdd: Análisis funcional y de insumos del PDD/FDD.
        warnings: Advertencias consolidadas.
    """

    project_id: str | None
    output_filename: str
    pap: PapExtractionData
    pdd: PddAnalysisData
    warnings: list[str]


def build_pep_context(
    *,
    pap_data: PapExtractionData,
    pdd_data: PddAnalysisData,
) -> PepContext:
    """
    Construye el contexto combinado para el PEP.

    Args:
        pap_data: Información validada del PAP.
        pdd_data: Análisis validado del PDD/FDD.

    Returns:
        Contexto combinado listo para previsualizar o generar el PEP.
    """
    project_id = _clean_optional_text(
        pap_data.id_proyecto,
    )

    warnings = _build_context_warnings(
        pap_data=pap_data,
        pdd_data=pdd_data,
    )

    return PepContext(
        project_id=project_id,
        output_filename=build_pep_output_filename(project_id),
        pap=pap_data,
        pdd=pdd_data,
        warnings=warnings,
    )


def build_pep_context_payload(
    context: PepContext,
) -> dict[str, Any]:
    """
    Convierte el contexto PEP a un payload serializable.

    Args:
        context: Contexto combinado del PEP.

    Returns:
        Diccionario listo para JsonResponse o pruebas por consola.
    """
    requirements = context.pdd.requerimientos

    return {
        "ok": True,
        "project_id": context.project_id,
        "output_filename": context.output_filename,
        "pap": context.pap.model_dump(
            mode="json",
        ),
        "pdd": context.pdd.model_dump(
            mode="json",
        ),
        "warnings": context.warnings,
        "summary": {
            "functional_requirements": len(requirements),
            "insumo_calculation_status": (
                context.pdd.calculo_insumos.estado_calculo
            ),
            "technology_source": "pdd",
        },
    }

def build_pep_output_filename(
    project_id: str | None,
) -> str:
    """
    Construye el nombre del archivo PEP final.

    Args:
        project_id: ID del proyecto.

    Returns:
        Nombre del archivo DOCX.
    """
    safe_project_id = _sanitize_filename_part(
        project_id or "PROYECTO",
    )

    return f"{safe_project_id}_PEP.docx"


def _build_context_warnings(
    *,
    pap_data: PapExtractionData,
    pdd_data: PddAnalysisData,
) -> list[str]:
    """
    Consolida advertencias relevantes del PAP y PDD/FDD.

    Args:
        pap_data: Datos validados del PAP.
        pdd_data: Análisis validado del PDD/FDD.

    Returns:
        Lista de advertencias sin duplicados.
    """
    warnings = [
        *pap_data.advertencias,
        *pdd_data.advertencias,
    ]

    if not pap_data.id_proyecto:
        warnings.append(
            "No se detectó el ID del proyecto en el PAP."
        )

    if not pdd_data.requerimientos:
        warnings.append(
            "No se detectaron requerimientos funcionales principales "
            "para insertar en el PEP."
        )

    calculation = pdd_data.calculo_insumos

    if (
        calculation.estado_calculo == "error_validacion"
        and calculation.mensaje_validacion
    ):
        warnings.append(
            calculation.mensaje_validacion,
        )

    return _remove_duplicate_warnings(warnings)


def _remove_duplicate_warnings(
    warnings: list[str],
) -> list[str]:
    """
    Elimina advertencias duplicadas conservando el orden.

    Args:
        warnings: Lista original de advertencias.

    Returns:
        Advertencias únicas.
    """
    unique_warnings: list[str] = []
    seen: set[str] = set()

    for warning in warnings:
        clean_warning = " ".join(
            (warning or "").split(),
        )

        if not clean_warning:
            continue

        comparison_value = clean_warning.casefold()

        if comparison_value in seen:
            continue

        seen.add(comparison_value)
        unique_warnings.append(clean_warning)

    return unique_warnings


def _clean_optional_text(
    value: str | None,
) -> str | None:
    """
    Limpia un texto opcional.

    Args:
        value: Texto original.

    Returns:
        Texto limpio o None.
    """
    if value is None:
        return None

    clean_value = " ".join(value.split())

    return clean_value or None


def _sanitize_filename_part(
    value: str,
) -> str:
    """
    Limpia una cadena para usarla como parte de un nombre de archivo.

    Args:
        value: Texto original.

    Returns:
        Texto seguro para nombre de archivo.
    """
    clean = value.strip()
    clean = re.sub(r'[<>:"/\\|?*]', "_", clean)
    clean = re.sub(r"\s+", "_", clean)
    clean = clean.strip("._")

    return clean or "PROYECTO"