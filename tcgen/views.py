"""
Vistas HTTP para el generador de casos de prueba.

Este modulo expone la pantalla principal, la generacion sincronica,
la generacion por streaming, la descarga del CSV desde sesion y el
analisis del documento sin ejecutar el LLM.
"""
from __future__ import annotations

# Importaciones de la libreria estandar.
import json
import logging
import re
from typing import Any, Final, Iterator

# Importaciones de terceros (Django).
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

# Importaciones del proyecto.
from core.extractor import SUPPORTED_EXTS, extract_text_from_upload
from core.requirements_segmenter import segment_requirements_flexible
from core.requirements_splitter import extract_project_id
from tcgen.services.orchestrator import iter_stream, run_sync
from tcgen.utils.validators import (
    validate_extension,
    validate_prompt_file,
    validate_size,
)

logger = logging.getLogger(__name__)

EVENT_DONE: Final[str] = "done"

CONTENT_TYPE_NDJSON: Final[str] = "application/x-ndjson; charset=utf-8"
CONTENT_TYPE_CSV: Final[str] = "text/csv; charset=utf-8"
CONTENT_TYPE_TEXT: Final[str] = "text/plain; charset=utf-8"

UI_ERR_NO_FILE: Final[str] = "Please upload a file to continue."
UI_ERR_PROMPT_FILE: Final[str] = "Prompt file is invalid or missing."
UI_ERR_BAD_EXT: Final[str] = "Unsupported file type. Allowed: .pdf, .docx."
UI_ERR_TOO_LARGE: Final[str] = "The file exceeds the maximum allowed size."
UI_ERR_EMPTY_OUTPUT: Final[str] = (
    "The generated output is empty. Please try a different document."
)
UI_ERR_ENGINE: Final[str] = (
    "An error occurred while generating test cases. "
    "Please check server logs."
)
UI_ERR_ASSIGNED_TO: Final[str] = (
    "Assigned To is required. "
    "Please use the exact display name from Azure DevOps."
)
UI_ERR_ANALYZE: Final[str] = "No se pudo analizar el documento."


# Retorna la clave de sesión para almacenar el último resultado de generación.
def _session_key() -> str:
    """
    Returns:
        Cadena con la clave de sesion configurada o el valor por defecto.
    """
    return str(getattr(settings, "TCGEN_SESSION_KEY_RESULT", "tcgen_result"))


# Construye una respuesta JSON de error con estructura consistente para la UI.
def _json_error(*, status: int, code: str, message: str) -> JsonResponse:
    """
    Args:
        status: Codigo de estado HTTP de la respuesta.
        code: Identificador del tipo de error.
        message: Mensaje legible para el usuario.

    Returns:
        JsonResponse con el payload de error y el codigo de estado
        indicado.
    """
    return JsonResponse(
        {"ok": False, "code": code, "message": message},
        status=status,
    )


# Valida el archivo subido para el flujo de generacion.
def _validate_generation_upload(
    *,
    filename: str,
    file_size: int,
) -> JsonResponse | None:
    """
    Verifica que el archivo de prompt sea valido, que la extension
    del archivo este entre las permitidas y que su tamaño no supere
    el limite configurado.

    Args:
        filename: Nombre del archivo subido.
        file_size: Tamaño del archivo en bytes.

    Returns:
        JsonResponse con el error si alguna validacion falla, o None
        si todas las validaciones son exitosas.
    """
    vr = validate_prompt_file(settings.PROMPT_FILE)
    if not vr.ok:
        return _json_error(
            status=400,
            code="ERR_PROMPT_FILE",
            message=vr.message or UI_ERR_PROMPT_FILE,
        )

    vr = validate_extension(filename, SUPPORTED_EXTS)
    if not vr.ok:
        return _json_error(
            status=400,
            code="ERR_BAD_EXT",
            message=vr.message or UI_ERR_BAD_EXT,
        )

    vr = validate_size(file_size, settings.MAX_UPLOAD_MB)
    if not vr.ok:
        return _json_error(
            status=400,
            code="ERR_TOO_LARGE",
            message=vr.message or UI_ERR_TOO_LARGE,
        )

    return None


# Valida el archivo subido para el flujo de analisis.
def _validate_analyze_upload(
    *,
    filename: str,
    file_size: int,
) -> JsonResponse | None:
    """
    Verifica extension y tamaño unicamente. El archivo de prompt no
    se valida porque el analisis no invoca al LLM.

    Args:
        filename: Nombre del archivo subido.
        file_size: Tamaño del archivo en bytes.

    Returns:
        JsonResponse con el error si alguna validacion falla, o None
        si todas las validaciones son exitosas.
    """
    vr = validate_extension(filename, SUPPORTED_EXTS)
    if not vr.ok:
        return _json_error(
            status=400,
            code="ERR_BAD_EXT",
            message=vr.message or UI_ERR_BAD_EXT,
        )

    vr = validate_size(file_size, settings.MAX_UPLOAD_MB)
    if not vr.ok:
        return _json_error(
            status=400,
            code="ERR_TOO_LARGE",
            message=vr.message or UI_ERR_TOO_LARGE,
        )

    return None


# Obtiene el archivo subido y valida campos requeridos para la generación.
def _get_upload_for_generation_or_error(
    request: HttpRequest,
) -> tuple[UploadedFile, str, int, str] | JsonResponse:
    """
    Args:
        request: Solicitud HTTP con el archivo y los datos del formulario.

    Returns:
        Tupla con el archivo subido, el nombre del archivo, el tamaño
        en bytes y el valor de Assigned To si todo es valido, o
        JsonResponse de error en caso contrario.
    """
    uploaded = request.FILES.get("document")
    if not uploaded:
        return _json_error(
            status=400,
            code="ERR_NO_FILE",
            message=UI_ERR_NO_FILE,
        )

    assigned_to = (request.POST.get("assigned_to") or "").strip()
    if not assigned_to:
        return _json_error(
            status=400,
            code="ERR_ASSIGNED_TO",
            message=UI_ERR_ASSIGNED_TO,
        )

    filename = uploaded.name or ""
    file_size = int(getattr(uploaded, "size", 0) or 0)

    validation_error = _validate_generation_upload(
        filename=filename,
        file_size=file_size,
    )
    if validation_error:
        return validation_error

    return uploaded, filename, file_size, assigned_to


# Obtiene el archivo subido y valida campos requeridos para el análisis.
def _get_upload_for_analyze_or_error(
    request: HttpRequest,
) -> tuple[UploadedFile, str, int] | JsonResponse:
    """
    Args:
        request: Solicitud HTTP con el archivo del formulario.

    Returns:
        Tupla con el archivo subido, el nombre del archivo y el tamaño
        en bytes si todo es valido, o JsonResponse de error en caso
        contrario.
    """
    uploaded = request.FILES.get("document")
    if not uploaded:
        return _json_error(
            status=400,
            code="ERR_NO_FILE",
            message=UI_ERR_NO_FILE,
        )

    filename = uploaded.name or ""
    file_size = int(getattr(uploaded, "size", 0) or 0)

    validation_error = _validate_analyze_upload(
        filename=filename,
        file_size=file_size,
    )
    if validation_error:
        return validation_error

    return uploaded, filename, file_size


# Convierte la selección de requerimientos en una lista ordenada de enteros.
def _parse_selected_requirements(raw: str | None) -> list[int] | None:
    """
    Acepta numeros separados por comas o espacios, y rangos con guion.
    Retorna None cuando la cadena esta vacia, lo que indica que se
    deben procesar todos los requerimientos disponibles.

    Args:
        raw: Cadena con la seleccion de requerimientos del formulario.

    Returns:
        Lista ordenada de numeros de requerimiento seleccionados, o
        None si la cadena esta vacia.
    """
    s = (raw or "").strip()
    if not s:
        return None

    nums: set[int] = set()
    parts = re.split(r"[,\s]+", s)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            a, b = part.split("-", 1)
            a_i = int(a.strip())
            b_i = int(b.strip())
            if a_i > b_i:
                a_i, b_i = b_i, a_i
            for n in range(a_i, b_i + 1):
                nums.add(n)
        else:
            nums.add(int(part))

    return sorted(nums)


@require_http_methods(["GET"])
# Renderiza la pantalla principal del generador.
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "tcgen/index.html")


@require_http_methods(["POST"])
# Analiza el documento y retorna el ID del proyecto y requerimientos sin LLM.
def analyze_document(request: HttpRequest) -> JsonResponse:
    """
    Args:
        request: Solicitud HTTP con el archivo del formulario.

    Returns:
        JsonResponse con el ID del proyecto, el metodo de segmentacion,
        el total de bloques y la lista de requerimientos detectados,
        o un error si el analisis falla.
    """
    result = _get_upload_for_analyze_or_error(request)
    if isinstance(result, JsonResponse):
        return result

    uploaded, filename, _file_size = result

    try:
        file_bytes = uploaded.read()

        doc_text = extract_text_from_upload(filename, file_bytes)
        project_id = extract_project_id(doc_text, filename=filename)

        seg = segment_requirements_flexible(
            doc_text,
            project_id=(project_id or ""),
        )

        requirements = [
            {
                "number": int(b.requirement_number),
                "title": (b.scenario_name or "").strip(),
            }
            for b in (seg.blocks or [])
        ]

        # Se limita la respuesta para evitar payloads excesivamente
        # grandes en documentos con muchos requerimientos.
        max_reqs = 400
        truncated = False
        if len(requirements) > max_reqs:
            requirements = requirements[:max_reqs]
            truncated = True

        return JsonResponse(
            {
                "ok": True,
                "project_id": project_id,
                "method": seg.method,
                "total_blocks": len(seg.blocks or []),
                "requirements": requirements,
                "truncated": truncated,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except Exception:
        logger.exception("Analyze document failed")
        return _json_error(
            status=500,
            code="ERR_ANALYZE",
            message=UI_ERR_ANALYZE,
        )


@require_http_methods(["POST"])
# Genera casos de prueba en modo sincronico.
def generate(request: HttpRequest) -> JsonResponse:
    """
    Se mantiene como fallback para no romper integraciones existentes.

    Args:
        request: Solicitud HTTP con el archivo y los datos del formulario.

    Returns:
        JsonResponse con el resultado de la generacion o un error si
        el proceso falla.
    """
    result = _get_upload_for_generation_or_error(request)
    if isinstance(result, JsonResponse):
        return result

    uploaded, filename, _file_size, assigned_to = result
    selected_numbers = _parse_selected_requirements(
        request.POST.get("selected_requirements")
    )

    try:
        file_bytes = uploaded.read()
        payload = run_sync(
            original_filename=filename,
            file_bytes=file_bytes,
            assigned_to=assigned_to,
            selected_requirements=selected_numbers,
        )

        if not (payload.get("csv_out") or "").strip():
            return _json_error(
                status=400,
                code="ERR_EMPTY_OUTPUT",
                message=UI_ERR_EMPTY_OUTPUT,
            )

        request.session[_session_key()] = payload
        request.session.modified = True

        return JsonResponse(
            {
                "ok": True,
                "code": "OK_GENERATED",
                "message": "Test cases generated successfully.",
                "filename": payload.get("filename") or "TC.csv",
                "usage": payload.get("usage") or {},
                "elapsed": payload.get("elapsed") or 0,
                "stats": payload.get("stats") or {},
            }
        )

    except ValueError as exc:
        logger.warning("Generation validation failed: %s", exc)
        return _json_error(
            status=400,
            code="ERR_VALIDATION",
            message=str(exc),
        )

    except Exception:
        logger.exception("Generation failed")
        return _json_error(
            status=500,
            code="ERR_ENGINE",
            message=UI_ERR_ENGINE,
        )


@require_http_methods(["POST"])
# Genera casos de prueba en modo streaming emitiendo eventos NDJSON.
def generate_stream(request: HttpRequest) -> HttpResponse:
    """
    Args:
        request: Solicitud HTTP con el archivo y los datos del formulario.

    Returns:
        StreamingHttpResponse con los eventos de progreso y el evento
        final de finalizacion, o JsonResponse de error si la validacion
        falla antes de iniciar el streaming.
    """
    result = _get_upload_for_generation_or_error(request)
    if isinstance(result, JsonResponse):
        return result

    uploaded, filename, _file_size, assigned_to = result
    selected_numbers = _parse_selected_requirements(
        request.POST.get("selected_requirements")
    )

    file_bytes = uploaded.read()


    # Serializa un diccionario a una línea NDJSON preservando tildes.
    def ndjson(obj: dict[str, Any]) -> str:
        """
        Args:
            obj: Diccionario a serializar.

        Returns:
            Cadena JSON terminada en salto de linea.
        """
        return json.dumps(obj, ensure_ascii=False) + "\n"

    # Itera los eventos del motor y los emite como NDJSON.
    def event_iter() -> Iterator[str]:
        """
        Al recibir el evento de finalizacion, almacena el payload en
        sesion para permitir la descarga posterior del CSV.

        Yields:
            Lineas NDJSON con cada evento del motor o con el evento de
            error si ocurre una excepcion durante el streaming.
        """
        try:
            for evt in iter_stream(
                original_filename=filename,
                file_bytes=file_bytes,
                assigned_to=assigned_to,
                selected_requirements=selected_numbers,
            ):
                if evt.get("type") == EVENT_DONE:
                    payload = {
                        "filename": evt.get("filename") or "TC.csv",
                        "csv_out": evt.get("csv_out") or "",
                        "usage": evt.get("usage") or {},
                        "elapsed": evt.get("elapsed") or 0,
                        "stats": evt.get("stats") or {},
                    }
                    request.session[_session_key()] = payload
                    request.session.modified = True

                yield ndjson(evt)

        except Exception:
            logger.exception("Streaming generation failed")
            yield ndjson(
                {
                    "type": "error",
                    "code": "ERR_ENGINE",
                    "message": UI_ERR_ENGINE,
                }
            )

    resp = StreamingHttpResponse(
        event_iter(),
        content_type=CONTENT_TYPE_NDJSON,
    )
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@require_http_methods(["GET"])
# Descarga el CSV generado previamente almacenado en la sesion.
def download_csv(request: HttpRequest) -> HttpResponse:
    """
    Args:
        request: Solicitud HTTP entrante.

    Returns:
        HttpResponse con el archivo CSV listo para descarga, o una
        respuesta de error si no hay resultado en sesion o el contenido
        esta vacio.
    """
    payload = request.session.get(_session_key())
    if not payload:
        return HttpResponse(
            "No generated CSV found in session. "
            "Please generate test cases first.",
            status=404,
            content_type=CONTENT_TYPE_TEXT,
        )

    filename = payload.get("filename") or "TC.csv"
    csv_out = payload.get("csv_out") or ""

    if not csv_out.strip():
        return HttpResponse(
            "CSV content is empty. Please generate test cases again.",
            status=400,
            content_type=CONTENT_TYPE_TEXT,
        )

    resp = HttpResponse(
        csv_out.encode("utf-8-sig"),
        content_type=CONTENT_TYPE_CSV,
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "no-store"
    return resp