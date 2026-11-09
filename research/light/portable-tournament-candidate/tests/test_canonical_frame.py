"""Synthetic artifact consistency tests; NOT original/native admission evidence.

Frames are generated locally from public pinned inputs and wrapped in an explicitly
untrusted reference fixture. No original artifact, receipt, worker or lap is used.
The cosine patch is a sensitivity experiment, not a platform-libm model.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from math import cos, hypot, inf, nextafter, pi, sin
from pathlib import Path
import unittest
from unittest.mock import patch

from lapsim_light_course import course, _fsi_geometry as geometry
from lapsim_light_campaign.numerical_inputs import REFERENCE_PARAMETERS, raw_reference_inputs
from lapsim_light_campaign import raw_journal as journal
from lapsim_light_campaign.input_contracts import decode, digest, encode
from lapsim_light_campaign.tournament_plan import freeze_tournament
from test_campaign import plan_fixture, pin


DATA = Path(__file__).resolve().parents[1] / 'src/lapsim_light_course/data'
BUNDLE = (DATA / 'amz_fssim_fsi_approx.json').read_bytes()
CONES = (DATA / 'FSI.yaml').read_bytes()
UNTRUSTED_PIN = sha256(b'NO ORIGINAL AUTHENTICATION IN THIS TEST').hexdigest()


def synthetic_artifact(source):
    """A synthetic closed chord reference; never an original racing line."""
    x = [10 * sin(2*pi*i/16) for i in range(16)] + [0.]
    y = [10 * (1-cos(2*pi*i/16)) for i in range(16)] + [0.]
    s = [0.]
    for a,b,c,d in zip(x,x[1:],y,y[1:]):
        s.append(s[-1] + hypot(b-a,d-c))
    line = dict(model='sampled_polyline', closed=True, distance_m=s,
                x_m=x, y_m=y, curvature_per_m=[.1]*16)
    frame = source.frame_dict()
    return dict(schema='ev.awd-fsi-frozen-racing-reference.v6',
        status='GEOMETRY_SCREENED_DYNAMIC_REPLAY_UNRUN', role='development',
        heldout_used=False, shared_across_techniques=True, minimum_time_proven=False,
        source_geometry_sha256=source.geometry_sha256,
        source_bundle_payload_sha256=source.bundle_payload_sha256,
        raw_boundary_sha256=source.cones_raw_sha256,
        frame=frame, frame_sha256=geometry.digest(frame),
        geometry=line, reference_geometry_sha256=geometry.digest(line),
        parameters=deepcopy(REFERENCE_PARAMETERS),
        gate=dict(origin_xy_m=[0.,0.], forward_unit=[1.,0.], finite_half_width_m=3.,
                  scope='Source physical gate;not moved with reference distance'),
        test_scope='SYNTHETIC_LOCAL_FRAME_NOT_ORIGINAL_OR_ADMITTED')


class CanonicalFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local = course.construct_fsi_course(BUNDLE, CONES)

    def setUp(self):
        self.artifact = synthetic_artifact(self.local)

    def construct(self, artifact=None, *, bundle=BUNDLE, cones=CONES):
        raw = geometry.canonical(self.artifact if artifact is None else artifact).encode()
        return course.construct_fsi_course_from_reference(bundle, cones, raw,
            expected_line_artifact_sha256=sha256(raw).hexdigest())

    def test_canonical_frame_survives_local_cosine_sensitivity(self):
        original_cos = geometry.cos
        with patch.object(geometry, 'cos', side_effect=lambda x: nextafter(original_cos(x), inf)):
            local = course.construct_fsi_course(BUNDLE, CONES)
            fixed = self.construct()
        self.assertNotEqual(local._frame_json, self.local._frame_json)
        self.assertEqual(fixed._frame_json, self.local._frame_json)
        self.assertEqual(fixed.source_track, self.local.source_track)
        self.assertEqual(fixed.bundle_raw_sha256, self.local.bundle_raw_sha256)
        self.assertEqual(fixed.cones_raw_sha256, self.local.cones_raw_sha256)
        self.assertEqual(fixed.canonical_frame_artifact_sha256,
                         sha256(geometry.canonical(self.artifact).encode()).hexdigest())
        reference = raw_reference_inputs(geometry.canonical(self.artifact).encode(), fixed,
            producer_audit_sha256=UNTRUSTED_PIN, reviewed_promotion_sha256=UNTRUSTED_PIN)
        self.assertEqual(geometry.canonical(reference.frame).encode(), fixed._frame_json)
        self.assertEqual(reference.provenance['admission'], 'RAW_INPUT_CONSISTENCY_ONLY_NO_AUTHORITY')

    def test_expected_raw_artifact_pin_precedes_reconstruction(self):
        raw = geometry.canonical(self.artifact).encode()
        with patch.object(geometry, 'reconstruct_frame') as reconstruct:
            with self.assertRaises(ValueError):
                course.construct_fsi_course_from_reference(BUNDLE, CONES, raw+b' ',
                    expected_line_artifact_sha256=sha256(raw).hexdigest())
            reconstruct.assert_not_called()

    def test_unavailable_artifact_has_no_fallback(self):
        with self.assertRaises(TypeError):
            course.construct_fsi_course_from_reference(BUNDLE, CONES)
        for raw in (None, bytearray(b'{}'), b'', b'x'*(2*1024*1024+1)):
            with self.subTest(raw_type=type(raw)), self.assertRaises(ValueError):
                course.construct_fsi_course_from_reference(BUNDLE, CONES, raw,
                    expected_line_artifact_sha256=UNTRUSTED_PIN)

    def test_frame_digest_and_source_pairing_are_exact(self):
        for field in ('frame_sha256', 'source_geometry_sha256',
                      'source_bundle_payload_sha256', 'raw_boundary_sha256'):
            value = deepcopy(self.artifact)
            value[field] = UNTRUSTED_PIN
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.construct(value)

    def test_artifact_claims_cannot_promote_or_change_the_development_input(self):
        for field, changed in (('schema', 'unknown'), ('status', 'QUALIFIED'),
                               ('role', 'heldout'), ('heldout_used', True),
                               ('shared_across_techniques', False), ('minimum_time_proven', True)):
            value = deepcopy(self.artifact)
            value[field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.construct(value)

    def test_canonical_artifact_cannot_bypass_the_fixed_raw_source_pins(self):
        with patch.object(geometry, 'reconstruct_frame') as reconstruct:
            for bundle,cones in ((BUNDLE[:-1]+b' ', CONES), (BUNDLE, CONES[:-1]+b' ')):
                with self.subTest(bundle_changed=bundle!=BUNDLE), self.assertRaises(ValueError):
                    self.construct(bundle=bundle, cones=cones)
            reconstruct.assert_not_called()

    def test_changed_frame_fails_existing_exact_reference_check(self):
        fixed = self.construct()
        changed = deepcopy(self.artifact)
        changed['frame']['left_xy_m'][0][0] = nextafter(changed['frame']['left_xy_m'][0][0], inf)
        changed['frame_sha256'] = geometry.digest(changed['frame'])
        raw = geometry.canonical(changed).encode()
        with self.assertRaisesRegex(ValueError, 'canonical frame artifact pin'):
            raw_reference_inputs(raw, fixed,
                producer_audit_sha256=UNTRUSTED_PIN, reviewed_promotion_sha256=UNTRUSTED_PIN)
        # A caller-forged DTO pin still cannot weaken the separate frame check.
        forged = replace(fixed, canonical_frame_artifact_sha256=sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, 'identities differ'):
            raw_reference_inputs(raw, forged,
                producer_audit_sha256=UNTRUSTED_PIN, reviewed_promotion_sha256=UNTRUSTED_PIN)

    def test_same_frame_in_different_raw_artifact_cannot_cross_the_api_binding(self):
        raw = geometry.canonical(self.artifact).encode()
        fixed = self.construct()
        changed = deepcopy(self.artifact)
        changed['test_scope'] += ' DIFFERENT ARTIFACT'
        for other_raw in (raw+b' ', geometry.canonical(changed).encode()):
            with self.subTest(raw_bytes=len(other_raw)), self.assertRaisesRegex(ValueError, 'canonical frame artifact pin'):
                raw_reference_inputs(other_raw, fixed,
                    producer_audit_sha256=UNTRUSTED_PIN, reviewed_promotion_sha256=UNTRUSTED_PIN)

    def test_frame_shape_and_claims_rejected_even_with_recomputed_hash(self):
        mutations = (
            lambda f: f.pop('confidence'),
            lambda f: f.update(unreviewed_field=0),
            lambda f: f.update(runtime_or_corridor_admission=True),
            lambda f: f.update(schema='unknown'),
            lambda f: f.update(raw_sha256=UNTRUSTED_PIN),
            lambda f: f.update(LF_sha256=UNTRUSTED_PIN),
            lambda f: f.update(source_geometry_sha256=UNTRUSTED_PIN),
            lambda f: f.update(source_origin_m=[False, 0]),
            lambda f: f.update(source_heading_rad=True),
            lambda f: f['source_to_course_SE2'].update(scale=2.),
            lambda f: f['source_to_course_SE2'].update(scale=True),
            lambda f: f['source_to_course_SE2'].update(rotation_rad=0.),
            lambda f: f['source_to_course_SE2'].update(translation_x_m=False),
            lambda f: f.update(left_xy_m=[[0.,0.]]*8),
            lambda f: f.update(maximum_grid_xy_error_m=1e-6),
            lambda f: f.update(maximum_grid_station_error_m=-1.),
            lambda f: f.update(maximum_grid_curvature_error_per_m=1e-8),
        )
        for index, mutate in enumerate(mutations):
            value = deepcopy(self.artifact)
            mutate(value['frame'])
            value['frame_sha256'] = geometry.digest(value['frame'])
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                self.construct(value)

    def test_strict_json_rejects_duplicate_keys_and_overflow_anywhere(self):
        raw = geometry.canonical(self.artifact).encode()
        samples = (b'{"frame":{},"frame":{}}',
                   raw[:-1]+b',"untrusted_overflow":1e999}',
                   raw[:-1]+b',"untrusted_nan":NaN}')
        for altered in samples:
            with self.subTest(raw=altered[:30]), self.assertRaises(ValueError):
                course.construct_fsi_course_from_reference(BUNDLE, CONES, altered,
                    expected_line_artifact_sha256=sha256(altered).hexdigest())

    def test_canonical_expansion_remains_bounded(self):
        value = deepcopy(self.artifact)
        value['untrusted_unicode'] = '\u00e9' * 350_000
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.assertLess(len(raw), course.MAX_REFERENCE_BYTES)
        with patch.object(geometry, 'reconstruct_frame') as reconstruct:
            with self.assertRaisesRegex(ValueError, 'transport bound'):
                course.construct_fsi_course_from_reference(BUNDLE, CONES, raw,
                    expected_line_artifact_sha256=sha256(raw).hexdigest())
            reconstruct.assert_not_called()

    def test_existing_local_screens_still_run_and_failure_propagates(self):
        with patch.object(geometry, 'reconstruct_frame', side_effect=ValueError('local screen failed')) as local:
            with self.assertRaisesRegex(ValueError, 'local screen failed'):
                self.construct()
            local.assert_called_once()

    def test_raw_line_endings_stay_bound_to_actual_artifact(self):
        bundle, cones = BUNDLE.replace(b'\n',b'\r\n'), CONES.replace(b'\n',b'\r\n')
        crlf = course.construct_fsi_course(bundle, cones)
        with self.assertRaises(ValueError):
            self.construct(bundle=bundle, cones=cones)
        valid = self.construct(synthetic_artifact(crlf), bundle=bundle, cones=cones)
        self.assertEqual(valid.cones_raw_sha256, crlf.cones_raw_sha256)
        self.assertNotEqual(valid.cones_raw_sha256, self.local.cones_raw_sha256)
        self.assertEqual(valid.geometry_sha256, self.local.geometry_sha256)

    def test_canonical_diagnostics_preserved_as_artifact_claims(self):
        value = deepcopy(self.artifact)
        value['frame']['maximum_grid_xy_error_m'] = 5e-8
        value['frame_sha256'] = geometry.digest(value['frame'])
        fixed = self.construct(value)
        self.assertEqual(fixed.frame_dict(), value['frame'])
        self.assertNotEqual(fixed.frame_dict()['maximum_grid_xy_error_m'],
                            self.local.frame_dict()['maximum_grid_xy_error_m'])
        # Both DTO projections return fresh objects, never a mutable shared frame.
        exposed = fixed.frame_dict()
        exposed['left_xy_m'][0][0] += 1
        self.assertEqual(fixed.frame_dict(), value['frame'])

    def test_same_frame_cannot_hide_rehashed_checkpoint_environment_mismatch(self):
        plan_raw, _ = plan_fixture(reference_provenance={'frame_sha256': self.artifact['frame_sha256']})
        cell = decode(plan_raw, 2*1024*1024)['plan']['cells'][0]
        body, identity = cell['origin']['checkpoint'], cell['identity']
        context = body['context']
        source = context['source']
        source['numerical_environment_sha256'] = pin('different-environment')
        source['sha256'] = digest({k:v for k,v in source.items() if k != 'sha256'})
        identity['source_sha256'] = source['sha256']
        body['context_sha256'] = digest(context)
        cell['origin']['checkpoint_sha256'] = digest(body)
        with self.assertRaisesRegex(ValueError, 'environment declarations differ'):
            journal._bind_checkpoint(cell['origin'], identity)

    def test_same_frame_cannot_merge_individually_valid_cross_environment_cells(self):
        plan_raw, _ = plan_fixture(reference_provenance={'frame_sha256': self.artifact['frame_sha256']})
        cells = decode(plan_raw, 2*1024*1024)['plan']['cells']
        cell = cells[0]
        body, identity = cell['origin']['checkpoint'], cell['identity']
        source = body['context']['source']
        source['numerical_environment_sha256'] = pin('different-environment')
        source['sha256'] = digest({k:v for k,v in source.items() if k != 'sha256'})
        identity.update(source_sha256=source['sha256'], environment_sha256=source['numerical_environment_sha256'])
        body['context_sha256'] = digest(body['context'])
        cell['origin']['checkpoint_sha256'] = digest(body)
        journal._bind_checkpoint(cell['origin'], identity)  # The changed cell is self-consistent.
        raw = encode({c['policy_id']: {'identity': c['identity'], 'origin': c['origin']} for c in cells})
        with self.assertRaisesRegex(ValueError, 'Unmatched field'):
            freeze_tournament(raw, expected_origins_raw_sha256=sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
