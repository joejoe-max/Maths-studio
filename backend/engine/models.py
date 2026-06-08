from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MethodOption(BaseModel):
    id: str
    label: str
    description: str = ""
    feasible: bool = True
    recommended: bool = False


class StructuredError(BaseModel):
    type: str = "error"
    message: str
    suggestion: str = "Check the input and try again."
    stage: str = "solving"
    retryable: bool = True
    retry_available: bool = True
    valid_methods: list[MethodOption] = Field(default_factory=list)
    problem_id: str | None = None


class EquationSpec(BaseModel):
    raw: str
    normalized: str
    order: int = 0
    is_linear: bool | None = None
    degree: int | None = None


class DomainScore(BaseModel):
    domain: str
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class ProblemStructure(BaseModel):
    equation_count: int = 0
    unknown_count: int = 0
    is_system: bool = False
    is_linear: bool | None = None
    max_degree: int | None = None
    differential_order: int = 0
    has_units: bool = False
    has_boundary_conditions: bool = False


class CanonicalProblem(BaseModel):
    domain: str = "unknown"
    equations: list[EquationSpec] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    units: dict[str, str] = Field(default_factory=dict)
    problem_type: str = "general"
    structure_properties: ProblemStructure = Field(default_factory=ProblemStructure)
    domain_confidence: list[DomainScore] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SubProblemSpec(BaseModel):
    id: str
    domain: str
    problem_type: str
    raw_query: str
    normalized_text: str
    canonical: CanonicalProblem = Field(default_factory=CanonicalProblem)
    input_summary: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    knowns: dict[str, Any] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    equations: list[EquationSpec] = Field(default_factory=list)
    units: dict[str, str] = Field(default_factory=dict)
    requested_method: str | None = None
    feasible_methods: list[MethodOption] = Field(default_factory=list)
    selected_method: str | None = None


class ProblemSpec(BaseModel):
    raw_input: str
    sub_problems: list[SubProblemSpec] = Field(default_factory=list)
