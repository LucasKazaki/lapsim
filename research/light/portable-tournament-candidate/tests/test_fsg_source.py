"""Pinned public FSG input preparation; no driving reference or admission."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lapsim_light_course import course, _fsi_geometry as geometry

DATA = Path(__file__).resolve().parents[1] / "src/lapsim_light_course/data"
BUNDLE = (DATA / "amz_fssim_fsg_approx.json").read_bytes()
CONES = (DATA / "FSG.yaml").read_bytes()
FSI_BUNDLE = (DATA / "amz_fssim_fsi_approx.json").read_bytes()
FSI_CONES = (DATA / "FSI.yaml").read_bytes()
SOURCE_RECORDS = []


class FsgSourceTests(unittest.TestCase):
    def test_complete_pinned_fsg_source_and_frame(self):
        result = course.construct_fsg_course(BUNDLE, CONES)
        self.assertIs(type(result), course.FsgSourceCourse)
        self.assertIsNot(type(result), course.SourceCourse)
        self.assertEqual(result.course_id, "amz_fssim_fsg_approx")
        self.assertEqual(result.contract, "lapsim.light-fsg-source-course.v1")
        self.assertEqual(result.status, "SOURCE_INPUT_ONLY_UNQUALIFIED")
        self.assertEqual(result.source_track.cell_count, 724)
        self.assertEqual(result.source_track.length_m, 306.45041872992834)
        self.assertEqual(result.bundle_raw_sha256, sha256(BUNDLE).hexdigest())
        self.assertEqual(result.cones_raw_sha256, sha256(CONES).hexdigest())
        self.assertEqual(result.geometry_sha256,
            "0863d0fe882a9e7d756e35b211ee510e829f1dde3384ec85d26d4737e748c0ee")
        self.assertIsNone(result.canonical_frame_artifact_sha256)
        frame = result.frame_dict()
        self.assertEqual(frame["schema"], "ev.fsg-cone-frame.v1")
        self.assertEqual((len(frame["left_xy_m"]), len(frame["right_xy_m"])), (94, 88))
        self.assertFalse(frame["runtime_or_corridor_admission"])
        self.assertLessEqual(frame["maximum_grid_xy_error_m"], 1e-7)
        self.assertLessEqual(frame["maximum_grid_station_error_m"], 1e-7)
        self.assertLessEqual(frame["maximum_grid_curvature_error_per_m"], 1e-9)
        SOURCE_RECORDS.append({"role": "development_source_grid_and_local_frame_only",
            "course_id": result.course_id, "contract": result.contract,
            "bundle_raw_sha256": result.bundle_raw_sha256,
            "cones_raw_sha256": result.cones_raw_sha256,
            "geometry_sha256": result.geometry_sha256,
            "source_geometry": result.source_track.geometry_dict(),
            "metadata": result.metadata_dict(), "local_frame": frame,
            "driving_reference_supplied": False, "heldout_results_used": False,
            "qualification_or_execution_authority": False})

    def test_exact_saved_channels_are_preserved_instead_of_regenerated(self):
        result = course.construct_fsg_course(BUNDLE, CONES)
        original = json.loads(BUNDLE)["geometry"]
        expected = {k: v for k, v in original.items() if k != "model"}
        self.assertEqual(result.source_track.geometry_dict(), expected)
        self.assertEqual(geometry.digest(expected), result.geometry_sha256)
        self.assertEqual(result.bundle_payload_sha256, geometry.digest(json.loads(BUNDLE)))

    def test_source_dto_and_nested_projections_do_not_share_mutable_state(self):
        result = course.construct_fsg_course(BUNDLE, CONES)
        metadata, frame = result.metadata_dict(), result.frame_dict()
        metadata["ai_defaults"]["half_width_m"] = 999.
        frame["left_xy_m"][0][0] = 999.
        self.assertEqual(result.metadata_dict()["ai_defaults"]["half_width_m"], 3.)
        self.assertNotEqual(result.frame_dict()["left_xy_m"][0][0], 999.)
        with self.assertRaises(FrozenInstanceError):
            result.bundle_encoding = "unknown"
        with self.assertRaises(TypeError):
            result.source_track.x_m[0] = 1.

    def test_cross_paired_or_wrong_course_inputs_fail_before_geometry(self):
        for constructor, bundle, cones in (
            (course.construct_fsg_course, FSI_BUNDLE, FSI_CONES),
            (course.construct_fsg_course, BUNDLE, FSI_CONES),
            (course.construct_fsg_course, FSI_BUNDLE, CONES),
            (course.construct_fsi_course, BUNDLE, CONES),
            (course.construct_fsi_course, FSI_BUNDLE, CONES),
            (course.construct_fsi_course, BUNDLE, FSI_CONES),
        ):
            with self.subTest(constructor=constructor.__name__, bundle=len(bundle), cones=len(cones)), \
                    patch.object(geometry, "reconstruct_fsg_frame") as fsg, \
                    patch.object(geometry, "reconstruct_frame") as fsi:
                with self.assertRaises(ValueError):
                    constructor(bundle, cones)
                fsg.assert_not_called()
                fsi.assert_not_called()

    def test_changed_same_length_bytes_fail_before_reconstruction(self):
        for bundle, cones in ((BUNDLE[:-1]+b" ", CONES), (BUNDLE, CONES[:-1]+b" ")):
            with self.subTest(bundle_changed=bundle != BUNDLE), \
                    patch.object(geometry, "reconstruct_fsg_frame") as reconstruct:
                with self.assertRaises(ValueError):
                    course.construct_fsg_course(bundle, cones)
                reconstruct.assert_not_called()

    def test_only_bounded_immutable_complete_inputs_are_accepted(self):
        for invalid in (None, b"", bytearray(BUNDLE), memoryview(BUNDLE), "not bytes", b"x"*80000):
            with self.subTest(kind=type(invalid)), self.assertRaises(ValueError):
                course.construct_fsg_course(invalid, CONES)
        for invalid in (None, b"", bytearray(CONES), memoryview(CONES), "not bytes", b"x"*32769):
            with self.subTest(kind=type(invalid)), self.assertRaises(ValueError):
                course.construct_fsg_course(BUNDLE, invalid)

    def test_fsg_lf_only_pin_has_no_automatic_encoding_fallback(self):
        for bundle, cones in ((BUNDLE.replace(b"\n", b"\r\n"), CONES),
                              (BUNDLE, CONES.replace(b"\n", b"\r\n"))):
            with self.subTest(bundle_bytes=len(bundle)), self.assertRaises(ValueError):
                course.construct_fsg_course(bundle, cones)

    def test_legacy_fsi_lf_crlf_still_return_the_exact_fsi_dto(self):
        lf = course.construct_fsi_course(FSI_BUNDLE, FSI_CONES)
        crlf = course.construct_fsi_course(FSI_BUNDLE.replace(b"\n", b"\r\n"),
                                         FSI_CONES.replace(b"\n", b"\r\n"))
        self.assertIs(type(lf), course.SourceCourse)
        self.assertIs(type(crlf), course.SourceCourse)
        self.assertEqual(lf.source_track, crlf.source_track)
        self.assertEqual(lf.metadata_dict(), crlf.metadata_dict())
        self.assertEqual(lf.frame_dict()["schema"], "ev.fsi-cone-frame.v1")
        self.assertEqual(lf.geometry_sha256, course.GEOMETRY_SHA256)
        self.assertEqual(lf.contract, course.CONTRACT)

    def test_mutated_geometry_cannot_use_the_fixed_fsg_wrapper(self):
        source = json.loads(BUNDLE)["geometry"]
        for change in (lambda v: v["x_m"].__setitem__(10, v["x_m"][10]+1e-10),
                       lambda v: v.update(closed=False),
                       lambda v: v.update(x_m=[0.] * 5002)):
            altered = deepcopy(source)
            change(altered)
            with self.subTest(changed=altered != source), self.assertRaises(ValueError):
                geometry.reconstruct_fsg_frame(CONES, altered)

    def test_generated_grid_is_capped_before_allocating_cells(self):
        for reconstruct, cones, bundle in (
            (geometry.reconstruct_fsg_frame, CONES, BUNDLE),
            (geometry.reconstruct_frame, FSI_CONES, FSI_BUNDLE),
        ):
            with self.subTest(reconstruct=reconstruct.__name__), \
                    patch.object(geometry, "ceil", return_value=6000), \
                    self.assertRaisesRegex(ValueError, "fixed source cell bound"):
                reconstruct(cones, json.loads(bundle)["geometry"])

    def test_bad_reconstruction_is_rejected_without_best_fit_or_source_replacement(self):
        original_cos = geometry.cos
        with patch.object(geometry, "cos", side_effect=lambda x: original_cos(x)+1e-4), \
                self.assertRaisesRegex(ValueError, "Full source grid mismatch"):
            course.construct_fsg_course(BUNDLE, CONES)

    def test_fsg_type_is_rejected_before_native_reference_decoding(self):
        from lapsim_light_campaign import numerical_inputs
        result = course.construct_fsg_course(BUNDLE, CONES)
        with patch.object(numerical_inputs, "decode", side_effect=AssertionError("decoded artifact")), \
                self.assertRaisesRegex(ValueError, "Exact native source-course DTO"):
            numerical_inputs.raw_reference_inputs(b"{}", result,
                producer_audit_sha256="0"*64, reviewed_promotion_sha256="0"*64)

    def test_fsi_artifact_constructor_cannot_select_fsg(self):
        from test_canonical_frame import synthetic_artifact
        source = course.construct_fsi_course(FSI_BUNDLE, FSI_CONES)
        raw = geometry.canonical(synthetic_artifact(source)).encode()
        with self.assertRaises(ValueError):
            course.construct_fsi_course_from_reference(BUNDLE, CONES, raw,
                expected_line_artifact_sha256=sha256(raw).hexdigest())

    def test_retyped_fsg_cannot_bypass_independent_fsi_reference_identity(self):
        from test_canonical_frame import synthetic_artifact
        from lapsim_light_campaign.numerical_inputs import raw_reference_inputs
        result = course.construct_fsg_course(BUNDLE, CONES)
        forged = course.SourceCourse(**{f.name: getattr(result, f.name) for f in fields(course.SourceCourse)})
        fsi = course.construct_fsi_course(FSI_BUNDLE, FSI_CONES)
        raw = geometry.canonical(synthetic_artifact(fsi)).encode()
        with self.assertRaisesRegex(ValueError, "identities differ"):
            raw_reference_inputs(raw, forged,
                producer_audit_sha256="0"*64, reviewed_promotion_sha256="0"*64)

    def test_seven_policy_execution_registry_remains_fsi_only(self):
        from lapsim_light_policies import core_registry
        registry = {"schema": core_registry.SCHEMA, "policies": core_registry.entries(),
                    "hardware": core_registry.hardware_eligibility(core_registry.TOPOLOGY),
                    "courses": [{"id": "amz_fssim_fsg_approx"}]}
        with self.assertRaisesRegex(ValueError, "Exact FSI source course"):
            core_registry.validate(registry)
        self.assertTrue(all(p["native_qualification"] == "UNRUN" and not p["campaign_eligible"]
                            for p in core_registry.entries()))


if __name__ == "__main__":
    unittest.main()
