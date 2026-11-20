"""Privileged environment scoring; this module never constructs policy inputs."""

from dataclasses import dataclass

from .contracts import TIME_TOLERANCE_S, driver_frame_budget, finite


@dataclass(frozen=True, slots=True)
class ScoreFrame:
    elapsed_s: float
    # Continuous locally unwrapped station, from the environment's projector.
    progress_m: float
    footprint_inside: bool
    cone_collision: bool
    finish_gate_crossed: bool
    ordered_route_valid: bool = True
    stalled: bool = False  # private evaluation flag; never a policy observation
    earned_gate_count: int | None = None  # owner-derived valid1ms crossings only

    segment_complete: bool = False  # private task result, NEVER a lap
    mission_kind: str = 'lap'

    def __post_init__(self) -> None:
        if (type(self.segment_complete) is not bool or self.mission_kind not in ('lap','segment')
                or (self.mission_kind=='lap' and self.segment_complete)
                or (self.mission_kind=='segment' and self.finish_gate_crossed)):
            raise ValueError('explicit nonaliased mission completion required')
        finite(self.elapsed_s, "elapsed time")
        finite(self.progress_m, "progress")
        if any(
            type(getattr(self, name)) is not bool
            for name in ("footprint_inside", "cone_collision", "finish_gate_crossed", "ordered_route_valid", "stalled")
        ):
            raise ValueError("explicit environment gate flags required")


class LapScorer:
    """Completion v2: valid furthest distance, retained credit minus100 on failure.

    Station bounds reject obvious jumps; they are not an authenticated timing
    gate or swept-footprint proof. The backend must supply those separately.
    """

    def __init__(self, *, length_m: float, maximum_time_s: float):
        finite(length_m, "lap length")
        finite(maximum_time_s, "time limit")
        if length_m <= 0.0 or not 0.0 < maximum_time_s <= 600.0:
            raise ValueError("finite positive lap length and time cap required")
        driver_frame_budget(maximum_time_s)
        self.length_m, self.maximum_time_s = length_m, maximum_time_s
        self.progress_m = self.elapsed_s = self._station_m = self.total_reward = 0.0
        self.valid_lap = False
        self.termination: str | None = None

    def step(self, frame: ScoreFrame) -> float:
        if self.termination is not None:
            raise RuntimeError("terminal episode cannot resume")
        if type(frame) is not ScoreFrame or frame.mission_kind!='lap':
            raise TypeError("privileged LAP score frame required")
        dt = frame.elapsed_s - self.elapsed_s
        if (
            not 0.0 < dt <= 2.0
            or frame.elapsed_s > self.maximum_time_s + TIME_TOLERANCE_S
        ):
            raise ValueError("invalid or exhausted scorer clock")
        if abs(frame.progress_m - self._station_m) > 40.0 * dt + 0.25:
            raise ValueError("unphysical progress jump or projection branch change")
        if frame.progress_m > self.length_m + 40.0 * dt + 0.25:
            raise ValueError("more than one lap of progress")
        reward = 0.0  # Completion training: no per-second deduction.
        # Reject leaving/colliding before rewarding progress from that step.
        if not frame.footprint_inside or not frame.ordered_route_valid:
            reward -= 100.0
            self.termination = "off_course"
        elif frame.cone_collision:
            reward -= 100.0
            self.termination = "cone_collision"
        elif frame.stalled:
            reward -= 100.0
            self.termination = "stalled"
        else:
            next_progress = max(self.progress_m, min(self.length_m, frame.progress_m))
            reward += next_progress - self.progress_m
            self.progress_m = next_progress
            if frame.finish_gate_crossed and frame.progress_m >= self.length_m - 1e-6:
                self.valid_lap = True
                self.termination = "lap_complete"
                reward += 100.0  # Fixed legal-finish bonus; time/energy deferred.
            elif frame.elapsed_s >= self.maximum_time_s - TIME_TOLERANCE_S:
                self.termination = "time_limit"
        self.elapsed_s, self._station_m = frame.elapsed_s, frame.progress_m
        self.total_reward += reward
        return reward


GATE_EARNED_CONTRACT = 'lapsim.completion-valid-ordered-gates.v1'

class GateLapScorer(LapScorer):
    """Credit only distance established by valid ordered physical crossings.

    A frame may carry gates earned on earlier valid1ms ticks before an invalid
    terminal tick. No new credit originates from that invalid tick. The owner
    and both full replays independently derive earned_gate_count from geometry.
    """
    def __init__(self,*,length_m,maximum_time_s):
        super().__init__(length_m=length_m,maximum_time_s=maximum_time_s)
        from math import ceil
        self.maximum_gate_count=ceil(length_m/5.)-1
        self.earned_gate_count=0

    def step(self,frame):
        if self.termination is not None:raise RuntimeError('terminal episode cannot resume')
        if type(frame) is not ScoreFrame or frame.mission_kind!='lap':raise TypeError('privileged LAP score frame required')
        dt=frame.elapsed_s-self.elapsed_s
        if not 0.<dt<=2. or frame.elapsed_s>self.maximum_time_s+TIME_TOLERANCE_S:
            raise ValueError('invalid or exhausted scorer clock')
        n=frame.earned_gate_count
        if type(n) is not int or not self.earned_gate_count<=n<=self.maximum_gate_count:
            raise ValueError('finite monotone independently earned gate count required')
        legal_finish=(frame.finish_gate_crossed and frame.footprint_inside
                      and not frame.cone_collision and frame.ordered_route_valid and not frame.stalled)
        if frame.finish_gate_crossed and (not legal_finish or n!=self.maximum_gate_count):
            raise ValueError('finish needs all ordered gates and valid physical crossing')
        expected=self.length_m if legal_finish else n*5.
        if frame.progress_m!=expected:raise ValueError('gate-earned distance claim differs')
        reward=expected-self.progress_m
        self.progress_m=expected;self.earned_gate_count=n
        if not frame.footprint_inside or not frame.ordered_route_valid:
            reward-=100.;self.termination='off_course'
        elif frame.cone_collision:
            reward-=100.;self.termination='cone_collision'
        elif frame.stalled:
            reward-=100.;self.termination='stalled'
        elif legal_finish:
            reward+=100.;self.valid_lap=True;self.termination='lap_complete'
        elif frame.elapsed_s>=self.maximum_time_s-TIME_TOLERANCE_S:
            self.termination='time_limit'
        self.elapsed_s=frame.elapsed_s;self._station_m=frame.progress_m
        self.total_reward+=reward
        return reward


# Independently pinned R117 arithmetic, with explicit progress consistency.
"""Isolated evaluator-only hypothesis. Does not authenticate physical crossings.

The owner and each replay must first independently establish ordered finite-plane
crossings, containment, collisions and route validity. This component cannot
replace those checks or establish a legal lap. No actor observations are changed.
"""
from dataclasses import dataclass
import math

OBJECTIVE='lapsim.completion-plus-ordered-forward-speed.experimental.v2'
SELECTION='lapsim.genetic-completion-progress.v2'
BETA=0.1  # metre-equivalent bonus per metre; total bonus <0.1*legal lap length
REFERENCE_SPEED_MPS=5.0  # declared scaling assumption, not a calibrated target

def number(x):
    if type(x) not in (int,float) or not math.isfinite(x):
        raise ValueError('finite nonboolean scalar required')
    return float(x)

def forward_speed(u_mps,v_mps,heading_minus_gate_rad):
    """Body-longitudinal forward contribution, capped by actual course velocity.

    Lateral velocity cannot increase the credited speed. Pure sideways motion,
    reversing the body, facing backwards or moving backwards along the gate
    normal yields zero. Physical limits remain the simulator's responsibility.
    """
    u,v,angle=map(number,(u_mps,v_mps,heading_minus_gate_rad))
    c,s=math.cos(angle),math.sin(angle)
    if u<=0. or c<=0.:return 0.
    return max(0.,min(u*c,u*c-v*s))

@dataclass(frozen=True,slots=True)
class Crossing:
    index:int
    tick_ms:int
    u_mps:float
    v_mps:float
    heading_minus_gate_rad:float
    inside:bool
    collision:bool
    ordered_route_valid:bool
    physical_forward_crossing:bool
    fraction:float=1.0

class GateSpeedBonus:
    def __init__(self,gate_stations_m,maximum_tick_ms):
        self.stations=tuple(map(number,gate_stations_m))
        if (not self.stations or len(self.stations)>4096 or self.stations[0]<=0.
            or any(b<=a for a,b in zip(self.stations,self.stations[1:]))
            or type(maximum_tick_ms) is not int or not 0<maximum_tick_ms<=3600000):
            raise ValueError('finite ordered source gates and episode bound required')
        self.maximum_tick_ms=maximum_tick_ms;self.count=0;self.last_tick=0;self.last_fraction=0.
        self.total=0.;self.terminated=False;self.components=[];self._final=None;self._terminal_args=None

    def cross(self,event):
        if self.terminated:raise RuntimeError('terminal objective cannot continue')
        if type(event) is not Crossing:raise TypeError('exact crossing record required')
        if (type(event.index) is not int or event.index!=self.count+1
            or event.index>len(self.stations) or type(event.tick_ms) is not int
            or not self.last_tick<=event.tick_ms<=self.maximum_tick_ms or event.tick_ms<=0):
            raise ValueError('no missing duplicate reordered or out-of-bound crossings')
        fraction=number(event.fraction)
        if not 0.<fraction<=1. or (event.tick_ms==self.last_tick and fraction<=self.last_fraction):
            raise ValueError('strict physical fraction order within a tick required')
        if any(type(x) is not bool for x in (event.inside,event.collision,event.ordered_route_valid,event.physical_forward_crossing)):
            raise ValueError('explicit independent physical evidence required')
        # Invalid terminal step adds no new bonus and does not erase earlier credit.
        if not event.inside or event.collision or not event.ordered_route_valid or not event.physical_forward_crossing:
            self.terminated=True;return 0.
        speed=forward_speed(event.u_mps,event.v_mps,event.heading_minus_gate_rad)
        previous=0. if self.count==0 else self.stations[self.count-1]
        distance=self.stations[self.count]-previous
        bonus=BETA*distance*(speed/(speed+REFERENCE_SPEED_MPS))
        if not 0.<=bonus<BETA*distance:raise ArithmeticError('bounded bonus lost precision')
        self.components.append(dict(index=event.index,tick_ms=event.tick_ms,fraction=fraction,distance_m=distance,
                                    eligible_forward_mps=speed,bonus_m_equivalent=bonus))
        self.count+=1;self.last_tick=event.tick_ms;self.last_fraction=fraction;self.total=math.fsum(x['bonus_m_equivalent'] for x in self.components)
        return bonus

    def terminal(self,baseline_reward,valid_lap,progress_m,candidate_index):
        if type(valid_lap) is not bool:raise ValueError('explicit validity required')
        baseline_reward,progress_m=map(number,(baseline_reward,progress_m))
        if type(candidate_index) is not int or candidate_index<0 or not 0.<=progress_m<=self.stations[-1]:
            raise ValueError('original candidate index and validated prefix progress required')
        expected=self.stations[-1] if valid_lap else (self.stations[self.count-1] if self.count else 0.)
        if progress_m!=expected or (not valid_lap and self.count==len(self.stations)):
            raise ValueError('speed credit requires exact earned-gate progress/finish consistency')
        args=(baseline_reward,valid_lap,progress_m,candidate_index)
        if self._final is not None:
            if args!=self._terminal_args:raise RuntimeError('conflicting terminal result cannot replace first outcome')
            return dict(self._final)
        if valid_lap and self.count!=len(self.stations):raise ValueError('no finish without every gate')
        self.terminated=True
        self._terminal_args=args
        self._final=dict(objective=OBJECTIVE,baseline_reward_m_equivalent=baseline_reward,
                    speed_bonus_m_equivalent=self.total,total_m_equivalent=baseline_reward+self.total,
                    valid_lap=valid_lap,progress_m=progress_m,selection_contract=SELECTION,
                    selection_key=(-int(valid_lap),-progress_m,-(baseline_reward+self.total),candidate_index),
                    official_points=False)
        return dict(self._final)
