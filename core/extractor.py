"""
Modulo para extraccion de texto desde archivos PDF y DOCX.

Este modulo proporciona funciones para extraer texto de documentos
manteniendo el orden y estructura del contenido original.

Responsabilidades:
- Extraccion de texto desde archivos PDF (PyMuPDF)
- Extraccion de texto desde archivos DOCX (python-docx)
- Normalizacion y limpieza de texto extraido
- Manejo de tablas y parrafos en orden correcto
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Final

import fitz
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

# Constantes de tipos de archivo soportados
SUPPORTED_EXTS: Final[tuple[str, ...]] = (".pdf", ".docx")
PDF_EXT: Final[str] = ".pdf"
DOCX_EXT: Final[str] = ".docx"

# Separador para celdas de tabla
# Nota: En DOCX, unir celdas con "|" rompe regex comunes
# (ej. "ID del proyecto: XXX.000").
# Un espacio mantiene legibilidad y hace que el splitter/regex sea
# mas confiable.
TABLE_CELL_SEP: Final[str] = " "


def _clean_text(text: str) -> str:
    """
    Normaliza artefactos comunes de extraccion para mejorar la
    confiabilidad de busquedas y regex.

    Args:
        text: Texto crudo extraido de documento

    Returns:
        Texto normalizado sin caracteres especiales problematicos
    """
    if not text:
        return ""

    # Normaliza saltos de linea
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remueve caracteres especiales Unicode problematicos
    text = text.replace("\u200b", "").replace("\xa0", " ")

    # Normaliza guiones
    text = text.replace("–", "-").replace("—", "-")

    # Limpia lineas vacias y normaliza espacios
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()


def _iter_docx_blocks(doc: Document):
    """
    Itera bloques (parrafos y tablas) en el orden real del documento.

    Args:
        doc: Documento DOCX cargado

    Yields:
        Objetos Paragraph o Table en orden de aparicion
    """
    body = doc.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, doc)
        elif isinstance(child, CT_Tbl):
            yield Table(child, doc)


def extract_text_from_upload(filename: str, file_bytes: bytes) -> str:
    """
    Extrae texto de PDF o DOCX.

    Reglas:
    - PDF: se lee pagina por pagina preservando el orden
    - DOCX: se extrae respetando el orden real (parrafos y tablas)

    Args:
        filename: Nombre del archivo con extension
        file_bytes: Contenido binario del archivo

    Returns:
        Texto extraido y normalizado

    Raises:
        ValueError: Si el tipo de archivo no esta soportado
    """
    ext = Path(filename).suffix.lower()

    if ext == PDF_EXT:
        parts: list[str] = []
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                page_text = _clean_text(page.get_text("text") or "")
                if page_text:
                    parts.append(page_text)
        return "\n\n".join(parts).strip()

    if ext == DOCX_EXT:
        doc = Document(io.BytesIO(file_bytes))
        parts: list[str] = []

        for block in _iter_docx_blocks(doc):
            # Procesa parrafo
            if isinstance(block, Paragraph):
                paragraph_text = _clean_text(block.text)
                if paragraph_text:
                    parts.append(paragraph_text)
                continue

            # Procesa tabla
            if isinstance(block, Table):
                for row in block.rows:
                    cells: list[str] = []
                    for cell in row.cells:
                        cell_text = _clean_text(cell.text)
                        if not cell_text:
                            continue
                        # Une lineas multiples dentro de la celda
                        cell_text = " ".join(
                            cell_text.splitlines()
                        ).strip()
                        if cell_text:
                            cells.append(cell_text)

                    if cells:
                        parts.append(TABLE_CELL_SEP.join(cells))

        return "\n".join(parts).strip()

    raise ValueError(
        f"Tipo de archivo no soportado. Permitidos: {SUPPORTED_EXTS}"
    )
