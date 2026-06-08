"""Advanced structural mechanics solvers.

Provides focused deterministic handlers for Euler column buckling, circular
shaft torsion, and thin-walled pressure-vessel membrane stresses.
"""
from __future__ import annotations

import math
from typing import Any


def _section(title: str) -> dict:
    return {"type": "section", "title": title}


def _eq_state(latex_str: str, label: str = "") -> dict:
    return {"type": "equation_state", "latex": latex_str, "label": label}


def _step(operation: str, op_label: str, from_latex: str, to_latex: str, note: str = "") -> dict:
    return {
        "type": "derivation_step",
        "operation": operation,
        "operation_label": op_label,
        "from_latex": from_latex,
        "to_latex": to_latex,
        "note": note,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _load_label(value: float) -> str:
    if abs(value) >= 1e6:
        return f"{value / 1e6:.6g} MN"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.6g} kN"
    return f"{value:.6g} N"


def _stress_label(value: float) -> str:
    if abs(value) >= 1e6:
        return f"{value / 1e6:.6g} MPa"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.6g} kPa"
    return f"{value:.6g} Pa"


def can_solve(problem) -> float:
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    return 1.0 if problem_type in {"euler_column_buckling", "shaft_torsion", "thin_pressure_vessel"} else 0.0


async def solve_advanced_structural(data: dict):
    problem_type = str(data.get("problem_type") or data.get("canonical_problem_type") or "").lower()
    params = data.get("parameters", {}) or {}
    if problem_type == "euler_column_buckling":
        async for event in _solve_euler_column(params):
            yield event
    elif problem_type == "shaft_torsion":
        async for event in _solve_shaft_torsion(params):
            yield event
    elif problem_type == "thin_pressure_vessel":
        async for event in _solve_pressure_vessel(params):
            yield event
    else:
        yield {"type": "error", "message": "Unsupported advanced structural problem type."}


async def _solve_euler_column(params: dict):
    L = _safe_float(params.get("L", params.get("length")))
    E = _safe_float(params.get("E", params.get("youngs_modulus")))
    I = _safe_float(params.get("I", params.get("second_moment")))
    K = _safe_float(params.get("K"), 1.0)

    if min(L, E, I, K) <= 0.0:
        yield {"type": "error", "message": "Euler column buckling requires positive L, E, I, and effective length factor K."}
        return

    Le = K * L
    Pcr = math.pi**2 * E * I / Le**2

    yield _section("EULER COLUMN BUCKLING")
    yield _eq_state(fr"L={L:.6g}\,\text{{m}},\quad E={E:.6g}\,\text{{Pa}},\quad I={I:.6g}\,\text{{m}}^4,\quad K={K:.6g}", "Given column data")
    yield _step(
        "effective_length",
        "Effective buckling length",
        r"L_e=K L",
        fr"L_e={K:.6g}({L:.6g})={Le:.6g}\,\text{{m}}",
        "K captures end restraint: pinned-pinned ≈ 1.0, fixed-fixed ≈ 0.5, fixed-free ≈ 2.0.",
    )
    yield _step(
        "euler_load",
        "Euler elastic critical load",
        r"P_{cr}=\frac{\pi^2 E I}{(K L)^2}",
        fr"P_{{cr}}=\frac{{\pi^2({E:.6g})({I:.6g})}}{{({Le:.6g})^2}}={Pcr:.6g}\,\text{{N}}",
        "Valid for slender elastic columns before yielding or inelastic buckling controls.",
    )
    yield {
        "type": "final",
        "answer": (
            "### Euler Column Buckling Result\n\n"
            f"- **Effective length:** $L_e = {Le:.6g}\\,\\text{{m}}$.\n"
            f"- **Euler critical load:** $P_{{cr}} = {_load_label(Pcr)}$.\n"
            "- **Engineering note:** check slenderness and yield stress before using Euler load as design capacity."
        ),
        "summary": [{"label": "P_cr", "value": f"{Pcr:.6g}", "unit": "N", "decimal": Pcr}],
    }


async def _solve_shaft_torsion(params: dict):
    T = _safe_float(params.get("T", params.get("torque")))
    L = _safe_float(params.get("L", params.get("length")))
    G = _safe_float(params.get("G", params.get("shear_modulus")))
    d = _safe_float(params.get("d", params.get("diameter")))
    d_inner = _safe_float(params.get("d_inner"), 0.0)

    if min(T, L, G, d) <= 0.0:
        yield {"type": "error", "message": "Shaft torsion requires positive torque T, length L, shear modulus G, and outer diameter d."}
        return
    if d_inner < 0.0 or d_inner >= d:
        yield {"type": "error", "message": "For a hollow shaft, inner diameter must be nonnegative and smaller than outer diameter."}
        return

    J = math.pi * (d**4 - d_inner**4) / 32.0
    c = d / 2.0
    tau_max = T * c / J
    theta = T * L / (G * J)
    section_label = "hollow circular" if d_inner > 0.0 else "solid circular"

    yield _section("CIRCULAR SHAFT TORSION")
    yield _eq_state(fr"T={T:.6g}\,\text{{N·m}},\quad L={L:.6g}\,\text{{m}},\quad G={G:.6g}\,\text{{Pa}},\quad d_o={d:.6g}\,\text{{m}}", "Given shaft data")
    yield _step(
        "polar_second_moment",
        "Polar second moment of area",
        r"J=\frac{\pi(d_o^4-d_i^4)}{32}",
        fr"J=\frac{{\pi({d:.6g}^4-{d_inner:.6g}^4)}}{{32}}={J:.6g}\,\text{{m}}^4",
        f"Using a {section_label} section.",
    )
    yield _step(
        "maximum_shear_stress",
        "Maximum torsional shear stress",
        r"\tau_{max}=\frac{T c}{J}",
        fr"\tau_{{max}}=\frac{{{T:.6g}({c:.6g})}}{{{J:.6g}}}={tau_max:.6g}\,\text{{Pa}}",
        "Maximum shear stress occurs at the outer surface.",
    )
    yield _step(
        "angle_of_twist",
        "Angle of twist",
        r"\theta=\frac{T L}{G J}",
        fr"\theta=\frac{{{T:.6g}({L:.6g})}}{{{G:.6g}({J:.6g})}}={theta:.6g}\,\text{{rad}}",
        "Small-angle elastic torsion formula for circular shafts.",
    )
    yield {
        "type": "final",
        "answer": (
            "### Circular Shaft Torsion Result\n\n"
            f"- **Polar second moment:** $J = {J:.6g}\\,\\text{{m}}^4$.\n"
            f"- **Maximum shear stress:** $\\tau_{{max}} = {_stress_label(tau_max)}$.\n"
            f"- **Angle of twist:** $\\theta = {theta:.6g}\\,\\text{{rad}} = {math.degrees(theta):.6g}^\\circ$."
        ),
        "summary": [
            {"label": "J", "value": f"{J:.6g}", "unit": "m^4", "decimal": J},
            {"label": "tau_max", "value": f"{tau_max:.6g}", "unit": "Pa", "decimal": tau_max},
            {"label": "theta", "value": f"{theta:.6g}", "unit": "rad", "decimal": theta},
        ],
    }


async def _solve_pressure_vessel(params: dict):
    p = _safe_float(params.get("p", params.get("pressure")))
    R = _safe_float(params.get("R", params.get("radius")))
    t = _safe_float(params.get("t_wall", params.get("t", params.get("thickness"))))

    if min(p, R, t) <= 0.0:
        yield {"type": "error", "message": "Thin pressure-vessel stress requires positive internal pressure p, radius R, and wall thickness t."}
        return

    hoop = p * R / t
    longitudinal = p * R / (2.0 * t)
    thin_ratio = R / t

    yield _section("THIN-WALLED PRESSURE VESSEL")
    yield _eq_state(fr"p={p:.6g}\,\text{{Pa}},\quad R={R:.6g}\,\text{{m}},\quad t={t:.6g}\,\text{{m}}", "Given vessel data")
    yield _step(
        "hoop_stress",
        "Circumferential hoop stress",
        r"\sigma_h=\frac{pR}{t}",
        fr"\sigma_h=\frac{{{p:.6g}({R:.6g})}}{{{t:.6g}}}={hoop:.6g}\,\text{{Pa}}",
        "Thin-walled closed cylinder membrane stress; hoop stress is the larger principal membrane stress.",
    )
    yield _step(
        "longitudinal_stress",
        "Longitudinal stress",
        r"\sigma_l=\frac{pR}{2t}",
        fr"\sigma_l=\frac{{{p:.6g}({R:.6g})}}{{2({t:.6g})}}={longitudinal:.6g}\,\text{{Pa}}",
        "Closed-end cylinder axial membrane stress.",
    )
    if thin_ratio < 10.0:
        yield {"type": "step", "content": f"Warning: R/t = {thin_ratio:.6g}; thin-wall membrane formulas are usually best when R/t ≥ 10."}
    yield {
        "type": "final",
        "answer": (
            "### Thin Pressure Vessel Result\n\n"
            f"- **Hoop stress:** $\\sigma_h = {_stress_label(hoop)}$.\n"
            f"- **Longitudinal stress:** $\\sigma_l = {_stress_label(longitudinal)}$.\n"
            f"- **Thinness ratio:** $R/t = {thin_ratio:.6g}$."
        ),
        "summary": [
            {"label": "sigma_hoop", "value": f"{hoop:.6g}", "unit": "Pa", "decimal": hoop},
            {"label": "sigma_longitudinal", "value": f"{longitudinal:.6g}", "unit": "Pa", "decimal": longitudinal},
            {"label": "R/t", "value": f"{thin_ratio:.6g}", "decimal": thin_ratio},
        ],
    }
