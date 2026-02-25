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
    blocks: list[RequirementBlock]
    context_text: str
    method: str  # "tobe" | "req_id" | "hash_steps" | "process_steps" | "none" | "empty"


# -----------------------------------------------------------------------------
# Regex base
# -----------------------------------------------------------------------------
_HAS_LETTERS_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")

# Encabezados por ID (pueden aparecer en la misma línea o separados en PDF):
#   MCC.021.001
#   Obtener Listas ...
_REQ_ID_ANYWHERE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<prefix>[A-Z]{2,10}\.\d{3})\.(?P<num>\d{3})\b"
)

# Process steps estilo "#1 Title"
_HASH_STEP_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^\s*#\s*(?P<num>\d{1,3})\s+(?P<title>.+?)\s*$"
)

# Identificación de headings para recortar el cuerpo real (evitar TOC/índice).
# Ejemplos:
#   6.3 Process steps Ice cream
#   6.6 Process steps Refrigerated
_PROCESS_STEPS_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:\d+\.\d+(?:\.\d+)?\.?\s+)?Process\s+steps\b.*$"
)

# Típico final del bloque de steps en PDD:
#   7. Data storage locations
_PROCESS_STEPS_END_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*7\.\s*Data\s+storage\s+locations\b.*$"
)

# Process steps numéricos (fallback final). OJO: se endurece para evitar TOC.
_STEP_INLINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<num>\d{1,3})\s*(?:[.)-]\s+|\s+)(?P<title>\S.+?)\s*$"
)
_STEP_ONLY_NUM_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<num>\d{1,3})\s*\.?\s*$"
)
# Evita casos como "4.1. Automation Team" (title empieza con "1." y es TOC)
_TITLE_LOOKS_LIKE_SECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(\.\d+){1,3}\.?\s+"
)
_ONLY_NUMBER_OR_DOTTED_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(\.\d+)?$")


# -----------------------------------------------------------------------------
# API principal
# -----------------------------------------------------------------------------
def segment_requirements_flexible(doc_text: str, *, project_id: str) -> SegmentationResult:
    """
    Segmenta requerimientos para PDD/FDD con distintas estructuras.

    Orden (del más confiable al menos confiable):
    1) TO-BE clásico (2.4) usando tu lógica actual
    2) REQ IDs tipo "<PREFIX>.<NNN>" (ej. MCC.021.001) con título en misma línea
       o en la siguiente (PDF/tablas)
    3) HASH steps: "#1 Título" (ideal para PDDs como NSC.C.007) con recorte para
       evitar TOC/índice
    4) Process steps numéricos (fallback estricto) "1. Title" / "1 Title" / "1" + title
    5) none si no se detecta nada
    """
    text = (doc_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return SegmentationResult([], "", "empty")

    # 1) TO-BE (tu método actual)
    to_be = slice_to_be_section(text)
    if to_be.strip():
        blocks = split_by_requirement(to_be)
        if blocks:
            return SegmentationResult(blocks=blocks, context_text=to_be, method="tobe")

    # 2) FDD por REQ IDs (MCC.021.001 / NSC.B.003.012 etc.)
    blocks = _segment_by_req_ids(text, project_id=project_id)
    if blocks:
        return SegmentationResult(blocks=blocks, context_text=text, method="req_id")

    # 3) PDD por "#<n> <title>" dentro del bloque real de process steps
    hash_body = _slice_best_process_steps_body(text, prefer_hash_steps=True)
    if hash_body:
        blocks = _segment_by_hash_steps(hash_body)
        if blocks:
            return SegmentationResult(
                blocks=blocks,
                context_text=hash_body,
                method="hash_steps",
            )

    # 4) Último fallback: pasos numerados (estricto)
    steps_body = _slice_best_process_steps_body(text, prefer_hash_steps=False) or text
    blocks = _segment_by_process_steps_strict(steps_body)
    if blocks:
        return SegmentationResult(
            blocks=blocks,
            context_text=steps_body,
            method="process_steps",
        )

    return SegmentationResult([], text, "none")


# -----------------------------------------------------------------------------
# Estrategia 2: segmentación por REQ IDs (MCC.021.001...)
# -----------------------------------------------------------------------------
def _segment_by_req_ids(text: str, *, project_id: str) -> list[RequirementBlock]:
    """
    Segmenta por IDs tipo 'MCC.021.001' aunque el título venga en la línea
    siguiente (común en PDFs/tablas).

    - Si project_id está vacío, infiere el prefijo más frecuente (ej. MCC.021).
    - Corta desde la aparición del ID hasta antes del siguiente ID.
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
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(t)
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


def _extract_title_after_id(t: str, pos: int) -> str:
    """
    Obtiene el título del requerimiento:
    - Si viene en la misma línea después del ID, úsalo.
    - Si el ID está solo, toma la siguiente línea no vacía.
    """
    window = t[pos : pos + 500].lstrip()

    # Caso A: título en la misma línea
    first_line = window.split("\n", 1)[0].strip()
    if _looks_like_title(first_line, max_len=140):
        cleaned = first_line.lstrip("-–:").strip()
        if _looks_like_title(cleaned, max_len=140):
            return cleaned

    # Caso B: título en la siguiente línea no vacía
    for line in window.split("\n")[1:10]:
        candidate = line.strip().lstrip("-–:").strip()
        if _looks_like_title(candidate, max_len=160):
            return candidate

    return ""


def _looks_like_title(s: str, *, max_len: int) -> bool:
    s = (s or "").strip()
    if not s or len(s) > max_len:
        return False
    if not _HAS_LETTERS_RE.search(s):
        return False
    if _ONLY_NUMBER_OR_DOTTED_RE.match(s):
        return False
    return True


# -----------------------------------------------------------------------------
# Estrategia 3: HASH steps (#1 Title) + recorte para evitar TOC
# -----------------------------------------------------------------------------
def _slice_best_process_steps_body(text: str, *, prefer_hash_steps: bool) -> str:
    """
    Intenta recortar el cuerpo REAL donde están los process steps, evitando
    capturar el índice/TOC.

    Selecciona el mejor candidato en base a:
    - cantidad de "#<n>" si prefer_hash_steps=True
    - cantidad de pasos numéricos si prefer_hash_steps=False
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip():
        return ""

    headings = list(_PROCESS_STEPS_HEADING_RE.finditer(t))
    if not headings:
        return ""

    best_slice = ""
    best_score = 0

    for h in headings:
        start = h.start()
        tail = t[start:]

        end_m = _PROCESS_STEPS_END_RE.search(tail)
        end = start + end_m.start() if end_m else len(t)

        candidate = t[start:end].strip()
        if not candidate:
            continue

        if prefer_hash_steps:
            score = len(_HASH_STEP_RE.findall(candidate))
        else:
            score = _count_numeric_step_candidates(candidate)

        if score > best_score:
            best_score = score
            best_slice = candidate

    # Umbrales mínimos para evitar devolver TOC:
    if prefer_hash_steps and best_score >= 5:
        return best_slice
    if (not prefer_hash_steps) and best_score >= 8:
        return best_slice

    return ""


def _count_numeric_step_candidates(text: str) -> int:
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


def _segment_by_hash_steps(body: str) -> list[RequirementBlock]:
    """
    Segmenta por pasos tipo "#1 Title" dentro del body recortado.
    """
    b = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_HASH_STEP_RE.finditer(b))
    if len(matches) < 3:
        return []

    blocks: list[RequirementBlock] = []
    for idx, m in enumerate(matches):
        num = int(m.group("num"))
        title = m.group("title").strip()

        if not _looks_like_title(title, max_len=160):
            title = f"Step #{num}"

        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(b)
        chunk = b[start:end].strip()
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


# -----------------------------------------------------------------------------
# Estrategia 4: process steps numéricos (fallback estricto)
# -----------------------------------------------------------------------------
def _segment_by_process_steps_strict(text: str) -> list[RequirementBlock]:
    """
    Segmenta por pasos numerados, pero con reglas estrictas para evitar TOC.

    Se considera válido si existe un "run" largo de pasos consecutivos
    (por ejemplo 1..N) y los títulos parecen pasos reales, no secciones.

    Formatos soportados:
    - "1. Obtain pending loads"
    - "1 Obtain pending loads"
    - "1" (línea sola) y título en la siguiente
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
        end_i = best_run[idx + 1][0] if idx + 1 < len(best_run) else len(lines)
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


def _is_valid_numeric_step(*, num: int, title: str) -> bool:
    """
    Filtra falsos positivos típicos (TOC, numeración de secciones, etc.)
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

    # Evita secciones como "4.1. ..." o títulos que empiezan con "1. ..."
    if _TITLE_LOOKS_LIKE_SECTION_RE.match(t):
        return False

    # Evita títulos que sean solo números o "2.4"
    if _ONLY_NUMBER_OR_DOTTED_RE.match(t):
        return False

    return True


def _pick_best_consecutive_run(
    candidates: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """
    Escoge el mejor "run" consecutivo en el orden de aparición.
    Busca secuencias del tipo 1,2,3,... con tolerancia mínima.

    - Reinicia cuando encuentra un salto grande o un reset a 1.
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

        # Si hay reset a 1, cerramos run y empezamos otro
        if num == 1:
            if len(current) > len(best):
                best = current
            current = [item]
            expected_next = 2
            continue

        # Si el salto es pequeño (ej. 5 -> 7), NO lo aceptamos como run consecutivo
        if len(current) > len(best):
            best = current
        current = [item]
        expected_next = num + 1

    if len(current) > len(best):
        best = current

    # Validación final: el run debe iniciar cercano a 1
    if best:
        start_num = best[0][1]
        if start_num not in {1, 0, 2}:
            return []
    return best