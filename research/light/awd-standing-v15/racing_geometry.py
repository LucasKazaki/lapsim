"""Isolated simulator-cone frame, boundary and reference geometry. UNQUALIFIED.

Pure bounded geometry, no dependency import, optimizer, model, process or I/O.
The reference controls guidance; retained cone polylines own physical clearance.
"""
from copy import deepcopy
from hashlib import sha256
import json
from math import atan2,ceil,cos,floor,fsum,hypot,isfinite,pi,sin,tan

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

def _point_segment_distance(p,a,b):
    delta=sub(b,a);f=max(0.,min(1.,dot(sub(p,a),delta)/dot(delta,delta)))
    return hypot(p[0]-a[0]-f*delta[0],p[1]-a[1]-f*delta[1])

def _segment_distance(a,b,c,d):
    if _hit(a,b,c,d):return 0.
    return min(_point_segment_distance(a,c,d),_point_segment_distance(b,c,d),
        _point_segment_distance(c,a,b),_point_segment_distance(d,a,b))

def cubic_curvature_upper_bound(velocity,acceleration,jerk,half_interval):
    """Conservative |curvature| bound for one cubic interval about its midpoint.

    The caller supplies a single cubic cell and recursively bisects whenever
    this bound is too loose. No sampled-point value certifies an interval.
    """
    vectors=(velocity,acceleration,jerk)
    require(all(type(v) in (tuple,list) and len(v)==2 and all(type(x) in (int,float) and isfinite(x) for x in v)
        for v in vectors) and type(half_interval) in (int,float) and isfinite(half_interval) and half_interval>=0,
        'Finite cubic midpoint derivatives and interval required')
    h=half_interval;v,a,j=vectors
    speed_lower=hypot(*v)-h*hypot(*a)-.5*h*h*hypot(*j)
    if speed_lower<=1e-12:return float('inf')
    numerator=abs(cross(v,a))+h*abs(cross(v,j))+.5*h*h*abs(cross(a,j))
    result=numerator/speed_lower**3
    return result if isfinite(result) else float('inf')

def verify_nonlocal_polyline_clearance(points,polyline_error_m,*,rounding_m=1e-9,
        grid_m=.5,max_pairs=200000,max_bucket_entries=100000,max_pair_visits=1000000,deadline_callback=None):
    """Fail-closed nonadjacent chord separation for a bounded closed path.

    Each corresponding spline subarc must separately be proved within
    polyline_error_m of its chord. Adjacent subarcs still require an independent
    positive derivative-projection proof, including the periodic seam.
    """
    require(type(points) in (tuple,list) and 4<=len(points)<=5000 and
        all(type(p) in (tuple,list) and len(p)==2 and all(type(x) in (int,float) and isfinite(x) for x in p) for p in points),
        'Finite bounded unclosed reference required')
    require(all(type(v) in (int,float) and isfinite(v) for v in (polyline_error_m,rounding_m,grid_m)) and
        polyline_error_m>0 and rounding_m>0 and grid_m>0 and type(max_pairs) is int and max_pairs>0 and
        type(max_bucket_entries) is int and max_bucket_entries>0 and type(max_pair_visits) is int and max_pair_visits>0 and
        (deadline_callback is None or callable(deadline_callback)),'Bounded topology-check limits required')
    path=[tuple(p) for p in points];edges=segments(path);separation=2*polyline_error_m+rounding_m
    require(all(hypot(*sub(b,a))>1e-9 for a,b in edges),'No collapsed reference chord')
    buckets={};seen=set();entries=0;visits=0
    for i,(a,b) in enumerate(edges):
        if deadline_callback is not None:deadline_callback()
        xmin=floor((min(a[0],b[0])-separation)/grid_m);xmax=floor((max(a[0],b[0])+separation)/grid_m)
        ymin=floor((min(a[1],b[1])-separation)/grid_m);ymax=floor((max(a[1],b[1])+separation)/grid_m)
        require((xmax-xmin+1)*(ymax-ymin+1)<=64,'Individual reference chord spans too many topology cells')
        for gx in range(xmin,xmax+1):
            for gy in range(ymin,ymax+1):
                key=(gx,gy);prior=buckets.setdefault(key,[])
                for j in prior:
                    visits+=1;require(visits<=max_pair_visits,'Reference topology visit cap exhausted')
                    if deadline_callback is not None and visits%64==0:deadline_callback()
                    if j==i-1 or (j==0 and i==len(edges)-1) or (j,i) in seen:continue
                    seen.add((j,i));require(len(seen)<=max_pairs,'Reference topology pair cap exhausted')
                    require(_segment_distance(a,b,*edges[j])>separation,
                        'Nonadjacent reference subarcs can meet within polyline error')
                prior.append(i);entries+=1
                require(entries<=max_bucket_entries,'Reference topology bucket cap exhausted')
    return {'nonadjacent_pairs_checked':len(seen),'bucket_entries':entries,'pair_visits':visits,
        'minimum_required_separation_m':separation,'adjacent_projection_screen_required':True}

def verify_adjacent_tangent_projection(stations,velocities,accelerations,*,speed_margin=1e-9,deadline_callback=None):
    """Conservatively screen each complete adjacent cubic interval and seam.

    Every interval must lie within one cubic cell, so acceleration is affine.
    Its endpoint-norm maximum bounds acceleration over that whole interval.
    This floating-point screen is not an independently validated roundoff proof.
    """
    require(type(stations) in (tuple,list) and 5<=len(stations)<=5001 and
        type(velocities) in (tuple,list) and type(accelerations) in (tuple,list) and
        len(stations)==len(velocities)==len(accelerations) and
        all(type(x) in (int,float) and isfinite(x) for x in stations) and
        all(b>a for a,b in zip(stations,stations[1:])) and
        all(type(v) in (tuple,list) and len(v)==2 and all(type(x) in (int,float) and isfinite(x) for x in v)
            for v in (*velocities,*accelerations)) and
        type(speed_margin) in (int,float) and isfinite(speed_margin) and speed_margin>0 and
        (deadline_callback is None or callable(deadline_callback)),'Bounded cubic seam inputs required')
    require(hypot(*sub(velocities[-1],velocities[0]))<=speed_margin and
        hypot(*sub(accelerations[-1],accelerations[0]))<=speed_margin,'Periodic derivative seam differs')
    intervals=[b-a for a,b in zip(stations,stations[1:])];count=len(intervals)
    for i in range(count):
        if deadline_callback is not None and i%64==0:deadline_callback()
        speed=hypot(*velocities[i]);previous=(i-1)%count
        for j in (previous,i):
            accel=max(hypot(*accelerations[j]),hypot(*accelerations[j+1]))
            require(speed-accel*intervals[j]>speed_margin,
                'Adjacent cubic tangent projection unresolved;no simple-loop claim')
    return {'joins_screened':count,'speed_margin':speed_margin,'rigorous_roundoff_proof':False}

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

def _normal_hits(point,normal,polygon):
    hits=[]
    for a,b in segments(polygon):
        edge=sub(b,a);den=cross(normal,edge)
        if abs(den)<=1e-10:continue
        t=cross(sub(a,point),edge)/den;u=cross(sub(a,point),normal)/den
        if -1e-9<=u<=1+1e-9 and all(abs(t-v)>1e-8 for v in hits):hits.append(t)
    return hits

def widths_on_normals(frame,xy,normals):
    require(4<=len(xy)<=551 and len(xy)==len(normals),'Bounded matched spline arrays')
    left=[];right=[];normal_segments=[]
    for p,n in zip(xy,normals):
        require(len(p)==len(n)==2 and all(type(v) in (int,float) and isfinite(v) for v in (*p,*n)) and abs(hypot(*n)-1)<=1e-9,'Finite right unit normals')
        lh=[t for t in _normal_hits(p,n,frame['left_xy_m']) if t<0]
        rh=[t for t in _normal_hits(p,n,frame['right_xy_m']) if t>0]
        require(lh and rh,'Spline reference outside or ambiguous source corridor')
        l=-max(lh);r=min(rh);require(.1<l<10 and .1<r<10,'Unsupported normal width')
        left.append(l);right.append(r)
        normal_segments.append(((p[0]-l*n[0],p[1]-l*n[1]),(p[0]+r*n[0],p[1]+r*n[1])))
    for i,(a,b) in enumerate(normal_segments):
        for j in range(i+1,len(normal_segments)):
            require(not _hit(a,b,*normal_segments[j]),'Mapped corridor normals cross; no silent folding')
    return {'left_width_m':left,'right_width_m':right,'reference_xy_sha256':digest(xy),
        'normals_sha256':digest(normals),'frame_sha256':digest(frame),
        'scope':'Nodal normal correspondence only; continuous spline and swept footprint still require validation'}

def _point_inside(p,polygon):
    inside=False
    for a,b in segments(polygon):
        if (a[1]>p[1])!=(b[1]>p[1]):
            at=a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if at>p[0]:inside=not inside
    return inside

def point_clearance(frame,p):
    """Distance to both physical cone polylines; valid road is their annulus."""
    left,right=frame['left_xy_m'],frame['right_xy_m']
    valid=_point_inside(p,left)!=_point_inside(p,right)
    distance=min(hypot(*sub(p,_nearest(p,poly))) for poly in (left,right))
    return distance if valid else -distance

def footprint_clearance(frame,pose,*,front_m,rear_m,width_m,margin_m):
    require(all(type(v) in (int,float) and isfinite(v) for v in (*pose,front_m,rear_m,width_m,margin_m)) and
        min(front_m,rear_m,width_m)>0 and margin_m>=0,'Declared full rectangle required')
    x,y,h=pose;vertices=[]
    for a,b in ((front_m,width_m/2),(-rear_m,width_m/2),(-rear_m,-width_m/2),(front_m,-width_m/2)):
        vertices.append((x+cos(h)*a-sin(h)*b,y+sin(h)*a+cos(h)*b))
    slack=min(point_clearance(frame,p)-margin_m for p in vertices)
    for a,b in segments(vertices):
        for poly in (frame['left_xy_m'],frame['right_xy_m']):
            for c,d in segments(poly):
                if _hit(a,b,c,d):return min(slack,-1e-12)
                slack=min(slack,_segment_distance(a,b,c,d)-margin_m)
    for poly in (frame['left_xy_m'],frame['right_xy_m']):
        for px,py in poly:
            dx,dy=px-x,py-y;bx=cos(h)*dx+sin(h)*dy;by=-sin(h)*dx+cos(h)*dy
            if -rear_m<bx<front_m and abs(by)<width_m/2:return min(slack,-1e-12)
    return slack # Instantaneous rectangle only; continuous swept checks are separate.

def anchor_at_source_gate(xy,*,maximum_gate_offset_m=3.):
    """Reseam a new closed polyline at physical source x=0, forward crossing.

    Keeps original course gate, not a percentage of a changed reference length.
    """
    require(8<=len(xy)<=5000,'Bounded unclosed reference')
    hits=[]
    for i,(a,b) in enumerate(segments(xy)):
        if a[0]<0<=b[0] and b[0]>a[0]:
            f=-a[0]/(b[0]-a[0]);y=a[1]+f*(b[1]-a[1])
            if abs(y)<=maximum_gate_offset_m:hits.append((abs(y),i,(0.,y)))
    require(len(hits)==1,'Physical start gate must have one eligible forward crossing')
    _,i,p=hits[0];out=[p]+[tuple(v) for v in xy[i+1:]+xy[:i+1]]
    if hypot(*sub(out[-1],out[0]))<1e-9:out.pop()
    require(all(hypot(*sub(b,a))>1e-9 for a,b in segments(out)),'Collapsed reseamed path')
    return {'xy_unclosed_m':[list(v) for v in out],'gate':{'origin_xy_m':[0.,0.],'forward_unit':[1.,0.],
        'crossing_xy_m':list(p),'source_gate':'pinned FSI origin/initial tangent'},'source_gate_reseamed':True}
