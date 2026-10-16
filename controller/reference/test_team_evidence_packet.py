import json
import unittest

from team_evidence_packet import EvidencePacketError, SCHEMA, validate_packet


def template():
    return {
        "schema": SCHEMA,
        "evidence_revision": "synthetic-test",
        "target_car": "2027-28",
        "mcu": {"part_number": None, "package": None, "silicon_revision": None, "board_revision": None},
        "firmware": {
            "repository_reference": None, "revision": None, "build_working_directory": None,
            "build_command": None, "toolchain": None, "compiler_version": None,
            "optimization": None, "cpu_flags": None, "linker_script": None
        },
        "clock": {"sysclk_hz": None, "hclk_hz": None, "apb1_hz": None, "apb2_hz": None, "configuration_source": None},
        "reset": {"startup_file": None, "system_init_file": None, "reset_cause_owner": None},
        "watchdog": {"independent_watchdog_used": None, "window_watchdog_used": None, "configuration_file": None, "ownership": None},
        "logging": {"sink": None, "format": None, "timestamp_source": None},
        "can": {"controllers": [], "message_map_reference": None},
        "control_path_files": [],
        "sources": [],
        "claims": {"vehicle_specific_thresholds_verified": False, "hardware_test_executed": False, "rule_compliance_verified": False},
    }


def full_synthetic():
    x = template()
    x["mcu"].update(part_number="STM32F405xx-example", package="example", board_revision="synthetic")
    x["firmware"].update(
        repository_reference="synthetic/repo", revision="a" * 40, build_working_directory="firmware",
        build_command="example-build --no-flash", toolchain="example-toolchain", compiler_version="0.0-test",
        optimization="-O2", cpu_flags=["-mcpu=cortex-m4"], linker_script="synthetic.ld"
    )
    x["clock"].update(sysclk_hz=1, hclk_hz=1, apb1_hz=1, apb2_hz=1, configuration_source="synthetic-clock.c")
    x["reset"].update(startup_file="startup.s", system_init_file="system.c", reset_cause_owner="startup")
    x["watchdog"].update(ownership="unknown-by-design")
    x["logging"].update(sink="synthetic-buffer", timestamp_source="synthetic-counter")
    x["can"].update(message_map_reference="synthetic-map")
    x["control_path_files"] = ["control.c"]
    x["sources"] = [{"kind": "team_file", "reference": "synthetic", "sha256": "0" * 64}]
    return x


class PacketTests(unittest.TestCase):
    def test_empty_template_is_valid_but_not_ready(self):
        r = validate_packet(template())
        self.assertFalse(r.ready_for_source_specific_patch)
        self.assertIn("firmware.build_command", r.missing)
        self.assertIn("control_path_files", r.missing)
        self.assertIn("sources", r.missing)

    def test_full_synthetic_packet_is_ready(self):
        r = validate_packet(full_synthetic())
        self.assertTrue(r.ready_for_source_specific_patch)
        self.assertEqual(r.missing, ())
        self.assertEqual(r.populated, r.total_required)

    def test_missing_build_command_blocks_readiness(self):
        x = full_synthetic()
        x["firmware"]["build_command"] = None
        self.assertEqual(validate_packet(x).missing, ("firmware.build_command",))

    def test_missing_mcu_part_blocks_readiness(self):
        x = full_synthetic()
        x["mcu"]["part_number"] = None
        self.assertIn("mcu.part_number", validate_packet(x).missing)

    def test_zero_clock_is_rejected(self):
        x = template()
        x["clock"]["sysclk_hz"] = 0
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_boolean_is_not_clock_integer(self):
        x = template()
        x["clock"]["hclk_hz"] = True
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_duplicate_can_controller_names_rejected(self):
        x = template()
        entry = {"name": "CAN1", "used": None, "bitrate_bps": None, "pins": None, "transceiver": None}
        x["can"]["controllers"] = [entry, dict(entry)]
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_zero_bitrate_is_rejected(self):
        x = template()
        x["can"]["controllers"] = [{"name": "CAN1", "used": None, "bitrate_bps": 0, "pins": None, "transceiver": None}]
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_duplicate_control_files_rejected(self):
        x = template()
        x["control_path_files"] = ["a.c", "a.c"]
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_bad_sha_rejected(self):
        x = template()
        x["sources"] = [{"kind": "team_file", "reference": "a", "sha256": "xyz"}]
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_unknown_source_kind_rejected(self):
        x = template()
        x["sources"] = [{"kind": "internet_guess", "reference": "a", "sha256": None}]
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_positive_claims_rejected(self):
        for key in template()["claims"]:
            x = template()
            x["claims"][key] = True
            with self.assertRaises(EvidencePacketError):
                validate_packet(x)

    def test_wrong_target_car_rejected(self):
        x = template()
        x["target_car"] = "2026-27"
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_unknown_fields_rejected(self):
        x = template()
        x["extra"] = "no"
        with self.assertRaises(EvidencePacketError):
            validate_packet(x)

    def test_json_roundtrip(self):
        x = template()
        self.assertEqual(validate_packet(json.loads(json.dumps(x))).schema, SCHEMA)


if __name__ == "__main__":
    unittest.main()
