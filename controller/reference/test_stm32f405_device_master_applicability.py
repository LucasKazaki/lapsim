import json
import unittest
from stm32f405_device_master_applicability import (
    B43_MASTERS,
    DeviceApplicabilityError,
    DeviceIdentityEvidence,
    assess_device_master_applicability,
    frozen_f405_ethernet_counterexample,
    make_b43_absence_receipts,
)

class ApplicabilityTests(unittest.TestCase):
    def test_f405_excludes_only_ethernet_from_b43_superset(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","team_verified")
        )
        self.assertEqual(r.architecturally_absent_masters,("ethernet_dma",))
        self.assertEqual(r.applicable_masters,(
            "dma1_memory","dma2_memory","dma2_peripheral","usb_otg_hs_dma"
        ))

    def test_f407_keeps_all_b43_masters(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F407xx","team_verified")
        )
        self.assertEqual(r.architecturally_absent_masters,())
        self.assertEqual(r.applicable_masters,B43_MASTERS)

    def test_f405_keeps_usb_hs_dma(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","team_verified")
        )
        self.assertIn("usb_otg_hs_dma",r.applicable_masters)

    def test_user_statement_not_team_acceptance(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","user_statement")
        )
        self.assertFalse(r.ready_to_prune_b43_inventory)
        self.assertIn("device_family_not_team_verified",r.blockers)

    def test_scenario_not_team_acceptance(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","scenario")
        )
        self.assertFalse(r.ready_to_prune_b43_inventory)

    def test_team_verified_can_prune(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence(
                "STM32F405xx","team_verified","rev-a","schematic/U1"
            )
        )
        self.assertTrue(r.ready_to_prune_b43_inventory)
        self.assertTrue(r.physical_board_identity_proven)

    def test_unsupported_family_rejected(self):
        with self.assertRaises(DeviceApplicabilityError):
            assess_device_master_applicability(
                DeviceIdentityEvidence("STM32F415xx","team_verified")
            )

    def test_bad_source_rejected(self):
        with self.assertRaises(DeviceApplicabilityError):
            assess_device_master_applicability(
                DeviceIdentityEvidence("STM32F405xx","guessed")
            )

    def test_absence_bridge_requires_team_verified_identity(self):
        with self.assertRaises(DeviceApplicabilityError):
            make_b43_absence_receipts(
                DeviceIdentityEvidence("STM32F405xx","user_statement")
            )

    def test_f405_absence_bridge_has_only_ethernet(self):
        obs=make_b43_absence_receipts(
            DeviceIdentityEvidence("STM32F405xx","team_verified")
        )
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]["master"],"ethernet_dma")
        self.assertTrue(obs[0]["quiescent_for_exception_window"])
        self.assertEqual(obs[0]["possible_access_windows"],())
        self.assertTrue(obs[0]["all_possible_memory_accesses_covered"])

    def test_f407_absence_bridge_empty(self):
        self.assertEqual(
            make_b43_absence_receipts(
                DeviceIdentityEvidence("STM32F407xx","team_verified")
            ),
            (),
        )

    def test_counterexample(self):
        c=frozen_f405_ethernet_counterexample()
        self.assertTrue(c["b43_superset_contains_ethernet"])
        self.assertFalse(c["ethernet_present_on_f405"])
        self.assertTrue(c["usb_otg_hs_dma_present_on_f405"])
        self.assertFalse(c["ready_to_prune_team_inventory"])

    def test_no_runtime_or_action_claim(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","team_verified")
        )
        self.assertFalse(r.runtime_quiescence_proven)
        self.assertFalse(r.actual_contention_observed)
        self.assertFalse(r.peripheral_change_selected)
        self.assertFalse(r.firmware_change_authorized)
        self.assertFalse(r.vehicle_acceptance_proven)
        self.assertFalse(r.action_authority)

    def test_deterministic_json(self):
        r=assess_device_master_applicability(
            DeviceIdentityEvidence("STM32F405xx","user_statement")
        )
        self.assertEqual(r.to_json(),r.to_json())
        self.assertFalse(json.loads(r.to_json())["action_authority"])

if __name__=="__main__": unittest.main()
