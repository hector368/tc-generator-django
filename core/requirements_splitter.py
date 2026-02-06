"""
Modulo de division de documento TO-BE en bloques por requerimiento.

Este modulo se encarga de:
- Extraer la seccion 2.4 (Acciones detalladas TO-BE) del documento
- Dividir la seccion en bloques individuales por requerimiento
- Extraer el ID del proyecto desde el documento
- Normalizar y limpiar el contenido para procesamiento posterior

Responsabilidades:
- Parsing de estructura de documento TO-BE
- Deteccion de encabezados de acciones/requerimientos
- Manejo de formatos PDF y DOCX (con tablas y variantes)
- Extraccion de metadatos del proyecto
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RequirementBlock:
    """
    Representa un bloque de requerimiento extraido de la seccion TO-BE.

    Attributes:
        requirement_number: Numero del requerimiento
        scenario_name: Nombre del escenario/accion
        input_text: Texto completo del bloque de requerimiento
    """

    requirement_number: int
    scenario_name: str
    input_text: str


# Patrones para extraccion de seccion TO-BE
# Nota: En DOCX (sobre todo cuando viene en tablas), es comun ver
# separadores " | ".
# Ademas, algunos documentos concatenan "TO-BE2.4" (sin espacio),
# por eso NO se usa \b.
_TO_BE_START_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*2\.4\s*(?:\|\s*)?"
    r"Acciones\s+detalladas\s+del\s+proceso\s+TO[-\s]?BE.*$"
)
_TO_BE_START_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*(?:\|\s*)?"
    r"Acciones\s+detalladas\s+del\s+proceso\s+TO[-\s]?BE.*$"
)

_TO_BE_END_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*2\.5\s*(?:\|\s*)?"
    r"Matriz\s+(?:de\s+)?criterios\s+de\s+aceptaci[oó]n.*$"
)
_TO_BE_END_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*(?:\|\s*)?"
    r"Matriz\s+(?:de\s+)?criterios\s+de\s+aceptaci[oó]n.*$"
)

# Marcador de accion: soporta numeracion jerarquica (1.1.1.) y
# separador "|".
_ACTION_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*\d{1,3}(?:\.\d{1,3})*\.?\s*(?:\|\s*)?"
    r"Nombre\s+de\s+la\s+acci[oó]n\b"
)
_TABLE_CELL_SEP: Final[str] = "|"

_LOOKAHEAD_CHARS: Final[int] = 80000


def slice_to_be_section(text: str) -> str:
    """
    Extrae la seccion 2.4 (acciones TO-BE) sin confundirse con el indice.

    Estrategia:
    - Se buscan todas las ocurrencias del encabezado 2.4
    - Se elige aquella en la que el primer marcador de accion aparece
      mas cerca
    - Se recorta hasta el encabezado 2.5 (o un marcador alterno)

    Args:
        text: Texto completo del documento

    Returns:
        Texto de la seccion TO-BE extraida
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return ""

    starts = list(_TO_BE_START_RE.finditer(normalized))
    if not starts:
        starts = list(_TO_BE_START_FALLBACK_RE.finditer(normalized))

    if not starts:
        return ""

    best_start: re.Match[str] | None = None
    best_dist: int | None = None

    for match in starts:
        lookahead_end = match.end() + _LOOKAHEAD_CHARS
        lookahead = normalized[match.end() : lookahead_end]
        action_match = _ACTION_MARKER_RE.search(lookahead)
        if not action_match:
            continue

        dist = action_match.start()
        if best_start is None or best_dist is None or dist < best_dist:
            best_start = match
            best_dist = dist

    # Si ninguna ocurrencia tiene marcador de accion, se toma la ultima
    start_match = best_start or starts[-1]
    start_pos = start_match.end()

    end_match = _TO_BE_END_RE.search(normalized, pos=start_pos)
    if end_match is None:
        end_match = _TO_BE_END_FALLBACK_RE.search(
            normalized,
            pos=start_pos
        )

    end_pos = end_match.start() if end_match else len(normalized)

    if end_pos <= start_pos:
        return normalized[start_pos:].strip()

    return normalized[start_pos:end_pos].strip()


# Patrones para separacion por requerimiento
_NOISE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(Público|Interno|Código|Tipo|Documento|Versión|"
    r"Fecha de emisión.*|PDD_.*|ID\s*(?:del|de)?\s*proyecto.*)\s*$"
)

# Caso A: "12. Nombre de la accion: Escenario"
# (tambien soporta "1.1.1. | Nombre ...").
_ACTION_SAME_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s*(?:\|\s*)?"
    r"Nombre\s+de\s+la\s+acci[oó]n\s*:\s*(.+?)\s*$"
)

# Caso B: "12." en una linea (o "1.1.1.") y el nombre en las siguientes
_NUM_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s*$"
)

_NAME_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(?:\|\s*)?Nombre\s+de\s+la\s+acci[oó]n\s*:\s*(.*)\s*$"
)

_LOOKAHEAD_LINES: Final[int] = 8


def _normalize(text: str) -> list[str]:
    """
    Normaliza saltos de linea y filtra ruido para facilitar el parseo.

    Args:
        text: Texto a normalizar

    Returns:
        Lista de lineas normalizadas y filtradas
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u200b", "")

    out: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # En DOCX tablas: separar por celdas para recuperar
        # encabezados y marcadores
        parts = [
            p.strip() for p in stripped.split(_TABLE_CELL_SEP) if p.strip()
        ]
        for part in parts:
            if _NOISE_RE.match(part):
                continue
            if part in {"◦", "•"}:
                continue
            out.append(part)

    return out


def _parse_action_number(num_str: str) -> int:
    """
    Convierte numeracion tipo "12" o "1.1.1" a entero.

    Regla:
    - Se eliminan puntos y se concatenan segmentos numericos:
      "1.1.1" -> 111
    - Esto evita colisiones cuando el documento viene con numeracion
      jerarquica

    Args:
        num_str: String con numero de accion (puede ser jerarquico)

    Returns:
        Numero de accion como entero
    """
    raw = (num_str or "").strip()
    raw = re.sub(r"[^0-9.]", "", raw).strip(".")
    if not raw:
        return 0

    parts = [p for p in raw.split(".") if p.isdigit()]
    digits = "".join(parts)
    return int(digits) if digits else 0


def _clean_scenario_name(text: str) -> str:
    """
    Limpia el nombre del escenario para evitar basura por extraccion.

    Ejemplos comunes:
    - Texto concatenado con "Nombre de la accion:" repetido
    - Separadores '|' de tablas

    Args:
        text: Texto del nombre del escenario

    Returns:
        Nombre del escenario limpio
    """
    s = (text or "").strip()
    s = re.split(r"(?i)\bNombre\s+de\s+la\s+acci[oó]n\s*:", s)[0].strip()
    s = s.replace("|", " ").strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s or "InputText"


def _action_key(num_str: str) -> str:
    """
    Key estable: conserva jerarquia con puntos (ej. '33.1').

    Args:
        num_str: String con numero de accion

    Returns:
        Clave normalizada para la accion
    """
    raw = (num_str or "").strip()
    raw = re.sub(r"[^0-9.]", "", raw).strip(".")
    return raw


def _scenario_key(text: str) -> str:
    """
    Normaliza el titulo para deduplicacion y tolerancia a
    comillas/espacios.

    Args:
        text: Texto del escenario

    Returns:
        Clave normalizada para deduplicacion (primeros 120 chars)
    """
    s = (text or "").strip().lower()
    s = s.replace(""", '"').replace(""", '"')
    s = s.replace("'", "'").replace("'", "'")
    s = s.replace("|", " ")
    s = re.sub(r"\s{2,}", " ", s)
    return s[:120]


def _allow_hierarchical_headers(lines: list[str]) -> bool:
    """
    Decide si permitimos numeracion jerarquica (33.1, 1.1.1) como
    encabezado.

    Regla practica:
    - Si detectamos suficientes candidatos simples (sin puntos internos),
      asumimos que el documento es 1..N y NO permitimos jerarquicos
    - Si casi no hay simples pero si hay jerarquicos, entonces si
      los permitimos

    Args:
        lines: Lista de lineas del documento

    Returns:
        True si se permiten encabezados jerarquicos, False en caso
        contrario
    """
    simple = 0
    hierarchical = 0

    for line in lines[:2000]:
        m = _ACTION_SAME_LINE_RE.match(line) or _NUM_ONLY_RE.match(line)
        if not m:
            continue

        num = (m.group(1) or "").strip().strip(".")
        if not num:
            continue

        if "." in num:
            hierarchical += 1
        else:
            simple += 1

    return simple < 3 and hierarchical > 0


def _is_valid_header_num(
    num_raw: str,
    *,
    allow_hierarchical: bool
) -> bool:
    """
    Valida el 'num_raw' para evitar falsos positivos por extraccion PDF.

    Reglas:
    - Rechaza ceros a la izquierda (ej. '05', '003') porque suelen
      ser artefactos
    - Rechaza jerarquicos si allow_hierarchical=False (ej. '33.1')

    Args:
        num_raw: Numero crudo extraido
        allow_hierarchical: Si se permiten numeros jerarquicos

    Returns:
        True si es un numero de header valido, False en caso contrario
    """
    s = (num_raw or "").strip()
    s = re.sub(r"[^0-9.]", "", s).strip(".")
    if not s:
        return False

    # PDFs suelen meter '05' como renglon suelto -> NO es header real
    if s.isdigit() and len(s) > 1 and s.startswith("0"):
        return False

    if "." in s and not allow_hierarchical:
        return False

    return True


def _detect_header(
    lines: list[str],
    i: int,
    *,
    allow_hierarchical: bool,
) -> tuple[str, int, str, int] | None:
    """
    Detecta encabezado en lines[i].

    Args:
        lines: Lista de lineas del documento
        i: Indice de la linea a evaluar
        allow_hierarchical: Si se permiten encabezados jerarquicos

    Returns:
        Tupla (dedupe_key, req_num_int, scenario_name,
        skip_lines_for_duplicate) o None si no es encabezado
    """
    line = lines[i]

    # Caso A: "N(.?) Nombre de la accion: <titulo>"
    m1 = _ACTION_SAME_LINE_RE.match(line)
    if m1:
        num_raw = m1.group(1)
        is_valid = _is_valid_header_num(
            num_raw,
            allow_hierarchical=allow_hierarchical
        )
        if not is_valid:
            return None

        scenario = _clean_scenario_name(m1.group(2))
        key = f"{_action_key(num_raw)}|{_scenario_key(scenario)}"
        req_num = _parse_action_number(num_raw)
        return key, req_num, scenario, 1

    # Caso B: "N" o "N." en una linea y el nombre en las siguientes
    m2 = _NUM_ONLY_RE.match(line)
    if m2:
        num_raw = m2.group(1)
        is_valid = _is_valid_header_num(
            num_raw,
            allow_hierarchical=allow_hierarchical
        )
        if not is_valid:
            return None

        req_num = _parse_action_number(num_raw)

        max_j = min(i + 1 + _LOOKAHEAD_LINES, len(lines))
        for j in range(i + 1, max_j):
            mn = _NAME_LINE_RE.match(lines[j])
            if not mn:
                continue

            tail = (mn.group(1) or "").strip()
            if tail:
                scenario = _clean_scenario_name(tail)
                key_value = _action_key(num_raw)
                scenario_key_value = _scenario_key(scenario)
                key = f"{key_value}|{scenario_key_value}"
                return key, req_num, scenario, (j - i + 1)

            has_next_line = j + 1 < len(lines) and lines[j + 1].strip()
            if has_next_line:
                scenario = _clean_scenario_name(lines[j + 1])
                key_value = _action_key(num_raw)
                scenario_key_value = _scenario_key(scenario)
                key = f"{key_value}|{scenario_key_value}"
                return key, req_num, scenario, (j - i + 2)

    return None


def split_by_requirement(text: str) -> list[RequirementBlock]:
    """
    Separa la seccion TO-BE en bloques usando encabezados de accion.

    Mejoras:
    - Soporta "N." y "N" (punto opcional)
    - Evita falsos positivos por extraccion PDF:
      * ignora numeros con cero a la izquierda (ej. '05')
      * ignora jerarquicos (33.1) cuando el documento usa 1..N
    - Deduplica encabezados repetidos (salto de pagina / repeticion
      en PDF)

    Args:
        text: Texto de la seccion TO-BE

    Returns:
        Lista de bloques de requerimiento
    """
    lines = _normalize(text)
    if not lines:
        return []

    allow_hierarchical = _allow_hierarchical_headers(lines)

    blocks: list[RequirementBlock] = []
    seen_headers: set[str] = set()

    current_req_num: int | None = None
    current_scenario: str | None = None
    current_buf: list[str] = []

    def flush() -> None:
        nonlocal current_req_num, current_scenario, current_buf
        if current_req_num is None:
            return
        chunk = "\n".join(current_buf).strip()
        if not chunk:
            return
        blocks.append(
            RequirementBlock(
                requirement_number=int(current_req_num),
                scenario_name=(current_scenario or "InputText").strip(),
                input_text=chunk,
            )
        )

    i = 0
    n = len(lines)

    while i < n:
        header = _detect_header(
            lines,
            i,
            allow_hierarchical=allow_hierarchical
        )
        if header:
            key, req_num, scenario, skip_dup = header

            # Encabezado repetido -> no partimos, y lo saltamos
            # para no ensuciar el bloque
            if key in seen_headers:
                i += max(1, int(skip_dup or 1))
                continue

            # Nuevo bloque real
            flush()
            seen_headers.add(key)

            current_req_num = req_num or (len(blocks) + 1)
            current_scenario = scenario or "InputText"
            current_buf = [lines[i]]
            i += 1
            continue

        # Linea normal
        current_buf.append(lines[i])
        i += 1

    flush()

    if not blocks:
        joined = "\n".join(lines).strip()
        if not joined:
            return []
        return [RequirementBlock(1, "InputText", joined)]

    return blocks


# Extraccion de Project ID
_ID_SEGMENT_RE = r"(?:[A-Z]{1,10}|\d{1,6}|[A-Z]{1,10}\d{1,10})"
_PROJECT_ID_TOKEN_RE = re.compile(
    rf"(?i)(?P<id>[A-Z]{{2,10}}(?:\.{_ID_SEGMENT_RE}){{1,8}})(?=$|[^.])"
)

# Etiquetas (se prioriza 'ID del proyecto')
_PROJECT_ID_LABELS = [
    # (regex, prioridad) -> menor prioridad = mejor
    (re.compile(r"(?i)\bID\s+del\s+proyecto\b"), 0),
    (re.compile(r"(?i)\bID\s+proyecto\b"), 1),
]

_PROJECT_ID_LOOKAHEAD_CHARS = 600


def _is_valid_project_id(candidate: str) -> bool:
    """
    Valida un candidato de IdProyecto evitando falsos positivos.

    Reglas minimas:
    - Debe contener al menos un punto
    - Debe contener al menos un digito en algun segmento

    Args:
        candidate: String candidato a ID de proyecto

    Returns:
        True si es valido, False en caso contrario
    """
    if not candidate:
        return False
    if "." not in candidate:
        return False
    return any(ch.isdigit() for ch in candidate)


def _score_project_id(
    candidate: str,
    label_priority: int,
    position: int
) -> tuple[int, int, int]:
    """
    Puntua un IdProyecto candidato.

    Criterios:
    - Mas segmentos y mas longitud = mejor
    - Etiqueta 'ID del proyecto' gana
    - Aparicion mas tarde en el texto gana en desempate

    Args:
        candidate: String candidato
        label_priority: Prioridad de la etiqueta encontrada
        position: Posicion en el texto donde aparece

    Returns:
        Tupla (score, position, length) para comparacion
    """
    segments = candidate.count(".") + 1
    length = len(candidate)
    # (segmentos, longitud, posicion) y penalizamos por prioridad
    # del label
    score = segments * 100 + length - (label_priority * 10)
    return (score, position, length)


def extract_project_id(text: str) -> str | None:
    """
    Extrae el IdProyecto completo desde el documento.

    Si existen multiples IDs, elige el mas probable:
    - Prioriza 'ID del proyecto' sobre 'ID proyecto'
    - Prioriza IDs mas especificos (mas segmentos/mas largo)
    - En empate, toma el que aparece mas adelante (cuerpo > portada)

    Args:
        text: Texto completo del documento

    Returns:
        ID del proyecto o None si no se encuentra
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return None

    best_id: str | None = None
    best_score: tuple[int, int, int] | None = None

    for label_re, label_priority in _PROJECT_ID_LABELS:
        for m in label_re.finditer(t):
            lookahead_end = m.end() + _PROJECT_ID_LOOKAHEAD_CHARS
            lookahead = t[m.end() : lookahead_end]
            # Tolerancia por extraccion en tablas (DOCX/PDF)
            lookahead = lookahead.replace("|", " ").replace("\n", " ")

            id_match = _PROJECT_ID_TOKEN_RE.search(lookahead)
            if not id_match:
                continue

            candidate = id_match.group("id").upper().strip()
            if not _is_valid_project_id(candidate):
                continue

            score = _score_project_id(candidate, label_priority, m.start())
            if best_score is None or score > best_score:
                best_score = score
                best_id = candidate

    return best_id
