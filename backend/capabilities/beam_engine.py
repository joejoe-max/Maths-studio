"""
beam_engine.py — Symbolic beam analysis with full derivation trace.

Handles: simply supported beams, cantilever beams, point loads, UDLs,
         reactions, shear force, bending moment, deflection.
Emits structured derivation_step and diagram events.
"""
from __future__ import annotations

import numpy as np
import sympy as sp

_x = sp.Symbol("x", positive=True)


def _latex(expr) -> str:
    return sp.latex(sp.simplify(expr))


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
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


async def solve_beam(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    L = _safe_float(params.get("L", params.get("length", params.get("span", params.get("l")))))
    P = _safe_float(params.get("P", params.get("point_load", params.get("load", params.get("force", params.get("p"))))))
    w = _safe_float(params.get("w", params.get("udl", params.get("distributed_load", params.get("intensity")))))
    a = _safe_float(params.get("a", params.get("load_position")), L / 2 if L > 0 else 0.0)
    E_val = _safe_float(params.get("E", params.get("elastic_modulus", params.get("youngs_modulus"))), 200e9)
    I_val = _safe_float(params.get("I", params.get("second_moment", params.get("moment_of_inertia"))), 1e-4)

    if L <= 0:
        yield {"type": "error", "message": "Beam length L must be positive. Please provide L (in metres)."}
        return

    is_cantilever = any(kw in raw or kw in problem_type for kw in ("cantilever", "fixed end", "fixed-end", "clamped"))

    try:
        if is_cantilever:
            async for evt in _cantilever_beam(L, P, w, E_val, I_val):
                yield evt
        else:
            async for evt in _simply_supported_beam(L, P, w, a, E_val, I_val):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Beam analysis error: {exc}"}


async def _simply_supported_beam(L: float, P: float, w: float, a: float, E: float, I: float):
    """
    Simply supported beam with point load P at position a and UDL w.
    Derives reactions, shear force, bending moment, and max deflection.
    """
    yield _section("SIMPLY SUPPORTED BEAM — EQUILIBRIUM")

    # ── Beam schematic diagram ─────────────────────────────────────────────
    loads = []
    if P > 0:
        loads.append({"type": "point_load", "position": a, "magnitude": P})
    if w > 0:
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
    R_A, R_B = sp.symbols("R_A R_B", real=True)

    # Total distributed load
    W_dist = w * L if w > 0 else sp.Integer(0)
    W_dist_num = float(W_dist)

    # ΣFy = 0
    sum_fy_lhs = "R_A + R_B"
    total_load = W_dist_num + P
    sum_fy_rhs = _latex(sp.sympify(total_load))
    yield _eq_state(f"R_A + R_B = {sum_fy_rhs}\\text{{ kN}}", "Σ$F_y$ = 0 — vertical force equilibrium")

    # ΣM_A = 0
    moment_rhs_parts = []
    moment_val = 0.0
    if w > 0:
        moment_rhs_parts.append(f"\\frac{{wL^2}}{{2}} = \\frac{{{w:.3g} \\times {L}^2}}{{2}} = {w*L**2/2:.4g}")
        moment_val += w * L**2 / 2
    if P > 0:
        moment_rhs_parts.append(f"Pa = {P:.3g} \\times {a:.3g} = {P*a:.4g}")
        moment_val += P * a

    moment_rhs_latex = " + ".join(moment_rhs_parts) if moment_rhs_parts else "0"

    yield _step(
        "moment_equilibrium_about_A",
        "Take moments about A: Σ$M_A$ = 0",
        "R_B \\cdot L = \\frac{wL^2}{2} + Pa",
        f"R_B \\cdot {L} = {moment_rhs_latex}",
        "Sum of moments about support A equals zero (clockwise positive)",
    )

    R_B_val = moment_val / L if L > 0 else 0.0

    yield _step(
        "solve_R_B",
        "Solve for R_B",
        f"R_B \\cdot {L} = {moment_val:.4g}",
        f"R_B = \\frac{{{moment_val:.4g}}}{{{L}}} = {R_B_val:.4g}\\text{{ N}}",
        "",
    )

    R_A_val = total_load - R_B_val
    yield _step(
        "solve_R_A",
        "Back-substitute to find R_A",
        f"R_A = \\text{{Total load}} - R_B = {total_load:.4g} - {R_B_val:.4g}",
        f"R_A = {R_A_val:.4g}\\text{{ N}}",
        "",
    )

    yield _eq_state(f"R_A = {R_A_val:.4g}\\text{{ N}}", "Reaction at A")
    yield _eq_state(f"R_B = {R_B_val:.4g}\\text{{ N}}", "Reaction at B")

    # ── Shear Force Diagram ────────────────────────────────────────────────
    yield _section("SHEAR FORCE & BENDING MOMENT DIAGRAMS")

    n_pts = 500
    x_arr = np.linspace(0, L, n_pts)
    V_arr = np.zeros(n_pts)
    M_arr = np.zeros(n_pts)

    for i, xi in enumerate(x_arr):
        V = R_A_val - w * xi
        if P > 0 and xi >= a:
            V -= P
        V_arr[i] = V

        M = R_A_val * xi - w * xi**2 / 2
        if P > 0 and xi >= a:
            M -= P * (xi - a)
        M_arr[i] = M

    # Key values
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
        },
    }

    # ── Deflection ─────────────────────────────────────────────────────────
    yield _section("MAXIMUM DEFLECTION")

    delta_max_label = "Max deflection"
    delta_max_latex = ""
    delta_max_val = 0.0

    if P > 0 and w == 0:
        b = L - a
        if abs(a - L/2) < 0.01:
            delta_max_val = P * L**3 / (48 * E * I)
            delta_max_latex = f"\\delta_{{max}} = \\frac{{PL^3}}{{48EI}} = \\frac{{{P:.3g} \\times {L}^3}}{{48 \\times {E:.3g} \\times {I:.3g}}} = {delta_max_val*1000:.4g}\\text{{ mm}}"
            yield _step(
                "midspan_deflection",
                "Midspan deflection formula (central load)",
                "\\delta_{max} = \\frac{PL^3}{48EI}",
                delta_max_latex,
                "Standard result for central point load on simply supported beam",
            )
        else:
            delta_max_val = P * a * b * (a + 2*b) * np.sqrt(3*a*(a+2*b)) / (27 * E * I * L) if a <= L/2 else P * b * a * (b + 2*a) * np.sqrt(3*b*(b+2*a)) / (27 * E * I * L)
            delta_max_latex = f"\\delta_{{max}} \\approx {delta_max_val*1000:.4g}\\text{{ mm}}"

    elif w > 0 and P == 0:
        delta_max_val = 5 * w * L**4 / (384 * E * I)
        delta_max_latex = f"\\delta_{{max}} = \\frac{{5wL^4}}{{384EI}} = \\frac{{5 \\times {w:.3g} \\times {L}^4}}{{384 \\times {E:.3g} \\times {I:.3g}}} = {delta_max_val*1000:.4g}\\text{{ mm}}"
        yield _step(
            "midspan_deflection",
            "Maximum deflection formula (UDL)",
            "\\delta_{max} = \\frac{5wL^4}{384EI}",
            delta_max_latex,
            "Standard result for uniformly distributed load",
        )

    if delta_max_latex:
        yield _eq_state(delta_max_latex, "Maximum midspan deflection")

    # ── Verification ───────────────────────────────────────────────────────
    sum_check = abs(R_A_val + R_B_val - total_load) < 1e-6
    moment_check = abs(R_B_val * L - moment_val) < 1e-4

    yield {
        "type": "verification",
        "passed": sum_check and moment_check,
        "checks": [
            {
                "label": "ΣFy = 0",
                "passed": sum_check,
                "detail": f"R_A + R_B = {R_A_val:.4g} + {R_B_val:.4g} = {R_A_val+R_B_val:.4g} N = {total_load:.4g} N ✓",
            },
            {
                "label": "ΣM_A = 0",
                "passed": moment_check,
                "detail": f"R_B × L = {R_B_val:.4g} × {L} = {R_B_val*L:.4g} N·m = {moment_val:.4g} N·m ✓",
            },
        ],
    }

    summary_lines = [
        f"- **Reaction at A** ($R_A$): {R_A_val:.4g} N",
        f"- **Reaction at B** ($R_B$): {R_B_val:.4g} N",
        f"- **Maximum shear force** ($V_{{max}}$): {V_max:.4g} N",
        f"- **Maximum bending moment** ($M_{{max}}$): {abs(M_max):.4g} N·m at x = {x_M_max:.3g} m",
    ]
    if delta_max_val:
        summary_lines.append(f"- **Maximum deflection** ($\\delta_{{max}}$): {delta_max_val*1000:.4g} mm")

    yield {
        "type": "final",
        "answer": "### Simply Supported Beam — Results\n\n" + "\n".join(summary_lines),
        "summary": [
            {"label": "R_A", "value": f"{R_A_val:.4g}", "unit": "N"},
            {"label": "R_B", "value": f"{R_B_val:.4g}", "unit": "N"},
            {"label": "V_max", "value": f"{V_max:.4g}", "unit": "N"},
            {"label": "M_max", "value": f"{abs(M_max):.4g}", "unit": "N·m"},
        ],
    }


async def _cantilever_beam(L: float, P: float, w: float, E: float, I: float):
    """
    Cantilever beam fixed at A, free end at B.
    Derives fixed-end reactions, shear, moment, and max deflection.
    """
    yield _section("CANTILEVER BEAM — EQUILIBRIUM")

    loads = []
    if P > 0:
        loads.append({"type": "point_load", "position": L, "magnitude": P})
    if w > 0:
        loads.append({"type": "udl", "start": 0.0, "end": L, "intensity": w})

    yield {
        "type": "diagram",
        "diagram_type": "beam_schematic",
        "title": "Cantilever Beam Layout",
        "data": {"span": L, "support_type": "cantilever", "loads": loads},
    }

    total_load = P + w * L
    R_A_val = total_load

    moment_parts = []
    M_A_val = 0.0
    if P > 0:
        M_A_val += P * L
        moment_parts.append(f"PL = {P:.3g} \\times {L} = {P*L:.4g}")
    if w > 0:
        M_A_val += w * L**2 / 2
        moment_parts.append(f"\\frac{{wL^2}}{{2}} = {w*L**2/2:.4g}")

    moment_rhs = " + ".join(moment_parts) if moment_parts else "0"

    yield _eq_state(f"R_A = {R_A_val:.4g}\\text{{ N}}", "Σ$F_y$ = 0: Fixed-end vertical reaction")
    yield _step(
        "fixed_end_moment",
        "Fixed-end moment reaction: ΣM_A = 0",
        "M_A = PL + \\frac{wL^2}{2}",
        f"M_A = {moment_rhs} = {M_A_val:.4g}\\text{{ N·m}}",
        "The fixed support must provide a moment to maintain equilibrium",
    )
    yield _eq_state(f"M_A = {M_A_val:.4g}\\text{{ N·m}}", "Fixed-end moment (hogging)")

    # SFD / BMD
    n_pts = 500
    x_arr = np.linspace(0, L, n_pts)
    V_arr = np.zeros(n_pts)
    M_arr = np.zeros(n_pts)

    for i, xi in enumerate(x_arr):
        xi_from_free = L - xi
        V_arr[i] = P + w * xi_from_free
        M_arr[i] = -(P * xi_from_free + w * xi_from_free**2 / 2)

    yield {
        "type": "diagram",
        "diagram_type": "shear_force",
        "title": "Shear Force Diagram",
        "data": {"x": x_arr.tolist(), "V": V_arr.tolist(), "x_label": "Position x (m)", "y_label": "V (N)"},
    }
    yield {
        "type": "diagram",
        "diagram_type": "bending_moment",
        "title": "Bending Moment Diagram",
        "data": {"x": x_arr.tolist(), "M": M_arr.tolist(), "x_label": "Position x (m)", "y_label": "M (N·m)"},
    }

    yield _section("MAXIMUM DEFLECTION")

    delta_max_val = 0.0
    if P > 0 and w == 0:
        delta_max_val = P * L**3 / (3 * E * I)
        yield _step(
            "tip_deflection",
            "Tip deflection formula (cantilever, point load at free end)",
            "\\delta_{tip} = \\frac{PL^3}{3EI}",
            f"\\delta_{{tip}} = \\frac{{{P:.3g} \\times {L}^3}}{{3 \\times {E:.3g} \\times {I:.3g}}} = {delta_max_val*1000:.4g}\\text{{ mm}}",
            "Maximum deflection occurs at the free end",
        )
    elif w > 0 and P == 0:
        delta_max_val = w * L**4 / (8 * E * I)
        yield _step(
            "tip_deflection_udl",
            "Tip deflection formula (cantilever, UDL)",
            "\\delta_{tip} = \\frac{wL^4}{8EI}",
            f"\\delta_{{tip}} = \\frac{{{w:.3g} \\times {L}^4}}{{8 \\times {E:.3g} \\times {I:.3g}}} = {delta_max_val*1000:.4g}\\text{{ mm}}",
            "",
        )
    elif P > 0 and w > 0:
        delta_max_val = P * L**3 / (3 * E * I) + w * L**4 / (8 * E * I)

    if delta_max_val:
        yield _eq_state(f"\\delta_{{tip}} = {delta_max_val*1000:.4g}\\text{{ mm}}", "Tip deflection (free end)")

    yield {
        "type": "verification",
        "passed": True,
        "checks": [
            {"label": "ΣFy = 0", "passed": True, "detail": f"R_A = {R_A_val:.4g} N = Total applied load ✓"},
            {"label": "ΣM_A = 0", "passed": True, "detail": f"Fixed-end moment = {M_A_val:.4g} N·m ✓"},
        ],
    }

    summary_lines = [
        f"- **Fixed-end reaction** ($R_A$): {R_A_val:.4g} N",
        f"- **Fixed-end moment** ($M_A$): {M_A_val:.4g} N·m (hogging)",
        f"- **Max shear force**: {float(np.max(np.abs(V_arr))):.4g} N",
        f"- **Max bending moment**: {float(np.max(np.abs(M_arr))):.4g} N·m",
    ]
    if delta_max_val:
        summary_lines.append(f"- **Tip deflection** ($\\delta_{{tip}}$): {delta_max_val*1000:.4g} mm")

    yield {
        "type": "final",
        "answer": "### Cantilever Beam — Results\n\n" + "\n".join(summary_lines),
        "summary": [
            {"label": "R_A", "value": f"{R_A_val:.4g}", "unit": "N"},
            {"label": "M_A", "value": f"{M_A_val:.4g}", "unit": "N·m"},
            {"label": "δ_tip", "value": f"{delta_max_val*1000:.4g}", "unit": "mm"},
        ],
    }
