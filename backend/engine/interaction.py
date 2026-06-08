from __future__ import annotations

from typing import Any

from .models import SubProblemSpec


def should_prompt_for_method(spec: SubProblemSpec, popup_domains: set[str]) -> bool:
    return False


def determine_missing_fields(spec: SubProblemSpec) -> list[dict[str, Any]]:
    domain = (spec.domain or "").lower()
    problem_type = (spec.problem_type or "").lower()
    params = dict(spec.parameters or {})
    knowns = dict(spec.knowns or {})
    merged = {**params, **knowns}
    structure = spec.canonical.structure_properties

    def get_value(*keys: str):
        for key in keys:
            value = merged.get(key)
            if value not in (None, "", []):
                return value
        return None

    def require(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for field in fields:
            aliases = field.get("aliases", [])
            value = get_value(field["name"], *aliases)
            if value in (None, "", []):
                missing.append(field)
        return missing

    if domain == "algebra" and spec.equations:
        return []

    if domain == "algebra" and structure.is_system and len(spec.equations) < max(2, structure.unknown_count):
        return [
            {
                "name": "equation_1",
                "label": "Equation 1",
                "placeholder": "e.g., 3x + 2y = 12",
                "hint": "Enter each equation in standard math form.",
                "required": True,
            },
            {
                "name": "equation_2",
                "label": "Equation 2",
                "placeholder": "e.g., x - y = 1",
                "hint": "You can add more equations if needed.",
                "required": True,
            },
        ]

    if domain == "mechanics" and problem_type in {"projectile_motion", "kinematics"}:
        if sum(1 for key in ("u", "v", "a", "t", "s", "theta") if get_value(key) is not None) < 3:
            return [
                {"name": "u", "aliases": ["v0", "velocity"], "label": "Initial velocity", "unit": "m/s", "hint": "Provide known kinematic values.", "required": False},
                {"name": "theta", "aliases": ["angle"], "label": "Launch angle", "unit": "deg", "required": False},
                {"name": "a", "label": "Acceleration", "unit": "m/s^2", "required": False},
                {"name": "t", "label": "Time", "unit": "s", "required": False},
                {"name": "s", "label": "Displacement", "unit": "m", "required": False},
            ]

    if domain == "circuits" and problem_type in {"ohms_law", "circuit_analysis"}:
        known = sum(1 for key in ("v", "i", "r", "V", "I", "R") if get_value(key) is not None)
        if known < 2:
            return [
                {"name": "v", "aliases": ["V"], "label": "Voltage", "unit": "V", "hint": "Provide any 2 of V, I, R.", "required": False},
                {"name": "i", "aliases": ["I"], "label": "Current", "unit": "A", "required": False},
                {"name": "r", "aliases": ["R"], "label": "Resistance", "unit": "Ohm", "required": False},
            ]

    if domain == "fluids" and problem_type == "continuity":
        known = sum(1 for key in ("v1", "v2", "a1", "a2", "d1", "d2") if get_value(key) is not None)
        if known < 3:
            return [
                {"name": "v1", "label": "Inlet velocity", "unit": "m/s", "required": False},
                {"name": "v2", "label": "Outlet velocity", "unit": "m/s", "required": False},
                {"name": "a1", "label": "Inlet area", "unit": "m^2", "required": False},
                {"name": "a2", "label": "Outlet area", "unit": "m^2", "required": False},
            ]

    if domain == "structural" and problem_type in {"rc_beam_design"}:
        return []

    if domain == "structural" and problem_type in {"beam_analysis", "beam_deflection"}:
        fields = [{"name": "L", "aliases": ["l", "span", "length"], "label": "Beam length", "unit": "m", "hint": "Total span length.", "required": True}]
        if get_value("P", "point_load", "load", "force") is None and get_value("w", "udl", "distributed_load") is None:
            fields.extend([
                {"name": "P", "aliases": ["point_load", "load", "force"], "label": "Point load magnitude", "unit": "N", "required": False},
                {"name": "w", "aliases": ["udl", "distributed_load"], "label": "Uniformly distributed load", "unit": "N/m", "required": False},
            ])
        return require(fields)

    if domain == "thermo" and problem_type in {"constant_pressure_gas_process"}:
        return []

    if domain == "thermo" and problem_type in {"ideal_gas", "thermodynamics"}:
        known = sum(1 for key in ("p", "v", "n", "t", "P", "V", "T") if get_value(key) is not None)
        if known < 3:
            return [
                {"name": "p", "aliases": ["P"], "label": "Pressure", "unit": "Pa", "hint": "Provide any 3 of P, V, n, T.", "required": False},
                {"name": "v", "aliases": ["V"], "label": "Volume", "unit": "m^3", "required": False},
                {"name": "n", "label": "Moles", "unit": "mol", "required": False},
                {"name": "t", "aliases": ["T"], "label": "Temperature", "unit": "K", "required": False},
            ]

    if domain in {"calculus", "ode", "data_viz"} and not get_value("expression") and not spec.equations:
        return [
            {
                "name": "expression",
                "label": "Mathematical expression",
                "placeholder": "e.g., sin(x)",
                "hint": "Enter the function or expression in standard math notation.",
                "required": True,
            }
        ]

    return []


def build_missing_parameters_event(spec: SubProblemSpec) -> dict[str, Any] | None:
    fields = determine_missing_fields(spec)
    if not fields:
        return None
    return {
        "type": "needs_parameters",
        "stage": "parameter_collection",
        "problem_id": spec.id,
        "domain": spec.domain,
        "problem_type": spec.problem_type,
        "message": "More information is needed before solving can continue.",
        "fields": fields,
        "missing_params": fields,
        "problem_description": spec.input_summary or spec.raw_query,
        "retryable": True,
        "retry_available": True,
    }


def build_method_selection_event(spec: SubProblemSpec) -> dict[str, Any]:
    return {
        "type": "needs_method_selection",
        "stage": "method_selection",
        "problem_id": spec.id,
        "domain": spec.domain,
        "problem_type": spec.problem_type,
        "message": "Select a feasible method to continue this solution.",
        "methods": [method.model_dump() for method in spec.feasible_methods],
        "problem_description": spec.input_summary or spec.raw_query,
        "retryable": True,
        "retry_available": True,
    }
