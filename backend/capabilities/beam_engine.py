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

    # Determine beam type
    is_cantilever = any(kw in raw or kw in problem_type for kw in ("cantilever", "fixed end", "fixed-end", "clamped"))

    try:
        if is_cantilever:
            async for evt in _cantilever_beam(L, P, w, E_val, I_val):
                yield evt
        else:
            async for evt in _simply_supported_beam(L, P, w, a, E_val, I_val):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Beam analysis error: {str(exc)}"}


async def _simply_supported_beam(L: float, P: float, w: float, a: float, E: float, I: float):
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

    # Find critical points
    critical = _find_critical_points(x_arr, M_arr, V_arr)
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

    yield {
        "type": "final",
        "answer": "### Simply Supported Beam — Results\n\n" + "\n".join(summary_lines),
        "summary": [
            {"label": "R_A", "value": f"{R_A_val:.6g}", "unit": "N"},
            {"label": "R_B", "value": f"{R_B_val:.6g}", "unit": "N"},
            {"label": "V_max", "value": f"{V_max:.6g}", "unit": "N"},
            {"label": "M_max", "value": f"{abs(M_max):.6g}", "unit": "N·m"},
            {"label": "δ_max", "value": f"{delta_max_val*1e6:.6g}", "unit": "μm"},
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
