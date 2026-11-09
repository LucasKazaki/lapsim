"""Pinned FSI cone/frame extraction. Source only, unqualified.

Bodies retained from awd-standing-v15/racing_geometry.py at main 07ccb4b.
Only the module header/import boundary and line endings differ. This private
module must be reached through course.construct_fsi_course's byte checks.
No optimizer, clearance certificate, filesystem access or runtime dispatch.
"""
from hashlib import sha256
import json
from math import atan2, ceil, cos, fsum, hypot, isfinite, pi, sin, tan

RAW_LF_SHA='7e0cfd65403406e3d6cf0e12aeeb605efb0163b35f3b6312250f871f0ee85134'
SOURCE_GEOMETRY_SHA='4d0404480da3f1035a4a22f6d94ae6870278d010ca8b215f0160b8263156210d'
def require(ok,message):
    if not ok:raise ValueError(message)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return sha256(canonical(v).encode()).hexdigest()
def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def sub(a,b):return (a[0]-b[0],a[1]-b[1])
def dot(a,b):return a[0]*b[0]+a[1]*b[1]
def segments(points):return tuple(zip(points,points[1:]+points[:1]))

def _hit(a,b,c,d,epsilon=1e-10):
    ab,cd=sub(b,a),sub(d,c);den=cross(ab,cd)
    if abs(den)<=epsilon:
        if abs(cross(sub(c,a),ab))>epsilon:return False
        length=dot(ab,ab)
        require(length>epsilon**2,'Collapsed polygon edge')
        lo,hi=sorted((dot(sub(c,a),ab)/length,dot(sub(d,a),ab)/length))
        return max(lo,0)<=min(hi,1)+epsilon
    t=cross(sub(c,a),cd)/den;u=cross(sub(c,a),ab)/den
    return -epsilon<=t<=1+epsilon and -epsilon<=u<=1+epsilon

def checked_polygon(value):
    require(type(value) in (tuple,list) and 8<=len(value)<=128,'Bounded cone polygon')
    p=[tuple(v) for v in value]
    require(all(len(v)==2 and all(type(x) in (int,float) and isfinite(x) and abs(x)<=10000 for x in v) for v in p),'Finite metre coordinates')
    if hypot(*sub(p[-1],p[0]))<1e-8:p.pop()
    require(len(p)>=8 and all(hypot(*sub(b,a))>=.1 for a,b in segments(p)),'Duplicate/collapsed cone vertices')
    edges=segments(p)
    for i,(a,b) in enumerate(edges):
        for j in range(i+2,len(edges)):
            if i==0 and j==len(edges)-1:continue
            require(not _hit(a,b,*edges[j]),'Self-crossing/retraced cone boundary')
    return p

def parse_cones(raw):
    require(type(raw) is bytes and len(raw)<=32768 and sha256(raw.replace(b'\r\n',b'\n')).hexdigest()==RAW_LF_SHA,
        'Exact retained FSI YAML, with explicit LF identity')
    fields={'cones_left':[],'cones_right':[]};key=pending=None
    for line in raw.decode('utf-8').splitlines():
        if line and not line.startswith((' ','-')):
            require(pending is None,'Incomplete coordinate');key=line.split(':',1)[0]
        elif key in fields:
            if line.startswith('- - '):
                require(pending is None,'Incomplete coordinate');pending=float(line[4:])
            elif line.startswith('  - ') and pending is not None:
                fields[key].append((pending,float(line[4:])));pending=None
            elif line.strip():raise ValueError('Unsupported numeric point-list syntax')
    require(pending is None,'Incomplete coordinate')
    return checked_polygon(fields['cones_left']),checked_polygon(fields['cones_right'])

def _resample(points,count=96):
    lengths=[hypot(*sub(b,a)) for a,b in segments(points)];stations=[0.]
    for length in lengths:stations.append(stations[-1]+length)
    out=[];index=0
    for i in range(count):
        s=i*stations[-1]/count
        while index<len(points)-1 and stations[index+1]<=s:index+=1
        f=(s-stations[index])/lengths[index];a,b=segments(points)[index]
        out.append((a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])))
    return out

def _nearest(point,polygon):
    result=[]
    for a,b in segments(polygon):
        delta=sub(b,a);f=max(0.,min(1.,dot(sub(point,a),delta)/dot(delta,delta)))
        result.append((a[0]+f*delta[0],a[1]+f*delta[1]))
    return min(result,key=lambda p:hypot(*sub(point,p)))

def reconstruct_frame(raw,source_geometry):
    """Reproduce the pinned builder's96-centre construction and full arc grid.

    This establishes numerical frame correspondence only, not survey accuracy.
    """
    channels={k:source_geometry[k] for k in ('closed','distance_m','x_m','y_m','curvature_per_m')}
    require(digest(channels)==SOURCE_GEOMETRY_SHA,'Exact original FSI geometry required')
    left,right=parse_cones(raw)
    centres=[((a[0]+b[0])/2,(a[1]+b[1])/2) for a in _resample(left) for b in [_nearest(a,right)]]
    start=min(range(96),key=lambda i:hypot(*centres[i]));centres=centres[start:]+centres[:start]
    vectors=[sub(b,a) for a,b in segments(centres)];lengths=[hypot(*d) for d in vectors]
    unit=[(x/l,y/l) for (x,y),l in zip(vectors,lengths)]
    turns=[atan2(cross(unit[i-1],u),dot(unit[i-1],u)) for i,u in enumerate(unit)]
    require(all(abs(t)<pi-.01 for t in turns) and abs(abs(fsum(turns))-2*pi)<=1e-8,'Source loop winding/turn')
    trims=[.49*min(lengths[i-1],lengths[i]) if abs(t)>1e-10 else 0. for i,t in enumerate(turns)]
    origin=(centres[0][0]+trims[0]*unit[0][0],centres[0][1]+trims[0]*unit[0][1]);heading=atan2(unit[0][1],unit[0][0])
    x=[0.];y=[0.];s=[0.];k=[];theta=0.
    def append(length,curvature):
        nonlocal theta
        require(length>0,'Positive source segment');count=max(1,ceil(length/.5));step=length/count
        for _ in range(count):
            half=.5*curvature*step;chord=step*(sin(half)/half if half else 1.)
            x.append(x[-1]+chord*cos(theta+half));y.append(y[-1]+chord*sin(theta+half))
            s.append(s[-1]+step);k.append(curvature);theta+=2*half
    for i in range(96):
        j=(i+1)%96;append(lengths[i]-trims[i]-trims[j],0.)
        if trims[j]:
            radius=trims[j]/tan(abs(turns[j])/2);append(radius*abs(turns[j]),(1 if turns[j]>0 else -1)/radius)
    require(len(x)==len(source_geometry['x_m']) and len(k)==len(source_geometry['curvature_per_m']),'Regenerated full grid count differs')
    xy_error=max(hypot(a-c,b-d) for a,b,c,d in zip(x,y,source_geometry['x_m'],source_geometry['y_m']))
    station_error=max(abs(a-b) for a,b in zip(s,source_geometry['distance_m']))
    curvature_error=max(abs(a-b) for a,b in zip(k,source_geometry['curvature_per_m']))
    require(xy_error<=1e-7 and station_error<=1e-7 and curvature_error<=1e-9,'Full source grid mismatch; no best-fit or endpoint-only alignment')
    def local(p):
        q=sub(p,origin);return (cos(heading)*q[0]+sin(heading)*q[1],-sin(heading)*q[0]+cos(heading)*q[1])
    mapped_left=[local(p) for p in left];mapped_right=[local(p) for p in right]
    for a,b in segments(mapped_left):
        for c,d in segments(mapped_right):require(not _hit(a,b,c,d),'Left/right cone boundaries cross')
    return {'schema':'ev.fsi-cone-frame.v1','raw_sha256':sha256(raw).hexdigest(),'LF_sha256':RAW_LF_SHA,
        'source_geometry_sha256':SOURCE_GEOMETRY_SHA,'source_origin_m':list(origin),'source_heading_rad':heading,
        'source_to_course_SE2':{'translation_x_m':-cos(heading)*origin[0]-sin(heading)*origin[1],
            'translation_y_m':sin(heading)*origin[0]-cos(heading)*origin[1],'rotation_rad':-heading,'scale':1.},
        'left_xy_m':[list(p) for p in mapped_left],'right_xy_m':[list(p) for p in mapped_right],
        'maximum_grid_xy_error_m':xy_error,'maximum_grid_station_error_m':station_error,
        'maximum_grid_curvature_error_per_m':curvature_error,
        'confidence':'APPROXIMATE_SIMULATOR_CONES_NOT_SURVEY','runtime_or_corridor_admission':False}
