"""
Esquema de validación para la extracción de información desde PAP.

Este módulo valida que la respuesta JSON generada por el modelo cumpla
con la estructura esperada antes de utilizarla para llenar el PEP.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TechnologyDetection = Literal["explicita", "inferida", "no_encontrada"]


class TechnologyData(BaseModel):
    """
    Representa la tecnología detectada en el PAP.

    Attributes:
        valor: Tecnología identificada o inferida.
        tipo_deteccion: Forma en que se detectó la tecnología.
        justificacion: Evidencia breve usada para justificar la detección.
    """

    model_config = ConfigDict(extra="forbid")

    valor: str | None
    tipo_deteccion: TechnologyDetection
    justificacion: str | None

    @model_validator(mode="after")
    def validate_technology_consistency(self) -> "TechnologyData":
        """
        Valida coherencia entre valor, tipo de detección y justificación.
        """
        if self.tipo_deteccion == "no_encontrada":
            if self.valor is not None:
                raise ValueError(
                    "tecnologia.valor debe ser null cuando "
                    "tipo_deteccion es no_encontrada."
                )

            if self.justificacion is not None:
                raise ValueError(
                    "tecnologia.justificacion debe ser null cuando "
                    "tipo_deteccion es no_encontrada."
                )

            return self

        if not (self.valor or "").strip():
            raise ValueError(
                "tecnologia.valor es obligatorio cuando la tecnología "
                "fue explícita o inferida."
            )

        if self.tipo_deteccion == "inferida":
            if not (self.justificacion or "").strip():
                raise ValueError(
                    "tecnologia.justificacion es obligatoria cuando "
                    "la tecnología fue inferida."
                )

        return self


class RolesData(BaseModel):
    """
    Representa los responsables del proyecto por rol.

    Todos los roles deben recibirse como lista de strings o null.
    """

    model_config = ConfigDict(extra="forbid")

    desarrollador: list[str] | None
    tester: list[str] | None
    scrum_master: list[str] | None
    delivery_manager: list[str] | None
    business_analyst: list[str] | None
    arquitecto: list[str] | None
    code_reviewer: list[str] | None

    @field_validator(
        "desarrollador",
        "tester",
        "scrum_master",
        "delivery_manager",
        "business_analyst",
        "arquitecto",
        "code_reviewer",
    )
    @classmethod
    def validate_role_names(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        """
        Valida que cada rol sea null o una lista de nombres no vacíos.
        """
        if value is None:
            return None

        cleaned = []
        for item in value:
            name = (item or "").strip()
            if not name:
                raise ValueError("Los nombres de roles no pueden ir vacíos.")
            cleaned.append(name)

        return cleaned


class RequirementSection(BaseModel):
    """
    Representa una sección de requisitos de hardware o software.
    """

    model_config = ConfigDict(extra="forbid")

    texto_introductorio: str | None
    items: list[str] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def validate_items(cls, value: list[str]) -> list[str]:
        """
        Valida que cada requisito sea texto útil.
        """
        cleaned = []
        for item in value:
            text = (item or "").strip()
            if not text:
                raise ValueError("Los requisitos no pueden incluir items vacíos.")
            cleaned.append(text)

        return cleaned


class PapExtractionData(BaseModel):
    """
    Estructura completa esperada para la extracción del PAP.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_proyecto: str | None
    id_proyecto: str | None
    nombre_cliente: str | None
    tecnologia: TechnologyData
    roles: RolesData
    requisitos_software: RequirementSection
    requisitos_hardware: RequirementSection
    advertencias: list[str] = Field(default_factory=list)

    @field_validator("advertencias")
    @classmethod
    def validate_warnings(cls, value: list[str]) -> list[str]:
        """
        Valida que las advertencias sean textos no vacíos.
        """
        cleaned = []
        for item in value:
            warning = (item or "").strip()
            if not warning:
                raise ValueError("Las advertencias no pueden ir vacías.")
            cleaned.append(warning)

        return cleaned


def validate_pap_payload(payload: dict[str, Any]) -> PapExtractionData:
    """
    Valida un diccionario con la estructura esperada del PAP.

    Args:
        payload: Diccionario obtenido desde la respuesta JSON del modelo.

    Returns:
        Modelo PapExtractionData validado.

    Raises:
        ValueError: Si el payload no cumple la estructura requerida.
    """
    try:
        return PapExtractionData.model_validate(payload)
    except Exception as exc:
        raise ValueError(
            "La extracción del PAP no cumple la estructura esperada."
        ) from exc