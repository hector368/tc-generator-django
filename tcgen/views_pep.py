"""
Vistas Django para el flujo de generación de PEP.

Este módulo mantiene separado el flujo PEP del generador actual de
casos de prueba, reduciendo el riesgo de afectar el proceso existente.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from django.conf import settings
from django.http import FileResponse
from django.http import HttpRequest
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from pydantic import ValidationError

from tcgen.services.pep.pap_schema import validate_pap_payload
from tcgen.services.pep.pdd_schema import validate_pdd_payload
from tcgen.services.pep.pep_orchestrator import (
    build_pep_preview,
    generate_pep_document,
    generate_pep_document_from_validated_data,
)
from tcgen.utils.validators import validate_extension
from tcgen.utils.validators import validate_size


ALLOWED_DOCUMENT_EXTS = (".pdf", ".docx")

PEP_ANALYSIS_CACHE_KEY = "pep_cached_analysis_payload"


@require_GET
def pep_home(request: HttpRequest):
    """
    Renderiza la pantalla del generador PEP.

    Args:
        request: Petición HTTP.

    Returns:
        Respuesta HTML.
    """
    return render(
        request,
        "tcgen/pep_generator.html",
    )


@require_POST
def pep_preview(
    request: HttpRequest,
) -> JsonResponse:
    """
    Genera una previsualización del PEP.

    Analiza PAP y PDD/FDD, calcula los insumos y almacena los resultados
    validados en sesión para reutilizarlos durante la generación del DOCX.

    Args:
        request: Petición HTTP con archivos multipart.

    Returns:
        JsonResponse con los datos analizados del PEP.
    """
    pap_file = request.FILES.get("pap_document")
    pdd_file = request.FILES.get("pdd_document")

    upload_error = _validate_pep_uploads(
        pap_file=pap_file,
        pdd_file=pdd_file,
    )

    if upload_error:
        return upload_error

    pap_bytes = pap_file.read()
    pdd_bytes = pdd_file.read()

    try:
        result = build_pep_preview(
            pap_filename=pap_file.name,
            pap_bytes=pap_bytes,
            pdd_filename=pdd_file.name,
            pdd_bytes=pdd_bytes,
        )
    except Exception as exc:
        return _json_error(
            code="ERR_PEP_PREVIEW",
            message=str(exc),
            status=400,
        )

    request.session[PEP_ANALYSIS_CACHE_KEY] = {
        "pap_hash": _hash_bytes(pap_bytes),
        "pdd_hash": _hash_bytes(pdd_bytes),
        "pap": result.payload.get("pap"),
        "pdd": result.payload.get("pdd"),
    }

    request.session.modified = True

    return JsonResponse(
        result.payload,
        status=200,
    )


@require_POST
def pep_generate(
    request: HttpRequest,
) -> FileResponse | JsonResponse:
    """
    Genera y descarga el documento PEP final.

    Reutiliza los análisis PAP y PDD/FDD almacenados durante la
    previsualización cuando ambos archivos coinciden con el cache.

    Args:
        request: Petición HTTP con PAP y PDD/FDD.

    Returns:
        FileResponse con el DOCX o JsonResponse de error.
    """
    pap_file = request.FILES.get("pap_document")
    pdd_file = request.FILES.get("pdd_document")

    upload_error = _validate_pep_uploads(
        pap_file=pap_file,
        pdd_file=pdd_file,
    )

    if upload_error:
        return upload_error

    pap_bytes = pap_file.read()
    pdd_bytes = pdd_file.read()

    try:
        result = _generate_pep_with_cache_fallback(
            request=request,
            pap_filename=pap_file.name,
            pap_bytes=pap_bytes,
            pdd_filename=pdd_file.name,
            pdd_bytes=pdd_bytes,
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
):
    """
    Genera el PEP reutilizando el análisis cacheado cuando es válido.

    Si el PAP o PDD/FDD cambió, ejecuta nuevamente el flujo completo.

    Args:
        request: Petición HTTP actual.
        pap_filename: Nombre del archivo PAP.
        pap_bytes: Contenido binario del PAP.
        pdd_filename: Nombre del archivo PDD/FDD.
        pdd_bytes: Contenido binario del PDD/FDD.

    Returns:
        Resultado de generación del PEP.
    """
    cached_payload = request.session.get(
        PEP_ANALYSIS_CACHE_KEY,
    )

    current_pap_hash = _hash_bytes(pap_bytes)
    current_pdd_hash = _hash_bytes(pdd_bytes)

    if _is_valid_analysis_cache(
        cached_payload=cached_payload,
        current_pap_hash=current_pap_hash,
        current_pdd_hash=current_pdd_hash,
    ):
        try:
            pap_data = validate_pap_payload(
                cached_payload["pap"],
            )

            pdd_data = validate_pdd_payload(
                cached_payload["pdd"],
            )
        except (
            ValidationError,
            TypeError,
            ValueError,
        ):
            pass
        else:
            return generate_pep_document_from_validated_data(
                pap_data=pap_data,
                pdd_data=pdd_data,
            )

    return generate_pep_document(
        pap_filename=pap_filename,
        pap_bytes=pap_bytes,
        pdd_filename=pdd_filename,
        pdd_bytes=pdd_bytes,
    )


def _is_valid_analysis_cache(
    *,
    cached_payload: Any,
    current_pap_hash: str,
    current_pdd_hash: str,
) -> bool:
    """
    Valida que el cache corresponda al PAP y PDD/FDD actuales.

    Args:
        cached_payload: Información almacenada en sesión.
        current_pap_hash: Hash SHA-256 del PAP actual.
        current_pdd_hash: Hash SHA-256 del PDD/FDD actual.

    Returns:
        True cuando ambos análisis pueden reutilizarse.
    """
    if not isinstance(cached_payload, dict):
        return False

    if (
        cached_payload.get("pap_hash")
        != current_pap_hash
    ):
        return False

    if (
        cached_payload.get("pdd_hash")
        != current_pdd_hash
    ):
        return False

    if not isinstance(
        cached_payload.get("pap"),
        dict,
    ):
        return False

    if not isinstance(
        cached_payload.get("pdd"),
        dict,
    ):
        return False

    return True


def _hash_bytes(
    content: bytes,
) -> str:
    """
    Calcula el hash SHA-256 de un contenido binario.

    Args:
        content: Bytes del archivo.

    Returns:
        Hash hexadecimal.
    """
    return hashlib.sha256(
        content,
    ).hexdigest()


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
        JsonResponse si existe error o None.
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
        label: Nombre lógico usado en los mensajes.

    Returns:
        JsonResponse de error o None.
    """
    ext_validation = validate_extension(
        uploaded_file.name,
        ALLOWED_DOCUMENT_EXTS,
    )

    if not ext_validation.ok:
        return _json_error(
            code=getattr(
                ext_validation,
                "code",
                "ERR_BAD_EXT",
            ),
            message=(
                f"{label}: "
                f"{getattr(
                    ext_validation,
                    'message',
                    'Extensión inválida.',
                )}"
            ),
            status=400,
        )

    size_validation = validate_size(
        uploaded_file.size,
        settings.MAX_UPLOAD_MB,
    )

    if not size_validation.ok:
        return _json_error(
            code=getattr(
                size_validation,
                "code",
                "ERR_TOO_LARGE",
            ),
            message=(
                f"{label}: "
                f"{getattr(
                    size_validation,
                    'message',
                    'Archivo demasiado grande.',
                )}"
            ),
            status=400,
        )

    return None


def _json_error(
    *,
    code: str,
    message: str,
    status: int,
) -> JsonResponse:
    """
    Construye una respuesta JSON de error estándar.

    Args:
        code: Código del error.
        message: Mensaje visible.
        status: Estado HTTP.

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


def _bytes_to_stream(
    content: bytes,
) -> BytesIO:
    """
    Convierte bytes a un stream compatible con FileResponse.

    Args:
        content: Contenido binario.

    Returns:
        Stream BytesIO.
    """
    return BytesIO(content)