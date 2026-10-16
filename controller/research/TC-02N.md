# TC-02N — pedal/sensor plausibility evidence before command authority

Status: portable synthetic reference only. Target remains the 2027-28 Terps Racing EV torque-control project.

## Decision

Split `CommandGuardInput.sensor_agreement_ok` and the accelerator/brake overlap inputs into a separate, replayable evidence layer before source-specific integration.

The current `command_guard.py` correctly keeps `sensor_agreement_ok` abstract, but that boolean is not yet reproducible from raw pedal-channel observations. TC-02N adds a conservative observer that:

- requires at least two independently labelled accelerator channels;
- normalizes each channel from explicit released/applied calibration endpoints, including reversed transfer functions;
- rejects non-finite values and raw values outside the supplied calibrated travel;
- compares normalized channels against an explicitly supplied disagreement threshold;
- refuses to resolve an accelerator fraction when the channels disagree;
- reports instantaneous brake/accelerator overlap from an explicitly supplied threshold; and
- carries threshold provenance (`scenario`, `team_file`, or `final_rule`) into the evidence record.

It does **not** vote around a bad third channel, latch a fault, shut down motors, command torque, or select a recovery threshold. Those behaviors remain source/rule/team-policy dependent.

## Why this stays parameterized

SAE's official September 15, 2026 announcement says the final 2027 Formula SAE rules were published. The accessible Formula SAE news page also still exposes the July public-comment draft as a draft. The final 2027 rules body was not retrievable through the available public browser path in this pass, so no numeric APPS disagreement, persistence, brake/accelerator trip, or recovery threshold is encoded as a 2027 requirement.

Historical/draft rule text is useful for identifying the *kind* of evidence an implementation may need, but it is not accepted here as the final 2027 compliance source. Before a vehicle-specific threshold is used, bind it either to the exact final 2027 rule text or an authorized team requirement, record that provenance, and review the interaction with the independent shutdown/safety system.

## Relationship to existing branch code

- `command_guard.py` remains authoritative for the portable synthetic command-gating behavior currently on the branch.
- TC-02N is an upstream observation contract, not a replacement command guard.
- A later source-specific adapter may feed `accelerator_fraction` and `sensor_agreement_ok` into the guard only after the actual sensor count, calibration, rule thresholds, brake signal semantics, firmware timing and ownership are verified.
- The observer's `action_authority` is permanently false.

## Portable verification

CPython 3.13.5 / Linux x86_64, standard library only.

Commands:

    python -S -m unittest -v test_pedal_plausibility.py
    python -S -m py_compile pedal_plausibility.py test_pedal_plausibility.py

Observed: 23/23 tests passed, 0 failed, 0 skipped; py_compile exited 0.

Coverage includes different and reversed transfer functions, endpoint normalization, exact disagreement boundary, disagreement faulting, brake/accelerator overlap observation, strict boolean validation, NaN/Inf/out-of-calibration inputs, missing/extra/duplicate channels, invalid calibration, at-least-two-channel enforcement, threshold bounds, provenance validation, conservative three-channel behavior with no majority vote, and deterministic JSON.

Portable SHA-256:
- `pedal_plausibility.py`: `d38134a13c284a45738c253d9e86d4c1a234043f695e13a74251094336d4c1c6`
- `test_pedal_plausibility.py`: `1ae9aace307e98dc1895166bf6b3fa712241246e5c3c5816a5fcab3c61a734f2`

These are synthetic host-language tests only. No STM32 build/run, real pedal hardware, CAN traffic, HIL, dyno, track, firmware flash or vehicle actuation occurred.

## Keep/revert rule

Keep this layer only while it remains evidence-first. Rework or reject a future implementation that:
1. averages disagreeing accelerator channels into a usable request;
2. treats a non-finite or out-of-calibration channel as nominal;
3. silently adopts a threshold without source provenance;
4. treats a historical/draft rule value as verified 2027 compliance;
5. implements majority voting or degraded operation without reviewed source-specific authority; or
6. allows this observer to replace an independent shutdown/safety function.

## Next source-specific action

When TC-03A is populated, reproduce the untouched firmware build and inspect the actual APPS/BSE or equivalent input path. Bind the real channel count, calibration representation, sample timing, disagreement logic, brake signal semantics, and final 2027 rule references. Adapt or discard this portable contract if the team architecture differs.
