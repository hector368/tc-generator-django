"""
Módulo de cálculo de métricas a partir del CSV final de ADO.

Este módulo analiza el CSV generado para extraer métricas sobre
requerimientos, test cases y otros indicadores de calidad.

Responsabilidades:
- Contar requerimientos detectados en el CSV
- Contar test cases generados exitosamente
- Identificar requerimientos no testeables
- Detectar requerimientos con límite alcanzado (Limit reached)
- Extraer detalles de objetivos omitidos (lista de bullets)

Nota: No modifica el CSV, solo lo analiza para métricas de UI.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

# -----------------------------
# Patrones y constantes
# -----------------------------

REQ_TC_RE = re.compile(r"^\d{3}$")
ADO_NCOLS = 15

# Índices de columnas (ADO)
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

# Objetivos: compatibilidad con estilo viejo ("Que el bot ...")
# y nuevo (verbo en infinitivo: Validar/Verificar/Registrar/Manejar..., etc.)
# También permite opcional "No ..." al inicio.
_OBJETIVE_START_RE = re.compile(
    r"^\s*(?:no\s+)?(?:que el bot\b|[a-záéíóúñü]+(?:ar|er|ir)\b)",
    re.IGNORECASE,
)


def _looks_like_objetive(text: str) -> bool:
    """
    Heurística para detectar si un texto "parece" un objetivo:

    - Formato anterior: inicia con "Que el bot ..."
    - Formato nuevo: inicia con verbo en infinitivo (termina en ar/er/ir)
    - Permite "No ..." como negación al inicio

    Args:
        text: texto a evaluar

    Returns:
        True si parece objetivo, False si no.
    """
    s = (text or "").strip()
    if not s:
        return False
    return bool(_OBJETIVE_START_RE.match(s))


def _extract_bullets(obj: str) -> list[str]:
    """
    Extrae items tipo bullet en una sola celda.

    Regla:
    - Los objetivos omitidos en Limit reached vienen como lista en Objetive
      con "•" (o caracteres similares).
    - Devuelve items limpios, sin el marcador.

    Args:
        obj: Texto con bullets a extraer

    Returns:
        Lista de items separados por bullets
    """
    s = (obj or "").replace("\r\n", " ")
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if not s:
        return []
    s = s.replace("·", "•").replace("◦", "•")
    return [x.strip() for x in re.split(r"\s*•\s*", s) if x.strip()]


def _tc_num_from_title(title: str) -> int | None:
    """
    Extrae el número de TC (último bloque XXX) desde Title.

    Args:
        title: Título del test case (formato: PROJECT.REQ.TC)

    Returns:
        Número de TC o None si no se puede extraer.
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


def _is_limit_row(row: list[str]) -> tuple[bool, dict[str, Any]]:
    """
    Detecta si la fila es la fila final de Limit reached.

    Nuevo formato (backend actual):
    - Test Step vacío (fila metadata)
    - Expected result == "(Limit reached)"
    - Objetive contiene lista con bullets

    Legado:
    - Step action inicia con "(Limit reached): Generated X of Y identified ..."

    Args:
        row: fila CSV a evaluar

    Returns:
        Tupla (es_limit_row, diccionario_con_detalles)
    """
    step_action = (row[IDX_STEP_ACTION] or "").strip()
    expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()
    obj = (row[IDX_OBJETIVE] or "").strip()
    test_step = (row[IDX_TEST_STEP] or "").strip()
    title = (row[IDX_TITLE] or "").strip()

    tc_num = _tc_num_from_title(title)

    # 1) Nuevo formato: marca EXACTA en Expected result y metadata (Test Step vacío)
    if test_step == "" and expected_result == LIMIT_REACHED_MARK:
        bullets_all = _extract_bullets(obj)
        bullets = [b for b in bullets_all if _looks_like_objetive(b)]
        # Si no detecta objetivos por heurística, usa lo que haya (evita perder info)
        used = bullets if bullets else bullets_all

        return True, {
            "generated_tcs": None,
            "identified_tcs": None,
            "omitted_tcs": len(used),
            "omitted_objectives": used[:50],
        }

    # 2) Legado
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

    # 3) Fallback: si el modelo olvida "(Limit reached)" pero deja lista en Objetive
    # Solo si:
    # - metadata (Test Step vacío)
    # - TC >= 11
    # - Objetive tiene >=2 bullets que parezcan objetivos
    if test_step == "" and (tc_num is not None and tc_num >= 11):
        bullets_all = _extract_bullets(obj)
        bullets = [b for b in bullets_all if _looks_like_objetive(b)]
        if len(bullets) >= 2:
            return True, {
                "generated_tcs": None,
                "identified_tcs": None,
                "omitted_tcs": len(bullets),
                "omitted_objectives": bullets[:50],
            }

    return False, {}


def compute_csv_stats(csv_text: str) -> dict[str, Any]:
    """
    Calcula métricas completas del CSV de test cases.

    Args:
        csv_text: contenido completo del CSV

    Returns:
        Diccionario con métricas:
        - requirements_total
        - test_cases_total
        - requirements_not_testable
        - requirements_not_testable_list
        - requirements_limit_reached_total
        - requirements_limit_reached_list
        - requirements_limit_reached_detail
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
    limit_detail_by_req: dict[str, dict[str, Any]] = {}

    test_cases_total = 0
    current_req: str | None = None

    for row in reader:
        if not row:
            continue

        # Detecta header estándar ADO
        is_header = (
            len(row) >= 2
            and row[0].strip() == "ID"
            and row[1].strip() == "Work Item Type"
        )
        if is_header:
            continue

        # Normaliza a 15 columnas
        if len(row) < ADO_NCOLS:
            row = row + [""] * (ADO_NCOLS - len(row))
        elif len(row) > ADO_NCOLS:
            row = row[:ADO_NCOLS]

        work_item_type = (row[IDX_WORK_ITEM] or "").strip()
        title = (row[IDX_TITLE] or "").strip()
        expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()

        # Detecta requirement desde Title (PROJECT.REQ.TC)
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

        # Cuenta TCs (solo filas metadata de TC; excluye limit row)
        if work_item_type.lower() == "test case":
            if not is_limit:
                test_cases_total += 1

            # Not testable (en metadata row típicamente)
            if current_req and expected_result.startswith(NO_TESTEABLE_PREFIX):
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
