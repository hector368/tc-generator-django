"""
Motor de generacion de casos de prueba a partir de documentos PDD y FDD.

Este modulo extrae el texto del archivo, identifica el ID del proyecto,
segmenta los requerimientos y llama al LLM por cada bloque para consolidar
la salida en formato CSV compatible con Azure DevOps.

Los resultados se emiten como eventos para consumo de la interfaz de usuario.
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
from core.requirements_segmenter import segment_requirements_flexible
from core.requirements_splitter import extract_project_id
from core.stats import compute_csv_stats

logger = logging.getLogger(__name__)

# Tipos de evento emitidos hacia la interfaz de usuario.
EVENT_META: Final[str] = "meta"
EVENT_PROGRESS: Final[str] = "progress"
EVENT_DONE: Final[str] = "done"
EVENT_ERROR: Final[str] = "error"

# Codigos de resultado para la interfaz de usuario.
ERR_ASSIGNED_TO: Final[str] = "ERR_ASSIGNED_TO"
ERR_NO_PROJECT_ID: Final[str] = "ERR_NO_PROJECT_ID"
ERR_NO_REQS: Final[str] = "ERR_NO_REQS"
ERR_NO_SELECTED_REQS: Final[str] = "ERR_NO_SELECTED_REQS"
ERR_ENGINE: Final[str] = "ERR_ENGINE"

OK_GENERATED: Final[str] = "OK_GENERATED"

# Mensajes de respuesta para la interfaz de usuario.
MSG_ASSIGNED_TO_REQUIRED: Final[str] = (
    "El campo 'Assigned To' es obligatorio."
)
MSG_NO_PROJECT_ID: Final[str] = (
    "No se encontró el Project ID en el documento o en el nombre del archivo."
)
MSG_NO_REQS: Final[str] = (
    "No fue posible segmentar requerimientos "
    "(TO-BE / FDD / Process Steps)."
)
MSG_NO_SELECTED_REQS: Final[str] = (
    "No se encontraron requerimientos para la selección indicada."
)
MSG_OK_GENERATED: Final[str] = "Casos de prueba generados correctamente."
MSG_ENGINE_ERROR: Final[str] = (
    "Ocurrió un error durante la generación. Revise los logs del servidor."
)

# Instrucciones de reparacion para salidas que no cumplen el formato
# ADO CSV requerido.
REPAIR_INSTRUCTIONS: Final[str] = (
    "\n\nREPAIR: Your previous output did not comply with ADO CSV formatting. "
    "Return ONLY CSV rows with EXACTLY 15 columns (14 commas). "
    "Do NOT include headers. Keep EXACTLY 15 columns (14 commas). "
    "If you don't know State/Area Path/Assigned To, leave them empty; "
    "the backend will populate them."
)

# Claves de estadisticas de limite esperadas por la interfaz de usuario.
STATS_LIMIT_TOTAL: Final[str] = "requirements_limit_reached_total"
STATS_LIMIT_REQS: Final[str] = "requirements_limit_reached_list"
STATS_LIMIT_DETAIL: Final[str] = "requirements_limit_reached_detail"

USAGE_INPUT: Final[str] = "input_tokens"
USAGE_OUTPUT: Final[str] = "output_tokens"

NO_TC_START_DEFAULT: Final[int] = 1


# Acumula el conteo de tokens de dos diccionarios de uso.
def _sum_usage(
    total: dict[str, int],
    add: dict[str, int] | None,
) -> dict[str, int]:
    """
    Args:
        total: Acumulado actual de tokens de entrada y salida.
        add: Valores a sumar al acumulado. Si es None se trata como
            vacio.

    Returns:
        Nuevo diccionario con la suma de tokens de entrada y salida.
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


# Construye el mensaje al LLM respetando el contrato de campos del prompt.
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
    Args:
        project_id: Identificador del proyecto extraido del documento.
        req_num: Numero del requerimiento a procesar.
        scenario_name: Nombre del escenario asociado al requerimiento.
        no_tc_start: Numero inicial para la numeracion de casos de
            prueba.
        global_context: Contexto global del documento.
        input_text: Texto del bloque de requerimiento a procesar.

    Returns:
        Cadena con el mensaje de usuario formateado para el LLM.
    """
    return (
        f"IdProyecto: {project_id}\n"
        f"RequirementNumber: {req_num}\n"
        f"ScenarioName: {scenario_name}\n"
        f"NoTCStart: {no_tc_start}\n"
        f"GlobalContext:\n{global_context}\n"
        f"InputText:\n{input_text}\n"
    )


# Construye un evento de error con estructura consistente para la UI.
def _error_event(
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Args:
        code: Codigo de error identificador del tipo de fallo.
        message: Mensaje legible para el usuario.
        extra: Campos adicionales opcionales a incluir en el evento.

    Returns:
        Diccionario con el evento de error listo para emitir.
    """
    evt: dict[str, Any] = {
        "type": EVENT_ERROR,
        "code": code,
        "message": message,
    }
    if extra:
        evt.update(extra)
    return evt


# arga el prompt desde settings y valida que la ruta no esté vacía.
def _load_prompt_text() -> str:
    """
    Raises:
        ValueError: Si el archivo existe pero no contiene texto util.
        FileNotFoundError: Si el archivo no existe en la ruta indicada.

    Returns:
        Texto del prompt listo para enviarse al LLM.
    """
    prompt_path = settings.PROMPT_FILE
    prompt_text = Path(prompt_path).read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise ValueError("El archivo de prompt está vacío.")
    return prompt_text


# Invoca el LLM y convierte la respuesta en filas ADO parseadas.
def _llm_to_rows(
    *,
    client: Any,
    prompt_text: str,
    user_text: str,
) -> tuple[list[list[str]], dict[str, int]]:
    """
    Si la primera respuesta no es parseable como CSV ADO valido, realiza
    un segundo intento adjuntando instrucciones de reparacion al mensaje
    de usuario original.

    Args:
        client: Cliente del LLM inicializado.
        prompt_text: Texto del prompt de sistema.
        user_text: Mensaje de usuario con el contexto del requerimiento.

    Returns:
        Tupla con la lista de filas ADO parseadas y el diccionario de
        uso de tokens acumulado del intento o intentos realizados.
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


# Filtra los bloques según los requerimientos seleccionados por el usuario.
def _filter_blocks_by_selection(
    blocks: list[Any],
    selected_requirements: list[int] | None,
) -> tuple[list[Any], list[int], list[int] | None]:
    """
    Si no se proporciona seleccion, retorna todos los bloques sin
    modificacion. Cuando se aplica filtro, calcula cuales de los
    numeros solicitados no se encontraron en los bloques disponibles.

    Args:
        blocks: Lista completa de bloques de requerimiento segmentados.
        selected_requirements: Numeros de requerimiento solicitados por
            el usuario. Si es None o vacio, no se aplica filtro.

    Returns:
        Tupla con los bloques filtrados, la lista de numeros solicitados
        que no se encontraron y la lista ordenada de seleccionados o
        None si no se aplico filtro.
    """
    if not selected_requirements:
        return blocks, [], None

    selected_set = {int(n) for n in selected_requirements}
    selected_sorted = sorted(selected_set)

    available = {int(getattr(b, "requirement_number", -1)) for b in blocks}
    missing = sorted(selected_set - available)

    filtered = [
        b for b in blocks
        if int(getattr(b, "requirement_number", -1)) in selected_set
    ]

    return filtered, missing, selected_sorted


# Fuente unica de verdad para la generacion de casos de prueba.
def iter_generation_events(
    *,
    filename: str,
    file_bytes: bytes,
    assigned_to: str,
    selected_requirements: list[int] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Ejecuta el flujo completo de extraccion, segmentacion y generacion
    emitiendo eventos de progreso para la interfaz de usuario. Ante
    cualquier condicion de error emite un evento de error y detiene la
    iteracion. Si ocurre una excepcion no controlada, la registra en el
    log y emite un evento de error generico.

    Args:
        filename: Nombre del archivo original subido.
        file_bytes: Contenido binario del archivo.
        assigned_to: Usuario al que se asignaran los casos de prueba
            generados.
        selected_requirements: Numeros de requerimiento a procesar. Si
            es None se procesan todos los disponibles.

    Yields:
        Eventos de tipo meta, progress, done o error segun el estado
        de la generacion.
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

        # Se pasa el nombre del archivo como respaldo para la extraccion
        # del ID cuando el documento no lo contiene explicitamente.
        project_id = extract_project_id(doc_text, filename=filename)
        if not project_id:
            yield _error_event(ERR_NO_PROJECT_ID, MSG_NO_PROJECT_ID)
            return

        seg = segment_requirements_flexible(doc_text, project_id=project_id)
        blocks = seg.blocks
        if not blocks:
            yield _error_event(ERR_NO_REQS, MSG_NO_REQS)
            return

        # Se aplica el filtro de seleccion solo cuando el usuario
        # especifico requerimientos concretos.
        blocks, missing_selected, selected_sorted = (
            _filter_blocks_by_selection(
                blocks,
                selected_requirements=selected_requirements,
            )
        )
        if not blocks:
            yield _error_event(
                ERR_NO_SELECTED_REQS,
                MSG_NO_SELECTED_REQS,
                extra={
                    "missing_selected": missing_selected,
                    "selected_requirements": selected_sorted,
                },
            )
            return

        context_pack = build_context_pack(seg.context_text)

        total = len(blocks)
        yield {
            "type": EVENT_META,
            "total_blocks": total,
            "segmentation_method": seg.method,
            "selected_requirements": selected_sorted,
            "missing_selected": missing_selected,
        }

        for idx, block in enumerate(blocks, start=1):
            t0 = time.perf_counter()

            req_num = int(block.requirement_number)
            scenario = (block.scenario_name or "").strip()

            user_text = _build_user_text(
                project_id=project_id,
                req_num=req_num,
                scenario_name=scenario,
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
                requirement_number=req_num,
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
                "req": req_num,
                "scenario": scenario,
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