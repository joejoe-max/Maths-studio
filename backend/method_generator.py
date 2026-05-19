"""
backend/method_generator.py — Method analysis and generation engine
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class MethodDefinition:
    id: str
    name: str
    description: str
    is_recommended: bool
    complexity: str
    estimated_steps: int
    solver_name: str
    validation_checks: list[str]
    requires_params: dict = field(default_factory=dict)
    optional_params: list[str] = field(default_factory=list)
    
    def is_feasible(self, parameters: dict, missing_params: list) -> bool:
        for req_key in self.requires_params.keys():
            if req_key in missing_params:
                return False
        return True


@dataclass
class MissingParameter:
    key: str
    label: str
    unit: str
    type: str
    hint: str


@dataclass
class ProblemAnalysis:
    domain: str
    problem_type: str
    confidence: float
    parameters: dict
    missing_parameters: list
    available_methods: list
    recommended_method_id: Optional[str] = None
    can_solve: bool = False
    error_message: Optional[str] = None


REQUIRED_PARAMETERS = {
    ("algebra", "simultaneous_equations"): {"required": ["equations"], "optional": []},
    ("algebra", "quadratic_equation"): {"required": ["a", "b", "c"], "optional": []},
    ("calculus", "differentiation"): {"required": ["expression"], "optional": []},
    ("structural", "simply_supported_beam"): {"required": ["L"], "optional": ["P", "w"]},
    ("mechanics", "projectile_motion"): {"required": ["u", "theta"], "optional": []},
    ("circuits", "ohms_law"): {"required": [], "optional": ["V", "I", "R"]},
}

PARAMETER_HINTS = {
    "L": MissingParameter("L", "Beam length", "m", "numeric", "e.g., L = 6 m"),
    "P": MissingParameter("P", "Point load", "N", "numeric", "e.g., P = 50 kN"),
    "u": MissingParameter("u", "Initial velocity", "m/s", "numeric", "e.g., u = 40 m/s"),
    "theta": MissingParameter("theta", "Launch angle", "deg", "numeric", "e.g., θ = 30°"),
    "expression": MissingParameter("expression", "Mathematical expression", "formula", "numeric", "e.g., sin(x)"),
}


def find_missing_params(domain: str, problem_type: str, parameters: dict) -> list:
    key = (domain, problem_type)
    reqs = REQUIRED_PARAMETERS.get(key, {})
    required = reqs.get("required", [])
    missing = []
    
    for param_key in required:
        if param_key not in parameters or parameters[param_key] in (None, "", []):
            hint = PARAMETER_HINTS.get(param_key)
            if hint:
                missing.append(hint)
    
    return missing


def get_methods_for_problem(domain: str, problem_type: str, parameters: dict):
    from .methods_registry import METHODS_REGISTRY
    
    methods = METHODS_REGISTRY.get(domain, {}).get(problem_type, [])
    if not methods:
        return ([], None)
    
    missing = find_missing_params(domain, problem_type, parameters)
    missing_keys = [p.key for p in missing]
    
    feasible = [m for m in methods if m.is_feasible(parameters, missing_keys)]
    feasible.sort(key=lambda m: (not m.is_recommended, {"basic": 0, "intermediate": 1, "advanced": 2}.get(m.complexity, 99)))
    
    recommended_id = next((m.id for m in feasible if m.is_recommended), None)
    return (feasible, recommended_id)


def analyze_problem(domain: str, problem_type: str, parameters: dict, confidence: float = 1.0) -> ProblemAnalysis:
    missing = find_missing_params(domain, problem_type, parameters)
    methods, recommended_id = get_methods_for_problem(domain, problem_type, parameters)
    
    can_solve = len(methods) > 0 and len(missing) == 0
    error_msg = None
    
    if len(missing) > 0:
        error_msg = f"Missing {len(missing)} required parameters"
    elif len(methods) == 0:
        error_msg = f"No methods available for {domain}/{problem_type}"
    
    return ProblemAnalysis(
        domain=domain,
        problem_type=problem_type,
        confidence=confidence,
        parameters=parameters,
        missing_parameters=missing,
        available_methods=methods,
        recommended_method_id=recommended_id,
        can_solve=can_solve,
        error_message=error_msg,
    )
