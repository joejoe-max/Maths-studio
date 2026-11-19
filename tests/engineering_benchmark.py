"""Evaluate real semantic-router outputs against canonical engineering gold cases.

Input is JSONL: one object per case with an "id" and "routing" (the parsed
router JSON). This deliberately evaluates the production build_problem_spec
handoff, not just hand-constructed IR objects. It does not call an LLM itself.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from backend.engine.problem_pipeline import build_problem_spec

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "engineering_benchmark_cases.json"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())


def _walk(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join([_walk(k) for k in value] + [_walk(v) for v in value.values()])
    if isinstance(value, (list, tuple)):
        return " ".join(_walk(item) for item in value)
    return _norm(value)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _extract_actual(prompt: str, routing: dict[str, Any]) -> dict[str, Any]:
    """Run the same routing-to-SubProblemSpec pipeline used by the app."""
    spec = build_problem_spec(prompt, routing)
    if not spec.sub_problems:
        return {}
    # The benchmark cases intentionally describe one physical task each.
    sub = spec.sub_problems[0]
    return {
        "domain": sub.domain,
        "problem_type": sub.problem_type,
        "model": sub.engineering_model or {},
    }


def evaluate_case(case: dict[str, Any], routing: dict[str, Any]) -> dict[str, Any]:
    actual = _extract_actual(case["prompt"], routing)
    gold = case["gold"]
    model = actual.get("model") or {}
    errors: list[str] = []
    metrics = {
        "domain": actual.get("domain") == gold["domain"],
        "problem_type": _norm(actual.get("problem_type")) == _norm(gold["problem_type"]),
        "entities": True,
        "quantities": True,
        "relationships": True,
        "boundary_conditions": True,
        "requested_outputs": True,
        "blockers": True,
        "no_invented_quantities": True,
    }

    if not metrics["domain"]:
        errors.append(f'domain: expected {gold["domain"]}, got {actual.get("domain")}')
    if not metrics["problem_type"]:
        errors.append(f'problem_type: expected {gold["problem_type"]}, got {actual.get("problem_type")}')

    entity_types = {_norm(e.get("type")) for e in model.get("entities", []) if isinstance(e, dict)}
    expected_entities = {_norm(x) for x in gold.get("entity_types", [])}
    metrics["entities"] = expected_entities.issubset(entity_types)
    if not metrics["entities"]:
        errors.append(f"missing entity types: {sorted(expected_entities - entity_types)}")

    quantities = {
        _norm(q.get("name")): q for q in model.get("quantities", [])
        if isinstance(q, dict) and q.get("name")
    }
    expected_q = gold.get("quantities", {})
    for name, expected in expected_q.items():
        found = quantities.get(_norm(name))
        if not found:
            metrics["quantities"] = False
            errors.append(f"missing quantity: {name}")
            continue
        value = _number(found.get("value"))
        expected_value = _number(expected.get("value"))
        if expected_value is not None and (value is None or not math.isclose(value, expected_value, rel_tol=1e-6, abs_tol=1e-9)):
            metrics["quantities"] = False
            errors.append(f'{name}: expected value {expected_value}, got {found.get("value")}')
        expected_unit = _norm(expected.get("unit"))
        if expected_unit and _norm(found.get("unit")) != expected_unit:
            metrics["quantities"] = False
            errors.append(f'{name}: expected unit {expected_unit}, got {found.get("unit")}')
    # Legacy routing parameters may include categorical metadata such as
    # support_condition/load_type. They are not extracted physical quantities.
    # Flag only unexpected numeric or explicitly unit-bearing quantities.
    extras = {
        name for name, item in quantities.items()
        if name not in {_norm(k) for k in expected_q}
        and name not in {_norm(k) for k in gold.get("allowed_extra_quantities", [])}
        and (_number(item.get("value")) is not None or bool(item.get("unit")))
    }
    metrics["no_invented_quantities"] = not extras
    if extras:
        errors.append(f"unexpected quantities (possible hallucination): {sorted(extras)}")

    rel_types = {_norm(r.get("type")) for r in model.get("relationships", []) if isinstance(r, dict)}
    expected_rel = {_norm(x) for x in gold.get("relationship_types", [])}
    metrics["relationships"] = expected_rel.issubset(rel_types)
    if not metrics["relationships"]:
        errors.append(f"missing relationship types: {sorted(expected_rel - rel_types)}")

    boundary_text = _walk(model.get("boundary_conditions", []))
    expected_boundary = [_norm(x) for x in gold.get("boundary_terms", [])]
    missing_boundary = [term for term in expected_boundary if term not in boundary_text]
    metrics["boundary_conditions"] = not missing_boundary
    if missing_boundary:
        errors.append(f"missing boundary-condition evidence: {missing_boundary}")

    output_text = _walk(model.get("requested_outputs", []))
    expected_outputs = [_norm(x) for x in gold.get("requested_outputs", [])]
    missing_outputs = [term for term in expected_outputs if term not in output_text]
    metrics["requested_outputs"] = not missing_outputs
    if missing_outputs:
        errors.append(f"missing requested outputs: {missing_outputs}")

    blocker_text = _walk(model.get("blocking_issues", []) + model.get("missing_information", []) + model.get("ambiguities", []))
    expected_blockers = [_norm(x) for x in gold.get("required_blocker_terms", [])]
    missing_blockers = [term for term in expected_blockers if term not in blocker_text]
    metrics["blockers"] = not missing_blockers
    if missing_blockers:
        errors.append(f"failed to flag required ambiguity/missing information: {missing_blockers}")

    passed = all(metrics.values())
    return {"id": case["id"], "group": case.get("equivalence_group"), "passed": passed, "metrics": metrics, "errors": errors, "actual": actual}


def run_benchmark(cases: list[dict[str, Any]], predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        prediction = predictions.get(case["id"])
        if prediction is None:
            results.append({"id": case["id"], "group": case.get("equivalence_group"), "passed": False, "metrics": {}, "errors": ["No router output supplied."]})
            continue
        results.append(evaluate_case(case, prediction))

    # Semantically equivalent prompts must produce the same core physical model.
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if result.get("group") and result.get("actual"):
            groups.setdefault(result["group"], []).append(result)
    equivalence_failures = []
    for group, members in groups.items():
        signatures = []
        for member in members:
            model = member["actual"].get("model") or {}
            quantities = sorted(
                (_norm(q.get("name")), _number(q.get("value")), _norm(q.get("unit")))
                for q in model.get("quantities", []) if isinstance(q, dict)
            )
            entity_types = sorted(_norm(e.get("type")) for e in model.get("entities", []) if isinstance(e, dict))
            relation_types = sorted(_norm(r.get("type")) for r in model.get("relationships", []) if isinstance(r, dict))
            boundary = _norm(_walk(model.get("boundary_conditions", [])))
            signatures.append((quantities, entity_types, relation_types, boundary))
        if signatures and any(signature != signatures[0] for signature in signatures[1:]):
            equivalence_failures.append(group)

    passed = sum(1 for item in results if item["passed"])
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "equivalence_failures": equivalence_failures,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, help="JSONL file: each row {id, routing}.")
    parser.add_argument("--cases", default=str(CASES_PATH), help="Gold case JSON file.")
    parser.add_argument("--output", help="Optional path to write the full JSON report.")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    predictions: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(Path(args.predictions).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("routing"), dict) or not row.get("id"):
            raise ValueError(f"Invalid prediction row at line {line_number}; expected id and routing object.")
        predictions[row["id"]] = row["routing"]

    report = run_benchmark(cases, predictions)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total", "passed", "failed", "pass_rate", "equivalence_failures")}, indent=2))
    if report["failed"] or report["equivalence_failures"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
