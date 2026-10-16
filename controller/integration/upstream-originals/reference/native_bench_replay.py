"""Offline normalized scenario -> actual five-unit C replay -> review evidence.

No transport or target execution. The immutable run is sealed before downstream
exports; an export error cannot revise the numerical evidence it references.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
import io
import json
import math
import multiprocessing as mp
from pathlib import Path
import subprocess
import sys
import time
import traceback

import allocator_parity as native
from allocator import AllocationResult, allocate_propulsive_torque
from bench_replay import MAX_INPUT_BYTES, SCHEMA, load_scenario, write_csv
from command_guard import CommandGuardState, apply_command_guard
from control_pipeline import replay_control_pipeline
from cycle_clock import CycleClockState, observe_cycle_clock
from guard_trusted_clear import apply_trusted_clear_guard
from c_parity import Cycle, Policy, Snapshot, STATE_NAMES, allocation, guard
from clock_parity import ClockState, clock_input, clock_policy, unpack
from pedal_parity import facts, adapted
from guard_parity import guard_input, config as guard_config, state as guard_state
from guard_parity import decoded as decoded_guard, signature as guard_signature

ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / '../research/TC-03I-native-bench-replay-protocol.json'
PROTOCOL_SHA256 = '474f0a2928b169e13bd41779b45fa73f4806ab03cc7d88817fc231c1c0f83733'
CASE_FREEZE = ROOT / '../research/TC-03I-native-bench-case-generator.json'
MAX_SAFE = 2**53 - 1
ZERO = (0.,) * 4
LABEL_PREFIX = 'Native C replay: '
PROVENANCE_PREFIX = 'Compiled C host replay; caller declaration (unverified): '
LIMITS = ['Offline synthetic/normalized host evidence only; no hardware IO, CAN, target or vehicle authority.',
          'Viewer checks presentation consistency, not authentication or controller reproduction.',
          'Abstract four-slot mapping; no physical motor calibration or safety certification.']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def bit_tree(value):
    """Strict JSON trace: preserve every float bit, including nonfinite results."""
    if type(value) is float:
        return {'binary64': native.bits(value)}
    if type(value) is dict:
        return {k: bit_tree(v) for k, v in value.items()}
    if type(value) in (list, tuple):
        return [bit_tree(v) for v in value]
    return value


def source_files():
    p = json.loads(PROTOCOL.read_bytes())
    return tuple(name.removeprefix('studio/reference/') if name.startswith('studio/reference/')
                 else '../' + name.removeprefix('studio/')
                 for name in p['source_bindings'] if name.startswith('studio/')) + (
                     'native_bench_replay.py', 'test_native_bench_replay.py',
                     '../research/TC-03I-native-bench-replay-protocol.json',
                     '../research/TC-03I-native-bench-case-generator.json')


def freeze_sources():
    if sha(PROTOCOL.read_bytes()) != PROTOCOL_SHA256:
        raise ValueError('frozen native replay protocol changed')
    p = json.loads(PROTOCOL.read_bytes())
    for name, identity in p['source_bindings'].items():
        if name.startswith('studio/'):
            relative = name.removeprefix('studio/')
            path = ROOT.parent / relative
            if sha(path.read_bytes().replace(b'\r\n', b'\n')) != identity['lf_normalized_sha256']:
                raise ValueError('frozen source changed: ' + relative)
    for name, identity in json.loads(CASE_FREEZE.read_bytes())['generator_files'].items():
        if sha((ROOT / name).read_bytes().replace(b'\r\n', b'\n')) != identity:
            raise ValueError('frozen replay generator changed: ' + name)
    return {name: sha((ROOT / name).read_bytes()) for name in source_files()}


def preflight(raw):
    value, cfg, samples = load_scenario(raw)
    def numbers(item):
        if type(item) in (int, float):
            try:
                finite = math.isfinite(float(item))
            except (ValueError, OverflowError):
                finite = False
            if not finite:
                raise ValueError('numeric input outside finite binary64 consumer domain')
        elif type(item) is dict:
            for child in item.values(): numbers(child)
        elif type(item) is list:
            for child in item: numbers(child)
    numbers(value)
    for title, prefix in (('label', LABEL_PREFIX), ('provenance', PROVENANCE_PREFIX)):
        if len((prefix + value[title]).encode('utf-16-le')) // 2 > 4000:
            raise ValueError(title + ' exceeds post-prefix UTF-16 viewer limit')
    for sample in samples:
        if type(sample.restart_requested) is not bool:
            raise ValueError('restart_requested must be boolean')
    ticks = [cfg.allocator.max_input_age_ms]
    for sample in samples:
        ticks.extend((sample.allocation.now_ms, sample.allocation.input_timestamp_ms))
    if any(type(v) is int and abs(v) > MAX_SAFE for v in ticks):
        raise ValueError('timestamp/age outside JavaScript-safe consumer domain')
    if not 1 <= cfg.fault.valid_samples_to_recover <= 2**32 - 1:
        raise ValueError('recovery policy outside uint32 consumer domain')
    return value, cfg, samples


class CommandRecorder:
    """Proxy only the old builder's module binding; delegate real commands."""
    def __init__(self, folder):
        self.folder, self.commands = folder, []

    def run(self, args, **kwargs):
        record = {'argv': [str(v) for v in args], 'cwd': str(kwargs.get('cwd', Path.cwd())),
                  'kind': 'version' if '--version' in args else 'compile'}
        self.commands.append(record)
        try:
            result = subprocess.run(args, **kwargs)
        except (OSError, subprocess.SubprocessError) as exc:
            record.update(status='failed', exception=type(exc).__name__, error=str(exc))
            self.logs(record, getattr(exc, 'stdout', '') or '', getattr(exc, 'stderr', '') or '')
            raise
        record.update(status='completed', returncode=result.returncode)
        self.logs(record, result.stdout or '', result.stderr or '')
        return result

    def logs(self, record, stdout, stderr):
        for label, data in (('stdout', stdout), ('stderr', stderr)):
            raw = data if isinstance(data, bytes) else data.encode('utf-8', errors='replace')
            name = f'command-{len(self.commands):02}-{label}.txt'
            (self.folder / name).write_bytes(raw)
            record[label] = {'file': name, 'sha256': sha(raw), 'bytes': len(raw)}

    @contextmanager
    def intercept_builder(self):
        previous = native.subprocess
        native.subprocess = self
        try:
            yield
        finally:
            native.subprocess = previous


def safe_number(value):
    return float(value) if math.isfinite(float(value)) else 0.


def run_native_samples(core, samples, cfg):
    """Native outputs own every proposed value; Python owners are an oracle only."""
    expected_rows = replay_control_pipeline(samples, cfg)
    previous, py_previous = CommandGuardState(ZERO), CommandGuardState(ZERO)
    clock_state, py_clock, gate_state = ClockState(), CycleClockState(), Snapshot(3, 0, 0)
    rows, traces = [], []
    for index, (sample, expected) in enumerate(zip(samples, expected_rows)):
        if sample.restart_requested:
            previous = CommandGuardState(ZERO, previous.pedal_overlap_latched)
            py_previous = CommandGuardState(ZERO, py_previous.pedal_overlap_latched)
        raw = core.allocate_raw(native.allocator_input(sample.allocation), native.allocator_config(cfg.allocator))
        candidate = native.decoded(raw)
        oracle = allocate_propulsive_torque(sample.allocation, cfg.allocator)
        base = decoded_guard(core.apply_raw(raw, guard_input(sample.guard), guard_config(cfg.guard), guard_state(previous)))
        py_base = apply_command_guard(oracle, sample.guard, cfg.guard, py_previous)
        clock = core.step(clock_state, clock_input(sample.allocation.now_ms, sample.guard.dt_s), clock_policy(cfg.period_ms))
        py_step = observe_cycle_clock(py_clock, sample.allocation.now_ms, sample.guard.dt_s, cfg.period_ms)
        clock_data = unpack(clock)
        reconciled = core.reconcile(facts(candidate, sample.guard, cfg.guard, previous, base, bool(clock.fault.kind)))
        effective = adapted(base, reconciled)
        py_effective = apply_trusted_clear_guard(oracle, sample.guard, cfg.guard, py_previous)
        py_effective = replace(py_effective, next_state=replace(py_effective.next_state,
            pedal_overlap_latched=py_effective.next_state.pedal_overlap_latched or
            (py_step.fault is not None and py_previous.pedal_overlap_latched)))
        clock_fault = clock_data['fault']
        observer_candidate = candidate
        if clock_fault or effective.status == 'inhibited':
            reason = clock_fault or (candidate.fault if candidate.status == 'fault' else effective.reason)
            observer_candidate = AllocationResult(ZERO, candidate.requested_nm, 0., 'fault', reason)
        gate_candidate = allocation(observer_candidate) if effective.status == 'inhibited' else raw
        decision = core.decide_raw(gate_state, Cycle(gate_candidate, guard(effective), clock.fault,
                                   sample.restart_requested), Policy(cfg.fault.valid_samples_to_recover))
        reason = bytes(decision.reason).decode('ascii')
        allowed, command = bool(decision.command_allowed), list(decision.command)
        row = {'sequence': index, 'now_ms': clock_data['now_ms'], 'restart_requested': sample.restart_requested,
            'allocator': asdict(candidate), 'guard': {'status': effective.status, 'reason': effective.reason,
                'output_nm': list(effective.output_nm), 'pedal_overlap_latched': bool(reconciled.next_latched)},
            'fault': {'sequence': index, 'generation': decision.next.generation,
                'restart_requested': sample.restart_requested, 'previous_state': STATE_NAMES[gate_state.state],
                'next_state': STATE_NAMES[decision.next.state], 'allocator_status': observer_candidate.status,
                'allocator_fault': observer_candidate.fault, 'requested_nm': safe_number(observer_candidate.requested_nm),
                'delivered_nm': safe_number(observer_candidate.delivered_nm),
                'wheel_torque_nm': [safe_number(v) for v in observer_candidate.wheel_torque_nm],
                'recovery_streak': decision.next.recovery_streak, 'reference_gate_allowed': allowed, 'reason': reason},
            'clock_fault': clock_fault, 'command_allowed': allowed, 'command_nm': command,
            'command_reason': effective.reason if allowed else reason}
        # Only request object identity is normalized: the source may retain int.
        expected = dict(expected, allocator=dict(expected['allocator'], requested_nm=float(expected['allocator']['requested_nm'])))
        actual_checks = {'allocator': native.signature(candidate), 'base': guard_signature(base),
            'effective': guard_signature(effective), 'clock': clock_data, 'row': bit_tree(row)}
        expected_checks = {'allocator': native.signature(oracle), 'base': guard_signature(py_base),
            'effective': guard_signature(py_effective),
            'clock': {'previous_tick': py_step.next_state.previous_tick, 'now_ms': py_step.now_ms, 'fault': py_step.fault},
            'row': bit_tree(expected)}
        trace = {'sequence': index, 'previous_proposed_bits': [native.bits(v) for v in previous.previous_output_nm],
                 'checks': actual_checks, 'python_checks': expected_checks, 'agreement': actual_checks == expected_checks}
        traces.append(trace)
        rows.append(row)
        if not trace['agreement']:
            return rows, traces, {'sequence': index, 'actual': actual_checks, 'expected': expected_checks}
        if not allowed and any(native.bits(v) != native.bits(0.) for v in command):
            return rows, traces, {'sequence': index, 'error': 'held command is not exact positive zero'}
        previous = CommandGuardState(tuple(command), bool(reconciled.next_latched))
        py_previous = CommandGuardState(tuple(expected['command_nm']), expected['guard']['pedal_overlap_latched'])
        clock_state, py_clock, gate_state = clock.next, py_step.next_state, decision.next
    return rows, traces, None


def _worker(library, samples, cfg, sender):
    try:
        core = native.AllocatorCore(Path(library))
        first = run_native_samples(core, samples, cfg)
        second = run_native_samples(core, samples, cfg)
        if encoded(bit_tree(first)) != encoded(bit_tree(second)):
            raise ValueError('same-library repeat disagreement')
        sender.send({'first': first, 'repeat_agreement': True})
    except BaseException:
        sender.send({'error': traceback.format_exc()})
    finally:
        sender.close()


def verify_in_child(library, samples, cfg, audit=None):
    """Bound native execution and release Windows DLL handles at child exit."""
    context = mp.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(str(library), samples, cfg, sender))
    audit = audit if audit is not None else {}
    started = time.monotonic()
    process.start(); sender.close()
    audit.update(status='started', pid=process.pid, replay_runs_requested=2, cycles_per_run_requested=len(samples))
    try:
        if not receiver.poll(120):
            raise RuntimeError('native scenario child timed out')
        try:
            result = receiver.recv()
        except EOFError as exc:
            process.join(10)
            raise RuntimeError(f'native child closed its pipe; exit {process.exitcode}') from exc
        process.join(10)
        if process.is_alive() or process.exitcode != 0 or 'error' in result:
            raise RuntimeError(result.get('error', f'native scenario child exit {process.exitcode}'))
        audit.update(status='completed', replay_runs_completed=2, cycles_per_run_completed=len(result['first'][0]))
        return result['first']
    except (RuntimeError, OSError, EOFError) as exc:
        audit.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        receiver.close()
        if process.is_alive():
            audit['owned_child_termination_requested'] = True
            process.terminate()
        process.join(10)
        audit.update(exitcode=process.exitcode, alive_after_cleanup=process.is_alive(),
                     elapsed_seconds=time.monotonic() - started)


def viewer_receipt(value, cfg, rows, identities, raw, run_hash, build=None):
    return {'schema': SCHEMA, 'numeric_contract_version': 2, 'clock_contract_version': 1,
        'label': LABEL_PREFIX + value['label'], 'provenance': PROVENANCE_PREFIX + value['provenance'],
        'scope': LIMITS[0], 'torque_unit': 'N*m', 'wheel_order': ['slot_' + str(i) for i in range(4)],
        'wheel_order_note': 'Abstract slots; physical wheel mapping requires team evidence.',
        'scenario_sha256': sha(raw), 'source_sha256': identities, 'config': asdict(cfg),
        'native_execution': {'engine': 'compiled C host; five owners', 'run_sha256': run_hash,
            'run_schema': 'enme408-native-bench-run/v1', 'repeat_agreement': True,
            'build': {key: build[key] for key in ('compiler', 'version', 'binary_sha256')} if build else None,
            'owner_versions': {'abi': 1, 'numeric': 2, 'allocator': 1, 'guard': 1, 'clock': 1, 'pedal': 1},
            'comparison': 'actual untouched Python owners; normalized requested binary64', 'limits': LIMITS},
        'summary': {'cycles': len(rows), 'allowed_cycles': sum(r['command_allowed'] for r in rows),
            'zero_command_cycles': sum(not any(r['command_nm']) for r in rows),
            'inhibited_cycles': sum(r['fault']['next_state'] == 'inhibited' for r in rows),
            'recovery_pending_cycles': sum(r['fault']['next_state'] == 'recovery_pending' for r in rows)},
        'records': rows}


def representation_check(receipt):
    """Encoding/finite presentation preflight, not a second JS gate validator."""
    def visit(value, path):
        if type(value) is float and not math.isfinite(value):
            raise ValueError('nonfinite viewer field: ' + path)
        if type(value) is dict:
            for key, child in value.items(): visit(child, path + '.' + key)
        elif type(value) in (list, tuple):
            for index, child in enumerate(value): visit(child, f'{path}[{index}]')
    visit(receipt, 'receipt')
    if not 1 <= len(receipt['source_sha256']) <= 50:
        raise ValueError('viewer source identity count outside 1..50')
    for row in receipt['records']:
        for name, values in (('allocator', row['allocator']['wheel_torque_nm']), ('command', row['command_nm'])):
            total = 0.
            for number in values: total += number
            if not math.isfinite(total):
                raise ValueError(f'nonfinite ordered {name} total at row {row["sequence"]}')
    raw = encoded(receipt)
    if len(raw) > 20_000_000:
        raise ValueError('viewer JSON exceeds 20000000-byte loader limit')
    return raw


def csv_bytes(receipt):
    class Buffer:
        @contextmanager
        def open(self, *args, **kwargs):
            yield stream
    stream = io.StringIO(newline='')
    write_csv(receipt, Buffer())
    return stream.getvalue().encode('utf-8')


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def reserve_directory(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('output directory must be new')
    resolved = output.resolve()
    if resolved.is_relative_to(ROOT.parents[2]):
        raise ValueError('attempt directory must be outside the source checkout')
    for parent in resolved.parents:
        if (parent / 'attempt.json').exists() or (parent / 'run.json').exists():
            raise ValueError('output must not descend from a retained attempt')
    resolved.mkdir(parents=False, exist_ok=False)
    write_new(resolved / 'attempt.json', encoded({'schema': 'enme408-native-bench-attempt/v1', 'limits': LIMITS}))
    return resolved


def execute(raw, folder, compiler=None):
    """One new attempt, one actual builder call, two replays on its one library."""
    run = {'schema': 'enme408-native-bench-run/v1', 'status': 'failed_retained', 'limits': LIMITS,
        'input_status': 'pending', 'build_status': 'not_attempted', 'execution_status': 'not_attempted',
        'parity_status': 'not_attempted', 'representation_status': 'not_attempted',
        'viewer_status': 'not_attempted', 'commands': []}
    recorder = CommandRecorder(folder)
    stage, rows = 'input', None
    try:
        write_new(folder / 'scenario.json', raw)
        run['scenario_sha256'] = sha(raw)
        value, cfg, samples = preflight(raw)
        run.update(input_status='accepted', scenario=value)
        identities = freeze_sources()
        run['source_sha256_before'] = identities
        snapshots = folder / 'sources'
        snapshots.mkdir()
        for index, name in enumerate(identities):
            write_new(snapshots / f'{index:02}-{Path(name).name}', (ROOT / name).read_bytes())
        stage = 'build'
        with recorder.intercept_builder():
            library, build = native.build_allocator_library(folder, compiler)
        run.update(build_status='completed', build=build)
        stage = 'execution'
        run.update(execution_status='started', native_child={})
        first = verify_in_child(library, samples, cfg, run['native_child'])
        rows, traces, failure = first
        run.update(execution_status='completed', trace=traces)
        if failure:
            run['first_mismatch'] = failure
            raise ValueError('C/Python parity mismatch')
        run.update(parity_status='passed', repeat_agreement=True, trace_sha256=sha(encoded(traces)))
        run['owner_versions'] = {'abi': 1, 'numeric': 2, 'allocator': 1, 'guard': 1, 'clock': 1, 'pedal': 1}
        run['source_sha256_after'] = freeze_sources()
        run['scenario_sha256_after'] = sha((folder / 'scenario.json').read_bytes())
        if run['scenario_sha256_after'] != run['scenario_sha256']:
            raise ValueError('retained scenario changed during replay')
        if identities != run['source_sha256_after']:
            raise ValueError('source changed during replay')
        stage = 'representation'
        provisional = viewer_receipt(value, cfg, rows, identities, raw, '0' * 64, build)
        representation_check(provisional)
        csv_raw = csv_bytes(provisional)
        run.update(status='native_verified', representation_status='preflight_passed', viewer_status='representable_preflight')
    except (ValueError, OSError, UnicodeError, RecursionError, OverflowError, RuntimeError, EOFError, subprocess.SubprocessError) as exc:
        run.update(failure={'stage': stage, 'type': type(exc).__name__, 'message': str(exc)})
        if stage == 'execution' and run['execution_status'] != 'completed':
            run['execution_status'] = 'failed'
        if stage == 'representation':
            run['viewer_status'] = 'unrepresentable'
        run[{'input': 'input_status', 'build': 'build_status', 'execution': 'parity_status',
             'representation': 'representation_status'}[stage]] = 'failed'
    run['commands'] = recorder.commands
    run['actual_invocations'] = {kind: sum(v['kind'] == kind for v in recorder.commands) for kind in ('version', 'compile')}
    # Sealed once, without downstream hashes or claims about export writes.
    run_raw = encoded(run)
    write_new(folder / 'run.json', run_raw)
    export = {'schema': 'enme408-native-bench-export/v1', 'run_sha256': sha(run_raw),
              'status': 'not_attempted', 'completed_files': {'run.json': sha(run_raw)}}
    if run['status'] == 'native_verified':
        export_stage, failed_file = 'encode_viewer', 'viewer-receipt.json'
        try:
            viewer_raw = representation_check(viewer_receipt(value, cfg, rows, identities, raw, sha(run_raw), build))
            for name, data in (('viewer-receipt.json', viewer_raw), ('trace.csv', csv_raw)):
                export_stage = 'write_viewer_receipt' if name == 'viewer-receipt.json' else 'write_csv'
                failed_file = name
                write_new(folder / name, data)
                export['completed_files'][name] = sha(data)
            export['status'] = 'completed'
        except (ValueError, OSError, UnicodeError) as exc:
            export.update(status='failed_retained', error={'stage': export_stage, 'failed_file': failed_file,
                          'type': type(exc).__name__, 'message': str(exc)})
    try:
        write_new(folder / 'export-status.json', encoded(export))
    except (OSError, UnicodeError) as exc:
        failure = {'schema': 'enme408-native-bench-export-failure/v1', 'status': 'failed_retained',
                   'error': {'stage': 'write_export_status', 'failed_file': 'export-status.json',
                             'type': type(exc).__name__, 'message': str(exc)}, 'prior_export': export}
        try:
            write_new(folder / 'export-failure.json', encoded(failure))
        except (OSError, UnicodeError) as fallback:
            failure['fallback_error'] = {'stage': 'write_export_failure', 'failed_file': 'export-failure.json',
                                         'type': type(fallback).__name__, 'message': str(fallback)}
            print(json.dumps(failure, sort_keys=True, ensure_ascii=True), file=sys.stderr)
        return 2
    return 0 if export['status'] == 'completed' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--example', action='store_true')
    source.add_argument('--scenario', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--cc')
    args = parser.parse_args(argv)
    try:
        folder = reserve_directory(args.output_dir)
        scenario = ROOT / 'bench-scenario.example.json' if args.example else args.scenario
        try:
            with scenario.open('rb') as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        except OSError as exc:
            write_new(folder / 'run.json', encoded({'schema': 'enme408-native-bench-run/v1',
                'status': 'failed_retained', 'input_status': 'failed', 'error': str(exc),
                'actual_invocations': {'version': 0, 'compile': 0}, 'limits': LIMITS}))
            return 2
        result = execute(raw, folder, args.cc)
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        print('native bench replay: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({'attempt': str(folder), 'exit_code': result}, sort_keys=True))
    return result


if __name__ == '__main__':
    raise SystemExit(main())
