"""Source-pinned audit facts, not a live eligibility or admission provider."""
from copy import deepcopy
from types import MappingProxyType

PORTABLE_COMMIT = "0d4b19290931e100819169930079427e95e100a5"
PORTABLE_MANIFEST = "b10149e88c0c73fb5c21518d24313745e23c839a6bcb6d7803a6c8bf65d32f2d"
SOURCE_PINS = MappingProxyType({
    "src/lapsim_light_policies/core_registry.py": "7b869fce5775fa6875246bd22f4ce81eaf1936c545bd52fae99b64035020bc3a",
    "src/lapsim_light_policies/policy_layers.py": "4af256dcae65e6a85680b4c9f22a9e33a2447fad3a35ce9ac77b76f103c1b47a",
    "src/lapsim_light_policies/core_adapter.py": "fa74d965bcc385e6d64bb0fa9f5a719efa711369ecde77e6d26f688212e3701a",
    "src/lapsim_light_campaign/worker_inputs.py": "93feac70dfa1879239336eaaa9d646e8a3d3b0f353856b9e0059703e576d115e",
    "src/lapsim_light_campaign/numerical_bridge.py": "8ca6e15c0071ab610ff84799598580682390cd9c2bec98599833e87660ff1dc7",
    "src/lapsim_light_campaign/guarded_dispatch.py": "5e0e41d0b725bed6aaaca4285a46057c334835cc2b5df646b8f18d8868eac602",
    "src/lapsim_light_course/course.py": "7148a903abda03acb585352b58f2e240e501f424fc0e2b10a885c8b45732eff0",
    "src/lapsim_light_course/_fsi_geometry.py": "0a0966d4ada6f2f84a1f4069b88946c2c219e4e8ab01082e41c0f7ba704c4e1c",
    "src/lapsim_light_course/data/FSG.yaml": "7b3351cd9db27912131b9f5de427861061e2144ed6795498fe980adcd905c30d",
    "src/lapsim_light_course/data/amz_fssim_fsg_approx.json": "c6e4c47a3a4e5aa6efd3c1e4b93d332dc9cd1796f8ae88d02d4a970f6e6525af",
    "src/lapsim_light_course/fsg_reference.py": "9b004f5b120aa95d1c201a881e2a110c9eaf0ac27d7ab043e29c3f20340db639",
})
_POLICIES = (
    ("awd7-equal-off-v4", "Matched baseline trajectory, limits and accounting"),
    ("awd7-load-off-v4", "Nonuniform/dynamic load activation and zero-load rejection"),
    ("awd7-slip-off-v4", "Slip activation, shedding and low-speed behavior"),
    ("awd7-feedforward-off-v4", "Both steering signs/speeds and saturation effects"),
    ("awd7-yaw-pi-off-v4", "Closed-loop error, windup/unwind and actuator-limit freeze"),
    ("awd7-yaw-slip-off-v4", "Simultaneous yaw/slip activation and conservative integral freeze"),
    ("awd7-eco-neutral-off-v4", "Feasibility/failure cases and actual surrogate intervention; no measured loss-map optimum"),
)


def portable_policy_scope():
    """Return immutable-source audit declarations without importing that stack.

    These facts do not prove the portable distribution or native bindings are
    installed. The ordinary suite implements no portable dispatch route and
    never promotes these declarations using its RWD development evidence.
    """
    return deepcopy({
        "schema": "lapsim.portable-policy-source-audit.v2",
        "scope": "RECORDED_SOURCE_DECLARATIONS_NOT_CURRENT_RUNTIME_ELIGIBILITY",
        "source_commit": PORTABLE_COMMIT, "source_manifest_sha256": PORTABLE_MANIFEST,
        "source_pins": dict(SOURCE_PINS),
        "runtime_availability": "UNVERIFIED_BY_THIS_ORDINARY_SUITE",
        "distribution_version": "0.0.0.dev28",
        "bounded_component_tests": {
            "source_and_installed_cases": 110, "new_component_and_boundary_cases": 16,
            "rolling_policy_count": 7, "rolling_intervals_each": 20,
            "standing_one_tick_probes": 7, "work_counter_parity_intervals": 2,
            "scope": "SYNTHETIC_FIXED_CONTROLS_NOT_COURSE_OR_NATIVE_QUALIFICATION",
            "course_or_native_qualification": False, "campaign_eligibility_promoted": False,
        },
        "source_course_preparation": {
            "prepared_inputs": ["amz_fssim_fsi_approx", "amz_fssim_fsg_approx"],
            "fsg_source_test_cases": 15, "fsg_local_source_frame_constructed": True,
            "fsg_canonical_producer_frame_available": False,
            "fsg_admissible_driving_reference_available": False, "fsg_numerical_path_enabled": False,
            "fsg_source_chord_reference_candidate_available": True,
            "fsg_source_tk_device_gate_candidate_available": True,
            "fsg_reference_candidate_test_cases": 17,
            "fsg_gate_semantics_or_exact_arc_phase_qualified": False,
            "source_preparation_is_campaign_eligibility": False,
        },
        "required_original_guard_methods": ["execute_owned_request", "require_authenticated_owned_execution_and_cleanup"],
        "domain": {"topology": "synthetic_independent_four_awd_v1", "all_four_available": True,
                   "regen_enabled": False, "course": "amz_fssim_fsi_approx",
                   "mission": "one_standing_start_lap", "plant_step_s": .001,
                   "allocator_step_s": .01, "driver_step_s": .05},
        "policies": [{"id": name, "source_supported_in_snapshot": True,
                      "source_declared_native_qualification": "UNRUN",
                      "source_declared_campaign_eligible": False,
                      "implemented_in_this_suite": False, "qualification_gap": gap}
                     for name, gap in _POLICIES],
        "shared_gaps": {
            "nine_courses": "FSI/FSG source grids and local frames prepared; complete per-course sampled references/canonical producer frames/gates/admission and reviewed generalization of FSI-only numerical contracts still required",
            "skidpad": "Portable open ordered reference, driver/session/checkpoint/gate/chunk/replay contract; ordinary RWD skidpad is a different backend",
            "admission": "Genuine fixed native worker and both original guard methods, authenticated current inputs/authority, complete source/environment-v2 observation, original ownership/allocation/cleanup",
            "qualification": "Fresh matched seven-policy origins and genuine trajectory/limit/accounting evidence before any eligibility promotion",
        },
        "ordinary_or_heldout_results_promote_portable_eligibility": False,
        "qualification_or_execution_authority": False,
    })
