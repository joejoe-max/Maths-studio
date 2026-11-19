"""Canonical engineering intermediate representation.

The semantic extractor supplies meaning; this layer records it in a stable,
auditable form and checks it before solver routing. It does not use wording
templates to decide what a problem means.
"""
from __future__ import annotations
import math
from typing import Any

ENGINEERING_DOMAINS = {"structural", "mechanics", "fluids", "thermo", "circuits", "physics", "controls"}
_UNIT_DIMENSIONS = {
    "m":"length","mm":"length","cm":"length","km":"length","m^2":"area","m2":"area",
    "mm^2":"area","mm2":"area","m^3":"volume","m3":"volume","l":"volume",
    "n":"force","kn":"force","mn":"force","n/m":"force_per_length","kn/m":"force_per_length",
    "pa":"pressure","kpa":"pressure","mpa":"pressure","gpa":"pressure","n/m^2":"pressure",
    "kg":"mass","g":"mass","tonne":"mass","s":"time","min":"time","h":"time",
    "m/s":"velocity","km/h":"velocity","m/s^2":"acceleration","kg/m^3":"density",
    "n*m":"moment","kn*m":"moment","j":"energy","kj":"energy","w":"power","kw":"power",
    "k":"temperature","degc":"temperature","°c":"temperature","a":"current","ma":"current",
    "v":"voltage","ohm":"resistance","hz":"frequency","1/s":"frequency",
}
_POSITIVE_KEYS = {"l","length","span","width","height","depth","diameter","radius","area","volume","mass","density"}

def _dimension(unit: Any) -> str | None:
    if not isinstance(unit, str): return None
    key = unit.strip().lower().replace(" ","").replace("²","^2").replace("³","^3")
    return _UNIT_DIMENSIONS.get(key)

def build_engineering_model(raw_query: str, sub: dict[str, Any], parameters: dict[str, Any], units: dict[str, Any]) -> dict[str, Any]:
    supplied = sub.get("engineering_model")
    supplied = supplied if isinstance(supplied, dict) else {}
    supplied_quantities = supplied.get("quantities") if isinstance(supplied.get("quantities"), list) else []
    by_name = {str(q.get("name")): q for q in supplied_quantities if isinstance(q, dict) and q.get("name")}
    quantities = []
    for name, value in (parameters or {}).items():
        if str(name).startswith("_") or name == "canonical_problem_type" or value is None: continue
        item = by_name.get(str(name), {})
        unit = item.get("unit") or (units or {}).get(name)
        try:
            number = float(value)
            numeric = math.isfinite(number)
        except (TypeError, ValueError):
            number, numeric = None, False
        quantities.append({
            "name": str(name), "value": number if numeric else value, "unit": unit,
            "dimension": item.get("dimension") or _dimension(unit),
            "role": item.get("role") or ("known" if numeric else "symbolic_or_unresolved"),
            "object": item.get("object"), "location": item.get("location"),
            "direction": item.get("direction"), "source_text": item.get("source_text") or raw_query,
            "confidence": item.get("confidence"),
        })
    model = {
        "schema_version":"1.0", "domain":str(sub.get("domain") or "unknown").lower(),
        "problem_type":str(sub.get("problem_type") or "general"), "source_text":raw_query,
        "entities":supplied.get("entities") if isinstance(supplied.get("entities"),list) else [],
        "quantities":quantities,
        "relationships":supplied.get("relationships") if isinstance(supplied.get("relationships"),list) else [],
        "boundary_conditions":supplied.get("boundary_conditions") if isinstance(supplied.get("boundary_conditions"),list) else [],
        "initial_conditions":supplied.get("initial_conditions") if isinstance(supplied.get("initial_conditions"),list) else [],
        "requested_outputs":supplied.get("requested_outputs") if isinstance(supplied.get("requested_outputs"),list) else (sub.get("required_outputs") or []),
        "assumptions":supplied.get("assumptions") if isinstance(supplied.get("assumptions"),list) else [],
        "missing_information":list(supplied.get("missing_information") or sub.get("missing_information") or []),
        "ambiguities":list(supplied.get("ambiguities") or sub.get("ambiguities") or []),
        "validation":{"status":"valid","errors":[],"warnings":[]},
    }
    errors, warnings = [], []
    for q in quantities:
        value = q["value"]
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            errors.append(f'{q["name"]} must be a finite number.')
        if q["name"].lower() in _POSITIVE_KEYS and isinstance(value,(int,float)) and value <= 0:
            errors.append(f'{q["name"]} must be greater than zero; verify the extracted value.')
        mapped_dimension = _dimension(q["unit"])
        declared_dimension = q["dimension"]
        if q["unit"] and not mapped_dimension:
            warnings.append(f'Unit "{q["unit"]}" for {q["name"]} is unrecognised; preserved without conversion.')
        elif mapped_dimension and declared_dimension and mapped_dimension != declared_dimension:
            errors.append(f'{q["name"]} declares dimension "{declared_dimension}" but unit "{q["unit"]}" represents "{mapped_dimension}".')
    entity_ids = {str(entity.get("id")) for entity in model["entities"] if isinstance(entity, dict) and entity.get("id")}
    for relationship in model["relationships"]:
        if not isinstance(relationship, dict):
            warnings.append("A physical relationship was not represented as an object.")
            continue
        for endpoint in ("source", "target"):
            ref = relationship.get(endpoint)
            if ref and entity_ids and str(ref) not in entity_ids:
                errors.append(f'Relationship {relationship.get("type", "unknown")} refers to missing entity "{ref}".')
        left_dimension = relationship.get("left_dimension") or relationship.get("lhs_dimension")
        right_dimension = relationship.get("right_dimension") or relationship.get("rhs_dimension")
        if left_dimension and right_dimension and left_dimension != right_dimension:
            errors.append(f'Relationship {relationship.get("type", "unknown")} compares incompatible dimensions: {left_dimension} and {right_dimension}.')
    if not model["entities"]: warnings.append("No physical entities were explicitly supplied by semantic extraction.")
    if not model["relationships"]: warnings.append("No explicit physical relationships were supplied; solver compatibility requires review.")
    if model["ambiguities"]: warnings.append("The statement contains unresolved ambiguities.")
    if model["missing_information"]: warnings.append("The statement may be under-specified for the requested outputs.")
    model["validation"] = {"status":"invalid" if errors else ("needs_review" if warnings else "valid"),"errors":errors,"warnings":warnings}
    return model
