"""Conservative adapters from the semantic engineering IR to legacy solvers.

Adapters may derive a solver input only from explicit, structured physical facts.
They must never fill a missing engineering condition with a textbook default.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _flatten_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.append(str(key).lower().replace("_", " "))
            result.extend(_flatten_values(item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_flatten_values(item))
        return result
    if value is None:
        return []
    return [str(value).lower().replace("_", " ")]


def _is_negated_occurrence(text: str, start: int) -> bool:
    """Return True when a physical fact is explicitly negated nearby."""
    prefix = text[max(0, start - 48):start].lower()
    words = re.findall(r"[a-z]+", prefix)
    recent = words[-4:]
    if "not" in recent:
        if recent[-2:] == ["not", "only"]:
            return False
        return True
    return any(word in recent for word in ("no", "without", "neither", "never", "lacking", "absent"))


def _has_asserted(pattern: str, facts: str) -> bool:
    return any(
        not _is_negated_occurrence(facts, match.start())
        for match in re.finditer(pattern, facts, flags=re.IGNORECASE)
    )


def _support_facts(model: dict[str, Any]) -> set[str]:
    facts = " ".join(
        item
        for key in ("boundary_conditions", "relationships", "entities")
        for item in _flatten_values(model.get(key, []))
    )
    tokens = set()
    if _has_asserted(r"\b(?:pinned|pin|hinged|hinge)\b", facts):
        tokens.add("pin")
    if _has_asserted(r"\broller\b", facts):
        tokens.add("roller")
    if _has_asserted(r"\b(?:fixed|clamped|built in|built-in)\b", facts):
        tokens.add("fixed")
    if _has_asserted(r"\bfree\b", facts):
        tokens.add("free")
    return tokens


def _has_simply_supported_condition(model: dict[str, Any]) -> bool:
    facts = " ".join(
        item
        for key in ("boundary_conditions", "relationships", "entities")
        for item in _flatten_values(model.get(key, []))
    )
    explicit = _has_asserted(r"\bsimply supported\b|\bsimple support\b", facts)
    return explicit or ("pin" in _support_facts(model) and "roller" in _support_facts(model))


def _has_cantilever_condition(model: dict[str, Any]) -> bool:
    facts = " ".join(
        item
        for key in ("boundary_conditions", "relationships", "entities")
        for item in _flatten_values(model.get(key, []))
    )
    explicit = _has_asserted(r"\bcantilever\b", facts)
    return explicit or ("fixed" in _support_facts(model) and "free" in _support_facts(model))


_SI_UNIT_SCALES = {
    "m": 1.0, "mm": 1e-3, "cm": 1e-2,
    "n": 1.0, "kn": 1e3, "n*m": 1.0, "kn*m": 1e3,
    "n/m": 1.0, "kn/m": 1e3,
    "pa": 1.0, "kpa": 1e3, "mpa": 1e6, "gpa": 1e9,
    "m^4": 1.0, "m4": 1.0, "mm^4": 1e-12, "mm4": 1e-12,
    "1": 1.0, "dimensionless": 1.0,
}


def _quantity_value(model: dict[str, Any], names: set[str]) -> float | None:
    for quantity in model.get("quantities", []):
        if not isinstance(quantity, dict):
            continue
        if str(quantity.get("name", "")).strip().lower() not in names:
            continue
        # Prefer a value already normalized by the trusted parser.
        value = _number(quantity.get("solver_value"))
        if value is not None:
            return value
        # Otherwise convert only units with an explicit, known SI scale.
        raw = _number(quantity.get("value"))
        unit = str(quantity.get("unit") or "").strip().lower().replace(" ", "")
        scale = _SI_UNIT_SCALES.get(unit)
        if raw is not None and scale is not None:
            return raw * scale
    return None


def _set_if_missing(params: dict[str, Any], key: str, value: float | None) -> None:
    if params.get(key) in (None, "") and value is not None:
        params[key] = value


def prepare_engineering_solver_input(data: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Validate and adapt physical facts for currently supported solver families."""
    prepared = deepcopy(data)
    domain = str(prepared.get("domain") or "").lower()
    problem_type = str(prepared.get("problem_type") or "").lower()
    if domain not in {"structural", "advanced_structural"}:
        return prepared, None

    model = prepared.get("engineering_model")
    if not isinstance(model, dict):
        return prepared, "The engineering interpretation is missing; the solver cannot verify the physical setup."

    params = prepared.setdefault("parameters", {})
    if not isinstance(params, dict):
        return prepared, "The solver parameters are not a valid object."

    if problem_type in {"beam_analysis", "beam_deflection", "cantilever_beam", "simply_supported_beam"}:
        if _has_simply_supported_condition(model):
            prepared["raw_query"] = f'{prepared.get("raw_query", "")} Semantic support condition: simply supported beam.'
        elif _has_cantilever_condition(model):
            prepared["raw_query"] = f'{prepared.get("raw_query", "")} Semantic support condition: cantilever beam, fixed at one end and free at the other.'
        else:
            return prepared, (
                "The beam support conditions are not explicitly represented. "
                "Specify the actual supports (for example, pin-and-roller or fixed-free) before solving."
            )

        _set_if_missing(params, "L", _quantity_value(model, {"l", "length", "span"}))
        _set_if_missing(params, "P", _quantity_value(model, {"p", "point_load", "concentrated_load"}))
        _set_if_missing(params, "w", _quantity_value(model, {"w", "udl", "distributed_load", "load_intensity"}))
        _set_if_missing(params, "a", _quantity_value(model, {"a", "load_position", "point_load_position"}))
        _set_if_missing(params, "E", _quantity_value(model, {"e", "youngs_modulus", "elastic_modulus"}))
        _set_if_missing(params, "I", _quantity_value(model, {"i", "second_moment", "second_moment_of_area"}))

        span = _number(params.get("L"))
        modulus = _number(params.get("E"))
        inertia = _number(params.get("I"))
        if span is None or span <= 0:
            return prepared, "A positive beam span is required."
        if modulus is None or inertia is None:
            return prepared, (
                "The current beam solver also calculates deflection, so it requires explicit "
                "Young's modulus E and second moment of area I. They must not be replaced by defaults."
            )
        if modulus <= 0 or inertia <= 0:
            return prepared, "Young's modulus E and second moment of area I must be positive."
        point_load = _number(params.get("P")) or 0.0
        distributed_load = _number(params.get("w")) or 0.0
        if point_load > 0 and _number(params.get("a")) is None:
            return prepared, (
                "The point-load position is missing. State where the load acts along the beam; "
                "the solver must not assume midspan."
            )
        if point_load <= 0 and distributed_load <= 0:
            return prepared, "Provide a positive point load or distributed load."

    elif problem_type == "euler_column_buckling":
        _set_if_missing(params, "L", _quantity_value(model, {"l", "length"}))
        _set_if_missing(params, "E", _quantity_value(model, {"e", "youngs_modulus", "elastic_modulus"}))
        _set_if_missing(params, "I", _quantity_value(model, {"i", "second_moment", "second_moment_of_area"}))
        _set_if_missing(params, "K", _quantity_value(model, {"k", "effective_length_factor"}))
        if _number(params.get("K")) is None:
            boundary = " ".join(
                item
                for key in ("boundary_conditions", "relationships", "entities")
                for item in _flatten_values(model.get(key, []))
            )
            pinned_at_both_ends = _has_asserted(r"\bpinned\s+at\s+both\s+ends\b", boundary)
            fixed_at_both_ends = _has_asserted(r"\bfixed\s+at\s+both\s+ends\b", boundary)
            pinned_count = sum(
                1 for match in re.finditer(r"\b(?:pinned|pin)\b", boundary)
                if not _is_negated_occurrence(boundary, match.start())
            )
            fixed_count = sum(
                1 for match in re.finditer(r"\b(?:fixed|clamped)\b", boundary)
                if not _is_negated_occurrence(boundary, match.start())
            )
            if pinned_at_both_ends or pinned_count >= 2:
                params["K"] = 1.0
            elif fixed_at_both_ends or fixed_count >= 2:
                params["K"] = 0.5
            elif _has_asserted(r"\bfixed\b", boundary) and _has_asserted(r"\bfree\b", boundary):
                params["K"] = 2.0
            else:
                return prepared, (
                    "The column end restraints are not sufficiently specified to determine "
                    "the effective length factor K. State both end conditions or provide K."
                )
        for key in ("L", "E", "I", "K"):
            value = _number(params.get(key))
            if value is None or value <= 0:
                return prepared, f"Euler buckling requires an explicit positive {key} value."

    elif problem_type == "shaft_torsion":
        _set_if_missing(params, "T", _quantity_value(model, {"t", "torque"}))
        _set_if_missing(params, "L", _quantity_value(model, {"l", "length"}))
        _set_if_missing(params, "G", _quantity_value(model, {"g", "shear_modulus"}))
        _set_if_missing(params, "d", _quantity_value(model, {"d", "diameter", "outer_diameter"}))
        _set_if_missing(params, "d_inner", _quantity_value(model, {"d_inner", "inner_diameter"}))
        facts = " ".join(
            item
            for key in ("entities", "relationships", "boundary_conditions")
            for item in _flatten_values(model.get(key, []))
        )
        is_hollow = _has_asserted(r"\bhollow\b", facts)
        is_solid = _has_asserted(r"\bsolid\b", facts)
        if is_hollow and _number(params.get("d_inner")) is None:
            return prepared, "A hollow shaft requires its inner diameter."
        if is_solid == is_hollow:
            return prepared, "Specify one unambiguous solid or hollow circular cross-section."
        if is_hollow and _number(params.get("d_inner")) is not None and _number(params.get("d_inner")) <= 0:
            return prepared, "A hollow shaft inner diameter must be greater than zero."
        for key in ("T", "L", "G", "d"):
            value = _number(params.get(key))
            if value is None or value <= 0:
                return prepared, f"Shaft torsion requires an explicit positive {key} value."
        outer = _number(params["d"])
        inner = _number(params.get("d_inner"))
        if inner is not None and (inner < 0 or inner >= outer):
            return prepared, "The shaft inner diameter must be nonnegative and smaller than its outer diameter."
        if is_solid and inner is None:
            params["d_inner"] = 0.0

    elif problem_type == "thin_pressure_vessel":
        _set_if_missing(params, "p", _quantity_value(model, {"p", "pressure", "internal_pressure"}))
        _set_if_missing(params, "R", _quantity_value(model, {"r", "radius", "internal_radius"}))
        _set_if_missing(params, "t_wall", _quantity_value(model, {"t", "t_wall", "wall_thickness", "thickness"}))
        facts = " ".join(
            item
            for key in ("entities", "relationships", "boundary_conditions")
            for item in _flatten_values(model.get(key, []))
        )
        if not _has_asserted(r"\bcylinder\b|\bcylindrical\b", facts):
            return prepared, "The current pressure-vessel solver supports cylindrical vessels only."
        if not _has_asserted(r"\bclosed[- ]ends?\b", facts):
            return prepared, "State explicitly that the cylindrical pressure vessel has closed ends before calculating longitudinal stress."
        for key in ("p", "R", "t_wall"):
            value = _number(params.get(key))
            if value is None or value <= 0:
                return prepared, f"Pressure-vessel analysis requires an explicit positive {key} value."
        if _number(params["R"]) / _number(params["t_wall"]) < 10:
            return prepared, "The thin-wall assumption is not satisfied (R/t must be at least 10 for this solver)."
    else:
        # No adapter is registered for this solver family yet. Leave its legacy
        # execution path unchanged rather than implying its inputs were checked.
        return prepared, None

    prepared["parameters_in_si"] = True
    return prepared, None
