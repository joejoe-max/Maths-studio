const DOMAIN_PATTERNS = {
  algebra: /\bsolve\b.*=|simultaneous|system of equation|\b\d*[a-z]\s*[+\-]\s*\d*[a-z]|quadratic|polynomial|roots of|factori[sz]e|eigenvalue|matrix/i,
  calculus: /differentiat|integrat|derivative|integral|\bd\/dx\b|limit as|gradient|laplace transform|fourier|taylor series|maclaurin|ode\b|differential equation/i,
  structural: /\bbeam\b|\btruss\b|deflection|bending moment|shear force|simply.supported|cantilever|fixed.end|moment of inertia|udl|uniformly distributed|point load/i,
  mechanics: /projectile|velocity|acceleration|friction|momentum|kinetic energy|potential energy|\bspring\b|vibration|oscillation|torque|\brotation\b|statics|dynamics|kinematics/i,
  circuits: /circuit|resistor|capacitor|inductor|\bvoltage\b|\bcurrent\b|\bohm\b|kirchhoff|thevenin|norton|impedance|phasor|rc circuit|rl circuit|rlc|\bamps?\b/i,
  thermo: /temperature|heat transfer|entropy|carnot|rankine|thermodynamic|ideal gas|\bpressure\b.*\bvolume\b|isothermal|adiabatic|isobaric|isochoric|carnot engine/i,
  fluids: /fluid|pipe flow|bernoulli|reynolds number|viscosity|pressure drop|hydrostatic|buoyancy|continuity equation|navier/i,
  statistics: /\bmean\b|\bmedian\b|variance|standard deviation|regression|hypothesis test|confidence interval|probability|normal distribution/i,
};

const DOMAIN_METHODS = {
  algebra: [
    { id: 'elimination', label: 'Elimination Method', desc: 'Multiply equations to cancel a variable, then solve step by step' },
    { id: 'substitution', label: 'Substitution Method', desc: 'Isolate one variable and substitute into remaining equations' },
    { id: 'matrix', label: 'Matrix Method (Gaussian)', desc: 'Form augmented matrix and row-reduce to reduced echelon form' },
    { id: 'cramers_rule', label: "Cramer's Rule", desc: 'Solve using determinants of the coefficient matrix' },
  ],
  calculus: [
    { id: 'symbolic', label: 'Symbolic (Exact)', desc: 'Compute exact closed-form result using SymPy symbolic engine' },
    { id: 'integration_by_parts', label: 'Integration by Parts', desc: '∫u·dv = u·v − ∫v·du — for products of functions' },
    { id: 'substitution_u', label: 'u-Substitution', desc: 'Change of variable to simplify the integrand' },
    { id: 'partial_fractions', label: 'Partial Fractions', desc: 'Decompose rational functions before integrating' },
  ],
  structural: [
    { id: 'equilibrium', label: 'Equilibrium Method', desc: 'Apply ΣF = 0 and ΣM = 0 to find reactions and internal forces' },
    { id: 'macaulay', label: "Macaulay's Method", desc: 'Singularity functions for beams with multiple discontinuous loads' },
    { id: 'direct_integration', label: 'Direct Integration', desc: 'Integrate EI·y″ = M(x) twice to get slope and deflection' },
    { id: 'moment_area', label: 'Moment-Area Theorems', desc: 'Use area of M/EI diagram to compute slopes and deflections' },
  ],
  mechanics: [
    { id: 'newton', label: "Newton's Laws (F=ma)", desc: 'Apply free-body diagram and second law to each body' },
    { id: 'work_energy', label: 'Work-Energy Theorem', desc: 'W_net = ΔKE — relates net work to change in kinetic energy' },
    { id: 'impulse_momentum', label: 'Impulse-Momentum', desc: 'J = Δp — integrate force over time to find momentum change' },
    { id: 'lagrangian', label: 'Lagrangian Method', desc: 'Energy-based formulation via generalized coordinates' },
  ],
  circuits: [
    { id: 'nodal', label: 'Nodal Analysis (KCL)', desc: 'Apply Kirchhoff\'s Current Law at each independent node' },
    { id: 'mesh', label: 'Mesh Analysis (KVL)', desc: 'Apply Kirchhoff\'s Voltage Law around each independent loop' },
    { id: 'thevenin', label: 'Thévenin Equivalent', desc: 'Reduce network to V_th in series with R_th' },
    { id: 'superposition', label: 'Superposition Theorem', desc: 'Analyse one independent source at a time, then superpose' },
  ],
  thermo: [
    { id: 'first_law', label: 'First Law (Energy Balance)', desc: 'Q − W = ΔU — apply to closed or open system' },
    { id: 'second_law', label: 'Second Law (Entropy)', desc: 'Analyse irreversibilities and entropy generation' },
    { id: 'ideal_gas', label: 'Ideal Gas Relations', desc: 'Apply PV = nRT with process constraints' },
    { id: 'carnot_cycle', label: 'Carnot / Cycle Analysis', desc: 'Compute efficiency and heat exchange for thermodynamic cycles' },
  ],
  fluids: [
    { id: 'bernoulli', label: 'Bernoulli Equation', desc: 'P + ½ρv² + ρgh = const along a streamline' },
    { id: 'continuity', label: 'Continuity + Momentum', desc: 'Mass conservation combined with momentum equation' },
    { id: 'darcy', label: 'Darcy-Weisbach (Pipe)', desc: 'Head loss h_f = f·(L/D)·(v²/2g) for pipe flow' },
  ],
  statistics: [
    { id: 'descriptive', label: 'Descriptive Statistics', desc: 'Compute mean, variance, standard deviation, and quartiles' },
    { id: 'regression', label: 'Linear Regression (OLS)', desc: 'Fit y = mx + b using least-squares minimisation' },
    { id: 't_test', label: 't-Test (Hypothesis)', desc: 'Test population mean using Student\'s t-distribution' },
  ],
};

const POPUP_DOMAINS = new Set(['algebra', 'calculus', 'structural', 'mechanics', 'circuits', 'thermo', 'fluids']);

export function detectDomain(text) {
  for (const [domain, pattern] of Object.entries(DOMAIN_PATTERNS)) {
    if (pattern.test(text)) return domain;
  }
  return null;
}

export function getMethodsForDomain(domain) {
  return DOMAIN_METHODS[domain] || [];
}

export function shouldShowMethodPopup(domain) {
  return POPUP_DOMAINS.has(domain) && (DOMAIN_METHODS[domain]?.length ?? 0) > 1;
}
