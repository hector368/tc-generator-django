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
from typing import Any, Final

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Constantes de configuración.
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"
DEFAULT_TEMPERATURE: Final[int] = 0


def get_client() -> Anthropic:
    """
    Crea un cliente de Anthropic usando la clave desde variables de entorno.

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
    Ejecuta una llamada al modelo y retorna el texto y las métricas de uso.

    Notas:
    - Se concatenan múltiples bloques de salida para evitar pérdida de contenido.
    - El diccionario de usage siempre retorna enteros (0 si no están disponibles).

    Args:
        client: Cliente de Anthropic configurado.
        system_prompt: Prompt del sistema con instrucciones.
        user_text: Texto de entrada del usuario.
        model: Identificador del modelo a usar.
        max_tokens: Límite máximo de tokens de salida.

    Returns:
        Una tupla con:
        - output_text: Texto generado por el modelo.
        - usage: Diccionario con input_tokens y output_tokens.

    Raises:
        Exception: Si falla la llamada al modelo (se registra en logs y se relanza).
    """
    try:
        msg = client.messages.create(
            model=model,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception:
        logger.exception("Falló la llamada al modelo Claude.")
        raise

    output_text = _join_text_blocks(getattr(msg, "content", None))
    usage = _extract_usage(getattr(msg, "usage", None))
    return output_text, usage


def _join_text_blocks(content: Any) -> str:
    """
    Concatena los bloques de texto de la respuesta en un solo string.

    Esta función es tolerante a respuestas sin contenido o con estructura parcial.
    """
    parts: list[str] = []
    for block in content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)

    return "\n".join(parts).strip()


def _extract_usage(msg_usage: Any) -> dict[str, int]:
    """
    Extrae métricas de tokens desde el objeto usage.

    Retorna 0 cuando no existen métricas.
    """
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    if not msg_usage:
        return usage

    input_tokens = getattr(msg_usage, "input_tokens", 0)
    output_tokens = getattr(msg_usage, "output_tokens", 0)

    usage["input_tokens"] = int(input_tokens or 0)
    usage["output_tokens"] = int(output_tokens or 0)
    return usage
