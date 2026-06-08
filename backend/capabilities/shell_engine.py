"""
shell_engine.py — Classical cylindrical shell buckling and stability notes.

Handles thin-walled cylindrical shells under uniform axial compression, with
Donnell/Koiter-style imperfection-sensitivity explanation and post-buckling
limit-point interpretation.
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


def _fmt(value: float, unit: str = "") -> str:
    suffix = f" {unit}" if unit else ""
    if value == 0:
        return f"0{suffix}"
    if abs(value) >= 1e6 or abs(value) < 1e-3:
        return f"{value:.6e}{suffix}"
    return f"{value:.6g}{suffix}"


def _load_label(value: float) -> str:
    if abs(value) >= 1e6:
        return f"{value / 1e6:.6g} MN"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.6g} kN"
    return f"{value:.6g} N"


def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    text = (getattr(problem, "raw_query", "") if not isinstance(problem, dict) else problem.get("raw_query", "")) or ""
    source = f"{domain} {problem_type} {text}".lower()
    if "shell_buckling" in source:
        return 1.0
    if "structural" in source and "shell" in source and "buckl" in source:
        return 0.95
    return 0.0


async def solve_shell_buckling(data: dict):
    params = data.get("parameters", {}) or {}
    raw = str(data.get("raw_query") or data.get("input_summary") or "")

    R = _safe_float(params.get("R", params.get("radius")))
    t = _safe_float(params.get("t_shell", params.get("thickness", params.get("t"))))
    L = _safe_float(params.get("L", params.get("length", params.get("l"))))
    E = _safe_float(params.get("E", params.get("youngs_modulus", params.get("elastic_modulus"))))
    nu = _safe_float(params.get("nu", params.get("poisson", params.get("poissons_ratio"))), 0.3)
    n = int(round(_safe_float(params.get("n"), 0))) or None

    delta = _safe_float(params.get("delta"), 0.0)
    delta_over_t = _safe_float(params.get("delta_over_t"), 0.0)
    if delta <= 0.0 and delta_over_t > 0.0 and t > 0.0:
        delta = delta_over_t * t
    elif delta > 0.0 and t > 0.0 and delta_over_t <= 0.0:
        delta_over_t = delta / t

    if min(R, t, L, E) <= 0.0:
        yield {
            "type": "error",
            "message": "Shell buckling requires positive radius R, thickness t, length L, and Young's modulus E in consistent SI units.",
        }
        return
    if not (-0.99 < nu < 0.5):
        yield {"type": "error", "message": "Poisson's ratio must be between -1 and 0.5 for an isotropic elastic shell."}
        return
    if t / R > 0.05:
        yield {
            "type": "step",
            "content": f"Warning: t/R = {t/R:.4g}; classical thin-shell formulas are most reliable for very thin shells.",
        }

    yield _section("CYLINDRICAL SHELL BUCKLING — CLASSICAL RESULT")
    yield _eq_state(
        f"R={R:.6g}\\,\\text{{m}},\\quad t={t:.6g}\\,\\text{{m}},\\quad L={L:.6g}\\,\\text{{m}},\\quad E={E:.6g}\\,\\text{{Pa}},\\quad \\nu={nu:.6g}",
        "Given shell properties",
    )

    denominator = math.sqrt(3.0 * (1.0 - nu**2))
    sigma_cr = E * t / (R * denominator)
    area = 2.0 * math.pi * R * t
    P_cr = sigma_cr * area
    axial_strain_cr = sigma_cr / E
    end_shortening_cr = axial_strain_cr * L
    rt_ratio = R / t

    yield _step(
        "classical_axial_stress",
        "Donnell classical axial buckling stress",
        r"\\sigma_{cr}=\\frac{E t}{R\\sqrt{3(1-\\nu^2)}}",
        f"\\sigma_{{cr}}=\\frac{{{E:.6g}({t:.6g})}}{{{R:.6g}\\sqrt{{3(1-{nu:.6g}^2)}}}}={sigma_cr:.6g}\\,\\text{{Pa}}",
        "For a long, thin, isotropic cylindrical shell under uniform axial compression.",
    )
    yield _step(
        "critical_load",
        "Convert stress to total axial load",
        r"P_{cr}=2\\pi R t\\,\\sigma_{cr}",
        f"P_{{cr}}=2\\pi({R:.6g})({t:.6g})({sigma_cr:.6g})={P_cr:.6g}\\,\\text{{N}}",
        "The loaded wall area is the shell circumference times thickness.",
    )
    yield _step(
        "critical_end_shortening",
        "Elastic end-shortening at classical bifurcation",
        r"\\Delta_{cr}=L\\frac{\\sigma_{cr}}{E}",
        f"\\Delta_{{cr}}={L:.6g}\\frac{{{sigma_cr:.6g}}}{{{E:.6g}}}={end_shortening_cr:.6g}\\,\\text{{m}}",
        "This marks the ideal linear bifurcation point, not a safe design load.",
    )

    knockdown_note = _imperfection_note(delta_over_t)
    yield _section("IMPERFECTION SENSITIVITY")
    if delta > 0.0:
        yield _eq_state(
            f"w_0=\\delta\\cos\\left(\\frac{{\\pi x}}{{L}}\\right)\\cos(n\\theta),\\quad \\delta={delta:.6g}\\,\\text{{m}}={delta_over_t:.6g}t" + (f",\\quad n={n}" if n else ""),
            "Initial geometric imperfection",
        )
    yield {
        "type": "step",
        "content": (
            "The imperfection removes the perfect-shell bifurcation. Lateral deflection is present from the start, "
            "the tangent stiffness softens earlier, and the maximum attainable load is usually well below the classical value. "
            f"{knockdown_note}"
        ),
    }
    yield {
        "type": "step",
        "content": (
            "Real cylindrical shells are highly imperfection-sensitive because nonlinear membrane/bending coupling lets small inward/outward waviness seed local dimples and ovalization. "
            "Therefore the classical Donnell load is an upper-bound reference and is often unconservative unless reduced by validated knockdown factors or nonlinear analysis with measured imperfections."
        ),
    }

    perfect_points = _perfect_curve_points(P_cr, end_shortening_cr)
    imperfect_points = _imperfect_curve_points(P_cr, end_shortening_cr, delta_over_t)
    yield {
        "type": "diagram",
        "diagram_type": "load_end_shortening",
        "title": "Qualitative Load vs End-Shortening Path",
        "data": {
            "perfect_shell": perfect_points,
            "imperfect_shell": imperfect_points,
            "units": {"end_shortening": "m", "load": "N"},
            "annotations": [
                {"label": "perfect bifurcation / limit", "x": end_shortening_cr, "y": P_cr},
                {"label": "imperfect limit point", "x": imperfect_points[3]["end_shortening"], "y": imperfect_points[3]["load"]},
            ],
        },
    }

    yield _section("POST-BUCKLING AND ARC-LENGTH METHOD")
    yield {
        "type": "step",
        "content": (
            "A simple load-control Newton solve cannot pass the limit point because the load reaches a local maximum and the equilibrium tangent becomes singular. "
            "A displacement-control solve can also fail on snap-back branches where both load and a chosen displacement decrease. "
            "An arc-length/Riks method constrains the combined load-displacement increment, so it can continue along unstable descending and snap-back equilibrium paths."
        ),
    }
    yield {
        "type": "step",
        "content": "At the limit point the shell undergoes snap-through/snap-buckling: a small load change can trigger a large jump to a distant post-buckled configuration with lower load capacity.",
    }

    answer = (
        "### Cylindrical Shell Buckling Result\n\n"
        f"- **Classical Donnell stress:** $\\sigma_{{cr}} = {sigma_cr/1e6:.6g}\\,\\text{{MPa}}$.\n"
        f"- **Classical axial buckling load:** $P_{{cr}} = {_load_label(P_cr)}$.\n"
        f"- **Critical end-shortening estimate:** $\\Delta_{{cr}} = {end_shortening_cr*1e3:.6g}\\,\\text{{mm}}$.\n"
        f"- **Thinness ratio:** $R/t = {rt_ratio:.6g}$.\n"
        "- **Design caution:** this is an ideal upper-bound value and is unconservative for real shells unless reduced; imperfections, residual stress, eccentricity, boundary nonuniformity, and material/geometric nonlinearities usually make shells buckle below it.\n"
        "- **Imperfection effect:** the $w_0$ shape makes the response smooth and nonlinear from the start, lowers the peak load, and promotes snap-through/post-buckling localization.\n"
        "- **Arc-length need:** it traces the descending/snap-back path after the limit point where ordinary load control becomes singular."
    )
    yield {
        "type": "final",
        "answer": answer,
        "summary": [
            {"label": "sigma_cr", "value": f"{sigma_cr:.6g}", "unit": "Pa", "decimal": sigma_cr},
            {"label": "P_cr", "value": f"{P_cr:.6g}", "unit": "N", "decimal": P_cr},
            {"label": "Delta_cr", "value": f"{end_shortening_cr:.6g}", "unit": "m", "decimal": end_shortening_cr},
            {"label": "R/t", "value": f"{rt_ratio:.6g}", "decimal": rt_ratio},
        ],
    }


def _imperfection_note(delta_over_t: float) -> str:
    if delta_over_t <= 0.0:
        return "No imperfection amplitude was provided, so only the qualitative imperfection sensitivity is reported."
    if delta_over_t < 0.1:
        return "The amplitude is small, but thin cylindrical shells can still show a noticeable knockdown."
    if delta_over_t <= 1.0:
        return "An amplitude on the order of the wall thickness fraction is significant; a pronounced knockdown from the classical load is expected."
    return "An amplitude exceeding the wall thickness is severe; classical linear buckling is not a reliable capacity estimate."


def _perfect_curve_points(P_cr: float, d_cr: float) -> list[dict[str, float]]:
    return [
        {"end_shortening": 0.0, "load": 0.0},
        {"end_shortening": 0.5 * d_cr, "load": 0.5 * P_cr},
        {"end_shortening": d_cr, "load": P_cr},
        {"end_shortening": 1.05 * d_cr, "load": 0.65 * P_cr},
        {"end_shortening": 1.25 * d_cr, "load": 0.45 * P_cr},
        {"end_shortening": 1.7 * d_cr, "load": 0.35 * P_cr},
    ]


def _imperfect_curve_points(P_cr: float, d_cr: float, delta_over_t: float) -> list[dict[str, float]]:
    severity = min(max(delta_over_t, 0.15), 1.5)
    peak_factor = max(0.35, 0.92 - 0.28 * severity)
    return [
        {"end_shortening": 0.0, "load": 0.0},
        {"end_shortening": 0.35 * d_cr, "load": 0.32 * P_cr},
        {"end_shortening": 0.7 * d_cr, "load": 0.62 * peak_factor * P_cr / max(peak_factor, 1e-9)},
        {"end_shortening": 0.9 * d_cr, "load": peak_factor * P_cr},
        {"end_shortening": 1.05 * d_cr, "load": 0.72 * peak_factor * P_cr},
        {"end_shortening": 1.45 * d_cr, "load": 0.55 * peak_factor * P_cr},
    ]
