"""
Modulo de segmentacion flexible de requerimientos para documentos PDD y FDD.

Este modulo aplica distintas estrategias en orden de confiabilidad para
identificar y extraer bloques de requerimientos, adaptandose a las
variaciones estructurales que presentan los distintos formatos de documento.

Responsabilidades:
- Seleccion automatica de la estrategia de segmentacion adecuada.
- Segmentacion por estructura TO-BE, por IDs de requerimiento,
  por pasos con prefijo hash y por pasos numerados.
- Prevencion de falsos positivos originados en indices y tablas de
  contenido del documento.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Final

from core.requirements_splitter import (
    RequirementBlock,
    slice_to_be_section,
    split_by_requirement,
)


@dataclass(frozen=True)
class SegmentationResult:
    """
    Encapsula el resultado de la segmentacion de un documento.

    Attributes:
        blocks: Lista de bloques de requerimiento extraidos.
        context_text: Fragmento del documento utilizado como contexto.
        method: Identificador de la estrategia aplicada para segmentar.
    """

    blocks: list[RequirementBlock]
    context_text: str
    method: str


# Patron para verificar que una cadena contiene al menos una letra,
# incluyendo caracteres con tilde y enye.
_HAS_LETTERS_RE: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]"
)

# Patron para localizar IDs de requerimiento con estructura jerarquica
# de prefijo alfabetico y segmentos numericos separados por puntos.
_REQ_ID_ANYWHERE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<prefix>[A-Z]{2,10}\.\d{3})\.(?P<num>\d{3})\b"
)

# Patron para pasos con prefijo hash seguido de numero y titulo.
_HASH_STEP_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^\s*#\s*(?P<num>\d{1,3})\s+(?P<title>.+?)\s*$"
)

# Patron para identificar encabezados de seccion de pasos de proceso,
# con o sin numeracion de seccion previa.
_PROCESS_STEPS_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:\d+\.\d+(?:\.\d+)?\.?\s+)?Process\s+steps\b.*$"
)

# Patron para detectar el encabezado que marca el fin del bloque de
# pasos de proceso en documentos PDD.
_PROCESS_STEPS_END_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*7\.\s*Data\s+storage\s+locations\b.*$"
)

# Patron para pasos numerados con titulo en la misma linea, con
# distintos separadores entre el numero y el texto.
_STEP_INLINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<num>\d{1,3})\s*(?:[.)-]\s+|\s+)(?P<title>\S.+?)\s*$"
)

# Patron para lineas que contienen unicamente un numero, indicando que
# el titulo del paso puede encontrarse en la linea siguiente.
_STEP_ONLY_NUM_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<num>\d{1,3})\s*\.?\s*$"
)

# Patron para descartar titulos que comienzan con numeracion de seccion,
# ya que corresponden a entradas del indice y no a pasos reales.
_TITLE_LOOKS_LIKE_SECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(\.\d+){1,3}\.?\s+"
)

# Patron para descartar cadenas compuestas exclusivamente por numeros
# o por un numero con punto decimal, que no representan titulos validos.
_ONLY_NUMBER_OR_DOTTED_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(\.\d+)?$"
)

# Patron para detectar lineas de indice con puntos guia seguidos de
# numero de pagina al final de la linea.
_TOC_LEADER_RE: Final[re.Pattern[str]] = re.compile(r"\.{3,}\s*\d+\s*$")

# Patron para identificar secuencias densas de puntos consecutivos
# caracteristicas de indices y tablas de contenido.
_TOC_DOTS_RE: Final[re.Pattern[str]] = re.compile(r"\.{10,}")


# ----------------------------------------------------------------------------
# Helpers internos
# ----------------------------------------------------------------------------
# Elimina artefactos de indice del titulo de un paso.
def _clean_toc_title(title: str) -> str:
    """
    Remueve los puntos guia con numero de pagina que pueden quedar al
    final del titulo cuando el texto proviene de una tabla de contenido,
    y colapsa los espacios multiples resultantes.

    Args:
        title: Texto del titulo a limpiar.

    Returns:
        Titulo limpio sin artefactos de indice.
    """
    t = (title or "").strip()
    t = _TOC_LEADER_RE.sub("", t).strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Determina si una linea con prefijo hash pertenece a un indice.
def _is_toc_hash_line(line: str) -> bool:
    """
    Una linea se considera parte del indice cuando contiene
    simultaneamente puntos guia y un numero de pagina al final.

    Args:
        line: Linea de texto a evaluar.

    Returns:
        True si la linea parece pertenecer a un indice,
        False en caso contrario.
    """
    s = (line or "").strip()
    if not s:
        return False
    return bool(_TOC_DOTS_RE.search(s) and _TOC_LEADER_RE.search(s))


# Corrige saltos de línea entre '#' y el número de paso en textos de PDF.
def _fix_hash_line_breaks(text: str) -> str:
    """
    Algunos extractores de PDF introducen saltos de linea entre el
    caracter hash y el numero que le sigue. Esta funcion los une
    para que el patron de deteccion pueda reconocerlos correctamente.

    Args:
        text: Texto con posibles saltos de linea incorrectos.

    Returns:
        Texto con los prefijos hash y sus numeros reunidos en una
        sola linea.
    """
    t = (text or "")
    t = re.sub(r"\n\s*#\s*\n\s*(\d{1,3})\s+", r"\n#\1 ", t)
    return t


# Calcula la puntuación de calidad del fragmento para pasos con '#'.
def _hash_step_quality_score(candidate: str) -> tuple[int, int, int]:
    """
    Evalua cuantos encabezados hash no son de indice, la mediana de
    distancia entre ellos y la penalizacion por lineas de indice
    detectadas. Los fragmentos con encabezados bien separados y sin
    ruido de indice reciben puntuaciones mas altas.

    Args:
        candidate: Fragmento de texto a evaluar.

    Returns:
        Tupla con el conteo de encabezados validos, la mediana de
        distancia entre ellos y la penalizacion negativa por lineas
        de indice.
    """
    c = _fix_hash_line_breaks(candidate)
    matches = list(_HASH_STEP_RE.finditer(c))
    if len(matches) < 3:
        return (0, 0, 0)

    good = []
    for m in matches:
        if _is_toc_hash_line(m.group(0) or ""):
            continue
        good.append(m)

    if len(good) < 3:
        return (0, 0, 0)

    gaps = []
    for i in range(len(good) - 1):
        gaps.append(good[i + 1].start() - good[i].start())
    gaps.sort()
    median_gap = gaps[len(gaps) // 2] if gaps else 0

    toc_penalty = len(re.findall(r"(?m)\.{10,}\s*\d+\s*$", c))
    return (len(good), median_gap, -toc_penalty)


# -----------------------------------------------------------------------------
# API principal
# -----------------------------------------------------------------------------
def segment_requirements_flexible(
    doc_text: str,
    *,
    project_id: str
) -> SegmentationResult:
    """
    Segmenta los requerimientos de un documento PDD o FDD adaptandose
    a su estructura.

    Aplica las estrategias disponibles en orden de confiabilidad hasta
    obtener un resultado valido. Si ninguna estrategia produce bloques,
    retorna un resultado con metodo indicando la ausencia de segmentacion.

    Estrategias en orden de prioridad:
    - Estructura TO-BE clasica de la seccion 2.4.
    - IDs de requerimiento con prefijo y numeracion jerarquica.
    - Pasos con prefijo hash con filtrado de indice.
    - Pasos numerados con criterios estrictos de validacion.

    Args:
        doc_text: Texto completo del documento a segmentar.
        project_id: Identificador del proyecto para filtrar IDs de
            requerimiento. Si se omite, se infiere del contenido.

    Returns:
        Resultado de segmentacion con los bloques extraidos, el
        fragmento de contexto utilizado y el metodo aplicado.
    """
    text = (doc_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return SegmentationResult([], "", "empty")

    # Estrategia 1: estructura TO-BE de la seccion 2.4.
    to_be = slice_to_be_section(text)
    if to_be.strip():
        blocks = split_by_requirement(to_be)
        if blocks:
            return SegmentationResult(
                blocks=blocks,
                context_text=to_be,
                method="tobe"
            )

    # Estrategia 2: IDs de requerimiento con prefijo jerarquico.
    blocks = _segment_by_req_ids(text, project_id=project_id)
    if blocks:
        return SegmentationResult(
            blocks=blocks,
            context_text=text,
            method="req_id"
        )

    # Estrategia 3: pasos con prefijo hash dentro del bloque real.
    hash_body = _slice_best_process_steps_body(
        text,
        prefer_hash_steps=True
    )
    if hash_body:
        blocks = _segment_by_hash_steps(hash_body)
        if blocks:
            return SegmentationResult(
                blocks=blocks,
                context_text=hash_body,
                method="hash_steps",
            )

    # Estrategia 4: pasos numerados con validacion estricta.
    steps_body = (
        _slice_best_process_steps_body(text, prefer_hash_steps=False)
        or text
    )
    blocks = _segment_by_process_steps_strict(steps_body)
    if blocks:
        return SegmentationResult(
            blocks=blocks,
            context_text=steps_body,
            method="process_steps",
        )

    return SegmentationResult([], text, "none")


# -----------------------------------------------------------------------------
# Estrategia 2: segmentacion por IDs de requerimiento
# -----------------------------------------------------------------------------
def _segment_by_req_ids(
    text: str,
    *,
    project_id: str
) -> list[RequirementBlock]:
    """
    Segmenta el texto usando IDs de requerimiento con estructura
    jerarquica como delimitadores de bloque.

    Cuando el ID del proyecto no se proporciona, infiere el prefijo
    mas frecuente en el texto. Cada bloque abarca desde la aparicion
    del ID hasta el inicio del siguiente.

    Args:
        text: Texto del documento a segmentar.
        project_id: Prefijo del proyecto para filtrar los IDs. Si esta
            vacio, se infiere automaticamente.

    Returns:
        Lista de bloques de requerimiento extraidos, o lista vacia si
        no se encuentran suficientes IDs validos.
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return []

    matches = list(_REQ_ID_ANYWHERE_RE.finditer(t))
    if not matches:
        return []

    pid = (project_id or "").strip().upper()
    if not pid:
        prefixes = [m.group("prefix").upper() for m in matches]
        pid, count = Counter(prefixes).most_common(1)[0]
        if count < 3:
            return []

    matches = [m for m in matches if m.group("prefix").upper() == pid]
    if len(matches) < 2:
        return []

    blocks: list[RequirementBlock] = []
    for idx, m in enumerate(matches):
        req_num = int(m.group("num"))

        start = m.start()
        end = (
            matches[idx + 1].start()
            if idx + 1 < len(matches)
            else len(t)
        )
        chunk = t[start:end].strip()
        if not chunk:
            continue

        title = _extract_title_after_id(t, m.end())
        blocks.append(
            RequirementBlock(
                requirement_number=req_num,
                scenario_name=title or f"REQ {pid}.{req_num:03d}",
                input_text=chunk,
            )
        )

    return blocks

# Obtiene el título del requerimiento desde la posición indicada en el texto.
def _extract_title_after_id(t: str, pos: int) -> str:
    """
    Primero verifica si el titulo aparece en la misma linea que el ID.
    Si esa linea no contiene un titulo valido, busca en las siguientes
    lineas no vacias dentro de una ventana reducida.

    Args:
        t: Texto completo del documento.
        pos: Posicion en el texto donde termina el ID del requerimiento.

    Returns:
        Titulo del requerimiento encontrado, o cadena vacia si no se
        localiza un candidato valido.
    """
    window = t[pos: pos + 500].lstrip()

    # El titulo puede estar en la misma linea inmediatamente despues
    # del ID.
    first_line = window.split("\n", 1)[0].strip()
    if _looks_like_title(first_line, max_len=140):
        cleaned = first_line.lstrip("-–:").strip()
        if _looks_like_title(cleaned, max_len=140):
            return cleaned

    # Si el ID ocupa su propia linea, el titulo estara en las
    # siguientes lineas no vacias.
    for line in window.split("\n")[1:10]:
        candidate = line.strip().lstrip("-–:").strip()
        if _looks_like_title(candidate, max_len=160):
            return candidate

    return ""


# Determina si una cadena tiene la forma de un titulo valido.
def _looks_like_title(s: str, *, max_len: int) -> bool:
    """
    Descarta cadenas vacias, demasiado largas, sin letras, o que
    corresponden a numeracion pura o con puntos propios de indices.

    Args:
        s: Cadena a evaluar.
        max_len: Longitud maxima permitida para considerar la cadena
            como titulo.

    Returns:
        True si la cadena parece un titulo valido, False en caso
        contrario.
    """
    s = (s or "").strip()
    if not s or len(s) > max_len:
        return False
    if not _HAS_LETTERS_RE.search(s):
        return False
    if _ONLY_NUMBER_OR_DOTTED_RE.match(s):
        return False
    return True


# -----------------------------------------------------------------------------
# Estrategia 3: pasos hash y recorte de bloque real
# -----------------------------------------------------------------------------
def _slice_best_process_steps_body(
    text: str,
    *,
    prefer_hash_steps: bool
) -> str:
    """
    Recorta el fragmento del documento que contiene los pasos de proceso
    reales, evitando capturar el indice o tabla de contenido.

    Evalua cada encabezado de seccion de pasos encontrado y selecciona
    el fragmento con mejor puntuacion segun la estrategia activa.
    Aplica umbrales minimos para descartar fragmentos que probablemente
    corresponden al indice.

    Args:
        text: Texto completo del documento.
        prefer_hash_steps: Si es True, puntua segun calidad de pasos
            hash. Si es False, puntua segun cantidad de pasos numerados.

    Returns:
        Fragmento de texto con los pasos de proceso, o cadena vacia si
        no se encuentra un fragmento que supere los umbrales minimos.
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return ""

    headings = list(_PROCESS_STEPS_HEADING_RE.finditer(t))
    if not headings:
        return ""

    best_slice = ""
    best_score = None

    for h in headings:
        start = h.start()
        tail = t[start:]

        end_m = _PROCESS_STEPS_END_RE.search(tail)
        end = start + end_m.start() if end_m else len(t)

        candidate = t[start:end].strip()
        if not candidate:
            continue

        if prefer_hash_steps:
            score = _hash_step_quality_score(candidate)
        else:
            score = (_count_numeric_step_candidates(candidate), 0, 0)

        if best_score is None or score > best_score:
            best_score = score
            best_slice = candidate

    if not best_slice:
        return ""

    # Verificacion de umbrales minimos para descartar indices.
    if prefer_hash_steps:
        good_count, median_gap, _neg_toc = best_score or (0, 0, 0)
        # Se requieren suficientes encabezados validos y gaps grandes
        # que indiquen contenido real en lugar de lineas de indice.
        if good_count >= 3 and median_gap >= 40:
            return best_slice
        return ""
    else:
        cnt, _, _ = best_score or (0, 0, 0)
        if cnt >= 8:
            return best_slice
        return ""


# Cuenta las lineas que tienen la forma de pasos numerados validos.
def _count_numeric_step_candidates(text: str) -> int:
    """
    Recorre el texto linea por linea aplicando el patron de paso en
    linea y el validador de pasos para obtener un conteo que sirve
    como indicador de densidad de pasos en el fragmento.

    Args:
        text: Texto a analizar.

    Returns:
        Cantidad de lineas que corresponden a pasos numerados validos.
    """
    lines = [ln.strip() for ln in (text or "").split("\n")]
    count = 0
    for ln in lines:
        if not ln:
            continue
        m = _STEP_INLINE_RE.match(ln)
        if not m:
            continue
        num = int(m.group("num"))
        title = m.group("title").strip()
        if _is_valid_numeric_step(num=num, title=title):
            count += 1
    return count


# Segmenta el fragmento usando pasos con '#' como delimitadores de bloque.
def _segment_by_hash_steps(body: str) -> list[RequirementBlock]:
    """
    Filtra los encabezados que provienen del indice antes de construir
    los bloques. Aplica una guarda de longitud minima para descartar
    bloques demasiado cortos que probablemente son ruido. Si el numero
    de bloques resultante es insuficiente, descarta el resultado
    completo para evitar falsos positivos.

    Args:
        body: Fragmento de texto con los pasos de proceso.

    Returns:
        Lista de bloques de requerimiento, o lista vacia si no se
        obtienen suficientes bloques validos.
    """
    b = _fix_hash_line_breaks(
        (body or "").replace("\r\n", "\n").replace("\r", "\n")
    )
    matches = list(_HASH_STEP_RE.finditer(b))
    if len(matches) < 3:
        return []

    # Se descartan los encabezados identificados como lineas de indice.
    filtered = [
        m for m in matches if not _is_toc_hash_line(m.group(0) or "")
    ]
    if len(filtered) < 3:
        return []

    blocks: list[RequirementBlock] = []
    for idx, m in enumerate(filtered):
        num = int(m.group("num"))
        title = _clean_toc_title(m.group("title").strip())

        if not _looks_like_title(title, max_len=160):
            title = f"Step #{num}"

        start = m.start()
        end = (
            filtered[idx + 1].start()
            if idx + 1 < len(filtered)
            else len(b)
        )
        chunk = b[start:end].strip()
        if not chunk:
            continue

        # Los bloques demasiado cortos suelen ser entradas residuales
        # del indice que no fueron filtradas correctamente.
        if len(chunk) < 120:
            continue

        blocks.append(
            RequirementBlock(
                requirement_number=num,
                scenario_name=title,
                input_text=chunk,
            )
        )

    # Un numero insuficiente de bloques indica que el fragmento no
    # contiene pasos reales y el resultado se descarta.
    if len(blocks) < 3:
        return []

    return blocks


# -----------------------------------------------------------------------------
# Estrategia 4: pasos numerados con validacion estricta
# -----------------------------------------------------------------------------
def _segment_by_process_steps_strict(
    text: str
) -> list[RequirementBlock]:
    """
    Segmenta el texto por pasos numerados aplicando criterios estrictos
    para evitar falsos positivos por entradas de indice o secciones.

    Soporta pasos con numero y titulo en la misma linea con distintos
    separadores, y pasos donde el numero ocupa su propia linea y el
    titulo aparece en la siguiente. Solo produce resultado si existe
    una secuencia consecutiva suficientemente larga.

    Args:
        text: Texto del fragmento a segmentar.

    Returns:
        Lista de bloques de requerimiento correspondientes a la mejor
        secuencia consecutiva encontrada, o lista vacia si no se
        cumple el umbral minimo.
    """
    lines = [ln.rstrip() for ln in (text or "").split("\n")]
    candidates: list[tuple[int, int, str]] = []

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1
            continue

        m_inline = _STEP_INLINE_RE.match(ln)
        if m_inline:
            num = int(m_inline.group("num"))
            title = m_inline.group("title").strip()
            if _is_valid_numeric_step(num=num, title=title):
                candidates.append((i, num, title))
            i += 1
            continue

        m_only = _STEP_ONLY_NUM_RE.match(ln)
        if m_only:
            num = int(m_only.group("num"))
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                title = lines[j].strip()
                if _is_valid_numeric_step(num=num, title=title):
                    candidates.append((i, num, title))
                    i = j + 1
                    continue

        i += 1

    if len(candidates) < 8:
        return []

    best_run = _pick_best_consecutive_run(candidates)
    if len(best_run) < 8:
        return []

    blocks: list[RequirementBlock] = []
    for idx, (start_i, num, title) in enumerate(best_run):
        end_i = (
            best_run[idx + 1][0]
            if idx + 1 < len(best_run)
            else len(lines)
        )
        chunk = "\n".join(lines[start_i:end_i]).strip()
        if not chunk:
            continue
        blocks.append(
            RequirementBlock(
                requirement_number=num,
                scenario_name=title,
                input_text=chunk,
            )
        )

    return blocks


# Valida que un paso numerado sea real y no un artefacto de extracción.
def _is_valid_numeric_step(*, num: int, title: str) -> bool:
    """
    Aplica restricciones de rango en el numero, longitud del titulo,
    presencia de letras y formato del texto para descartar falsos
    positivos habituales en documentos PDF y DOCX.

    Args:
        num: Numero del paso.
        title: Texto del titulo del paso.

    Returns:
        True si el paso cumple todos los criterios de validez,
        False en caso contrario.
    """
    if num <= 0 or num > 300:
        return False

    t = (title or "").strip()
    if not t:
        return False
    if len(t) > 160:
        return False
    if not _HAS_LETTERS_RE.search(t):
        return False

    # Los titulos que comienzan con numeracion de seccion corresponden
    # a entradas del indice, no a pasos de proceso.
    if _TITLE_LOOKS_LIKE_SECTION_RE.match(t):
        return False

    # Los titulos que son exclusivamente numericos no representan pasos
    # validos.
    if _ONLY_NUMBER_OR_DOTTED_RE.match(t):
        return False

    return True


# Selecciona la secuencia consecutiva más larga entre pasos candidatos.
def _pick_best_consecutive_run(
    candidates: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """
    Recorre la lista de candidatos buscando secuencias donde el numero
    de cada paso es exactamente el siguiente al anterior. Cuando
    encuentra un reinicio desde el numero uno, cierra la secuencia
    actual y comienza una nueva. La secuencia mas larga encontrada
    se devuelve como resultado.

    Args:
        candidates: Lista de tuplas con indice de linea, numero de paso
            y titulo, en el orden en que aparecen en el texto.

    Returns:
        Secuencia consecutiva mas larga encontrada, o lista vacia si
        ninguna secuencia comienza cerca del numero uno.
    """
    best: list[tuple[int, int, str]] = []
    current: list[tuple[int, int, str]] = []

    expected_next: int | None = None

    for item in candidates:
        _line_i, num, _title = item

        if not current:
            current = [item]
            expected_next = num + 1
            continue

        if expected_next is not None and num == expected_next:
            current.append(item)
            expected_next += 1
            continue

        # Al encontrar un reinicio desde el numero uno, se cierra la
        # secuencia actual y se inicia una nueva.
        if num == 1:
            if len(current) > len(best):
                best = current
            current = [item]
            expected_next = 2
            continue

        if len(current) > len(best):
            best = current
        current = [item]
        expected_next = num + 1

    if len(current) > len(best):
        best = current

    # La secuencia debe iniciar en un numero cercano al inicio para
    # ser considerada una secuencia de pasos real.
    if best:
        start_num = best[0][1]
        if start_num not in {1, 0, 2}:
            return []
    return best