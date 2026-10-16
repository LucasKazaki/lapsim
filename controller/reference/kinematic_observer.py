"""TC-01C portable kinematic plausibility observer.

Synthetic/offline only. A mismatch does not prove tire slip, sensor failure,
traction loss, yaw instability, or vehicle acceptance.
"""
from dataclasses import asdict, dataclass
import json, math

SCHEMA="enme408-tc01c-kinematic-observer/v1"

class ObserverError(ValueError): pass

def _finite(v,name):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)):
        raise ObserverError(f"{name} must be finite")
    return float(v)

def _vec(v,n,name):
    if not isinstance(v,(tuple,list)) or len(v)!=n:
        raise ObserverError(f"{name} must contain {n} values")
    return tuple(_finite(x,f"{name}[{i}]") for i,x in enumerate(v))

@dataclass(frozen=True)
class Reference:
    wheel_mps: tuple[float,float,float,float]
    steer_rad: tuple[float,float]
    source_ref: str="TC-01B"
    def checked(self):
        w=_vec(self.wheel_mps,4,"reference.wheel_mps")
        if any(x<0 for x in w): raise ObserverError("reference wheel speeds must be nonnegative")
        s=_vec(self.steer_rad,2,"reference.steer_rad")
        if not isinstance(self.source_ref,str) or not self.source_ref.strip(): raise ObserverError("source_ref required")
        return Reference(w,s,self.source_ref.strip())

@dataclass(frozen=True)
class Observation:
    wheel_mps: tuple[float,float,float,float]
    steer_rad: tuple[float,float]
    wheel_unit: str="m/s"
    steer_unit: str="rad"
    def checked(self):
        if self.wheel_unit!="m/s": raise ObserverError("wheel_unit must be m/s")
        if self.steer_unit!="rad": raise ObserverError("steer_unit must be rad")
        return Observation(_vec(self.wheel_mps,4,"observation.wheel_mps"),_vec(self.steer_rad,2,"observation.steer_rad"),self.wheel_unit,self.steer_unit)

@dataclass(frozen=True)
class Tolerance:
    wheel_abs_mps: float
    wheel_rel: float
    steer_abs_rad: float
    floor_mps: float=0.1
    def checked(self):
        vals=[_finite(self.wheel_abs_mps,"wheel_abs_mps"),_finite(self.wheel_rel,"wheel_rel"),_finite(self.steer_abs_rad,"steer_abs_rad"),_finite(self.floor_mps,"floor_mps")]
        if any(x<0 for x in vals[:3]) or vals[3]<=0: raise ObserverError("invalid tolerance")
        return Tolerance(*vals)

@dataclass(frozen=True)
class Result:
    schema: str
    plausible: bool
    wheel_residual_mps: tuple[float,float,float,float]
    steer_residual_rad: tuple[float,float]
    blockers: tuple[str,...]
    slip_proven: bool=False
    sensor_failure_proven: bool=False
    vehicle_acceptance_proven: bool=False
    action_authority: bool=False
    def to_json(self):
        d=asdict(self)
        for k in ("wheel_residual_mps","steer_residual_rad","blockers"): d[k]=list(d[k])
        return json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False)

def observe(reference,observation,tolerance):
    r,o,t=reference.checked(),observation.checked(),tolerance.checked()
    wr=tuple(a-b for a,b in zip(o.wheel_mps,r.wheel_mps))
    sr=tuple(a-b for a,b in zip(o.steer_rad,r.steer_rad))
    blockers=[]
    names=("front_left","front_right","rear_left","rear_right")
    for name,res,expected in zip(names,wr,r.wheel_mps):
        limit=t.wheel_abs_mps+t.wheel_rel*max(abs(expected),t.floor_mps)
        if abs(res)>limit: blockers.append(f"wheel:{name}:kinematic_mismatch")
    for name,res in zip(("front_left","front_right"),sr):
        if abs(res)>t.steer_abs_rad: blockers.append(f"steering:{name}:kinematic_mismatch")
    return Result(SCHEMA,not blockers,wr,sr,tuple(blockers))

def equal_speed_counterexample():
    ref=Reference(
        (7.508635225738027,9.061055425643401,7.196152422706633,8.803847577293368),
        (0.2895111739035429,0.2388363511581407),
        "TC-01B synthetic 1.6m/1.2m/8mps/15deg fixture",
    )
    obs=Observation((8.0,8.0,8.0,8.0),ref.steer_rad)
    result=observe(ref,obs,Tolerance(0.05,0.01,math.radians(0.5)))
    return {"plausible":result.plausible,"rear_residual_mps":result.wheel_residual_mps[2:],"slip_proven":False,"action_authority":False}
