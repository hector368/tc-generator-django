"""
Modulo de construccion de Context Pack global.

Este modulo construye un contexto global para mantener trazabilidad entre
bloques de requerimientos.

Responsabilidades:
- Resumir/extraer contexto relevante del TO-BE completo
- Generar texto compacto que se inyecta en cada requerimiento para
  evitar perdida de contexto
- Detectar sistemas, inputs, outputs y formatos mencionados
- Identificar notas y referencias cruzadas repetidas

Nota: No divide requerimientos ni genera CSV.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Final

# Patrones para detectar valores explicitos del documento TO-BE
_SYSTEM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bSistema\s*:\s*([^\n]+)"
)
_INPUT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bInput\s*:\s*([^\n]+)"
)
_OUTPUT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bOutput\s*:\s*([^\n]+)"
)
_NOTE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^\s*Nota(?:\s*\d+)?\s*:\s*(.+)$"
)
_ACTIVITY_REF_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:obtenid[ao]s?\s+en\s+la\s+actividad|actividad)\s+\d+\b"
)

# Extrae nombres entre comillas tipograficas o comillas dobles
# Nota: Las comillas tipograficas (" ") son parte del patron a buscar
# en documentos, no del codigo
_QUOTED_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r'["""\']([^"""\'\n]{3,90})["""\']'
)

# Detecta formatos/herramientas comunes de forma determinista
_FORMAT_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b("
    r"DD/MM/YYYY|DD/MM/AAAA|HH:MI|YYYYMMDDhhmmss|ANSI|"
    r"\.csv|SharePoint|Outlook|GeoVictoria|Turnex"
    r")\b"
)

# Constantes de limites
DEFAULT_MAX_CHARS: Final[int] = 2400
DEFAULT_MAX_LINES: Final[int] = 80

MAX_LONG_LINE_SPLIT: Final[int] = 180
MAX_LOOKUP_FORMAT_LINES: Final[int] = 30
MAX_LIST_ITEMS: Final[int] = 12


def _normalize(text: str) -> str:
    """
    Normaliza saltos de linea y elimina caracteres invisibles.

    Args:
        text: Texto a normalizar

    Returns:
        Texto normalizado
    """
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u200b", "")
    return normalized


def _split_long_line(
    line: str,
    max_len: int = MAX_LONG_LINE_SPLIT
) -> list[str]:
    """
    Divide lineas muy largas para mejorar legibilidad en el contexto.

    Se intenta dividir por limites de oracion y, si no es posible,
    se hace un corte duro por longitud.

    Args:
        line: Linea de texto a dividir
        max_len: Longitud maxima permitida por segmento

    Returns:
        Lista de segmentos de texto
    """
    cleaned = (line or "").strip()
    if len(cleaned) <= max_len:
        return [cleaned] if cleaned else []

    parts: list[str] = []
    buffer_text = ""

    for chunk in re.split(r"(\.\s+)", cleaned):
        if not chunk:
            continue

        if len(buffer_text) + len(chunk) <= max_len:
            buffer_text += chunk
            continue

        if buffer_text.strip():
            parts.append(buffer_text.strip())

        buffer_text = chunk

    if buffer_text.strip():
        parts.append(buffer_text.strip())

    out: list[str] = []
    for part in parts:
        if len(part) <= max_len:
            out.append(part)
            continue

        for idx in range(0, len(part), max_len):
            segment = part[idx : idx + max_len].strip()
            out.append(segment)

    return [item for item in out if item]


def _collect_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    """
    Extrae coincidencias del grupo 1 de un patron regex.

    Args:
        pattern: Patron de expresion regular
        text: Texto donde buscar

    Returns:
        Lista de valores extraidos
    """
    items: list[str] = []
    for match in pattern.finditer(text or ""):
        value = (match.group(1) or "").strip()
        if value:
            items.append(value)
    return items


def _stable_unique(items: list[str]) -> list[str]:
    """
    Elimina duplicados manteniendo el orden de aparicion.

    Args:
        items: Lista con posibles duplicados

    Returns:
        Lista sin duplicados en orden original
    """
    return list(dict.fromkeys(items))


def build_context_pack(
    to_be_text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """
    Construye un contexto global determinista (sin LLM) a partir del
    TO-BE.

    Objetivo:
    - Compartir sistemas, artefactos, formatos y notas repetidas
    - Evitar contaminar con reglas especificas de un bloque

    Args:
        to_be_text: Texto completo de la seccion TO-BE
        max_chars: Limite de caracteres del contexto generado
        max_lines: Limite de lineas del contexto generado

    Returns:
        Texto del contexto global formateado
    """
    normalized = _normalize(to_be_text)

    # Extrae sistemas, inputs, outputs
    systems = sorted(set(_collect_matches(_SYSTEM_RE, normalized)))
    inputs = sorted(set(_collect_matches(_INPUT_RE, normalized)))
    outputs = sorted(set(_collect_matches(_OUTPUT_RE, normalized)))

    # Extrae nombres entre comillas
    quoted = sorted(set(_collect_matches(_QUOTED_NAME_RE, normalized)))

    # Procesa lineas y divide las muy largas
    raw_lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
    lines: list[str] = []
    for ln in raw_lines:
        lines.extend(_split_long_line(ln))

    # Extrae notas y encuentra las repetidas
    note_texts: list[str] = []
    for ln in lines:
        match = _NOTE_RE.match(ln)
        if match:
            note_texts.append(match.group(1).strip())

    note_counts = Counter([note.lower() for note in note_texts])
    repeated_notes: list[str] = []
    for note in note_texts:
        if note_counts.get(note.lower(), 0) >= 2:
            repeated_notes.append(note)
    repeated_notes = _stable_unique(repeated_notes)

    # Extrae referencias a otras actividades
    activity_refs: list[str] = []
    for ln in lines:
        if _ACTIVITY_REF_RE.search(ln):
            activity_refs.append(ln)
    activity_refs = _stable_unique(activity_refs)

    # Extrae hints de formatos y herramientas
    format_hints: list[str] = []
    for ln in lines:
        if _FORMAT_HINT_RE.search(ln):
            format_hints.append(ln)
    format_hints = _stable_unique(format_hints)[:MAX_LOOKUP_FORMAT_LINES]

    # Construye el texto de salida
    out_lines: list[str] = []
    out_lines.append(
        "GLOBAL_CONTEXT (extracted from TO-BE; use only if applicable):"
    )

    if systems:
        out_lines.append(f"- Systems: {', '.join(systems)}")

    if inputs:
        inputs_joined = ", ".join(inputs[:MAX_LIST_ITEMS])
        suffix = " ..." if len(inputs) > MAX_LIST_ITEMS else ""
        out_lines.append(f"- Inputs mentioned: {inputs_joined}{suffix}")

    if outputs:
        outputs_joined = ", ".join(outputs[:MAX_LIST_ITEMS])
        suffix = " ..." if len(outputs) > MAX_LIST_ITEMS else ""
        out_lines.append(f"- Outputs mentioned: {outputs_joined}{suffix}")

    if quoted:
        quoted_joined = ", ".join(quoted[:MAX_LIST_ITEMS])
        suffix = " ..." if len(quoted) > MAX_LIST_ITEMS else ""
        out_lines.append(
            f"- Named folders/files (quoted): {quoted_joined}{suffix}"
        )

    if repeated_notes:
        out_lines.append("- Repeated notes (appear multiple times):")
        for note in repeated_notes[:MAX_LIST_ITEMS]:
            out_lines.append(f"  • {note}")

    if activity_refs:
        out_lines.append("- Cross-activity references (dependencies):")
        for ref in activity_refs[:MAX_LIST_ITEMS]:
            out_lines.append(f"  • {ref}")

    if format_hints:
        out_lines.append(
            "- Format/tooling hints "
            "(verbatim lines containing formats/tools):"
        )
        for hint in format_hints[:MAX_LIST_ITEMS]:
            out_lines.append(f"  • {hint}")

    # Aplica limites
    out_lines = out_lines[:max_lines]
    pack = "\n".join(out_lines).strip()

    if len(pack) > max_chars:
        pack = pack[:max_chars].rstrip() + "\n(Truncated)"

    return pack
