"""AWD command contracts extracted without fixture/driver construction.

UNTESTED source-only candidate; no campaign or execution authority.
"""
from dataclasses import replace
from math import isfinite
from lapsim_light_core.planar import PlanarControls

AVAILABLE=(True,True,True,True)
STEERING_MODEL='parallel_front_v1'
TOTAL_DRIVE_MAX_NM=190.

def require(value,message):
    if not value:raise ValueError(message)
def four(values,name):
    require(type(values) in (tuple,list) and len(values)==4 and
            all(type(v) in (int,float) and isfinite(v) for v in values),'Four finite '+name)
    return tuple(values)
def steering(values):
    angles=four(values,'wheel steer rad')
    require(all(abs(v)<=.4 for v in angles) and angles[0]==angles[1] and angles[2:]==(0.,0.),
            'Explicit parallel front steering required;no silent Ackermann/rear-steer approximation')
    return angles
def validate_driver_command(command):
    require(type(command) is PlanarControls,'Typed common driver controls')
    steering(command.steering_angles_rad)
    drive=four(command.drive_torques_nm,'AWD baseline wheel Nm');brakes=four(command.brake_torques_nm,'brake Nm')
    require(all(0<=v<=TOTAL_DRIVE_MAX_NM/4 for v in drive) and len(set(drive))==1 and
            all(0<=v<=80. for v in brakes) and len(set(brakes))==1 and
            not(sum(drive)>0 and sum(brakes)>0),'Common normalized AWD drive/brake demand')
    require(command.normal_loads_n is None and command.wheel_radii_m is None and
            command.external_force_x_n==command.external_force_y_n==command.external_yaw_moment_nm==0,
            'Driver cannot override tire loads/radii or inject unrecorded forces')
    return command
def normalize_driver_command(command):
    """The existing pose driver generates scalar demand as two rear proxies.

    Convert once before saving/allocating: total stays2*proxy, all four authoritative
    drive channels are equal. This is a demand adapter,never rear actuator fallback.
    """
    require(type(command) is PlanarControls,'Known pose-driver controls required')
    steering(command.steering_angles_rad);drive=four(command.drive_torques_nm,'legacy driver proxy')
    require(drive[0]==drive[1]==0. and drive[2]==drive[3] and 0<=drive[2]<=95.,
            'Exact bounded legacy pose-driver scalar demand;no double conversion')
    mapped=replace(command,drive_torques_nm=(sum(drive)/4,)*4)
    return validate_driver_command(mapped)
