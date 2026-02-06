"""
Vistas HTTP para el generador de casos de prueba (tcgen).

Este módulo expone:
- La pantalla principal.
- La generación sincrónica (fallback).
- La generación por streaming (NDJSON).
- La descarga del CSV desde sesión.
"""

from __future__ import annotations

# Importaciones de la librería estándar.
import json
import logging
from typing import Any, Final, Iterator

# Importaciones de terceros (Django).
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

# Importaciones del proyecto.
from core.extractor import SUPPORTED_EXTS
from tcgen.services.orchestrator import iter_stream, run_sync
from tcgen.utils.validators import validate_extension, validate_prompt_file, validate_size

# IDs de Trazabilidad Técnica:
# - TCGEN-WEB-020: Vistas HTTP para carga de PDD, generación y descarga de CSV.
# - TCGEN-WEB-021: Contrato de eventos NDJSON para progreso en frontend.
# - TCGEN-WEB-022: Persistencia del último resultado en sesión para descarga posterior.

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
    "An error occurred while generating test cases. Please check server logs."
)
UI_ERR_ASSIGNED_TO: Final[str] = (
    "Assigned To is required. Please use the exact display name from Azure DevOps."
)


def _session_key() -> str:
    """Obtiene la clave de sesión usada para almacenar el último resultado."""
    return str(getattr(settings, "TCGEN_SESSION_KEY_RESULT", "tcgen_result"))


def _json_error(*, status: int, code: str, message: str) -> JsonResponse:
    """Construye una respuesta JSON de error consistente para la UI."""
    return JsonResponse({"ok": False, "code": code, "message": message}, status=status)


def _validate_upload(*, filename: str, file_size: int) -> JsonResponse | None:
    """
    Valida prompt, extensión y tamaño del archivo.

    Retorna JsonResponse si hay error; retorna None si todo es válido.
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


def _get_upload_or_error(
    request: HttpRequest,
) -> tuple[UploadedFile, str, int, str] | JsonResponse:
    """
    Obtiene el archivo cargado y valida lo esencial.

    Retorna (uploaded, filename, file_size, assigned_to) si es válido; de lo contrario,
    retorna una respuesta JsonResponse de error.
    """
    uploaded = request.FILES.get("document")
    if not uploaded:
        return _json_error(status=400, code="ERR_NO_FILE", message=UI_ERR_NO_FILE)

    assigned_to = (request.POST.get("assigned_to") or "").strip()
    if not assigned_to:
        return _json_error(
            status=400,
            code="ERR_ASSIGNED_TO",
            message=UI_ERR_ASSIGNED_TO,
        )

    filename = uploaded.name or ""
    file_size = int(getattr(uploaded, "size", 0) or 0)

    validation_error = _validate_upload(filename=filename, file_size=file_size)
    if validation_error:
        return validation_error

    return uploaded, filename, file_size, assigned_to


@require_http_methods(["GET"])
def home(request: HttpRequest) -> HttpResponse:
    """Renderiza la pantalla principal del generador."""
    return render(request, "tcgen/index.html")


@require_http_methods(["POST"])
def generate(request: HttpRequest) -> JsonResponse:
    """
    Genera casos de prueba en modo sincrónico.

    Nota: Se mantiene este endpoint como fallback para no romper integraciones o pruebas existentes.
    """
    result = _get_upload_or_error(request)
    if isinstance(result, JsonResponse):
        return result

    uploaded, filename, _file_size, assigned_to = result

    try:
        file_bytes = uploaded.read()
        payload = run_sync(
            original_filename=filename,
            file_bytes=file_bytes,
            assigned_to=assigned_to,
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
        return _json_error(status=400, code="ERR_VALIDATION", message=str(exc))

    except Exception:
        logger.exception("Generation failed")
        return _json_error(status=500, code="ERR_ENGINE", message=UI_ERR_ENGINE)


@require_http_methods(["POST"])
def generate_stream(request: HttpRequest) -> HttpResponse:
    """Genera casos de prueba en modo streaming (NDJSON)."""
    result = _get_upload_or_error(request)
    if isinstance(result, JsonResponse):
        return result

    uploaded, filename, _file_size, assigned_to = result
    file_bytes = uploaded.read()

    def ndjson(obj: dict[str, Any]) -> str:
        """Serializa un objeto a NDJSON preservando acentos."""
        return json.dumps(obj, ensure_ascii=False) + "\n"

    def event_iter() -> Iterator[str]:
        """
        Itera eventos del motor y los emite como NDJSON.

        Si llega un evento final, se guarda en sesión el CSV para descarga.
        """
        try:
            for evt in iter_stream(
                original_filename=filename,
                file_bytes=file_bytes,
                assigned_to=assigned_to,
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

    resp = StreamingHttpResponse(event_iter(), content_type=CONTENT_TYPE_NDJSON)
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@require_http_methods(["GET"])
def download_csv(request: HttpRequest) -> HttpResponse:
    """Descarga el CSV generado previamente desde la sesión."""
    payload = request.session.get(_session_key())
    if not payload:
        return HttpResponse(
            (
                "No generated CSV found in session. Please generate test cases first."
            ),
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

    resp = HttpResponse(csv_out.encode("utf-8-sig"), content_type=CONTENT_TYPE_CSV)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "no-store"
    return resp
