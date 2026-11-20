"""Exact original _Projection, _path_point and _project_local declarations; no driver/Full imports."""
from dataclasses import dataclass
from math import atan2, floor, hypot, isfinite, pi, sqrt
from bisect import bisect_right
from lapsim.courses.spatial_track import SpatialTrack

@dataclass(frozen=True, slots=True)
class _Projection:
    station_m: float
    cross_track_m: float
    heading_rad: float


def _path_point(track: SpatialTrack, station_m: float) -> tuple[float, float]:
    if track.closed:
        station_m %= track.length_m
    else:
        if not isfinite(station_m):
            raise ValueError("open path station must be finite")
        station_m = min(track.length_m, max(0.0, station_m))
    # The course grid is at most 0.5 m in the supplied synthetic case.
    # Linear chords are a reference geometry approximation, not road edges.
    i = min(bisect_right(track.distance_m, station_m) - 1, track.cell_count - 1)
    fraction = ((station_m - track.distance_m[i]) /
                (track.distance_m[i + 1] - track.distance_m[i]))
    return (
        track.x_m[i] + fraction * (track.x_m[i + 1] - track.x_m[i]),
        track.y_m[i] + fraction * (track.y_m[i + 1] - track.y_m[i]),
    )


def _project_local(
    track: SpatialTrack, x_m: float, y_m: float, previous_station_m: float,
    window_m: float,
) -> _Projection:
    if not track.closed and (
        not all(isfinite(value) for value in (x_m, y_m, previous_station_m, window_m))
        or window_m < 0.0
    ):
        raise ValueError("open projection requires finite inputs and a nonnegative window")
    best_distance_sq = float("inf")
    best: _Projection | None = None
    length_m = track.length_m
    lower_m = previous_station_m - window_m
    upper_m = previous_station_m + window_m
    candidate_entries: set[tuple[int, int]] = set()
    if not track.closed:
        # Intersect the caller's original window with this one open route.
        # Recentring previous progress would hide a disconnected checkpoint.
        lower_m = max(0.0, lower_m)
        upper_m = min(length_m, upper_m)
        if lower_m <= upper_m:
            first = min(track.cell_count - 1,
                        max(0, bisect_right(track.distance_m, lower_m) - 1))
            last = min(track.cell_count, bisect_right(track.distance_m, upper_m))
            candidate_entries.update((i, 0) for i in range(first, last))
    elif window_m >= length_m / 2.0:
        for i in range(track.cell_count):
            center_station = 0.5 * (track.distance_m[i] + track.distance_m[i + 1])
            nearest_lap = round((previous_station_m - center_station) / length_m)
            candidate_entries.add((i, nearest_lap))
            # A window shorter than one lap can cover both ends of a cell
            # longer than half a lap. The adjacent copies remain bounded.
            if window_m < length_m:
                candidate_entries.add((i, nearest_lap - 1))
                candidate_entries.add((i, nearest_lap + 1))
    else:
        # Station and cell boundaries are sorted. Visit cells that overlap the
        # local window, including each overlapping lap copy at the seam.
        for lap in range(floor(lower_m / length_m), floor(upper_m / length_m) + 1):
            interval_lower_m = max(0.0, lower_m - lap * length_m)
            interval_upper_m = min(length_m, upper_m - lap * length_m)
            if interval_lower_m > interval_upper_m:
                continue
            first = max(0, bisect_right(track.distance_m, interval_lower_m) - 1)
            last = min(track.cell_count,
                       bisect_right(track.distance_m, interval_upper_m))
            candidate_entries.update((i, lap) for i in range(first, last))

    def candidate_order(entry: tuple[int, int]) -> tuple[int, int, float, int]:
        i, lap = entry
        center_station = 0.5 * (track.distance_m[i] + track.distance_m[i + 1])
        if not track.closed:
            return (i, 0, abs(center_station - previous_station_m), 0)
        nearest_lap = round((previous_station_m - center_station) / length_m)
        return (i, lap != nearest_lap,
                abs(center_station + lap * length_m - previous_station_m), lap)

    # Cell index remains the primary tie order; the former nearest-center
    # copy wins physical-distance ties within one cell.
    for i, lap in sorted(candidate_entries, key=candidate_order):
        lap_shift = lap * length_m
        start_station_m = track.distance_m[i] + lap_shift
        end_station_m = track.distance_m[i + 1] + lap_shift
        overlap_lower_m = max(start_station_m, lower_m)
        overlap_upper_m = min(end_station_m, upper_m)
        if overlap_lower_m > overlap_upper_m:
            continue
        dx = track.x_m[i + 1] - track.x_m[i]
        dy = track.y_m[i + 1] - track.y_m[i]
        norm_sq = dx * dx + dy * dy
        if norm_sq <= 0.0:
            continue
        cell_length_m = end_station_m - start_station_m
        lower_fraction = (overlap_lower_m - start_station_m) / cell_length_m
        upper_fraction = (overlap_upper_m - start_station_m) / cell_length_m
        fraction = min(upper_fraction, max(lower_fraction,
            ((x_m - track.x_m[i]) * dx + (y_m - track.y_m[i]) * dy) / norm_sq
        ))
        px = track.x_m[i] + fraction * dx
        py = track.y_m[i] + fraction * dy
        error_x, error_y = x_m - px, y_m - py
        distance_sq = error_x * error_x + error_y * error_y
        if distance_sq < best_distance_sq:
            best_distance_sq = distance_sq
            best = _Projection(
                start_station_m + fraction * cell_length_m,
                (dx * error_y - dy * error_x) / sqrt(norm_sq),
                atan2(dy, dx),
            )
    if best is None:
        raise ValueError("no course segment lies in the local projection window")
    return best



def ordered_gate_crossing(track,before_xy,after_xy,source_before,source_after,station_m,
                          *,half_width_m,body_radius_m):
    """Original finite plane, localized by actual crossing XY, not q interpolation."""
    gx,gy=_path_point(track,station_m)
    a,b=_path_point(track,station_m-.1),_path_point(track,station_m+.1)
    dx,dy=b[0]-a[0],b[1]-a[1];norm=hypot(dx,dy)
    if norm==0:raise ValueError('degenerate physical gate tangent')
    ux,uy=dx/norm,dy/norm
    x0,y0=before_xy;x1,y1=after_xy
    d0=(x0-gx)*ux+(y0-gy)*uy;d1=(x1-gx)*ux+(y1-gy)*uy
    if d0<0<=d1:
        f=-d0/(d1-d0)
        cx,cy=x0+f*(x1-x0),y0+f*(y1-y0)
        lateral=(cx-gx)*(-uy)+(cy-gy)*ux
        source=_project_local(track,cx,cy,source_before,12.).station_m
        valid=abs(lateral)+body_radius_m<=half_width_m and abs(source-station_m)<=2.
        return valid,not valid,f
    return False,source_after>station_m+2.,None


def ordered_gate_event(track,before_xy,after_xy,source_before,source_after,station_m,
                       *,half_width_m,body_radius_m):
    """Compatibility surface; complete producer/replay also check crossing order."""
    passed,missed,_=ordered_gate_crossing(track,before_xy,after_xy,source_before,source_after,
        station_m,half_width_m=half_width_m,body_radius_m=body_radius_m)
    return passed,missed


from math import cos as _rectangle_cos, sin as _rectangle_sin, ulp as _rectangle_ulp

def rectangle_road_tube_bound(track, before_pose, after_pose, station_m,
                             body_half_length_m, body_half_width_m):
    """Sound sufficient bound for a swept rectangle in this local polyline tube.

    A segment enlarged by a radius is convex. Bounding all four after-pose
    corners against ONE authenticated source segment therefore bounds their
    entire convex hull. Translation plus R*abs(delta heading) bounds every
    body point during endpoint-linear interpolation. Min over at most five
    neighboring source segments is still a sufficient containment certificate.
    This never claims that failure to certify proves physical departure.
    """
    if type(track) is not SpatialTrack:
        raise ValueError('exact source-owned SpatialTrack required')
    if (type(before_pose) is not tuple or type(after_pose) is not tuple
            or len(before_pose)!=3 or len(after_pose)!=3):
        raise ValueError('two complete ordinary endpoint poses required')
    values=(*before_pose,*after_pose,station_m,body_half_length_m,body_half_width_m)
    if any(type(v) not in (int,float) or not isfinite(v) for v in values):
        raise ValueError('finite ordinary rectangle geometry required')
    if body_half_length_m<=0 or body_half_width_m<=0:
        raise ValueError('positive declared rectangle half dimensions required')
    x0,y0,h0=before_pose;x1,y1,h1=after_pose
    c,s=_rectangle_cos(h1),_rectangle_sin(h1)
    corners=tuple((x1+c*u-s*v,y1+s*u+c*v)
        for u,v in ((-body_half_length_m,-body_half_width_m),
                    (body_half_length_m,-body_half_width_m),
                    (body_half_length_m,body_half_width_m),
                    (-body_half_length_m,body_half_width_m)))
    sweep=hypot(x1-x0,y1-y0)+hypot(body_half_length_m,body_half_width_m)*abs(h1-h0)
    if not isfinite(sweep) or any(not isfinite(v) for p in corners for v in p):
        raise ValueError('rectangle geometry overflow')
    station=track.wrap_distance_m(station_m) if track.closed else min(track.length_m,max(0.,station_m))
    center=min(track.cell_count-1,max(0,bisect_right(track.distance_m,station)-1))
    candidates={(center+k)%track.cell_count for k in range(-2,3)} if track.closed else {
        center+k for k in range(-2,3) if 0<=center+k<track.cell_count}
    best=float('inf');scale=max(1.,*(abs(v) for p in corners for v in p),sweep)
    for i in candidates:
        ax,ay=track.x_m[i],track.y_m[i];bx,by=track.x_m[i+1],track.y_m[i+1]
        scale=max(scale,abs(ax),abs(ay),abs(bx),abs(by))
        dx,dy=bx-ax,by-ay;length=hypot(dx,dy)
        if not isfinite(length):raise ValueError('source segment overflow')
        if length==0:continue
        ux,uy=dx/length,dy/length;worst=0.
        for x,y in corners:
            along=min(length,max(0.,(x-ax)*ux+(y-ay)*uy))
            worst=max(worst,hypot(x-(ax+along*ux),y-(ay+along*uy)))
        best=min(best,worst)
    if not isfinite(best):raise ValueError('no supported nondegenerate local source segment')
    # A small outward roundoff allowance preserves a conservative comparison.
    return best+sweep+max(1e-9,128*_rectangle_ulp(scale))

def rectangle_gate_half_width(track,before_pose,after_pose,station_m,
                              body_half_length_m,body_half_width_m):
    """Bound body extent normal to the unchanged finite crossing plane."""
    if type(track) is not SpatialTrack or any(type(p) is not tuple or len(p)!=3 for p in (before_pose,after_pose)):
        raise ValueError('exact track and endpoint poses required')
    values=(*before_pose,*after_pose,station_m,body_half_length_m,body_half_width_m)
    if any(type(v) not in (int,float) or not isfinite(v) for v in values) or min(body_half_length_m,body_half_width_m)<=0:
        raise ValueError('finite positive rectangle gate geometry required')
    a,b=_path_point(track,station_m-.1),_path_point(track,station_m+.1)
    dx,dy=b[0]-a[0],b[1]-a[1];norm=hypot(dx,dy)
    if not norm or not isfinite(norm):raise ValueError('degenerate original gate tangent')
    nx,ny=-dy/norm,dx/norm;c,s=_rectangle_cos(after_pose[2]),_rectangle_sin(after_pose[2])
    extent=body_half_length_m*abs(c*nx+s*ny)+body_half_width_m*abs(-s*nx+c*ny)
    radius=hypot(body_half_length_m,body_half_width_m)
    scale=max(1.,*(abs(v) for p in (a,b) for v in p))
    epsilon=max(1e-9,1024*_rectangle_ulp(scale)/norm*radius)
    return min(radius,extent+radius*abs(after_pose[2]-before_pose[2]))+epsilon

def swept_rectangle_cone_collision(before_pose,after_pose,body_half_length_m,
                                   body_half_width_m,cone_xy,cone_radius_m):
    """Conservative swept box/point-or-disc test, with original circle broad phase.

    The after-pose box inflated by maximum point motion contains the whole
    endpoint-linear sweep. Intersecting this with the circumscribed swept-disc
    broad phase cannot hide a collision. Tiny conservative inflation handles
    roundoff; this is not a continuous-ODE trajectory certificate.
    """
    if (type(before_pose) is not tuple or type(after_pose) is not tuple or len(before_pose)!=3 or len(after_pose)!=3
            or type(cone_xy) is not tuple or len(cone_xy)>4096):
        raise ValueError('bounded ordinary rectangle/cone tuples required')
    values=(*before_pose,*after_pose,body_half_length_m,body_half_width_m,cone_radius_m)
    if (any(type(v) not in (int,float) or not isfinite(v) for v in values)
            or min(body_half_length_m,body_half_width_m)<=0 or cone_radius_m<0):
        raise ValueError('finite positive body/nonnegative cone geometry required')
    x0,y0,h0=before_pose;x1,y1,h1=after_pose;radius=hypot(body_half_length_m,body_half_width_m)
    dx,dy=x1-x0,y1-y0;travel=hypot(dx,dy);sweep=travel+radius*abs(h1-h0)
    if not isfinite(sweep):raise ValueError('sweep overflow')
    c,s=_rectangle_cos(h1),_rectangle_sin(h1);scale=max(1.,*(abs(v) for v in (*before_pose[:2],*after_pose[:2])),sweep)
    for point in cone_xy:
        if type(point) is not tuple or len(point)!=2 or any(type(v) not in (int,float) or not isfinite(v) for v in point):
            raise ValueError('ordinary finite source cone coordinates required')
        x,y=point;epsilon=max(1e-9,128*_rectangle_ulp(max(scale,abs(x),abs(y))))
        if travel:
            along=min(travel,max(0.,(x-x0)*(dx/travel)+(y-y0)*(dy/travel)))
            broad=hypot(x-(x0+along*dx/travel),y-(y0+along*dy/travel))
        else:broad=hypot(x-x1,y-y1)
        if broad>radius+cone_radius_m+epsilon:continue
        rx,ry=x-x1,y-y1;u=c*rx+s*ry;v=-s*rx+c*ry
        distance=hypot(max(0.,abs(u)-body_half_length_m),max(0.,abs(v)-body_half_width_m))
        if distance<=cone_radius_m+sweep+epsilon:return True
    return False


def rectangle_road_tube_partition_bound(track, before_pose, after_pose, station_m,
                                      body_half_length_m, body_half_width_m):
    """Additional fixed2x2 swept-rectangle containment certificate.

    Each closed cell's FOUR vertices must share ONE source-segment capsule.
    The four cells cover the whole original rectangle, including its interior.
    Witnesses use only the SAME at-most-five segments as the original bound.
    The original FULL-body translation+R*abs(delta-heading) and outward
    allowance remain. This is the same endpoint-linear numerical sweep model,
    not an ODE-path, cone-collision or surveyed-road certificate.

    Caller invokes this only after the original whole-body certificate fails
    and retains min(original_bound, this_bound). No adaptive subdivision.
    """
    if type(track) is not SpatialTrack:
        raise ValueError('exact source-owned SpatialTrack required')
    if (type(before_pose) is not tuple or type(after_pose) is not tuple
            or len(before_pose)!=3 or len(after_pose)!=3):
        raise ValueError('two complete ordinary endpoint poses required')
    values=(*before_pose,*after_pose,station_m,body_half_length_m,body_half_width_m)
    if any(type(v) not in (int,float) or not isfinite(v) for v in values):
        raise ValueError('finite ordinary rectangle geometry required')
    if body_half_length_m<=0 or body_half_width_m<=0:
        raise ValueError('positive declared rectangle half dimensions required')
    x0,y0,h0=before_pose;x1,y1,h1=after_pose
    c,s=_rectangle_cos(h1),_rectangle_sin(h1)
    corners=tuple((x1+c*u-s*v,y1+s*u+c*v)
        for u,v in ((-body_half_length_m,-body_half_width_m),
                    (body_half_length_m,-body_half_width_m),
                    (body_half_length_m,body_half_width_m),
                    (-body_half_length_m,body_half_width_m)))
    sweep=hypot(x1-x0,y1-y0)+hypot(body_half_length_m,body_half_width_m)*abs(h1-h0)
    if not isfinite(sweep) or any(not isfinite(v) for p in corners for v in p):
        raise ValueError('rectangle geometry overflow')
    station=track.wrap_distance_m(station_m) if track.closed else min(track.length_m,max(0.,station_m))
    center=min(track.cell_count-1,max(0,bisect_right(track.distance_m,station)-1))
    candidates={(center+k)%track.cell_count for k in range(-2,3)} if track.closed else {
        center+k for k in range(-2,3) if 0<=center+k<track.cell_count}
    scale=max(1.,*(abs(v) for p in corners for v in p),sweep)
    largest_cell_bound=0.
    for ulo,uhi in ((-body_half_length_m,0.),(0.,body_half_length_m)):
        for vlo,vhi in ((-body_half_width_m,0.),(0.,body_half_width_m)):
            vertices=tuple((x1+c*u-s*v,y1+s*u+c*v)
                for u,v in ((ulo,vlo),(uhi,vlo),(uhi,vhi),(ulo,vhi)))
            if any(not isfinite(v) for point in vertices for v in point):
                raise ValueError('rectangle geometry overflow')
            best=float('inf')
            for i in candidates:
                ax,ay=track.x_m[i],track.y_m[i];bx,by=track.x_m[i+1],track.y_m[i+1]
                scale=max(scale,abs(ax),abs(ay),abs(bx),abs(by))
                dx,dy=bx-ax,by-ay;length=hypot(dx,dy)
                if not isfinite(length):raise ValueError('source segment overflow')
                if length==0:continue
                ux,uy=dx/length,dy/length;worst=0.
                for x,y in vertices:
                    along=min(length,max(0.,(x-ax)*ux+(y-ay)*uy))
                    worst=max(worst,hypot(x-(ax+along*ux),y-(ay+along*uy)))
                best=min(best,worst)
            if not isfinite(best):raise ValueError('no supported nondegenerate local source segment')
            largest_cell_bound=max(largest_cell_bound,best)
    return largest_cell_bound+sweep+max(1e-9,128*_rectangle_ulp(scale))


def rectangle_road_tube_spacetime_bound(track, before_pose, after_pose, station_m,
                                      body_half_length_m, body_half_width_m):
    """Additional fixed2-time x4x4-cell sufficient containment certificate.

    All32 closed space-time cells are covered, never only sampled corners.
    The same at-most-five source segments are selected ONCE from station_m.
    Each spatial cell's four after-subinterval vertices must share ONE capsule;
    full-body translation+R*abs(delta-heading) bounds that complete interval.
    No geometry/width/body/cone/gate change, adaptive subdivision, angle unwrap
    or intermediate ODE-trajectory claim is made. Existing faster certificates
    remain unchanged; caller uses this only when they fail to certify.
    """
    if type(track) is not SpatialTrack:
        raise ValueError('exact source-owned SpatialTrack required')
    if (type(before_pose) is not tuple or type(after_pose) is not tuple
            or len(before_pose)!=3 or len(after_pose)!=3):
        raise ValueError('two complete ordinary endpoint poses required')
    values=(*before_pose,*after_pose,station_m,body_half_length_m,body_half_width_m)
    if any(type(v) not in (int,float) or not isfinite(v) for v in values):
        raise ValueError('finite ordinary rectangle geometry required')
    if body_half_length_m<=0 or body_half_width_m<=0:
        raise ValueError('positive declared rectangle half dimensions required')
    delta=tuple(b-a for a,b in zip(before_pose,after_pose))
    middle=tuple(a+.5*d for a,d in zip(before_pose,delta))
    radius=hypot(body_half_length_m,body_half_width_m)
    if any(not isfinite(v) for v in (*delta,*middle,radius)):
        raise ValueError('rectangle geometry overflow')
    station=track.wrap_distance_m(station_m) if track.closed else min(track.length_m,max(0.,station_m))
    center=min(track.cell_count-1,max(0,bisect_right(track.distance_m,station)-1))
    candidates=tuple(sorted({(center+k)%track.cell_count for k in range(-2,3)} if track.closed else {
        center+k for k in range(-2,3) if 0<=center+k<track.cell_count}))
    segments=[];scale=1.
    for i in candidates:
        ax,ay=track.x_m[i],track.y_m[i];bx,by=track.x_m[i+1],track.y_m[i+1]
        scale=max(scale,abs(ax),abs(ay),abs(bx),abs(by))
        dx,dy=bx-ax,by-ay;length=hypot(dx,dy)
        if not isfinite(length):raise ValueError('source segment overflow')
        if length==0:continue
        segments.append((ax,ay,dx/length,dy/length,length))
    if not segments:raise ValueError('no supported nondegenerate local source segment')
    ugrid=(-body_half_length_m,-.5*body_half_length_m,0.,.5*body_half_length_m,body_half_length_m)
    vgrid=(-body_half_width_m,-.5*body_half_width_m,0.,.5*body_half_width_m,body_half_width_m)
    largest_bound=0.
    for p0,p1 in ((before_pose,middle),(middle,after_pose)):
        x0,y0,h0=p0;x1,y1,h1=p1
        c,s=_rectangle_cos(h1),_rectangle_sin(h1)
        sweep=hypot(x1-x0,y1-y0)+radius*abs(h1-h0)
        outer=tuple((x1+c*u-s*v,y1+s*u+c*v)
            for u,v in ((-body_half_length_m,-body_half_width_m),
                        (body_half_length_m,-body_half_width_m),
                        (body_half_length_m,body_half_width_m),
                        (-body_half_length_m,body_half_width_m)))
        if not isfinite(sweep) or any(not isfinite(v) for point in outer for v in point):
            raise ValueError('rectangle geometry overflow')
        scale=max(scale,sweep,*(abs(v) for point in outer for v in point))
        for ui in range(4):
            for vi in range(4):
                ulo,uhi=ugrid[ui:ui+2];vlo,vhi=vgrid[vi:vi+2]
                vertices=tuple((x1+c*u-s*v,y1+s*u+c*v)
                    for u,v in ((ulo,vlo),(uhi,vlo),(uhi,vhi),(ulo,vhi)))
                if any(not isfinite(v) for point in vertices for v in point):
                    raise ValueError('rectangle geometry overflow')
                best=float('inf')
                for ax,ay,ux,uy,length in segments:
                    worst=0.
                    for x,y in vertices:
                        projection=(x-ax)*ux+(y-ay)*uy
                        if not isfinite(projection):raise ValueError('rectangle projection overflow')
                        along=min(length,max(0.,projection))
                        distance=hypot(x-(ax+along*ux),y-(ay+along*uy))
                        if not isfinite(distance):raise ValueError('rectangle distance overflow')
                        worst=max(worst,distance)
                    best=min(best,worst)
                bound=best+sweep
                if not isfinite(bound):raise ValueError('rectangle bound overflow')
                largest_bound=max(largest_bound,bound)
    result=largest_bound+max(1e-9,128*_rectangle_ulp(scale))
    if not isfinite(result):raise ValueError('rectangle bound overflow')
    return result
