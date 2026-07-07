"""
Vistas Django para el flujo de generación de PEP.

Este módulo mantiene separado el flujo PEP del generador actual de
casos de prueba, reduciendo el riesgo de afectar el proceso existente.
"""
from __future__ import annotations

import hashlib

from typing import Any

from django.conf import settings
from django.http import FileResponse
from django.http import HttpRequest
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from tcgen.services.pep.pep_orchestrator import build_pep_preview
from tcgen.services.pep.pep_orchestrator import generate_pep_document
from tcgen.utils.validators import validate_extension
from tcgen.utils.validators import validate_size

from tcgen.services.pep.pap_schema import validate_pap_payload
from tcgen.services.pep.pep_orchestrator import (
    generate_pep_document_from_validated_data,
)
from tcgen.services.pep.tobe_requirements import extract_tobe_requirements

ALLOWED_DOCUMENT_EXTS = (".pdf", ".docx")
PEP_PAP_CACHE_KEY = "pep_cached_pap_payload"

@require_GET
def pep_home(request: HttpRequest):
    """
    Renderiza la pantalla del generador PEP.

    Args:
        request: Petición HTTP.

    Returns:
        Respuesta HTML.
    """
    return render(request, "tcgen/pep_generator.html")


@require_POST
@require_POST
def pep_preview(request: HttpRequest) -> JsonResponse:
    """
    Genera una previsualización del PEP.

    Recibe PAP y PDD/FDD, extrae la información necesaria y devuelve
    un JSON combinado para la UI. Además, guarda el resultado PAP en
    sesión para evitar una segunda llamada a Claude al generar el DOCX.

    Args:
        request: Petición HTTP con archivos multipart.

    Returns:
        JsonResponse con resumen PAP + TO-BE.
    """
    pap_file = request.FILES.get("pap_document")
    pdd_file = request.FILES.get("pdd_document")

    upload_error = _validate_pep_uploads(
        pap_file=pap_file,
        pdd_file=pdd_file,
    )
    if upload_error:
        return upload_error

    selected_requirements = _parse_selected_requirements(
        request.POST.get("selected_requirements", ""),
    )

    pap_bytes = pap_file.read()
    pdd_bytes = pdd_file.read()
    pap_hash = _hash_bytes(pap_bytes)

    try:
        result = build_pep_preview(
            pap_filename=pap_file.name,
            pap_bytes=pap_bytes,
            pdd_filename=pdd_file.name,
            pdd_bytes=pdd_bytes,
            selected_requirements=selected_requirements,
        )
    except Exception as exc:
        return _json_error(
            code="ERR_PEP_PREVIEW",
            message=str(exc),
            status=400,
        )

    request.session[PEP_PAP_CACHE_KEY] = {
        "pap_hash": pap_hash,
        "pap": result.payload.get("pap"),
    }
    request.session.modified = True

    return JsonResponse(result.payload, status=200)


@require_POST
@require_POST
def pep_generate(request: HttpRequest) -> FileResponse | JsonResponse:
    """
    Genera y descarga el documento PEP final.

    Si existe una extracción PAP cacheada desde la previsualización y
    corresponde al mismo archivo PAP, reutiliza esa información para no
    llamar a Claude por segunda vez.

    Args:
        request: Petición HTTP con PAP, PDD/FDD y selección opcional.

    Returns:
        FileResponse con DOCX o JsonResponse de error.
    """
    pap_file = request.FILES.get("pap_document")
    pdd_file = request.FILES.get("pdd_document")

    upload_error = _validate_pep_uploads(
        pap_file=pap_file,
        pdd_file=pdd_file,
    )
    if upload_error:
        return upload_error

    selected_requirements = _parse_selected_requirements(
        request.POST.get("selected_requirements", ""),
    )

    pap_bytes = pap_file.read()
    pdd_bytes = pdd_file.read()

    try:
        result = _generate_pep_with_cache_fallback(
            request=request,
            pap_filename=pap_file.name,
            pap_bytes=pap_bytes,
            pdd_filename=pdd_file.name,
            pdd_bytes=pdd_bytes,
            selected_requirements=selected_requirements,
        )
    except Exception as exc:
        return _json_error(
            code="ERR_PEP_GENERATE",
            message=str(exc),
            status=400,
        )

    response = FileResponse(
        _bytes_to_stream(result.docx_bytes),
        as_attachment=True,
        filename=result.filename,
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
    response["X-PEP-Filename"] = result.filename

    return response

def _generate_pep_with_cache_fallback(
    *,
    request: HttpRequest,
    pap_filename: str,
    pap_bytes: bytes,
    pdd_filename: str,
    pdd_bytes: bytes,
    selected_requirements: list[int] | None,
):
    """
    Genera el PEP reutilizando la extracción PAP cacheada si es válida.

    Args:
        request: Petición HTTP actual.
        pap_filename: Nombre del PAP.
        pap_bytes: Bytes del PAP.
        pdd_filename: Nombre del PDD/FDD.
        pdd_bytes: Bytes del PDD/FDD.
        selected_requirements: Requerimientos seleccionados.

    Returns:
        Resultado de generación PEP.
    """
    cached_payload = request.session.get(PEP_PAP_CACHE_KEY)
    current_hash = _hash_bytes(pap_bytes)

    if _is_valid_pap_cache(cached_payload, current_hash):
        pap_data = validate_pap_payload(cached_payload["pap"])

        tobe_data = extract_tobe_requirements(
            filename=pdd_filename,
            file_bytes=pdd_bytes,
            selected_requirements=selected_requirements,
        )

        return generate_pep_document_from_validated_data(
            pap_data=pap_data,
            tobe_data=tobe_data,
        )

    return generate_pep_document(
        pap_filename=pap_filename,
        pap_bytes=pap_bytes,
        pdd_filename=pdd_filename,
        pdd_bytes=pdd_bytes,
        selected_requirements=selected_requirements,
    )


def _is_valid_pap_cache(
    cached_payload: Any,
    current_hash: str,
) -> bool:
    """
    Valida si el cache PAP de sesión corresponde al archivo actual.

    Args:
        cached_payload: Payload guardado en sesión.
        current_hash: Hash SHA-256 del PAP actual.

    Returns:
        True si el cache puede reutilizarse.
    """
    if not isinstance(cached_payload, dict):
        return False

    cached_hash = cached_payload.get("pap_hash")
    cached_pap = cached_payload.get("pap")

    if cached_hash != current_hash:
        return False

    if not isinstance(cached_pap, dict):
        return False

    return True


def _hash_bytes(content: bytes) -> str:
    """
    Calcula hash SHA-256 de un contenido binario.

    Args:
        content: Bytes del archivo.

    Returns:
        Hash hexadecimal.
    """
    return hashlib.sha256(content).hexdigest()

def _validate_pep_uploads(
    *,
    pap_file: Any,
    pdd_file: Any,
) -> JsonResponse | None:
    """
    Valida los archivos requeridos para generar el PEP.

    Args:
        pap_file: Archivo PAP subido.
        pdd_file: Archivo PDD/FDD subido.

    Returns:
        JsonResponse si existe error, None si todo es válido.
    """
    if pap_file is None:
        return _json_error(
            code="ERR_NO_PAP",
            message="Debes subir el documento PAP.",
            status=400,
        )

    if pdd_file is None:
        return _json_error(
            code="ERR_NO_PDD",
            message="Debes subir el documento PDD/FDD.",
            status=400,
        )

    pap_error = _validate_single_upload(
        uploaded_file=pap_file,
        label="PAP",
    )
    if pap_error:
        return pap_error

    pdd_error = _validate_single_upload(
        uploaded_file=pdd_file,
        label="PDD/FDD",
    )
    if pdd_error:
        return pdd_error

    return None


def _validate_single_upload(
    *,
    uploaded_file: Any,
    label: str,
) -> JsonResponse | None:
    """
    Valida extensión y tamaño de un archivo.

    Args:
        uploaded_file: Archivo subido.
        label: Nombre lógico del archivo para mensajes.

    Returns:
        JsonResponse de error o None.
    """
    ext_validation = validate_extension(
        uploaded_file.name,
        ALLOWED_DOCUMENT_EXTS,
    )
    if not ext_validation.ok:
        return _json_error(
            code=getattr(ext_validation, "code", "ERR_BAD_EXT"),
            message=(
                f"{label}: "
                f"{getattr(ext_validation, 'message', 'Extensión inválida.')}"
            ),
            status=400,
        )

    size_validation = validate_size(
        uploaded_file.size,
        settings.MAX_UPLOAD_MB,
    )
    if not size_validation.ok:
        return _json_error(
            code=getattr(size_validation, "code", "ERR_TOO_LARGE"),
            message=(
                f"{label}: "
                f"{getattr(size_validation, 'message', 'Archivo demasiado grande.')}"
            ),
            status=400,
        )

    return None


def _parse_selected_requirements(
    raw_value: str,
) -> list[int] | None:
    """
    Convierte una cadena tipo '1,3,5' en lista de enteros.

    Args:
        raw_value: Valor recibido desde POST.

    Returns:
        Lista de números o None cuando no hay selección específica.
    """
    clean_value = (raw_value or "").strip()
    if not clean_value:
        return None

    selected = []

    for item in clean_value.split(","):
        clean_item = item.strip()
        if not clean_item:
            continue

        try:
            number = int(clean_item)
        except ValueError:
            continue

        if number > 0:
            selected.append(number)

    if not selected:
        return None

    return sorted(set(selected))


def _json_error(
    *,
    code: str,
    message: str,
    status: int,
) -> JsonResponse:
    """
    Construye una respuesta JSON de error estándar.

    Args:
        code: Código de error.
        message: Mensaje visible.
        status: HTTP status.

    Returns:
        JsonResponse de error.
    """
    return JsonResponse(
        {
            "ok": False,
            "code": code,
            "message": message,
        },
        status=status,
    )


def _bytes_to_stream(content: bytes):
    """
    Convierte bytes a un stream compatible con FileResponse.

    Args:
        content: Contenido binario.

    Returns:
        BytesIO listo para FileResponse.
    """
    from io import BytesIO

    return BytesIO(content)