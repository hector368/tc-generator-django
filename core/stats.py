"""
Modulo de calculo de metricas a partir del CSV final de ADO.

Este modulo analiza el CSV generado para extraer indicadores sobre
requerimientos, casos de prueba y condiciones especiales detectadas
durante la generacion. No modifica el contenido del CSV.
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

# Patron para verificar que un texto inicia con verbo en infinitivo
# o con la expresion negativa equivalente, indicando que es un objetivo.
_OBJETIVE_START_RE = re.compile(
    r"^\s*(?:no\s+)?(?:que el bot\b|[a-záéíóúñü]+(?:ar|er|ir)\b)",
    re.IGNORECASE,
)


# Determina si un texto tiene la forma de un objetivo de caso de prueba.
def _looks_like_objetive(text: str) -> bool:
    """
    Aplica una heuristica basada en el inicio del texto: se considera
    objetivo cuando comienza con un verbo en infinitivo o con su
    equivalente negativo.

    Args:
        text: Texto a evaluar.

    Returns:
        True si el texto parece un objetivo, False en caso contrario.
    """
    s = (text or "").strip()
    if not s:
        return False
    return bool(_OBJETIVE_START_RE.match(s))


# Extrae los items de una celda que contiene una lista con bullets.
def _extract_bullets(obj: str) -> list[str]:
    """
    Normaliza los distintos caracteres de bullet que pueden aparecer
    segun el formato del documento y devuelve cada item limpio como
    elemento de la lista resultante.

    Args:
        obj: Texto de la celda con los items separados por bullets.

    Returns:
        Lista de items limpios extraidos del texto.
    """
    s = (obj or "").replace("\r\n", " ")
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if not s:
        return []
    s = s.replace("·", "•").replace("◦", "•")
    return [x.strip() for x in re.split(r"\s*•\s*", s) if x.strip()]


# Extrae el numero de caso de prueba a partir del titulo de la fila.
def _tc_num_from_title(title: str) -> int | None:
    """
    El numero corresponde al ultimo segmento del titulo cuando tiene
    exactamente tres digitos. Si el titulo no sigue la estructura
    esperada, retorna None.

    Args:
        title: Texto del titulo del caso de prueba.

    Returns:
        Numero de caso de prueba como entero, o None si no se puede
        extraer.
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


# Detecta filas de CSV tipo "límite alcanzado" y extrae detalles si aplica.
def _is_limit_row(row: list[str]) -> tuple[bool, dict[str, Any]]:
    """
    Evalua tres variantes en orden de prioridad: el formato actual del
    backend con marca exacta en el resultado esperado, el formato legado
    con la marca en el campo de accion, y un fallback para casos donde
    el modelo omite la marca pero deja la lista de objetivos.

    Args:
        row: Fila del CSV normalizada a quince columnas.

    Returns:
        Tupla con un booleano que indica si es fila de limite y un
        diccionario con los detalles extraidos. El diccionario esta
        vacio cuando no se detecta la condicion.
    """
    step_action = (row[IDX_STEP_ACTION] or "").strip()
    expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()
    obj = (row[IDX_OBJETIVE] or "").strip()
    test_step = (row[IDX_TEST_STEP] or "").strip()
    title = (row[IDX_TITLE] or "").strip()

    tc_num = _tc_num_from_title(title)

    # Formato actual: marca exacta en resultado esperado y fila de
    # metadata con Test Step vacio.
    if test_step == "" and expected_result == LIMIT_REACHED_MARK:
        bullets_all = _extract_bullets(obj)
        bullets = [b for b in bullets_all if _looks_like_objetive(b)]
        # Cuando la heuristica no identifica objetivos se usan todos
        # los bullets para no perder informacion.
        used = bullets if bullets else bullets_all

        return True, {
            "generated_tcs": None,
            "identified_tcs": None,
            "omitted_tcs": len(used),
            "omitted_objectives": used[:50],
        }

    # Formato legado: la marca aparece al inicio del campo de accion.
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

    # Fallback para casos donde el modelo omite la marca de limite pero
    # deja la lista de objetivos en la celda. Se activa unicamente en
    # filas de metadata con numero de TC alto y suficientes bullets.
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


# Calcula las metricas completas del CSV de casos de prueba.
def compute_csv_stats(csv_text: str) -> dict[str, Any]:
    """
    Recorre todas las filas del CSV identificando requerimientos,
    casos de prueba, condiciones no testeables y limites alcanzados.
    Normaliza cada fila a quince columnas antes de procesarla y
    omite la fila de encabezado estandar de ADO si esta presente.

    Args:
        csv_text: Contenido completo del CSV a analizar.

    Returns:
        Diccionario con los conteos e identificadores de requerimientos
        totales, casos de prueba generados, requerimientos no testeables
        y requerimientos con limite alcanzado junto con su detalle.
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

        # Omite la fila de encabezado estandar de ADO.
        is_header = (
            len(row) >= 2
            and row[0].strip() == "ID"
            and row[1].strip() == "Work Item Type"
        )
        if is_header:
            continue

        # Normaliza la fila a quince columnas antes de acceder a indices.
        if len(row) < ADO_NCOLS:
            row = row + [""] * (ADO_NCOLS - len(row))
        elif len(row) > ADO_NCOLS:
            row = row[:ADO_NCOLS]

        work_item_type = (row[IDX_WORK_ITEM] or "").strip()
        title = (row[IDX_TITLE] or "").strip()
        expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()

        # Extrae el numero de requerimiento desde el titulo cuando
        # los dos ultimos segmentos tienen tres digitos.
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

        # Registra el requerimiento como limite alcanzado cuando la
        # fila cumple los criterios de deteccion.
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

        # Cuenta solo filas de metadata de caso de prueba que no sean
        # de limite alcanzado.
        if work_item_type.lower() == "test case":
            if not is_limit:
                test_cases_total += 1

            # Marca el requerimiento como no testeable cuando el campo
            # de resultado esperado contiene el prefijo correspondiente.
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