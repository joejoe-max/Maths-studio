# Production Readiness — Engineering Semantic Model

**Status: Not approved for merge or production yet.** This document records what has been verified and what remains unverified. A passing unit/CI suite is necessary, not sufficient.

## Implemented on PR #11

- Solver-independent engineering IR for entities, quantities, units, relationships, boundary/initial conditions, outputs, assumptions, ambiguities and blockers.
- Conservative adapters for beam analysis, Euler column buckling, circular shaft torsion and thin-walled cylindrical pressure vessels.
- SI conversion for recognized units; unknown units are not guessed.
- Negated support/geometry conditions are rejected by adapter checks.
- Benchmark harness with ten initial prompts, paraphrase groups, missing/contradictory cases, invented quantity/boundary checks and unit-normalized equivalence comparison.
- Live Gemini benchmark runner: `python tests/run_live_engineering_benchmark.py`.
- API smoke tests for FastAPI startup, health/analyze endpoints, a deterministic math solve over SSE, routing isolation and proxy identity.
- Default solve concurrency bounded to six; stale in-memory rate-limit windows are periodically pruned.

## Verified evidence

- GitHub Actions workflow: `.github/workflows/engineering-ir-tests.yml`.
- Python 3.11 compile check and backend dependency installation; 58 automated tests pass across six test groups.
- Engineering IR, semantic routing, adapter-to-solver, benchmark evaluator, API smoke and advanced structural regression suites.
- The live benchmark harness itself is compile-checked and its evaluator is tested with controlled predictions.

The live model score has **not** been established by deterministic fixtures. The benchmark must be run against actual Gemini responses and the resulting JSONL/report reviewed.

## Merge blockers / required evidence

| Gate | Current evidence | Required before approval |
| --- | --- | --- |
| Live semantic understanding | Harness and runner exist; no live model score recorded | Run with configured Gemini credentials; review every failure and fallback source; add cases for any discovered semantic gap |
| Full solve journey | Health/analyze plus a deterministic math SSE solve have smoke coverage | Exercise `/api/compute/solve` through routing, IR validation, adapter, solver, SSE events and final result using a controlled provider/staging environment |
| Deployment | No staging deployment or production telemetry inspected | Verify actual deployment runtime, secrets, proxy topology, memory, timeouts and rollback |
| Proxy-aware rate limiting | `TRUSTED_PROXY_IPS` allowlist support and unit tests exist | Set it only to actual trusted proxy peer IPs; ensure the proxy overwrites/sanitizes `X-Forwarded-For`; otherwise forwarded headers are intentionally ignored |
| Rate-limit distribution | Current counters are process-local in-memory state | Confirm single-process deployment or move rate limiting to shared storage/edge infrastructure for multi-instance/serverless deployments |
| Request body limits | Middleware rejects oversized declared `Content-Length` | Add/verify streaming body-size enforcement for chunked requests with no declared length |
| Dependency reproducibility | Backend requirements install successfully in CI | Pin direct/transitive dependencies and use a reviewed lock/constraints file before production |
| Solver coverage | Four structural adapters are tested | Keep unsupported engineering families explicitly blocked or on their separately validated legacy path; do not imply universal engineering support |

## Safety expectations

- Missing or contradictory essential physical conditions must block the affected solver.
- No solver should receive a fabricated support, load position, geometry, material property, unit or end condition.
- AI extraction and numerical computation remain separate. Numerical outputs must come from deterministic solvers.
- Keep PR #11 as draft until all merge blockers are closed or explicitly accepted with documented scope limits.

## Live benchmark

Configure `GEMINI_API_KEY` or `AI_INTEGRATIONS_GEMINI_API_KEY` in the execution environment, then run:

```bash
python tests/run_live_engineering_benchmark.py
```

The runner saves `engineering-benchmark-predictions.jsonl` and `engineering-benchmark-report.json`. Inspect `router_sources` and `deterministic_fallback_cases`: a fallback is not evidence of successful LLM interpretation. Never commit API credentials or raw user data into benchmark artifacts.
