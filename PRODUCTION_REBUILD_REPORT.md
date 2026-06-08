# Production Rebuild Report

## Current Architecture

The codebase now has a backend-owned computation path:

1. Raw input is accepted by the backend.
2. Input is normalized in `backend/engine/math_normalizer.py`.
3. A canonical problem object is built in `backend/engine/problem_pipeline.py`.
4. Domain confidence scores are attached to the canonical object.
5. Feasible methods are inferred from equation/problem structure.
6. Solver selection happens through the backend solver map only.
7. Solver events are normalized before streaming to the frontend.
8. Errors are converted to structured retryable user-facing payloads.

The frontend remains render-only: it sends input, streams backend events, displays backend-returned methods, collects missing values, and retries failed requests.

## Files Changed

- `backend/main.py`
  - Removed dependency on the old keyword router.
  - Uses canonical problem objects for `/api/compute/analyze` and `/api/compute/solve`.
  - Streams `problem_parsed` events with `canonical_problem` and `domain_confidence`.
  - Converts solver-selection and runtime failures into structured error envelopes.

- `backend/engine/models.py`
  - Added `CanonicalProblem`, `DomainScore`, and `ProblemStructure` models.
  - Added backend method payload fields `feasible` and `recommended`.
  - Standardized errors around `message`, `suggestion`, `retryable`, and `retry_available`.

- `backend/engine/problem_pipeline.py`
  - Rebuilt the central canonical pipeline.
  - Added structure-based domain scoring, method inference, requested-method validation, solver-domain mapping, and event normalization.
  - Added deterministic parameter extraction for equations and common engineering quantities.

- `backend/engine/math_normalizer.py`
  - Improved multi-equation extraction from comma/semicolon/newline separated input.
  - Keeps equation normalization centralized before canonical problem construction.

- `backend/engine/interaction.py`
  - Removed method-request text hint tables.
  - Determines missing fields from canonical domain/problem structure.
  - Builds backend-owned method-selection and parameter-collection events.

- `backend/engine/__init__.py`
  - Exports the canonical models and pipeline functions as the single engine interface.

- `backend/capabilities/thermo_engine.py`
  - Fixed invalid LaTeX f-string brace syntax that prevented backend compilation.

- `backend/capabilities/beam_engine.py`
  - Gives simply supported beam statements priority over comparison mentions of cantilevers.
  - Adds a direct conceptual answer path for full-span UDL beam questions.

- `.env.example`
  - Documents optional Groq explainer configuration.

- `frontend/src/App.jsx`
  - Keeps endpoint construction safe when `VITE_BACKEND_URL` is unset.
  - Continues to render backend streaming events without domain/method inference.

- `frontend/src/components/MethodPopup.jsx`
  - Displays the backend `recommended` flag instead of assuming the first method is recommended.

## Files Removed

- `backend/router.py`
  - Removed old keyword/pattern classifier and pre-extractor.

- `backend/method_generator.py`
  - Removed duplicate method-analysis system.

- `backend/methods_registry.py`
  - Removed duplicate method registry.

- `frontend/src/lib/methodDetector.js`
  - Removed stale frontend method/domain detector stub.

- `backend/.venv/`
  - Removed tracked virtual-environment artifacts.

- `backend/__pycache__/` and `backend/solvers/__pycache__/`
  - Removed tracked/generated Python bytecode artifacts.

## Bugs Fixed

- Backend no longer imports or calls the old keyword router.
- Method feasibility is validated by the backend before solver execution.
- Invalid user-selected methods return structured errors with valid alternatives.
- Solver exceptions no longer stream raw stack traces to the UI.
- No-solver cases are errors, not successful final answers.
- Thermodynamics capability engine now compiles after fixing malformed f-string braces.
- Conceptual simply supported beam questions no longer route into cantilever calculations just because the question asks for a cantilever comparison.
- Optional Groq explainer can rewrite final engine answers without changing solved values.
- Direct equation inputs now bypass AI routing entirely, so simple algebra remains deterministic during model outages.
- Temporary model high-demand errors and permanent quota-limit errors are classified separately with correct retry behavior.
- Frontend method popup no longer invents a recommendation based on list order.
- Multi-equation algebra input such as `3x + 2y = 12, x - y = 1` is split into canonical equations.
- Routed summaries such as `unknown / equation_solve` no longer hide the original raw equation from canonical parsing.

## Duplicates Removed

- Removed the old routing system: `backend/router.py`.
- Removed duplicate backend method systems: `backend/method_generator.py` and `backend/methods_registry.py`.
- Removed the stale frontend detector: `frontend/src/lib/methodDetector.js`.
- Removed tracked generated artifacts: `.venv` and `__pycache__` files.

## Remaining Risks

- Some solver internals still contain local operation selection to choose subroutines after canonical dispatch. They should be progressively migrated to consume `canonical_problem` directly.
- Legacy solvers under `backend/solvers/` remain for domains not yet migrated to `backend/capabilities/`.
- The active Python in this shell lacks installed runtime dependencies such as `pydantic`, so full FastAPI runtime tests could not be executed locally here.
- `ARCHITECTURE_REFACTOR.md` is historical and still describes the previous plan; this report reflects the current implementation.

## Validation Performed

- `python3 -m py_compile backend/main.py backend/engine/*.py backend/capabilities/*.py backend/solvers/*.py`
  - Result: passed, with two pre-existing warning-only invalid escape sequence notices in `backend/solvers/utils.py`.

- `npm install` in `frontend/`
  - Result: passed after allowing registry access; installed the declared `plotly.js-dist-min` dependency that was missing locally.

- `npm run build` in `frontend/`
  - Result: passed. Vite reported large Plotly bundle chunks as a warning only.

## Incremental Stabilization — 2026-05-31

### Files Changed

- `backend/engine/math_normalizer.py`
  - Tightened equation splitting so adjacent equations like `x + y = 10 2x - y = 5` split only after a completed numeric right-hand side.

- `backend/engine/problem_pipeline.py`
  - Strengthened confidence scoring for ideal-gas thermodynamics, circuits, ODE language, and reinforced-concrete beam design quantities.
  - Reduced semantic-hint dominance so an old `structural` hint cannot override stronger canonical algebra/thermo evidence.
  - Added canonical problem types for `rc_beam_design` and `constant_pressure_gas_process`.
  - Canonicalizes gas-process values into solver-ready `T1`, `P`, and `m` fields.

- `backend/engine/interaction.py`
  - Disabled frontend-blocking method selection prompts.
  - Prevents complete RC beam and constant-pressure gas problems from entering missing-parameter loops.

- `backend/main.py`
  - Removed the `linear_system -> matrix` override so simultaneous equations route to the algebra engine with elimination/substitution steps.

- `backend/capabilities/beam_engine.py`
  - Fixed an existing duplicate `if w > ZERO_TOL:` syntax regression.
  - Added deterministic RC beam design response for factored UDL bending, provided `3T20` steel adequacy, support shear, and diagram events.
  - Emits simply supported UDL diagrams for conceptual beam questions.

- `backend/capabilities/thermo_engine.py`
  - Added deterministic constant-pressure ideal-gas process solving for final temperature, boundary work, heat added, and verification.

- `frontend/src/App.jsx`
  - Preserves supplemental parameters across interruption resumes.
  - Sends only backend method IDs back to the backend if method selection is ever enabled again.

### Bugs Fixed

- Simple equations such as `2x - 4 = 9` now stay in canonical algebra instead of `unknown / equation_solve`.
- Simultaneous equations such as `x + y = 10, 2x - y = 5` no longer route to beam or matrix-only paths.
- Complete thermodynamics word problems no longer open method/missing-parameter loops before solving.
- Complete RC beam design word problems no longer repeatedly request inputs already present in the statement.
- Beam conceptual outputs now include beam layout, shear-force, and bending-moment diagram events.
- Frontend remains render-only and does not infer domain, methods, or solver route.

### Validation Performed

- `python3 -m py_compile backend/engine/problem_pipeline.py backend/engine/interaction.py backend/engine/math_normalizer.py backend/main.py backend/capabilities/beam_engine.py backend/capabilities/thermo_engine.py backend/capabilities/symbolic_engine.py`
  - Result: passed.

- `cd frontend && npm run build`
  - Result: passed. Vite reported only the existing large Plotly chunk warning.

### Remaining Runtime Validation Blocker

- The active backend Python environment does not currently have required runtime packages installed (`pydantic`, `sympy`, etc.), so live FastAPI/SSE solve tests could not be executed in this shell. Install `backend/requirements.txt` into the active venv before running end-to-end server tests.

## Repo-Wide Audit — 2026-05-31

### What This Repo Is Meant To Be

This repository is a derivation-first engineering computation studio. The intended architecture is:

- React frontend: render-only notebook UI for raw questions, streamed derivation steps, diagrams, summaries, errors, and optional backend-returned method lists.
- FastAPI backend: the intelligence layer that normalizes input, extracts canonical problem objects, scores domains, selects solver capability, streams deterministic solving steps, verifies results, and optionally sends final answers to Groq for clearer explanation.
- Capability engines: deterministic symbolic/numeric solvers for algebra, calculus/ODE, structural beams, mechanics, thermodynamics, circuits, and matrices.
- Legacy solvers: still used for fluids, physics, controls, statistics, and data visualization until those domains are migrated into `backend/capabilities/`.

### What Was Making It Inefficient Or Fragile

- AI routing could still run for normal word problems and return a bad `domain`, causing beam/structural capture of unrelated questions.
- Problem type hints from AI were trusted before canonical structure, so `unknown / general` or stale types could hide valid equations.
- Domain scoring had broad unit matching: `pa` and generic single-letter parameters could pull thermodynamics/structural/circuits in the wrong direction.
- Simple linear systems could be overridden to the matrix solver instead of the algebra derivation engine.
- Method and missing-parameter interruptions could restart the same pipeline with incomplete state, creating frontend-visible loops.
- Diagram payloads for new factored loads were not rendered by the frontend schematic.
- The app has duplicate serving layers: FastAPI can serve the built frontend, while `server/` starts FastAPI and proxies SSE for dev. This is workable but heavier than one production entrypoint.
- Plotly is dynamically imported, which is good, but it is still the largest frontend payload when diagrams are opened.
- Legacy solver folders still contain local keyword dispatch inside each solver. This is acceptable as internal subroutine selection, but it is not yet a perfect canonical-only engine.

### Fixes Applied In This Pass

- `backend/main.py`
  - Made text routing deterministic-by-default with `USE_AI_ROUTER=0`; Gemini routing is now opt-in instead of a default route authority.
  - Kept Groq as an HTTP-based optional explainer, so no Groq package is required in `backend/requirements.txt`.

- `backend/engine/problem_pipeline.py`
  - Always combines raw input with AI summary instead of allowing the summary to replace the original math/problem statement.
  - Canonical problem type inference now prioritizes mathematical/domain structure before any hinted type.
  - Linear systems score algebra more strongly and matrix less strongly unless explicitly matrix-oriented.
  - Tightened unit-family matching to exact normalized unit tokens, reducing `pa`/letter false positives.
  - Added deterministic scoring and problem-type inference for mechanics, fluids, controls, statistics, and data visualization.
  - Added lightweight plot expression inference for common plot requests.

- `frontend/src/components/DiagramRenderer.jsx`
  - Renders backend `factored_udl` loads in beam schematics as `wu`, so RC beam design diagrams appear correctly.

### Current Readiness Assessment

The repo is now more stable and closer to the intended production architecture, especially for algebra, beam UDL/RC beam checks, constant-pressure ideal-gas problems, RC circuits, and basic ODEs. It is not yet a world-class MATLAB/Mathematica/EES replacement across every advanced engineering topic because several migrated capability engines still need deeper canonical schemas and regression coverage.

### Must-Do Before Calling It Production-Grade

- Install backend runtime dependencies in the active venv and run live FastAPI/SSE smoke tests.
- Add regression tests for canonical classification: algebra, beam, RC beam, thermodynamics, circuits, ODE, controls, fluids, statistics, and plotting.
- Expand the migrated fluids/controls/statistics/data-viz capability engines with deeper canonical schemas and regression tests.
- Replace internal keyword sub-dispatch in capability engines with `problem_type` and canonical property dispatch.
- Add a small benchmark suite for routing latency and solver latency.
- Decide the production entrypoint: either FastAPI serves `frontend/dist`, or Node proxies FastAPI, not both.

## Solver Production Pass — 2026-05-31

### Solver Issues Found

- `backend/capabilities/*`: strongest and preferred engines, but some were too strict when students asked conceptual questions without numeric values.
- `backend/solvers/*`: legacy engines remain useful for fluids, controls, statistics, physics, and data visualization, but many older failures returned `final` answers beginning with `Error:` instead of structured error events.
- `backend/engine/problem_pipeline.py`: canonical extraction lacked common natural-language values for mechanics, fluids, controls, statistics, matrices, and resistor lists, making otherwise valid questions look under-specified.
- Repository hygiene: `.venv_backend` metadata was tracked, and generated Python caches/frontend build output were present locally.

### Solver Fixes Applied

- `backend/engine/problem_pipeline.py`
  - Converts legacy `final` answers that start with `Error`, `Solver Error`, or `Engine Error` into structured backend errors.
  - Extracts common mechanics quantities: speed/velocity, acceleration, time, displacement, mass, launch angle.
  - Extracts fluids quantities: flow rate/discharge and pipe diameter, with `d_pipe -> D` canonical aliasing.
  - Extracts controls coefficients: `num: [...]` and `den: [...]`.
  - Extracts statistics datasets from `data: [...]`, `values: ...`, etc.
  - Extracts matrix literals from natural text like `matrix [[1,2],[3,4]]`.
  - Extracts resistor lists for circuit network problems.

- `backend/capabilities/mechanics_engine.py`
  - Projectile questions without numeric initial speed now return governing equations and required inputs instead of hard-failing.

- `backend/capabilities/circuit_engine.py`
  - Ohm's-law questions with fewer than two values now return the general formulas and required inputs instead of hard-failing.

- `backend/capabilities/matrix_engine.py`
  - Matrix requests without a provided matrix now return accepted input format and supported operations instead of a terse solver error.

- `backend/solvers/statistics.py`
  - Missing/invalid data now streams a structured `error` event instead of a successful `final` answer.
  - Statistics exceptions now stream structured `error` events.

- `backend/solvers/utils.py`
  - Fixed invalid LaTeX escape warnings in uncertainty-report strings.

- `.gitignore`
  - Added `.venv_backend/` so local Python virtualenv files do not enter Git again.

### Repo Cleanup Applied

- Removed tracked `.venv_backend` files from Git.
- Removed local generated Python `__pycache__` folders.
- Removed local generated `frontend/dist` build output after validation.

### Validation

- `python3 -m py_compile backend/main.py backend/engine/*.py backend/capabilities/*.py backend/solvers/*.py`
  - Passed.

- `cd frontend && npm run build`
  - Passed. Existing warning remains: Plotly chunk is large, but it is dynamically imported only when diagrams render.

### Remaining Production Work

- Add automated smoke/regression tests once backend dependencies are fully installed in a clean venv.
- Expand fluids, controls, statistics, physics, and data visualization capability engines beyond the migrated legacy coverage.
- Strengthen solver capability contracts with subtype-level scoring and automated regression tests.
- Add dimensional-analysis verification across all engineering domains, not just selected structural/algebra checks.

## Parser/Router Stabilization Pass — 2026-05-31

### Bugs Fixed

- `backend/engine/math_normalizer.py`
  - Fixed false unit extraction from adjacent equations such as `x + y = 10, 2x - y = 5`; the parser no longer invents units like `{y: "y"}` or `{p: "0"}`.
  - Added an equation-candidate guard so prose assignments like `R = 10 kOhm` and `Cp = 1.005 kJ/kg·K` do not enter solvers as corrupted equations.
  - Narrowed compact product splitting to two-letter products only, preserving named variables such as `area`, `force`, `stress`, and `theta` while still parsing `xy` as `x*y`.

- `backend/engine/problem_pipeline.py`
  - Corrected canonical `is_system`: a system now means multiple equations, not merely one equation with multiple symbols.
  - This prevents formulas like `stress = force/area` from being mislabeled as nonlinear systems.

- `backend/main.py`
  - The dispatcher now enforces each capability module's `can_solve(canonical_problem)` contract before executing a solver.
  - A solver with capability score `0` is rejected instead of becoming an accidental fallback.

- `backend/capabilities/calculus_engine.py`
  - Updated `can_solve()` so ODE problems routed through the calculus engine are accepted intentionally.

### Regression Results

- `2x - 4 = 3` → `algebra / single_equation`, no missing-parameter popup.
- `4 notebooks + 3 pens cost ₦2100; 2 notebooks + 5 pens cost ₦1900` → `algebra / linear_system`, equations extracted as `4*n + 3*p = 2100` and `2*n + 5*p = 1900`.
- `2x² + 3xy - y² = 12; x² - xy + 4y² = 21` → `algebra / nonlinear_system`, no circuit routing, no missing-parameter popup, all four symbolic solution sets returned.
- `RC circuit has R = 10 kOhm and C = 100 uF` → `circuits / rc_circuit`, no algebra equation pollution and no Ohm's-law popup.
- Constant-pressure ideal-gas word problem → `thermo / constant_pressure_gas_process`, no structural/beam routing.
- Simply supported UDL beam → `structural / beam_analysis`.

### Validation Run

- `PYTHONPATH=backend .venv_backend/bin/python -m compileall backend`
  - Passed.
- Direct parser and algebra solver smokes passed for simple linear equation, cost word-problem linear system, and nonlinear simultaneous equations.
- Live FastAPI import was not run in this shell because the local `.venv_backend` is missing `fastapi` and `google-genai`; these are already listed in `backend/requirements.txt`.

### Additional Hardening In Same Pass

- `backend/engine/problem_pipeline.py`
  - ODE equations now outrank plain algebra when derivative structure is present, preventing `x'' + 3x' + 2x = 0` from being classified as algebra.
  - Added `rc_circuit` and `rl_circuit` problem-type inference so RC transient questions do not trigger the Ohm's-law missing-value popup.
  - Added circuit unit scaling during canonicalization: `kOhm -> Ω`, `uF -> F`, `mH/uH -> H`, etc. Example: `R = 10 kOhm`, `C = 100 uF` becomes `R = 10000`, `C = 0.0001`, so `τ = RC = 1 s`.

- `backend/engine/math_normalizer.py`
  - Fixed over-greedy `Solve ...` stripping that removed ODE expressions before parsing.
  - Filtered false units such as `and`, `with`, `the`, and other prose words.

- `backend/capabilities/calculus_engine.py`
  - ODE solver now supports dependent variables other than `y`, e.g. `x'' + 3x' + 2x = 0`.
  - Added implicit multiplication after derivative normalization, e.g. `3x'` becomes `3*Derivative(x(t), t)`.

### Final Targeted Smoke Results

- Simple equation: `2x - 4 = 3` → `algebra / single_equation`, solved.
- Linear system: `x + y = 10, 2x - y = 5` → `algebra / linear_system`, solved.
- Cost word problem: notebook/pen equations → `algebra / linear_system`, solved.
- Nonlinear simultaneous equations → `algebra / nonlinear_system`, returned 4 solution sets.
- Thermodynamics gas process → `thermo / constant_pressure_gas_process`, no missing-parameter popup.
- RC circuit time constant → `circuits / rc_circuit`, no Ohm's-law popup, canonical SI values generated.
- ODE: `x'' + 3x' + 2x = 0` → `ode / ode`, solved to `x(t) = (C1 + C2*exp(-t))*exp(-t)`.

## Basic Equation + Proxy Routing Fix — 2026-05-31

### Root Causes Found

- Natural wrappers like `Find x if ...`, `What is x when ...`, and `Determine the value of x from ...` were not stripped before equation extraction, causing corrupted equations such as `x i*f 2*x - 9 = 24`.
- Trailing question punctuation stayed inside equations, e.g. `2*x - 9 = 24?`, which made SymPy fail even though routing was correct.
- The dev Node proxy only handled `POST /api/compute`, while React sends `POST /api/compute/solve`; this could bypass the FastAPI solve endpoint in dev/proxy mode.

### Fixes Applied

- `backend/engine/math_normalizer.py`
  - Added safe stripping for common natural-language equation wrappers.
  - Removed trailing `?` and sentence punctuation from normalized equations.
  - Added a small deterministic plain-language linear-equation extractor for forms such as `2 times a number minus 9 equal to 24` and `twice a number plus 5 equals 17`.

- `server/routes/compute.js`
  - Added explicit proxy support for `/api/compute/solve` and `/api/compute/analyze`.
  - Kept backward-compatible `/api/compute` solve proxy.
  - Preserved SSE streaming to the frontend.

### Behavior Smoke Results

- `2X - 9 = 24` → `algebra / single_equation`, solved: `X = 33/2 = 16.5`.
- `Find x if 2x - 9 = 24` → `algebra / single_equation`, solved: `x = 33/2 = 16.5`.
- `What is x if 2x - 9 = 24?` → `algebra / single_equation`, solved.
- `A student has 2 times a number minus 9 equal to 24` → `algebra / single_equation`, solved.
- Word problems still route by their actual structure: thermo → `thermo`, beam → `structural`, RC circuit → `circuits`, projectile → `mechanics`.
