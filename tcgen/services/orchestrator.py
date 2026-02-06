"""
Orquestador de generación de casos de prueba.

Este módulo expone una API estable para las vistas:
- Modo sincrónico: ejecuta generación y retorna payload para sesión/JSON.
- Modo streaming: emite eventos NDJSON y transforma el evento final (done).
"""

from __future__ import annotations

# Importaciones de librería estándar.
import base64
from pathlib import Path
from typing import Any, Final, Iterator

# Importaciones del proyecto.
from core.ado_csv import ensure_csv_header
from tcgen.services.engine import iter_generation_events
from tcgen.services.generate import generate_test_cases_sync

EVENT_DONE: Final[str] = "done"
DEFAULT_OK_CODE: Final[str] = "OK_GENERATED"
DEFAULT_OK_MESSAGE: Final[str] = "Test cases generated successfully."
CSV_EXCEL_ENCODING: Final[str] = "utf-8-sig"


def build_download_filename(original_filename: str) -> str:
    """
    Construye el nombre del archivo de descarga con base en el archivo original.

    Nota:
    - Conserva el stem del archivo (sin extensión) y añade sufijo `_TC.csv`.
    """
    stem = Path(original_filename).stem
    return f"{stem}_TC.csv"


def build_payload(
    *,
    filename: str,
    csv_body: str,
    usage: dict[str, Any] | None,
    elapsed: float | None,
    stats: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Construye un payload consistente para sesión y respuestas.

    - Asegura que el CSV tenga encabezado compatible con Azure DevOps.
    - Normaliza campos opcionales para evitar nulos.
    """
    csv_out = ensure_csv_header(csv_body)
    return {
        "filename": filename,
        "csv_out": csv_out,
        "usage": usage or {},
        "elapsed": float(elapsed or 0),
        "stats": stats or {},
    }


def run_sync(
    *,
    original_filename: str,
    file_bytes: bytes,
    assigned_to: str,
) -> dict[str, Any]:
    """
    Ejecuta la generación en modo sincrónico.

    Retorna un payload listo para almacenar en sesión y responder como JSON.
    """
    result = generate_test_cases_sync(
        filename=original_filename,
        file_bytes=file_bytes,
        assigned_to=assigned_to,
    )

    filename = result.download_filename or build_download_filename(original_filename)

    return build_payload(
        filename=filename,
        csv_body=result.csv_out,
        usage=result.usage,
        elapsed=result.elapsed_seconds,
        stats=result.stats,
    )


def iter_stream(
    *,
    original_filename: str,
    file_bytes: bytes,
    assigned_to: str,
) -> Iterator[dict[str, Any]]:
    """
    Genera eventos para streaming NDJSON.

    - Reenvía eventos intermedios sin cambios.
    - Transforma el evento final a un payload completo para la UI, incluyendo:
      - filename
      - csv_out (con encabezado)
      - csv_b64 (para descarga directa)
      - csv_body (sin encabezado, si el motor lo proporciona)
    """
    for evt in iter_generation_events(
        filename=original_filename,
        file_bytes=file_bytes,
        assigned_to=assigned_to,
    ):
        if evt.get("type") != EVENT_DONE:
            yield evt
            continue

        filename = evt.get("download_filename") or build_download_filename(
            original_filename
        )
        csv_body = evt.get("csv_body") or ""

        payload = build_payload(
            filename=filename,
            csv_body=csv_body,
            usage=evt.get("usage") or {},
            elapsed=evt.get("elapsed") or 0,
            stats=evt.get("stats") or {},
        )

        csv_b64 = _encode_csv_b64(payload["csv_out"])

        yield {
            "type": EVENT_DONE,
            "ok": True,
            "code": evt.get("code") or DEFAULT_OK_CODE,
            "message": evt.get("message") or DEFAULT_OK_MESSAGE,
            "filename": payload["filename"],
            "usage": payload["usage"],
            "elapsed": payload["elapsed"],
            "stats": payload["stats"],
            "csv_b64": csv_b64,
            "csv_out": payload["csv_out"],
            "csv_body": csv_body,
        }


def _encode_csv_b64(csv_out: str) -> str:
    """
    Convierte el CSV final a base64 usando UTF-8 con BOM.

    Se conserva `utf-8-sig` para compatibilidad con Excel.
    """
    return base64.b64encode(csv_out.encode(CSV_EXCEL_ENCODING)).decode("ascii")
