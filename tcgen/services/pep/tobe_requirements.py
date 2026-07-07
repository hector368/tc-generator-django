"""
Servicio para extraer títulos de requerimientos TO-BE desde PDD/FDD.

Este módulo reutiliza la lógica de segmentación existente del generador
de casos de prueba, pero devuelve una estructura simple para llenar
la sección 5.1 del PEP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.extractor import extract_text_from_upload
from core.requirements_segmenter import segment_requirements_flexible
from core.requirements_splitter import RequirementBlock
from core.requirements_splitter import extract_project_id
from tcgen.utils.validators import validate_extracted_text


@dataclass(frozen=True)
class ToBeRequirement:
    """
    Representa un requerimiento TO-BE detectado en el PDD/FDD.

    Attributes:
        number: Número del requerimiento.
        title: Título limpio del requerimiento.
    """

    number: int
    title: str


@dataclass(frozen=True)
class ToBeRequirementsResult:
    """
    Resultado normalizado de extracción de requerimientos TO-BE.

    Attributes:
        project_id: ID de proyecto detectado en el PDD/FDD.
        method: Método de segmentación utilizado.
        requirements: Requerimientos resultantes.
        total_blocks: Total de bloques detectados antes de filtrar.
        selected_requirements: Requerimientos solicitados por el usuario.
        missing_selected: Requerimientos seleccionados que no existían.
    """

    project_id: str | None
    method: str
    requirements: list[ToBeRequirement]
    total_blocks: int
    selected_requirements: list[int] | None
    missing_selected: list[int]


def extract_tobe_requirements(
    *,
    filename: str,
    file_bytes: bytes,
    selected_requirements: list[int] | None = None,
) -> ToBeRequirementsResult:
    """
    Extrae títulos de requerimientos TO-BE desde un PDD/FDD.

    Args:
        filename: Nombre original del archivo PDD/FDD.
        file_bytes: Contenido binario del archivo.
        selected_requirements: Números que el usuario desea incluir.
            Si es None o lista vacía, se incluyen todos.

    Returns:
        Resultado con los requerimientos detectados.

    Raises:
        ValueError: Si no se puede extraer texto o no se detectan
            requerimientos válidos.
    """
    doc_text = extract_text_from_upload(filename, file_bytes)
    validation = validate_extracted_text(doc_text)
    if not validation.ok:
        raise ValueError(validation.message)

    project_id = extract_project_id(doc_text, filename=filename)

    segmentation = segment_requirements_flexible(
        doc_text,
        project_id=(project_id or ""),
    )

    blocks = list(segmentation.blocks or [])
    if not blocks:
        raise ValueError(
            "No se detectaron requerimientos TO-BE en el PDD/FDD."
        )

    filtered_blocks, missing_selected, selected_sorted = (
        _filter_blocks_by_selection(
            blocks,
            selected_requirements=selected_requirements,
        )
    )

    if not filtered_blocks:
        raise ValueError(
            "Los requerimientos seleccionados no existen en el PDD/FDD."
        )

    requirements = [
        _build_requirement_from_block(block)
        for block in filtered_blocks
    ]

    return ToBeRequirementsResult(
        project_id=project_id,
        method=segmentation.method,
        requirements=requirements,
        total_blocks=len(blocks),
        selected_requirements=selected_sorted,
        missing_selected=missing_selected,
    )


def build_tobe_preview_payload(
    result: ToBeRequirementsResult,
) -> dict[str, Any]:
    """
    Convierte el resultado TO-BE a un payload serializable.

    Args:
        result: Resultado de extracción TO-BE.

    Returns:
        Diccionario listo para JsonResponse o pruebas por consola.
    """
    return {
        "ok": True,
        "project_id": result.project_id,
        "method": result.method,
        "total_blocks": result.total_blocks,
        "requirements": [
            {
                "number": requirement.number,
                "title": requirement.title,
            }
            for requirement in result.requirements
        ],
        "selected_requirements": result.selected_requirements,
        "missing_selected": result.missing_selected,
    }


def _build_requirement_from_block(
    block: RequirementBlock,
) -> ToBeRequirement:
    """
    Construye un requerimiento limpio desde un bloque segmentado.

    Args:
        block: Bloque generado por el segmentador existente.

    Returns:
        Requerimiento TO-BE normalizado.
    """
    number = int(block.requirement_number)
    raw_title = (block.scenario_name or "").strip()
    clean_title = _clean_requirement_title(raw_title, number)

    return ToBeRequirement(
        number=number,
        title=clean_title or raw_title or f"Requerimiento {number}",
    )


def _filter_blocks_by_selection(
    blocks: list[RequirementBlock],
    *,
    selected_requirements: list[int] | None,
) -> tuple[list[RequirementBlock], list[int], list[int] | None]:
    """
    Filtra bloques según los requerimientos seleccionados por el usuario.

    Args:
        blocks: Bloques detectados en el PDD/FDD.
        selected_requirements: Números seleccionados por el usuario.

    Returns:
        Tupla con bloques filtrados, números faltantes y selección
        normalizada. Si no hay selección, retorna todos los bloques.
    """
    if not selected_requirements:
        return blocks, [], None

    selected_set = {int(number) for number in selected_requirements}
    selected_sorted = sorted(selected_set)

    available = {
        int(getattr(block, "requirement_number", -1))
        for block in blocks
    }

    missing = sorted(selected_set - available)

    filtered = [
        block
        for block in blocks
        if int(getattr(block, "requirement_number", -1)) in selected_set
    ]

    return filtered, missing, selected_sorted


def _clean_requirement_title(title: str, number: int) -> str:
    """
    Limpia prefijos repetidos del título del requerimiento.

    Ejemplos:
        "1. Ingresar a portal" -> "Ingresar a portal"
        "#1 Ingresar a portal" -> "Ingresar a portal"

    Args:
        title: Título original detectado.
        number: Número del requerimiento.

    Returns:
        Título limpio.
    """
    clean_title = (title or "").strip()
    num = str(number)

    patterns = [
        rf"^\s*#\s*{re.escape(num)}\s+",
        rf"^\s*{re.escape(num)}\s*[.)-]\s+",
        rf"^\s*{re.escape(num)}\s*\.\s*{re.escape(num)}\s*\.\s+",
    ]

    for pattern in patterns:
        clean_title = re.sub(
            pattern,
            "",
            clean_title,
            flags=re.IGNORECASE,
        ).strip()

    return clean_title