"""Offline, deterministic line/arc approximations of pinned cone layouts.

This is a bounded converter for the checked-in FSSIM point-list subset, not a
general YAML importer. No network, ROS, Gazebo or new runtime dependency needed.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from hashlib import sha256
import json
from math import atan2, ceil, cos, fsum, hypot, isfinite, pi, sin, tan
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lapsim.courses.course_bundle import CourseBundle, course_geometry_sha256
from lapsim.courses.spatial_track import SpatialTrack
from lapsim.courses.track import Curve, Straight, Track

COMMIT = "cf652d8d3f1e13031dad3fb75eb3d4e6fbaaeff4"
UPSTREAM = f"https://github.com/AMZ-Racing/fssim/blob/{COMMIT}"
DESTINATION = ROOT / "configs/courses"


def points_checked(points, *, minimum_segment_m=.1, maximum_vertices=1000):
    if not 8 <= len(points) <= maximum_vertices:
        raise ValueError(f"A course needs 8-{maximum_vertices} ordered vertices")
    out = []
    for point in points:
        if len(point) != 2 or any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 10000 for v in point):
            raise ValueError("Finite metric x/y coordinates within 10 km required")
        out.append(tuple(float(v) for v in point))
    if hypot(out[-1][0]-out[0][0], out[-1][1]-out[0][1]) < 1e-8:
        out.pop()
    for a, b in zip(out, out[1:]+out[:1]):
        if hypot(a[0]-b[0], a[1]-b[1]) < minimum_segment_m:
            raise ValueError("Duplicate/near-duplicate course vertex")
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i, (a,b) in enumerate(zip(out, out[1:]+out[:1])):
        for j in range(i+2, len(out)):
            if i == 0 and j == len(out)-1:
                continue
            c,d = out[j],out[(j+1)%len(out)]
            if max(a[0],b[0]) < min(c[0],d[0]) or max(c[0],d[0]) < min(a[0],b[0]) or max(a[1],b[1]) < min(c[1],d[1]) or max(c[1],d[1]) < min(a[1],b[1]):
                continue
            if cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0:
                raise ValueError("Self-crossing/retraced polygon is not a course")
    return out


def cone_boundaries(path):
    """Read only the two numeric point-list fields of pinned upstream files."""
    result = {"cones_left": [], "cones_right": []}
    key, pending = None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith((" ", "-")):
            key = line.split(":", 1)[0]
            if pending is not None:
                raise ValueError("Incomplete cone coordinate")
        elif key in result:
            if line.startswith("- - "):
                if pending is not None:
                    raise ValueError("Incomplete cone coordinate")
                pending = float(line[4:])
            elif line.startswith("  - ") and pending is not None:
                result[key].append((pending, float(line[4:])))
                pending = None
            elif line.strip():
                raise ValueError("Unsupported point-list syntax")
    if pending is not None:
        raise ValueError("Incomplete cone coordinate")
    return [points_checked(result[key]) for key in ("cones_left", "cones_right")]


def resample_loop(points, count):
    lengths = [hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:]+points[:1])]
    stations = [0.]
    for length in lengths:
        stations.append(stations[-1]+length)
    result = []
    for i in range(count):
        station = i*stations[-1]/count
        index = min(bisect_right(stations,station)-1,len(points)-1)
        fraction = (station-stations[index])/lengths[index]
        a,b = points[index],points[(index+1)%len(points)]
        result.append((a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])))
    return result


def center_from_cones(left,right):
    # Normalized boundary progress is not correspondence: inner/outer curves
    # have different lengths. Project ordered left samples onto the closest
    # right segment instead. No same-index or same-start assumption is made.
    # Bounds/crossing checks reject ambiguous or implausible approximations.
    count = 96
    left = resample_loop(left,count)
    def nearest(point):
        candidates=[]
        for a,b in zip(right,right[1:]+right[:1]):
            dx,dy=b[0]-a[0],b[1]-a[1]
            t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
            candidates.append((a[0]+t*dx,a[1]+t*dy))
        return min(candidates,key=lambda p:hypot(point[0]-p[0],point[1]-p[1]))
    pairs = [(a,nearest(a)) for a in left]
    gaps = [hypot(a[0]-b[0],a[1]-b[1]) for a,b in pairs]
    if not 1 <= min(gaps) <= max(gaps) <= 8:
        raise ValueError("Boundary phase/width is implausible; correspondence needs review")
    center = [((a[0]+b[0])/2,(a[1]+b[1])/2) for a,b in pairs]
    start = min(range(count),key=lambda i: hypot(*center[i]))
    center = center[start:]+center[:start]
    return points_checked(center), {"boundary_pair_gap_min_m":min(gaps),"boundary_pair_gap_max_m":max(gaps),"correspondence":"nearest right-boundary segment from ordered left samples","samples":count}


def rounded_polygon(points):
    """Tangent circular fillets inside each vertex; no endpoint correction.

    Each trim is 49% of the smaller adjacent edge, so adjacent trims cannot
    overlap. Straight connectors and signed circular turns close analytically.
    """
    points = points_checked(points)
    vectors = [(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:]+points[:1])]
    lengths = [hypot(*v) for v in vectors]
    units = [(x/l,y/l) for (x,y),l in zip(vectors,lengths)]
    trims,turns = [],[]
    for i, outgoing in enumerate(units):
        incoming = units[i-1]
        angle = atan2(incoming[0]*outgoing[1]-incoming[1]*outgoing[0], incoming[0]*outgoing[0]+incoming[1]*outgoing[1])
        if abs(angle) >= pi-.01:
            raise ValueError("Near-reversing vertex cannot form a stable fillet")
        turns.append(angle)
        trims.append(.49*min(lengths[i-1],lengths[i]) if abs(angle)>1e-10 else 0.)
    if abs(abs(fsum(turns))-2*pi) > 1e-8:
        raise ValueError("Course must wind exactly once")
    segments = []
    for i in range(len(points)):
        j = (i+1)%len(points)
        segments.append(Straight(lengths[i]-trims[i]-trims[j]))
        if trims[j]:
            segments.append(Curve(trims[j]/tan(abs(turns[j])/2),turns[j]))
    track = SpatialTrack.from_track(Track.from_segments(segments),maximum_cell_length_m=.5,close_geometry=False)
    track.validate_coherent_arcs()
    # Check sampled arc chords too: fillets must not introduce intersections.
    points_checked(list(zip(track.x_m,track.y_m)),minimum_segment_m=1e-9,maximum_vertices=5001)
    radii = [s.radius_m for s in segments if isinstance(s,Curve)]
    return track, {"source_vertices":len(points),"minimum_radius_m":min(radii),"maximum_radius_m":max(radii),"signed_turn_rad":fsum(turns),"endpoint_correction_m":0.0}


def manifest(course_id,label,description,track,source_name,source_sha,method):
    return CourseBundle.from_dict({
        "schema_version":1,"course_id":course_id,"revision":"v1","label":label,
        "description":description,"source_kind":"synthetic",
        "provenance":{"source_name":source_name,"source_sha256":source_sha,
            "processing_method":method,"review_note":"Approximation with an assumed uniform corridor; no surveyed boundaries, real-car calibration or official event claim."},
        "coordinate_frame":{"type":"local_cartesian_right_handed_xy","units":"m","origin":"First tangent after selected source seam","x_axis":"initial outgoing tangent","y_axis":"local left"},
        "travel_direction":"counterclockwise" if fsum(k*d for k,d in zip(track.curvature_per_m,track.cell_length_m))>0 else "clockwise",
        "boundary_status":"absent","ai_defaults":{"width_source":"assumed_uniform","half_width_m":3.,"vehicle_width_m":1.4,"safety_margin_m":.2},
        "geometry":{"model":"piecewise_constant_curvature_arcs","closed":True,"distance_m":list(track.distance_m),"x_m":list(track.x_m),"y_m":list(track.y_m),"curvature_per_m":list(track.curvature_per_m)},
        "geometry_sha256":course_geometry_sha256(track),
    })


def build():
    catalog = {"schema":"lapsim.course-library.v1","courses":[]}
    for name in ("FSG","FSI"):
        source = DESTINATION/"upstream/amz-fssim"/(name+".yaml")
        points,alignment = center_from_cones(*cone_boundaries(source))
        track,audit = rounded_polygon(points)
        course_id = "amz_fssim_"+name.lower()+"_approx"
        label = "FSSIM "+name+" · map approximation"
        description = "AMZ simulator cone layout converted to an approximate metric centerline. Event year and survey accuracy unknown; not an official course."
        url = UPSTREAM+"/fssim_gazebo/models/track/tracks_yaml/"+name+".yaml"
        bundle = manifest(course_id,label,description,track,url,sha256(source.read_bytes()).hexdigest(),"Ordered left-boundary samples (96) projected to nearest right segments, midpoint approximation, exact tangent fillets; source coordinates interpreted as Gazebo meters; no scaling/endpoint correction.")
        catalog["courses"].append((bundle,{"classification":"map_derived_approximation","source_url":url,"license":"MIT (AMZ FSSIM)","audit":{**alignment,**audit}}))
    points = [(0,0),(25,0),(36,4),(47,-4),(58,4),(69,-4),(80,0),(105,0),(115,-10),(112,-25),(95,-33),(84,-42),(68,-46),(60,-37),(50,-32),(42,-43),(24,-46),(6,-36),(-10,-24),(-13,-10)]
    track,audit = rounded_polygon(points)
    bundle = manifest("technical_slalom_v1","Technical slalom · synthetic","Original FSAE-inspired slaloms, changing-radius corners and long braking approaches. Not an official or surveyed event.",track,"Original LapSim technical test vertices",sha256(json.dumps(points).encode()).hexdigest(),"Original metric vertices joined by tangent circular fillets and straights; no source-map copying or endpoint correction.")
    catalog["courses"].append((bundle,{"classification":"synthetic_fsae_inspired","source_url":None,"license":"Repository license unchanged","audit":audit}))
    return catalog["schema"],catalog["courses"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    schema,courses = build()
    catalog = {"schema":schema,"courses":[]}
    payloads = {}
    for bundle,extra in courses:
        payloads[bundle.course_id+".json"] = bundle.to_dict()
        catalog["courses"].append({"id":bundle.course_id,"label":bundle.label,"description":bundle.description,"path":f"configs/courses/{bundle.course_id}.json","length_m":bundle.track.length_m,"geometry_sha256":bundle.geometry_sha256,**extra})
    payloads["catalog.json"] = catalog
    for filename,value in payloads.items():
        path = DESTINATION/filename
        text = json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                raise SystemExit("Course library differs: "+filename)
        else:
            path.write_text(text,encoding="utf-8",newline="\n")
    print(json.dumps({"status":"checked" if args.check else "generated","courses":[{"id":b.course_id,"length_m":b.track.length_m,"cells":b.track.cell_count,**e["audit"]} for b,e in courses]},indent=2))


if __name__ == "__main__":
    main()
