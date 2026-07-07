"""
Construcción del contexto combinado para generar el PEP.

Este módulo une la información extraída desde el PAP con los
requerimientos TO-BE extraídos desde el PDD/FDD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tcgen.services.pep.pap_schema import PapExtractionData
from tcgen.services.pep.tobe_requirements import ToBeRequirementsResult


@dataclass(frozen=True)
class PepContext:
    """
    Contexto completo requerido para llenar la plantilla PEP.

    Attributes:
        project_id: ID final usado para el PEP.
        output_filename: Nombre sugerido para el archivo DOCX.
        pap: Datos extraídos desde el PAP.
        tobe: Requerimientos extraídos desde PDD/FDD.
        warnings: Advertencias consolidadas.
    """

    project_id: str | None
    output_filename: str
    pap: PapExtractionData
    tobe: ToBeRequirementsResult
    warnings: list[str]


def build_pep_context(
    *,
    pap_data: PapExtractionData,
    tobe_data: ToBeRequirementsResult,
) -> PepContext:
    """
    Construye el contexto combinado para el PEP.

    Args:
        pap_data: Información validada del PAP.
        tobe_data: Requerimientos TO-BE detectados del PDD/FDD.

    Returns:
        Contexto combinado listo para previsualizar o generar el PEP.
    """
    warnings = _build_context_warnings(
        pap_data=pap_data,
        tobe_data=tobe_data,
    )

    project_id = _resolve_project_id(
        pap_project_id=pap_data.id_proyecto,
        pdd_project_id=tobe_data.project_id,
    )

    return PepContext(
        project_id=project_id,
        output_filename=build_pep_output_filename(project_id),
        pap=pap_data,
        tobe=tobe_data,
        warnings=warnings,
    )


def build_pep_context_payload(context: PepContext) -> dict[str, Any]:
    """
    Convierte el contexto PEP a un payload serializable.

    Args:
        context: Contexto combinado del PEP.

    Returns:
        Diccionario listo para JsonResponse o pruebas por consola.
    """
    return {
        "ok": True,
        "project_id": context.project_id,
        "output_filename": context.output_filename,
        "pap": context.pap.model_dump(mode="json"),
        "tobe": {
            "project_id": context.tobe.project_id,
            "method": context.tobe.method,
            "total_blocks": context.tobe.total_blocks,
            "selected_requirements": context.tobe.selected_requirements,
            "missing_selected": context.tobe.missing_selected,
            "requirements": [
                {
                    "number": requirement.number,
                    "title": requirement.title,
                }
                for requirement in context.tobe.requirements
            ],
        },
        "warnings": context.warnings,
        "summary": {
            "roles_detected": _count_detected_roles(context.pap),
            "software_items": len(context.pap.requisitos_software.items),
            "hardware_items": len(context.pap.requisitos_hardware.items),
            "tobe_requirements": len(context.tobe.requirements),
        },
    }


def build_pep_output_filename(project_id: str | None) -> str:
    """
    Construye el nombre del archivo PEP final.

    Args:
        project_id: ID del proyecto.

    Returns:
        Nombre del archivo DOCX.
    """
    safe_project_id = _sanitize_filename_part(project_id or "PROYECTO")
    return f"{safe_project_id}_PEP.docx"


def _resolve_project_id(
    *,
    pap_project_id: str | None,
    pdd_project_id: str | None,
) -> str | None:
    """
    Resuelve el ID principal del proyecto.

    Se prioriza el ID del PAP porque el PEP se llena principalmente
    desde la planeación administrativa.

    Args:
        pap_project_id: ID encontrado en PAP.
        pdd_project_id: ID encontrado en PDD/FDD.

    Returns:
        ID final del proyecto.
    """
    pap_id = (pap_project_id or "").strip()
    pdd_id = (pdd_project_id or "").strip()

    if pap_id:
        return pap_id

    if pdd_id:
        return pdd_id

    return None


def _build_context_warnings(
    *,
    pap_data: PapExtractionData,
    tobe_data: ToBeRequirementsResult,
) -> list[str]:
    """
    Consolida advertencias relevantes para generar el PEP.

    Args:
        pap_data: Datos del PAP.
        tobe_data: Datos del PDD/FDD.

    Returns:
        Lista de advertencias.
    """
    warnings = list(pap_data.advertencias)

    pap_project_id = (pap_data.id_proyecto or "").strip()
    pdd_project_id = (tobe_data.project_id or "").strip()

    if pap_project_id and pdd_project_id:
        if pap_project_id.lower() != pdd_project_id.lower():
            warnings.append(
                "El ID del proyecto detectado en el PAP no coincide "
                "con el ID detectado en el PDD/FDD."
            )

    if not pap_project_id and not pdd_project_id:
        warnings.append(
            "No se detectó ID de proyecto en PAP ni en PDD/FDD."
        )

    if tobe_data.missing_selected:
        missing = ", ".join(str(num) for num in tobe_data.missing_selected)
        warnings.append(
            "Algunos requerimientos seleccionados no fueron encontrados "
            f"en el PDD/FDD: {missing}."
        )

    if not tobe_data.requirements:
        warnings.append(
            "No hay requerimientos TO-BE seleccionados para insertar "
            "en el PEP."
        )

    return warnings


def _count_detected_roles(pap_data: PapExtractionData) -> int:
    """
    Cuenta cuántos roles tienen al menos un responsable asignado.

    Args:
        pap_data: Datos del PAP.

    Returns:
        Número de roles detectados.
    """
    roles = pap_data.roles.model_dump(mode="python")
    return sum(1 for value in roles.values() if value)


def _sanitize_filename_part(value: str) -> str:
    """
    Limpia una cadena para usarla como parte de un nombre de archivo.

    Args:
        value: Texto original.

    Returns:
        Texto seguro para nombre de archivo.
    """
    clean = (value or "").strip()
    clean = re.sub(r'[<>:"/\\|?*]', "_", clean)
    clean = re.sub(r"\s+", "_", clean)
    clean = clean.strip("._")

    return clean or "PROYECTO"