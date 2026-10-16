import json
import unittest

from can_tx_publication_evidence import (
    SCHEMA,
    TxEvidenceError,
    TxPublicationEvidence,
    TxRecord,
    classify_publication,
)


class TxPublicationEvidenceTests(unittest.TestCase):
    def test_empty_snapshot_has_no_authority(self):
        s = TxPublicationEvidence().snapshot()
        self.assertEqual(s.schema, SCHEMA)
        self.assertEqual(s.records, ())
        self.assertFalse(s.action_authority)
        self.assertTrue(s.descriptive_only)

    def test_intent_is_not_publication(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd-1")
        r = model.snapshot().records[0]
        self.assertEqual(r.state, "computed_not_enqueued")
        self.assertEqual(classify_publication(r), "intent_only")
        self.assertFalse(r.transmitted)

    def test_enqueue_acceptance_is_not_confirmation(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd-1")
        model.enqueue_accepted(1, 0)
        r = model.snapshot().records[0]
        self.assertEqual(r.state, "pending")
        self.assertEqual(classify_publication(r), "requested_not_confirmed")
        self.assertFalse(r.transmitted)

    def test_transmit_completion_is_separate_terminal_evidence(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd-1")
        model.enqueue_accepted(1, 0)
        model.complete(0, "transmitted")
        s = model.snapshot()
        self.assertEqual(s.transmitted_count, 1)
        self.assertEqual(s.latest_transmitted_seq, 1)
        self.assertEqual(classify_publication(s.records[0]), "transmit_confirmed")

    def test_no_free_mailbox_rejection_is_explicit(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd-1")
        model.enqueue_rejected(1, "no_free_mailbox")
        r = model.snapshot().records[0]
        self.assertEqual(r.state, "enqueue_rejected")
        self.assertEqual(r.enqueue_reason, "no_free_mailbox")
        self.assertEqual(classify_publication(r), "enqueue_failed")

    def test_all_supported_enqueue_rejections(self):
        for reason in ("no_free_mailbox", "not_ready", "parameter_error", "other"):
            model = TxPublicationEvidence()
            model.add_intent(1, "cmd")
            model.enqueue_rejected(1, reason)
            self.assertEqual(model.snapshot().records[0].enqueue_reason, reason)

    def test_arbitration_lost_is_failure(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd")
        model.enqueue_accepted(1, 0)
        model.complete(0, "arbitration_lost")
        r = model.snapshot().records[0]
        self.assertEqual(r.state, "tx_failed")
        self.assertEqual(classify_publication(r), "transmit_failed:arbitration_lost")

    def test_transmit_error_is_failure(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd")
        model.enqueue_accepted(1, 1)
        model.complete(1, "transmit_error")
        self.assertEqual(classify_publication(model.snapshot().records[0]), "transmit_failed:transmit_error")

    def test_abort_is_failure(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "cmd")
        model.enqueue_accepted(1, 2)
        model.complete(2, "aborted")
        self.assertEqual(classify_publication(model.snapshot().records[0]), "transmit_failed:aborted")

    def test_mailbox_cannot_hold_two_pending_records(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        model.add_intent(2, "b")
        model.enqueue_accepted(1, 0)
        with self.assertRaises(TxEvidenceError):
            model.enqueue_accepted(2, 0)

    def test_mailbox_can_be_reused_after_terminal_result(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        model.enqueue_accepted(1, 0)
        model.complete(0, "transmitted")
        model.add_intent(2, "b")
        model.enqueue_accepted(2, 0)
        self.assertEqual(model.snapshot().pending_mailboxes, ((0, 2),))

    def test_completion_without_pending_mailbox_rejected(self):
        with self.assertRaises(TxEvidenceError):
            TxPublicationEvidence().complete(0, "transmitted")

    def test_duplicate_sequence_rejected(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        with self.assertRaises(TxEvidenceError):
            model.add_intent(1, "again")

    def test_sequence_gap_rejected(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        with self.assertRaises(TxEvidenceError):
            model.add_intent(3, "gap")

    def test_zero_sequence_rejected(self):
        with self.assertRaises(TxEvidenceError):
            TxPublicationEvidence().add_intent(0, "zero")

    def test_blank_request_tag_rejected(self):
        with self.assertRaises(TxEvidenceError):
            TxPublicationEvidence().add_intent(1, "  ")

    def test_invalid_mailbox_rejected(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        with self.assertRaises(TxEvidenceError):
            model.enqueue_accepted(1, 3)

    def test_unknown_sequence_enqueue_rejected(self):
        with self.assertRaises(TxEvidenceError):
            TxPublicationEvidence().enqueue_accepted(1, 0)

    def test_invalid_terminal_result_rejected(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        model.enqueue_accepted(1, 0)
        with self.assertRaises(TxEvidenceError):
            model.complete(0, "delivered_to_inverter")

    def test_free_level_accepts_zero_through_three(self):
        model = TxPublicationEvidence()
        for value in range(4):
            model.observe_free_level(value)

    def test_free_level_out_of_range_rejected(self):
        model = TxPublicationEvidence()
        with self.assertRaises(TxEvidenceError):
            model.observe_free_level(4)
        with self.assertRaises(TxEvidenceError):
            model.observe_free_level(-1)

    def test_latest_intent_can_lead_latest_transmitted(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        model.enqueue_accepted(1, 0)
        model.complete(0, "transmitted")
        model.add_intent(2, "b")
        model.enqueue_accepted(2, 1)
        s = model.snapshot()
        self.assertEqual(s.latest_intent_seq, 2)
        self.assertEqual(s.latest_transmitted_seq, 1)
        self.assertEqual(s.pending_count, 1)

    def test_counts_distinguish_rejected_failed_pending_and_transmitted(self):
        model = TxPublicationEvidence()
        for seq in range(1, 5):
            model.add_intent(seq, f"cmd-{seq}")
        model.enqueue_accepted(1, 0)
        model.complete(0, "transmitted")
        model.enqueue_accepted(2, 1)
        model.complete(1, "transmit_error")
        model.enqueue_rejected(3, "not_ready")
        model.enqueue_accepted(4, 2)
        s = model.snapshot()
        self.assertEqual((s.transmitted_count, s.failed_count, s.rejected_count, s.pending_count), (1, 1, 1, 1))

    def test_deterministic_json_and_transmitted_derived_field(self):
        model = TxPublicationEvidence()
        model.add_intent(1, "a")
        model.enqueue_accepted(1, 0)
        model.complete(0, "transmitted")
        first = model.snapshot().to_json()
        second = model.snapshot().to_json()
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertTrue(payload["records"][0]["transmitted"])
        self.assertFalse(payload["action_authority"])
        self.assertTrue(payload["descriptive_only"])

    def test_classifier_rejects_non_record(self):
        with self.assertRaises(TxEvidenceError):
            classify_publication({"state": "transmitted"})

    def test_classifier_rejects_unknown_state(self):
        record = TxRecord(1, "a", "mystery", None, None, None)
        with self.assertRaises(TxEvidenceError):
            classify_publication(record)


if __name__ == "__main__":
    unittest.main()
