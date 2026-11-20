"""Pure synthetic rectangle mission/geometry, NOT physics or an owner provider.

Original car constructor/integrator/actuation remain in LsdDriverEpisode. This
module reads supplied immutable DATA only. No filesystem, native, actor, UI,
server, allocation, reset, lease or simulator API exists here.
"""
from dataclasses import asdict,dataclass
from hashlib import sha256
import json
from math import asin,atan2,ceil,cos,floor,hypot,isfinite,pi,sin,ulp


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):return sha256(canonical(value)).hexdigest()


def _number(value):return type(value) in (int,float) and isfinite(value)


def _pin(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('exact immutable source SHA256 required')


def _json(raw,maximum):
    if type(raw) is not bytes or not 0<len(raw)<=maximum:
        raise ValueError('bounded immutable original input bytes required')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate mission input key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite mission input')))


def _coordinate_extrema(c0,dc,a,b,h0,dh):
    """Extrema of c0+dc*t+a*cos(h0+dh*t)+b*sin(h0+dh*t),0<=t<=1.

    Analytic derivative roots; no discrete sampling that could miss rotation.
    Finite <=one-turn-per-endpoint-sweep domain bounds candidate enumeration.
    """
    values=[c0+a*cos(h0)+b*sin(h0),c0+dc+a*cos(h0+dh)+b*sin(h0+dh)]
    if dh and (a or b):
        radius=hypot(a,b);ratio=-dc/(dh*radius)
        if -1<=ratio<=1:
            phase=atan2(b,-a)
            for root in (asin(ratio)-phase,pi-asin(ratio)-phase):
                lower,upper=sorted((h0,h0+dh))
                first=ceil((lower-root)/(2*pi));last=floor((upper-root)/(2*pi))
                if last-first>4:raise ValueError('bounded angular-extremum search exhausted')
                for k in range(first,last+1):
                    angle=root+2*pi*k;t=(angle-h0)/dh
                    if 0<=t<=1:values.append(c0+dc*t+a*cos(angle)+b*sin(angle))
    return min(values),max(values)


def swept_rectangle_bounds(before_pose,after_pose,half_length_m=1.,half_width_m=.7):
    """Outward bound for endpoint-LINEAR translation/unwrapped heading motion.

    This certifies the stated interpolation, not the continuous internal ODE.
    Numeric padding is conservative; touching/uncertain boundaries are not
    certified clear. No circumscribed-disc approximation is used for walls.
    """
    if any(type(p) is not tuple or len(p)!=3 for p in (before_pose,after_pose)):
        raise ValueError('complete immutable endpoint poses required')
    values=(*before_pose,*after_pose,half_length_m,half_width_m)
    if (any(not _number(x) or abs(x)>1e6 for x in values)
            or half_length_m<=0 or half_width_m<=0):
        raise ValueError('bounded finite positive swept rectangle geometry required')
    x0,y0,h0=before_pose;x1,y1,h1=after_pose;dh=h1-h0
    if abs(dh)>2*pi:
        raise ValueError('more than one full rotation in one physical sweep; incomplete geometry')
    # Keep unwrapped dh. Reducing initial heading bounds root arithmetic error.
    angle=h0%(2*pi)
    xs=[];ys=[]
    for u,v in ((-half_length_m,-half_width_m),(-half_length_m,half_width_m),
                (half_length_m,-half_width_m),(half_length_m,half_width_m)):
        xlow,xhigh=_coordinate_extrema(x0,x1-x0,u,-v,angle,dh)
        ylow,yhigh=_coordinate_extrema(y0,y1-y0,v,u,angle,dh)
        xs.extend((xlow,xhigh));ys.extend((ylow,yhigh))
    scale=max(1.,*(abs(x) for x in values),*(abs(x) for x in xs+ys))
    epsilon=max(1e-9,512*ulp(scale)*(1+hypot(half_length_m,half_width_m)))
    return dict(xmin_m=min(xs)-epsilon,xmax_m=max(xs)+epsilon,
        ymin_m=min(ys)-epsilon,ymax_m=max(ys)+epsilon,roundoff_margin_m=epsilon,
        motion='linear-center-and-unwrapped-heading-between-accepted1ms-endpoints')


@dataclass(frozen=True)
class ParkingLotMission:
    schema: str
    xmin_m: float
    xmax_m: float
    ymin_m: float
    ymax_m: float
    padding_m: float
    background_course_sha256: str
    background_cones_sha256: str
    vehicle_profile_sha256: str
    physical_cones: bool
    show_background: bool
    half_length_m: float = 1.
    half_width_m: float = .7

    def __post_init__(self):
        if self.schema!='lapsim.synthetic-rectangular-parking-lot.v1':raise ValueError('exact mission schema required')
        for pin in (self.background_course_sha256,self.background_cones_sha256,self.vehicle_profile_sha256):_pin(pin)
        if (any(not _number(x) or abs(x)>1e6 for x in (self.xmin_m,self.xmax_m,self.ymin_m,self.ymax_m,self.padding_m))
                or not self.xmin_m<self.xmax_m or not self.ymin_m<self.ymax_m
                or not 5<=self.padding_m<=100 or self.half_length_m!=1. or self.half_width_m!=.7
                or type(self.physical_cones) is not bool or type(self.show_background) is not bool):
            raise ValueError('explicit finite synthetic rectangle/body assumptions required')

    @classmethod
    def from_raws(cls,raws,*,padding_m=25.,physical_cones=True,show_background=True):
        if type(raws) is not dict:raise ValueError('original captured inputs required')
        course=_json(raws['course'],1048576);cones=_json(raws['cones'],1048576);profile=_json(raws['profile'],65536)
        geometry=course['geometry'];xs,ys=geometry['x_m'],geometry['y_m']
        if (type(xs) is not list or type(ys) is not list or not 2<=len(xs)==len(ys)<=20000
                or any(not _number(x) or abs(x)>1e6 for x in xs+ys)):
            raise ValueError('actual bounded source-map SI extent required')
        cone_list=cones['cones']
        if type(cone_list) is not list or len(cone_list)>4096 or any(
                type(c) is not dict or not _number(c.get('x_m')) or not _number(c.get('y_m')) for c in cone_list):
            raise ValueError('actual bounded source cones required')
        actuation=profile['actuation']
        if (profile['vehicle']['mass_kg']!=272.2 or actuation['gear_ratio']!=3.455
                or abs(actuation['motor_maximum_speed_rad_s']*60/(2*pi)-5500)>1e-8):
            raise ValueError('selected original272.2kg/3.455RWD/5500RPM profile required')
        return cls('lapsim.synthetic-rectangular-parking-lot.v1',min(xs)-padding_m,max(xs)+padding_m,
            min(ys)-padding_m,max(ys)+padding_m,padding_m,sha256(raws['course']).hexdigest(),
            sha256(raws['cones']).hexdigest(),sha256(raws['profile']).hexdigest(),physical_cones,show_background)

    @property
    def sha256(self):return digest(asdict(self))

    @property
    def perimeter_m(self):return 2*((self.xmax_m-self.xmin_m)+(self.ymax_m-self.ymin_m))

    def sweep(self,before_pose,after_pose):
        footprint=swept_rectangle_bounds(before_pose,after_pose,self.half_length_m,self.half_width_m)
        clearance=min(footprint['xmin_m']-self.xmin_m,self.xmax_m-footprint['xmax_m'],
            footprint['ymin_m']-self.ymin_m,self.ymax_m-footprint['ymax_m'])
        return dict(inside=clearance>=0,clearance_lower_bound_m=clearance,footprint=footprint,
            mission_sha256=self.sha256,lap_defined=False,route_progress_m=None)

    def initial_monitor(self,state_sha256,context_sha256):
        return dict(schema='lapsim.parking-lot-monitor.v1',mission_sha256=self.sha256,
            context_sha256=context_sha256,accepted_tick=0,accepted_state_sha256=state_sha256,
            crossing=None,lap_defined=False,route_progress_m=None,
            checkpoint_role='diagnostic-only-not-certified-physics-restore')

    def monitor(self,previous,state_sha256,tick,inside,collision):
        if previous['mission_sha256']!=self.sha256 or tick!=previous['accepted_tick']+1:
            raise ValueError('parking-lot monitor identity/tick continuity differs')
        return dict(previous,accepted_tick=tick,accepted_state_sha256=state_sha256,
                    inside=inside,cone_contact=collision)

    def record(self):
        return dict(**asdict(self),mission_sha256=self.sha256,course_kind='synthetic_free_drive_rectangle',
            coordinate_frame='unchanged source local_cartesian_xy metres;coarse inferred registration,not surveyed',
            lap_defined=False,route_progress_defined=False,
            cone_geometry='source inferred cones used as obstacles' if self.physical_cones else 'no physical cones; optional background is decorative',
            vehicle_geometry='assumed2.0m length/1.4m width;not measured body dimensions',
            validity='swept oriented rectangle,not old course corridor or ordered gates')


def checked_mission(mission,raws,bounds):
    if mission is None:return None  # exact old Michigan semantics/data remain
    if type(mission) is not ParkingLotMission:raise TypeError('exact frozen mission type required')
    reconstructed=ParkingLotMission.from_raws(raws,padding_m=mission.padding_m,
        physical_cones=mission.physical_cones,show_background=mission.show_background)
    if (reconstructed!=mission or bounds.body_half_length_m!=mission.half_length_m
            or bounds.body_half_width_m!=mission.half_width_m):
        raise ValueError('source-derived mission identity/body assumptions differ')
    return mission


def mission_header_track(mission,raws):
    """Actual-source optional background; rectangle is the mission geometry."""
    if type(mission) is not ParkingLotMission:raise TypeError('exact mission required')
    course=_json(raws['course'],1048576);cones=_json(raws['cones'],1048576)
    if (sha256(raws['course']).hexdigest()!=mission.background_course_sha256
            or sha256(raws['cones']).hexdigest()!=mission.background_cones_sha256):
        raise ValueError('actual background source identity differs')
    a,b,c,d=mission.xmin_m,mission.xmax_m,mission.ymin_m,mission.ymax_m
    return dict(length_m=mission.perimeter_m,length_note='rectangle perimeter for geometry only;NO lap or progress',
        centerline=[[a,c],[b,c],[b,d],[a,d],[a,c]],
        cones=cones['cones'] if mission.physical_cones else [],mission=mission.record(),
        background=(dict(source_sha256=mission.background_course_sha256,
            centerline=list(map(list,zip(course['geometry']['x_m'],course['geometry']['y_m']))),
            cones=cones['cones'],label='Approximate Michigan source background;NOT drivable corridor or official surveyed map')
            if mission.show_background else None),grid_spacing_m=20.)
