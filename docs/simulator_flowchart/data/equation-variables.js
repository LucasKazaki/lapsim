/* Reviewed notation guide. Source catalog definitions remain the authoritative
   implementation; shorthand here is local to each curated equation. */
(() => {
  "use strict";
  const { N, branches } = window.LAPSIM_FLOWCHART_BUILD;
  const glossary = {
    rho: ["kg/m³", "Air density"], v: ["m/s", "Vehicle speed; in the planar branch, body lateral velocity"],
    u: ["m/s", "Body longitudinal velocity in the planar model"],
    q: ["Pa", "Dynamic pressure; normalized grip/geometry quantities use separate local definitions"],
    A: ["m²", "Aerodynamic reference area"], C_d: ["dimensionless", "Drag coefficient"],
    C_l: ["dimensionless", "Signed lift coefficient; negative lift produces downforce"],
    CdA: ["m²", "Drag coefficient multiplied by reference area"],
    D: ["N", "Drag force; in Pacejka, peak force amplitude"],
    D_down: ["N", "Total aerodynamic downforce"], D_front: ["N", "Front axle downforce"], D_rear: ["N", "Rear axle downforce"],
    phi: ["rad", "Quasi-static body roll angle"], phi_limit: ["rad", "Configured roll breakpoint"],
    retention_at_limit: ["dimensionless", "Downforce retained at the roll breakpoint"],
    f_roll: ["dimensionless", "Clipped body roll fraction"], front_fraction: ["dimensionless", "Front downforce distribution"],
    f_front: ["dimensionless", "Static front weight fraction"],
    m: ["kg", "Vehicle mass"], m_eff: ["kg", "Vehicle mass plus equivalent rotating mass"], m_vehicle: ["kg", "Translating vehicle mass"],
    g: ["m/s²", "Gravitational acceleration; g_i in the corridor audit is a lateral coordinate"],
    t: ["s", "Elapsed time"], s: ["m", "Path station/distance; a literal s after a number denotes seconds"],
    ds: ["m", "Spatial cell length"], dt: ["s", "Elapsed timestep"], dt_next: ["s", "Next timestep iterate"],
    x: ["m or state vector", "World x coordinate; x=[...] denotes the planar state vector"], y: ["m", "World y coordinate"],
    X: ["m", "Planar world x coordinate"], Y: ["m", "Planar world y coordinate"], psi: ["rad", "World heading/yaw angle"],
    a_x: ["m/s²", "Longitudinal acceleration"], a_y: ["m/s²", "Lateral acceleration"],
    a_target: ["m/s²", "Requested constant-acceleration cell target"], a_to_limit: ["m/s²", "Acceleration that reaches the speed cap at cell exit"],
    a_brake: ["m/s²", "Positive braking deceleration magnitude"], a_lat: ["m/s²", "Lateral acceleration allowance"],
    a_decel: ["m/s²", "Positive deceleration magnitude for the brake root"],
    v_entry: ["m/s", "Cell entry speed"], v_exit: ["m/s", "Cell exit speed"], v_target: ["m/s", "Target speed"],
    v_limit: ["m/s", "Vehicle speed cap"], v_start: ["m/s", "Lap start speed"], v_finish: ["m/s", "Lap finish speed"],
    v_wheel: ["m/s", "Driven tire surface speed"], wheel_surface_speed: ["m/s", "Tire circumference speed after slip response"],
    v_prior: ["m/s", "Speed before the corridor edge rule"], v_final: ["m/s", "Edge-rule limited speed"], v_lat: ["m/s", "Velocity normal to the reference path"],
    R_tire: ["m", "Loaded tire radius"], R_wheel: ["m", "Loaded wheel/tire radius"], wheelbase: ["m", "Front-to-rear axle spacing"],
    L: ["m", "Wheelbase; source path length in racing-line preprocessing"], L_track: ["m", "Track lap length"], L_relax: ["m", "Longitudinal slip relaxation length"],
    h_CG: ["m", "Center of gravity height above the ground"], h_elastic: ["m", "CG height above the roll axis, clipped nonnegative"],
    h_RA: ["m", "Roll axis height"], track_front: ["m", "Front axle track width"], track_rear: ["m", "Rear axle track width"],
    K_front: ["N·m/rad", "Front elastic roll stiffness"], K_rear: ["N·m/rad", "Rear elastic roll stiffness"], K_roll: ["N·m/rad", "Total elastic roll stiffness"],
    Fz: ["N", "Positive normal load at the contact patch"], F_x: ["N", "Longitudinal tire force"], F_y: ["N", "Lateral tire force"],
    F: ["N", "Force magnitude in the qualified axle pressure map"], N: ["count", "Number of geometry samples in racing-line preprocessing"],
    Fx: ["N", "Longitudinal tire force"], Fy: ["N", "Lateral tire force"], F_peak: ["N", "Peak pure-slip tire force"],
    F_roll: ["N", "Rolling resistance force"], F_corner: ["N", "Empirical cornering resistance force"], F_resist: ["N", "Total resisting force"],
    F_drive: ["N", "Delivered drive force"], F_brake: ["N", "Braking force magnitude"], F_regen: ["N", "Regenerative braking force magnitude"],
    F_target: ["N", "Requested longitudinal force before actuator conversion"], F_capacity: ["N", "Available contact-patch force capacity"],
    C_rr: ["dimensionless", "Rolling resistance coefficient"], C_corner: ["dimensionless", "Empirical cornering resistance coefficient"],
    mu: ["dimensionless", "Tire friction coefficient"], mu_base: ["dimensionless", "Base planar tire friction coefficient"],
    mu_effective: ["dimensionless", "Tire friction coefficient multiplied by scenario grip"], grip_multiplier: ["dimensionless", "Uniform tire grip assumption"],
    road_multiplier: ["dimensionless", "Local road grip factor"], u_y: ["dimensionless", "Fraction of lateral tire capacity used"],
    alpha: ["rad", "Slip angle; target-bearing angle in pure pursuit"], alpha_y: ["dimensionless", "tan(slip angle) plus Pacejka horizontal shift"],
    S_H: ["dimensionless", "Pacejka horizontal shift in tangent-slip coordinate"], S_V: ["N", "Pacejka vertical force shift"],
    B: ["context dependent", "Pacejka stiffness factor; in corridor audit, interpolation remainder bound"],
    C: ["dimensionless", "Pacejka shape factor"], E: ["dimensionless or J", "Pacejka curvature factor; E in planar-energy is mechanical energy"],
    phase: ["rad", "Pacejka sine phase"], C_kappa: ["N", "Planar longitudinal stiffness per unit slip ratio"], C_alpha: ["N/rad", "Planar lateral cornering stiffness"],
    kappa: ["1/m", "Path curvature; tire-slip and planar-slip nodes use dimensionless longitudinal slip ratio"],
    kappa_request: ["1/m", "Steering-requested path curvature"], kappa_effective: ["1/m", "Achieved curvature after tire lateral saturation"],
    kappa_target: ["dimensionless", "Longitudinal tire slip target"], kappa_peak: ["dimensionless", "Slip ratio at peak longitudinal force"],
    kappa_prev: ["dimensionless", "Previous longitudinal slip ratio"], kappa_next: ["dimensionless", "Updated longitudinal slip ratio"],
    delta: ["rad", "Road-wheel steering angle"],
    omega: ["rad/s", "Wheel angular velocity"], omega_motor: ["rad/s", "Motor angular velocity"], omega_wheel: ["rad/s", "Wheel angular velocity"],
    RPM: ["rev/min", "Motor rotational speed"], RPM_max: ["rev/min", "Motor hard speed limit"],
    T_motor: ["N·m", "Motor shaft torque"], T_wheel: ["N·m", "Wheel torque"], T_drive: ["N·m", "Per-wheel drive torque"], T_brake: ["N·m", "Brake torque; tire-slip branch uses F_brake for force"],
    T_available: ["N·m", "Available motor torque after limits"], T_power: ["N·m", "Motor torque allowed by power"],
    ratio: ["dimensionless", "Final drive motor-to-wheel speed ratio"], eta_chain: ["dimensionless", "Chain-drive efficiency"],
    eta_motor: ["dimensionless", "Motor efficiency"], eta_inverter: ["dimensionless", "Inverter efficiency"],
    P_wheel: ["W", "Wheel mechanical power"], P_motor: ["W", "Motor shaft or electrical power as qualified by the equation"],
    P_battery: ["W", "Battery terminal discharge power"], P_terminal: ["W", "Signed battery terminal power; positive is discharge"],
    P_request: ["W", "Signed requested terminal power"], P_charge: ["W", "Charging power magnitude"], P_DC: ["W", "Battery DC power"],
    I: ["A", "Battery current; positive discharge and negative charge"], R0: ["Ω", "Battery instantaneous ohmic resistance"],
    R1: ["Ω", "Battery polarization resistance"], C1: ["F", "Battery polarization capacitance"],
    V_terminal: ["V", "Battery terminal voltage"], V_OCV: ["V", "Open-circuit pack voltage at SOC"], V_p: ["V", "RC polarization voltage"],
    V_source: ["V", "OCV minus polarization voltage"], SOC: ["dimensionless", "State of charge, a fraction from zero to one"], SOC_next: ["dimensionless", "Updated state of charge"],
    Q_pack: ["Ah", "Pack charge capacity"], Q_cell: ["Ah", "Per-cell charge capacity"], series_cells: ["count", "Number of cells in series"], parallel_cells: ["count", "Number of parallel cell strings"],
    J: ["context dependent", "Rotational inertia in wheel dynamics; geometric objective in racing-line optimization"],
    Jw: ["kg·m²", "Wheel rotational inertia"], Iz: ["kg·m²", "Vehicle yaw moment of inertia"], J_i: ["kg·m²", "Per-wheel rotational inertia"],
    J_rotor: ["kg·m²", "Motor rotor moment of inertia"], J_chain: ["kg·m²", "Chain-drive rotational inertia at its specified shaft"],
    r: ["rad/s", "Planar yaw rate; tire-slip r is dimensionless relaxation fraction"],
    pi: ["dimensionless", "Circle constant π"], Delta: ["operator", "Change/increment prefix; units belong to the following quantity"],
    theta: ["rad", "Polygon turning angle"], ell: ["m", "Cell/chord length"], lambda: ["1/m²", "Geometric objective length penalty coefficient"],
    c: ["m", "B-spline lateral offset coefficients"], d: ["m", "Lateral offset or preview distance according to source"],
    n: ["dimensionless", "Unit path-normal vector; n in integration subscripts is a step index"],
    i: ["index", "Wheel, cell, or sample index"], j: ["index", "Wheel, cell, or basis index"],
    T: ["s", "Event elapsed time in scoring"], T_min: ["s", "Fastest/reference event time"], T_max: ["s", "Maximum eligible event time"],
    P_min: ["points", "Minimum event score"], P_max: ["points", "Maximum event score"],
    EF: ["dimensionless", "Efficiency factor from time and adjusted energy ratios"], EF_min: ["dimensionless", "Minimum eligible efficiency factor"], EF_max: ["dimensionless", "Reference maximum efficiency factor"],
    energy_kWh: ["kWh", "Consumed terminal energy used for scoring"], completed_laps: ["count", "Completed endurance laps"],
    points: ["points", "Event score after clipping"], p: ["context dependent", "Brake pressure in psi; timed-score exponent is dimensionless"],
    p_eff: ["psi", "Pressure after cap and deadband"], p_max: ["psi", "Brake pressure cap"], p_front: ["psi", "Front circuit pressure"], p_rear: ["psi", "Rear circuit pressure"],
    deadband: ["psi", "Pressure below which no linear braking force is requested"],
  };
  const ignored = new Set(["min", "max", "abs", "sqrt", "sin", "cos", "tan", "atan", "atan2", "exp", "sign", "sum", "clip", "hypot", "dot", "cross", "sinc", "ceil", "Solve", "If", "For", "Use", "CG", "Ah", "Per", "FL", "FR", "RL", "RR"]);

  function notation(symbol, node) {
    const base = symbol.replace(/_(?:i|j|next|prev)$/, "");
    let entry = glossary[symbol] || glossary[base];
    if (!entry) {
      if (/^(Fz|F_|Fx|Fy|D_)/.test(symbol)) entry = ["N", "Force/load quantity; qualifiers identify axle, wheel, direction, request, capacity, or limit"];
      else if (/^v_/.test(symbol)) entry = ["m/s", "Speed quantity; qualifiers identify the operating point or limit"];
      else if (/^a_/.test(symbol)) entry = ["m/s²", "Acceleration/deceleration quantity; inspect its sign and qualifier"];
      else if (/^P_/.test(symbol)) entry = ["context dependent", "Power or score quantity; inspect the enclosing equation"];
      else if (/^T_/.test(symbol)) entry = ["context dependent", "Torque or elapsed-time quantity; inspect the enclosing equation"];
      else entry = ["not declared", "Local shorthand in the curated equation. Inspect the linked exact source definitions for type, units, and context"];
    }
    if (symbol === "kappa" && ["planar-slip", "tire-slip"].includes(node.id)) entry = ["dimensionless", "Longitudinal tire slip ratio"];
    if (symbol === "r" && node.id === "tire-slip") entry = ["dimensionless", "Time/distance relaxation update fraction"];
    if (symbol === "E" && node.id === "planar-energy") entry = ["J", "Total translational, yaw, and wheel rotational mechanical energy"];
    if (symbol === "R" && node.id.startsWith("planar-wheel-velocity")) entry = ["dimensionless", "2D rotation matrix"];
    else if (symbol === "R" && node.id.includes("score")) entry = ["dimensionless", "Normalized timing ratio used in event scoring"];
    else if (symbol === "R") entry = ["m", "Tire radius"];
    if (symbol === "q" && node.id.startsWith("pose-")) entry = ["dimensionless", "Road grip multiplier"];
    if (symbol === "a" && node.id === "battery-rc") entry = ["dimensionless", "RC exponential decay factor exp(-dt/(R1*C1))"];
    if (symbol === "p" && node.id === "timed-score") entry = ["dimensionless", "Scoring exponent: one for acceleration, two for skidpad"];
    if (symbol === "a_brake" && node.id === "eq-brake-entry") entry = ["m/s²", "Signed longitudinal acceleration while braking; negative for deceleration"];
    if (node.id === "rl-audit-bound") {
      const audit = {
        D: ["m", "Displacement vector between modeled and reference paths"],
        D_max: ["m", "Upper bound on displacement-vector magnitude over the interval"],
        ell: ["m", "Modeled cell arc length"], r: ["m", "Magnitude of reference-position derivative with respect to cell fraction"],
        h: ["dimensionless", "Subinterval span in normalized cell fraction"],
        u: ["dimensionless", "Magnitude of the unnormalized reference-normal derivative with respect to cell fraction"],
        q_min: ["dimensionless", "Minimum magnitude of the interpolated reference normal"],
        B: ["m", "Bound on the second derivative of scalar lateral coordinate with respect to cell fraction"],
        g: ["m", "Scalar lateral displacement along the normalized reference normal"],
      };
      if (audit[symbol]) entry = audit[symbol];
    }
    if (node.id === "rl-audit-coordinate") {
      const coordinate = {g_i: ["m", "Scalar normal-coordinate displacement for cell i"], f: ["dimensionless", "Normalized cell fraction"], P_i: ["m", "Modeled path position vector"], R_i: ["m", "Reference path position vector"], N_i: ["dimensionless", "Interpolated reference normal vector"]};
      if (coordinate[symbol]) entry = coordinate[symbol];
    }
    if (node.id === "rl-curvature" && ["a", "b"].includes(symbol)) entry = ["m", "Adjacent polygon chord vectors"];
    if (node.id === "rl-objective" && symbol === "J") entry = ["1/m²", "Length-averaged squared curvature plus geometric length penalty"];
    if (node.id === "rl-offset" && symbol === "B_ij") entry = ["dimensionless", "Periodic B-spline basis weight for sample i and coefficient j"];
    if (node.id === "road-map-cell-factor" && ["q_i", "gamma", "beta", "patch_factor"].includes(symbol)) entry = ["dimensionless", "Scenario/base/local patch grip factor as qualified in the equation"];
    return {name: symbol, unit: entry[0], meaning: entry[1], type: "mathematical shorthand", role: "equation quantity", unitEvidence: "Reviewed notation guide; the exact source catalog exposes implementation names"};
  }

  function addDetails(node) {
    const originalChildren = node.children || [];
    for (const child of originalChildren) addDetails(child);
    if (!(node.equations || []).length) return;
    const equationChildren = node.equations.map((equation, index) => {
      // Strip dimensional literals before identifying variables: the "m" in
      // "0.01 m^-2" is a unit, rather than the vehicle-mass shorthand m.
      const expression = equation.replace(/\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\s*(?:m\/s(?:\^2)?|m\^-?2|m|s|rad)\b/gi, "");
      const tokens = [...new Set(expression.match(/[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*/g) || [])]
        .filter((token) => !ignored.has(token) && (glossary[token] || glossary[token.replace(/_(?:i|j|next|prev)$/, "")] || token.includes("_") || /^[A-Z][a-z]?$/.test(token) || ["a", "b", "h", "f", "r", "q", "R", "lambda", "ell", "omega", "multiplier", "scale", "lookahead", "margin", "residual", "conversion", "w", "gamma", "beta"].includes(token)));
      const variableChildren = tokens.map((symbol, tokenIndex) => ({
        ...N(`${node.id}-eq-${index + 1}-var-${tokenIndex + 1}`, symbol, "variable", node.status, notation(symbol, node).meaning, {s: []}),
        variable: notation(symbol, node), sources: node.sources || [],
        equations: [], related: [node.id],
      }));
      return { ...N(`${node.id}-eq-${index + 1}`, `Equation ${index + 1}`, "equation", node.status, equation, {e: [equation]}, variableChildren), sources: node.sources || [] };
    });
    node.children = [...originalChildren, ...equationChildren];
  }
  for (const branch of branches) addDetails(branch);
})();
