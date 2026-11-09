"""UNTRUSTED factory wiring/preflight only; no real line or native admission.

The constructor-chain test uses explicit doubles. Other cases refuse inconsistent
inputs before construction. No numerical state advances or receipt is produced.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lapsim_light_campaign import worker_inputs
from lapsim_light_campaign.input_contracts import decode, digest, encode
from lapsim_light_campaign.numerical_inputs import NumericalBindings
from lapsim_light_campaign.tournament_plan import freeze_tournament
from test_campaign import RequestSource, plan_fixture, pin
from test_profile_projection import synthetic_manifest


class UntrustedObserver:
    implementation_sha256 = pin('no-observer')

    def observe_source_identity(self):
        raise AssertionError('Factory must not substitute runtime observation')


class UntrustedResidual:
    implementation_sha256 = pin('no-rule')

    def residual_low_speed_regen(self, u_mps, electrical):
        raise AssertionError('Factory must not run the model')


class WorkerInputsTests(unittest.TestCase):
    def setUp(self):
        self.course_raw = b'UNTRUSTED COURSE UNIT DOUBLE NOT ACTUAL FSI GEOMETRY'
        self.line_raw = b'UNTRUSTED LINE UNIT DOUBLE NOT AN ADMITTED ARTIFACT'
        self.cones_raw = b'UNTRUSTED CONES UNIT DOUBLE'
        plan_raw, _ = plan_fixture(course_sha256=sha256(self.course_raw).hexdigest(),
            line_sha256=sha256(self.line_raw).hexdigest(),
            reference_provenance={'producer_audit_sha256': pin('no-producer-audit'),
                                  'reviewed_promotion_sha256': pin('no-promotion')})
        cell = decode(plan_raw, 2*1024*1024)['plan']['cells'][0]
        self.plan_raw = plan_raw
        self.parent_raw = encode(cell['origin'])
        self.request_raw = RequestSource(plan_raw)(cell['policy_id'], self.parent_raw,
            requested_ticks=10, remaining_requested_wall_time_ms=1000)
        self.request_pin = decode(self.request_raw, 128*1024)['request_sha256']
        root = Path(__file__).resolve().parents[1]
        self.arguments = dict(expected_request_sha256=self.request_pin,
            baseline_raw=(root/'src/lapsim_light_campaign/baseline-configuration.json').read_bytes(),
            source_bundle_raw=self.course_raw, cones_raw=self.cones_raw, line_artifact_raw=self.line_raw,
            expected_cones_raw_sha256=sha256(self.cones_raw).hexdigest(),
            producer_audit_sha256=pin('no-producer-audit'), reviewed_promotion_sha256=pin('no-promotion'),
            reviewed_source_manifest_sha256=pin('source-not-observed'),
            bindings=NumericalBindings(UntrustedObserver(), UntrustedResidual(), pin('no-observer'), pin('no-rule')))

    def call(self, **overrides):
        return worker_inputs.construct_worker_bridge(self.request_raw, self.parent_raw,
            **{**self.arguments, **overrides})

    def test_actual_constructor_chain_is_fixed_and_exact(self):
        course, bridge = object(), object()
        fixture = SimpleNamespace(configuration_sha256=pin('configuration'))
        reference = SimpleNamespace(length_m=123., provenance={'reference_geometry_sha256': pin('raw-geometry')})
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference', return_value=course) as make_course, \
             patch('lapsim_light_campaign.numerical_inputs.raw_reference_inputs', return_value=reference) as make_reference, \
             patch('lapsim_light_campaign.fixture.construct_standing_fixture', return_value=fixture) as make_fixture, \
             patch('lapsim_light_campaign.numerical_bridge.NumericalBridge', return_value=bridge) as make_bridge:
            self.assertIs(self.call(), bridge)
            make_course.assert_called_once_with(self.course_raw, self.cones_raw, self.line_raw,
                expected_line_artifact_sha256=sha256(self.line_raw).hexdigest())
            make_reference.assert_called_once_with(self.line_raw, course,
                producer_audit_sha256=self.arguments['producer_audit_sha256'],
                reviewed_promotion_sha256=self.arguments['reviewed_promotion_sha256'])
            make_fixture.assert_called_once_with(self.arguments['baseline_raw'], reference_length_m=123.,
                reference_geometry_sha256=reference.provenance['reference_geometry_sha256'])
            identity = decode(self.request_raw, 128*1024)['request']['identity']
            make_bridge.assert_called_once_with(fixture=fixture, source_course=course,
                reference=reference, bindings=self.arguments['bindings'], expected_identity=identity,
                reviewed_source_manifest_sha256=self.arguments['reviewed_source_manifest_sha256'])

    def stage_synthetic_configuration(self, configuration_sha256):
        """Reseal existing untrusted metadata doubles; never source/admission evidence."""
        origins = {}
        for cell in decode(self.plan_raw, 2*1024*1024)['plan']['cells']:
            identity, origin = deepcopy(cell['identity']), deepcopy(cell['origin'])
            identity['configuration_sha256'] = configuration_sha256
            origin['checkpoint']['context']['configuration_sha256'] = configuration_sha256
            origin['checkpoint']['context_sha256'] = digest(origin['checkpoint']['context'])
            origin['checkpoint_sha256'] = digest(origin['checkpoint'])
            origins[cell['policy_id']] = dict(identity=identity, origin=origin)
        raw = encode(origins)
        plan_raw = encode(freeze_tournament(raw, expected_origins_raw_sha256=sha256(raw).hexdigest()))
        cell = decode(plan_raw, 2*1024*1024)['plan']['cells'][0]
        self.parent_raw = encode(cell['origin'])
        self.request_raw = RequestSource(plan_raw)(cell['policy_id'], self.parent_raw,
            requested_ticks=10, remaining_requested_wall_time_ms=1000)
        self.arguments['expected_request_sha256'] = decode(self.request_raw, 128*1024)['request_sha256']

    def test_profile_bytes_and_pin_are_paired_and_preflighted_before_coursework(self):
        raw = encode(synthetic_manifest())
        values = [dict(resolved_manifest_raw=raw),
                  dict(reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest()),
                  dict(resolved_manifest_raw=raw, reviewed_resolved_manifest_raw_sha256=pin('wrong-profile')),
                  dict(resolved_manifest_raw=bytearray(raw), reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest()),
                  dict(resolved_manifest_raw=b'{"missing":"complete manifest"}',
                       reviewed_resolved_manifest_raw_sha256=sha256(b'{"missing":"complete manifest"}').hexdigest())]
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as course:
            for override in values:
                with self.subTest(keys=tuple(override)), self.assertRaises(ValueError):
                    self.call(**override)
            course.assert_not_called()

    def test_profile_path_uses_actual_typed_fixture_and_exact_request_pin(self):
        from lapsim_light_campaign.fixture import construct_partial_profile_fixture, construct_standing_fixture
        raw = encode(synthetic_manifest())
        profile_arguments = dict(resolved_manifest_raw=raw,
            reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest())
        expected = construct_partial_profile_fixture(self.arguments['baseline_raw'], **profile_arguments,
            reference_length_m=123., reference_geometry_sha256=pin('raw-geometry'))
        self.stage_synthetic_configuration(expected.configuration_sha256)
        course, bridge = object(), object()
        reference = SimpleNamespace(length_m=123., provenance={'reference_geometry_sha256': pin('raw-geometry')})
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference', return_value=course), \
             patch('lapsim_light_campaign.numerical_inputs.raw_reference_inputs', return_value=reference), \
             patch('lapsim_light_campaign.fixture.construct_standing_fixture', wraps=construct_standing_fixture) as baseline, \
             patch('lapsim_light_campaign.numerical_bridge.NumericalBridge', return_value=bridge) as make_bridge:
            self.assertIs(self.call(**profile_arguments), bridge)
            actual = make_bridge.call_args.kwargs['fixture']
            self.assertEqual(actual, expected)
            self.assertEqual(actual.settings.forces.plant.mass_kg, 310.)
            self.assertEqual(make_bridge.call_args.kwargs['expected_identity']['configuration_sha256'], actual.configuration_sha256)
            baseline.assert_called_once()

    def test_request_profile_or_baseline_configuration_mismatch_precedes_bridge(self):
        raw = encode(synthetic_manifest())
        reference = SimpleNamespace(length_m=123., provenance={'reference_geometry_sha256': pin('raw-geometry')})
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference', return_value=object()), \
             patch('lapsim_light_campaign.numerical_inputs.raw_reference_inputs', return_value=reference), \
             patch('lapsim_light_campaign.numerical_bridge.NumericalBridge') as bridge:
            for override in ({}, dict(resolved_manifest_raw=raw,
                    reviewed_resolved_manifest_raw_sha256=sha256(raw).hexdigest())):
                with self.subTest(profile=bool(override)), self.assertRaisesRegex(ValueError, 'request configuration'):
                    self.call(**override)
            bridge.assert_not_called()

    def test_changed_source_or_reference_or_cones_refused_before_construction(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            for field in ('source_bundle_raw', 'line_artifact_raw', 'cones_raw'):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.call(**{field: self.arguments[field]+b' altered'})
            constructor.assert_not_called()

    def test_mutable_or_oversized_inputs_refused_before_construction(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            for raw in (bytearray(self.course_raw), b'x'*(worker_inputs.MAX_INPUT_BYTES+1)):
                with self.subTest(type=type(raw)), self.assertRaises(ValueError):
                    self.call(source_bundle_raw=raw)
            constructor.assert_not_called()

    def test_changed_baseline_refused_before_construction(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            with self.assertRaises(ValueError):
                self.call(baseline_raw=self.arguments['baseline_raw']+b' altered')
            constructor.assert_not_called()

    def test_missing_bindings_refused_before_construction(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            with self.assertRaises(ValueError):
                self.call(bindings=None)
            constructor.assert_not_called()

    def test_source_manifest_or_binding_pin_mismatch_refused(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            with self.assertRaises(ValueError):
                self.call(reviewed_source_manifest_sha256=pin('other-source'))
            other = replace(self.arguments['bindings'], source_observer_sha256=pin('other-observer'))
            with self.assertRaises(ValueError):
                self.call(bindings=other)
            constructor.assert_not_called()

    def test_request_pin_mismatch_refused_before_construction(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            with self.assertRaises(ValueError):
                self.call(expected_request_sha256=pin('other-request'))
            constructor.assert_not_called()

    def test_parent_reference_review_pins_cannot_be_replaced(self):
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference') as constructor:
            for field in ('producer_audit_sha256', 'reviewed_promotion_sha256'):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.call(**{field: pin('other-review')})
            constructor.assert_not_called()

    def test_constructor_control_exception_propagates_unchanged(self):
        class OwnerControl(BaseException):
            pass
        error = OwnerControl('UNTRUSTED OWNER CONTROL UNIT DOUBLE')
        with patch('lapsim_light_course.course.construct_fsi_course_from_reference', side_effect=error), \
             patch('lapsim_light_campaign.numerical_inputs.raw_reference_inputs') as reference:
            with self.assertRaises(OwnerControl) as caught:
                self.call()
            self.assertIs(caught.exception, error)
            reference.assert_not_called()


if __name__ == '__main__':
    unittest.main()
