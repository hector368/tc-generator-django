"""
Modulo de division de documento TO-BE en bloques por requerimiento.

Este modulo se encarga de extraer la seccion de acciones detalladas
del documento TO-BE, dividirla en bloques individuales por requerimiento,
obtener el ID del proyecto y normalizar el contenido para su
procesamiento posterior.

Responsabilidades:
- Parsing de la estructura del documento TO-BE.
- Deteccion de encabezados de acciones y requerimientos.
- Manejo de formatos PDF y DOCX con tablas y variantes de formato.
- Extraccion de metadatos del proyecto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from pathlib import Path
from collections import Counter

@dataclass(frozen=True)
class RequirementBlock:
    """
    Representa un bloque de requerimiento extraido de la seccion TO-BE.

    Attributes:
        requirement_number: Numero identificador del requerimiento.
        scenario_name: Nombre del escenario o accion asociada.
        input_text: Texto completo del bloque de requerimiento.
    """

    requirement_number: int
    scenario_name: str
    input_text: str


# Patron principal para localizar el inicio de la seccion 2.4.
# Se omite el delimitador de palabra porque algunos documentos
# concatenan el titulo sin espacio previo.
# En archivos DOCX generados desde tablas es frecuente encontrar
# el separador de celda antes del titulo.
_TO_BE_START_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*2\.4\s*(?:\|\s*)?"
    r"Acciones\s+detalladas\s+del\s+proceso\s+TO[-\s]?BE.*$"
)

# Patron de respaldo para cuando el encabezado 2.4 no incluye numeracion.
_TO_BE_START_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*(?:\|\s*)?"
    r"Acciones\s+detalladas\s+del\s+proceso\s+TO[-\s]?BE.*$"
)

# Patron principal para localizar el fin de la seccion en el encabezado 2.5.
_TO_BE_END_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*2\.5\s*(?:\|\s*)?"
    r"Matriz\s+(?:de\s+)?criterios\s+de\s+aceptaci[oó]n.*$"
)

# Patron de respaldo para cuando el encabezado 2.5 no incluye numeracion.
_TO_BE_END_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*(?:\|\s*)?"
    r"Matriz\s+(?:de\s+)?criterios\s+de\s+aceptaci[oó]n.*$"
)

# Patron para detectar marcadores de accion con numeracion simple
# o jerarquica, incluyendo el separador de celda de tablas DOCX.
_ACTION_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?mi)^\s*\d{1,3}(?:\.\d{1,3})*\.?\s*(?:\|\s*)?"
    r"Nombre\s+de\s+la\s+acci[oó]n\b"
)
_TABLE_CELL_SEP: Final[str] = "|"

_LOOKAHEAD_CHARS: Final[int] = 80000


def slice_to_be_section(text: str) -> str:
    """
    Extrae la seccion de acciones TO-BE del texto del documento.

    Busca todas las ocurrencias del encabezado de la seccion y selecciona
    aquella donde el primer marcador de accion aparece mas cercano.
    El recorte finaliza al encontrar el encabezado de la seccion siguiente
    o al llegar al final del texto.

    Args:
        text: Texto completo del documento.

    Returns:
        Texto de la seccion TO-BE extraida, o cadena vacia si no se
        encuentra.
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

    # Si ninguna ocurrencia tiene marcador de accion, se toma la ultima.
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


# Patron para eliminar lineas de metadatos y encabezados de documento
# que no forman parte del contenido de los requerimientos.
_NOISE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(Público|Interno|Código|Tipo|Documento|Versión|"
    r"Fecha de emisión.*|PDD_.*|ID\s*(?:del|de)?\s*proyecto.*)\s*$"
)

# Patron para encabezados donde el numero y el nombre de la accion
# aparecen en la misma linea, con soporte para separador de celda.
_ACTION_SAME_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s*(?:\|\s*)?"
    r"Nombre\s+de\s+la\s+acci[oó]n\s*:\s*(.+?)\s*$"
)

# Patron para encabezados donde el numero ocupa una linea propia
# y el nombre de la accion se encuentra en las lineas siguientes.
_NUM_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(\d{1,3}(?:\.\d{1,3})*)\.?\s*$"
)

_NAME_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*(?:\|\s*)?Nombre\s+de\s+la\s+acci[oó]n\s*:\s*(.*)\s*$"
)

_LOOKAHEAD_LINES: Final[int] = 8


# Normaliza saltos de linea y elimina contenido irrelevante del texto.
def _normalize(text: str) -> list[str]:
    """

    Unifica los distintos formatos de salto de linea, remueve caracteres
    de espacio sin ancho y descarta lineas que corresponden a ruido de
    extraccion. Cuando una linea contiene el separador de celdas de
    tablas DOCX, la divide en partes individuales antes de filtrar.

    Args:
        text: Texto a normalizar.

    Returns:
        Lista de lineas limpias listas para el parseo.
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u200b", "")

    out: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Separar celdas de tablas DOCX para recuperar encabezados
        # y marcadores que pudieran estar concatenados.
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

# Convierte la numeracion de una accion a un entero unico.
def _parse_action_number(num_str: str) -> int:
    """
    Los segmentos numericos se concatenan en orden para evitar colisiones
    entre distintos niveles de la numeracion jerarquica del documento.

    Args:
        num_str: Cadena con el numero de accion, simple o jerarquico.

    Returns:
        Representacion entera del numero de accion, o cero si la entrada
        no contiene digitos validos.
    """
    raw = (num_str or "").strip()
    raw = re.sub(r"[^0-9.]", "", raw).strip(".")
    if not raw:
        return 0

    parts = [p for p in raw.split(".") if p.isdigit()]
    digits = "".join(parts)
    return int(digits) if digits else 0


# Limpia el nombre del escenario eliminando artefactos de extraccion.
def _clean_scenario_name(text: str) -> str:
    """
    Remueve repeticiones del prefijo de encabezado, separadores de
    celda y espacios multiples que pueden quedar al procesar tablas
    de documentos PDF o DOCX.

    Args:
        text: Texto crudo del nombre del escenario.

    Returns:
        Nombre del escenario limpio, o el valor por defecto si el
        resultado queda vacio.
    """
    s = (text or "").strip()
    s = re.split(r"(?i)\bNombre\s+de\s+la\s+acci[oó]n\s*:", s)[0].strip()
    s = s.replace("|", " ").strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s or "InputText"


# Genera una clave estable a partir del numero de accion.
def _action_key(num_str: str) -> str:
    """
    Conserva la estructura jerarquica con puntos para distinguir
    correctamente entre niveles de numeracion.

    Args:
        num_str: Cadena con el numero de accion.

    Returns:
        Clave normalizada que preserva la jerarquia numerica.
    """
    raw = (num_str or "").strip()
    raw = re.sub(r"[^0-9.]", "", raw).strip(".")
    return raw


# Genera una clave de deduplicacion a partir del nombre del escenario.
def _scenario_key(text: str) -> str:
    """
    Normaliza el texto a minusculas, unifica variantes tipograficas de
    comillas y apostrofes, elimina separadores de celda y colapsa
    espacios multiples. La clave se trunca para evitar comparaciones
    excesivamente largas.

    Args:
        text: Texto del nombre del escenario.

    Returns:
        Clave normalizada de hasta 120 caracteres.
    """
    s = (text or "").strip().lower()
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("|", " ")
    s = re.sub(r"\s{2,}", " ", s)
    return s[:120]


# Determina si el documento usa numeración jerárquica en encabezados de acción.
def _allow_hierarchical_headers(lines: list[str]) -> bool:
    """
    Analiza las primeras lineas del texto para contar cuantos encabezados
    tienen numeracion simple y cuantos tienen numeracion jerarquica.
    Cuando los encabezados simples son escasos y existen jerarquicos,
    se habilita su reconocimiento para evitar que sean ignorados.

    Args:
        lines: Lista de lineas normalizadas del documento.

    Returns:
        True si se deben reconocer encabezados jerarquicos,
        False en caso contrario.
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


# Valida que el numero extraido corresponda a un encabezado real.
def _is_valid_header_num(
    num_raw: str,
    *,
    allow_hierarchical: bool
) -> bool:
    """
    Descarta numeros con ceros a la izquierda, que suelen ser artefactos
    de la extraccion PDF. Tambien descarta numeracion jerarquica cuando
    el documento no la utiliza, para evitar falsos positivos.

    Args:
        num_raw: Numero crudo extraido del texto.
        allow_hierarchical: Indica si se permiten numeros jerarquicos.

    Returns:
        True si el numero corresponde a un encabezado valido,
        False en caso contrario.
    """
    s = (num_raw or "").strip()
    s = re.sub(r"[^0-9.]", "", s).strip(".")
    if not s:
        return False

    # Los renglones sueltos con cero a la izquierda son artefactos
    # de extraccion y no representan encabezados reales.
    if s.isdigit() and len(s) > 1 and s.startswith("0"):
        return False

    if "." in s and not allow_hierarchical:
        return False

    return True


# Detecta si la linea indicada corresponde a un encabezado de accion.
def _detect_header(
    lines: list[str],
    i: int,
    *,
    allow_hierarchical: bool,
) -> tuple[str, int, str, int] | None:
    """
    Evalua dos formatos posibles: numero y nombre en la misma linea,
    o numero solo en una linea con el nombre en las lineas siguientes.
    En ambos casos valida el numero antes de construir el resultado.

    Args:
        lines: Lista de lineas normalizadas del documento.
        i: Indice de la linea a evaluar.
        allow_hierarchical: Indica si se permiten encabezados jerarquicos.

    Returns:
        Tupla con la clave de deduplicacion, el numero de requerimiento
        como entero, el nombre del escenario y la cantidad de lineas
        que abarca el encabezado. Retorna None si la linea no es un
        encabezado valido.
    """
    line = lines[i]

    # Formato A: numero y nombre de la accion en la misma linea.
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

    # Formato B: numero solo en una linea, nombre en las siguientes.
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
            # Si aparece otro numero de accion antes de encontrar
            # "Nombre de la acción", el numero actual probablemente
            # pertenece a metadatos del encabezado del PDF, por ejemplo:
            #
            # Versión
            # 10
            # 2.
            # Nombre de la acción: Obtener EC
            #
            # En ese caso, no debemos convertir "10" en requerimiento.
            if _NUM_ONLY_RE.match(lines[j]):
                break
            
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


# Separa la seccion TO-BE en bloques individuales por requerimiento.
def split_by_requirement(text: str) -> list[RequirementBlock]:
    """
    Recorre las lineas normalizadas detectando encabezados de accion
    para delimitar cada bloque. Los encabezados repetidos, habituales
    en saltos de pagina de documentos PDF, se omiten sin crear un nuevo
    bloque. Si no se detecta ningun encabezado, el texto completo se
    devuelve como un unico bloque.

    Args:
        text: Texto de la seccion TO-BE a dividir.

    Returns:
        Lista ordenada de bloques de requerimiento extraidos.
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

            # Encabezado repetido: se omite para no contaminar el bloque
            # activo con contenido duplicado.
            if key in seen_headers:
                i += max(1, int(skip_dup or 1))
                continue

            # Nuevo encabezado: se cierra el bloque anterior y se inicia
            # uno nuevo.
            flush()
            seen_headers.add(key)

            current_req_num = req_num or (len(blocks) + 1)
            current_scenario = scenario or "InputText"
            current_buf = [lines[i]]
            i += 1
            continue

        # Linea de contenido ordinario: se acumula en el bloque activo.
        current_buf.append(lines[i])
        i += 1

    flush()

    if not blocks:
        joined = "\n".join(lines).strip()
        if not joined:
            return []
        return [RequirementBlock(1, "InputText", joined)]

    return blocks


# Segmento de ID: acepta bloques alfabeticos, numericos o alfanumericos.
_ID_SEGMENT_RE = r"(?:[A-Z]{1,10}|\d{1,6}|[A-Z]{1,10}\d{1,10})"

# Patron para reconocer tokens con estructura de ID de proyecto.
_PROJECT_ID_TOKEN_RE = re.compile(
    rf"(?i)(?P<id>[A-Z]{{2,10}}(?:\.{_ID_SEGMENT_RE}){{1,8}})(?=$|[^.])"
)

# Etiquetas reconocidas para localizar el ID del proyecto en el texto.
# El segundo elemento de cada tupla indica la prioridad de la etiqueta:
# menor valor significa mayor confianza en el resultado.
_PROJECT_ID_LABELS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"(?i)\bID\s+del\s+proyecto\b"), 0),
    (re.compile(r"(?i)\bID\s+proyecto\b"), 1),
    (re.compile(r"(?i)\bIdProyecto\b"), 1),
    (re.compile(r"(?i)\bCódigo\s+del\s+proyecto\b"), 2),
    (re.compile(r"(?i)\bClave\s+del\s+proyecto\b"), 3),
    (re.compile(r"(?i)\bProject\s+ID\b"), 2),
    (re.compile(r"(?i)\bProject\s+Code\b"), 3),
]

_PROJECT_ID_LOOKAHEAD_CHARS: Final[int] = 600


# Verifica que el candidato cumpla requisitos de un ID de proyecto válido.
def _is_valid_project_id(candidate: str) -> bool:
    """
    Se exige que el candidato contenga al menos un punto separador y
    al menos un digito en cualquiera de sus segmentos, para descartar
    cadenas alfabeticas puras que no corresponden a identificadores.

    Args:
        candidate: Cadena candidata a ID de proyecto.

    Returns:
        True si el candidato es un ID de proyecto valido,
        False en caso contrario.
    """
    if not candidate:
        return False
    if "." not in candidate:
        return False
    return any(ch.isdigit() for ch in candidate)


# Calcula la puntuacion de un candidato a ID de proyecto.
def _score_project_id(
    candidate: str,
    label_priority: int,
    position: int
) -> tuple[int, int, int]:
    """
    Favorece candidatos con mas segmentos y mayor longitud. La prioridad
    de la etiqueta que lo precede penaliza o bonifica el resultado, y la
    posicion en el texto se usa como criterio de desempate.

    Args:
        candidate: Cadena candidata a ID de proyecto.
        label_priority: Prioridad de la etiqueta que precede al candidato.
        position: Posicion en caracteres donde aparece en el texto.

    Returns:
        Tupla de puntuacion, posicion y longitud para comparacion.
    """
    segments = candidate.count(".") + 1
    length = len(candidate)
    # La prioridad de etiqueta penaliza el puntaje: menor prioridad
    # numerica implica mayor confianza y menos penalizacion.
    score = segments * 100 + length - (label_priority * 10)
    return (score, position, length)


# Intenta extraer el ID del proyecto a partir del nombre del archivo.
def _extract_project_id_from_filename(filename: str) -> str | None:
    """
    Elimina prefijos entre corchetes que algunos sistemas añaden al
    nombre, normaliza separadores y busca un token con estructura de
    ID de proyecto en el nombre base del archivo.

    Args:
        filename: Nombre original del archivo, con o sin ruta.

    Returns:
        ID del proyecto extraido del nombre del archivo, o None si
        no se encuentra un candidato valido.
    """
    if not filename:
        return None

    name = Path(filename).name
    # Elimina prefijos de clasificacion entre corchetes.
    name = re.sub(r"^\[[^\]]+\]\s*", "", name).strip()

    stem = Path(name).stem
    # Normaliza los separadores frecuentes en nombres de archivo.
    normalized = re.sub(r"[_\-\s]+", " ", stem).strip()

    m = _PROJECT_ID_TOKEN_RE.search(normalized)
    if not m:
        return None

    candidate = m.group("id").upper().strip()
    return candidate if _is_valid_project_id(candidate) else None


# Busca el ID del proyecto en todo el texto sin usar etiquetas ni el archivo.
def _extract_project_id_anywhere(text: str) -> str | None:
    """
    Recorre todos los tokens con estructura de ID de proyecto y
    selecciona el de mayor puntuacion. Se emplea como ultimo recurso
    cuando los metodos mas confiables no producen resultado.

    Args:
        text: Texto completo del documento.

    Returns:
        ID del proyecto con mayor puntuacion encontrado, o None si
        no se localiza ningun candidato valido.
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return None

    best_id: str | None = None
    best_score: tuple[int, int, int] | None = None

    for m in _PROJECT_ID_TOKEN_RE.finditer(t):
        candidate = m.group("id").upper().strip()
        if not _is_valid_project_id(candidate):
            continue

        score = _score_project_id(
            candidate,
            label_priority=9,
            position=m.start()
        )
        if best_score is None or score > best_score:
            best_score = score
            best_id = candidate

    return best_id


# Extrae el ID del proyecto con una estrategia escalonada por confianza.
def extract_project_id(text: str, filename: str | None = None) -> str | None:
    """
    El proceso intenta primero localizar etiquetas explicitas en el texto,
    luego extrae el ID del nombre del archivo si esta disponible, despues
    busca el prefijo mas frecuente en los encabezados del documento y
    finalmente realiza una busqueda global como ultimo recurso.

    Args:
        text: Texto completo del documento.
        filename: Nombre original del archivo. Se recomienda proporcionarlo
            para aumentar la precision de la extraccion.

    Returns:
        ID del proyecto encontrado, o None si ninguna estrategia
        produce un resultado valido.
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return None

    # Paso 1: busqueda por etiquetas explicitas en el texto.
    best_id: str | None = None
    best_score: tuple[int, int, int] | None = None

    for label_re, label_priority in _PROJECT_ID_LABELS:
        for m in label_re.finditer(t):
            lookahead_end = m.end() + _PROJECT_ID_LOOKAHEAD_CHARS
            lookahead = t[m.end() : lookahead_end]
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

    if best_id:
        return best_id

    # Paso 2: extraccion a partir del nombre del archivo.
    from_name = _extract_project_id_from_filename(filename or "")
    if from_name:
        return from_name

    # Paso 3: busqueda del prefijo mas frecuente en encabezados del
    # documento.
    header_re = re.compile(
        r"\b(?P<prefix>[A-Z]{2,10}\.\d{3})\.(?P<num>\d{3})\b"
    )
    prefixes = [m.group("prefix").upper() for m in header_re.finditer(t)]
    if prefixes:
        most_common_prefix, count = Counter(prefixes).most_common(1)[0]
        if count >= 3:
            # Se devuelve aunque tenga solo dos segmentos, ya que
            # el validador acepta cualquier formato con punto y digito.
            return most_common_prefix

    # Paso 4: busqueda global como ultimo recurso.
    return _extract_project_id_anywhere(t)