"""
Modulo para manejo de archivos CSV de Azure DevOps (ADO).

Este modulo contiene funciones para parsear, validar y generar archivos CSV
compatibles con la estructura de Test Cases de Azure DevOps.

Responsabilidades:
- Parseo y validacion de estructura CSV de ADO
- Normalizacion de filas y columnas
- Sanitizacion de texto para evitar ruptura de formato CSV
- Aplicacion de reglas de estructura ADO (metadata vs pasos)
"""
from __future__ import annotations

import csv
import io
import re
from typing import Final

# Constantes de formato CSV
BOM: Final[str] = "\ufeff"
CSV_DELIMITER: Final[str] = ","
CSV_QUOTECHAR: Final[str] = '"'
DEFAULT_STATE: Final[str] = "Design"

# Definicion de columnas de Azure DevOps
ADO_COLUMNS: Final[list[str]] = [
    "ID",
    "Work Item Type",
    "Title",
    "Test Step",
    "Step action",
    "Step Expected",
    "Type of test",
    "Priority",
    "Expected result",
    "Objetive",
    "Operating Scenario",
    "Preconditions",
    "State",
    "Area Path",
    "Assigned To",
]

# Constantes derivadas
ADO_NCOLS: Final[int] = len(ADO_COLUMNS)
ADO_CSV_HEADER: Final[str] = CSV_DELIMITER.join(ADO_COLUMNS)

# Marcadores especiales
LIMIT_REACHED_MARK: Final[str] = "(Limit reached)"
LIMIT_REACHED_MARKERS: Final[tuple[str, ...]] = (
    "(Limit reached)",
    "(Limit reached):",
)
BULLET_SEP: Final[str] = " • "

# Valores permitidos/esperados (defensivo ante salidas del LLM)
TYPE_TEST_ALIASES: Final[frozenset[str]] = frozenset(
    {"functional", "no functional"}
)
PRIORITY_ALLOWED: Final[frozenset[str]] = frozenset({"1", "2", "3"})


def _one_line_with_bullets(text: str) -> str:
    """
    Convierte saltos de linea en separador inline para no romper el CSV.

    Args:
        text: Texto con posibles saltos de linea

    Returns:
        Texto en una sola linea con bullets como separadores
    """
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return ""
    s = re.sub(r"\n+", BULLET_SEP, s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _sanitize_omitted_objectives(text: str) -> str:
    """
    Normaliza la lista de objetivos omitidos para la fila final Limit reached.

    Reglas:
    - Una sola linea (sin saltos de linea)
    - Cada objetivo separado por bullet
    - La celda completa debe iniciar con bullet

    Args:
        text: Texto con lista de objetivos

    Returns:
        Texto normalizado con formato de bullets
    """
    s = _one_line_with_bullets(text)
    if not s:
        return ""

    # Normaliza posibles variantes de bullet
    s = s.replace("·", "•").replace("◦", "•")

    # Divide por bullets existentes
    items = [x.strip() for x in re.split(r"\s*•\s*", s) if x.strip()]
    if not items:
        return ""

    return BULLET_SEP + BULLET_SEP.join(items)


def ensure_csv_header(csv_body: str) -> str:
    """
    Asegura que el encabezado del CSV de Azure DevOps exista en la primera
    linea.

    Si el cuerpo esta vacio, retorna unicamente el encabezado.
    Si el primer renglon ya corresponde al encabezado, retorna el cuerpo
    intacto.

    Args:
        csv_body: Contenido CSV potencialmente sin encabezado

    Returns:
        CSV con encabezado garantizado
    """
    body = (csv_body or "").lstrip(BOM).strip()
    if not body:
        return ADO_CSV_HEADER

    first_line = body.splitlines()[0].strip()

    # Tolerancia a espacios accidentales despues de comas
    normalized_first = first_line.replace(" ", "")
    normalized_header = ADO_CSV_HEADER.replace(" ", "")
    if normalized_first == normalized_header:
        return body

    return f"{ADO_CSV_HEADER}\n{body}"


def is_header_row(row: list[str]) -> bool:
    """
    Determina si la fila corresponde al encabezado de ADO.

    Args:
        row: Lista de valores de una fila CSV

    Returns:
        True si la fila es el encabezado, False en caso contrario
    """
    if len(row) < 2:
        return False

    # Tolerancia ligera a espacios accidentales en el header
    c0 = (row[0] or "").strip().replace(" ", "")
    c1 = (row[1] or "").strip().replace(" ", "")
    return c0 == "ID" and c1 == "WorkItemType"


def _ensure_ncols(row: list[str]) -> list[str]:
    """
    Valida y normaliza que una fila tenga el numero de columnas esperado
    por ADO.

    Reglas:
    - Si trae columnas extra vacias (trailing comma), recorta
    - Si trae menos columnas, rellena con strings vacios
    - Si trae columnas extra con contenido, levanta ValueError

    Args:
        row: Lista de valores de una fila CSV

    Returns:
        Lista normalizada con exactamente ADO_NCOLS elementos

    Raises:
        ValueError: Si la fila tiene columnas extra con contenido
    """
    cleaned = [(cell or "").strip() for cell in row]

    if len(cleaned) > ADO_NCOLS:
        extras = cleaned[ADO_NCOLS:]
        if all(x == "" for x in extras):
            cleaned = cleaned[:ADO_NCOLS]
        else:
            raise ValueError(
                f"Fila CSV invalida: se esperaban {ADO_NCOLS} columnas, "
                f"se recibieron {len(cleaned)}. "
                f"Extra(s) con contenido={extras!r}. Fila={cleaned!r}"
            )

    if len(cleaned) < ADO_NCOLS:
        cleaned.extend([""] * (ADO_NCOLS - len(cleaned)))

    return cleaned


def parse_ado_rows(csv_text: str) -> list[list[str]]:
    """
    Parsea texto CSV a filas ADO (sin encabezado).

    Omite filas vacias y omite la fila de encabezado si viene incluida.

    Args:
        csv_text: Texto en formato CSV

    Returns:
        Lista de filas parseadas y normalizadas
    """
    txt = (csv_text or "").lstrip(BOM).strip()
    if not txt:
        return []

    reader = csv.reader(
        io.StringIO(txt),
        delimiter=CSV_DELIMITER,
        quotechar=CSV_QUOTECHAR,
    )

    rows: list[list[str]] = []
    for row in reader:
        if not row:
            continue
        if is_header_row(row):
            continue
        rows.append(_ensure_ncols(row))

    return rows


def dump_ado_rows(rows: list[list[str]]) -> str:
    """
    Reescribe CSV con comillas correctas para evitar comas accidentales.

    Retorna el CSV sin encabezado y sin lineas finales extra.

    Args:
        rows: Lista de filas a serializar

    Returns:
        Texto CSV formateado

    Raises:
        ValueError: Si alguna fila no tiene el numero correcto de columnas
    """
    buf = io.StringIO()
    writer = csv.writer(
        buf,
        delimiter=CSV_DELIMITER,
        quotechar=CSV_QUOTECHAR,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )

    for row in rows:
        if len(row) != ADO_NCOLS:
            raise ValueError(
                f"Fila interna invalida: se esperaban {ADO_NCOLS} columnas."
            )
        writer.writerow(row)

    return buf.getvalue().strip()


def is_tc_start(row: list[str]) -> bool:
    """
    Determina si la fila debe considerarse como inicio de un Test Case.

    Logica:
    - Inicia si 'Work Item Type' es 'Test Case' (case-insensitive).
    - Inicia si existe un 'Title' no vacio Y no es una fila de paso
      (Test Step vacio). Esto evita que pasos mal formateados se
      interpreten como un nuevo Test Case.

    Args:
        row: Fila CSV a evaluar

    Returns:
        True si es inicio de Test Case, False en caso contrario
    """
    work_item = (row[1] or "").strip().lower()
    title = (row[2] or "").strip()
    test_step = (row[3] or "").strip()
    return work_item == "test case" or (bool(title) and not test_step)


def _sanitize_preconditions(text: str) -> str:
    """
    Sanitiza precondiciones para evitar saltos de linea que rompan el CSV.

    Args:
        text: Texto de precondiciones

    Returns:
        Texto en una sola linea con bullets como separadores
    """
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s:
        return ""
    s = re.sub(r"\n+", BULLET_SEP, s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def enforce_structure_and_titles(
    rows: list[list[str]],
    *,
    project_id: str,
    requirement_number: int,
    tc_start: int,
    state: str = DEFAULT_STATE,
    area_path: str | None = None,
    assigned_to: str = "",
) -> tuple[list[list[str]], int]:
    """
    Normaliza filas a una estructura ADO consistente.

    Reglas aplicadas:
    - Fila metadata del TC: sin Test Step/Step action/Step Expected
    - EXCEPCION: fila final Limit reached tiene Expected result especial
    - Filas siguientes: pasos 1..N (solo Step action/expected)
    - Fuerza State/Area Path/Assigned To en metadata
    - Sanitiza Preconditions para que no rompa el CSV
    - Repara corrimientos comunes de columnas en metadata (salidas del LLM)

    Args:
        rows: Filas parseadas a normalizar
        project_id: ID del proyecto
        requirement_number: Numero de requerimiento
        tc_start: Indice inicial de numeracion de TCs
        state: Estado del Test Case (por defecto "Design")
        area_path: Ruta de area en ADO
        assigned_to: Usuario asignado

    Returns:
        Tupla con (filas_normalizadas, cantidad_de_test_cases)
    """
    # Indices de columnas ADO
    IDX_ID = 0
    IDX_WORK_ITEM = 1
    IDX_TITLE = 2
    IDX_TEST_STEP = 3
    IDX_STEP_ACTION = 4
    IDX_STEP_EXPECTED = 5
    IDX_TYPE_TEST = 6
    IDX_PRIORITY = 7
    IDX_EXPECTED_RESULT = 8
    IDX_OBJETIVE = 9
    IDX_OPER_SCENARIO = 10
    IDX_PRECONDITIONS = 11
    IDX_STATE = 12
    IDX_AREA = 13
    IDX_ASSIGNED = 14

    def _count_omitted_objectives(obj_text: str) -> int:
        """
        Heuristica: el Limit row nuevo trae una lista en Objetive con
        bullets. Si hay >=2 bullets y al menos uno inicia con "Que el bot",
        lo tratamos como Limit row.
        """
        s = (obj_text or "").strip()
        if not s:
            return 0
        s = s.replace("·", "•").replace("◦", "•")
        items = [x.strip() for x in re.split(r"\s*•\s*", s) if x.strip()]
        if len(items) < 2:
            return 0
        if not any(x.lower().startswith("que el bot") for x in items):
            return 0
        return len(items)

    out: list[list[str]] = []
    tc_idx = tc_start - 1
    step_idx = 0
    tcs_count = 0

    has_open_tc = False
    limit_emitted = False

    forced_state = (state or DEFAULT_STATE).strip() or DEFAULT_STATE
    forced_area = (area_path or project_id or "").strip()
    forced_assigned = (assigned_to or "").strip()

    for row in rows:
        row = _ensure_ncols(row)

        # Si ya emitimos la fila final "Limit reached", ignoramos todo
        # lo que venga despues.
        if limit_emitted:
            continue

        if is_tc_start(row):
            tc_idx += 1
            tcs_count += 1
            has_open_tc = True
            step_idx = 0

            first_step_action = (row[IDX_STEP_ACTION] or "").strip()
            first_step_expected = (row[IDX_STEP_EXPECTED] or "").strip()
            expected_result = (row[IDX_EXPECTED_RESULT] or "").strip()

            # Detecta limit row por marcador explicito.
            is_limit_marker = any(
                first_step_action.startswith(m)
                for m in LIMIT_REACHED_MARKERS
            ) or any(
                expected_result.startswith(m)
                for m in LIMIT_REACHED_MARKERS
            )

            omitted_count = _count_omitted_objectives(row[IDX_OBJETIVE])
            is_limit_like = tc_idx >= 11 and omitted_count > 0

            is_limit_row = is_limit_marker or is_limit_like

            # Metadata base
            row[IDX_ID] = ""
            row[IDX_WORK_ITEM] = "Test Case"
            title = f"{project_id}.{requirement_number:03d}.{tc_idx:03d}"
            row[IDX_TITLE] = title
            row[IDX_TEST_STEP] = ""

            # Sanitiza Preconditions (una sola linea)
            preconditions_text = row[IDX_PRECONDITIONS]
            row[IDX_PRECONDITIONS] = _sanitize_preconditions(preconditions_text)

            # Reparacion defensiva: corrimiento de columnas en metadata.
            #
            # Caso observado: el LLM duplica "Functional" en Priority y desplaza:
            # Priority(1/2/3) -> Expected result -> Objetive -> Operating Scenario
            prio_raw = (row[IDX_PRIORITY] or "").strip().lower()
            expected_maybe_priority = (row[IDX_EXPECTED_RESULT] or "").strip()
            objetive_maybe_expected = (row[IDX_OBJETIVE] or "").strip()
            scenario_maybe_objetive = (row[IDX_OPER_SCENARIO] or "").strip()
            precond_maybe_scenario = (row[IDX_PRECONDITIONS] or "").strip()

            is_shift_pattern = (
                prio_raw in TYPE_TEST_ALIASES
                and expected_maybe_priority in PRIORITY_ALLOWED
                and bool(objetive_maybe_expected)
                and scenario_maybe_objetive.lower().startswith("que el bot")
            )

            if is_shift_pattern:
                row[IDX_PRIORITY] = expected_maybe_priority
                row[IDX_EXPECTED_RESULT] = objetive_maybe_expected
                row[IDX_OBJETIVE] = scenario_maybe_objetive
                row[IDX_OPER_SCENARIO] = precond_maybe_scenario
                row[IDX_PRECONDITIONS] = ""

            # Default tipo de prueba si viene vacio
            if not (row[IDX_TYPE_TEST] or "").strip():
                row[IDX_TYPE_TEST] = "Functional"

            # En metadata, Priority debe ser numerico.
            prio_final = (row[IDX_PRIORITY] or "").strip()
            if prio_final and prio_final not in PRIORITY_ALLOWED:
                row[IDX_PRIORITY] = "1"

            # Fuerza State/Area/Assigned en metadata
            row[IDX_STATE] = forced_state
            row[IDX_AREA] = forced_area
            row[IDX_ASSIGNED] = forced_assigned

            if is_limit_row:
                # Fila FINAL Limit reached: una sola fila, sin pasos.
                row[IDX_TEST_STEP] = ""

                # Limpia columnas de pasos (por consistencia).
                row[IDX_STEP_ACTION] = ""
                row[IDX_STEP_EXPECTED] = ""

                # Marca ahora en Expected result (columna correcta).
                row[IDX_EXPECTED_RESULT] = LIMIT_REACHED_MARK

                # La lista va en Objetive, una sola linea con bullets.
                objetive_text = row[IDX_OBJETIVE]
                row[IDX_OBJETIVE] = _sanitize_omitted_objectives(objetive_text)

                out.append(row)

                limit_emitted = True
                has_open_tc = False
                step_idx = 0
                continue

            # TC normal: metadata NO lleva pasos.
            row[IDX_STEP_ACTION] = ""
            row[IDX_STEP_EXPECTED] = ""
            out.append(row)

            # Si el modelo metio Step action en metadata, lo movemos a Step 1.
            if first_step_action:
                step_idx = 1
                step_row = [""] * ADO_NCOLS
                step_row[IDX_TEST_STEP] = "1"
                action_text = _one_line_with_bullets(first_step_action)
                step_row[IDX_STEP_ACTION] = action_text
                if first_step_expected:
                    expected_text = _one_line_with_bullets(first_step_expected)
                    step_row[IDX_STEP_EXPECTED] = expected_text
                out.append(step_row)

            continue

        # Steps fuera de un TC abierto: se ignoran.
        if not has_open_tc:
            continue

        step_action = (row[IDX_STEP_ACTION] or "").strip()
        step_expected = (row[IDX_STEP_EXPECTED] or "").strip()

        if not step_action:
            continue

        step_idx += 1
        step_row = [""] * ADO_NCOLS
        step_row[IDX_TEST_STEP] = str(step_idx)
        step_row[IDX_STEP_ACTION] = _one_line_with_bullets(step_action)
        if step_expected:
            expected_text = _one_line_with_bullets(step_expected)
            step_row[IDX_STEP_EXPECTED] = expected_text

        out.append(step_row)

    return out, tcs_count
