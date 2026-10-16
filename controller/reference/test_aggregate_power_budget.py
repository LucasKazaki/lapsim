import json
import math
import unittest

from allocator import AllocationInput, AllocatorConfig
from aggregate_power_budget import (
    AggregatePowerBudgetError,
    AggregatePowerConfig,
    allocate_with_aggregate_power_budget,
    frozen_aggregate_power_counterexample,
)


def inp(**overrides):
    values = dict(
        now_ms=1000,
        input_timestamp_ms=1000,
        request_nm=400.0,
        wheel_limits_nm=(200.0, 200.0, 200.0, 200.0),
        wheel_enabled=(True, True, True, True),
        external_interlock=True,
    )
    values.update(overrides)
    return AllocationInput(**values)


def pwr(**overrides):
    values = dict(
        dc_power_available_w=12000.0,
        dc_to_wheel_efficiency=0.90,
        source_kind="scenario",
    )
    values.update(overrides)
    return AggregatePowerConfig(**values)


class AggregatePowerBudgetTests(unittest.TestCase):
    def test_counterexample_base_allocation_is_equal(self):
        r = frozen_aggregate_power_counterexample()
        self.assertEqual(r.base_allocation.wheel_torque_nm, (100.0, 100.0, 100.0, 100.0))

    def test_counterexample_candidate_mechanical_power(self):
        self.assertAlmostEqual(frozen_aggregate_power_counterexample().candidate_wheel_mechanical_power_w, 20000.0)

    def test_counterexample_wheel_power_budget(self):
        self.assertAlmostEqual(frozen_aggregate_power_counterexample().wheel_mechanical_power_budget_w, 10800.0)

    def test_counterexample_scale(self):
        self.assertAlmostEqual(frozen_aggregate_power_counterexample().power_scale, 0.54)

    def test_counterexample_final_torque_preserves_distribution(self):
        r = frozen_aggregate_power_counterexample()
        self.assertEqual(tuple(round(x, 8) for x in r.final_wheel_torque_nm), (54.0, 54.0, 54.0, 54.0))

    def test_counterexample_final_delivered_torque(self):
        self.assertAlmostEqual(frozen_aggregate_power_counterexample().final_delivered_nm, 216.0)

    def test_counterexample_hits_dc_budget(self):
        self.assertAlmostEqual(frozen_aggregate_power_counterexample().estimated_final_dc_power_w, 12000.0)

    def test_counterexample_reports_power_limit(self):
        r = frozen_aggregate_power_counterexample()
        self.assertTrue(r.power_limit_active)
        self.assertEqual(r.status, "saturated")
        self.assertEqual(r.fault, "aggregate_dc_power_limit")

    def test_low_speed_same_torque_does_not_hit_power_limit(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(5.0, 5.0, 5.0, 5.0),
            power_config=pwr(),
        )
        self.assertFalse(r.power_limit_active)
        self.assertEqual(r.final_delivered_nm, 400.0)

    def test_zero_speed_torque_has_zero_mechanical_power(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(0.0, 0.0, 0.0, 0.0),
            power_config=pwr(dc_power_available_w=0.0),
        )
        self.assertFalse(r.power_limit_active)
        self.assertEqual(r.candidate_wheel_mechanical_power_w, 0.0)
        self.assertEqual(r.final_delivered_nm, 400.0)

    def test_zero_power_budget_at_positive_speed_scales_to_zero(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(10.0, 10.0, 10.0, 10.0),
            power_config=pwr(dc_power_available_w=0.0),
        )
        self.assertTrue(r.power_limit_active)
        self.assertEqual(r.final_delivered_nm, 0.0)
        self.assertEqual(r.power_scale, 0.0)

    def test_common_scale_preserves_non_equal_base_ratios(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(request_nm=500.0, wheel_limits_nm=(50.0, 200.0, 200.0, 200.0)),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
            power_config=pwr(dc_power_available_w=8000.0),
        )
        base = r.base_allocation.wheel_torque_nm
        final = r.final_wheel_torque_nm
        self.assertTrue(r.power_limit_active)
        for b, f in zip(base, final):
            if b > 0.0:
                self.assertAlmostEqual(f / b, r.power_scale)

    def test_disabled_wheel_remains_zero(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(wheel_enabled=(True, True, True, False), request_nm=300.0),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
            power_config=pwr(),
        )
        self.assertEqual(r.base_allocation.wheel_torque_nm[3], 0.0)
        self.assertEqual(r.final_wheel_torque_nm[3], 0.0)

    def test_existing_stale_fault_passes_through(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(input_timestamp_ms=900),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
            power_config=pwr(),
        )
        self.assertEqual(r.status, "fault")
        self.assertEqual(r.fault, "stale_input")
        self.assertEqual(r.final_delivered_nm, 0.0)

    def test_existing_interlock_fault_passes_through(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(external_interlock=False),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
            power_config=pwr(),
        )
        self.assertEqual(r.fault, "external_interlock_open")

    def test_existing_wrong_unit_fault_passes_through(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(torque_unit="lb*ft"),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
            power_config=pwr(),
        )
        self.assertEqual(r.fault, "unsupported_torque_unit")

    def test_negative_wheel_speed_fails_closed(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(20.0, -1.0, 60.0, 80.0),
            power_config=pwr(),
        )
        self.assertEqual(r.status, "fault")
        self.assertEqual(r.fault, "invalid_wheel_speed")
        self.assertEqual(r.final_delivered_nm, 0.0)

    def test_nonfinite_wheel_speed_fails_closed(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad):
                r = allocate_with_aggregate_power_budget(
                    allocation_input=inp(),
                    allocator_config=AllocatorConfig(max_input_age_ms=50),
                    wheel_omega_rad_s=(20.0, bad, 60.0, 80.0),
                    power_config=pwr(),
                )
                self.assertEqual(r.fault, "invalid_wheel_speed")

    def test_wrong_channel_count_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0),
                power_config=pwr(),
            )

    def test_negative_power_budget_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
                power_config=pwr(dc_power_available_w=-1.0),
            )

    def test_nonfinite_power_budget_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
                power_config=pwr(dc_power_available_w=math.nan),
            )

    def test_zero_efficiency_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
                power_config=pwr(dc_to_wheel_efficiency=0.0),
            )

    def test_efficiency_over_one_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
                power_config=pwr(dc_to_wheel_efficiency=1.01),
            )

    def test_bad_source_kind_rejected(self):
        with self.assertRaises(AggregatePowerBudgetError):
            allocate_with_aggregate_power_budget(
                allocation_input=inp(),
                allocator_config=AllocatorConfig(max_input_age_ms=50),
                wheel_omega_rad_s=(20.0, 40.0, 60.0, 80.0),
                power_config=pwr(source_kind="guessed"),
            )

    def test_team_verified_source_retained(self):
        r = allocate_with_aggregate_power_budget(
            allocation_input=inp(request_nm=10.0),
            allocator_config=AllocatorConfig(max_input_age_ms=50),
            wheel_omega_rad_s=(1.0, 1.0, 1.0, 1.0),
            power_config=pwr(source_kind="team_verified"),
        )
        self.assertEqual(r.source_kind, "team_verified")

    def test_battery_soc_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().battery_soc_limit_proven)

    def test_battery_current_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().battery_current_limit_proven)

    def test_dc_voltage_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().dc_voltage_limit_proven)

    def test_inverter_current_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().inverter_current_limit_proven)

    def test_thermal_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().thermal_limit_proven)

    def test_traction_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().traction_limit_proven)

    def test_regen_limit_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().regen_limit_proven)

    def test_vehicle_acceptance_not_invented(self):
        self.assertFalse(frozen_aggregate_power_counterexample().vehicle_acceptance_proven)

    def test_zero_action_authority(self):
        self.assertFalse(frozen_aggregate_power_counterexample().action_authority)

    def test_deterministic_json(self):
        r = frozen_aggregate_power_counterexample()
        self.assertEqual(r.to_json(), r.to_json())
        payload = json.loads(r.to_json())
        self.assertFalse(payload["action_authority"])


if __name__ == "__main__":
    unittest.main()
