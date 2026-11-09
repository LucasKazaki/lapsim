"""Terminal DATA codec tests; evidence and native calls are untrusted doubles."""
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

import test_light_tournament_session as fixtures
from lapsim.tournament import terminal
from lapsim.tournament.session import HostUpdate
from lapsim_light_campaign.input_contracts import decode, digest, encode


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.SessionTests(methodName="test_real_first_cell_storage_preserves_six_unrun")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        _, self.output = self.case.fresh_output()
        self.operation = self.case.operation
        self.case.controller.start(self.operation)
        self.update = self.case.terminal(self.output)

    def raw(self, update=None, failure=None):
        return terminal.encode_terminal_record(self.operation, self.update if update is None else update, failure=failure)

    def read(self, raw, operation=None):
        return terminal.decode_terminal_record(raw, operation=self.operation if operation is None else operation,
            expected_raw_sha256=sha256(raw).hexdigest())

    def changed(self, mutate):
        envelope = decode(self.raw(), terminal.MAX_TERMINAL_BYTES)
        mutate(envelope["terminal_record"])
        envelope["record_sha256"] = digest(envelope["terminal_record"])
        return encode(envelope)

    def test_round_trip_preserves_exact_original_bytes_and_data_only_status(self):
        raw = self.raw()
        result = self.read(raw)
        self.assertEqual(result.raw, raw)
        self.assertEqual(result.update, self.update)
        self.assertEqual(result.update.terminal_evidence_raw, self.update.terminal_evidence_raw)
        self.assertEqual(result.update.output.bundle_raw, self.output.bundle_raw)
        self.assertFalse(result.qualification_or_execution_authority)
        self.assertIsNone(result.failure)

    def test_structured_failure_remains_data_never_imports_exception(self):
        update = replace(self.update, outcome="failed", output=None, paused_continuation_eligible=False)
        failure = terminal.SessionFailureData("original_owned_dispatch", "execution", "fake_package.FatalCreatorExit",
            "UNTRUSTED diagnostic string, not an exception", self.operation.output_root)
        result = self.read(self.raw(update, failure))
        self.assertEqual(result.failure, failure)
        self.assertEqual(result.update.outcome, "failed")
        self.assertIsNone(result.update.output)
        self.assertFalse(result.qualification_or_execution_authority)

    def test_failed_terminal_requires_structured_failure(self):
        with self.assertRaisesRegex(ValueError, "exact failure"):
            self.raw(replace(self.update, outcome="failed", output=None, paused_continuation_eligible=False))

    def test_returned_terminal_cannot_carry_failure(self):
        failure = terminal.SessionFailureData("stage", "execution", "ValueError", "UNTRUSTED", self.operation.output_root)
        with self.assertRaisesRegex(ValueError, "other outcomes"):
            self.raw(failure=failure)

    def test_returned_raw_numerical_failure_is_distinct_from_host_failure(self):
        operation = replace(self.operation, output_root=str(self.case.root/"raw-invalid"))
        _, output = self.case.fresh_output(operation, fixtures.fixtures.FakeProvider(statuses=("invalid",)))
        update = HostUpdate(operation.operation_sha256, 0, "terminal", 0, "returned", output,
            b"UNTRUSTED returned invalid numerical packet")
        raw = terminal.encode_terminal_record(operation, update)
        result = self.read(raw, operation)
        self.assertIsNone(result.failure)
        self.assertEqual(result.update.outcome, "returned")
        self.assertEqual(result.update.output.inspect(operation)["terminal"]["terminal"]["status"], "failed")

    def test_cancelled_terminal_preserves_outcome_without_invented_output(self):
        result = self.read(self.raw(replace(self.update, outcome="cancelled", output=None, paused_continuation_eligible=False)))
        self.assertEqual(result.update.outcome, "cancelled")
        self.assertIsNone(result.update.output)

    def test_missing_or_changed_original_evidence_refused(self):
        with self.assertRaisesRegex(ValueError, "complete immutable"):
            self.raw(replace(self.update, terminal_evidence_raw=b""))
        raw = self.changed(lambda body: body.update(original_evidence_b64="not base64!"))
        with self.assertRaisesRegex(ValueError, "Invalid base64"):
            self.read(raw)

    def test_changed_operation_rejected_even_with_recomputed_transport_hashes(self):
        changed = replace(self.operation, output_root=str(self.case.root/"another-operation"))
        with self.assertRaisesRegex(ValueError, "operation/sequence/outcome"):
            self.read(self.raw(), changed)

    def test_changed_runtime_output_identity_rejected(self):
        raw = self.changed(lambda body: body["output"].update(manifest_sha256=fixtures.pin("unrelated manifest")))
        with self.assertRaises(ValueError):
            self.read(raw)

    def test_wrong_expected_record_pin_and_internal_digest_refused(self):
        raw = self.raw()
        with self.assertRaisesRegex(ValueError, "pinned complete"):
            terminal.decode_terminal_record(raw, operation=self.operation, expected_raw_sha256=fixtures.pin("wrong raw pin"))
        value = decode(raw, terminal.MAX_TERMINAL_BYTES)
        value["record_sha256"] = fixtures.pin("wrong digest")
        with self.assertRaisesRegex(ValueError, "digest differs"):
            self.read(encode(value))

    def test_unknown_fields_and_false_authority_claim_refused(self):
        for mutate in (lambda body: body.update(unknown=1),
                       lambda body: body.update(qualification_or_execution_authority=True)):
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    self.read(self.changed(mutate))

    def test_duplicate_keys_noncanonical_json_and_noncanonical_base64_refused(self):
        raw = self.raw()
        for changed in (b' {"x":1}', raw.replace(b'{"record_sha256":', b'{"record_sha256":"duplicate","record_sha256":', 1)):
            with self.subTest(changed=changed[:100]):
                with self.assertRaises(ValueError):
                    self.read(changed)
        # Both forms decode to b'A'; only QQ== is canonical.
        with self.assertRaisesRegex(ValueError, "Canonical base64"):
            terminal._unraw("QR==", 1)

    def test_bounds_apply_before_decoding_and_aggregate_all_fields(self):
        with patch.object(terminal, "MAX_OWNED_RECEIPT_BYTES", 2):
            with self.assertRaises(ValueError):
                self.raw()
        raw = self.raw()
        with patch.object(terminal, "MAX_TERMINAL_BYTES", len(raw)-1):
            with self.assertRaisesRegex(ValueError, "transport bound"):
                self.raw()
            with self.assertRaisesRegex(ValueError, "pinned complete"):
                self.read(raw)

    def test_caller_supplied_matching_hash_does_not_authenticate_cleanup(self):
        forged = replace(self.update, terminal_evidence_raw=b"UNTRUSTED caller supplied fake cleanup receipt")
        data = self.read(self.raw(forged))  # Consistency succeeds; authority remains false.
        self.assertFalse(data.qualification_or_execution_authority)
        self.case.host.error = ValueError("UNTRUSTED verifier double rejects record without real native issuance")
        self.case.controller.handle.updates.append(data.update)
        with self.assertRaisesRegex(ValueError, "real native issuance"):
            self.case.controller.poll()
        self.assertFalse(self.case.controller.cleanup_verified)
        self.assertFalse(self.case.controller.can_close)
        self.assertFalse(self.case.controller.can_continue)

    def test_native_retained_record_correlation_can_refuse_caller_copy(self):
        data = self.read(self.raw())

        def correlate(operation, update):
            if update is not data.update:
                raise ValueError("UNTRUSTED host double: terminal was not this handle's issued object")
            return None  # No actual native authentication in this unit double.

        self.case.host.require_authenticated_terminal = correlate
        self.case.controller.handle.updates.append(replace(data.update))
        with self.assertRaisesRegex(ValueError, "issued object"):
            self.case.controller.poll()
        self.assertFalse(self.case.controller.cleanup_verified)
        self.case.controller.handle.updates.append(data.update)
        self.case.controller.poll()
        self.assertTrue(self.case.controller.can_continue)


if __name__ == "__main__":
    unittest.main()
