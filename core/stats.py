"""
Modulo de calculo de metricas a partir del CSV final de ADO.

Este modulo analiza el CSV generado para extraer metricas sobre
requerimientos, test cases, y otros indicadores de calidad.

Responsabilidades:
- Contar requerimientos detectados en el CSV
- Contar test cases generados exitosamente
- Identificar requerimientos no testeables
- Detectar requerimientos con limite alcanzado
- Extraer detalles de objetivos omitidos

Nota: No modifica el CSV, solo lo analiza para metricas de UI.
"""
from __future__ import annotations

import csv
import io
import re

# Patrones de expresiones regulares
REQ_TC_RE = re.compile(r"^\d{3}$")

# Constantes de estructura ADO
ADO_NCOLS = 15

# Indices de columnas (ADO)
IDX_WORK_ITEM = 1
IDX_TITLE = 2
IDX_TEST_STEP = 3
IDX_STEP_ACTION = 4
IDX_EXPECTED_RESULT = 8
IDX_OBJETIVE = 9

# Marcadores especiales
NO_TESTEABLE_PREFIX = "(No testeable):"
LIMIT_REACHED_MARK = "(Limit reached)"

# Marcadores de formato legado
LIMIT_REACHED_LEGACY_PREFIX = "(Limit reached):"
LIMIT_REACHED_LEGACY_RE = re.compile(
    r"\(Limit reached\):\s*Generated\s+(\d+)\s+of\s+(\d+)\s+identified",
    re.IGNORECASE,
)


def _count_bullets(obj: str) -> list[str]:
    """
    Extrae bullets en una sola celda.

    Regla: cada objetivo inicia con bullet (o caracter similar).

    Args:
        obj: Texto con bullets a extraer

    Returns:
        Lista de items separados por bullets
    """
    s = (obj or "").replace("\r\n", " ")
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if not s:
        return []
    parts = [x.strip() for x in re.split(r"\s*•\s*", s) if x.strip()]
    return parts


def _tc_num_from_title(title: str) -> int | None:
    """
    Extrae el numero de TC (ultimo bloque XXX) desde Title.

    Args:
        title: Titulo del test case (formato: PROJECT.REQ.TC)

    Returns:
        Numero de TC o None si no se puede extraer
    """
    if not title:
        return None
    parts = [p.strip() for p in title.split(".") if p.strip()]
    if not parts:
        return None
    last = parts[-1]
    if not REQ_TC_RE.match(last):
        return None
    try:
        return int(last)
    except ValueError:
        return None


def _is_limit_row(row: list[str]) -> tuple[bool, dict]:
    """
    Detecta si la fila es la fila final de Limit reached.

    Nuevo formato (actual backend):
    - Test Step vacio (metadata)
    - Expected result == "(Limit reached)"
    - Objetive contiene lista con bullets

    Legado:
    - Step action inicia con "(Limit reached): Generated X of Y ..."

    Args:
        row: Fila CSV a evaluar

    Returns:
        Tupla (es_limit_row, diccionario_con_detalles)
    """
    step_action = (row[IDX_STEP_ACTION] or "").strip()
    expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()
    obj = (row[IDX_OBJETIVE] or "").strip()
    test_step = (row[IDX_TEST_STEP] or "").strip()
    title = (row[IDX_TITLE] or "").strip()

    tc_num = _tc_num_from_title(title)

    # Nuevo formato: marca EXACTA en Expected result
    # (fila metadata => Test Step vacio)
    if test_step == "" and expected_result == LIMIT_REACHED_MARK:
        bullets = _count_bullets(obj)
        bullets = [b for b in bullets if b.lower().startswith("que el bot")]
        return True, {
            "generated_tcs": None,
            "identified_tcs": None,
            "omitted_tcs": len(bullets),
            "omitted_objectives": bullets[:50],
        }

    # Legado: "(Limit reached): Generated X of Y identified ..."
    if step_action.startswith(LIMIT_REACHED_LEGACY_PREFIX):
        m = LIMIT_REACHED_LEGACY_RE.search(step_action)
        if m:
            generated = int(m.group(1))
            identified = int(m.group(2))
            omitted = max(0, identified - generated)
        else:
            generated = None
            identified = None
            omitted = None
        return True, {
            "generated_tcs": generated,
            "identified_tcs": identified,
            "omitted_tcs": omitted,
            "omitted_objectives": None,
        }

    # Fallback (si el modelo olvida poner "(Limit reached)" en
    # Expected result)
    # Solo si:
    # - fila metadata (Test Step vacio)
    # - TC >= 11
    # - Objetive tiene >=2 bullets "Que el bot ..."
    if test_step == "" and (tc_num is not None and tc_num >= 11):
        bullets = _count_bullets(obj)
        bullets = [b for b in bullets if b.lower().startswith("que el bot")]
        if len(bullets) >= 2:
            return True, {
                "generated_tcs": None,
                "identified_tcs": None,
                "omitted_tcs": len(bullets),
                "omitted_objectives": bullets[:50],
            }

    return False, {}


def compute_csv_stats(csv_text: str) -> dict:
    """
    Calcula metricas completas del CSV de test cases.

    Args:
        csv_text: Contenido completo del CSV

    Returns:
        Diccionario con metricas:
        - requirements_total: Total de requerimientos detectados
        - test_cases_total: Total de TCs generados
        - requirements_not_testable: Cantidad no testeables
        - requirements_not_testable_list: Lista de reqs no testeables
        - requirements_limit_reached_total: Cantidad con limite
        - requirements_limit_reached_list: Lista de reqs con limite
        - requirements_limit_reached_detail: Detalles de limites
    """
    txt = (csv_text or "").lstrip("\ufeff").strip()
    if not txt:
        return {
            "requirements_total": 0,
            "test_cases_total": 0,
            "requirements_not_testable": 0,
            "requirements_not_testable_list": [],
            "requirements_limit_reached_total": 0,
            "requirements_limit_reached_list": [],
            "requirements_limit_reached_detail": [],
        }

    reader = csv.reader(io.StringIO(txt), delimiter=",", quotechar='"')

    requirements: set[str] = set()
    not_testable: set[str] = set()
    limit_reached: set[str] = set()
    limit_detail_by_req: dict[str, dict] = {}

    test_cases_total = 0
    current_req: str | None = None

    for row in reader:
        if not row:
            continue

        # Detecta header
        is_header = (
            len(row) >= 2
            and row[0].strip() == "ID"
            and row[1].strip() == "Work Item Type"
        )
        if is_header:
            continue

        # Normaliza a 15 columnas sin romper metricas
        if len(row) < ADO_NCOLS:
            row = row + [""] * (ADO_NCOLS - len(row))
        elif len(row) > ADO_NCOLS:
            row = row[:ADO_NCOLS]

        work_item_type = (row[IDX_WORK_ITEM] or "").strip()
        title = (row[IDX_TITLE] or "").strip()
        expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()

        # Detecta requirement desde Title
        if title:
            parts = [p.strip() for p in title.split(".") if p.strip()]
            has_req_and_tc = (
                len(parts) >= 2
                and REQ_TC_RE.match(parts[-2])
                and REQ_TC_RE.match(parts[-1])
            )
            if has_req_and_tc:
                current_req = parts[-2]

        if current_req:
            requirements.add(current_req)

        # Detecta limit row
        is_limit, info = _is_limit_row(row)
        if is_limit and current_req:
            limit_reached.add(current_req)
            limit_detail_by_req[current_req] = {
                "requirement": current_req,
                "generated_tcs": info.get("generated_tcs"),
                "identified_tcs": info.get("identified_tcs"),
                "omitted_tcs": info.get("omitted_tcs"),
                "omitted_objectives": info.get("omitted_objectives"),
            }

        # Cuenta TCs (solo filas metadata de TC; EXCLUYE limit row
        # para "TCs created")
        if work_item_type.lower() == "test case":
            if not is_limit:
                test_cases_total += 1

            # Not testable (en metadata row tipicamente)
            is_not_testable = expected_result.startswith(
                NO_TESTEABLE_PREFIX
            )
            if current_req and is_not_testable:
                not_testable.add(current_req)

    not_testable_list = sorted(not_testable, key=lambda x: int(x))
    limit_list = sorted(limit_reached, key=lambda x: int(x))

    detail_list = [
        limit_detail_by_req[r] for r in limit_list if r in limit_detail_by_req
    ]

    return {
        "requirements_total": len(requirements),
        "test_cases_total": test_cases_total,
        "requirements_not_testable": len(not_testable),
        "requirements_not_testable_list": not_testable_list,
        "requirements_limit_reached_total": len(limit_reached),
        "requirements_limit_reached_list": limit_list,
        "requirements_limit_reached_detail": detail_list,
    }
