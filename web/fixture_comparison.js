/* Compare recorded synthetic fixtures; no simulation or inferred hardware data. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LapSimFixtureComparison = api;
})(typeof window === 'object' ? window : this, function () {
  'use strict';
  const PROFILES = {
    synthetic_awd: {label: 'AWD (4 motors)', motors: 4, topology: 'synthetic_independent_four_awd_v1'},
    synthetic_single_motor_rwd: {label: 'RWD (1 motor, open differential)', motors: 1, topology: 'synthetic_single_motor_open_diff_rwd_v1'},
    synthetic_rwd: {label: 'RWD (2 independent rear motors)', motors: 2, topology: 'synthetic_independent_rear_rwd_v1'}
  };
  function need(condition, message) { if (!condition) throw Error(message); }
  function validateObjective(objective) {
    need(objective?.name === 'engineering_proxy' && objective.fsae_points_enabled === false
      && objective.expression === 'lap_time_s + 120 * net_energy_kwh' && objective.lower_is_better === true,
      'Only the declared engineering proxy (lap seconds + 120 s/kWh times net energy; official points disabled) is supported');
  }
  function canonical(value) {
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort()
      .map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
    return JSON.stringify(value);
  }
  function finite(value, name) { need(Number.isFinite(value), name + ' must be finite'); return value; }
  function near(a, b) { return Number.isFinite(a) && Number.isFinite(b) && Math.abs(a-b) <= 1e-9*Math.max(1, Math.abs(a), Math.abs(b)); }
  function mean(values) { return values.reduce((sum, value) => sum+value, 0)/values.length; }
  function withoutProfile(spec) { const {profile, ...shared} = spec; return shared; }
  function context(run) {
    const {topology_id, ...sharedActuation} = run.actuation;
    return {car:run.car, driver:run.driver, environment:run.environment,
      clocks:run.clocks, course:run.course, actuation:sharedActuation};
  }
  function inspect(record) {
    need(record?.schema === 'lapsim.controller-tournament.v1' && record.status === 'completed', 'A completed tournament record is required');
    const spec = record.specification, profile = PROFILES[spec?.profile];
    need(profile, 'Unsupported synthetic fixture');
    validateObjective(spec.objective);
    need(record.sources && !Array.isArray(record.sources) && Object.keys(record.sources).length > 0
      && Object.values(record.sources).every(v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)), 'Source hashes are required');
    need(Array.isArray(spec.training) && spec.training.length > 0, 'Training conditions are required');
    const candidate = record.candidates?.[record.best_so_far];
    need(candidate?.summary?.eligible === true, 'An eligible recorded training winner is required');
    need(['fixed','traction','yaw_pi','tire_reserve'].includes(candidate.controller?.philosophy), 'Unsupported recorded controller');
    need(Array.isArray(candidate.run_ids) && candidate.run_ids.length === spec.training.length, 'Winner must contain exactly the training conditions');
    const cases = new Map(spec.training.map(c => [c.name, c]));
    need(cases.size === spec.training.length, 'Training condition names must be unique');
    const runs = new Map();
    for (const id of candidate.run_ids) {
      const run = record.runs?.[id];
      need(run?.eligible === true && run.status === 'completed' && Array.isArray(run.violations) && run.violations.length === 0,
        'Training winner contains an incomplete or ineligible run');
      need(cases.has(run.case?.name) && !runs.has(run.case.name) && canonical(run.case) === canonical(cases.get(run.case.name)),
        'Recorded run does not match its training condition');
      need(run.profile === spec.profile && run.topology?.motor_count === profile.motors && run.actuation?.topology_id === profile.topology,
        'Recorded topology does not match its declared fixture');
      need(run.topology.independent_yaw_authority === (profile.motors !== 1), 'Recorded yaw authority does not match its fixture');
      need(canonical(run.controller) === canonical(candidate.controller), 'Recorded controller differs from the winning candidate');
      for (const key of ['car','driver','environment','clocks','course']) need(run[key] && typeof run[key] === 'object', 'Missing recorded '+key);
      need(/^[a-f0-9]{64}$/.test(run.course.geometry_sha256), 'Course geometry hash is required');
      need(finite(run.course.length_m, 'Course length') > 0, 'Course length must be positive');
      const m = run.metrics;
      need(m && finite(m.lap_time_s, 'Lap time') > 0, 'Lap time must be positive');
      finite(m.net_energy_kwh, 'Net energy');
      need(near(m.fitness, m.lap_time_s+120*m.net_energy_kwh), 'Run proxy does not match its recorded lap and energy');
      runs.set(run.case.name, run);
    }
    const values = [...runs.values()];
    const lap = mean(values.map(r => r.metrics.lap_time_s));
    const energy = mean(values.map(r => r.metrics.net_energy_kwh));
    const fitness = mean(values.map(r => r.metrics.fitness));
    need(near(candidate.summary.mean_lap_time_s, lap) && near(candidate.summary.mean_net_energy_kwh, energy)
      && near(candidate.summary.fitness, fitness), 'Winner summary differs from its recorded runs');
    return {spec, runs, row:{profile:spec.profile, label:profile.label, motorCount:profile.motors,
      controller:candidate.controller.philosophy, lapTimeS:lap, netEnergyWh:energy*1000, proxy:fitness,
      candidateId:record.best_so_far, runIds:[...candidate.run_ids]}};
  }
  function compare(records) {
    need(Array.isArray(records) && records.length >= 2 && records.length <= 3, 'Choose two or three recorded fixtures');
    const checked = records.map(inspect), first = checked[0];
    need(new Set(checked.map(c => c.spec.profile)).size === checked.length, 'Choose distinct fixture profiles');
    for (let i=1; i<checked.length; i++) {
      need(canonical(records[0].sources) === canonical(records[i].sources), 'Source versions differ');
      need(canonical(withoutProfile(first.spec)) === canonical(withoutProfile(checked[i].spec)), 'Scenario or search budget differs');
      for (const [name, run] of first.runs) {
        need(canonical(context(run)) === canonical(context(checked[i].runs.get(name))),
          'Recorded course, vehicle, driver, environment or actuator settings differ for '+name);
      }
    }
    const course = first.runs.values().next().value.course;
    return {rows:checked.map(c => c.row), courseLabel:course.label, courseLengthM:course.length_m,
      geometrySha256:course.geometry_sha256, seed:first.spec.seed, trainingConditions:first.runs.size,
      classification:'synthetic fixtures; motor count and total available torque differ; not a calibrated drivetrain benefit'};
  }
  return {compare, validateObjective};
});
