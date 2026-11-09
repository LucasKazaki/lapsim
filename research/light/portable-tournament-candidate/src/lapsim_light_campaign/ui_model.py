"""UNTESTED passive saved-evidence model and optional Tk integration panel.

No provider discovery, numerical import, process, HTTP route or action dispatch.
The host supplies independently pinned immutable export bytes. Hash consistency
is displayed separately from authentication and numeric replay.
"""
from dataclasses import dataclass

from .continuation_archive import validate_raw_child_archive
from .input_contracts import decode, encode
from .raw_evidence import MAX_EXPORT_BYTES, replay_raw_bundle


def saved_evidence_model(bundle_raw, *, expected_bundle_sha256, expected_manifest_sha256):
    bundle = decode(bundle_raw, MAX_EXPORT_BYTES, canonical=True)
    tail = replay_raw_bundle(bundle, expected_bundle_sha256=expected_bundle_sha256,
                             expected_manifest_sha256=expected_manifest_sha256)
    checkpoint = tail["checkpoint"]["checkpoint"]
    power = checkpoint["state"]["thermal"]["light"]["powered"]
    identity = bundle["bundle"]["manifest"]["identity"]
    return {
        "label": "Saved raw development evidence",
        "bundle_sha256": expected_bundle_sha256, "manifest_sha256": expected_manifest_sha256,
        "policy_id": identity["policy_id"], "source_sha256": identity["source_sha256"],
        "environment_sha256": identity["environment_sha256"],
        "checkpoint_sha256": tail["checkpoint"]["checkpoint_sha256"],
        "storage_chain": "consistent_with_supplied_pins",
        "execution_admission": "not_authenticated_by_this_panel",
        "numerical_replay": "not_performed_by_this_panel",
        "runtime": "no_original_provider_bound_to_this_panel",
        "storage_terminal": None if tail["terminal"] is None else tail["terminal"]["terminal"]["status"],
        "numerical_status": checkpoint["status"], "committed_records": tail["records"],
        "tick": checkpoint["tick"], "segment": checkpoint["segment"],
        "pack_energy_j": power["pack_energy_j"],
        "source_progress_m": checkpoint["memory"]["source_progress_m"],
        "reference_progress_m": checkpoint["memory"]["previous_progress"],
        "raw_violation": checkpoint["violation"],
        "stop_requested": False, "owned_cleanup_confirmed": False,
        "actions": {name: {"enabled": False,
                           "reason": "A genuine original admitted runtime is not integrated with this saved-evidence panel"}
                    for name in ("run", "continue", "replay_numerically", "stop", "close_worker")},
        "campaign_eligible": False, "official_points": None, "winner": None,
        "qualification_or_execution_authority": False,
    }


def saved_child_evidence_model(ancestry_raw, owned_admission_raw, predecessor_bundle_raw,
                                historical_owned_receipts_raw, child_bundle_raw, *,
                                expected_ancestry_sha256, expected_continuation_sha256,
                                expected_child_bundle_sha256):
    """Show one child chronology, separating copied history from new RAW records."""
    summary = validate_raw_child_archive(
        ancestry_raw, owned_admission_raw, predecessor_bundle_raw, historical_owned_receipts_raw, child_bundle_raw,
        expected_ancestry_sha256=expected_ancestry_sha256,
        expected_continuation_sha256=expected_continuation_sha256,
        expected_child_bundle_sha256=expected_child_bundle_sha256)
    model = saved_evidence_model(child_bundle_raw, expected_bundle_sha256=expected_child_bundle_sha256,
                                  expected_manifest_sha256=summary["child_manifest_sha256"])
    model.update(label="Saved raw child evidence; copied history is not new execution",
                 child_lineage="consistent_with_supplied_pins",
                 ancestry_sha256=expected_ancestry_sha256,
                 continuation_sha256=expected_continuation_sha256,
                 lineage_id=summary["lineage_id"],
                 predecessor_bundle_sha256=summary["predecessor_bundle_sha256"],
                 predecessor_manifest_sha256=summary["predecessor_manifest_sha256"],
                 copied_prefix_records=summary["copied_prefix_records"],
                 new_raw_records=summary["new_raw_records"], history_credit=summary["history_credit"])
    return model


@dataclass(slots=True)
class SavedEvidencePanel:
    """Host-owned Tk view only. No worker can be attached by supplying a result DTO."""

    frame: object
    status_label: object
    values: object
    model: dict | None = None

    def clear(self):
        self.model = None
        self.values.delete(*self.values.get_children())
        self.status_label.configure(text="No saved light evidence loaded. Runtime controls are unavailable.")

    def load_pinned_export(self, bundle_raw, *, expected_bundle_sha256, expected_manifest_sha256):
        # Clear first: a rejected new file must never leave the old result visible
        # as if it belonged to the new selection. The host handles the exception.
        self.clear()
        model = saved_evidence_model(bundle_raw, expected_bundle_sha256=expected_bundle_sha256,
                                      expected_manifest_sha256=expected_manifest_sha256)
        self._show_model(model)

    def load_pinned_child_exports(self, ancestry_raw, owned_admission_raw, predecessor_bundle_raw,
                                  historical_owned_receipts_raw, child_bundle_raw, *,
                                  expected_ancestry_sha256, expected_continuation_sha256,
                                  expected_child_bundle_sha256):
        self.clear()
        model = saved_child_evidence_model(
            ancestry_raw, owned_admission_raw, predecessor_bundle_raw, historical_owned_receipts_raw, child_bundle_raw,
            expected_ancestry_sha256=expected_ancestry_sha256,
            expected_continuation_sha256=expected_continuation_sha256,
            expected_child_bundle_sha256=expected_child_bundle_sha256)
        self._show_model(model)

    def _show_model(self, model):
        for name in ("policy_id", "storage_chain", "child_lineage", "execution_admission", "numerical_replay", "runtime",
                     "storage_terminal", "numerical_status", "committed_records", "tick", "segment",
                     "copied_prefix_records", "new_raw_records", "history_credit",
                     "pack_energy_j", "source_progress_m", "reference_progress_m", "raw_violation",
                     "stop_requested", "owned_cleanup_confirmed", "source_sha256", "environment_sha256",
                     "checkpoint_sha256", "bundle_sha256", "manifest_sha256", "ancestry_sha256",
                     "continuation_sha256", "lineage_id", "predecessor_bundle_sha256", "predecessor_manifest_sha256"):
            if name in model:
                self.values.insert("", "end", values=(name, encode(model[name]).decode("utf-8")))
        self.model = model
        self.status_label.configure(text=model["label"] + ". Storage matches supplied pins; execution admission and numerical replay are unverified.")


def create_saved_evidence_panel(parent):
    """Optional host integration factory; no root window, mainloop or file I/O.

    Existing apps may explicitly embed the returned frame after later UI
    acceptance. It is not registered in the legacy web or desktop launcher.
    Destroying this passive panel cannot stop/clean a separate application job.
    """
    from tkinter import ttk

    frame = ttk.Frame(parent)
    status = ttk.Label(frame, text="No saved light evidence loaded. Runtime controls are unavailable.", wraplength=760)
    status.pack(fill="x", padx=8, pady=8)
    controls = ttk.Frame(frame)
    controls.pack(fill="x", padx=8)
    for label in ("Run", "Continue", "Replay numerically", "Stop", "Close worker"):
        ttk.Button(controls, text=label, state="disabled").pack(side="left", padx=3)
    values = ttk.Treeview(frame, columns=("field", "value"), show="headings", height=18)
    values.heading("field", text="Saved field")
    values.heading("value", text="Raw value / evidence scope")
    values.column("field", width=230, stretch=False)
    values.column("value", width=600, stretch=True)
    values.pack(fill="both", expand=True, padx=8, pady=8)
    return SavedEvidencePanel(frame, status, values)
