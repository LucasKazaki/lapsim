"""TC-02U pure arithmetic contract for STM32F4 IWDG timing evidence."""
from dataclasses import dataclass
import math

PRESCALERS=(4,8,16,32,64,128,256)
MAX_RELOAD=4095
ST_HAL_COMMIT="1f6451c3e07728b4c830744de380e56bf5bc0026"
ST_IWDG_HEADER_BLOB="5273730c147899c6fa48370ec34a4bb05b60a187"
ST_IWDG_SOURCE_BLOB="bc03a530b84ea913de0cb44d76d1c8d3e009fb9c"

@dataclass(frozen=True)
class Interval:
    cycles:int
    earliest_s:float
    nominal_s:float
    latest_s:float
    action_authority:bool=False


def compute(prescaler:int,reload:int,f_min_hz:float,f_nom_hz:float,f_max_hz:float)->Interval:
    if isinstance(prescaler,bool) or prescaler not in PRESCALERS: raise ValueError("prescaler")
    if isinstance(reload,bool) or not isinstance(reload,int) or not 0<=reload<=MAX_RELOAD: raise ValueError("reload")
    vals=(f_min_hz,f_nom_hz,f_max_hz)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)) for v in vals): raise ValueError("frequency")
    lo,nom,hi=map(float,vals)
    if not 0<lo<=nom<=hi: raise ValueError("frequency order")
    cycles=(reload+1)*prescaler
    return Interval(cycles,cycles/hi,cycles/nom,cycles/lo)


def refresh_gap_guaranteed(interval:Interval,max_gap_s:float)->bool:
    return math.isfinite(max_gap_s) and max_gap_s>=0 and max_gap_s<interval.earliest_s


def reset_deadline_guaranteed(interval:Interval,deadline_s:float)->bool:
    return math.isfinite(deadline_s) and deadline_s>=0 and interval.latest_s<=deadline_s


def frozen_counterexample():
    x=compute(32,999,17000,32000,47000)
    return {
        "nominal_s":x.nominal_s,
        "earliest_s":x.earliest_s,
        "latest_s":x.latest_s,
        "nominal_says_0_9_refresh_ok":0.9<x.nominal_s,
        "interval_says_0_9_refresh_ok":refresh_gap_guaranteed(x,0.9),
        "nominal_says_1_5_deadline_ok":x.nominal_s<=1.5,
        "interval_says_1_5_deadline_ok":reset_deadline_guaranteed(x,1.5),
        "terps_racing_setting":False,
        "action_authority":False,
    }
