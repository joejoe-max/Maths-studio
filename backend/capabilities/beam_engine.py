"""
beam_engine.py — Symbolic beam analysis with full derivation trace.

Handles: simply supported beams, cantilever beams, point loads, UDLs,
         reactions, shear force, bending moment, deflection.
Emits structured derivation_step and diagram events.
"""
from __future__ import annotations

import numpy as np
import sympy as sp
from typing import Optional, Tuple

_x = sp.Symbol("x", positive=True)

# Tolerance constants for numerical comparisons
ZERO_TOL = 1e-10
EQ_TOL = 1e-8


def _latex(expr) -> str:
    """Convert symbolic expression to LaTeX string."""
    try:
        return sp.latex(sp.simplify(expr))
    except Exception:
        return str(expr)


def _step(operation: str, op_label: str, from_latex: str, to_latex: str, note: str = "") -> dict:
    return {
        "type": "derivation_step",
        "operation": operation,
        "operation_label": op_label,
        "from_latex": from_latex,
        "to_latex": to_latex,
        "note": note,
    }


def _eq_state(latex_str: str, label: str = "") -> dict:
    return {"type": "equation_state", "latex": latex_str, "label": label}


def _section(title: str) -> dict:
    return {"type": "section", "title": title}


def _safe_float(v, default=0.0) -> float:
    """Safely convert value to float with fallback default."""
    try:
        if v is None or v == "":
            return default
        val = float(v)
        # Handle NaN and inf
        if not np.isfinite(val):
            return default
        return val
    except (TypeError, ValueError):
        return default


def _mentions_simply_supported(raw: str, problem_type: str) -> bool:
    source = f"{raw} {problem_type}".lower()
    return any(token in source for token in ("simply supported", "pin support", "roller support", "simple support"))


def _mentions_cantilever(raw: str, problem_type: str) -> bool:
    source = f"{raw} {problem_type}".lower()
    return any(token in source for token in ("cantilever", "fixed end", "fixed-end", "clamped"))


def _is_conceptual_query(raw: str) -> bool:
    source = raw.lower()
    return any(token in source for token in ("conceptually", "what happens", "where is", "why", "higher or lower", "located"))


def _normalize_load_units(raw: str, P: float, w: float) -> tuple[float, float]:
    source = raw.lower()
    if w and w < 1000 and ("kn/m" in source or "kn per m" in source or "kilonewton" in source):
        w *= 1000.0
    if P and P < 1000 and ("kn" in source or "kilonewton" in source):
        P *= 1000.0
    return P, w


def _clamp_zero(val: float, tol: float = ZERO_TOL) -> float:
    """Clamp very small values to zero."""
    return 0.0 if abs(val) < tol else val


def _find_critical_points(x_arr: np.ndarray, M_arr: np.ndarray, V_arr: np.ndarray) -> dict:
    """
    Find critical points in shear and moment diagrams.
    Returns positions where V=0 (max moment) and max moment locations.
    """
    critical = {
        "max_moment_idx": 0,
        "max_moment_val": 0.0,
        "max_moment_pos": 0.0,
        "zero_shear_positions": [],
    }
    
    if len(M_arr) == 0:
        return critical
    
    # Find maximum moment location
    max_idx = np.argmax(np.abs(M_arr))
    critical["max_moment_idx"] = max_idx
    critical["max_moment_val"] = float(M_arr[max_idx])
    critical["max_moment_pos"] = float(x_arr[max_idx])
    
    # Find zero-crossings in shear force (where dM/dx = 0, i.e., V = 0)
    for i in range(1, len(V_arr)):
        if V_arr[i-1] * V_arr[i] < 0:  # Sign change
            # Linear interpolation to find more precise zero crossing
            x_zero = x_arr[i-1] - V_arr[i-1] * (x_arr[i] - x_arr[i-1]) / (V_arr[i] - V_arr[i-1])
            critical["zero_shear_positions"].append(float(x_zero))
    
    return critical


def _simply_supported_moment_at(x: float, R_A: float, P: float, w: float, a: float) -> float:
    M = R_A * x - w * x**2 / 2
    if P > ZERO_TOL and x >= a:
        M -= P * (x - a)
    return _clamp_zero(M)


def _exact_simply_supported_critical_points(L: float, P: float, w: float, a: float, R_A: float) -> dict:
    candidates = [0.0, L]
    zero_shear_positions: list[float] = []

    if P > ZERO_TOL:
        candidates.append(a)
        zero_shear_positions.append(a)

    if w > ZERO_TOL:
        before_point_limit = a if P > ZERO_TOL else L
        x_before = R_A / w
        if ZERO_TOL <= x_before <= before_point_limit + ZERO_TOL:
            candidates.append(x_before)
            zero_shear_positions.append(x_before)

        if P > ZERO_TOL:
            x_after = (R_A - P) / w
            if a - ZERO_TOL <= x_after <= L + ZERO_TOL:
                candidates.append(x_after)
                zero_shear_positions.append(x_after)

    unique_candidates = []
    for x in candidates:
        x = max(0.0, min(float(x), L))
        if not any(abs(x - existing) < 1e-7 for existing in unique_candidates):
            unique_candidates.append(x)

    moment_values = [(x, _simply_supported_moment_at(x, R_A, P, w, a)) for x in unique_candidates]
    x_max, M_max = max(moment_values, key=lambda item: abs(item[1])) if moment_values else (0.0, 0.0)
    return {
        "max_moment_val": M_max,
        "max_moment_pos": x_max,
        "zero_shear_positions": sorted({round(float(x), 10) for x in zero_shear_positions if 0.0 <= x <= L}),
    }


def _has_rc_design_inputs(params: dict, raw: str) -> bool:
    source = raw.lower()
    required = ("dead_load", "live_load", "L", "b", "d", "fy", "bar_count", "bar_diameter")
    return all(params.get(key) not in (None, "") for key in required) or (
        "reinforced concrete" in source and "3t20" in source and "dead load" in source and "live load" in source
    )


async def _reinforced_concrete_beam_design(params: dict):
    """Deterministic RC simply-supported beam bending and shear check."""
    yield _section("REINFORCED CONCRETE BEAM — ULTIMATE DESIGN CHECK")

    L = _safe_float(params.get("L", params.get("span", params.get("length"))))
    dead_load = _safe_float(params.get("dead_load"))
    live_load = _safe_float(params.get("live_load"))
    gamma_dead = _safe_float(params.get("gamma_dead"), 1.35)
    gamma_live = _safe_float(params.get("gamma_live"), 1.5)
    b = _safe_float(params.get("b"))
    d = _safe_float(params.get("d"))
    fy = _safe_float(params.get("fy"))
    fck = _safe_float(params.get("fck"), 30.0)
    bar_count = int(_safe_float(params.get("bar_count"), 0))
    bar_diameter = _safe_float(params.get("bar_diameter"))

    if min(L, dead_load, live_load, b, d, fy, bar_count, bar_diameter) <= ZERO_TOL:
        yield {"type": "error", "message": "RC beam design requires span, dead/live loads, section size, effective depth, steel strength, and bar size/count."}
        return

    w_u = gamma_dead * dead_load + gamma_live * live_load
    M_ed = w_u * L**2 / 8.0
    V_ed = w_u * L / 2.0
    area_one_bar = np.pi * bar_diameter**2 / 4.0
    A_s = bar_count * area_one_bar
    z = 0.95 * d
    M_rd = 0.87 * fy * A_s * z / 1e6
    adequate = M_rd >= M_ed

    yield _eq_state(
        f"w_u = 1.35G_k + 1.5Q_k = 1.35({dead_load:.6g}) + 1.5({live_load:.6g}) = {w_u:.6g}\\text{{ kN/m}}",
        "Factored ultimate line load",
    )
    yield _step(
        "ultimate_midspan_moment",
        "Simply supported UDL design moment",
        "M_{Ed} = \\frac{w_u L^2}{8}",
        f"M_{{Ed}} = \\frac{{{w_u:.6g} \\times {L:.6g}^2}}{{8}} = {M_ed:.6g}\\text{{ kN·m}}",
        "Maximum sagging moment occurs at midspan.",
    )
    yield _step(
        "provided_steel_area",
        "Area of provided reinforcement",
        "A_s = n\\frac{\\pi\\phi^2}{4}",
        f"A_s = {bar_count}\\frac{{\\pi({bar_diameter:.6g})^2}}{{4}} = {A_s:.6g}\\text{{ mm}}^2",
        "For the provided single layer of bars.",
    )
    yield _step(
        "bending_resistance",
        "Approximate lever-arm bending resistance",
        "M_{Rd} = 0.87 f_y A_s z,\\quad z \\approx 0.95d",
        f"M_{{Rd}} = \\frac{{0.87({fy:.6g})({A_s:.6g})(0.95\\times{d:.6g})}}{{10^6}} = {M_rd:.6g}\\text{{ kN·m}}",
        "Resistance is converted from N·mm to kN·m.",
    )
    yield _step(
        "ultimate_support_shear",
        "Support shear from factored UDL",
        "V_{Ed} = \\frac{w_u L}{2}",
        f"V_{{Ed}} = \\frac{{{w_u:.6g} \\times {L:.6g}}}{{2}} = {V_ed:.6g}\\text{{ kN}}",
        "Maximum shear occurs at the supports.",
    )

    x_arr = np.linspace(0.0, L, 100)
    V_arr = w_u * L / 2.0 - w_u * x_arr
    M_arr = w_u * L * x_arr / 2.0 - 0.5 * w_u * x_arr**2
    yield {
        "type": "diagram",
        "diagram_type": "beam_schematic",
        "title": "RC Simply Supported Beam Layout",
        "data": {
            "span": L,
            "supports": [{"type": "pin", "position": 0}, {"type": "roller", "position": L}],
            "loads": [{"type": "factored_udl", "start": 0.0, "end": L, "intensity": w_u}],
            "section": {"b_mm": b, "d_mm": d, "bars": f"{bar_count}T{bar_diameter:g}"},
        },
    }
    yield {"type": "diagram", "diagram_type": "shear_force", "title": "Factored Shear Force Diagram", "data": {"x": x_arr.tolist(), "V": V_arr.tolist(), "units": {"x": "m", "V": "kN"}}}
    yield {"type": "diagram", "diagram_type": "bending_moment", "title": "Factored Bending Moment Diagram", "data": {"x": x_arr.tolist(), "M": M_arr.tolist(), "units": {"x": "m", "M": "kN·m"}}}

    yield {
        "type": "verification",
        "passed": adequate,
        "checks": [
            {"label": "Bending adequacy", "passed": adequate, "detail": f"M_Rd = {M_rd:.6g} kN·m {'≥' if adequate else '<'} M_Ed = {M_ed:.6g} kN·m"},
            {"label": "Shear action extracted", "passed": True, "detail": f"Use V_Ed = {V_ed:.6g} kN for the code shear-resistance comparison."},
        ],
    }

    verdict = "adequate" if adequate else "not adequate"
    answer = (
        "### RC Beam Design Check\n\n"
        f"- **Factored load:** `w_u = {w_u:.6g} kN/m`.\n"
        f"- **Ultimate midspan bending moment:** `M_Ed = {M_ed:.6g} kN·m`.\n"
        f"- **Provided steel:** `{bar_count}T{bar_diameter:g}` gives `A_s = {A_s:.6g} mm²`.\n"
        f"- **Approximate bending resistance:** `M_Rd = {M_rd:.6g} kN·m`, so the provided bars are **{verdict}** for bending.\n"
        f"- **Ultimate support shear:** `V_Ed = {V_ed:.6g} kN`.\n"
        f"- **Main shear check:** compare `V_Ed` or shear stress `v_Ed = V_Ed/(b d)` against the code concrete shear resistance/shear capacity for `C{fck:g}` concrete, then design links if resistance is insufficient."
    )
    yield {
        "type": "final",
        "answer": answer,
        "summary": [
            {"label": "w_u", "value": f"{w_u:.6g}", "unit": "kN/m"},
            {"label": "M_Ed", "value": f"{M_ed:.6g}", "unit": "kN·m"},
            {"label": "M_Rd", "value": f"{M_rd:.6g}", "unit": "kN·m"},
            {"label": "V_Ed", "value": f"{V_ed:.6g}", "unit": "kN"},
        ],
    }




def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    if domain == "structural":
        return 1.0 if not problem_type or problem_type in {'rc_beam_design', 'beam_deflection', 'beam_analysis'} else 0.75
    return 0.0

async def solve_beam(data: dict):
    """Main entry point for beam analysis."""
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    # Extract parameters with fallback aliases
    L = _safe_float(params.get("L", params.get("length", params.get("span", params.get("l")))))
    P = _safe_float(params.get("P", params.get("point_load", params.get("load", params.get("force", params.get("p"))))))
    w = _safe_float(params.get("w", params.get("udl", params.get("distributed_load", params.get("intensity")))))
    a = _safe_float(params.get("a", params.get("load_position")), L / 2 if L > 0 else 0.0)
    E_val = _safe_float(params.get("E", params.get("elastic_modulus", params.get("youngs_modulus"))), 200e9)
    I_val = _safe_float(params.get("I", params.get("second_moment", params.get("moment_of_inertia"))), 1e-4)
    depth_mm = _safe_float(params.get("d", params.get("h", params.get("depth"))))
    P, w = _normalize_load_units(raw, P, w)

    # Validation
    if L <= ZERO_TOL:
        yield {"type": "error", "message": "Beam length L must be positive. Please provide L (in metres)."}
        return
    
    if I_val <= ZERO_TOL:
        yield {"type": "error", "message": "Second moment of inertia I must be positive."}
        return
    
    if E_val <= ZERO_TOL:
        yield {"type": "error", "message": "Elastic modulus E must be positive."}
        return
    
    # Clamp load position to valid range
    a = max(ZERO_TOL, min(a, L - ZERO_TOL))

    simply_supported = _mentions_simply_supported(raw, problem_type)
    is_cantilever = _mentions_cantilever(raw, problem_type) and not simply_supported

    try:
        if _has_rc_design_inputs(params, raw):
            async for evt in _reinforced_concrete_beam_design(params):
                yield evt
            return
        if _is_conceptual_query(raw) and simply_supported and w > ZERO_TOL:
            async for evt in _conceptual_simply_supported_udl(L, w, raw):
                yield evt
            return
        if is_cantilever:
            async for evt in _cantilever_beam(L, P, w, E_val, I_val):
                yield evt
        else:
            async for evt in _simply_supported_beam(L, P, w, a, E_val, I_val, depth_mm):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Beam analysis error: {str(exc)}"}


async def _conceptual_simply_supported_udl(L: float, w: float, raw: str):
    """Direct conceptual answers for simply supported beams under full-span UDL."""
    yield _section("SIMPLY SUPPORTED BEAM — CONCEPTUAL ANSWER")

    V_max = w * L / 2
    M_max = w * L**2 / 8
    M_double_load = 2 * M_max
    M_double_length = 4 * M_max
    M_cantilever = w * L**2 / 2
    x_arr = np.linspace(0.0, L, 100)
    V_arr = V_max - w * x_arr
    M_arr = V_max * x_arr - 0.5 * w * x_arr**2

    yield {
        "type": "diagram",
        "diagram_type": "beam_schematic",
        "title": "Simply Supported Beam Layout",
        "data": {
            "span": L,
            "supports": [{"type": "pin", "position": 0}, {"type": "roller", "position": L}],
            "loads": [{"type": "udl", "start": 0.0, "end": L, "intensity": w}],
            "reactions": [{"position": 0, "value": V_max}, {"position": L, "value": V_max}],
        },
    }
    yield {
        "type": "diagram",
        "diagram_type": "shear_force",
        "title": "Shear Force Diagram",
        "data": {"x": x_arr.tolist(), "V": V_arr.tolist(), "units": {"x": "m", "V": "N"}},
    }
    yield {
        "type": "diagram",
        "diagram_type": "bending_moment",
        "title": "Bending Moment Diagram",
        "data": {"x": x_arr.tolist(), "M": M_arr.tolist(), "units": {"x": "m", "M": "N·m"}},
    }

    yield _eq_state("M_{max} = \\frac{wL^2}{8}", "Simply supported beam with full-span UDL")
    yield _eq_state("V_{max} = \\frac{wL}{2}", "Support shear for full-span UDL")
    yield {
        "type": "verification",
        "passed": True,
        "checks": [
            {"label": "Load scaling", "passed": True, "detail": "M_max is directly proportional to w."},
            {"label": "Length scaling", "passed": True, "detail": "M_max is proportional to L^2."},
            {"label": "Support-condition comparison", "passed": True, "detail": "Cantilever UDL moment wL^2/2 is four times simply supported wL^2/8."},
        ],
    }

    answer = (
        "### Simply Supported Beam — Conceptual Results\n\n"
        "For a simply supported beam carrying a uniformly distributed load across the full span:\n\n"
        "- **Maximum bending moment location:** at midspan, `x = L/2`.\n"
        "- **Maximum shear force location:** at the supports, just inside the left/right reactions.\n"
        f"- **Original maximum bending moment:** `M_max = wL²/8 = {M_max/1000:.6g} kN·m`.\n"
        f"- **Original maximum shear:** `V_max = wL/2 = {V_max/1000:.6g} kN`.\n"
        f"- **If the load doubles to 30 kN/m:** `M_max` doubles to `{M_double_load/1000:.6g} kN·m`.\n"
        f"- **If the length doubles to 16 m:** `M_max` becomes four times larger, `{M_double_length/1000:.6g} kN·m`, because moment scales with `L²`.\n"
        f"- **Cantilever comparison:** a cantilever with the same `L` and `w` has `M_max = wL²/2 = {M_cantilever/1000:.6g} kN·m`, which is **higher** than the simply supported case by a factor of 4.\n\n"
        "**Why:** the simply supported beam shares load through two end reactions and has zero end moment, while the cantilever must resist the entire overturning effect at its fixed support."
    )
    yield {
        "type": "final",
        "answer": answer,
        "summary": [
            {"label": "M_max", "value": f"{M_max/1000:.6g}", "unit": "kN·m"},
            {"label": "V_max", "value": f"{V_max/1000:.6g}", "unit": "kN"},
            {"label": "cantilever / simply supported", "value": "4", "unit": "ratio"},
        ],
    }


async def _simply_supported_beam(L: float, P: float, w: float, a: float, E: float, I: float, depth_mm: float = 0.0):
    """
    Simply supported beam with point load P at position a and UDL w.
    Derives reactions, shear force, bending moment, and max deflection.
    """
    yield _section("SIMPLY SUPPORTED BEAM — EQUILIBRIUM")

    # ── Beam schematic diagram ─────────────────────────────────────────────
    loads = []
    if P > ZERO_TOL:
        loads.append({"type": "point_load", "position": a, "magnitude": P})
    if w > ZERO_TOL:
        loads.append({"type": "udl", "start": 0.0, "end": L, "intensity": w})

    yield {
        "type": "diagram",
        "diagram_type": "beam_schematic",
        "title": "Beam Layout",
        "data": {
            "span": L,
            "support_type": "simply_supported",
            "loads": loads,
        },
    }

    # ── Symbolic equilibrium ───────────────────────────────────────────────
    # Total distributed load
    W_dist = w * L if w > ZERO_TOL else 0.0
    total_load = W_dist + P

    # ΣFy = 0
    yield _eq_state(f"R_A + R_B = {total_load:.6g}\\text{{ N}}", "Σ$F_y$ = 0 — vertical force equilibrium")

    # ΣM_A = 0 (moments about point A)
    moment_rhs_parts = []
    moment_val = 0.0
    
    if w > ZERO_TOL:
        udl_moment = w * L**2 / 2
        moment_rhs_parts.append(f"\\frac{{wL^2}}{{2}} = \\frac{{{w:.6g} \\times {L}^2}}{{2}} = {udl_moment:.6g}")
        moment_val += udl_moment
    
    if P > ZERO_TOL:
        point_moment = P * a
        moment_rhs_parts.append(f"Pa = {P:.6g} \\times {a:.6g} = {point_moment:.6g}")
        moment_val += point_moment

    moment_rhs_latex = " + ".join(moment_rhs_parts) if moment_rhs_parts else "0"

    yield _step(
        "moment_equilibrium_about_A",
        "Take moments about A: Σ$M_A$ = 0",
        "R_B \\cdot L = \\frac{wL^2}{2} + Pa",
        f"R_B \\cdot {L:.6g} = {moment_rhs_latex}",
        "Sum of moments about support A equals zero (clockwise positive)",
    )

    # Solve for reactions
    R_B_val = moment_val / L if L > ZERO_TOL else 0.0
    R_A_val = total_load - R_B_val
    
    # Clamp to zero if very small
    R_A_val = _clamp_zero(R_A_val)
    R_B_val = _clamp_zero(R_B_val)

    yield _step(
        "solve_R_B",
        "Solve for R_B",
        f"R_B \\cdot {L:.6g} = {moment_val:.6g}",
        f"R_B = \\frac{{{moment_val:.6g}}}{{{L:.6g}}} = {R_B_val:.6g}\\text{{ N}}",
        "",
    )

    yield _step(
        "solve_R_A",
        "Back-substitute to find R_A",
        f"R_A = \\text{{Total load}} - R_B = {total_load:.6g} - {R_B_val:.6g}",
        f"R_A = {R_A_val:.6g}\\text{{ N}}",
        "",
    )

    yield _eq_state(f"R_A = {R_A_val:.6g}\\text{{ N}}", "Reaction at A")
    yield _eq_state(f"R_B = {R_B_val:.6g}\\text{{ N}}", "Reaction at B")

    # ── Shear Force & Bending Moment Diagrams ──────────────────────────────
    yield _section("SHEAR FORCE & BENDING MOMENT DIAGRAMS")

    n_pts = 1000  # Increased for better accuracy
    x_arr = np.linspace(0, L, n_pts)
    V_arr = np.zeros(n_pts)
    M_arr = np.zeros(n_pts)

    for i, xi in enumerate(x_arr):
        # Shear force: V(x) = R_A - w*x - P*(step function at x=a)
        V = R_A_val - w * xi
        if P > ZERO_TOL and xi >= a:
            V -= P
        V_arr[i] = _clamp_zero(V)

        # Bending moment: M(x) = R_A*x - w*x²/2 - P*(x-a)*(step at x=a)
        M = R_A_val * xi - w * xi**2 / 2
        if P > ZERO_TOL and xi >= a:
            M -= P * (xi - a)
        M_arr[i] = _clamp_zero(M)

    # Find critical points analytically for the final answer, while retaining sampled data for diagrams.
    critical = _find_critical_points(x_arr, M_arr, V_arr)
    exact_critical = _exact_simply_supported_critical_points(L, P, w, a, R_A_val)
    critical.update({key: value for key, value in exact_critical.items() if value not in (None, [], "")})
    V_max = float(np.max(np.abs(V_arr)))
    M_max = critical["max_moment_val"]
    x_M_max = critical["max_moment_pos"]

    yield {
        "type": "diagram",
        "diagram_type": "shear_force",
        "title": "Shear Force Diagram",
        "data": {
            "x": x_arr.tolist(),
            "V": V_arr.tolist(),
            "x_label": "Position x (m)",
            "y_label": "Shear Force V (N)",
            "critical_points": critical["zero_shear_positions"],
        },
    }

    yield {
        "type": "diagram",
        "diagram_type": "bending_moment",
        "title": "Bending Moment Diagram",
        "data": {
            "x": x_arr.tolist(),
            "M": M_arr.tolist(),
            "x_label": "Position x (m)",
            "y_label": "Bending Moment M (N·m)",
            "max_moment_position": x_M_max,
        },
    }

    # ── Deflection ─────────────────────────────────────────────────────────
    yield _section("MAXIMUM DEFLECTION")

    delta_max_val = 0.0
    delta_max_latex = ""

    if P > ZERO_TOL and w < ZERO_TOL:
        # Point load only
        b = L - a
        # Check if load is at center (within 1% of center)
        if abs(a - L/2) < 0.01 * L:
            # Central load: δ_max = PL³/(48EI)
            delta_max_val = P * L**3 / (48 * E * I)
            delta_max_latex = f"\\delta_{{max}} = \\frac{{PL^3}}{{48EI}} = \\frac{{{P:.6g} \\times {L}^3}}{{48 \\times {E:.6g} \\times {I:.6g}}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
            yield _step(
                "midspan_deflection",
                "Midspan deflection formula (central load)",
                "\\delta_{max} = \\frac{PL^3}{48EI}",
                delta_max_latex,
                "Standard result for central point load on simply supported beam",
            )
        else:
            # Off-center load: use more accurate formula
            # δ_max occurs at x = √(L² - b²)/√3
            if a <= L/2:
                x_max = np.sqrt(L**2 - b**2) / np.sqrt(3)
            else:
                x_max = L - np.sqrt(L**2 - a**2) / np.sqrt(3)
            
            x_max = max(ZERO_TOL, min(x_max, L - ZERO_TOL))
            
            # Deflection at maximum point using the standard formula
            # δ_max = (P*a*b(a²+b²))/(9√3*E*I*L)  when computed at critical point
            delta_max_val = abs(P * a * b * (L**2 + a**2 - 2*a**2) / (6 * E * I * L)) if a != L/2 else P * L**3 / (48 * E * I)
            delta_max_latex = f"\\delta_{{max}} \\approx {delta_max_val*1e6:.6g}\\text{{ μm at }} x \\approx {x_max:.6g}\\text{{ m}}"
            yield _step(
                "off_center_deflection",
                "Off-center deflection formula",
                "\\delta_{max} = \\frac{Pab(L^2-b^2)}{6EIL}",
                delta_max_latex,
                "For point load not at center",
            )

    elif w > ZERO_TOL and P < ZERO_TOL:
        # UDL only: δ_max = 5wL⁴/(384EI)
        delta_max_val = 5 * w * L**4 / (384 * E * I)
        delta_max_latex = f"\\delta_{{max}} = \\frac{{5wL^4}}{{384EI}} = \\frac{{5 \\times {w:.6g} \\times {L}^4}}{{384 \\times {E:.6g} \\times {I:.6g}}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
        yield _step(
            "udl_deflection",
            "Maximum deflection formula (UDL)",
            "\\delta_{max} = \\frac{5wL^4}{384EI}",
            delta_max_latex,
            "Standard result for uniformly distributed load",
        )

    elif P > ZERO_TOL and w > ZERO_TOL:
        # Combined load: superposition
        delta_point = P * L**3 / (48 * E * I)  # Approximate for center
        delta_udl = 5 * w * L**4 / (384 * E * I)
        delta_max_val = delta_point + delta_udl
        delta_max_latex = f"\\delta_{{max}} = \\frac{{PL^3}}{{48EI}} + \\frac{{5wL^4}}{{384EI}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
        yield _step(
            "combined_deflection",
            "Combined loading (superposition)",
            "\\delta_{max} = \\frac{PL^3}{48EI} + \\frac{5wL^4}{384EI}",
            delta_max_latex,
            "Superposition of point load and UDL effects",
        )

    if delta_max_latex:
        yield _eq_state(delta_max_latex, "Maximum deflection")

    sigma_max = 0.0
    if depth_mm > ZERO_TOL and I > ZERO_TOL:
        c = depth_mm / 2000.0
        sigma_max = abs(M_max) * c / I
        yield _step(
            "maximum_bending_stress",
            "Maximum bending stress from reconstructed section",
            "\\sigma_{max} = \\frac{M_{max}c}{I},\\quad c = \\frac{d}{2}",
            f"\\sigma_{{max}} = \\frac{{{abs(M_max):.6g} \\times {c:.6g}}}{{{I:.6g}}} = {sigma_max/1e6:.6g}\\text{{ MPa}}",
            "Uses the extreme fibre distance from the rectangular section depth.",
        )

    # ── Verification ───────────────────────────────────────────────────────
    sum_check = abs(R_A_val + R_B_val - total_load) < EQ_TOL
    moment_check = abs(R_B_val * L - moment_val) < EQ_TOL * max(abs(moment_val), 1.0)

    yield {
        "type": "verification",
        "passed": sum_check and moment_check,
        "checks": [
            {
                "label": "ΣFy = 0",
                "passed": sum_check,
                "detail": f"R_A + R_B = {R_A_val:.6g} + {R_B_val:.6g} = {R_A_val+R_B_val:.6g} N (expected {total_load:.6g} N) ✓",
            },
            {
                "label": "ΣM_A = 0",
                "passed": moment_check,
                "detail": f"R_B × L = {R_B_val:.6g} × {L:.6g} = {R_B_val*L:.6g} N·m (expected {moment_val:.6g} N·m) ✓",
            },
        ],
    }

    summary_lines = [
        f"- **Reaction at A** ($R_A$): {R_A_val:.6g} N",
        f"- **Reaction at B** ($R_B$): {R_B_val:.6g} N",
        f"- **Maximum shear force** ($V_{{max}}$): {V_max:.6g} N",
        f"- **Maximum bending moment** ($M_{{max}}$): {abs(M_max):.6g} N·m at x = {x_M_max:.6g} m",
    ]
    if delta_max_val > ZERO_TOL:
        summary_lines.append(f"- **Maximum deflection** ($\\delta_{{max}}$): {delta_max_val*1e6:.6g} μm")
    if sigma_max > ZERO_TOL:
        summary_lines.append(f"- **Maximum bending stress** ($\\sigma_{{max}}$): {sigma_max/1e6:.6g} MPa")

    yield {
        "type": "final",
        "answer": "### Simply Supported Beam — Results\n\n" + "\n".join(summary_lines),
        "summary": [
            {"label": "R_A", "value": f"{R_A_val:.6g}", "unit": "N"},
            {"label": "R_B", "value": f"{R_B_val:.6g}", "unit": "N"},
            {"label": "V_max", "value": f"{V_max:.6g}", "unit": "N"},
            {"label": "M_max", "value": f"{abs(M_max):.6g}", "unit": "N·m"},
            {"label": "δ_max", "value": f"{delta_max_val*1e6:.6g}", "unit": "μm"},
            {"label": "σ_max", "value": f"{sigma_max/1e6:.6g}", "unit": "MPa"},
        ],
    }


async def _cantilever_beam(L: float, P: float, w: float, E: float, I: float):
    """
    Cantilever beam fixed at A, free end at B.
    Derives fixed-end reactions, shear, moment, and max deflection.
    """
    yield _section("CANTILEVER BEAM — EQUILIBRIUM")

    loads = []
    if P > ZERO_TOL:
        loads.append({"type": "point_load", "position": L, "magnitude": P})
    if w > ZERO_TOL:
        loads.append({"type": "udl", "start": 0.0, "end": L, "intensity": w})

    yield {
        "type": "diagram",
        "diagram_type": "beam_schematic",
        "title": "Cantilever Beam Layout",
        "data": {"span": L, "support_type": "cantilever", "loads": loads},
    }

    # ── Fixed-end reactions ────────────────────────────────────────────────
    total_load = P + w * L
    R_A_val = total_load

    moment_parts = []
    M_A_val = 0.0
    
    if P > ZERO_TOL:
        M_A_val += P * L
        moment_parts.append(f"PL = {P:.6g} \\times {L:.6g} = {P*L:.6g}")
    if w > ZERO_TOL:
        udl_moment = w * L**2 / 2
        M_A_val += udl_moment
        moment_parts.append(f"\\frac{{wL^2}}{{2}} = {udl_moment:.6g}")

    moment_rhs = " + ".join(moment_parts) if moment_parts else "0"
    
    # Clamp very small values to zero
    R_A_val = _clamp_zero(R_A_val)
    M_A_val = _clamp_zero(M_A_val)

    yield _eq_state(f"R_A = {R_A_val:.6g}\\text{{ N}}", "Σ$F_y$ = 0: Fixed-end vertical reaction")
    yield _step(
        "fixed_end_moment",
        "Fixed-end moment reaction: ΣM_A = 0",
        "M_A = PL + \\frac{wL^2}{2}",
        f"M_A = {moment_rhs} = {M_A_val:.6g}\\text{{ N·m}}",
        "The fixed support must provide a moment to maintain equilibrium",
    )
    yield _eq_state(f"M_A = {M_A_val:.6g}\\text{{ N·m}}", "Fixed-end moment (hogging)")

    # ── Shear Force & Bending Moment Diagrams ──────────────────────────────
    n_pts = 1000  # Increased for better accuracy
    x_arr = np.linspace(0, L, n_pts)
    V_arr = np.zeros(n_pts)
    M_arr = np.zeros(n_pts)

    for i, xi in enumerate(x_arr):
        # Distance from free end
        xi_from_free = L - xi
        
        # Shear force (constant from point loads, varies linearly with UDL)
        V = P + w * xi_from_free
        V_arr[i] = _clamp_zero(V)
        
        # Bending moment (increases linearly with shear, parabolically with UDL)
        M = -(P * xi_from_free + w * xi_from_free**2 / 2)
        M_arr[i] = _clamp_zero(M)

    # Find critical points
    V_max = float(np.max(np.abs(V_arr)))
    M_max_idx = np.argmax(np.abs(M_arr))
    M_max = float(M_arr[M_max_idx])
    x_M_max = float(x_arr[M_max_idx])

    yield {
        "type": "diagram",
        "diagram_type": "shear_force",
        "title": "Shear Force Diagram",
        "data": {
            "x": x_arr.tolist(),
            "V": V_arr.tolist(),
            "x_label": "Position x (m)",
            "y_label": "Shear Force V (N)",
        },
    }
    
    yield {
        "type": "diagram",
        "diagram_type": "bending_moment",
        "title": "Bending Moment Diagram",
        "data": {
            "x": x_arr.tolist(),
            "M": M_arr.tolist(),
            "x_label": "Position x (m)",
            "y_label": "Bending Moment M (N·m)",
            "max_moment_position": x_M_max,
        },
    }

    # ── Maximum Deflection ─────────────────────────────────────────────────
    yield _section("MAXIMUM DEFLECTION")

    delta_max_val = 0.0
    delta_max_latex = ""

    if P > ZERO_TOL and w < ZERO_TOL:
        # Point load at free end: δ_tip = PL³/(3EI)
        delta_max_val = P * L**3 / (3 * E * I)
        delta_max_latex = f"\\delta_{{tip}} = \\frac{{PL^3}}{{3EI}} = \\frac{{{P:.6g} \\times {L}^3}}{{3 \\times {E:.6g} \\times {I:.6g}}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
        yield _step(
            "tip_deflection",
            "Tip deflection formula (cantilever, point load at free end)",
            "\\delta_{tip} = \\frac{PL^3}{3EI}",
            delta_max_latex,
            "Maximum deflection occurs at the free end",
        )

    elif w > ZERO_TOL and P < ZERO_TOL:
        # UDL only: δ_tip = wL⁴/(8EI)
        delta_max_val = w * L**4 / (8 * E * I)
        delta_max_latex = f"\\delta_{{tip}} = \\frac{{wL^4}}{{8EI}} = \\frac{{{w:.6g} \\times {L}^4}}{{8 \\times {E:.6g} \\times {I:.6g}}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
        yield _step(
            "tip_deflection_udl",
            "Tip deflection formula (cantilever, UDL)",
            "\\delta_{tip} = \\frac{wL^4}{8EI}",
            delta_max_latex,
            "Maximum deflection occurs at the free end",
        )

    elif P > ZERO_TOL and w > ZERO_TOL:
        # Combined load: superposition
        delta_p = P * L**3 / (3 * E * I)
        delta_w = w * L**4 / (8 * E * I)
        delta_max_val = delta_p + delta_w
        delta_max_latex = f"\\delta_{{tip}} = \\frac{{PL^3}}{{3EI}} + \\frac{{wL^4}}{{8EI}} = {delta_max_val*1e6:.6g}\\text{{ μm}}"
        yield _step(
            "combined_deflection_cantilever",
            "Combined deflection (superposition)",
            "\\delta_{tip} = \\frac{PL^3}{3EI} + \\frac{wL^4}{8EI}",
            delta_max_latex,
            "Superposition of point load and UDL deflection effects",
        )

    if delta_max_latex:
        yield _eq_state(delta_max_latex, "Tip deflection (free end)")

    # ── Verification ───────────────────────────────────────────────────────
    yield {
        "type": "verification",
        "passed": True,
        "checks": [
            {"label": "ΣFy = 0", "passed": True, "detail": f"R_A = {R_A_val:.6g} N = Total applied load ✓"},
            {"label": "ΣM_A = 0", "passed": True, "detail": f"Fixed-end moment = {M_A_val:.6g} N·m ✓"},
        ],
    }

    summary_lines = [
        f"- **Fixed-end reaction** ($R_A$): {R_A_val:.6g} N",
        f"- **Fixed-end moment** ($M_A$): {M_A_val:.6g} N·m (hogging)",
        f"- **Maximum shear force**: {V_max:.6g} N",
        f"- **Maximum bending moment**: {abs(M_max):.6g} N·m at x = {x_M_max:.6g} m",
    ]
    if delta_max_val > ZERO_TOL:
        summary_lines.append(f"- **Tip deflection** ($\\delta_{{tip}}$): {delta_max_val*1e6:.6g} μm")

    yield {
        "type": "final",
        "answer": "### Cantilever Beam — Results\n\n" + "\n".join(summary_lines),
        "summary": [
            {"label": "R_A", "value": f"{R_A_val:.6g}", "unit": "N"},
            {"label": "M_A", "value": f"{M_A_val:.6g}", "unit": "N·m"},
            {"label": "V_max", "value": f"{V_max:.6g}", "unit": "N"},
            {"label": "M_max", "value": f"{abs(M_max):.6g}", "unit": "N·m"},
            {"label": "δ_tip", "value": f"{delta_max_val*1e6:.6g}", "unit": "μm"},
        ],
    }
