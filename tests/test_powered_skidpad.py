"""Small real powered steps; full gate circuits use separate geometric tests."""
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from lapsim.events.skidpad_sequence import standard_skidpad_sequence
from lapsim.events.powered_skidpad import (
    PoweredSkidpadRequest, fresh_session, advance_session, checkpoint, resume,
)
from lapsim.experiments.tournament_rollout import Controller, PHILOSOPHIES, fixture


def request(philosophy="fixed", maximum_ticks=100):
    return PoweredSkidpadRequest(
        standard_skidpad_sequence(entry_length_m=5., exit_length_m=5.),
        Controller(philosophy), maximum_ticks=maximum_ticks,
    )


@pytest.mark.parametrize("philosophy", PHILOSOPHIES)
def test_real_powered_chunk_resume_exact(philosophy):
    req = replace(request(philosophy), course=standard_skidpad_sequence(
        entry_length_m=1., exit_length_m=5.))
    whole = fresh_session(req)
    advance_session(whole, 35)
    split = fresh_session(req)
    advance_session(split, 17)  # Between driver updates: held command must survive.
    raw = checkpoint(split)
    restored = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
    advance_session(restored, 18)
    assert checkpoint(whole) == checkpoint(restored)
    assert whole.tick == 35
    assert whole.driver_updates == 7
    assert whole.allocator_updates == 35
    assert whole.state.plant.x_m > 0.
    assert [c["phase"] for c in whole.gates.crossings] == ["ENTRY"]
    assert len(whole.crossing_states) == 1
    assert whole.state.integration_trials > 0
    assert whole.state.pack_energy_j < whole.initial_state.pack_energy_j
    assert whole.result()["qualified_tournament_result"] is False
    assert whole.result()["timed_average_s"] is None


def test_checkpoint_rejects_identity_state_and_budget_changes():
    req = request()
    session = fresh_session(req)
    advance_session(session, 7)
    raw = checkpoint(session)
    with pytest.raises(ValueError, match="digest"):
        resume(raw, expected_sha256="0" * 64, request=req)
    for field in ("source", "runtime", "request"):
        value = json.loads(raw)
        value["binding"][field] = {"changed": True}
        changed = json.dumps(value).encode()
        with pytest.raises(ValueError, match="binding"):
            resume(changed, expected_sha256=sha256(changed).hexdigest(), request=req)
    value = json.loads(raw)
    value["state"]["plant"]["x_m"] += 1.
    changed = json.dumps(value).encode()
    with pytest.raises(ValueError, match="pose|state"):
        resume(changed, expected_sha256=sha256(changed).hexdigest(), request=req)
    with pytest.raises(ValueError, match="binding"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(),
               request=replace(req, maximum_ticks=101))


def test_budget_cancellation_and_terminal_resume_do_not_refund_ticks():
    req = request(maximum_ticks=8)
    session = fresh_session(req)
    advance_session(session, 7)
    advance_session(session, 7)
    assert session.tick == 8
    assert session.status == "budget_exhausted"
    raw = checkpoint(session)
    restored = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
    with pytest.raises(ValueError, match="terminal"):
        advance_session(restored, 1)
    cancelled = fresh_session(request())
    advance_session(cancelled, 3, cancelled=lambda: True)
    assert cancelled.tick == 0
    assert cancelled.status == "cancelled"
    with pytest.raises(ValueError, match="terminal"):
        advance_session(cancelled, 1)


def test_model_rejection_retains_pre_step_and_attempt(monkeypatch):
    import lapsim.events.powered_skidpad as module
    session = fresh_session(request())
    before = session.state
    def reject(*args, **kwargs):
        raise ValueError("forced integration rejection")
    monkeypatch.setattr(module, "advance_powered", reject)
    advance_session(session, 1)
    assert session.status == "model_error"
    assert session.tick == 0
    assert session.attempted_steps == 1
    assert session.state == before
    assert "forced integration rejection" in session.failure_reason
    raw = checkpoint(session)
    recovered = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=session.request)
    assert recovered.attempted_steps == 1
    assert json.dumps(recovered.rejected_attempt, sort_keys=True) == json.dumps(session.rejected_attempt, sort_keys=True)


def test_strict_checkpoint_decoder_rejects_booleans_and_extra_fields():
    req = request()
    raw = checkpoint(fresh_session(req))
    for field, value in (("tick", False), ("allocator_updates", False), ("extra", 1)):
        changed = json.loads(raw)
        changed[field] = value
        data = json.dumps(changed).encode()
        with pytest.raises(ValueError):
            resume(data, expected_sha256=sha256(data).hexdigest(), request=req)


def test_cli_real_chunk_creates_hashed_files_and_resumes(tmp_path, capsys):
    from lapsim.events.powered_skidpad import main
    first = tmp_path / "first"
    base = ["--entry-length-m", "5", "--exit-length-m", "5", "--maximum-ticks", "30"]
    assert main([*base, "--chunk-ticks", "7", "--output", str(first)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["accepted_ticks"] == 7
    assert printed["status"] == "running"
    index = json.loads((first / "files.json").read_bytes())["files"]
    for name, identity in index.items():
        raw = (first / name).read_bytes()
        assert len(raw) == identity["bytes"]
        assert sha256(raw).hexdigest() == identity["sha256"]
    second = tmp_path / "second"
    assert main([*base, "--chunk-ticks", "6", "--output", str(second),
                 "--resume-checkpoint", str(first / "checkpoint.json"),
                 "--resume-sha256", index["checkpoint.json"]["sha256"]]) == 0
    whole = fresh_session(request(maximum_ticks=30))
    advance_session(whole, 13)
    assert (second / "checkpoint.json").read_bytes() == checkpoint(whole)
    before = (first / "checkpoint.json").read_bytes()
    assert main([*base, "--chunk-ticks", "7", "--output", str(first)]) == 2
    assert (first / "checkpoint.json").read_bytes() == before


def test_checkpoint_cannot_claim_missing_gates_or_reset_accounting():
    req = request()
    s = fresh_session(req)
    advance_session(s, 7)
    saved = json.loads(checkpoint(s))
    edits = (("status", "completed"), ("allocator_updates", 0),
             ("driver_updates", 0), ("command", None), ("gross_pack_draw_j", 0.))
    for key, value in edits:
        changed = dict(saved)
        changed[key] = value
        raw = json.dumps(changed).encode()
        with pytest.raises(ValueError):
            resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)


def test_cumulative_work_exhaustion_is_terminal_without_retry():
    req = replace(request(), maximum_work=1)
    s = fresh_session(req)
    advance_session(s, 1)
    assert s.status == "model_error"
    assert s.attempted_steps == 1
    assert "budget" in s.failure_reason
    assert s.tick == 0
    assert s.state.integration_trials == 0  # No invented returned partial state.
    assert s.rejected_attempt["before_state_sha256"]
    with pytest.raises(ValueError, match="terminal"):
        advance_session(s, 1)


def test_gate_bracket_pose_requires_matching_complete_state():
    req = replace(request(), course=standard_skidpad_sequence(entry_length_m=1., exit_length_m=5.))
    s = fresh_session(req)
    advance_session(s, 35)
    assert len(s.crossing_states) == 1
    saved = json.loads(checkpoint(s))
    before_tick = s.gates.crossings[0]["before"]["tick"]
    saved["gate_trace"][before_tick]["pack_energy_j"] += .1
    # Match interval accounting so the full-state/pose check is the rejecting boundary.
    trace = saved["gate_trace"]
    saved["gross_pack_draw_j"] = sum(max(0., a["pack_energy_j"]-b["pack_energy_j"])
                                       for a,b in zip(trace, trace[1:]))
    saved["recovered_pack_j"] = sum(max(0., b["pack_energy_j"]-a["pack_energy_j"])
                                     for a,b in zip(trace, trace[1:]))
    raw = json.dumps(saved).encode()
    with pytest.raises(ValueError, match="crossing pose/full state"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)


def test_record_and_held_memory_changes_are_rejected():
    req = request()
    s = fresh_session(req)
    advance_session(s, 7)
    saved = json.loads(checkpoint(s))
    for key, value in (("requested_nm", "bad"), ("requested_nm", [1.,1.,1.,1.]), ("brake_shortfall_nm", float("inf")),
                       ("extra", 3)):
        changed = json.loads(json.dumps(saved))
        changed["records"][-1][key] = value
        raw = json.dumps(changed).encode()
        with pytest.raises(ValueError):
            resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
    changed = json.loads(json.dumps(saved))
    changed["command"]["drive_torques_nm"][2:] = [1.,1.]
    raw = json.dumps(changed).encode()
    with pytest.raises(ValueError, match="held controller memory"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)


def test_cli_retains_terminal_raw_state_after_unexpected_exception(tmp_path, monkeypatch, capsys):
    import lapsim.events.powered_skidpad as module
    original = module.advance_powered
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("unexpected model exception")
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "advance_powered", fail_second)
    output = tmp_path / "unexpected"
    assert module.main(["--entry-length-m", "5", "--exit-length-m", "5",
                        "--chunk-ticks", "3", "--output", str(output)]) == 3
    result = json.loads((output / "result.json").read_bytes())
    assert result["tick"] == 1 and result["attempted_steps"] == 2
    assert result["status"] == "model_error"
    assert "unexpected model exception" in result["failure_reason"]
    raw = (output / "checkpoint.json").read_bytes()
    restored = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=request(maximum_ticks=10000))
    assert restored.status == "model_error"
    assert restored.tick == 1


def test_nominal_terminal_restore_rechecks_final_energy_and_counters():
    req = request(maximum_ticks=8)
    s = fresh_session(req)
    advance_session(s, 8)
    assert s.status == "budget_exhausted"
    saved = json.loads(checkpoint(s))
    saved["state"]["conversion_loss_j"] += 100.
    digest = sha256(json.dumps(saved["state"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    saved["gate_trace"][-1]["state_sha256"] = digest
    saved["records"][-1]["after_state_sha256"] = digest
    raw = json.dumps(saved).encode()
    with pytest.raises(ValueError, match="energy residual"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
    saved = json.loads(checkpoint(s))
    saved["allocator_updates"] = 0
    raw = json.dumps(saved).encode()
    with pytest.raises(ValueError, match="accounting"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)


def test_cancellation_callback_failure_is_bounded_terminal_and_reconstructable():
    req = request()
    session = fresh_session(req)
    def broken_cancellation():
        raise ValueError("x" * 5000)
    with pytest.raises(ValueError):
        advance_session(session, 1, cancelled=broken_cancellation)
    assert session.status == "model_error" and session.attempted_steps == 0
    assert len(session.failure_reason) == 4096
    raw = checkpoint(session)
    restored = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
    assert restored.failure_reason == session.failure_reason
    with pytest.raises(ValueError, match="terminal"):
        advance_session(restored, 1)


def test_returned_endpoint_limits_are_checked_before_chunk_or_gate_completion(monkeypatch):
    import lapsim.events.powered_skidpad as module
    original = module.advance_powered
    def invalid_endpoint(car, pack, before, *args, **kwargs):
        after = original(car, pack, before, *args, **kwargs)
        # Explicit control-flow double: preserve energy balance while violating
        # the existing development yaw bound at the returned endpoint.
        extra_kinetic = .5 * car.yaw_inertia_kgm2 * (3.**2 - after.plant.yaw_rate_rad_s**2)
        return replace(after, plant=replace(after.plant, yaw_rate_rad_s=3.),
                       pack_energy_j=after.pack_energy_j-extra_kinetic)
    monkeypatch.setattr(module, "advance_powered", invalid_endpoint)
    session = fresh_session(request())
    advance_session(session, 1)
    assert session.status == "invalid"
    assert session.tick == 1 and session.attempted_steps == 1
    assert "endpoint" in session.failure_reason
    assert session.state.plant.yaw_rate_rad_s == 3.
    assert len(session.records) == 1
    raw = checkpoint(session)
    restored = resume(raw, expected_sha256=sha256(raw).hexdigest(), request=session.request)
    assert restored.status == "invalid"


def test_nominal_checkpoint_rechecks_endpoint_even_with_balanced_energy():
    req = request(maximum_ticks=8)
    session = fresh_session(req)
    advance_session(session, 8)
    saved = json.loads(checkpoint(session))
    car = fixture()[0]
    state = saved["state"]
    extra = .5 * car.yaw_inertia_kgm2 * (3.**2 - state["plant"]["yaw_rate_rad_s"]**2)
    state["plant"]["yaw_rate_rad_s"] = 3.
    state["pack_energy_j"] -= extra
    digest = sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    saved["gate_trace"][-1]["state_sha256"] = digest
    saved["gate_trace"][-1]["pack_energy_j"] = state["pack_energy_j"]
    saved["records"][-1]["after_state_sha256"] = digest
    saved["gross_pack_draw_j"] += extra
    raw = json.dumps(saved).encode()
    with pytest.raises(ValueError, match="endpoint"):
        resume(raw, expected_sha256=sha256(raw).hexdigest(), request=req)
