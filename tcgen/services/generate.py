"""
Servicio sincrónico de generación de casos de prueba.

Este módulo consume el motor de eventos y retorna un resultado final
normalizado para uso en capas superiores (orquestador y vistas).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from tcgen.services.engine import iter_generation_events
EVENT_ERROR: Final[str] = "error"
EVENT_DONE: Final[str] = "done"
DEFAULT_FILENAME: Final[str] = "TC.csv"
ERR_DEFAULT_MESSAGE: Final[str] = "Generation failed."


@dataclass(frozen=True)
class GenerationResult:
    """
    Resultado de una ejecución sincrónica de generación.

    Nota:
        csv_out contiene únicamente el cuerpo del CSV, sin encabezado.
        El encabezado se asegura en otra capa del servicio.
    """

    csv_out: str
    usage: dict[str, Any]
    elapsed_seconds: float
    stats: dict[str, Any]
    download_filename: str


def generate_test_cases_sync(
    *,
    filename: str,
    file_bytes: bytes,
    assigned_to: str,
) -> GenerationResult:
    """
    Consume el motor de eventos y devuelve el último evento final.

    Raises:
        ValueError: Si se recibe un evento de error o si no existe un evento final.
    """
    last_done: dict[str, Any] | None = None

    for evt in iter_generation_events(
        filename=filename,
        file_bytes=file_bytes,
        assigned_to=assigned_to,
    ):
        evt_type = evt.get("type")

        if evt_type == EVENT_ERROR:
            raise ValueError(evt.get("message") or ERR_DEFAULT_MESSAGE)

        if evt_type == EVENT_DONE:
            last_done = evt

    if last_done is None:
        raise ValueError(
            "The generation ended unexpectedly without a final result."
        )

    return GenerationResult(
        csv_out=last_done.get("csv_body") or "",
        usage=last_done.get("usage") or {},
        elapsed_seconds=float(last_done.get("elapsed") or 0),
        stats=last_done.get("stats") or {},
        download_filename=(
            last_done.get("download_filename") or DEFAULT_FILENAME
        ),
    )
