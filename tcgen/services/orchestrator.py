"""
Orquestador de generacion de casos de prueba.

Este modulo expone una API estable para las vistas en modo sincronico
y en modo streaming, encargandose de construir los payloads de respuesta
y transformar los eventos del motor de generacion.
"""

from __future__ import annotations

# Importaciones de libreria estandar.
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


# Construye el nombre de descarga CSV conservando el stem y añadiendo sufijo.
def build_download_filename(original_filename: str) -> str:
    """
    Args:
        original_filename: Nombre del archivo original subido.

    Returns:
        Nombre del archivo de descarga con sufijo de casos de prueba.
    """
    stem = Path(original_filename).stem
    return f"{stem}_TC.csv"


# Construye un payload estandarizado para sesion y respuestas JSON.
def build_payload(
    *,
    filename: str,
    csv_body: str,
    usage: dict[str, Any] | None,
    elapsed: float | None,
    stats: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Garantiza que el CSV incluya el encabezado requerido por Azure
    DevOps y normaliza los campos opcionales para evitar valores nulos
    en la respuesta.

    Args:
        filename: Nombre del archivo de descarga generado.
        csv_body: Contenido CSV sin procesar producido por el motor.
        usage: Metricas de uso del modelo. Se normaliza a diccionario
            vacio si no se proporciona.
        elapsed: Tiempo transcurrido en segundos. Se normaliza a cero
            si no se proporciona.
        stats: Estadisticas de la generacion. Se normaliza a diccionario
            vacio si no se proporciona.

    Returns:
        Diccionario con los campos del payload listos para sesion o JSON.
    """
    csv_out = ensure_csv_header(csv_body)
    return {
        "filename": filename,
        "csv_out": csv_out,
        "usage": usage or {},
        "elapsed": float(elapsed or 0),
        "stats": stats or {},
    }


# Genera eventos para streaming NDJSON durante la creación de casos de prueba.
def run_sync(
    *,
    original_filename: str,
    file_bytes: bytes,
    assigned_to: str,
    selected_requirements: list[int] | None = None,
) -> dict[str, Any]:
    """
    Invoca el motor de generacion y construye el payload resultante
    listo para almacenar en sesion o responder como JSON.
    Args:
        original_filename: Nombre del archivo original subido.
        file_bytes: Contenido binario del archivo.
        assigned_to: Usuario al que se asignaran los casos de prueba.
        selected_requirements: Lista de indices de requerimientos a
            procesar. Si es None, se procesan todos los disponibles.

    Returns:
        Payload con el resultado de la generacion.
    """
    result = generate_test_cases_sync(
        filename=original_filename,
        file_bytes=file_bytes,
        assigned_to=assigned_to,
        selected_requirements=selected_requirements,
    )

    filename = (
        result.download_filename
        or build_download_filename(original_filename)
    )

    return build_payload(
        filename=filename,
        csv_body=result.csv_out,
        usage=result.usage,
        elapsed=result.elapsed_seconds,
        stats=result.stats,
    )


# Genera eventos para streaming NDJSON durante la creación de casos de prueba.
def iter_stream(
    *,
    original_filename: str,
    file_bytes: bytes,
    assigned_to: str,
    selected_requirements: list[int] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Reenvía los eventos intermedios del motor sin modificacion.
    Al recibir el evento de finalizacion, lo transforma en un payload
    completo que incluye el CSV con encabezado, su codificacion en
    base64 y los metadatos de la generacion.

    Args:
        original_filename: Nombre del archivo original subido.
        file_bytes: Contenido binario del archivo.
        assigned_to: Usuario al que se asignaran los casos de prueba.
        selected_requirements: Lista de indices de requerimientos a
            procesar. Si es None, se procesan todos los disponibles.

    Yields:
        Diccionarios con los eventos de progreso y el evento final
        de finalizacion con el payload completo.
    """
    for evt in iter_generation_events(
        filename=original_filename,
        file_bytes=file_bytes,
        assigned_to=assigned_to,
        selected_requirements=selected_requirements,
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


# Codifica el contenido CSV en base64 para su transmision.
def _encode_csv_b64(csv_out: str) -> str:
    """
    Utiliza codificacion UTF-8 con BOM para garantizar la compatibilidad
    con hojas de calculo al momento de la descarga.

    Args:
        csv_out: Contenido CSV con encabezado listo para descargar.

    Returns:
        Cadena ASCII con el contenido CSV codificado en base64.
    """
    return base64.b64encode(
        csv_out.encode(CSV_EXCEL_ENCODING)
    ).decode("ascii")