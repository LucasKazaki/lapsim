"""Independent electrical/energy identities across declared synthetic topologies."""
from dataclasses import replace
from itertools import product
from math import isfinite
from unittest import TestCase

from lapsim.dynamics.actuation import (
    ActuationConfig, AWD_TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID,
    TOPOLOGY_ID, constrain_actuation,
)


class DrivetrainInvariantTests(TestCase):
    def test_shared_limits_and_independent_power_ledger(self):
        limits = ({}, {'pack_discharge_power_limit_w': 31.0},
                  {'pack_charge_power_limit_w': 13.0},
                  {'pack_discharge_current_limit_a': .05, 'pack_charge_current_limit_a': .02})
        speeds = ((0., 0., 0., 0.), (1., 1., .01, .03), (10., 10., 10., 30.),
                  (30., 30., 30., 30.), (180., 180., 140., 220.))
        for topology, limit, total, omega, fraction in product(
                (TOPOLOGY_ID, SINGLE_MOTOR_RWD_TOPOLOGY_ID, AWD_TOPOLOGY_ID),
                limits, (-1000., -80., 0., 80., 1000.), speeds, (0., 1e-9, .5, 1.-1e-9, 1.)):
            with self.subTest(topology=topology, limit=limit, total=total, omega=omega, soc=fraction):
                config = replace(ActuationConfig(), topology_id=topology, **limit)
                available = (True,)*4 if topology == AWD_TOPOLOGY_ID else (False, False, True, True)
                count = sum(available)
                request = tuple(total/count if active else 0. for active in available)
                energy = fraction*config.pack_capacity_j
                interval = .02
                out = constrain_actuation(config, request, omega, energy, interval, available)
                self.assertTrue(all(isfinite(x) for x in (*out.wheel_torques_nm,
                    *out.motor_currents_a, out.pack_power_w, out.conversion_loss_w)))
                # Contact-side work is independently reconstructed from actual
                # wheel outputs, not the virtual carrier used by the adapter.
                wheel_work_rate = sum(t*w for t,w in zip(out.wheel_torques_nm, omega, strict=True))
                self.assertAlmostEqual(wheel_work_rate, out.wheel_power_w, delta=1e-8)
                motor_work_rates = [t*w for t,w in zip(out.motor_torques_nm, out.motor_speeds_rad_s, strict=True)]
                expected_bus = 0.
                for work, current in zip(motor_work_rates, out.motor_currents_a, strict=True):
                    motor_dc = (work/config.motor_conversion_efficiency if work >= 0
                                else work*config.motor_conversion_efficiency)
                    motor_dc += current*current*config.equivalent_copper_resistance_ohm
                    expected_bus += (motor_dc/config.inverter_efficiency if motor_dc >= 0
                                     else motor_dc*config.inverter_efficiency)
                self.assertAlmostEqual(expected_bus, out.pack_power_w, delta=1e-8)
                self.assertAlmostEqual(out.pack_power_w-wheel_work_rate, out.conversion_loss_w, delta=1e-8)
                self.assertGreaterEqual(out.conversion_loss_w, -1e-8)
                self.assertLessEqual(out.pack_power_w, config.pack_discharge_power_limit_w+1e-8)
                self.assertGreaterEqual(out.pack_power_w, -config.pack_charge_power_limit_w-1e-8)
                self.assertLessEqual(out.pack_current_a, config.pack_discharge_current_limit_a+1e-8)
                self.assertGreaterEqual(out.pack_current_a, -config.pack_charge_current_limit_a-1e-8)
                after = energy-out.pack_power_w*interval
                self.assertGreaterEqual(after, -1e-8)
                self.assertLessEqual(after, config.pack_capacity_j+1e-8)
                self.assertLessEqual(max(abs(i) for i in out.motor_currents_a),
                    min(config.motor_current_limit_a, config.inverter_current_limit_a)+1e-8)
                for asked, actual in zip(request, out.wheel_torques_nm, strict=True):
                    self.assertLessEqual(abs(actual), abs(asked)+1e-8)
                    self.assertGreaterEqual(asked*actual, -1e-8)
                if topology == SINGLE_MOTOR_RWD_TOPOLOGY_ID:
                    self.assertEqual(out.wheel_torques_nm[2], out.wheel_torques_nm[3])
                    self.assertEqual(out.motor_currents_a[3], 0.)
                    self.assertEqual(out.motor_speeds_rad_s[2],
                        config.gear_ratio*(omega[2]/2+omega[3]/2))

    def test_single_motor_stall_copper_loss_is_one_unit(self):
        # At identical carrier speed/request, a single motor and two motors
        # should not silently share the same loss/current interpretation.
        one = replace(ActuationConfig(), topology_id=SINGLE_MOTOR_RWD_TOPOLOGY_ID)
        two = replace(one, topology_id=TOPOLOGY_ID)
        a = constrain_actuation(one, (0,0,40,40), (0,)*4, 1e6, .02)
        b = constrain_actuation(two, (0,0,40,40), (0,)*4, 1e6, .02)
        self.assertAlmostEqual(a.pack_power_w, 2*b.pack_power_w, places=10)
        self.assertEqual(a.wheel_power_w, b.wheel_power_w)

    def test_open_diff_output_speed_swap_preserves_energy_and_torque(self):
        config = replace(ActuationConfig(), topology_id=SINGLE_MOTOR_RWD_TOPOLOGY_ID)
        for effort in (-80., 0., 80.):
            with self.subTest(effort=effort):
                a = constrain_actuation(config, (0,0,effort,effort), (0,0,10,30), 1e6, .02)
                b = constrain_actuation(config, (0,0,effort,effort), (0,0,30,10), 1e6, .02)
                self.assertEqual(a, b)
