"""
Modulo de helpers para procesamiento de salida del modelo.

Este modulo contiene funciones para extraer y limpiar el contenido CSV
generado por el modelo, removiendo texto extra y normalizando el formato.

Responsabilidades:
- Extraer unicamente el bloque CSV desde la respuesta del modelo
- Remover markdown fences y texto adicional
- Normalizar formato de salida
- Validar estructura basica de filas CSV

Nota: No aplica reglas ADO ni asigna titulos, esas responsabilidades
corresponden a otros modulos.
"""
from __future__ import annotations

import csv
import io

from core.ado_csv import ADO_CSV_HEADER, ADO_NCOLS

# Constantes de formato
_BOM = "\ufeff"
_CSV_DELIMITER = ","
_CSV_QUOTECHAR = '"'


def _normalize_header(header: str) -> str:
    """
    Normaliza un encabezado para comparaciones tolerando espacios.

    Ejemplo:
    - "ID, Work Item Type" vs "ID,Work Item Type"

    Args:
        header: Texto de encabezado a normalizar

    Returns:
        Encabezado sin espacios para comparacion
    """
    return (header or "").replace(" ", "").strip()


def _strip_code_fences(text: str) -> str:
    """
    Elimina fences tipo ``` o ```csv si el modelo envolvio la respuesta.

    Si no hay fences, retorna el texto sin cambios relevantes.

    Args:
        text: Texto potencialmente con markdown fences

    Returns:
        Texto sin fences de codigo
    """
    cleaned = (text or "").strip()
    if not cleaned.startswith("```"):
        return cleaned

    lines = cleaned.splitlines()

    # Elimina la primera linea del fence: ``` o ```csv
    if lines:
        lines = lines[1:]

    # Elimina fences finales si existen
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()

    return "\n".join(lines).strip()


def _looks_like_ado_row(row: list[str]) -> bool:
    """
    Valida de forma conservadora si una fila parece una fila ADO.

    Reglas actuales:
    - Debe tener exactamente 15 columnas
    - El primer campo suele ser vacio o "ID" si se colo el header

    Args:
        row: Lista de valores de una fila CSV

    Returns:
        True si parece una fila ADO valida, False en caso contrario
    """
    if len(row) != ADO_NCOLS:
        return False

    first = (row[0] or "").strip()
    return first == "" or first.upper() == "ID"


def extract_csv_only(text: str) -> str:
    """
    Devuelve unicamente la parte CSV de la salida del modelo.

    Estrategia:
    - Remueve fences ``` si existen
    - Si encuentra el header ADO, recorta desde ahi
    - Si no hay header, busca la primera linea que parezca fila de
      15 columnas
    - Si no detecta CSV claro, retorna el texto limpio para que el
      parser valide

    Args:
        text: Texto crudo de salida del modelo

    Returns:
        Texto CSV extraido y limpio
    """
    cleaned = _strip_code_fences(text)
    cleaned = (cleaned or "").lstrip(_BOM).strip()
    if not cleaned:
        return ""

    lines = cleaned.splitlines()

    # Busca header ADO y recorta desde ahi
    ado_norm = _normalize_header(ADO_CSV_HEADER)
    for idx, line in enumerate(lines):
        if _normalize_header(line) == ado_norm:
            return "\n".join(lines[idx:]).strip()

    # Si no hay header, busca primera fila que parezca ADO
    for idx in range(len(lines)):
        chunk = "\n".join(lines[idx:]).strip()
        if not chunk:
            continue

        try:
            reader = csv.reader(
                io.StringIO(chunk),
                delimiter=_CSV_DELIMITER,
                quotechar=_CSV_QUOTECHAR,
            )
            first_row = next(reader, None)
            if first_row and _looks_like_ado_row(first_row):
                return chunk
        except Exception:
            # Ignora errores de parseo y continua la busqueda
            continue

    return cleaned
