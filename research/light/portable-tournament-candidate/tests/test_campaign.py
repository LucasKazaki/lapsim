"""UNTRUSTED metadata/storage integration fixtures, NOT numerical/auth evidence.

The fake provider never creates a worker, observes resources, holds a native
lease, verifies a signature or proves cleanup. Its deliberately synthetic raw
packets must never be used as production receipts, laps or qualified policies.
Tests exercise actual bounded cloud orchestration and temporary-file storage.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from lapsim_light_campaign import campaign, continuation, gate_ledger, raw_journal as journal
from lapsim_light_campaign.dispatch_request import SCHEMA, NUMERICAL_ENTRYPOINT, REQUIRED_RUNTIME_SERVICES
from lapsim_light_campaign.field_archive import read_field_archive
from lapsim_light_campaign.guarded_dispatch import OwnedChunkResult
from lapsim_light_campaign.input_contracts import decode, digest, encode
from lapsim_light_campaign.stepping import plan_chunk, boundary_counts
from lapsim_light_campaign.tournament_plan import freeze_tournament, _fresh_memory
from lapsim_light_policies import core_registry


def pin(label):
    return sha256(('UNTRUSTED-UNIT-TEST-' + label).encode()).hexdigest()


def plan_fixture(*, course_sha256=None, line_sha256=None, reference_provenance=None):
    course_sha256 = pin('course') if course_sha256 is None else course_sha256
    line_sha256 = pin('no-admitted-reference') if line_sha256 is None else line_sha256
    environment = pin('environment-not-observed')
    source = {'family': 'lapsim.portable-awd-standing-numerical-bridge.v1',
        'source_manifest_sha256': pin('source-not-observed'), 'numerical_environment_sha256': environment,
        'external_bindings': {'source_observer_sha256': pin('no-observer'), 'residual_regen_rule_sha256': pin('no-rule')}}
    source['sha256'] = digest(source)
    origins = {}
    for policy in journal.POLICIES:
        power = {name: 0 for name in ('integration_trials', 'integration_substeps', 'wheel_stop_events')}
        power.update({name: 0. for name in ('wheel_work_j', 'conversion_loss_j', 'contact_dissipation_j',
            'friction_brake_work_j', 'external_work_j', 'driver_proxy_impulse_ns', 'tire_longitudinal_impulse_ns',
            'absolute_contact_force_error_ns', 'wheel_stop_dissipation_j')})
        power.update(pack_energy_j=9_000_000., actuator_memory_nm=[0.]*4,
            plant={'u_mps': 0., 'v_mps': 0., 'yaw_rate_rad_s': 0., 'wheel_speeds_rad_s': [0.]*4,
                   'x_m': 0., 'y_m': 0., 'heading_rad': 0.})
        state = {'automatic_drs_enabled': True, 'last_signals': None,
            'drs': {'ticks': 0, 'pending_open_ticks': 0, 'commanded_mode': 'closed', 'actual_mode': 'closed', 'reason': 'initialized_closed'},
            'thermal': {'last_contact_slip_energy_j': 0.,
                'thermal': {'ticks': 0, 'temperature_c': 70., 'absorbed_slip_heat_j': 0., 'heat_to_ambient_j': 0.},
                'light': {'feedback_ticks': 0, 'load_longitudinal_mps2': 0., 'load_lateral_mps2': 0.,
                          'aero_mode': 'closed', 'powered': power}}}
        context = {'family': source['family'], 'source': source, 'configuration_sha256': pin('configuration'),
            'course': {'id': 'amz_fssim_fsi_approx', 'bundle_sha256': course_sha256, 'length_m': 100.},
            'reference_line': {'artifact_sha256': line_sha256, **(reference_provenance or {})},
            'controller_policy': core_registry.entry(policy), 'actuation': {'topology_id': journal.TOPOLOGY, 'pack_capacity_j': 18_000_000.},
            'motor_count': 4, 'drive_availability': [True]*4, 'campaign_eligible': False,
            'mode': 'one_lap', 'laps_target': 1, 'qualification_or_execution_authority': False,
            'initial_state': state,
            'standing_start': {'vehicle_u_mps': 0., 'vehicle_v_mps': 0., 'yaw_rate_rad_s': 0.,
                'wheel_omega_rad_s': [0.]*4, 'actuator_memory_nm': [0.]*4, 'clock_s': 0.},
            'clocks': {'plant_period_s': .001, 'driver_interval_ticks': 50, 'allocator_interval_ticks': 10, 'logging_interval_ticks': 20},
            'driver': {'initial_speed_mps': 0.}, 'limits': {'maximum_ticks': 1000, 'maximum_work': 8000, 'logging_ticks': 20}}
        checkpoint = {'schema': journal.CHECKPOINT_SCHEMA, 'config_id': policy, 'context': context, 'context_sha256': digest(context),
            'state': state, 'memory': _fresh_memory(), 'tick': 0, 'segment': 0, 'parent_chunk_sha256': None,
            'status': 'running', 'violation': None, 'finish': None, 'rejected_state': None, 'lap_crossings': []}
        identity = {'source_sha256': source['sha256'], 'configuration_sha256': pin('configuration'),
            'course_bundle_sha256': course_sha256, 'line_artifact_sha256': line_sha256,
            'environment_sha256': environment, 'policy_id': policy, 'topology_id': journal.TOPOLOGY,
            'drive_availability': [True]*4, 'regen_enabled': False, 'role': 'development', 'heldout_used': False}
        origins[policy] = {'identity': identity, 'origin': {'checkpoint': checkpoint, 'checkpoint_sha256': digest(checkpoint)}}
    raw = encode(origins)
    plan = freeze_tournament(raw, expected_origins_raw_sha256=sha256(raw).hexdigest())
    return encode(plan), plan['plan_sha256']


class FakeProvider:
    """Deliberate no-auth/no-worker double, not an OriginalGuard implementation."""
    implementation_sha256 = pin('fake-provider')

    def __init__(self, statuses=('completed',), fail=None, cancel=None):
        self.statuses, self.fail, self.cancel = statuses, fail, cancel
        self.calls = []

    def execute_owned_request(self, request_raw, checkpoint_raw, *, numerical_backend_family):
        if self.fail is not None:
            raise self.fail
        request, parent = decode(request_raw, 128*1024)['request'], decode(checkpoint_raw, journal.MAX_CHECKPOINT)
        self.calls.append((request, parent))
        status = self.statuses[min(len(self.calls)-1, len(self.statuses)-1)]
        output = deepcopy(parent['checkpoint'])
        delta = 0 if status == 'invalid' else 1
        output['tick'] += delta
        output['segment'] += 1
        output['parent_chunk_sha256'] = None
        output['status'] = status
        output['violation'] = 'UNTRUSTED unit failure' if status == 'invalid' else None
        output['memory'].update(boundary_counts(output['tick']))
        state = output['state']
        state['drs']['ticks'] = state['thermal']['thermal']['ticks'] = state['thermal']['light']['feedback_ticks'] = output['tick']
        power = state['thermal']['light']['powered']
        power['integration_trials'] += delta
        power['integration_substeps'] += delta
        power['pack_energy_j'] -= 1000*delta
        output['memory']['sampled_draw_j'] += 1000*delta
        if status == 'completed':
            power['plant']['x_m'] = .1
            output['memory']['source_progress_m'] = 100.
            before = deepcopy(parent['checkpoint']['state'])
            before['thermal']['light']['powered']['plant']['x_m'] = -.1
            gate = {'origin_xy_m': [0., 0.], 'forward_unit': [1., 0.], 'finite_half_width_m': 3.,
                    'scope': 'Source physical gate;not moved with reference distance'}
            output['lap_crossings'] = list(gate_ledger.crossing((), tick=output['tick'], before_pose=(-.1, 0.), after_pose=(.1, 0.),
                before_pack=before['thermal']['light']['powered']['pack_energy_j'], after_pack=power['pack_energy_j'],
                state=state, memory=output['memory'], before_state=before, source_sha256=request['identity']['source_sha256'],
                source_length_m=100., source_before_m=99.9, source_after_m=100., gate=gate))
            output['finish'] = output['lap_crossings'][0]['crossing']
        chunk = {'schema': journal.CHUNK_SCHEMA, 'source_sha256': request['identity']['source_sha256'],
            'config_id': output['config_id'], 'course_id': 'amz_fssim_fsi_approx', 'context_sha256': output['context_sha256'],
            'start_tick': parent['checkpoint']['tick'], 'end_tick': output['tick'],
            'parent_chunk_sha256': parent['checkpoint']['parent_chunk_sha256'], 'input_checkpoint_sha256': parent['checkpoint_sha256'],
            'output_checkpoint': {'checkpoint': deepcopy(output), 'checkpoint_sha256': digest(output)}, 'telemetry': [], 'status': status,
            'execution_evidence': 'RAW_STAGED_REQUIRES_SEPARATE_OWNED_RECEIPT_ADMISSION', 'awards': {'points': None, 'overall_winner': None}}
        envelope = {'chunk': chunk, 'chunk_sha256': digest(chunk)}
        output['parent_chunk_sha256'] = envelope['chunk_sha256']
        if self.cancel is not None:
            self.cancel.set()
        receipt = b'UNTRUSTED UNIT TEST DOUBLE: NO ORIGINAL EXECUTION OR CLEANUP RECEIPT'
        return OwnedChunkResult(digest(request), request['identity']['source_sha256'], encode(envelope),
            encode({'checkpoint': output, 'checkpoint_sha256': digest(output)}), receipt, sha256(receipt).hexdigest())

    def require_authenticated_owned_execution_and_cleanup(self, request_raw, result):
        return None  # Unit double only; never a production verifier.


class RequestSource:
    def __init__(self, plan_raw, count=None):
        self.cells = {c['policy_id']: c for c in decode(plan_raw, 2*1024*1024)['plan']['cells']}
        self.calls, self.count = [], count

    def __call__(self, policy_id, checkpoint_raw, *, requested_ticks, remaining_requested_wall_time_ms):
        if self.count is not None and len(self.calls) >= self.count:
            return None
        self.calls.append((policy_id, checkpoint_raw))
        parent = decode(checkpoint_raw, journal.MAX_CHECKPOINT)
        identity = self.cells[policy_id]['identity']
        planned = plan_chunk(checkpoint_raw, expected_checkpoint_sha256=parent['checkpoint_sha256'], expected_identity=identity, ticks=requested_ticks)
        body = {'schema': SCHEMA, 'mode': 'simulation_only', 'identity': identity, 'numerical_entrypoint': dict(NUMERICAL_ENTRYPOINT),
            'request_nonce': pin('request-'+str(len(self.calls))), 'prepared_at_unix_s': 1, 'input_admission_expires_at_unix_s': 100,
            'authority_key_id': 'UNTRUSTED_UNIT_TEST', 'authority_public_key_sha256': pin('no-key'), 'chunk_plan': planned,
            'input_admissions': {purpose: {'envelope_sha256': pin('no-statement'), 'statement_sha256': pin('no-signature'),
                'verifier_implementation_sha256': pin('no-verifier')} for purpose in ('line_geometry_review', 'runtime_environment_review')},
            'resource_request': {'maximum_wall_time_ms': 10, 'maximum_rss_bytes': 1024, 'workers': 1},
            'required_external_runtime_services': list(REQUIRED_RUNTIME_SERVICES),
            'status': 'STAGED_SIGNED_INPUT_CLAIMS_BOUND_ORIGINAL_RUNTIME_GUARDS_PENDING'}
        body.update({name: False for name in ('qualification_or_execution_authority', 'provider_registration_performed',
            'runtime_guards_performed', 'runtime_probe_performed', 'full_checkpoint_validation_performed', 'numerical_step_performed',
            'retry_or_continuation_authority')})
        return encode({'request': body, 'request_sha256': digest(body)})


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='untrusted-campaign-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'run'
        self.plan, self.pin = plan_fixture()
        self.limits = campaign.CampaignLimits(10, 10000, 64*1024*1024, 750, 4*1024*1024,
                                               64*1024*1024, 1024*1024*1024, False)

    def program(self, provider=None, source=None, **kwargs):
        provider = FakeProvider() if provider is None else provider
        return campaign.CampaignProgram(self.plan, expected_plan_sha256=self.pin,
            expected_provider_sha256=provider.implementation_sha256, provider=provider,
            request_source=RequestSource(self.plan) if source is None else source,
            output_root=self.root, limits=self.limits, **kwargs)

    def test_seven_cells_real_storage_and_reduction(self):
        provider, source = FakeProvider(), RequestSource(self.plan)
        program = self.program(provider, source)
        result = program.run()
        self.assertEqual(result.status, 'numerically_completed')
        self.assertEqual(len(provider.calls), 7)
        self.assertEqual([c[0] for c in source.calls], list(journal.POLICIES))
        self.assertTrue(all(c[1]['checkpoint']['tick'] == 0 for c in provider.calls))
        report = decode(result.report_raw, 4*1024*1024)
        self.assertTrue(report['coverage']['all_raw_cells_comparable'])
        self.assertFalse(report['qualification_or_execution_authority'])
        self.assertIsNone(report['awards']['overall_winner'])
        saved = read_field_archive(self.root/'field-packets', expected_archive_sha256=result.archive_sha256,
                                  maximum_archive_bytes=self.limits.archive_maximum_bytes)
        self.assertEqual(saved.snapshot, result.field_snapshot)
        self.assertEqual(len(list((self.root/'packets').iterdir())), 7)
        with self.assertRaises(ValueError):
            program.run()
        self.assertEqual(program.snapshot()['status'], 'numerically_completed')

    def test_running_parent_is_used_and_feed_exhaustion_pauses(self):
        provider = FakeProvider(statuses=('running',))
        result = self.program(provider, RequestSource(self.plan, count=2)).run()
        self.assertEqual([call[1]['checkpoint']['tick'] for call in provider.calls], [0, 1])
        self.assertEqual(result.field_snapshot.accepted_ticks, 2)
        self.assertEqual(result.status, 'request_source_exhausted')
        exported = decode(result.cell_exports[0][1].bundle_raw, 64*1024*1024)
        self.assertEqual(exported['bundle']['terminal']['terminal']['status'], 'paused_budget')

    def test_invalid_zero_tick_is_failed_not_retried(self):
        provider = FakeProvider(statuses=('invalid',))
        result = self.program(provider).run()
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result.status, 'numerical_failure')
        self.assertEqual(result.field_snapshot.accepted_ticks, 0)
        report = decode(result.report_raw, 4*1024*1024)
        self.assertEqual(len(report['coverage']['missing_policy_ids']), 6)
        self.assertIsNone(report['descriptive_raw_orders'])

    def test_cancel_before_start_has_no_dispatch(self):
        event = Event()
        event.set()
        provider = FakeProvider()
        result = self.program(provider, cancel_event=event).run()
        self.assertEqual(result.status, 'cancelled_between_chunks')
        self.assertFalse(provider.calls)
        self.assertFalse(result.cell_exports)

    def test_cancel_during_chunk_stops_after_return_and_persistence(self):
        event = Event()
        provider = FakeProvider(statuses=('running',), cancel=event)
        result = self.program(provider, cancel_event=event).run()
        self.assertEqual(len(provider.calls), 1)
        self.assertTrue((self.root/'packets'/'000001'/'owned-receipts.bin').is_file())
        exported = decode(result.cell_exports[0][1].bundle_raw, 64*1024*1024)
        self.assertEqual(exported['bundle']['terminal']['terminal']['status'], 'cancelled')

    def test_provider_error_is_same_and_no_post_failure_finalization(self):
        error = RuntimeError('UNTRUSTED provider error')
        program = self.program(FakeProvider(fail=error))
        with self.assertRaises(RuntimeError) as raised:
            program.run()
        self.assertIs(raised.exception, error)
        self.assertFalse((self.root/'outcome.json').exists())
        self.assertFalse((self.root/'field-packets').exists())
        self.assertTrue((self.root/'packets'/'000001'/'request.json').exists())
        self.assertEqual(program.snapshot()['field'].unresolved_dispatches, 1)

    def test_append_failure_retains_packet_and_stops(self):
        provider = FakeProvider()
        error = OSError('UNTRUSTED storage interruption')
        program = self.program(provider)
        with patch.object(journal.RawJournal, 'append', side_effect=error):
            with self.assertRaises(OSError) as raised:
                program.run()
        self.assertIs(raised.exception, error)
        self.assertEqual(len(provider.calls), 1)
        self.assertTrue((self.root/'packets'/'000001'/'checkpoint.json').exists())
        self.assertFalse(program.snapshot()['persisted_checkpoint_pins'])
        self.assertFalse((self.root/'outcome.json').exists())

    def test_no_available_provider_refused_before_files(self):
        with self.assertRaises(ValueError):
            campaign.CampaignProgram(self.plan, expected_plan_sha256=self.pin, expected_provider_sha256=pin('none'),
                provider=None, request_source=RequestSource(self.plan), output_root=self.root, limits=self.limits)
        self.assertFalse(self.root.exists())

    def test_existing_output_never_reused(self):
        self.root.mkdir()
        (self.root/'keep').write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            self.program().run()
        self.assertEqual((self.root/'keep').read_bytes(), b'keep')

    def test_tiny_file_cap_refused_before_cancelled_or_normal_output(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                event = Event()
                if cancelled:
                    event.set()
                self.limits = replace(self.limits, campaign_maximum_file_bytes=1)
                with self.assertRaises(ValueError):
                    self.program(cancel_event=event)
                self.assertFalse(self.root.exists())

    def test_tiny_archive_cap_refused_before_output(self):
        self.limits = replace(self.limits, archive_maximum_bytes=1)
        with self.assertRaises(ValueError):
            self.program()
        self.assertFalse(self.root.exists())

    def test_cancel_while_staging_does_not_dispatch(self):
        event, provider = Event(), FakeProvider()
        original = campaign._write_raw
        def staging(path, *args):
            value = original(path, *args)
            if path.name == 'request.json':
                event.set()
            return value
        with patch.object(campaign, '_write_raw', side_effect=staging):
            result = self.program(provider, cancel_event=event).run()
        self.assertFalse(provider.calls)
        self.assertEqual(len(result.field_snapshot.attempts), 0)
        self.assertTrue((self.root/'packets'/'000001'/'request.json').is_file())
        self.assertFalse((self.root/'packets'/'000001'/'packet.json').exists())

    def test_packet_parent_sync_requested_before_dispatch(self):
        with patch.object(journal, '_sync_directory', wraps=journal._sync_directory) as sync:
            self.program(FakeProvider(statuses=('invalid',))).run()
        sync.assert_any_call(self.root/'packets', False)

    def test_record_quota_pauses_without_retry_or_reset(self):
        self.limits = replace(self.limits, journal_maximum_records=1)
        provider = FakeProvider(statuses=('running',))
        result = self.program(provider).run()
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result.status, 'paused_budget')
        self.assertEqual(result.field_snapshot.accepted_ticks, 1)

    def test_source_cancel_and_exhaustion_close_running_journal_as_cancelled(self):
        event, provider = Event(), FakeProvider(statuses=('running',))
        source = RequestSource(self.plan, count=1)
        def stopping_source(*args, **kwargs):
            value = source(*args, **kwargs)
            if value is None:
                event.set()
            return value
        program = self.program(provider, stopping_source, cancel_event=event)
        result = program.run()
        self.assertEqual(result.status, 'cancelled_between_chunks')
        self.assertTrue(result.cancel_requested)
        self.assertTrue(program.snapshot()['cancel_requested'])
        self.assertEqual(len(provider.calls), 1)
        exported = decode(result.cell_exports[0][1].bundle_raw, 64*1024*1024)
        self.assertEqual(exported['bundle']['terminal']['terminal']['status'], 'cancelled')
        self.assertEqual(result.field_snapshot.accepted_ticks, 1)
        self.assertTrue(result.persisted_checkpoint_pins)
        self.assertTrue((self.root/'packets'/'000001'/'owned-receipts.bin').is_file())
        self.assertIsNone(decode(result.report_raw, 4*1024*1024)['descriptive_raw_orders'])
        exported = result.cell_exports[0][1]
        with patch.object(continuation, 'validate_staged_request') as validate:
            with self.assertRaisesRegex(ValueError, 'no terminal state revival'):
                continuation.prepare_continuation_request(exported.bundle_raw, b'{}', b'UNTRUSTED history only',
                    expected_bundle_sha256=exported.bundle_sha256,
                    expected_manifest_sha256=exported.manifest_sha256, lineage_id=pin('no-cancelled-revival'))
        validate.assert_not_called()

    def test_cancel_from_empty_initial_source_is_not_reported_as_feed_exhaustion(self):
        event, provider = Event(), FakeProvider()
        def stopping_source(*args, **kwargs):
            event.set()
            return None
        result = self.program(provider, stopping_source, cancel_event=event).run()
        self.assertEqual(result.status, 'cancelled_between_chunks')
        self.assertTrue(result.cancel_requested)
        self.assertFalse(provider.calls)
        self.assertFalse(result.cell_exports)

    def test_cancel_observed_after_budget_pause_is_classified_before_export(self):
        event, provider = Event(), FakeProvider(statuses=('running',))
        program = self.program(provider, cancel_event=event)
        original = program._room
        def room(snapshot, store):
            if store is not None:
                event.set()
                return False
            return original(snapshot, store)
        with patch.object(program, '_room', side_effect=room):
            result = program.run()
        self.assertEqual(result.status, 'cancelled_between_chunks')
        self.assertTrue(result.cancel_requested)
        exported = decode(result.cell_exports[0][1].bundle_raw, 64*1024*1024)
        self.assertEqual(exported['bundle']['terminal']['terminal']['status'], 'cancelled')
        self.assertEqual(len(provider.calls), 1)

    def test_late_cancel_during_outcome_publication_cannot_change_frozen_result(self):
        event, provider = Event(), FakeProvider()
        program = self.program(provider, RequestSource(self.plan, count=0), cancel_event=event)
        original = journal._write_new
        def write(path, value, *args):
            result = original(path, value, *args)
            if path.name == 'outcome.json':
                event.set()
            return result
        with patch.object(journal, '_write_new', side_effect=write):
            result = program.run()
        outcome = decode((self.root/'outcome.json').read_bytes(), campaign.MAX_CONTROL_BYTES)
        self.assertTrue(event.is_set())
        self.assertFalse(outcome['cancel_requested'])
        self.assertEqual(result.cancel_requested, outcome['cancel_requested'])
        self.assertEqual(program.snapshot()['cancel_requested'], outcome['cancel_requested'])
        self.assertEqual(result.status, outcome['status'])
        self.assertEqual(result.status, 'request_source_exhausted')
        self.assertFalse(provider.calls)
        event.clear()
        before = program.snapshot()
        event.set()
        self.assertEqual(program.snapshot(), before)

    def test_returned_numerical_terminal_keeps_priority_over_requested_stop(self):
        for status in ('invalid', 'completed'):
            with self.subTest(status=status):
                self.root = self.root.parent / (status + '-run')
                event = Event()
                provider = FakeProvider(statuses=(status,))
                original = provider.execute_owned_request
                def execute(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if status == 'invalid' or len(provider.calls) == 7:
                        event.set()
                    return result
                with patch.object(provider, 'execute_owned_request', side_effect=execute):
                    program = self.program(provider, cancel_event=event)
                    result = program.run()
                self.assertEqual(result.status, 'numerical_failure' if status == 'invalid' else 'numerically_completed')
                self.assertTrue(result.cancel_requested)
                self.assertTrue(program.snapshot()['cancel_requested'])
                self.assertEqual(len(provider.calls), 1 if status == 'invalid' else 7)

    def test_source_exception_with_pending_cancel_stays_unfinalized_and_is_same(self):
        event = Event()
        error = KeyboardInterrupt('UNTRUSTED request-source interruption')
        def interrupted_source(*args, **kwargs):
            event.set()
            raise error
        program = self.program(source=interrupted_source, cancel_event=event)
        with self.assertRaises(KeyboardInterrupt) as raised:
            program.run()
        self.assertIs(raised.exception, error)
        self.assertEqual(program.snapshot()['status'], 'failed_unfinalized_at_obtain_fresh_request')
        self.assertIsNone(program.snapshot()['cancel_requested'])
        self.assertFalse((self.root/'outcome.json').exists())
        self.assertFalse((self.root/'field-packets').exists())
        self.assertFalse(program.snapshot()['field'].attempts)

    def test_partial_receipt_requires_reconciliation_and_cannot_restart_or_reappend(self):
        provider = FakeProvider(statuses=('running',))
        program = self.program(provider)
        original = journal._write_new
        error = OSError('UNTRUSTED interrupted storage commit')
        def write(path, value, *args):
            if path.parent.name == 'records' and path.name == '000001.json':
                with path.open('xb') as stream:
                    stream.write(b'{')
                raise error
            return original(path, value, *args)
        with patch.object(journal, '_write_new', side_effect=write):
            with self.assertRaises(OSError) as raised:
                program.run()
        self.assertIs(raised.exception, error)
        snapshot = program.snapshot()
        self.assertEqual(snapshot['status'], 'failed_unfinalized_at_append_and_verify_journal')
        self.assertEqual(snapshot['field'].accepted_ticks, 1)
        self.assertFalse(snapshot['persisted_checkpoint_pins'])
        attempt = snapshot['field'].attempts[0]
        manifest_pin = digest(decode((self.root/'cells'/attempt.policy_id/'manifest.json').read_bytes(), journal.MAX_MANIFEST))
        store = journal.RawJournal(self.root/'cells'/attempt.policy_id, manifest_pin)
        state = store.inspect()
        self.assertTrue(state['reconciliation_required'])
        self.assertEqual(state['journal_committed_tail']['records'], 0)
        self.assertIsNone(state['terminal'])
        self.assertTrue((self.root/'packets'/'000001'/'checkpoint.json').is_file())
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            store.append(decode(attempt.result.raw_chunk_json, journal.MAX_CHUNK),
                         decode(attempt.result.linked_checkpoint_json, journal.MAX_CHECKPOINT))
        with self.assertRaisesRegex(ValueError, 'no restart/retry'):
            program.run()
        with self.assertRaises(FileExistsError):
            self.program().run()
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(len(provider.calls), 1)
        self.assertFalse((self.root/'outcome.json').exists())


if __name__ == '__main__':
    unittest.main()
