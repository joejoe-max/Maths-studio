"""Run the engineering understanding benchmark against the configured Gemini router.

Requires GEMINI_API_KEY or AI_INTEGRATIONS_GEMINI_API_KEY. Calls are sequential
to avoid unnecessary provider concurrency and records the exact router outputs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO_ROOT))

from main import _semantic_route_text, gemini_client
from tests.engineering_benchmark import CASES_PATH, run_benchmark


async def run_live(cases: list[dict], predictions_path: Path, report_path: Path) -> dict:
    if gemini_client is None:
        raise RuntimeError(
            "Gemini is not configured. Set GEMINI_API_KEY or "
            "AI_INTEGRATIONS_GEMINI_API_KEY; deterministic fallback is not a live AI evaluation."
        )

    predictions = {}
    rows = []
    for case in cases:
        routing = await _semantic_route_text(case["prompt"])
        predictions[case["id"]] = routing
        rows.append({"id": case["id"], "routing": routing})

    predictions_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    report = run_benchmark(cases, predictions)
    report["evaluation_mode"] = "live_gemini_router"
    report["model_fallback_warning"] = (
        "The router may fall back to deterministic parsing when Gemini fails; "
        "inspect saved predictions and backend logs before attributing failures."
    )
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--predictions", type=Path, default=Path("engineering-benchmark-predictions.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("engineering-benchmark-report.json"))
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = asyncio.run(run_live(cases, args.predictions, args.report))
    print(json.dumps({
        "mode": report["evaluation_mode"],
        "total": report["total"],
        "passed": report["passed"],
        "failed": report["failed"],
        "pass_rate": report["pass_rate"],
        "equivalence_failures": report["equivalence_failures"],
        "predictions": str(args.predictions),
        "report": str(args.report),
    }, indent=2))
    return 1 if report["failed"] or report["equivalence_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
