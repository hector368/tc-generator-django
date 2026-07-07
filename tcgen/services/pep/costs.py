"""
Cálculo de costo estimado para ejecuciones del flujo PEP.

El costo se calcula con base en tokens reportados por Claude y precios
configurables por variables de entorno.
"""

from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def build_cost_payload(usage: dict[str, int]) -> dict[str, Any]:
    """
    Construye un payload de costo estimado.

    Args:
        usage: Métricas de tokens reportadas por Claude.

    Returns:
        Diccionario serializable con costos estimados.
    """
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)

    input_rate = _get_decimal_env("CLAUDE_INPUT_USD_PER_MTOK")
    output_rate = _get_decimal_env("CLAUDE_OUTPUT_USD_PER_MTOK")

    input_cost = _calculate_token_cost(input_tokens, input_rate)
    output_cost = _calculate_token_cost(output_tokens, output_rate)
    total_cost = input_cost + output_cost

    return {
        "currency": "USD",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_usd": _to_float(input_cost),
        "output_usd": _to_float(output_cost),
        "total_usd": _to_float(total_cost),
        "total_usd_formatted": _format_usd(total_cost),
        "input_rate_per_1m": _to_float(input_rate),
        "output_rate_per_1m": _to_float(output_rate),
    }


def _calculate_token_cost(
    tokens: int,
    rate_per_million: Decimal,
) -> Decimal:
    """
    Calcula costo por tokens.

    Args:
        tokens: Cantidad de tokens.
        rate_per_million: Precio por 1M tokens.

    Returns:
        Costo estimado.
    """
    if tokens <= 0:
        return Decimal("0")

    return (Decimal(tokens) / Decimal("1000000")) * rate_per_million


def _get_decimal_env(name: str) -> Decimal:
    """
    Lee una variable de entorno decimal.

    Args:
        name: Nombre de la variable.

    Returns:
        Valor decimal. Si no existe o es inválida, devuelve 0.
    """
    raw_value = os.getenv(name, "0").strip()

    try:
        return Decimal(raw_value)
    except Exception:
        return Decimal("0")


def _format_usd(value: Decimal) -> str:
    """
    Formatea un costo en USD.

    Args:
        value: Costo decimal.

    Returns:
        Texto formateado.
    """
    rounded = value.quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )

    if rounded == Decimal("0.0000"):
        return "$0.00"

    if rounded < Decimal("1"):
        return f"${rounded}"

    return f"${rounded.quantize(Decimal('0.01'))}"


def _to_float(value: Decimal) -> float:
    """
    Convierte Decimal a float para serialización JSON.

    Args:
        value: Valor decimal.

    Returns:
        Valor float.
    """
    return float(value)