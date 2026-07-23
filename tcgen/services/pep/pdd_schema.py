"""
Esquemas de validación para el análisis de documentos PDD/FDD.

Este módulo define el contrato JSON esperado del análisis realizado por
Claude sobre el PDD/FDD utilizado por el generador PEP.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


AnalysisStatus = Literal["completado"]
CalculationStatus = Literal["ok", "error_validacion"]
StressBase = Literal["periodo_normal", "periodo_maximo"]
TechnologyDetection = Literal["explicita", "inferida", "no_encontrada"]

MissingField = Literal[
    "descripcion_breve_proceso",
    "calendario_frecuencia",
    "cantidad_periodo_normal.cantidad",
]

CalculationType = Literal["estres", "verificacion"]


class TechnologyData(BaseModel):
    """
    Tecnología detectada desde el PDD/FDD.

    La tecnología debe representar la herramienta, plataforma, framework,
    producto o entorno usado para construir la solución.
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


class ProcessQuantityData(BaseModel):
    """
    Cantidad de elementos procesados durante un periodo.
    """

    model_config = ConfigDict(extra="forbid")

    cantidad: float | None = Field(default=None, gt=0)
    unidad_elemento: str | None = None

    @field_validator("unidad_elemento")
    @classmethod
    def clean_unit(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Limpia la unidad del elemento procesado.
        """
        if value is None:
            return None

        clean_value = " ".join(value.split())
        return clean_value or None


class ProcessContextData(BaseModel):
    """
    Contexto operativo y volumétrico extraído del PDD/FDD.
    """

    model_config = ConfigDict(extra="forbid")

    descripcion_breve_proceso: str | None = None
    calendario_frecuencia: str | None = None
    cantidad_periodo_normal: ProcessQuantityData
    cantidad_periodo_maximo: ProcessQuantityData

    @field_validator(
        "descripcion_breve_proceso",
        "calendario_frecuencia",
    )
    @classmethod
    def clean_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Limpia valores textuales opcionales.
        """
        if value is None:
            return None

        clean_value = " ".join(value.split())
        return clean_value or None


class PercentageQuantityData(BaseModel):
    """
    Resultado de un cálculo porcentual simple.
    """

    model_config = ConfigDict(extra="forbid")

    porcentaje: int = Field(ge=0)
    cantidad: int = Field(ge=0)


class TypedPercentageQuantityData(BaseModel):
    """
    Resultado porcentual asociado a un tipo de prueba.
    """

    model_config = ConfigDict(extra="forbid")

    tipo: CalculationType
    porcentaje: int = Field(ge=0)
    cantidad: int = Field(ge=0)


class DevelopmentPlanData(BaseModel):
    """
    Plan de insumos para las fases de Development.
    """

    model_config = ConfigDict(extra="forbid")

    fase_1: PercentageQuantityData
    fase_2: PercentageQuantityData
    fase_3: TypedPercentageQuantityData


class DeploymentPlanData(BaseModel):
    """
    Insumos para Deployment/UAT.

    Deployment debe considerar únicamente el escenario productivo al 120%.
    """

    model_config = ConfigDict(extra="forbid")

    uat_productivo: TypedPercentageQuantityData


class CalculationTraceData(BaseModel):
    """
    Trazabilidad matemática de un cálculo de insumos.
    """

    model_config = ConfigDict(extra="forbid")

    calculo: str | None = None
    valor_base: float = Field(ge=0)
    porcentaje_aplicado: int = Field(ge=0)
    resultado_sin_redondear: float = Field(ge=0)
    resultado_final: int = Field(ge=0)


class SupplyPlanData(BaseModel):
    """
    Plan calculado de insumos para pruebas.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_proceso: str | None = None
    frecuencia: str | None = None
    unidad_elemento: str | None = None
    insumos_base_periodo_normal: int = Field(ge=0)
    insumos_estres_120: int = Field(ge=0)
    development: DevelopmentPlanData
    deployment: DeploymentPlanData
    trazabilidad_calculos: list[CalculationTraceData]
    criterio_calculo: str | None = None
    nota_deployment: str | None = None


class SupplyCalculationData(BaseModel):
    """
    Estado y resultado del cálculo de insumos.
    """

    model_config = ConfigDict(extra="forbid")

    estado_calculo: CalculationStatus
    datos_faltantes: list[MissingField]
    mensaje_validacion: str | None = None
    base_calculo_estres: StressBase | None = None
    plan_insumos: SupplyPlanData | None = None


class PddAnalysisData(BaseModel):
    """
    Resultado validado del análisis completo del PDD/FDD.
    """

    model_config = ConfigDict(extra="forbid")

    estado_analisis: AnalysisStatus
    tecnologia: TechnologyData
    requerimientos: list[str]
    contexto_proceso: ProcessContextData
    calculo_insumos: SupplyCalculationData
    advertencias: list[str]

    @field_validator("requerimientos")
    @classmethod
    def clean_requirements(
        cls,
        values: list[str],
    ) -> list[str]:
        """
        Limpia requerimientos y elimina duplicados conservando el orden.
        """
        requirements: list[str] = []
        seen: set[str] = set()

        for value in values:
            clean_value = " ".join((value or "").split())

            if not clean_value:
                continue

            comparison_value = clean_value.casefold()

            if comparison_value in seen:
                continue

            seen.add(comparison_value)
            requirements.append(clean_value)

        return requirements

    @field_validator("advertencias")
    @classmethod
    def clean_warnings(
        cls,
        values: list[str],
    ) -> list[str]:
        """
        Limpia las advertencias devueltas por el modelo.
        """
        return [
            clean_value
            for value in values
            if (clean_value := " ".join((value or "").split()))
        ]


def validate_pdd_payload(
    payload: dict[str, Any],
) -> PddAnalysisData:
    """
    Valida el JSON producido durante el análisis del PDD/FDD.

    Args:
        payload: Diccionario obtenido de la respuesta JSON del modelo.

    Returns:
        Resultado PDD/FDD validado.
    """
    return PddAnalysisData.model_validate(payload)