"""Bounded synthetic allocator/plant checks, not a course or native admission.

The fixture and component functions are real. No source observer, original line,
guard, worker or cleanup provider is replaced with a test double here. The
tests never enter that campaign path. Fixed control probes are not lap evidence.
"""
from dataclasses import asdict, replace
from math import isfinite
import unittest

from lapsim_light_campaign.fixture import construct_standing_fixture, fixture_resource_bytes
from lapsim_light_campaign.plant_tick import advance_tick
from lapsim_light_core.actuation import constrain_actuation
from lapsim_light_core.planar import PlanarState
from lapsim_light_core.powered_planar import PoweredState, energy_residual_j
from lapsim_light_core.torque_light_combined import initialize_combined_light
from lapsim_light_core.torque_light_thermal import evaluate_thermal_light
from lapsim_light_policies import core_adapter, core_registry, policy_layers

ZERO = (0.,) * 4
AVAILABLE = (True,) * 4
# Collected only by the external bounded test runner, never campaign evidence.
PROBE_RECORDS = []


class PolicyDynamicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = construct_standing_fixture(fixture_resource_bytes(),
            reference_length_m=100., reference_geometry_sha256="0" * 64)
        cls.car = cls.fixture.settings.forces.plant

    def state(self, *, speed=5., wheel_speeds=None, actuation=None,
              longitudinal_load=0., lateral_load=0., yaw=0.):
        f = self.fixture
        point = PlanarState(u_mps=speed, yaw_rate_rad_s=yaw,
            wheel_speeds_rad_s=((speed / self.car.wheel_radius_m,) * 4
                               if wheel_speeds is None else wheel_speeds))
        return initialize_combined_light(f.settings, f.thermal, f.drs_policy,
            f.actuation if actuation is None else actuation,
            PoweredState(point, ZERO, 9_000_000.), f.environment,
            initial_temperature_c=70., automatic_drs_enabled=True,
            load_longitudinal_mps2=longitudinal_load, load_lateral_mps2=lateral_load)

    def physical(self, state, *, held=ZERO, steer=ZERO, actuation=None):
        f = self.fixture
        return evaluate_thermal_light(f.settings, f.thermal,
            f.actuation if actuation is None else actuation,
            state.thermal, held, steer, ZERO, AVAILABLE, f.environment,
            aero_mode=state.drs.actual_mode)[1]

    def allocate(self, config, state, *, demand=100., integral=0.,
                 steer=(.08, .08, 0., 0.), actuation=None):
        return core_adapter.allocate_core(config, state.thermal.light.powered,
            self.physical(state, steer=steer, actuation=actuation), steer,
            demand, 0., integral, self.car,
            self.fixture.actuation if actuation is None else actuation,
            core_adapter.case_for(config))

    def test_eco_rejects_signed_power_branch_before_optimization(self):
        omega = (5. / self.car.wheel_radius_m,) * 3 + (-1.,)
        with self.assertRaisesRegex(ValueError, "nonnegative wheel speeds"):
            policy_layers.allocate("eco_neutral_off", total_drive_nm=100.,
                normal_loads_n=self.car.static_normal_loads_n, slip=ZERO,
                steer=0., u_mps=5., yaw_rate_rad_s=0., integral=0.,
                wheel_positions_m=self.car.wheel_positions_m,
                wheel_radius_m=self.car.wheel_radius_m,
                wheelbase_m=self.car.cg_to_front_axle_m+self.car.cg_to_rear_axle_m,
                wheel_speeds_rad_s=omega, mass_kg=self.car.mass_kg,
                nominal_mu=self.car.tire_mu, pack=self.fixture.actuation)

    def test_real_adapter_rejects_eco_negative_wheel_without_mutation(self):
        state = self.state()
        # The real initializer already rejects this domain. Exercise the direct
        # allocator boundary with an explicitly invalid typed powered input;
        # the load observation itself comes from the unchanged valid state.
        powered = state.thermal.light.powered
        invalid = replace(powered, plant=replace(powered.plant,
            wheel_speeds_rad_s=powered.plant.wheel_speeds_rad_s[:3] + (-1.,)))
        before = asdict(invalid)
        with self.assertRaisesRegex(ValueError, "nonnegative wheel speeds"):
            core_adapter.allocate_core("awd7-eco-neutral-off-v4", invalid,
                self.physical(state), ZERO, 100., 0., 0., self.car,
                self.fixture.actuation, core_adapter.case_for("awd7-eco-neutral-off-v4"))
        self.assertEqual(asdict(invalid), before)

    def test_adapter_rejects_simultaneous_drive_and_brake(self):
        state = self.state()
        before = asdict(state)
        for config in core_registry.IDS:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "Simultaneous"):
                core_adapter.allocate_core(config, state.thermal.light.powered,
                    self.physical(state), ZERO, 100., 20., 0., self.car,
                    self.fixture.actuation, core_adapter.case_for(config))
        self.assertEqual(asdict(state), before)

    def test_all_seven_matched_real_twenty_tick_probes(self):
        f = self.fixture
        steer = (.08, .08, 0., 0.)
        initial = asdict(self.state())
        for config in core_registry.IDS:
            with self.subTest(config=config):
                state = self.state()
                self.assertEqual(asdict(state), initial)
                record = {"policy_id": config, "role": "development_fixed_control_probe",
                    "fixture_sha256": f.configuration_sha256, "initial_state": asdict(state),
                    "course_or_original_admission_used": False, "ticks": [], "allocations": []}
                PROBE_RECORDS.append(record)
                integral, held = 0., ZERO
                for tick in range(20):
                    if tick % 10 == 0:
                        allocation = core_adapter.allocate_core(config,
                            state.thermal.light.powered,
                            self.physical(state, held=held, steer=steer), steer,
                            100., 0., integral, self.car, f.actuation, core_adapter.case_for(config))
                        integral, held = allocation.integral, allocation.limited.wheel_torques_nm
                        self.assertTrue(all(isfinite(t) and t >= 0 for t in held))
                        self.assertLessEqual(sum(allocation.proposed), 100. + 1e-8)
                        record["allocations"].append({"tick": tick, **asdict(allocation)})
                    old = asdict(state)
                    previous_work = (state.thermal.light.powered.integration_trials +
                                     state.thermal.light.powered.wheel_stop_events)
                    next_state = advance_tick(f.settings, f.thermal, f.drs_policy,
                        f.actuation, state, held, steer, ZERO, f.environment,
                        braking_requested=False, maximum_work=100)
                    self.assertEqual(asdict(state), old)
                    state = next_state
                    power = state.thermal.light.powered
                    self.assertEqual(state.drs.ticks, tick + 1)
                    self.assertEqual(state.thermal.thermal.ticks, tick + 1)
                    self.assertEqual(state.thermal.light.feedback_ticks, tick + 1)
                    self.assertGreater(power.integration_trials + power.wheel_stop_events, previous_work)
                    self.assertLessEqual(power.integration_trials + power.wheel_stop_events - previous_work, 100)
                    self.assertTrue(0 <= power.pack_energy_j <= 9_000_000.)
                    self.assertTrue(all(w >= 0 for w in power.plant.wheel_speeds_rad_s))
                    record["ticks"].append({"tick": tick + 1, "integral": integral,
                                           "state": asdict(state)})
                residual = energy_residual_j(self.car,
                    self.state().thermal.light.powered, state.thermal.light.powered)
                self.assertLess(abs(residual), .002 + 128 * 2.220446049250313e-16 *
                    f.actuation.pack_capacity_j * (power.integration_trials + 21))
                record.update(status="completed_fixed_twenty_tick_probe", mechanical_residual_j=residual)

    def test_standing_start_all_seven_one_tick(self):
        f = self.fixture
        for config in core_registry.IDS:
            with self.subTest(config=config):
                state = self.state(speed=0.)
                allocation = self.allocate(config, state, steer=ZERO)
                updated = advance_tick(f.settings, f.thermal, f.drs_policy, f.actuation,
                    state, allocation.limited.wheel_torques_nm, ZERO, ZERO, f.environment,
                    braking_requested=False, maximum_work=100)
                self.assertEqual(updated.drs.ticks, 1)
                self.assertGreaterEqual(updated.thermal.light.powered.plant.u_mps, 0.)
                self.assertLess(updated.thermal.light.powered.pack_energy_j, 9_000_000.)
                PROBE_RECORDS.append({"policy_id": config, "role": "development_one_tick_launch_probe",
                    "initial_state": asdict(state), "allocation": asdict(allocation),
                    "final_state": asdict(updated), "course_or_original_admission_used": False})

    def test_nonuniform_real_feedback_loads_drive_the_load_recipe(self):
        state = self.state(longitudinal_load=1., lateral_load=1.)
        physical = self.physical(state)
        loads = tuple(w.normal_load_n for w in physical.wheels)
        self.assertNotEqual(loads, self.car.static_normal_loads_n)
        result = self.allocate("awd7-load-off-v4", state, steer=ZERO)
        self.assertTrue(result.diagnostics["load_changed"])
        for torque, load in zip(result.proposed, loads):
            self.assertAlmostEqual(torque, 100. * load / sum(loads))
        self.assertAlmostEqual(sum(result.proposed), 100.)

    def test_real_overspeed_sheds_slip_and_freezes_combined_integral(self):
        speed = 5. / self.car.wheel_radius_m
        state = self.state(wheel_speeds=(1.4 * speed, speed, speed, speed))
        self.assertGreater(self.physical(state).wheels[0].slip_ratio, .1)
        slip = self.allocate("awd7-slip-off-v4", state, steer=ZERO)
        self.assertTrue(slip.diagnostics["slip_binding"])
        self.assertLess(slip.proposed[0], 25.)
        self.assertEqual(slip.proposed[1:], (25.,) * 3)
        combined = self.allocate("awd7-yaw-slip-off-v4", state, integral=.2)
        self.assertTrue(combined.diagnostics["yaw_changed"])
        self.assertTrue(combined.diagnostics["slip_binding"])
        self.assertTrue(combined.diagnostics["yaw_integral_frozen_by_slip"])
        self.assertEqual(combined.integral, .2)

    def test_feedforward_sign_symmetry_and_speed_scaling(self):
        for speed in (5., 10.):
            state = self.state(speed=speed)
            positive = self.allocate("awd7-feedforward-off-v4", state)
            negative = self.allocate("awd7-feedforward-off-v4", state,
                                     steer=(-.08, -.08, 0., 0.))
            for left, right in ((0, 1), (2, 3)):
                self.assertAlmostEqual(positive.proposed[left], negative.proposed[right])
                self.assertAlmostEqual(positive.proposed[right], negative.proposed[left])
            self.assertAlmostEqual(sum(positive.proposed), 100.)
        slow = self.allocate("awd7-feedforward-off-v4", self.state(speed=5.))
        self.assertAlmostEqual(positive.diagnostics["yaw_bias_requested_nm"],
                               2 * slow.diagnostics["yaw_bias_requested_nm"])

    def test_actual_electrical_limit_freezes_pi_memory(self):
        config = "awd7-yaw-pi-off-v4"
        ordinary = self.allocate(config, self.state(), integral=.1)
        self.assertGreater(ordinary.integral, .1)
        # Explicit synthetic stress variant, never a substituted car profile.
        act = replace(self.fixture.actuation, pack_discharge_power_limit_w=5.)
        state = self.state(actuation=act)
        result = self.allocate(config, state, integral=.1, actuation=act)
        self.assertTrue(result.limited.constraints)
        self.assertNotEqual(result.proposed, result.limited.wheel_torques_nm)
        self.assertTrue(result.diagnostics["antiwindup_actuator_limit_freeze"])
        self.assertEqual(result.integral, .1)

    def test_pi_command_saturation_freezes_and_opposite_error_unwinds(self):
        saturated = self.allocate("awd7-yaw-pi-off-v4", self.state(yaw=-2.),
            steer=(.4, .4, 0., 0.), integral=.8)
        self.assertTrue(saturated.diagnostics["yaw_integral_frozen"])
        self.assertEqual(saturated.integral, .8)
        unwind = self.allocate("awd7-yaw-pi-off-v4", self.state(yaw=.01),
            steer=ZERO, demand=.1, integral=1.)
        self.assertLess(unwind.integral, 1.)

    def test_eco_cost_matches_actual_forward_electrical_branch(self):
        state = self.state()
        result = self.allocate("awd7-eco-neutral-off-v4", state)
        self.assertEqual(result.proposed, result.limited.wheel_torques_nm)
        pack = self.fixture.actuation
        actual = constrain_actuation(pack, result.proposed,
            state.thermal.light.powered.plant.wheel_speeds_rad_s, 9_000_000., .01, AVAILABLE)
        self.assertAlmostEqual(result.diagnostics["energy_surrogate"]["surrogate_cost_w"],
                               actual.pack_power_w, places=8)

    def test_eco_infeasible_capacity_has_no_recipe_fallback(self):
        state = self.state(speed=20., yaw=2.)
        before = asdict(state)
        with self.assertRaisesRegex(ValueError, "No feasible energy allocation"):
            self.allocate("awd7-eco-neutral-off-v4", state, steer=ZERO)
        self.assertEqual(asdict(state), before)

    def test_zero_drive_braking_is_supported_without_pi_windup(self):
        state = self.state()
        for config in core_registry.IDS:
            with self.subTest(config=config):
                result = core_adapter.allocate_core(config, state.thermal.light.powered,
                    self.physical(state), ZERO, 0., 20., .3, self.car,
                    self.fixture.actuation, core_adapter.case_for(config))
                self.assertEqual(result.proposed, ZERO)
                self.assertEqual(result.integral, .3)
                self.assertEqual(result.total_brake, 20.)
                self.assertEqual(result.raw_regen, 0.)

    def test_zero_contact_load_does_not_substitute_equal_split(self):
        with self.assertRaisesRegex(ValueError, "No supported contact load"):
            policy_layers.allocate("load_off", total_drive_nm=100., normal_loads_n=ZERO,
                slip=ZERO, steer=0., u_mps=5., yaw_rate_rad_s=0., integral=0.,
                wheel_positions_m=self.car.wheel_positions_m,
                wheel_radius_m=self.car.wheel_radius_m,
                wheelbase_m=self.car.cg_to_front_axle_m+self.car.cg_to_rear_axle_m,
                wheel_speeds_rad_s=(5./self.car.wheel_radius_m,) * 4,
                mass_kg=self.car.mass_kg, nominal_mu=self.car.tire_mu, pack=self.fixture.actuation)

    def test_global_work_rebasing_preserves_actual_physics(self):
        f = self.fixture
        state = self.state()
        old = state.thermal.light.powered
        large = replace(old, integration_trials=60_000, integration_substeps=50_000,
                        wheel_stop_events=3)
        altered = replace(state, thermal=replace(state.thermal,
            light=replace(state.thermal.light, powered=large)))
        def step(s):
            return advance_tick(f.settings, f.thermal, f.drs_policy, f.actuation,
                s, (20.,) * 4, ZERO, ZERO, f.environment,
                braking_requested=False, maximum_work=100)
        ordinary, high = step(state), step(altered)
        hp, op = high.thermal.light.powered, ordinary.thermal.light.powered
        normalized = replace(hp, integration_trials=hp.integration_trials-60_000,
            integration_substeps=hp.integration_substeps-50_000,
            wheel_stop_events=hp.wheel_stop_events-3)
        self.assertEqual(asdict(normalized), asdict(op))
        self.assertEqual(high.thermal.thermal, ordinary.thermal.thermal)
        self.assertEqual(high.drs, ordinary.drs)

    def test_bounded_probes_cannot_promote_registry_eligibility(self):
        self.assertEqual(len(core_registry.entries()), 7)
        for entry in core_registry.entries():
            self.assertEqual(entry["native_qualification"], "UNRUN")
            self.assertIs(entry["campaign_eligible"], False)


if __name__ == "__main__":
    unittest.main()
