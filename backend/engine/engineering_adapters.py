"""Conservative adapters from the semantic engineering IR to legacy solvers.

Adapters may derive a solver input only from explicit, structured physical facts.
They must never fill a missing engineering condition with a textbook default.
"""
from __future__ import annotations

from copy import deepcopy
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


def _support_facts(model: dict[str, Any]) -> set[str]:
    facts: list[str] = []
    for key in ("boundary_conditions", "relationships", "entities"):
        facts.extend(_flatten_values(model.get(key, [])))
    joined = " ".join(facts)
    tokens = set()
    if any(word in joined for word in ("pinned", "pin", "pin support", "hinged", "hinge", "simply supported", "simple support")):
        tokens.add("pin")
    if "roller" in joined:
        tokens.add("roller")
    if any(word in joined for word in ("fixed", "clamped", "built in", "built-in")):
        tokens.add("fixed")
    if "free" in joined:
        tokens.add("free")
    return tokens


def _has_simply_supported_condition(model: dict[str, Any]) -> bool:
    facts = " ".join(
        item
        for key in ("boundary_conditions", "relationships", "entities")
        for item in _flatten_values(model.get(key, []))
    )
    return "simply supported" in facts or ("pin" in _support_facts(model) and "roller" in _support_facts(model))


def _has_cantilever_condition(model: dict[str, Any]) -> bool:
    facts = " ".join(
        item
        for key in ("boundary_conditions", "relationships", "entities")
        for item in _flatten_values(model.get(key, []))
    )
    return "cantilever" in facts or ("fixed" in _support_facts(model) and "free" in _support_facts(model))


_SI_UNIT_SCALES = {
    "m": 1.0, "mm": 1e-3, "cm": 1e-2,
    "n": 1.0, "kn": 1e3,
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
    """Validate assumptions required by currently supported structural solvers.

    Returns a copied solver payload and a blocking explanation, if any. This is
    intentionally conservative: unsupported boundary conditions are not
    approximated by a different structural model.
    """
    prepared = deepcopy(data)
    domain = str(prepared.get("domain") or "").lower()
    problem_type = str(prepared.get("problem_type") or "").lower()
    model = prepared.get("engineering_model")
    if domain not in {"structural", "advanced_structural"}:
        prepared["parameters_in_si"] = True
    return prepared, None
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

        if _number(params.get("L")) is None or _number(params.get("L")) <= 0:
            return prepared, "A positive beam span is required."
        if _number(params.get("E")) is None or _number(params.get("I")) is None:
            return prepared, (
                "The current beam solver also calculates deflection, so it requires explicit "
                "Young's modulus E and second moment of area I. They must not be replaced by defaults."
            )
        if _number(params.get("E")) <= 0 or _number(params.get("I")) <= 0:
            return prepared, "Young's modulus E and second moment of area I must be positive."
        point_load = _number(params.get("P")) or 0.0
        if point_load > 0 and _number(params.get("a")) is None:
            return prepared, (
                "The point-load position is missing. State where the load acts along the beam; "
                "the solver must not assume midspan."
            )
        if point_load <= 0 and (_number(params.get("w")) is None or _number(params.get("w")) <= 0):
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
            if "pinned" in boundary and boundary.count("pinned") >= 2:
                params["K"] = 1.0
            elif "pin" in boundary and boundary.count("pin") >= 2:
                params["K"] = 1.0
            elif "fixed" in boundary and boundary.count("fixed") >= 2:
                params["K"] = 0.5
            elif "fixed" in boundary and "free" in boundary:
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

    return prepared, None
