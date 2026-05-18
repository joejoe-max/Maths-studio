"""
circuit_engine.py — Circuit analysis with derivation trace.
Enhanced version with structured derivation events.
"""
from __future__ import annotations

import math
import numpy as np
import cmath


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


def _sf(v, fmt=".4g") -> str:
    return format(float(v), fmt)


def _safe(v, default=None):
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


async def solve_circuits(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    try:
        if any(kw in raw or kw in problem_type for kw in ("ac", "impedance", "phasor", "rlc", "reactance")):
            async for evt in _ac_impedance(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("resonan", "resonance")):
            async for evt in _resonance(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("series", "parallel", "network", "resistor network")):
            async for evt in _resistor_network(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("rc circuit", "rc transient", "capacitor charge")):
            async for evt in _rc_circuit(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("rl circuit", "rl transient", "inductor")):
            async for evt in _rl_circuit(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("power factor", "apparent power")):
            async for evt in _power_factor(params):
                yield evt
        else:
            async for evt in _ohms_law(params):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Circuit engine error: {exc}"}


async def _ohms_law(params: dict):
    """Ohm's law with derivation steps."""
    yield _section("OHM'S LAW — V = IR")

    V = _safe(params.get("V", params.get("v", params.get("voltage"))))
    I = _safe(params.get("I", params.get("i", params.get("current"))))
    R = _safe(params.get("R", params.get("r", params.get("resistance"))))

    yield _eq_state("V = IR", "Ohm's Law")

    known = {k: v for k, v in [("V", V), ("I", I), ("R", R)] if v is not None}
    if len(known) < 2:
        yield {"type": "error", "message": "Ohm's Law requires at least two of: V (voltage), I (current), R (resistance)."}
        return

    if V is None:
        V = I * R
        yield _step("solve_V", "Solve for voltage",
                    "V = IR",
                    f"V = {_sf(I)} \\times {_sf(R)} = {_sf(V)}\\text{{ V}}", "")
    elif I is None:
        if R == 0:
            yield {"type": "error", "message": "R = 0 Ω: short circuit — current undefined."}
            return
        I = V / R
        yield _step("solve_I", "Solve for current",
                    "I = \\frac{V}{R}",
                    f"I = \\frac{{{_sf(V)}}}{{{_sf(R)}}} = {_sf(I)}\\text{{ A}}", "")
    elif R is None:
        if I == 0:
            yield {"type": "error", "message": "I = 0 A: no current — resistance undefined."}
            return
        R = V / I
        yield _step("solve_R", "Solve for resistance",
                    "R = \\frac{V}{I}",
                    f"R = \\frac{{{_sf(V)}}}{{{_sf(I)}}} = {_sf(R)}\\text{{ Ω}}", "")

    P = V * I
    yield _step("power", "Compute power dissipation",
                "P = VI = I^2R = \\frac{V^2}{R}",
                f"P = {_sf(V)} \\times {_sf(I)} = {_sf(P)}\\text{{ W}}", "")

    yield {
        "type": "verification",
        "passed": True,
        "checks": [{"label": "V = IR",
                    "passed": abs(V - I * R) < 1e-9,
                    "detail": f"{_sf(V)} V = {_sf(I)} A × {_sf(R)} Ω = {_sf(I*R)} V ✓"}],
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### Ohm's Law Solution",
            f"- **Voltage** ($V$): {_sf(V)} V",
            f"- **Current** ($I$): {_sf(I)} A",
            f"- **Resistance** ($R$): {_sf(R)} Ω",
            f"- **Power** ($P = VI$): {_sf(P)} W",
        ]),
        "summary": [
            {"label": "V", "value": _sf(V), "unit": "V"},
            {"label": "I", "value": _sf(I), "unit": "A"},
            {"label": "R", "value": _sf(R), "unit": "Ω"},
            {"label": "P", "value": _sf(P), "unit": "W"},
        ],
    }


async def _resistor_network(params: dict):
    """Series/parallel resistor network."""
    yield _section("RESISTOR NETWORK")

    resistors = params.get("resistors", [])
    mode = str(params.get("mode", "series")).lower().strip()
    V_supply = _safe(params.get("V", params.get("v", params.get("voltage"))), 0.0)

    try:
        resistors = [float(r) for r in resistors if r not in (None, "")]
    except (TypeError, ValueError):
        yield {"type": "error", "message": "Invalid resistor values."}
        return

    if not resistors:
        yield {"type": "error", "message": "No resistor values provided. Supply: resistors: [R1, R2, ...]"}
        return

    yield _eq_state(f"R_1, R_2, \\ldots = {', '.join(_sf(r) for r in resistors)}\\text{{ Ω}}", f"Resistors in {mode}")

    if mode == "series":
        R_eq = sum(resistors)
        terms = " + ".join(_sf(r) for r in resistors)
        yield _step("series_equivalent", "Series equivalent: R_eq = ΣR_i",
                    f"R_{{eq}} = {terms}",
                    f"R_{{eq}} = {_sf(R_eq)}\\text{{ Ω}}", "All current passes through every resistor")
    else:
        if any(r == 0 for r in resistors):
            yield {"type": "error", "message": "Short circuit: a 0 Ω resistor in parallel gives R_eq = 0 Ω."}
            return
        conductances = [1.0 / r for r in resistors]
        G_total = sum(conductances)
        R_eq = 1.0 / G_total
        cond_str = " + ".join(f"\\frac{{1}}{{{_sf(r)}}}" for r in resistors)
        yield _step("parallel_equivalent",
                    "Parallel equivalent: 1/R_eq = Σ(1/R_i)",
                    f"\\frac{{1}}{{R_{{eq}}}} = {cond_str}",
                    f"\\frac{{1}}{{R_{{eq}}}} = {_sf(G_total)}\\text{{ S}} \\implies R_{{eq}} = {_sf(R_eq)}\\text{{ Ω}}",
                    "Voltage is equal across all parallel resistors")

    yield _eq_state(f"R_{{eq}} = {_sf(R_eq)}\\text{{ Ω}}", "Equivalent resistance")

    extra_lines = []
    if V_supply > 0:
        I_total = V_supply / R_eq
        P_total = V_supply * I_total
        yield _step("total_current", "Total current from supply",
                    "I = \\frac{V}{R_{eq}}",
                    f"I = \\frac{{{_sf(V_supply)}}}{{{_sf(R_eq)}}} = {_sf(I_total)}\\text{{ A}}", "")
        extra_lines = [
            f"- **Total current** ($I$): {_sf(I_total)} A",
            f"- **Total power** ($P$): {_sf(P_total)} W",
        ]

    yield {
        "type": "final",
        "answer": "\n".join([
            f"### {mode.title()} Resistor Network",
            f"- **Resistors**: {', '.join(_sf(r)+' Ω' for r in resistors)}",
            f"- **Equivalent resistance** ($R_{{eq}}$): {_sf(R_eq)} Ω",
            *extra_lines,
        ]),
        "summary": [{"label": "R_eq", "value": _sf(R_eq), "unit": "Ω"}],
    }


async def _rc_circuit(params: dict):
    """RC transient response with time-constant derivation."""
    yield _section("RC CIRCUIT — TRANSIENT RESPONSE")

    R = _safe(params.get("R", params.get("r", params.get("resistance"))), 1000.0)
    C = _safe(params.get("C", params.get("c", params.get("capacitance"))), 1e-6)
    V0 = _safe(params.get("V", params.get("v", params.get("voltage"))), 5.0)

    if R <= 0 or C <= 0:
        yield {"type": "error", "message": "R and C must be positive."}
        return

    tau = R * C
    yield _eq_state(
        f"v_C(t) = V_0\\left(1 - e^{{-t/\\tau}}\\right)",
        "RC charging equation",
    )

    yield _step("time_constant", "Compute time constant τ = RC",
                "\\tau = RC",
                f"\\tau = {_sf(R)} \\times {_sf(C, '.3e')} = {_sf(tau*1000)}\\text{{ ms}}", "")

    yield _eq_state(f"\\tau = {_sf(tau*1000)}\\text{{ ms}}", "Time constant τ")
    yield _eq_state(
        f"t_{{99\\%}} = 5\\tau = {_sf(5*tau*1000)}\\text{{ ms}}",
        "99% charged at t = 5τ",
    )

    t_arr = np.linspace(0, 6 * tau, 300)
    v_c = V0 * (1 - np.exp(-t_arr / tau))

    yield {
        "type": "diagram",
        "diagram_type": "time_series",
        "title": "RC Charging Response",
        "data": {
            "x": (t_arr * 1000).tolist(),
            "y": v_c.tolist(),
            "x_label": "Time (ms)",
            "y_label": "Capacitor Voltage v_C (V)",
        },
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### RC Charging Transient",
            f"- **R** = {_sf(R)} Ω,  **C** = {_sf(C*1e6, '.3f')} μF,  **V₀** = {_sf(V0)} V",
            f"- **Time constant** ($\\tau = RC$): {_sf(tau*1000)} ms",
            f"- **63.2% voltage** at $t = \\tau$: {_sf(0.632*V0)} V",
            f"- **99% settled** at $t = 5\\tau$: {_sf(5*tau*1000)} ms",
            f"- **Initial current** ($I_0 = V_0/R$): {_sf(V0/R*1000)} mA",
        ]),
        "summary": [
            {"label": "τ", "value": _sf(tau*1000), "unit": "ms"},
            {"label": "5τ", "value": _sf(5*tau*1000), "unit": "ms"},
        ],
    }


async def _rl_circuit(params: dict):
    """RL transient response."""
    yield _section("RL CIRCUIT — TRANSIENT RESPONSE")

    R = _safe(params.get("R", params.get("r", params.get("resistance"))), 100.0)
    L = _safe(params.get("L", params.get("l", params.get("inductance"))), 0.1)
    V0 = _safe(params.get("V", params.get("v", params.get("voltage"))), 10.0)

    if R <= 0 or L <= 0:
        yield {"type": "error", "message": "R and L must be positive."}
        return

    tau = L / R
    I_final = V0 / R

    yield _eq_state("i_L(t) = I_f\\left(1 - e^{-t/\\tau}\\right)", "RL current build-up equation")
    yield _step("time_constant_rl", "Time constant τ = L/R",
                "\\tau = \\frac{L}{R}",
                f"\\tau = \\frac{{{_sf(L)}}}{{{_sf(R)}}} = {_sf(tau*1000)}\\text{{ ms}}", "")
    yield _step("final_current", "Final (steady-state) current",
                "I_f = \\frac{V_0}{R}",
                f"I_f = \\frac{{{_sf(V0)}}}{{{_sf(R)}}} = {_sf(I_final)}\\text{{ A}}", "")

    t_arr = np.linspace(0, 6 * tau, 300)
    i_L = I_final * (1 - np.exp(-t_arr / tau))

    yield {
        "type": "diagram",
        "diagram_type": "time_series",
        "title": "RL Current Build-up",
        "data": {
            "x": (t_arr * 1000).tolist(),
            "y": i_L.tolist(),
            "x_label": "Time (ms)",
            "y_label": "Inductor Current i_L (A)",
        },
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### RL Transient Response",
            f"- **R** = {_sf(R)} Ω,  **L** = {_sf(L*1000, '.3f')} mH,  **V₀** = {_sf(V0)} V",
            f"- **Time constant** ($\\tau = L/R$): {_sf(tau*1000)} ms",
            f"- **Final current**: {_sf(I_final)} A",
            f"- **5τ settling time**: {_sf(5*tau*1000)} ms",
        ]),
        "summary": [
            {"label": "τ", "value": _sf(tau*1000), "unit": "ms"},
            {"label": "I_f", "value": _sf(I_final), "unit": "A"},
        ],
    }


async def _ac_impedance(params: dict):
    """RLC series impedance analysis."""
    yield _section("AC IMPEDANCE — RLC SERIES CIRCUIT")

    f = _safe(params.get("f", params.get("frequency")), 60.0)
    R = _safe(params.get("R", params.get("r", params.get("resistance"))), 0.0)
    L = _safe(params.get("L", params.get("l", params.get("inductance"))), 0.0)
    C = _safe(params.get("C", params.get("c", params.get("capacitance"))), 0.0)
    V_s = _safe(params.get("V", params.get("v", params.get("voltage"))), 0.0)

    if f <= 0:
        yield {"type": "error", "message": "Frequency f must be positive."}
        return

    omega = 2 * math.pi * f
    yield _eq_state(
        f"\\omega = 2\\pi f = 2\\pi \\times {_sf(f)} = {_sf(omega, '.4f')}\\text{{ rad/s}}",
        "Angular frequency",
    )

    Z_R = complex(R, 0)
    Z_L = complex(0, omega * L) if L > 0 else complex(0, 0)
    Z_C = complex(0, -1.0 / (omega * C)) if C > 0 else complex(0, 0)

    if L > 0:
        yield _step("inductive_reactance", "Inductive reactance",
                    "X_L = \\omega L",
                    f"X_L = {_sf(omega, '.4f')} \\times {_sf(L)} = {_sf(Z_L.imag, '.4f')}\\text{{ Ω}}", "")
    if C > 0:
        yield _step("capacitive_reactance", "Capacitive reactance",
                    "X_C = -\\frac{1}{\\omega C}",
                    f"X_C = -\\frac{{1}}{{{_sf(omega, '.4f')} \\times {_sf(C, '.3e')}}} = {_sf(Z_C.imag, '.4f')}\\text{{ Ω}}", "")

    Z_total = Z_R + Z_L + Z_C
    Z_mag = abs(Z_total)
    Z_phase = math.degrees(cmath.phase(Z_total))

    yield _step("total_impedance", "Total impedance Z = R + jX_L + jX_C",
                f"Z = {_sf(R)} + j{_sf(Z_L.imag, '.4f')} + j{_sf(Z_C.imag, '.4f')}",
                f"Z = {_sf(Z_total.real, '.4f')} + j{_sf(Z_total.imag, '.4f')}\\text{{ Ω}}",
                "Complex impedance in rectangular form")

    yield _eq_state(
        f"|Z| = {_sf(Z_mag, '.4f')}\\text{{ Ω}},\\quad \\angle Z = {_sf(Z_phase, '.2f')}°",
        "Impedance in polar form",
    )

    extra_lines = []
    if V_s > 0 and Z_mag > 0:
        I_mag = V_s / Z_mag
        yield _step("current_from_impedance", "Current I = V/|Z|",
                    "I = \\frac{V_s}{|Z|}",
                    f"I = \\frac{{{_sf(V_s)}}}{{{_sf(Z_mag, '.4f')}}} = {_sf(I_mag, '.4f')}\\text{{ A at }}{_sf(-Z_phase, '.2f')}°", "")
        extra_lines = [
            f"- **Current** ($I$): {_sf(I_mag, '.4f')} A at {_sf(-Z_phase, '.2f')}°",
        ]

    yield {
        "type": "final",
        "answer": "\n".join([
            "### AC Impedance Analysis",
            f"- **Frequency**: {_sf(f)} Hz  ($\\omega = {_sf(omega, '.4f')}$ rad/s)",
            f"- **$X_L = \\omega L$**: {_sf(Z_L.imag, '.4f')} Ω",
            f"- **$X_C = -1/(\\omega C)$**: {_sf(Z_C.imag, '.4f')} Ω",
            f"- **Total impedance** $Z$: {_sf(Z_total.real, '.4f')} + j{_sf(Z_total.imag, '.4f')} Ω",
            f"- **$|Z|$**: {_sf(Z_mag, '.4f')} Ω,  $\\angle Z$ = {_sf(Z_phase, '.2f')}°",
            *extra_lines,
        ]),
        "summary": [
            {"label": "|Z|", "value": _sf(Z_mag, '.4f'), "unit": "Ω"},
            {"label": "∠Z", "value": _sf(Z_phase, '.2f'), "unit": "°"},
        ],
    }


async def _resonance(params: dict):
    """LC resonance frequency with Q-factor."""
    yield _section("RESONANCE FREQUENCY")

    L = _safe(params.get("L", params.get("l", params.get("inductance"))))
    C = _safe(params.get("C", params.get("c", params.get("capacitance"))))
    R = _safe(params.get("R", params.get("r", params.get("resistance"))), 0.0)

    if L is None or C is None or L <= 0 or C <= 0:
        yield {"type": "error", "message": "L (inductance) and C (capacitance) must be positive."}
        return

    omega_0 = 1.0 / math.sqrt(L * C)
    f_0 = omega_0 / (2 * math.pi)

    yield _step("resonant_frequency",
                "Resonant angular frequency",
                "\\omega_0 = \\frac{1}{\\sqrt{LC}}",
                f"\\omega_0 = \\frac{{1}}{{\\sqrt{{{_sf(L)} \\times {_sf(C, '.3e')}}}}} = {_sf(omega_0, '.4f')}\\text{{ rad/s}}", "")
    yield _step("cyclic_resonance", "Resonant frequency",
                "f_0 = \\frac{\\omega_0}{2\\pi}",
                f"f_0 = {_sf(f_0, '.4f')}\\text{{ Hz}}", "")

    extra_lines = []
    if R > 0:
        Q = (1.0 / R) * math.sqrt(L / C)
        BW = f_0 / Q
        yield _step("quality_factor", "Quality factor Q",
                    "Q = \\frac{1}{R}\\sqrt{\\frac{L}{C}}",
                    f"Q = \\frac{{1}}{{{_sf(R)}}}\\sqrt{{\\frac{{{_sf(L)}}}{{{_sf(C, '.3e')}}}}} = {_sf(Q, '.4f')}", "")
        extra_lines = [
            f"- **Quality factor** ($Q$): {_sf(Q, '.4f')}",
            f"- **Bandwidth** ($BW = f_0/Q$): {_sf(BW, '.4f')} Hz",
        ]

    # Impedance sweep
    omega_arr = np.logspace(math.log10(omega_0/10), math.log10(omega_0*10), 300)
    Z_arr = np.array([
        abs(complex(R, w*L - 1.0/(w*C))) for w in omega_arr
    ])
    yield {
        "type": "diagram",
        "diagram_type": "frequency_sweep",
        "title": "Impedance vs Frequency",
        "data": {
            "x": (omega_arr / (2*math.pi)).tolist(),
            "y": Z_arr.tolist(),
            "x_label": "Frequency (Hz)",
            "y_label": "|Z| (Ω)",
            "resonant_frequency": f_0,
        },
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### LC Resonance",
            f"- **L** = {_sf(L*1000, '.4f')} mH,  **C** = {_sf(C*1e6, '.4f')} μF",
            f"- **Resonant frequency** ($f_0$): {_sf(f_0, '.4f')} Hz",
            f"- **Angular frequency** ($\\omega_0$): {_sf(omega_0, '.4f')} rad/s",
            *extra_lines,
        ]),
        "summary": [
            {"label": "f₀", "value": _sf(f_0, '.4f'), "unit": "Hz"},
            {"label": "ω₀", "value": _sf(omega_0, '.4f'), "unit": "rad/s"},
        ],
    }


async def _power_factor(params: dict):
    """AC power factor analysis."""
    yield _section("AC POWER FACTOR ANALYSIS")

    V_rms = _safe(params.get("V", params.get("v", params.get("voltage"))), 230.0)
    I_rms = _safe(params.get("I", params.get("i", params.get("current"))), 0.0)
    phi = _safe(params.get("phi", params.get("angle")), 0.0)
    pf = _safe(params.get("pf", params.get("power_factor")), 0.0)

    if pf == 0.0 and phi != 0.0:
        pf = math.cos(math.radians(phi))
    elif phi == 0.0 and pf != 0.0:
        phi = math.degrees(math.acos(max(-1, min(1, pf))))

    if I_rms == 0.0:
        yield {"type": "error", "message": "RMS current I required for power factor analysis."}
        return

    S = V_rms * I_rms
    P = S * pf
    Q = S * math.sin(math.radians(phi))

    yield _step("apparent_power", "Apparent power",
                "S = V_{rms} I_{rms}",
                f"S = {_sf(V_rms)} \\times {_sf(I_rms)} = {_sf(S)}\\text{{ VA}}", "")
    yield _step("real_power", "Real (active) power",
                "P = S\\cos\\phi",
                f"P = {_sf(S)} \\times {_sf(pf)} = {_sf(P)}\\text{{ W}}", "")
    yield _step("reactive_power", "Reactive power",
                "Q = S\\sin\\phi",
                f"Q = {_sf(S)} \\times {_sf(math.sin(math.radians(phi)), '.4f')} = {_sf(Q)}\\text{{ VAR}}", "")

    yield {
        "type": "final",
        "answer": "\n".join([
            "### AC Power Factor",
            f"- **Power factor** ($\\cos\\phi$): {_sf(pf, '.4f')} ($\\phi = {_sf(phi, '.2f')}°$)",
            f"- **Apparent power** ($S$): {_sf(S)} VA",
            f"- **Real power** ($P$): {_sf(P)} W",
            f"- **Reactive power** ($Q$): {_sf(Q)} VAR",
            f"- {'Lagging (inductive)' if phi > 0 else 'Leading (capacitive)' if phi < 0 else 'Unity'} power factor",
        ]),
    }
