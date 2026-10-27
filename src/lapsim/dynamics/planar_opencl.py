"""Optional FP64 GPU batch of the existing planar force/derivative evaluation.

One work item is one independent instantaneous state. Road lookup remains on
the host and uses the identical validated road object at each wheel position.
This is a numerical primitive, NOT a powered integrator, lap solver or GPU GA.
In particular it does not replace pack constraints, shaft coupling, actuator
memory, brake events or any of the tournament's separate clocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin
from time import perf_counter
from typing import Sequence

import numpy as np

from lapsim.backends.opencl_runtime import OpenCLKernel
from .conditions import PlanarEnvironment
from .planar import (PlanarControls, PlanarDerivative, PlanarEvaluation, PlanarState,
                     PlanarVehicleConfig, PlanarWheel, evaluate_planar_dynamics)


@dataclass(frozen=True)
class PlanarSample:
    config: PlanarVehicleConfig
    state: PlanarState
    controls: PlanarControls
    environment: PlanarEnvironment = PlanarEnvironment()

    def __post_init__(self) -> None:
        for value, expected in ((self.config, PlanarVehicleConfig), (self.state, PlanarState),
                                (self.controls, PlanarControls), (self.environment, PlanarEnvironment)):
            if not isinstance(value, expected):
                raise TypeError(f"Expected {expected.__name__}")


GLOBAL_FIELDS = (
    "x_dot_mps", "y_dot_mps", "heading_dot_rad_s", "u_dot_mps2", "v_dot_mps2",
    "yaw_rate_dot_rad_s2", "fl_omega_dot_rad_s2", "fr_omega_dot_rad_s2",
    "rl_omega_dot_rad_s2", "rr_omega_dot_rad_s2", "total_body_force_x_n",
    "total_body_force_y_n", "total_yaw_moment_nm", "cg_longitudinal_acceleration_mps2",
    "cg_lateral_acceleration_mps2", "mechanical_energy_j", "mechanical_energy_rate_w",
    "drive_power_w", "brake_power_w", "external_power_w", "aero_power_w",
    "aero_body_force_x_n", "aero_body_force_y_n", "air_relative_body_x_mps",
    "air_relative_body_y_mps", "apparent_air_speed_mps", "contact_dissipation_w",
    "energy_balance_residual_w", "invalid_road_queries",
)
WHEEL_FIELDS = (
    "normal_load_n", "local_velocity_x_mps", "local_velocity_y_mps", "slip_ratio",
    "slip_angle_rad", "local_force_x_n", "local_force_y_n", "body_force_x_n",
    "body_force_y_n", "applied_brake_torque_nm", "friction_limit_n",
    "world_contact_x_m", "world_contact_y_m", "road_friction_multiplier", "road_valid",
)
FIELDS = GLOBAL_FIELDS + tuple(f"{wheel}.{field}" for wheel in ("FL", "FR", "RL", "RR") for field in WHEEL_FIELDS)
INPUT_COLUMNS = 60


def pack_samples(samples: Sequence[PlanarSample]) -> np.ndarray:
    """Pack SI inputs and exact host road samples; no cached defaults or state."""
    if not 1 <= len(samples) <= 65536:
        raise ValueError("Require 1..65536 planar samples")
    packed = np.empty((len(samples), INPUT_COLUMNS), dtype=np.float64)
    for index, sample in enumerate(samples):
        if not isinstance(sample, PlanarSample):
            raise TypeError("Expected PlanarSample entries")
        c, s, u, e = sample.config, sample.state, sample.controls, sample.environment
        positions=c.wheel_positions_m
        if not e.road.patches and e.road.valid_domain is None:
            # Exact uniform-road fast path; no coordinate affects this query.
            grip=(e.road.base_friction_multiplier,)*4
            valid=(True,)*4
        else:
            hc, hs = cos(s.heading_rad), sin(s.heading_rad)
            road = [e.road.query(s.x_m + hc*x - hs*y, s.y_m + hs*x + hc*y)
                    for x, y in positions]
            grip=tuple(r.friction_multiplier for r in road)
            valid=tuple(r.valid for r in road)
        packed[index] = (
            c.mass_kg, c.yaw_inertia_kgm2, c.wheel_inertia_kgm2, c.tire_mu,
            c.longitudinal_stiffness_n_per_slip, c.cornering_stiffness_n_per_rad,
            c.low_speed_regularization_mps, s.x_m, s.y_m, s.heading_rad,
            s.u_mps, s.v_mps, s.yaw_rate_rad_s, *s.wheel_speeds_rad_s,
            *u.steering_angles_rad, *u.drive_torques_nm, *u.brake_torques_nm,
            *(c.static_normal_loads_n if u.normal_loads_n is None else u.normal_loads_n),
            *(u.wheel_radii_m or (c.wheel_radius_m,) * 4),
            *(p[0] for p in positions), *(p[1] for p in positions), *grip, *valid,
            u.external_force_x_n, u.external_force_y_n, u.external_yaw_moment_nm,
            e.wind_world_x_mps, e.wind_world_y_mps, e.air_density_kgpm3, e.drag_area_m2,
        )
    if not np.isfinite(packed).all():
        raise ValueError("Packed planar input exceeds finite numerical domain")
    return packed


def flatten_evaluation(evaluation: PlanarEvaluation) -> np.ndarray:
    """Stable SI column contract for independent CPU/GPU comparison."""
    d = evaluation.derivative
    return np.asarray((d.x_dot_mps, d.y_dot_mps, d.heading_dot_rad_s, d.u_dot_mps2,
        d.v_dot_mps2, d.yaw_rate_dot_rad_s2, *d.wheel_accelerations_rad_s2,
        *(getattr(evaluation, field) for field in GLOBAL_FIELDS[10:]),
        *(getattr(wheel, field) for wheel in evaluation.wheels for field in WHEEL_FIELDS)), dtype=np.float64)


def evaluate_cpu(samples: Sequence[PlanarSample]) -> np.ndarray:
    return np.vstack([flatten_evaluation(evaluate_planar_dynamics(s.config, s.state,
        s.controls, environment=s.environment)) for s in samples])


def unpack_evaluation(sample: PlanarSample, row: np.ndarray) -> PlanarEvaluation:
    """Recover the existing typed force contract from a validated device row."""
    if row.shape != (len(FIELDS),) or not np.isfinite(row).all():
        raise ValueError('Invalid GPU evaluation row')
    derivative = PlanarDerivative(x_dot_mps=float(row[0]),y_dot_mps=float(row[1]),
        heading_dot_rad_s=float(row[2]),u_dot_mps2=float(row[3]),v_dot_mps2=float(row[4]),
        yaw_rate_dot_rad_s2=float(row[5]),wheel_accelerations_rad_s2=(
            float(row[6]),float(row[7]),float(row[8]),float(row[9])))
    wheels=[]
    for i in range(4):
        start=29+15*i
        v=[float(value) for value in row[start:start+15]]
        road=sample.environment.road.query(v[11],v[12])
        wheels.append(PlanarWheel(normal_load_n=v[0],local_velocity_x_mps=v[1],
            local_velocity_y_mps=v[2],slip_ratio=v[3],slip_angle_rad=v[4],
            local_force_x_n=v[5],local_force_y_n=v[6],body_force_x_n=v[7],body_force_y_n=v[8],
            applied_brake_torque_nm=v[9],friction_limit_n=v[10],world_contact_x_m=v[11],
            world_contact_y_m=v[12],road_friction_multiplier=v[13],road_valid=bool(v[14]),
            road_material_id=road.material_id))
    return PlanarEvaluation(derivative=derivative,wheels=(wheels[0],wheels[1],wheels[2],wheels[3]),
        total_body_force_x_n=float(row[10]),total_body_force_y_n=float(row[11]),
        total_yaw_moment_nm=float(row[12]),cg_longitudinal_acceleration_mps2=float(row[13]),
        cg_lateral_acceleration_mps2=float(row[14]),mechanical_energy_j=float(row[15]),
        mechanical_energy_rate_w=float(row[16]),drive_power_w=float(row[17]),brake_power_w=float(row[18]),
        external_power_w=float(row[19]),aero_power_w=float(row[20]),aero_body_force_x_n=float(row[21]),
        aero_body_force_y_n=float(row[22]),air_relative_body_x_mps=float(row[23]),
        air_relative_body_y_mps=float(row[24]),apparent_air_speed_mps=float(row[25]),
        contact_dissipation_w=float(row[26]),energy_balance_residual_w=float(row[27]),
        invalid_road_queries=int(row[28]),road_valid=bool(row[28]==0))


# This is the algebra in planar.evaluate_planar_dynamics, not a different tire
# model. FP contraction and relaxed math are disabled; FP64 is mandatory. Host
# tests compare every named output, including brakes, contact work and residual.
PLANAR_FUNCTION = r"""
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
#pragma OPENCL FP_CONTRACT OFF
void planar_one(const double *p, double *out) {
    const double mass=p[0], inertia=p[1], wheel_inertia=p[2];
    const double u=p[10], v=p[11], r=p[12];
    const double hc=cos(p[9]), hs=sin(p[9]);
    const double airx=u-(hc*p[56]+hs*p[57]);
    const double airy=v-(-hs*p[56]+hc*p[57]);
    const double airspeed=hypot(airx,airy);
    const double drag=-0.5*p[58]*p[59]*airspeed;
    const double aerox=drag*airx, aeroy=drag*airy;
    const double aerop=aerox*u+aeroy*v;
    double fx=0, fy=0, moment=0, diss=0, drivep=0, brakep=0;
    double energy=0.5*mass*(u*u+v*v)+0.5*inertia*r*r, wheelrate=0;
    double invalid=0;
    for (int i=0; i<4; i++) {
        const double px=p[37+i], py=p[41+i], omega=p[13+i];
        const double c=cos(p[17+i]), s=sin(p[17+i]);
        const double vx=c*(u-r*py)+s*(v+r*px);
        const double vy=-s*(u-r*py)+c*(v+r*px);
        const double radius=p[33+i], surface=radius*omega, load=p[29+i];
        const double cap=p[3]*p[45+i]*load;
        double slip=0, angle=0, localx=0, localy=0;
        if (load != 0) {
            const double reference=fmax(fabs(vx),p[6]);
            slip=(surface-vx)/reference;
            angle=atan2(vy,reference);
            const double rx=p[4]*slip, ry=-p[5]*angle;
            const double magnitude=hypot(rx,ry);
            const double scale=magnitude>0 ? fmin(1.0,cap/magnitude) : 1.0;
            localx=scale*rx; localy=scale*ry;
        }
        const double bodyx=c*localx-s*localy, bodyy=s*localx+c*localy;
        fx+=bodyx; fy+=bodyy; moment+=px*bodyy-py*bodyx;
        const double torque=p[21+i], request=p[25+i];
        const double unbraked=torque-radius*localx;
        double brake;
        if (omega>0) brake=-request;
        else if (omega<0) brake=request;
        else if (unbraked>0) brake=-fmin(request,unbraked);
        else brake=fmin(request,-unbraked);
        const double acceleration=(unbraked+brake)/wheel_inertia;
        out[6+i]=acceleration;
        drivep+=torque*omega; brakep+=brake*omega;
        diss+=localx*(surface-vx)-localy*vy;
        energy+=0.5*wheel_inertia*omega*omega;
        wheelrate+=omega*acceleration;
        invalid+=(p[49+i]==0);
        double *w=out+29+15*i;
        w[0]=load; w[1]=vx; w[2]=vy; w[3]=slip; w[4]=angle;
        w[5]=localx; w[6]=localy; w[7]=bodyx; w[8]=bodyy;
        w[9]=brake; w[10]=cap;
        w[11]=p[7]+hc*px-hs*py; w[12]=p[8]+hs*px+hc*py;
        w[13]=p[45+i]; w[14]=p[49+i];
    }
    fx+=p[53]+aerox; fy+=p[54]+aeroy; moment+=p[55];
    const double du=r*v+fx/mass, dv=-r*u+fy/mass, dr=moment/inertia;
    const double rate=mass*(u*du+v*dv)+inertia*r*dr+wheel_inertia*wheelrate;
    const double external=u*p[53]+v*p[54]+r*p[55]+aerop;
    out[0]=u*hc-v*hs; out[1]=u*hs+v*hc; out[2]=r;
    out[3]=du; out[4]=dv; out[5]=dr;
    out[10]=fx; out[11]=fy; out[12]=moment;
    out[13]=fx/mass; out[14]=fy/mass; out[15]=energy; out[16]=rate;
    out[17]=drivep; out[18]=brakep; out[19]=external; out[20]=aerop;
    out[21]=aerox; out[22]=aeroy; out[23]=airx; out[24]=airy;
    out[25]=airspeed; out[26]=diss;
    out[27]=rate-drivep-brakep+diss-external; out[28]=invalid;
}
"""

KERNEL = PLANAR_FUNCTION + r"""
__kernel void planar_evaluate(__global const double *inputs,
                              __global double *outputs, const uint count) {
    const uint lane=get_global_id(0);
    if(lane>=count) return;
    double p[60],out[89];
    for(int i=0;i<60;i++)p[i]=inputs[lane*60+i];
    planar_one(p,out);
    for(int i=0;i<89;i++)outputs[lane*89+i]=out[i];
}
"""


class PlanarOpenCL:
    """Explicit GPU evaluator; construction compiles on the selected device."""

    def __init__(self, *, device_name: str):
        self.runtime = OpenCLKernel(KERNEL, "planar_evaluate", device_name=device_name)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.runtime.close()

    def evaluate(self, samples: Sequence[PlanarSample]) -> tuple[np.ndarray, dict]:
        started = perf_counter()
        packed = pack_samples(samples)
        packing_s = perf_counter() - started
        result, evidence = self.runtime.execute(packed, len(FIELDS))
        return result, {**evidence, "host_packing_road_lookup_s": packing_s,
            "total_batch_s": perf_counter() - started,
            "scope": "Instantaneous planar forces/derivatives only; not a powered rollout"}

    def evaluate_objects(self, samples: Sequence[PlanarSample]) -> tuple[list[PlanarEvaluation], dict]:
        values,evidence=self.evaluate(samples)
        return [unpack_evaluation(sample,row) for sample,row in zip(samples,values,strict=True)],evidence
