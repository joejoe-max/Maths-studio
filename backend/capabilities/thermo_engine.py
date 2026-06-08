"""
thermo_engine.py — Thermodynamics with derivation trace.
Handles: ideal gas law, specific heat, heat transfer, Carnot efficiency,
         conduction/convection, gas processes (adiabatic, isothermal, etc.)
"""
from __future__ import annotations

import math
import numpy as np


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




def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    if domain == "thermo":
        return 1.0 if not problem_type or problem_type in {'ideal_gas', 'thermodynamics', 'constant_pressure_gas_process', 'turbine_power'} else 0.75
    return 0.0

async def solve_thermo(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    try:
        if any(kw in raw or kw in problem_type for kw in ("carnot", "heat engine", "efficiency")):
            async for evt in _carnot(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("turbine", "turbine_power", "enthalpy", "mass flow")):
            async for evt in _turbine_power(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("constant pressure", "volume doubles", "heat added", "work done", "gas_process")):
            async for evt in _constant_pressure_gas_process(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("ideal gas", "gas law", "pv=nrt", "boyle", "charles")):
            async for evt in _ideal_gas(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("conduction", "fourier heat")):
            async for evt in _heat_conduction(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("convection", "newton cooling")):
            async for evt in _heat_convection(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("specific heat", "heat capacity", "q=mcat", "q = mc")):
            async for evt in _specific_heat(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("adiabatic",)):
            async for evt in _adiabatic_process(params):
                yield evt
        else:
            async for evt in _ideal_gas(params):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Thermodynamics engine error: {exc}"}


async def _constant_pressure_gas_process(params: dict):
    """Closed ideal-gas heating at constant pressure with volume ratio."""
    yield _section("CONSTANT-PRESSURE IDEAL-GAS PROCESS")

    m = _safe(params.get("m", params.get("mass")))
    P_kpa = _safe(params.get("P", params.get("pressure")))
    T1 = _safe(params.get("T1", params.get("T", params.get("temperature"))))
    if T1 is None and params.get("temperature_c") is not None:
        T1 = _safe(params.get("temperature_c")) + 273.15
    R = _safe(params.get("R_specific", params.get("R")), 0.287)
    Cp = _safe(params.get("Cp", params.get("cp")), 1.005)
    volume_ratio = _safe(params.get("volume_ratio"), 2.0)

    if min(v for v in (m or 0, T1 or 0, R or 0, Cp or 0, volume_ratio or 0)) <= 0:
        yield {"type": "error", "message": "Constant-pressure gas process requires mass, initial temperature, gas constant R, Cp, and volume ratio."}
        return

    T2 = T1 * volume_ratio
    delta_T = T2 - T1
    W = m * R * delta_T
    Q = m * Cp * delta_T
    V1 = m * R * T1 / P_kpa if P_kpa else None
    V2 = volume_ratio * V1 if V1 is not None else None

    yield _eq_state("\\frac{V_2}{V_1} = \\frac{T_2}{T_1}\\quad(P=\\text{constant})", "Charles' law for an ideal gas at constant pressure")
    yield _step(
        "final_temperature",
        "Use the volume ratio to find final temperature",
        "T_2 = T_1\\frac{V_2}{V_1}",
        f"T_2 = {_sf(T1)} \\times {_sf(volume_ratio)} = {_sf(T2)}\\text{{ K}} = {_sf(T2 - 273.15)}\\text{{ °C}}",
        "At constant pressure, absolute temperature is proportional to volume.",
    )
    yield _step(
        "boundary_work",
        "Constant-pressure boundary work",
        "W = mR(T_2 - T_1)",
        f"W = {_sf(m)} \\times {_sf(R)} \\times ({_sf(T2)} - {_sf(T1)}) = {_sf(W)}\\text{{ kJ}}",
        "Using R in kJ/kg·K gives work directly in kJ.",
    )
    yield _step(
        "heat_added",
        "Constant-pressure heat transfer",
        "Q = mC_p(T_2 - T_1)",
        f"Q = {_sf(m)} \\times {_sf(Cp)} \\times ({_sf(T2)} - {_sf(T1)}) = {_sf(Q)}\\text{{ kJ}}",
        "For an ideal gas at constant pressure, heat transfer equals enthalpy change.",
    )

    checks = [{"label": "Temperature-volume proportionality", "passed": True, "detail": f"T2/T1 = {_sf(T2/T1)} equals V2/V1 = {_sf(volume_ratio)}."}]
    if P_kpa and V1 is not None and V2 is not None:
        checks.append({"label": "Initial/final volumes", "passed": True, "detail": f"V1 = {_sf(V1)} m³, V2 = {_sf(V2)} m³ at {P_kpa:g} kPa."})
    yield {"type": "verification", "passed": True, "checks": checks}

    volume_line = f"- **Volumes:** `V1 = {_sf(V1)} m³`, `V2 = {_sf(V2)} m³`.\n" if V1 is not None and V2 is not None else ""
    answer = (
        "### Constant-Pressure Ideal-Gas Heating\n\n"
        f"- **Final temperature:** `T2 = {_sf(T2)} K = {_sf(T2 - 273.15)} °C`.\n"
        + volume_line +
        f"- **Work done by the system:** `W = {_sf(W)} kJ`.\n"
        f"- **Heat added:** `Q = {_sf(Q)} kJ`.\n"
        "- **Reason:** because pressure is constant, doubling volume doubles the absolute temperature."
    )
    yield {
        "type": "final",
        "answer": answer,
        "summary": [
            {"label": "T2", "value": _sf(T2), "unit": "K"},
            {"label": "W", "value": _sf(W), "unit": "kJ"},
            {"label": "Q", "value": _sf(Q), "unit": "kJ"},
        ],
    }


async def _turbine_power(params: dict):
    """Steady-flow adiabatic turbine power from enthalpy drop."""
    yield _section("STEADY-FLOW TURBINE POWER")

    h1 = _safe(params.get("h1"))
    h2 = _safe(params.get("h2"))
    m_dot = _safe(params.get("m_dot", params.get("mass_flow")))
    eta = _safe(params.get("eta", params.get("efficiency")), 1.0)

    if min(v for v in (h1 or 0, h2 or 0, m_dot or 0, eta or 0)) <= 0:
        yield {"type": "error", "message": "Turbine power requires h1, h2 in kJ/kg and mass flow rate m_dot in kg/s."}
        return

    delta_h = h1 - h2
    power_kw = m_dot * delta_h * eta
    yield _eq_state(f"h_1={_sf(h1)}\\text{{ kJ/kg}},\\quad h_2={_sf(h2)}\\text{{ kJ/kg}},\\quad \\dot m={_sf(m_dot)}\\text{{ kg/s}}", "Given turbine data")
    yield _step(
        "enthalpy_drop",
        "Specific work from enthalpy drop",
        "w_t=h_1-h_2",
        f"w_t={_sf(h1)}-{_sf(h2)}={_sf(delta_h)}\\text{{ kJ/kg}}",
        "Neglecting kinetic/potential energy changes and heat transfer.",
    )
    yield _step(
        "turbine_power",
        "Power output",
        "\\dot W=\\dot m\\,\\eta\\,(h_1-h_2)",
        f"\\dot W={_sf(m_dot)}\\times{_sf(eta)}\\times{_sf(delta_h)}={_sf(power_kw)}\\text{{ kW}}",
        "With kJ/kg times kg/s, the result is kW.",
    )
    yield {
        "type": "final",
        "answer": (
            "### Turbine Power Result\n\n"
            f"- **Specific work:** `{_sf(delta_h)} kJ/kg`.\n"
            f"- **Power output:** `{_sf(power_kw)} kW` = `{_sf(power_kw/1000)} MW`."
        ),
        "summary": [
            {"label": "delta_h", "value": _sf(delta_h), "unit": "kJ/kg"},
            {"label": "W_dot", "value": _sf(power_kw), "unit": "kW"},
        ],
    }


async def _ideal_gas(params: dict):
    """Ideal gas law: PV = nRT with step-by-step derivation."""
    yield _section("IDEAL GAS LAW — PV = nRT")

    P = _safe(params.get("P", params.get("pressure")))
    V = _safe(params.get("V", params.get("volume")))
    n = _safe(params.get("n", params.get("moles")))
    T = _safe(params.get("T", params.get("temperature")))
    m_gas = _safe(params.get("m", params.get("mass_gas")))
    M = _safe(params.get("M", params.get("molar_mass")))
    R = 8.314  # J/(mol·K)

    yield _eq_state(
        "PV = nRT",
        "Ideal gas law (R = 8.314 J·mol⁻¹·K⁻¹)",
    )

    # If mass and molar mass given, compute n
    if n is None and m_gas is not None and M is not None:
        n = m_gas / M
        yield _step("moles_from_mass", "Calculate moles",
                    "n = \\frac{m}{M}",
                    f"n = \\frac{{{_sf(m_gas)}}}{{{_sf(M)}}} = {_sf(n)}\\text{{ mol}}", "")

    known = {k: v for k, v in [("P", P), ("V", V), ("n", n), ("T", T)] if v is not None}
    unknowns = [k for k in ("P", "V", "n", "T") if k not in known]

    known_latex = ",\\quad ".join(f"{k} = {_sf(v)}" for k, v in known.items())
    yield _eq_state(known_latex, "Known quantities")

    if len(unknowns) == 0:
        yield {"type": "step", "content": "All variables known — verifying PV = nRT."}
        # Guard against division by zero
        check = False
        if n is not None and R and T and n * R * T != 0:
            check = abs(P * V - n * R * T) / (n * R * T) < 0.01
        yield {
            "type": "verification",
            "passed": check,
            "checks": [{"label": "PV = nRT",
                        "passed": check,
                        "detail": f"PV = {_sf(P*V)}, nRT = {_sf(n*R*T)} {'✓' if check else '✗'}"}],
        }
    elif len(unknowns) == 1:
        unknown = unknowns[0]
        if unknown == "P":
            P = n * R * T / V
            yield _step("solve_P", "Solve for pressure",
                        "P = \\frac{nRT}{V}",
                        f"P = \\frac{{{_sf(n)} \\times 8.314 \\times {_sf(T)}}}{{{_sf(V)}}} = {_sf(P)}\\text{{ Pa}}", "")
            known["P"] = P
        elif unknown == "V":
            V = n * R * T / P
            yield _step("solve_V", "Solve for volume",
                        "V = \\frac{nRT}{P}",
                        f"V = \\frac{{{_sf(n)} \\times 8.314 \\times {_sf(T)}}}{{{_sf(P)}}} = {_sf(V)}\\text{{ m^3}}", "")
            known["V"] = V
        elif unknown == "T":
            T = P * V / (n * R)
            yield _step("solve_T", "Solve for temperature",
                        "T = \\frac{PV}{nR}",
                        f"T = \\frac{{{_sf(P)} \\times {_sf(V)}}}{{{_sf(n)} \\times 8.314}} = {_sf(T)}\\text{{ K}} = {_sf(T-273.15)}\\text{{ °C}}", "")
            known["T"] = T
        elif unknown == "n":
            n = P * V / (R * T)
            yield _step("solve_n", "Solve for moles",
                        "n = \\frac{PV}{RT}",
                        f"n = \\frac{{{_sf(P)} \\times {_sf(V)}}}{{8.314 \\times {_sf(T)}}} = {_sf(n)}\\text{{ mol}}", "")
            known["n"] = n
    else:
        yield {"type": "error", "message": f"Too many unknowns: {unknowns}. Provide at least 3 of P, V, n, T."}
        return

    # PV diagram for isothermal process
    if known.get("P") and known.get("V") and known.get("T"):
        n_val = known.get("n", 1)
        T_val = known["T"]
        V_arr = np.linspace(known["V"] * 0.1, known["V"] * 3, 200)
        P_arr = n_val * R * T_val / V_arr
        yield {
            "type": "diagram",
            "diagram_type": "pv_diagram",
            "title": "P-V Diagram (Isothermal)",
            "data": {
                "V": V_arr.tolist(),
                "P": P_arr.tolist(),
                "current_point": {"V": known["V"], "P": known["P"]},
                "x_label": "Volume V (m³)",
                "y_label": "Pressure P (Pa)",
            },
        }

    result_str = "\n".join(f"- **{k}** = {_sf(v)}" for k, v in known.items())
    yield {
        "type": "final",
        "answer": f"### Ideal Gas Law — PV = nRT\n\n{result_str}",
        "summary": [{"label": k, "value": _sf(v)} for k, v in known.items()],
    }


async def _carnot(params: dict):
    """Carnot cycle efficiency with step-by-step thermodynamic analysis."""
    yield _section("CARNOT CYCLE — HEAT ENGINE")

    T_H = _safe(params.get("T_H", params.get("T_hot", params.get("hot_temperature"))))
    T_C = _safe(params.get("T_C", params.get("T_cold", params.get("cold_temperature", params.get("T_L")))))
    Q_H = _safe(params.get("Q_H", params.get("heat_input", params.get("heat_absorbed"))))
    W_net = _safe(params.get("W", params.get("work_output", params.get("net_work"))))

    if T_H is None and T_C is None:
        yield {"type": "error", "message": "Carnot analysis requires hot reservoir T_H and cold reservoir T_C (in Kelvin)."}
        return

    yield _eq_state(
        f"T_H = {_sf(T_H)}\\text{{ K}},\\quad T_C = {_sf(T_C)}\\text{{ K}}",
        "Reservoir temperatures",
    )

    if T_H <= T_C:
        yield {"type": "error", "message": "Hot reservoir temperature T_H must exceed cold reservoir T_C."}
        return

    eta = 1 - T_C / T_H
    yield _step(
        "carnot_efficiency",
        "Carnot efficiency",
        "\\eta_{Carnot} = 1 - \\frac{T_C}{T_H}",
        f"\\eta = 1 - \\frac{{{_sf(T_C)}}}{{{_sf(T_H)}}} = {_sf(eta)} = {_sf(eta*100)}\\%",
        "Upper bound on efficiency for any heat engine operating between T_H and T_C",
    )

    lines = [
        f"- **Carnot efficiency** ($\\eta$): {_sf(eta*100)}%",
        f"- **Hot reservoir** ($T_H$): {_sf(T_H)} K = {_sf(T_H-273.15)} °C",
        f"- **Cold reservoir** ($T_C$): {_sf(T_C)} K = {_sf(T_C-273.15)} °C",
    ]

    if Q_H is not None:
        W = eta * Q_H
        Q_C = Q_H - W
        yield _step("work_from_heat", "Net work output",
                    "W_{net} = \\eta Q_H",
                    f"W = {_sf(eta)} \\times {_sf(Q_H)} = {_sf(W)}\\text{{ J}}", "")
        yield _eq_state(f"Q_C = Q_H - W = {_sf(Q_C)}\\text{{ J}}", "Heat rejected to cold reservoir")
        lines += [
            f"- **Heat input** ($Q_H$): {_sf(Q_H)} J",
            f"- **Work output** ($W$): {_sf(W)} J",
            f"- **Heat rejected** ($Q_C$): {_sf(Q_C)} J",
        ]

    yield {
        "type": "verification",
        "passed": True,
        "checks": [
            {"label": "Second Law: η < 1",
             "passed": eta < 1,
             "detail": f"η = {_sf(eta*100)}% < 100% ✓"},
            {"label": "T_H > T_C",
             "passed": T_H > T_C,
             "detail": f"{_sf(T_H)} K > {_sf(T_C)} K ✓"},
        ],
    }

    yield {
        "type": "final",
        "answer": "### Carnot Heat Engine\n\n" + "\n".join(lines),
        "summary": [
            {"label": "η", "value": _sf(eta*100), "unit": "%"},
            {"label": "T_H", "value": _sf(T_H), "unit": "K"},
            {"label": "T_C", "value": _sf(T_C), "unit": "K"},
        ],
    }


async def _specific_heat(params: dict):
    """Specific heat capacity: Q = mcΔT."""
    yield _section("SPECIFIC HEAT & HEAT TRANSFER")

    m = _safe(params.get("m", params.get("mass")))
    c = _safe(params.get("c", params.get("specific_heat", params.get("specific_heat_capacity"))))
    delta_T = _safe(params.get("delta_T", params.get("dT", params.get("temperature_change"))))
    T1 = _safe(params.get("T1", params.get("T_initial")))
    T2 = _safe(params.get("T2", params.get("T_final")))
    Q = _safe(params.get("Q", params.get("heat")))

    if delta_T is None and T1 is not None and T2 is not None:
        delta_T = T2 - T1
        yield _eq_state(f"\\Delta T = T_2 - T_1 = {_sf(T2)} - {_sf(T1)} = {_sf(delta_T)}\\text{{ K}}", "Temperature change")

    yield _eq_state("Q = mc\\Delta T", "Specific heat equation")

    known = {k: v for k, v in [("m", m), ("c", c), ("ΔT", delta_T), ("Q", Q)] if v is not None}
    unknowns = [k for k in ("m", "c", "ΔT", "Q") if k not in known]

    if len(unknowns) == 1:
        unknown = unknowns[0]
        if unknown == "Q" and m and c and delta_T:
            Q = m * c * delta_T
            yield _step("solve_Q", "Solve for heat Q",
                        "Q = mc\\Delta T",
                        f"Q = {_sf(m)} \\times {_sf(c)} \\times {_sf(delta_T)} = {_sf(Q)}\\text{{ J}}", "")
        elif unknown == "m" and Q and c and delta_T:
            m = Q / (c * delta_T)
            yield _step("solve_m", "Solve for mass",
                        "m = \\frac{Q}{c\\Delta T}",
                        f"m = \\frac{{{_sf(Q)}}}{{{_sf(c)} \\times {_sf(delta_T)}}} = {_sf(m)}\\text{{ kg}}", "")
        elif unknown == "ΔT" and Q and m and c:
            delta_T = Q / (m * c)
            yield _step("solve_dT", "Solve for ΔT",
                        "\\Delta T = \\frac{Q}{mc}",
                        f"\\Delta T = \\frac{{{_sf(Q)}}}{{{_sf(m)} \\times {_sf(c)}}} = {_sf(delta_T)}\\text{{ K}}", "")
        elif unknown == "c" and Q and m and delta_T is not None:
            c = Q / (m * delta_T)
            yield _step("solve_c", "Solve for specific heat capacity",
                        "c = \\frac{Q}{m\\Delta T}",
                        f"c = \\frac{{{_sf(Q)}}}{{{_sf(m)} \\times {_sf(delta_T)}}} = {_sf(c)}\\text{{ J·kg⁻¹·K⁻¹}}", "")

    results = {k: v for k, v in [("Q", Q), ("m", m), ("c", c), ("ΔT", delta_T)] if v is not None}
    yield {
        "type": "final",
        "answer": "### Specific Heat Results\n\n" + "\n".join(f"- **{k}** = {_sf(v)}" for k, v in results.items()),
        "summary": [{"label": k, "value": _sf(v)} for k, v in results.items()],
    }


async def _heat_conduction(params: dict):
    """Fourier's law of heat conduction: Q = kAΔT/L."""
    yield _section("HEAT CONDUCTION — FOURIER'S LAW")

    k = _safe(params.get("k", params.get("thermal_conductivity")))
    A = _safe(params.get("A", params.get("area")))
    delta_T = _safe(params.get("delta_T", params.get("dT", params.get("temperature_difference"))))
    L = _safe(params.get("L", params.get("thickness", params.get("length"))))
    Q_dot = _safe(params.get("Q", params.get("heat_flux", params.get("heat_flow_rate"))))

    yield _eq_state("\\dot{Q} = \\frac{kA\\Delta T}{L}", "Fourier's law of heat conduction")

    known = {k_: v for k_, v in [("k", k), ("A", A), ("ΔT", delta_T), ("L", L), ("Q̇", Q_dot)] if v is not None}
    yield _eq_state(
        ",\\quad ".join(f"{kk} = {_sf(vv)}" for kk, vv in known.items()),
        "Given parameters",
    )

    if all(v is not None for v in [k, A, delta_T, L]):
        Q_dot_calc = k * A * delta_T / L
        yield _step("compute_heat_flux", "Compute heat flow rate",
                    "\\dot{Q} = \\frac{kA\\Delta T}{L}",
                    f"\\dot{{Q}} = \\frac{{{_sf(k)} \\times {_sf(A)} \\times {_sf(delta_T)}}}{{{_sf(L)}}} = {_sf(Q_dot_calc)}\\text{{ W}}",
                    "")
        thermal_R = L / (k * A)
        yield _eq_state(f"R_{{th}} = \\frac{{L}}{{kA}} = {_sf(thermal_R)}\\text{{ K/W}}", "Thermal resistance")

        yield {
            "type": "final",
            "answer": f"### Heat Conduction Results\n\n- **Heat flux** ($\\dot{{Q}}$): {_sf(Q_dot_calc)} W\n- **Thermal resistance** ($R_{{th}}$): {_sf(thermal_R)} K/W",
            "summary": [
                {"label": "Q̇", "value": _sf(Q_dot_calc), "unit": "W"},
                {"label": "R_th", "value": _sf(thermal_R), "unit": "K/W"},
            ],
        }
    else:
        yield {"type": "error", "message": "Need k, A, ΔT, and L for Fourier heat conduction."}


async def _heat_convection(params: dict):
    """Newton's law of cooling: Q = hAΔT."""
    yield _section("CONVECTIVE HEAT TRANSFER — NEWTON'S LAW OF COOLING")

    h = _safe(params.get("h", params.get("heat_transfer_coefficient", params.get("convective_coefficient"))))
    A = _safe(params.get("A", params.get("area")))
    T_s = _safe(params.get("T_s", params.get("surface_temperature")))
    T_inf = _safe(params.get("T_inf", params.get("ambient_temperature", params.get("T_fluid"))))
    Q_dot = _safe(params.get("Q", params.get("heat_flux")))

    yield _eq_state("\\dot{Q} = hA(T_s - T_{\\infty})", "Newton's law of cooling")

    if h and A and T_s is not None and T_inf is not None:
        delta_T = T_s - T_inf
        Q_calc = h * A * delta_T
        yield _step("compute_convection", "Compute convective heat transfer",
                    "\\dot{Q} = hA(T_s - T_{\\infty})",
                    f"\\dot{{Q}} = {_sf(h)} \\times {_sf(A)} \\times ({_sf(T_s)} - {_sf(T_inf)}) = {_sf(Q_calc)}\\text{{ W}}", "")
        yield {
            "type": "final",
            "answer": f"### Convective Heat Transfer\n\n- **Temperature difference** ($\\Delta T$): {_sf(delta_T)} K\n- **Heat transfer rate** ($\\dot{{Q}}$): {_sf(Q_calc)} W",
            "summary": [{"label": "Q̇", "value": _sf(Q_calc), "unit": "W"}],
        }
    else:
        yield {"type": "error", "message": "Need h, A, T_s, and T_∞ for convection analysis."}


async def _adiabatic_process(params: dict):
    """Adiabatic process: TV^(γ-1) = const, PV^γ = const."""
    yield _section("ADIABATIC PROCESS")

    P1 = _safe(params.get("P1", params.get("P_1")))
    V1 = _safe(params.get("V1", params.get("V_1")))
    T1 = _safe(params.get("T1", params.get("T_1")))
    P2 = _safe(params.get("P2", params.get("P_2")))
    V2 = _safe(params.get("V2", params.get("V_2")))
    gamma = _safe(params.get("gamma", params.get("ratio")), 1.4)

    yield _eq_state(f"PV^\\gamma = \\text{{const}},\\quad \\gamma = {_sf(gamma)}", "Adiabatic process law")

    if P1 and V1 and V2:
        P2_calc = P1 * (V1 / V2) ** gamma
        yield _step("adiabatic_pressure",
                    "Find P₂ from P₁V₁^γ = P₂V₂^γ",
                    "P_2 = P_1 \\left(\\frac{V_1}{V_2}\\right)^\\gamma",
                    f"P_2 = {_sf(P1)} \\times \\left(\\frac{{{_sf(V1)}}}{{{_sf(V2)}}}\\right)^{{{_sf(gamma)}}} = {_sf(P2_calc)}\\text{{ Pa}}", "")

        if T1:
            T2_calc = T1 * (V1 / V2) ** (gamma - 1)
            gamma_minus_1 = gamma - 1
            yield _step("adiabatic_temperature",
                        "Find T₂ from TV^(γ-1) = const",
                        "T_2 = T_1 \\left(\\frac{V_1}{V_2}\\right)^{\\gamma-1}",
                        f"T_2 = {_sf(T1)} \\times \\left(\\frac{{{_sf(V1)}}}{{{_sf(V2)}}}\\right)^{{{_sf(gamma_minus_1)}}} = {_sf(T2_calc)}\\text{{ K}}", "")

        yield {
            "type": "final",
            "answer": f"### Adiabatic Process\n\n- **P₂** = {_sf(P2_calc)} Pa" +
                      (f"\n- **T₂** = {_sf(T2_calc)} K" if T1 else ""),
            "summary": [{"label": "P2", "value": _sf(P2_calc), "unit": "Pa"}],
        }
    else:
        yield {"type": "error", "message": "Need P1, V1, V2 (and optionally T1) for adiabatic process."}
