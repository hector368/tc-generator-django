"""
Cliente de integración con el modelo Claude (Anthropic).

Este módulo encapsula la comunicación con la API de Claude y expone funciones
utilitarias para:
- Construir el cliente desde variables de entorno.
- Ejecutar una llamada al modelo con system_prompt + user_text.
- Retornar el texto generado y métricas de uso (tokens) sin lógica de negocio.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Final

import anthropic
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Constantes de configuración.
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"
DEFAULT_TEMPERATURE: Final[int] = 0

# Retries (configurables por env).
ENV_MAX_RETRIES: Final[str] = "CLAUDE_MAX_RETRIES"          # default 3
ENV_BACKOFF_BASE: Final[str] = "CLAUDE_RETRY_BACKOFF_BASE"  # default 1.0
ENV_BACKOFF_MAX: Final[str] = "CLAUDE_RETRY_BACKOFF_MAX"    # default 10.0
ENV_LOG_SIZES: Final[str] = "CLAUDE_LOG_SIZES"              # default 1 (log chars)

TRANSIENT_STATUS: Final[set[int]] = {429, 500, 502, 503, 504, 529}


def get_client() -> Anthropic:
    """
    Returns:
        Cliente de Anthropic configurado.

    Raises:
        RuntimeError: Si falta la clave API en las variables de entorno.
    """
    api_key = (os.getenv(ENV_API_KEY) or "").strip()
    if not api_key:
        raise RuntimeError(f"Falta {ENV_API_KEY} en las variables de entorno.")

    return Anthropic(api_key=api_key)


def call_claude(
    *,
    client: Anthropic,
    system_prompt: str,
    user_text: str,
    model: str,
    max_tokens: int,
) -> tuple[str, dict[str, int]]:
    """
    Ejecuta una llamada al modelo y retorna el texto y métricas de uso.

    Implementa retry con backoff (solo para errores transitorios).
    """
    max_retries = _env_int(ENV_MAX_RETRIES, 3)
    backoff_base = _env_float(ENV_BACKOFF_BASE, 1.0)
    backoff_max = _env_float(ENV_BACKOFF_MAX, 10.0)
    log_sizes = _env_bool(ENV_LOG_SIZES, True)

    if log_sizes:
        logger.info(
            "Claude request: model=%s system_chars=%s user_chars=%s max_tokens=%s retries=%s",
            model,
            len(system_prompt or ""),
            len(user_text or ""),
            max_tokens,
            max_retries,
        )

    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            msg = client.messages.create(
                model=model,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            output_text = _join_text_blocks(getattr(msg, "content", None))
            usage = _extract_usage(getattr(msg, "usage", None))
            return output_text, usage

        except Exception as exc:  # noqa: BLE001 (controlado por _is_transient)
            last_exc = exc
            status = _get_status_code(exc)
            req_id = _get_request_id(exc)

            is_transient = _is_transient_error(exc, status=status)
            if is_transient and attempt < max_retries:
                sleep_s = min(backoff_max, (backoff_base * (2 ** (attempt - 1))) + random.uniform(0, 0.6))
                logger.warning(
                    "Claude transient error (status=%s) attempt=%s/%s request_id=%s; retry in %.2fs",
                    status,
                    attempt,
                    max_retries,
                    req_id,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            # No transitorio o sin más retries.
            logger.exception(
                "Falló la llamada al modelo Claude (status=%s, request_id=%s, attempt=%s/%s).",
                status,
                req_id,
                attempt,
                max_retries,
            )
            raise

    # En teoría no llega aquí, pero por seguridad:
    if last_exc:
        raise last_exc

    raise RuntimeError("Falló la llamada al modelo Claude por una causa desconocida.")


def _join_text_blocks(content: Any) -> str:
    parts: list[str] = []
    for block in content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_usage(msg_usage: Any) -> dict[str, int]:
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    if not msg_usage:
        return usage

    usage["input_tokens"] = int(getattr(msg_usage, "input_tokens", 0) or 0)
    usage["output_tokens"] = int(getattr(msg_usage, "output_tokens", 0) or 0)
    return usage


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _get_status_code(exc: Exception) -> int | None:
    # Anthropic SDK suele exponer .status_code en errores HTTP.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status

    # Fallback: algunas variantes tienen response/status
    resp = getattr(exc, "response", None)
    status2 = getattr(resp, "status_code", None)
    if isinstance(status2, int):
        return status2

    return None


def _get_request_id(exc: Exception) -> str | None:
    # A veces existe .request_id
    rid = getattr(exc, "request_id", None)
    if isinstance(rid, str) and rid.strip():
        return rid.strip()

    # A veces viene en el body dict
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        rid2 = body.get("request_id")
        if isinstance(rid2, str) and rid2.strip():
            return rid2.strip()

    return None


def _is_transient_error(exc: Exception, *, status: int | None) -> bool:
    # 1) Por status code
    if status in TRANSIENT_STATUS:
        return True

    # 2) Por tipo de excepción (timeouts / red)
    # Estas clases existen en el SDK moderno; si no existen, getattr retorna None y no rompe.
    timeout_cls = getattr(anthropic, "APITimeoutError", None)
    conn_cls = getattr(anthropic, "APIConnectionError", None)
    if timeout_cls and isinstance(exc, timeout_cls):
        return True
    if conn_cls and isinstance(exc, conn_cls):
        return True

    # 3) Por nombre (compatibilidad)
    name = exc.__class__.__name__.lower()
    if "timeout" in name or "connection" in name or "temporar" in name:
        return True
    if "internalservererror" in name or "serviceunavailable" in name:
        return True

    return False