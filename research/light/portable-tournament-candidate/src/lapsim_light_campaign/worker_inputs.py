"""Fixed raw-input construction for the already admitted native numerical worker.

This composes the actual source course, raw reference, fixture and NumericalBridge
constructors. It does not authenticate a line, observe an environment, launch a
process or grant admission. Construction itself belongs inside the original
owner's finite worker allocation, not its post-cleanup receipt-verification call.
The native bootstrap supplies the real reviewed NumericalBindings. No payload
selects a module, callable, provider, key, model or alternate numerical family.
"""
from hashlib import sha256

from . import raw_journal as journal
from .guarded_dispatch import validate_staged_request
from .input_contracts import decode, is_sha256, require

MAX_INPUT_BYTES = 2 * 1024 * 1024


def construct_worker_bridge(
    request_raw, checkpoint_raw, *, expected_request_sha256,
    baseline_raw, source_bundle_raw, cones_raw, line_artifact_raw,
    expected_cones_raw_sha256, producer_audit_sha256,
    reviewed_promotion_sha256, reviewed_source_manifest_sha256, bindings,
    resolved_manifest_raw=None, reviewed_resolved_manifest_raw_sha256=None,
):
    """Build the real exact bridge from immutable bounded inputs, without stepping.

    Reviewed pins and bindings must come from the trusted native bootstrap, and
    original producer/reference/environment admission must precede this call.
    Hash matches here provide consistency only. The caller retains its real
    ChunkWorkerProgram and calls execute(bridge=returned_bridge), then snapshot()
    after return/failure under its original retention and cleanup controls.
    """
    body = validate_staged_request(request_raw, checkpoint_raw,
                                   expected_request_sha256=expected_request_sha256)
    require((resolved_manifest_raw is None) == (reviewed_resolved_manifest_raw_sha256 is None),
            "Resolved profile bytes and reviewed raw SHA256 must be supplied together")
    if resolved_manifest_raw is not None:
        from .profile_projection import resolve_partial_profile
        resolve_partial_profile(resolved_manifest_raw,
            reviewed_resolved_manifest_raw_sha256=reviewed_resolved_manifest_raw_sha256)
    for raw in (baseline_raw, source_bundle_raw, cones_raw, line_artifact_raw):
        require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT_BYTES,
                "Bounded immutable complete numerical input bytes required")
    require(all(is_sha256(pin) for pin in (
        expected_cones_raw_sha256, producer_audit_sha256,
        reviewed_promotion_sha256, reviewed_source_manifest_sha256)),
        "Explicit independently reviewed input/source pins required")
    identity = body['identity']
    require(sha256(source_bundle_raw).hexdigest() == identity['course_bundle_sha256'] and
            sha256(line_artifact_raw).hexdigest() == identity['line_artifact_sha256'] and
            sha256(cones_raw).hexdigest() == expected_cones_raw_sha256,
            "Raw course/reference/cone bytes differ from their exact input pins")

    # Delayed imports are fixed source names, never native factories from input.
    from lapsim_light_course.course import construct_fsi_course_from_reference
    from .fixture import (BASELINE_RAW_SHA256, MAX_BASELINE_BYTES, construct_standing_fixture,
                          construct_partial_profile_fixture)
    from .numerical_inputs import NumericalBindings, raw_reference_inputs
    from .numerical_bridge import NumericalBridge

    require(len(baseline_raw) <= MAX_BASELINE_BYTES and
            sha256(baseline_raw).hexdigest() == BASELINE_RAW_SHA256,
            "Exact packaged baseline snapshot required; no substituted calibration")
    require(type(bindings) is NumericalBindings, "Real reviewed native numerical bindings required")
    bindings.require_available()
    parent = decode(checkpoint_raw, journal.MAX_CHECKPOINT, canonical=True)['checkpoint']
    source = parent['context']['source']
    require(source['source_manifest_sha256'] == reviewed_source_manifest_sha256 and
            source['external_bindings'] == {
                'source_observer_sha256': bindings.source_observer_sha256,
                'residual_regen_rule_sha256': bindings.residual_regen_rule_sha256,
            }, "Native binding/source pins differ from the exact parent context")
    provenance = parent['context']['reference_line']
    require(provenance.get('producer_audit_sha256') == producer_audit_sha256 and
            provenance.get('reviewed_promotion_sha256') == reviewed_promotion_sha256,
            "Producer/reference review pins differ from the exact parent context")

    course = construct_fsi_course_from_reference(source_bundle_raw, cones_raw, line_artifact_raw,
        expected_line_artifact_sha256=identity['line_artifact_sha256'])
    reference = raw_reference_inputs(line_artifact_raw, course,
        producer_audit_sha256=producer_audit_sha256,
        reviewed_promotion_sha256=reviewed_promotion_sha256)
    fixture_arguments = dict(reference_length_m=reference.length_m,
        reference_geometry_sha256=reference.provenance['reference_geometry_sha256'])
    if resolved_manifest_raw is None:
        fixture = construct_standing_fixture(baseline_raw, **fixture_arguments)
    else:
        fixture = construct_partial_profile_fixture(baseline_raw,
            resolved_manifest_raw=resolved_manifest_raw,
            reviewed_resolved_manifest_raw_sha256=reviewed_resolved_manifest_raw_sha256,
            **fixture_arguments)
    require(fixture.configuration_sha256 == identity['configuration_sha256'],
            "Constructed baseline/profile fixture differs from exact request configuration SHA256")
    return NumericalBridge(fixture=fixture, source_course=course, reference=reference,
        bindings=bindings, expected_identity=identity,
        reviewed_source_manifest_sha256=reviewed_source_manifest_sha256)
