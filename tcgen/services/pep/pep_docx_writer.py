"""
Escritura del documento PEP en formato DOCX mediante placeholders.

Este módulo toma el contexto combinado PAP + PDD/FDD y llena una copia
de la plantilla PEP integrada reemplazando marcas configurables como
**Name_Project, **ID_Project o **Titles_requirements_Tobe.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

from tcgen.services.pep.pep_context import PepContext
from tcgen.services.pep.template_loader import read_pep_template_bytes


FONT_NAME = "Montserrat Medium"
FONT_SIZE_PT = 10
FONT_COLOR = RGBColor(0x59, 0x59, 0x59)
DEFAULT_TEXT_STYLE = {
    "font_name": "Montserrat",
    "font_size": 10,
    "bold": False,
    "alignment": WD_ALIGN_PARAGRAPH.LEFT,
}

PLACEHOLDER_STYLES = {
    "**Name_Project_T": {
        "font_name": "Open Sans",
        "font_size": 32,
        "bold": True,
        "alignment": WD_ALIGN_PARAGRAPH.CENTER,
    },
    "**ID_Project_H": {
        "font_name": "Montserrat",
        "font_size": 8,
        "bold": False,
        "alignment": WD_ALIGN_PARAGRAPH.CENTER,
    },
    "**Date_issue": {
        "font_name": "Montserrat",
        "font_size": 8,
        "bold": False,
        "alignment": WD_ALIGN_PARAGRAPH.CENTER,
    },
}

def generate_pep_docx_bytes(context: PepContext) -> bytes:
    """
    Genera un PEP en DOCX a partir del contexto combinado.

    Args:
        context: Contexto con datos PAP y requerimientos TO-BE.

    Returns:
        Contenido binario del DOCX generado.
    """
    template_bytes = read_pep_template_bytes()
    document = Document(BytesIO(template_bytes))

    replacements = _build_placeholder_replacements(context)
    _replace_placeholders(document, replacements)

    output = BytesIO()
    document.save(output)

    return output.getvalue()


def _build_placeholder_replacements(
    context: PepContext,
) -> dict[str, str]:
    """
    Construye el mapa de placeholders contra valores finales.

    Args:
        context: Contexto combinado del PEP.

    Returns:
        Diccionario con placeholders y textos de reemplazo.
    """
    pap = context.pap
    roles = pap.roles

    project_name = _safe_text(pap.nombre_proyecto)
    project_id = _safe_text(context.project_id)

    return {
        "**Name_Project_T": f'"{project_name}"',
        "**Name_Project": project_name,

        "**ID_Project_H": project_id,
        "**ID_Project": project_id,

        "**Client_Name": _safe_text(pap.nombre_cliente),
        "**Tecnology_Name": _safe_text(pap.tecnologia.valor),
        "**Date_issue": _format_issue_date(date.today()),

        "**Dev_Name": _join_people_names(roles.desarrollador),
        "**Tester_Name": _join_people_names(roles.tester),
        "**SC_Name": _join_people_names(roles.scrum_master),
        "**DM_Name": _join_people_names(roles.delivery_manager),
        "**BA_Name": _join_people_names(roles.business_analyst),
        "**Architec_Name": _join_people_names(roles.arquitecto),
        "**CR_Name": _join_people_names(roles.code_reviewer),

        "**Software_requirements": _build_bullet_list(
            pap.requisitos_software.items,
        ),
        "**Hardware_Requirements": _build_bullet_list(
            pap.requisitos_hardware.items,
        ),
        "**Titles_requirements_Tobe": _build_tobe_requirement_lines(context),
    }


def _replace_placeholders(
    document: Any,
    replacements: dict[str, str],
) -> None:
    """
    Reemplaza placeholders en todos los párrafos del documento.

    Incluye párrafos normales, tablas, encabezados y pies de página.

    Args:
        document: Documento DOCX cargado.
        replacements: Diccionario placeholder -> valor.
    """
    for paragraph in _iter_all_paragraphs(document):
        _replace_placeholders_in_paragraph(paragraph, replacements)


def _replace_placeholders_in_paragraph(
    paragraph: Any,
    replacements: dict[str, str],
) -> None:
    """
    Reemplaza placeholders dentro de un párrafo.

    Args:
        paragraph: Párrafo DOCX.
        replacements: Diccionario placeholder -> valor.
    """
    original_text = paragraph.text
    if not original_text:
        return

    matched_placeholders = [
        placeholder
        for placeholder in sorted(replacements, key=len, reverse=True)
        if placeholder in original_text
    ]

    if not matched_placeholders:
        return

    new_text = original_text

    for placeholder in matched_placeholders:
        new_text = new_text.replace(
            placeholder,
            replacements[placeholder],
        )

    style = _resolve_style_for_placeholders(matched_placeholders)

    _set_paragraph_text(
        paragraph,
        new_text,
        style,
    )

def _resolve_style_for_placeholders(
    placeholders: list[str],
) -> dict[str, Any]:
    """
    Resuelve el estilo a aplicar según el placeholder encontrado.

    Args:
        placeholders: Lista de placeholders encontrados.

    Returns:
        Diccionario de estilo.
    """
    style = dict(DEFAULT_TEXT_STYLE)

    for placeholder in placeholders:
        custom_style = PLACEHOLDER_STYLES.get(placeholder)
        if custom_style:
            style.update(custom_style)
            return style

    return style

def _iter_all_paragraphs(document: Any) -> Iterable[Any]:
    """
    Itera todos los párrafos del documento, incluyendo tablas,
    encabezados, pies de página y cuadros de texto.

    Args:
        document: Documento DOCX.

    Yields:
        Párrafos encontrados.
    """
    yield from document.paragraphs
    yield from _iter_textbox_paragraphs(document)

    for table in document.tables:
        yield from _iter_table_paragraphs(table)

    for section in document.sections:
        yield from section.header.paragraphs
        yield from _iter_textbox_paragraphs(section.header)

        yield from section.footer.paragraphs
        yield from _iter_textbox_paragraphs(section.footer)

        for table in section.header.tables:
            yield from _iter_table_paragraphs(table)

        for table in section.footer.tables:
            yield from _iter_table_paragraphs(table)

def _iter_textbox_paragraphs(parent: Any) -> Iterable[Any]:
    """
    Itera párrafos dentro de cuadros de texto.

    Args:
        parent: Documento, encabezado o pie de página.

    Yields:
        Párrafos encontrados dentro de text boxes.
    """
    for paragraph_element in parent._element.xpath(".//w:txbxContent//w:p"):
        yield Paragraph(paragraph_element, parent)

def _iter_table_paragraphs(table: Any) -> Iterable[Any]:
    """
    Itera párrafos dentro de una tabla, incluyendo tablas anidadas.

    Args:
        table: Tabla DOCX.

    Yields:
        Párrafos encontrados dentro de las celdas.
    """
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs

            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _set_paragraph_text(
    paragraph: Any,
    text: str,
    style: dict[str, Any],
) -> None:
    """
    Reemplaza el texto de un párrafo aplicando formato configurable.

    Args:
        paragraph: Párrafo DOCX.
        text: Texto a escribir.
        style: Estilo a aplicar.
    """
    _clear_paragraph_runs(paragraph)

    paragraph.alignment = style["alignment"]

    lines = text.splitlines() or [""]

    first_run = paragraph.add_run(lines[0])
    _apply_pep_run_style(first_run, style)

    for line in lines[1:]:
        run = paragraph.add_run()
        run.add_break()
        run.add_text(line)
        _apply_pep_run_style(run, style)


def _clear_paragraph_runs(paragraph: Any) -> None:
    """
    Elimina los runs existentes de un párrafo.

    Args:
        paragraph: Párrafo DOCX.
    """
    for run in list(paragraph.runs):
        run_element = run._element
        run_element.getparent().remove(run_element)


def _apply_pep_run_style(
    run: Any,
    style: dict[str, Any],
) -> None:
    """
    Aplica formato configurable para campos editados del PEP.

    Args:
        run: Run DOCX.
        style: Diccionario de estilo.
    """
    font_name = style["font_name"]

    run.font.name = font_name
    run.font.size = Pt(style["font_size"])
    run.font.bold = style["bold"]
    run.font.color.rgb = FONT_COLOR

    run_properties = run._element.rPr
    if run_properties is not None:
        run_properties.rFonts.set(qn("w:eastAsia"), font_name)


def _join_people_names(names: list[str] | None) -> str:
    """
    Convierte una lista de personas en texto multilinea.

    Args:
        names: Lista de nombres detectados.

    Returns:
        Texto con una persona por línea o N/A.
    """
    cleaned_names = [
        name.strip()
        for name in (names or [])
        if (name or "").strip()
    ]

    if not cleaned_names:
        return "N/A"

    return "\n".join(cleaned_names)


def _build_bullet_list(items: list[str]) -> str:
    """
    Construye una lista con viñetas para insertar en el PEP.

    Args:
        items: Elementos extraídos del PAP.

    Returns:
        Texto con viñetas o N/A.
    """
    cleaned_items = [
        item.strip()
        for item in items
        if (item or "").strip()
    ]

    if not cleaned_items:
        return "N/A"

    return "\n".join(f"• {item}" for item in cleaned_items)


def _build_tobe_requirement_lines(context: PepContext) -> str:
    """
    Construye la lista numerada de requerimientos TO-BE.

    Args:
        context: Contexto combinado del PEP.

    Returns:
        Texto con requerimientos numerados.
    """
    lines = []

    for requirement in context.tobe.requirements:
        title = _safe_text(requirement.title)
        lines.append(f"{requirement.number}. {title}")

    if not lines:
        return "No se detectaron requerimientos TO-BE."

    return "\n".join(lines)

def _format_issue_date(current_date: date) -> str:
    """
    Formatea la fecha de emisión.

    Args:
        current_date: Fecha actual.

    Returns:
        Fecha en formato dd de mm de aaaa.
    """
    return (
        f"{current_date.day:02d} de "
        f"{current_date.month:02d} de "
        f"{current_date.year}"
    )

def _safe_text(value: str | None) -> str:
    """
    Convierte valores nulos o vacíos a N/A.

    Args:
        value: Texto opcional.

    Returns:
        Texto seguro.
    """
    clean = (value or "").strip()
    return clean or "N/A"