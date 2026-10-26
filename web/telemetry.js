/* Numeric projection of saved telemetry; no simulation or resampling. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LapSimTelemetry = api;
})(typeof window === 'undefined' ? this : window, function () {
  'use strict';
  const base = ['time_s', 'x_m', 'y_m', 'u_mps', 'v_mps', 'heading_rad', 'yaw_rad_s',
    'progress_m', 'cross_track_m', 'pack_energy_j', 'pack_power_w', 'brake_shortfall_nm'];
  const wheels = ['fl', 'fr', 'rl', 'rr'];
  const stages = ['requested', 'proposed', 'limited', 'achieved', 'friction'];
  const fields = [...base];
  for (const wheel of wheels) {
    fields.push(...stages.map(stage => `${stage}_${wheel}_nm`),
      `slip_${wheel}_ratio`, `utilization_${wheel}_ratio`);
  }
  function timeseriesCsv(record) {
    let previous = -1;
    const extras=['policy_mode_code','brake_pedal_fraction','regen_request_nm','pack_soc_ratio'];
    const extended=record.telemetry.some(row=>extras.some(key=>Object.hasOwn(row,key)));
    const selectedFields=extended?[...fields,...extras]:fields;
    const lines = [selectedFields.join(',')];
    for (const sample of record.telemetry) {
      const values = base.map(key => sample[key === 'time_s' ? 't_s' : key]);
      for (let i = 0; i < wheels.length; i++) {
        values.push(...stages.map(stage => sample[`${stage}_nm`]?.[i]),
          sample.slip?.[i], sample.utilization?.[i]);
      }
      if(extended)values.push(...extras.map(key=>sample[key]));
      if (!values.every(Number.isFinite) || sample.t_s <= previous)
        throw Error('CSV requires finite channels and strictly increasing recorded time.');
      previous = sample.t_s;
      lines.push(values.join(','));
    }
    return lines.join('\n') + '\n';
  }
  return { fields, timeseriesCsv };
});
