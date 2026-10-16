/* Receipt presentation checks only. Reproduction remains in the Python tool. */
(function (root) {
  'use strict';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const text = value => typeof value === 'string' && value.length <= 4000;
  const vector = value => Array.isArray(value) && value.length === 4 && value.every(v => finite(v) && v >= 0);
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const fail = message => { throw new Error(message); };
  function validateReceipt(value) {
    if (!value || value.schema !== 'enme408-bench-replay/v1') fail('Choose an enme408-bench-replay/v1 receipt from the Python replay tool.');
    if (!text(value.label) || !text(value.provenance) || !value.label || !value.provenance) fail('The receipt needs a label and source provenance.');
    if (value.torque_unit !== 'N*m') fail('This viewer expects torque in N*m.');
    if (!Array.isArray(value.wheel_order) || value.wheel_order.join(',') !== 'slot_0,slot_1,slot_2,slot_3') fail('This viewer expects four abstract wheel slots in their recorded order.');
    if (!hash(value.scenario_sha256) || !value.source_sha256 || typeof value.source_sha256 !== 'object' || Array.isArray(value.source_sha256)) fail('The receipt has no valid source identity.');
    const hashes = Object.entries(value.source_sha256);
    if (!hashes.length || hashes.length > 50 || hashes.some(([name, digest]) => !text(name) || !hash(digest))) fail('A recorded source hash is malformed.');
    if (!Number.isInteger(value.config?.period_ms) || value.config.period_ms < 1 || value.config.period_ms > 60000 ||
        !Number.isInteger(value.config?.fault?.valid_samples_to_recover) || value.config.fault.valid_samples_to_recover < 1) fail('The replay period or recovery policy is malformed.');
    if (!Array.isArray(value.records) || !value.records.length || value.records.length > 4096) fail('The receipt must contain 1 to 4,096 cycles.');
    for (const [index, row] of value.records.entries()) {
      const bad = message => fail(`Cycle ${index}: ${message}`);
      if (!row || row.sequence !== index || (row.now_ms !== null && (!Number.isSafeInteger(row.now_ms) || row.now_ms < 0))) bad('sequence or timestamp is malformed.');
      if (typeof row.command_allowed !== 'boolean' || typeof row.restart_requested !== 'boolean' || !vector(row.command_nm) ||
          !finite(row.command_nm.reduce((a,b)=>a+b,0))) bad('proposed commands are malformed.');
      if (!['ready','limited','inhibited','recovery_pending'].includes(row.fault?.next_state) ||
          typeof row.fault?.reference_gate_allowed !== 'boolean' || !text(row.fault?.reason) ||
          !Number.isInteger(row.fault?.generation) || row.fault.generation < 0) bad('fault state is malformed.');
      if (!['ok','limited','inhibited'].includes(row.guard?.status) || !vector(row.guard?.output_nm) ||
          typeof row.guard?.pedal_overlap_latched !== 'boolean' ||
          !(row.guard.reason === null || text(row.guard.reason))) bad('guard state is malformed.');
      if (!(row.clock_fault === null || text(row.clock_fault)) || !(row.command_reason === null || text(row.command_reason))) bad('command reason is malformed.');
      if (!['ok','saturated','fault'].includes(row.allocator?.status) || !finite(row.allocator?.requested_nm) ||
          !finite(row.allocator?.delivered_nm) || row.allocator.delivered_nm < 0 || !vector(row.allocator?.wheel_torque_nm) ||
          !(row.allocator.fault === null || text(row.allocator.fault)) ||
          !finite(row.allocator.wheel_torque_nm.reduce((a,b)=>a+b,0))) bad('allocation is malformed.');
      const gate = row.fault.reference_gate_allowed && ['ready','limited'].includes(row.fault.next_state) && row.guard.status !== 'inhibited' && row.clock_fault === null;
      if (gate !== row.command_allowed || (!gate && row.command_nm.some(v => v !== 0))) bad('the final command disagrees with its recorded inhibit/recovery gate.');
      for (let wheel = 0; wheel < 4; wheel++) {
        if (gate && row.command_nm[wheel] !== row.guard.output_nm[wheel]) bad('an allowed command differs from the recorded guard output.');
        if (row.command_nm[wheel] > row.allocator.wheel_torque_nm[wheel]) bad('a proposed command exceeds its allocated wheel torque.');
      }
    }
    return value;
  }
  function summarize(receipt) {
    const rows = receipt.records;
    return {cycles: rows.length, allowed: rows.filter(row => row.command_allowed).length,
      held: rows.filter(row => !row.command_allowed).length,
      recovering: rows.filter(row => row.fault.next_state === 'recovery_pending').length};
  }
  function eventIndices(receipt) {
    return receipt.records.flatMap((row, index, rows) => {
      const previous = rows[index - 1];
      const changed = !previous || row.fault.next_state !== previous.fault.next_state ||
        row.command_reason !== previous.command_reason || row.restart_requested ||
        row.guard.pedal_overlap_latched !== previous.guard.pedal_overlap_latched;
      return changed ? [index] : [];
    });
  }
  const api = {validateReceipt, summarize, eventIndices};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BenchData = api;
})(globalThis);
