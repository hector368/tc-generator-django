"""
Motor de generación síncrona para el generador automático de Casos de Prueba
(TCs).

Flujo:
1) Extrae texto del archivo (PDF/DOCX).
2) Obtiene Project ID.
3) Recorta la sección TO-BE (2.4).
4) Divide por requerimiento/acción.
5) Llama al LLM por bloque y consolida la salida en CSV ADO.

Este módulo emite eventos (dict) para consumo de UI.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Final, Iterator

from django.conf import settings

from core.ado_csv import (
    dump_ado_rows,
    enforce_structure_and_titles,
    parse_ado_rows,
)
from core.claude_client import call_claude, get_client
from core.context_pack import build_context_pack
from core.extractor import extract_text_from_upload
from core.generator import extract_csv_only
from core.requirements_splitter import (
    extract_project_id,
    slice_to_be_section,
    split_by_requirement,
)
from core.stats import compute_csv_stats

logger = logging.getLogger(__name__)

# Tipos de evento para la UI.
EVENT_META: Final[str] = "meta"
EVENT_PROGRESS: Final[str] = "progress"
EVENT_DONE: Final[str] = "done"
EVENT_ERROR: Final[str] = "error"

# Códigos de error/success para la UI.
ERR_ASSIGNED_TO: Final[str] = "ERR_ASSIGNED_TO"
ERR_NO_PROJECT_ID: Final[str] = "ERR_NO_PROJECT_ID"
ERR_NO_TOBE: Final[str] = "ERR_NO_TOBE"
ERR_NO_REQS: Final[str] = "ERR_NO_REQS"
ERR_ENGINE: Final[str] = "ERR_ENGINE"

OK_GENERATED: Final[str] = "OK_GENERATED"

# Mensajes para la UI.
MSG_ASSIGNED_TO_REQUIRED: Final[str] = "El campo 'Assigned To' es obligatorio."
MSG_NO_PROJECT_ID: Final[str] = (
    "No se encontró el Project ID en el documento (se esperaba 'ID proyecto')."
)
MSG_NO_TOBE: Final[str] = (
    "No fue posible extraer la sección TO-BE (2.4) del documento."
)
MSG_NO_REQS: Final[str] = "No se detectaron requerimientos en la sección TO-BE."
MSG_OK_GENERATED: Final[str] = "Casos de prueba generados correctamente."
MSG_ENGINE_ERROR: Final[str] = (
    "Ocurrió un error durante la generación. Revise los logs del servidor."
)

# Instrucciones de reparación para salidas no conformes al formato ADO CSV.
REPAIR_INSTRUCTIONS: Final[str] = (
    "\n\nREPAIR: Your previous output did not comply with ADO CSV formatting. "
    "Return ONLY CSV rows with EXACTLY 15 columns (14 commas). "
    "Do NOT include headers. Keep EXACTLY 15 columns (14 commas). "
    "If you don't know State/Area Path/Assigned To, leave them empty; "
    "the backend will populate them."
)

# Llaves que la UI espera para métricas de límite (compatibilidad).
STATS_LIMIT_TOTAL: Final[str] = "requirements_limit_reached_total"
STATS_LIMIT_REQS: Final[str] = "requirements_limit_reached_list"
STATS_LIMIT_DETAIL: Final[str] = "requirements_limit_reached_detail"

USAGE_INPUT: Final[str] = "input_tokens"
USAGE_OUTPUT: Final[str] = "output_tokens"

NO_TC_START_DEFAULT: Final[int] = 1


def _sum_usage(
    total: dict[str, int],
    add: dict[str, int] | None,
) -> dict[str, int]:
    """
    Suma el uso de tokens de manera acumulativa retornando un dict nuevo.

    Args:
        total: Acumulado actual.
        add: Incremento a sumar (puede ser None).

    Returns:
        Diccionario con input_tokens y output_tokens.
    """
    add = add or {}

    total_in = int(total.get(USAGE_INPUT, 0))
    total_out = int(total.get(USAGE_OUTPUT, 0))
    add_in = int(add.get(USAGE_INPUT, 0))
    add_out = int(add.get(USAGE_OUTPUT, 0))

    return {
        USAGE_INPUT: total_in + add_in,
        USAGE_OUTPUT: total_out + add_out,
    }


def _build_user_text(
    *,
    project_id: str,
    req_num: int,
    scenario_name: str,
    no_tc_start: int,
    global_context: str,
    input_text: str,
) -> str:
    """
    Construye el contenido del mensaje de usuario para el LLM.

    Nota:
        Mantiene el contrato del prompt (IdProyecto, RequirementNumber, etc.).
    """
    return (
        f"IdProyecto: {project_id}\n"
        f"RequirementNumber: {req_num}\n"
        f"ScenarioName: {scenario_name}\n"
        f"NoTCStart: {no_tc_start}\n"
        f"GlobalContext:\n{global_context}\n"
        f"InputText:\n{input_text}\n"
    )


def _error_event(code: str, message: str) -> dict[str, Any]:
    """Construye un evento de error consistente para la UI."""
    return {"type": EVENT_ERROR, "code": code, "message": message}


def _load_prompt_text() -> str:
    """
    Carga el prompt desde settings y valida que no esté vacío.

    Raises:
        ValueError: Si el archivo existe pero está vacío.
        FileNotFoundError: Si el archivo no existe.
    """
    prompt_path = settings.PROMPT_FILE
    prompt_text = Path(prompt_path).read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise ValueError("El archivo de prompt está vacío.")
    return prompt_text


def _llm_to_rows(
    *,
    client: Any,
    prompt_text: str,
    user_text: str,
) -> tuple[list[list[str]], dict[str, int]]:
    """
    Ejecuta el LLM y devuelve filas ADO parseadas.

    Si el output no es parseable, reintenta una vez anexando
    REPAIR_INSTRUCTIONS.

    Returns:
        Tupla (rows, usage_total).
    """
    raw_out, usage = call_claude(
        client=client,
        model=settings.CLAUDE_MODEL,
        system_prompt=prompt_text,
        user_text=user_text,
        max_tokens=settings.MAX_TOKENS,
    )

    csv_text = extract_csv_only(raw_out).strip()

    try:
        rows = parse_ado_rows(csv_text)
        return rows, usage
    except ValueError:
        user_text_retry = user_text + REPAIR_INSTRUCTIONS

    raw_out2, usage2 = call_claude(
        client=client,
        model=settings.CLAUDE_MODEL,
        system_prompt=prompt_text,
        user_text=user_text_retry,
        max_tokens=settings.MAX_TOKENS,
    )

    csv_text2 = extract_csv_only(raw_out2).strip()
    rows2 = parse_ado_rows(csv_text2)

    base_usage = usage or {USAGE_INPUT: 0, USAGE_OUTPUT: 0}
    usage_total = _sum_usage(base_usage, usage2)
    return rows2, usage_total


def iter_generation_events(
    *,
    filename: str,
    file_bytes: bytes,
    assigned_to: str,
) -> Iterator[dict[str, Any]]:
    """
    Fuente única de verdad para la generación de casos de prueba.

    Eventos emitidos:
    - {"type":"meta","total_blocks":N}
    - {"type":"progress","done":i,"total":N,"req":<int>,"scenario":<str>,
       "secs":<float>}
    - {"type":"done","ok":True,"download_filename":...,"csv_body":...,
       "usage":...,"elapsed":...,"stats":...}
    - {"type":"error","code":"...","message":"..."}
    """
    start_all = time.perf_counter()
    usage_total: dict[str, int] = {USAGE_INPUT: 0, USAGE_OUTPUT: 0}
    all_rows: list[str] = []

    try:
        assigned_to = (assigned_to or "").strip()
        if not assigned_to:
            yield _error_event(ERR_ASSIGNED_TO, MSG_ASSIGNED_TO_REQUIRED)
            return

        prompt_text = _load_prompt_text()
        client = get_client()

        doc_text = extract_text_from_upload(filename, file_bytes)

        project_id = extract_project_id(doc_text)
        if not project_id:
            yield _error_event(ERR_NO_PROJECT_ID, MSG_NO_PROJECT_ID)
            return

        doc_text_to_be = slice_to_be_section(doc_text)
        if not doc_text_to_be.strip():
            yield _error_event(ERR_NO_TOBE, MSG_NO_TOBE)
            return

        context_pack = build_context_pack(doc_text_to_be)

        blocks = split_by_requirement(doc_text_to_be)
        if not blocks:
            yield _error_event(ERR_NO_REQS, MSG_NO_REQS)
            return

        total = len(blocks)
        yield {"type": EVENT_META, "total_blocks": total}

        for idx, block in enumerate(blocks, start=1):
            t0 = time.perf_counter()

            user_text = _build_user_text(
                project_id=project_id,
                req_num=block.requirement_number,
                scenario_name=block.scenario_name,
                no_tc_start=NO_TC_START_DEFAULT,
                global_context=context_pack,
                input_text=block.input_text,
            )

            rows, usage = _llm_to_rows(
                client=client,
                prompt_text=prompt_text,
                user_text=user_text,
            )
            usage_total = _sum_usage(usage_total, usage)

            rows, _ = enforce_structure_and_titles(
                rows,
                project_id=project_id,
                requirement_number=block.requirement_number,
                tc_start=NO_TC_START_DEFAULT,
                state="Design",
                area_path=project_id,
                assigned_to=assigned_to,
            )

            csv_rows_clean = dump_ado_rows(rows).strip()
            if csv_rows_clean:
                all_rows.append(csv_rows_clean)

            secs = time.perf_counter() - t0
            yield {
                "type": EVENT_PROGRESS,
                "done": idx,
                "total": total,
                "req": block.requirement_number,
                "scenario": block.scenario_name,
                "secs": round(secs, 2),
            }

        elapsed = time.perf_counter() - start_all
        csv_body = "\n".join(all_rows).strip()

        stats = compute_csv_stats(csv_body) or {}
        stats.setdefault(STATS_LIMIT_TOTAL, 0)
        stats.setdefault(STATS_LIMIT_REQS, [])
        stats.setdefault(STATS_LIMIT_DETAIL, [])
        stats["project_id"] = project_id
        stats["area_path"] = project_id
        stats["assigned_to"] = assigned_to

        download_filename = f"{Path(filename).stem}_TC.csv"

        yield {
            "type": EVENT_DONE,
            "code": OK_GENERATED,
            "ok": True,
            "message": MSG_OK_GENERATED,
            "download_filename": download_filename,
            "csv_body": csv_body,
            "usage": usage_total,
            "elapsed": round(elapsed, 2),
            "stats": stats,
        }

    except Exception:
        logger.exception("Falló el motor de generación de casos de prueba.")
        yield _error_event(ERR_ENGINE, MSG_ENGINE_ERROR)
