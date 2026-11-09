"""Real RAW/storage/controller tests with explicitly UNTRUSTED native doubles.

No numerical worker, original signature, lease, Windows Job, resource observer
or native cleanup is exercised. Temporary-directory results are unit fixtures.
"""
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from lapsim.tournament.session import (
    ContinuationExecution, ContinuationOperation, FreshExecution, FreshOperation,
    HostUpdate, SessionController,
    NativeSessionHost, SessionOutput,
)
from lapsim_light_campaign import raw_journal as journal
from lapsim_light_campaign.campaign import CampaignLimits
from lapsim_light_campaign.continuation import prepare_continuation_request
from lapsim_light_campaign.input_contracts import decode, digest, encode
from lapsim_light_campaign.raw_evidence import replay_raw_bundle, snapshot_raw_journal
from lapsim_light_campaign.tournament_results import RawCellExport, summarize_tournament


FIXTURE = Path(__file__).resolve().parents[1] / "research/light/portable-tournament-candidate/tests/test_campaign.py"
spec = importlib.util.spec_from_file_location("untrusted_light_session_fixtures", FIXTURE)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
pin = fixtures.pin


class UntrustedContinuationDouble(fixtures.FakeProvider):
    def execute_owned_continuation(self, request_raw, bundle_raw, historical_owned_receipts_raw, *, numerical_backend_family):
        request, bundle = decode(request_raw, 256*1024)["continuation"], decode(bundle_raw, 64*1024*1024)
        tail = replay_raw_bundle(bundle, expected_bundle_sha256=bundle["bundle_sha256"],
            expected_manifest_sha256=request["predecessor"]["manifest_sha256"])
        return super().execute_owned_request(encode(request["fresh_dispatch_request"]), encode(tail["checkpoint"]),
            numerical_backend_family=numerical_backend_family)

    def require_authenticated_continuation_and_cleanup(self, *args):
        return None  # Explicit no-auth double, never native evidence.


class UntrustedHandle:
    def __init__(self, operation):
        self.operation_sha256 = operation.operation_sha256
        self.updates, self.stops = [], []

    def poll(self):
        return self.updates.pop(0) if self.updates else None

    def request_stop(self, reason):
        self.stops.append(reason)


class UntrustedHost:
    implementation_sha256 = pin("session-host-not-native")

    def __init__(self):
        self.handles, self.verified, self.error = [], [], None

    def launch(self, operation):
        handle = UntrustedHandle(operation)
        self.handles.append(handle)
        return handle

    def require_authenticated_terminal(self, operation, update):
        if self.error:
            raise self.error
        self.verified.append((operation, update))
        return None  # Explicit no-auth double; not Windows cleanup proof.


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="UNTRUSTED-session-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan, self.plan_pin = fixtures.plan_fixture()
        self.source = fixtures.RequestSource(self.plan)
        first = decode(self.plan, 2*1024*1024)["plan"]["cells"][0]
        self.request = self.source(first["policy_id"], encode(first["origin"]), requested_ticks=10, remaining_requested_wall_time_ms=10000)
        self.provider = fixtures.FakeProvider(statuses=("running",))
        limits = CampaignLimits(10, 10000, 64*1024*1024, 750, 4*1024*1024, 64*1024*1024, 1024*1024*1024, False)
        self.operation = FreshOperation(self.plan, self.plan_pin, self.request, decode(self.request, 128*1024)["request_sha256"],
            self.provider.implementation_sha256, str(self.root / "first"), limits, 30.)
        self.host = UntrustedHost()
        self.now = [100.]
        self.controller = SessionController(self.host, expected_host_sha256=self.host.implementation_sha256, clock=lambda: self.now[0])

    def fresh_output(self, operation=None, provider=None, cancel=None):
        operation = self.operation if operation is None else operation
        execution = FreshExecution(operation, provider=self.provider if provider is None else provider,
            cancel_event=Event() if cancel is None else cancel)
        output = execution.run()
        return execution, output

    def child(self, output, previous=None, suffix="child", **kwargs):
        previous = self.operation if previous is None else previous
        parent = output.inspect(previous)
        policy = decode(self.plan, 2*1024*1024)["plan"]["cells"][0]["policy_id"]
        staged = decode(self.source(policy, encode(parent["checkpoint"]), requested_ticks=10, remaining_requested_wall_time_ms=10000), 128*1024)
        staged["request"]["request_nonce"] = pin("fresh-child-" + suffix)
        staged["request_sha256"] = digest(staged["request"])
        history = b"UNTRUSTED complete historical receipt transport fixture, no signature"
        outer = prepare_continuation_request(output.bundle_raw, encode(staged), history,
            expected_bundle_sha256=output.bundle_sha256, expected_manifest_sha256=output.manifest_sha256, lineage_id=pin(suffix))
        return ContinuationOperation(previous, output, encode(outer), outer["continuation_sha256"], history,
            self.provider.implementation_sha256, str(self.root / suffix), 30., 750, 4*1024*1024, False, **kwargs)

    def terminal(self, output, *, outcome="returned", sequence=1, ticks=1):
        return HostUpdate(self.controller.operation.operation_sha256, sequence, "terminal", ticks, outcome,
            output, b"UNTRUSTED terminal/cleanup double")

    def adopt(self, output, operation=None):
        self.controller.start(self.operation if operation is None else operation)
        self.host.handles[-1].updates.append(self.terminal(output))
        self.controller.poll()

    def test_real_first_cell_storage_preserves_six_unrun(self):
        execution, output = self.fresh_output()
        tail = output.inspect(self.operation)
        self.assertEqual(tail["records"], 1)
        self.assertEqual(tail["terminal"]["terminal"]["status"], "paused_budget")
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(execution.snapshot()["status"], "request_source_exhausted")
        report = decode(output.report_raw, 4*1024*1024)
        self.assertEqual(len(report["coverage"]["missing_policy_ids"]), 6)
        self.assertIsNone(report["awards"]["overall_winner"])
        with self.assertRaises(ValueError):
            execution.run()

    def test_request_identity_edit_rejected_before_output_or_provider(self):
        staged = decode(self.request, 128*1024)
        staged["request"]["identity"]["environment_sha256"] = pin("changed-env")
        staged["request_sha256"] = digest(staged["request"])
        changed = replace(self.operation, request_raw=encode(staged), request_sha256=staged["request_sha256"])
        with self.assertRaises(ValueError):
            FreshExecution(changed, provider=self.provider, cancel_event=Event())
        self.assertFalse(Path(changed.output_root).exists())
        self.assertFalse(self.provider.calls)

    def test_real_continuation_copies_prefix_appends_one_and_reads_export(self):
        _, output = self.fresh_output()
        child = self.child(output)
        provider = UntrustedContinuationDouble(statuses=("running",))
        admission = b"UNTRUSTED outer admission bytes; not authority"
        execution = ContinuationExecution(child, provider=provider, owned_admission_raw=admission,
            owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event())
        result = execution.run()
        tail = result.inspect(child)
        self.assertEqual(tail["records"], 2)
        self.assertEqual(tail["checkpoint"]["checkpoint"]["tick"], 2)
        self.assertEqual(tail["terminal"]["terminal"]["status"], "paused_budget")
        self.assertEqual({p.name for p in (Path(child.output_root)/"child").iterdir()}, {"ancestry.json", "owned-admission.bin", "journal"})
        self.assertTrue((Path(child.output_root)/"export.json").is_file())
        self.assertEqual(len(provider.calls), 1)
        with self.assertRaises(ValueError):
            execution.run()

    def test_append_failure_retains_returned_packet_and_no_export_or_retry(self):
        _, output = self.fresh_output()
        child, admission = self.child(output), b"UNTRUSTED outer admission"
        provider = UntrustedContinuationDouble(statuses=("running",))
        execution = ContinuationExecution(child, provider=provider, owned_admission_raw=admission,
            owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event())
        original = journal.RawJournal.append
        calls = [0]

        def fail_new(store, *args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("unit-injected new-tail failure")
            return original(store, *args, **kwargs)

        with patch.object(journal.RawJournal, "append", fail_new):
            with self.assertRaises(OSError):
                execution.run()
        self.assertTrue((Path(child.output_root)/"owned-receipts.bin").is_file())
        self.assertFalse((Path(child.output_root)/"export.json").exists())
        with self.assertRaises(ValueError):
            execution.run()
        self.assertEqual(len(provider.calls), 1)

    def test_cancel_before_start_never_dispatches(self):
        event = Event()
        event.set()
        execution, output = self.fresh_output(cancel=event)
        self.assertIsNone(output)
        self.assertEqual(execution.snapshot()["status"], "cancelled_between_chunks")
        self.assertFalse(self.provider.calls)

    def test_no_native_host_fails_closed(self):
        with self.assertRaises(ValueError):
            SessionController(None, expected_host_sha256=pin("absent"))

    def test_start_progress_terminal_enables_only_explicit_paused_continue(self):
        _, output = self.fresh_output()
        self.controller.start(self.operation)
        self.assertTrue(self.controller.active)
        handle = self.host.handles[-1]
        handle.updates.append(HostUpdate(self.operation.operation_sha256, 0, "running", 1))
        self.controller.poll()
        self.assertEqual(self.controller.state, "running")
        self.assertFalse(self.controller.can_continue)
        handle.updates.append(self.terminal(output))
        self.controller.poll()
        self.assertTrue(self.controller.can_continue)
        self.assertTrue(self.controller.cleanup_verified)
        self.assertEqual(self.controller.state, "paused")
        self.controller.start(self.child(output))
        self.assertEqual(len(self.host.handles), 2)

    def test_stop_is_sticky_until_authenticated_cleanup(self):
        _, output = self.fresh_output()
        self.controller.start(self.operation)
        handle = self.host.handles[-1]
        self.controller.stop()
        self.controller.stop()
        self.assertEqual(handle.stops, ["user_stop"])
        self.assertFalse(self.controller.can_close)
        self.assertFalse(self.controller.can_continue)
        handle.updates.append(self.terminal(output))
        self.controller.poll()
        self.assertEqual(self.controller.state, "paused")  # Actual result retained; Stop still bars Continue.
        self.assertEqual(self.controller.stop_requested, "user_stop")
        self.assertFalse(self.controller.can_continue)
        with self.assertRaises(ValueError):
            self.controller.start(self.child(output))

    def test_timeout_requests_stop_once_and_never_proves_cleanup(self):
        self.controller.start(self.operation)
        self.now[0] += 31.
        self.controller.poll()
        self.controller.poll()
        self.assertEqual(self.host.handles[-1].stops, ["timeout"])
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.can_close)
        self.host.handles[-1].updates.append(self.terminal(None, outcome="timed_out", ticks=0))
        self.controller.poll()
        self.assertEqual(self.controller.state, "timed_out")
        self.assertTrue(self.controller.can_close)

    def test_close_waits_for_cleanup_and_blocks_later_work(self):
        self.controller.start(self.operation)
        self.assertFalse(self.controller.close())
        self.assertEqual(self.host.handles[-1].stops, ["window_close"])
        self.host.handles[-1].updates.append(self.terminal(None, outcome="cancelled", ticks=0))
        self.controller.poll()
        self.assertTrue(self.controller.can_close)
        with self.assertRaises(ValueError):
            self.controller.start(self.operation)

    def test_cleanup_verifier_failure_keeps_blocked_active_handle(self):
        _, output = self.fresh_output()
        self.controller.start(self.operation)
        self.host.error = ValueError("unit cleanup authentication refusal")
        self.host.handles[-1].updates.append(self.terminal(output))
        with self.assertRaises(ValueError):
            self.controller.poll()
        self.assertEqual(self.controller.state, "blocked")
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.can_close)

    def test_failed_terminal_cannot_resume_paused_bytes(self):
        _, output = self.fresh_output()
        self.controller.start(self.operation)
        self.host.handles[-1].updates.append(self.terminal(output, outcome="failed"))
        self.controller.poll()
        self.assertEqual(self.controller.state, "failed")
        self.assertFalse(self.controller.can_continue)
        with self.assertRaises(ValueError):
            self.controller.start(self.child(output))

    def test_stale_operation_and_old_sequence_cannot_finish_current(self):
        self.controller.start(self.operation)
        handle = self.host.handles[-1]
        handle.updates.extend([HostUpdate(pin("old-op"), 999, "terminal", 0, "cancelled", None, b"UNTRUSTED"),
            HostUpdate(self.operation.operation_sha256, 2, "running", 1),
            HostUpdate(self.operation.operation_sha256, 1, "terminal", 1, "cancelled", None, b"UNTRUSTED")])
        for _ in range(3):
            self.controller.poll()
        self.assertTrue(self.controller.active)
        self.assertEqual(self.controller.state, "running")
        self.assertFalse(self.host.verified)

    def test_consumed_request_nonce_cannot_be_replayed_in_new_namespace(self):
        self.controller.start(self.operation)
        self.host.handles[-1].updates.append(self.terminal(None, outcome="cancelled", ticks=0))
        self.controller.poll()
        with self.assertRaises(ValueError):
            self.controller.start(replace(self.operation, output_root=str(self.root / "retry")))

    def test_unknown_launch_exception_propagates_and_no_implicit_retry(self):
        class FatalOwnerExit(BaseException):
            pass
        with patch.object(self.host, "launch", side_effect=FatalOwnerExit("unit fatal")):
            with self.assertRaises(FatalOwnerExit):
                self.controller.start(self.operation)
        self.assertEqual(self.controller.state, "blocked")
        self.assertFalse(self.controller.can_close)
        with self.assertRaises(ValueError):
            self.controller.start(self.operation)

    def test_inherited_native_verifier_placeholder_rejected(self):
        class IncompleteHost(NativeSessionHost):
            implementation_sha256 = pin("incomplete-host")

            def launch(self, operation):
                return UntrustedHandle(operation)

        # Bypass ABC instantiation only to exercise inherited-method refusal.
        IncompleteHost.__abstractmethods__ = frozenset()
        with self.assertRaisesRegex(ValueError, "placeholder"):
            SessionController(IncompleteHost(), expected_host_sha256=IncompleteHost.implementation_sha256)

    def test_cancel_during_request_staging_preserves_zero_attempt_outcome(self):
        from lapsim_light_campaign import campaign
        event, original = Event(), campaign._write_raw

        def staging(path, *args):
            original(path, *args)
            if path.name == "request.json":
                event.set()

        with patch.object(campaign, "_write_raw", side_effect=staging):
            execution, output = self.fresh_output(cancel=event)
        self.assertIsNone(output)
        self.assertFalse(self.provider.calls)
        self.assertEqual(execution.snapshot()["status"], "cancelled_between_chunks")
        self.assertTrue((Path(self.operation.output_root)/"packets"/"000001"/"request.json").is_file())

    def test_failed_resume_launch_clears_prior_handle_and_never_stops_it(self):
        _, output = self.fresh_output()
        self.adopt(output)
        old_handle = self.controller.handle
        with patch.object(self.host, "launch", side_effect=RuntimeError("unit uncertain creation")):
            with self.assertRaises(RuntimeError):
                self.controller.start(self.child(output))
        self.assertIsNone(self.controller.handle)
        self.controller.stop()
        self.controller.poll()
        self.assertFalse(old_handle.stops)
        self.assertTrue(self.controller.active)
        self.assertFalse(self.controller.can_close)

    def test_wrong_operation_handle_is_not_installed(self):
        wrong = UntrustedHandle(replace(self.operation, output_root=str(self.root/"wrong")))
        with patch.object(self.host, "launch", return_value=wrong):
            with self.assertRaises(ValueError):
                self.controller.start(self.operation)
        self.assertIsNone(self.controller.handle)
        self.controller.stop()
        self.assertFalse(wrong.stops)

    def test_malformed_status_does_not_poison_later_terminal(self):
        _, output = self.fresh_output()
        self.controller.start(self.operation)
        handle = self.controller.handle
        handle.updates.append(HostUpdate(self.operation.operation_sha256, 100, "running", 10, output=output))
        with self.assertRaises(ValueError):
            self.controller.poll()
        self.assertEqual(self.controller.progress_ticks, 0)
        handle.updates.append(self.terminal(output, sequence=1))
        self.controller.poll()
        self.assertEqual(self.controller.state, "paused")
        self.assertTrue(self.controller.cleanup_verified)

    def test_arbitrary_output_object_is_not_invoked(self):
        class Payload:
            def inspect(self, operation):
                self.fail = True
                raise AssertionError("must not invoke unknown output")

        self.controller.start(self.operation)
        self.controller.handle.updates.append(self.terminal(Payload()))
        with self.assertRaisesRegex(ValueError, "Exact immutable"):
            self.controller.poll()
        self.assertFalse(self.controller.cleanup_verified)
        self.assertFalse(self.host.verified)

    def test_failure_and_completion_take_priority_over_pending_stop(self):
        for status in ("invalid", "completed"):
            with self.subTest(status=status):
                operation = replace(self.operation, output_root=str(self.root/status))
                _, output = self.fresh_output(operation, fixtures.FakeProvider(statuses=(status,)))
                host = UntrustedHost()
                controller = SessionController(host, expected_host_sha256=host.implementation_sha256, clock=lambda: self.now[0])
                controller.start(operation)
                controller.stop()
                host.handles[-1].updates.append(HostUpdate(operation.operation_sha256, 0, "terminal", 0 if status == "invalid" else 1,
                    "returned", output, b"UNTRUSTED terminal"))
                controller.poll()
                self.assertEqual(controller.state, "failed" if status == "invalid" else "completed")
                self.assertEqual(controller.stop_requested, "user_stop")
                self.assertFalse(controller.can_continue)

    def test_host_failure_not_relabelled_by_expired_ui_timer(self):
        self.controller.start(self.operation)
        self.now[0] += 31.
        self.controller.handle.updates.append(self.terminal(None, outcome="failed", ticks=0))
        self.controller.poll()
        self.assertEqual(self.controller.state, "failed")
        self.assertEqual(self.controller.stop_requested, "timeout")

    def test_missing_terminal_write_does_not_publish_export(self):
        _, output = self.fresh_output()
        child, admission = self.child(output), b"UNTRUSTED admission"
        execution = ContinuationExecution(child, provider=UntrustedContinuationDouble(statuses=("running",)),
            owned_admission_raw=admission, owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event())
        with patch.object(journal.RawJournal, "write_terminal", return_value=None):
            with self.assertRaisesRegex(ValueError, "terminal/checkpoint"):
                execution.run()
        self.assertFalse((Path(child.output_root)/"export.json").exists())
        self.assertFalse((Path(child.output_root)/"results.json").exists())

    def test_truncated_admission_readback_stops_before_provider(self):
        _, output = self.fresh_output()
        child, admission = self.child(output), b"UNTRUSTED admission"
        provider = UntrustedContinuationDouble(statuses=("running",))
        execution = ContinuationExecution(child, provider=provider, owned_admission_raw=admission,
            owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event())
        from lapsim.tournament import session
        original = session.copy_raw_prefix_in_owned_worker

        def torn(*args, **kwargs):
            result = original(*args, **kwargs)
            (Path(result["root"])/"owned-admission.bin").write_bytes(admission[:-1])
            return result

        with patch.object(session, "copy_raw_prefix_in_owned_worker", side_effect=torn):
            with self.assertRaisesRegex(ValueError, "admission bytes differ"):
                execution.run()
        self.assertFalse(provider.calls)

    def test_output_quota_drift_rejected(self):
        other = replace(self.operation, limits=replace(self.operation.limits, journal_maximum_records=749))
        _, output = self.fresh_output(other)
        with self.assertRaisesRegex(ValueError, "bounds/sync"):
            replace(output, operation_sha256=self.operation.operation_sha256).inspect(self.operation)

    def test_nested_continuation_namespace_refused_before_mutating_parent(self):
        _, output = self.fresh_output()
        child = self.child(output)
        changed = replace(child, output_root=str(Path(self.operation.output_root)/"cells"/"new-child"))
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        with self.assertRaisesRegex(ValueError, "new canonical"):
            changed.validate()
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_new_fresh_start_cannot_create_under_previous_output(self):
        self.controller.start(self.operation)
        self.controller.handle.updates.append(self.terminal(None, outcome="cancelled", ticks=0))
        self.controller.poll()
        staged = decode(self.request, 128*1024)
        staged["request"]["request_nonce"] = pin("new-fresh-nonce")
        staged["request_sha256"] = digest(staged["request"])
        changed = replace(self.operation, request_raw=encode(staged), request_sha256=staged["request_sha256"],
            output_root=str(Path(self.operation.output_root)/"nested"))
        with self.assertRaisesRegex(ValueError, "namespace"):
            self.controller.start(changed)
        self.assertEqual(len(self.host.handles), 1)

    def test_completed_and_cancelled_raw_predecessors_cannot_continue(self):
        for status in ("completed", "cancelled"):
            with self.subTest(status=status):
                event = Event()
                provider = fixtures.FakeProvider(statuses=("completed" if status == "completed" else "running",),
                    cancel=None if status == "completed" else event)
                operation = replace(self.operation, output_root=str(self.root/status))
                _, output = self.fresh_output(operation, provider, event)
                with self.assertRaisesRegex(ValueError, "no terminal state revival|checkpoint is terminal"):
                    self.child(output, operation, "refused-"+status)

    def test_no_room_for_first_packet_refused_before_native_launch(self):
        changed = replace(self.operation, limits=replace(self.operation.limits, maximum_retained_history_payload_bytes=1))
        with self.assertRaisesRegex(ValueError, "reserve one complete"):
            self.controller.start(changed)
        self.assertFalse(self.host.handles)
        self.assertFalse(Path(changed.output_root).exists())

    def test_child_namespace_cannot_overlap_grandparent(self):
        _, output = self.fresh_output()
        child, admission = self.child(output), b"UNTRUSTED admission"
        continued = ContinuationExecution(child, provider=UntrustedContinuationDouble(statuses=("running",)),
            owned_admission_raw=admission, owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event()).run()
        grandchild = self.child(continued, child, "grandchild")
        changed = replace(grandchild, output_root=str(Path(self.operation.output_root)/"ancestor-child"))
        with self.assertRaisesRegex(ValueError, "ancestor namespace"):
            changed.validate()
        self.assertFalse(Path(changed.output_root).exists())

    def test_unknown_predecessor_object_never_invoked(self):
        _, output = self.fresh_output()
        child = self.child(output)

        class Payload:
            def inspect(self, operation):
                raise AssertionError("unknown predecessor must not execute")

        with self.assertRaisesRegex(ValueError, "Exact immutable predecessor"):
            replace(child, predecessor=Payload()).validate()

    def test_coherent_raw_journal_exceeding_staged_ticks_is_rejected(self):
        first = decode(self.plan, 2*1024*1024)["plan"]["cells"][0]
        source = fixtures.RequestSource(self.plan)
        request = source(first["policy_id"], encode(first["origin"]), requested_ticks=1, remaining_requested_wall_time_ms=10000)
        operation = replace(self.operation, request_raw=request, request_sha256=decode(request, 128*1024)["request_sha256"],
            limits=replace(self.operation.limits, chunk_ticks=1))
        provider = fixtures.FakeProvider(statuses=("running",))
        first_packet = provider.execute_owned_request(request, encode(first["origin"]), numerical_backend_family="UNTRUSTED fixture")
        child_request = source(first["policy_id"], first_packet.linked_checkpoint_json, requested_ticks=1, remaining_requested_wall_time_ms=10000)
        second = provider.execute_owned_request(child_request, first_packet.linked_checkpoint_json, numerical_backend_family="UNTRUSTED fixture")
        # Rebuild a coherent single 0->2 RAW transition, exceeding the actual
        # reviewed 0->1 request but still inside the broader mission limit.
        chunk = decode(second.raw_chunk_json, journal.MAX_CHUNK)
        body = chunk["chunk"]
        body["start_tick"], body["input_checkpoint_sha256"], body["parent_chunk_sha256"] = 0, first["origin"]["checkpoint_sha256"], None
        body["output_checkpoint"]["checkpoint"]["parent_chunk_sha256"] = None
        body["output_checkpoint"]["checkpoint"]["segment"] = 1
        body["output_checkpoint"]["checkpoint_sha256"] = digest(body["output_checkpoint"]["checkpoint"])
        chunk["chunk_sha256"] = digest(body)
        linked = deepcopy(body["output_checkpoint"])
        linked["checkpoint"]["parent_chunk_sha256"] = chunk["chunk_sha256"]
        linked["checkpoint_sha256"] = digest(linked["checkpoint"])
        store = journal.RawJournal.create(self.root/"over-request", first["identity"], first["origin"],
            maximum_records=operation.limits.journal_maximum_records, maximum_bytes=operation.limits.journal_maximum_bytes, sync_files=False)
        store.append(chunk, linked)
        store.write_terminal("paused_budget", "UNTRUSTED over-request fixture")
        bundle = snapshot_raw_journal(store.root, expected_manifest_sha256=store.expected_manifest_sha256)
        raw = encode(bundle)
        report = encode(summarize_tournament(self.plan,
            {first["policy_id"]: RawCellExport(raw, bundle["bundle_sha256"], store.expected_manifest_sha256)}, expected_plan_sha256=self.plan_pin))
        output = SessionOutput(operation.operation_sha256, operation.output_root, raw, bundle["bundle_sha256"], store.expected_manifest_sha256, report)
        with self.assertRaisesRegex(ValueError, "exceeds reviewed tick request"):
            output.inspect(operation)

    def test_changed_continuation_environment_rejected_before_output(self):
        _, output = self.fresh_output()
        child = self.child(output)
        outer = decode(child.request_raw, 256*1024)
        inner = outer["continuation"]["fresh_dispatch_request"]
        inner["request"]["identity"]["environment_sha256"] = pin("different environment")
        inner["request_sha256"] = digest(inner["request"])
        outer["continuation_sha256"] = digest(outer["continuation"])
        changed = replace(child, request_raw=encode(outer), continuation_sha256=outer["continuation_sha256"])
        with self.assertRaises(ValueError):
            changed.validate()
        self.assertFalse(Path(child.output_root).exists())

    def test_continuation_identity_cost_does_not_revalidate_ancestors(self):
        _, output = self.fresh_output()
        previous, parent = self.operation, output
        admission = b"UNTRUSTED repeated-child fixture"
        for index in range(4):
            child = self.child(parent, previous, "chain-"+str(index))
            parent = ContinuationExecution(child, provider=UntrustedContinuationDouble(statuses=("running",)),
                owned_admission_raw=admission, owned_admission_sha256=sha256(admission).hexdigest(), cancel_event=Event()).run()
            previous = child
        with patch.object(FreshOperation, "validate", side_effect=AssertionError("No ancestor revalidation for identity")):
            for _ in range(10):
                self.assertEqual(previous.operation_sha256, previous._pin)
                self.assertEqual(previous.plan_sha256, self.plan_pin)
        self.assertEqual(previous._depth, 4)


if __name__ == "__main__":
    unittest.main()
