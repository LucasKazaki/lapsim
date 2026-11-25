"""Ordered finite CG crossings of *accepted* 10 ms numerical boundary chords.

Independent of nearest-station projection for awarding crossings. A projected
seam is a diagnostic / missed-prerequisite check, never a finish. Source gate
centers, tangent/normal, and already body-shrunk aperture are supplied intact.
No integration, extrapolation, altered boundary, or true-dynamics certificate.
The configured runner binds the explicit contract to its canonical synthetic
source and assumed body before the first controller or plant observation.
"""
from __future__ import annotations
from bisect import bisect_right
from hashlib import sha256
import json
import math
import numpy as np

from lapsim.courses.course_bundle import course_geometry_sha256

DT=.01
SCHEMA='lapsim.finite-gate-contract.v1'

# Fixed numerical diagnostic assumptions, not measured vehicle or course
# dimensions. Match the previously reviewed synthetic stadium contract.
GATE_SPACING_M = 5.
OVERHANG_M = .25


def _arc_pose(track, station):
    """Evaluate the exact coherent constant-curvature arc at a station."""
    s = station % track.length_m
    ds = track.distance_m
    i = min(track.cell_count - 1, bisect_right(ds, s) - 1)
    d = s - ds[i]
    k = track.curvature_per_m[i]
    h = math.atan2(track.y_m[i+1]-track.y_m[i], track.x_m[i+1]-track.x_m[i]) - .5*k*(ds[i+1]-ds[i])
    h1 = h+k*d
    if abs(k) < 1e-12:
        x = track.x_m[i]+d*math.cos(h)
        y = track.y_m[i]+d*math.sin(h)
    else:
        x = track.x_m[i]+(math.sin(h1)-math.sin(h))/k
        y = track.y_m[i]+(math.cos(h)-math.cos(h1))/k
    return x, y, h1


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_gate_contract(track, settings, car):
    """Derive finite gates and their assumed aperture from one reviewed source.

    The runner, not an external caller's geometrical claims, chooses these
    assumptions. The rotation-invariant disk encloses the declared numerical
    body rectangle. This is not a surveyed course or swept-dynamics proof.
    """
    if not track.closed:
        raise ValueError("Finite finish requires a closed source course")
    track.validate_coherent_arcs()
    half = settings.assumed_half_width_m
    body_half = settings.vehicle_width_m / 2.
    radius = math.hypot(max(car.cg_to_front_axle_m, car.cg_to_rear_axle_m)+OVERHANG_M, body_half)
    sag = max(((1.-math.cos(.5*abs(k)*ds))/abs(k) if abs(k)>1e-12 else 0.)
              for k, ds in zip(track.curvature_per_m, track.cell_length_m, strict=True))
    limit = half-settings.safety_margin_m-radius
    if not math.isfinite(limit) or limit <= sag or limit <= 0.:
        raise ValueError("Assumed body does not fit the canonical finite corridor")
    stations = [i*GATE_SPACING_M for i in range(1, math.ceil(track.length_m/GATE_SPACING_M))
                if i*GATE_SPACING_M < track.length_m] + [track.length_m]
    gates = []
    for i, s in enumerate(stations, 1):
        x, y, h = _arc_pose(track, s)
        gates.append({"index": i, "station_m": s, "center": [x, y],
                      "tangent": [math.cos(h), math.sin(h)],
                      "normal": [-math.sin(h), math.cos(h)],
                      "center_half_width_m": limit})
    corridor = {"half_width_m": half, "body_width_m": settings.vehicle_width_m,
                "front_extent_m": car.cg_to_front_axle_m+OVERHANG_M,
                "rear_extent_m": car.cg_to_rear_axle_m+OVERHANG_M,
                "overhang_each_end_m": OVERHANG_M, "disk_radius_m": radius,
                "safety_margin_m": settings.safety_margin_m,
                "center_limit_m": limit, "source_arc_chord_sagitta_bound_m": sag,
                "nominal_tire_mu": car.tire_mu, "gravity_mps2": car.gravity_mps2,
                "gates": gates}
    return {"schema": SCHEMA, "source_geometry_sha256": course_geometry_sha256(track),
            "source_length_m": track.length_m,
            "corridor_sha256": sha256(_canonical_bytes(corridor)).hexdigest(),
            "gates": gates}


def _matches_canonical_wire(supplied, canonical):
    """Compare only the bounded trusted schema, never serialize untrusted data."""
    if type(supplied) is not type(canonical):
        return False
    if type(canonical) is dict:
        if len(supplied) != len(canonical) or any(type(k) is not str for k in supplied):
            return False
        return all(k in supplied and _matches_canonical_wire(supplied[k], value)
                   for k, value in canonical.items())
    if type(canonical) is list:
        return len(supplied) == len(canonical) and all(
            _matches_canonical_wire(a, b) for a, b in zip(supplied, canonical, strict=True))
    if type(canonical) is float:
        # Preserve the exact finite JSON numerical identity, including the
        # signed zero in a canonical tangent/normal. No conversion of an
        # untrusted object, tuple, Boolean, or numeric string is allowed.
        return math.isfinite(supplied) and supplied == canonical and (
            supplied != 0. or math.copysign(1., supplied) == math.copysign(1., canonical))
    return supplied == canonical


def validate_canonical_contract(supplied, canonical):
    """Fail closed even if the caller has rehashed a changed gate list."""
    if not _matches_canonical_wire(supplied, canonical):
        raise ValueError("Explicit canonical finite gate contract must match the configured source and assumed body")
    # Geometry shape, direction, finite values and ordered station checks,
    # separate from equality of serialized source evidence.
    FiniteGateObserver(canonical)
    return canonical

class FiniteGateObserver:
    def __init__(self, contract):
        if type(contract) is not dict or set(contract)!={'schema','source_geometry_sha256','source_length_m','corridor_sha256','gates'} or contract['schema']!=SCHEMA:raise ValueError('Exact finite gate contract required')
        for k in ('source_geometry_sha256','corridor_sha256'):
            h=contract[k]
            if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('Invalid finite gate provenance')
        self.length=float(contract['source_length_m']);gs=contract['gates'];self.n=len(gs)
        if not math.isfinite(self.length) or self.length<=0 or self.n<2:raise ValueError('Closed route and ordered finite gates required')
        s=[];cent=[];tan=[];normal=[];half=[]
        for i,g in enumerate(gs,1):
            if set(g)!={'index','station_m','center','tangent','normal','center_half_width_m'} or type(g['index']) is not int or g['index']!=i:raise ValueError('Invalid ordered gate identity')
            s.append(float(g['station_m']));cent.append(g['center']);tan.append(g['tangent']);normal.append(g['normal']);half.append(float(g['center_half_width_m']))
        if not all(math.isfinite(v) and v>0 for v in (*s,*half)) or any(a>=b for a,b in zip(s,s[1:])) or s[-1]!=self.length:raise ValueError('Invalid gate station/aperture')
        self.cent=np.array(cent,dtype=float);self.tan=np.array(tan,dtype=float);self.normal=np.array(normal,dtype=float);self.half=np.array(half,dtype=float)
        if not all(a.shape==(self.n,2) and np.all(np.isfinite(a)) for a in (self.cent,self.tan,self.normal)):raise ValueError('Finite 2D gate geometry required')
        if not np.all(np.abs(np.sum(self.tan*self.tan,axis=1)-1)<1e-12) or not np.all(np.abs(np.sum(self.normal*self.normal,axis=1)-1)<1e-12) or not np.all(np.abs(np.sum(self.tan*self.normal,axis=1))<1e-12):raise ValueError('Orthonormal gate geometry required')
        for arr in (self.cent,self.tan,self.normal,self.half):arr.setflags(write=False)
        self.geometry=contract['source_geometry_sha256'];self.corridor=contract['corridor_sha256'];self.events=[];self.rejected=[];self.outside_count=0;self.pending={};self.prev=None;self.xy=None;self.energy=None;self.tick=-1;self.failure=None;self.finish=None;self.projected=None

    @property
    def next_gate(self):return len(self.events)+1
    @property
    def done(self):return self.finish is not None and self.failure is None
    def _fail(self,reason,detail=None):
        if self.failure is None:self.failure={'reason':reason,'accepted_tick':self.tick,'expected_gate':self.next_gate,'detail':detail}
        self.finish=None
    def _event(self,j,now,xy,energy):
        prev,previous_xy,previous_energy=self.prev,self.xy,self.energy
        if prev is None or previous_xy is None or previous_energy is None:
            raise ValueError('A finite crossing requires two consecutive accepted observations')
        a=-prev[j]/(now[j]-prev[j]);p=previous_xy+a*(xy-previous_xy);lat=float(np.dot(p-self.cent[j],self.normal[j]));forward=bool(now[j]>prev[j]);fraction=float(a)
        return {'gate':int(j+1),'interval_end_tick':self.tick,'alpha':fraction,'direction':'forward' if forward else 'reverse','lateral_m':lat,'time_s':(self.tick-1+fraction)*DT,'crossing_position_m':p.tolist(),'interpolated_pack_energy_j':float(previous_energy+fraction*(energy-previous_energy)),'signed_before_m':float(prev[j]),'signed_after_m':float(now[j]),'confirmed_tick':self.tick,'inside':bool(abs(lat)<=self.half[j])}

    def _apply(self,ev):
        i=ev['gate'];inside=ev['inside'];forward=ev['direction']=='forward'
        if not inside:
            self.outside_count+=1
            if len(self.rejected)<40:self.rejected.append(ev)
            # Distant extensions of other gates are not checkpoints. The
            # very next required gate passed in its forward direction outside
            # the fixed aperture is an actual missed checkpoint.
            if forward and i==self.next_gate:self._fail('missed_expected_gate_outside_aperture',ev)
            return
        if not forward:self._fail('backward_finite_gate',ev);return
        if i==self.n and i!=self.next_gate:self._fail('premature_finite_finish',ev);return
        if i<self.next_gate:self._fail('repeated_finite_gate',ev);return
        if i>self.next_gate:self._fail('missed_or_out_of_order_finite_gate',ev);return
        self.events.append(ev)
        if i==self.n:self.finish=ev

    def observe(self,tick,xy,energy_j,projected_station_m,*,boundary_ok=True):
        if self.failure is not None or self.done:raise ValueError('Cannot append after finite terminal')
        if type(boundary_ok) is not bool:raise ValueError('Boolean accepted stock boundary required')
        if type(tick) is not int or tick!=self.tick+1:raise ValueError('Only consecutive accepted boundaries may be observed')
        p=np.array(xy,dtype=float);e=float(energy_j);s=float(projected_station_m)
        if p.shape!=(2,) or not np.all(np.isfinite(p)) or not math.isfinite(e) or e<0 or not math.isfinite(s):raise ValueError('Nonfinite accepted gate observation')
        self.tick=tick;now=np.sum((p-self.cent)*self.tan,axis=1)
        if self.prev is None:
            # Exact source spawn at the declared finite seam; no gate credit
            # for merely starting on it. No epsilon shifts to later gates.
            lat=float(np.dot(p-self.cent[-1],self.normal[-1]))
            if now[-1]!=0. or abs(lat)>self.half[-1] or s!=0.:self._fail('invalid_seam_spawn',{'signed_m':float(now[-1]),'lateral_m':lat,'station_m':s})
        else:
            ready=[];old_pending=set(self.pending)
            # Determine true passage when an accepted sample lands exactly on
            # a gate plane. Preserve the original touch timestamp only after
            # a later actual sample confirms traversal; a bounce cannot earn.
            for j in sorted(old_pending):
                ev=self.pending[j]
                if now[j]==0.:
                    if ev['inside'] and abs(float(np.dot(p-self.cent[j],self.normal[j])))>self.half[j]:self._fail('left_aperture_while_on_gate',ev)
                    continue
                del self.pending[j];passed=(now[j]>0.)==(ev['direction']=='forward')
                if passed:
                    ev={**ev,'confirmed_tick':tick};ready.append(ev)
                elif ev['inside']:self._fail('finite_gate_touch_reversed',ev)
            indexes=np.flatnonzero(((self.prev<0)&(now>=0))|((self.prev>0)&(now<=0)))
            for j0 in indexes:
                j=int(j0);ev=self._event(j,now,p,e)
                if now[j]==0.:self.pending[j]=ev
                else:ready.append(ev)
            # Departure backward from the start seam is not a free crossing.
            if tick==1 and self.prev[-1]==0. and now[-1]<0. and abs(float(np.dot(self.xy-self.cent[-1],self.normal[-1])))<=self.half[-1]:self._fail('backward_seam_departure')
            ready.sort(key=lambda v:(v['interval_end_tick'],v['alpha'],v['gate']))
            # Two different finite gates at the same numerical time cannot
            # be ordered safely. Do not manufacture sequence from array order.
            finite=[v for v in ready if v['inside']]
            if any(a['interval_end_tick']==b['interval_end_tick'] and a['alpha']==b['alpha'] for a,b in zip(finite,finite[1:])):self._fail('ambiguous_simultaneous_finite_gates')
            pending_finite=[v for v in self.pending.values() if v['inside']]
            if pending_finite and any((x['interval_end_tick'],x['alpha'])>(y['interval_end_tick'],y['alpha']) for x in finite for y in pending_finite):self._fail('unconfirmed_touch_before_other_finite_event')
            for ev in ready:
                if self.failure is not None:break
                if self.finish is not None:
                    if ev['inside']:self._fail('additional_finite_gate_in_finish_interval',ev)
                    elif ev['direction']=='forward' and ev['gate']==self.next_gate:self._fail('additional_missed_gate_in_finish_interval',ev)
                    continue
                self._apply(ev)
            if self.finish is not None and pending_finite:self._fail('unconfirmed_finite_gate_in_finish_interval')
        self.prev=now;self.xy=p;self.energy=e
        if s>=self.length and self.projected is None:self.projected={'accepted_tick':tick,'station_m':s,'confirmed_gate_count':len(self.events),'signed_finish_m':float(now[-1]),'xy_m':p.tolist()}
        if self.projected is not None and self.failure is None and not self.done:
            # Missing intermediate gate is never cured by a projected lap.
            if self.next_gate!=self.n:self._fail('projected_seam_missing_prior_ordered_gate')
            elif now[-1]>0. and self.n-1 not in self.pending:self._fail('finish_plane_passed_without_ordered_finite_crossing')
            # Exactly on the plane (pending) or still behind it: continue real
            # accepted physics; no manufactured terminal and no elapsed cap.
        # The physical event can remain visible in the raw event audit, but
        # a coincident invalid stock boundary cannot earn an accepted finish.
        if not boundary_ok and self.failure is None:self._fail('stock_boundary_rejected')
        return self.done

    def receipt(self):
        return {'schema':'lapsim.ordered-finite-crossing.v1','geometry_sha256':self.geometry,'corridor_sha256':self.corridor,'gate_count':self.n,'confirmed_gate_count':len(self.events),'events':self.events,'outside_line_crossings':self.outside_count,'rejected_extended_line_crossings_first40':self.rejected,'pending_exact_plane_touches':list(self.pending.values()),'first_projected_seam':self.projected,'last_accepted_tick':self.tick,'last_signed_finish_m':float(self.prev[-1]) if self.prev is not None else None,'finish_event':self.finish if self.done else None,'failure':self.failure,'ordered_finite_complete':self.done,'scope':'Actual accepted 10ms numerical CG chord intersection in fixed finite body-shrunk apertures; original separate corridor, tire, actuator and numerical body checks still required. No physical crossing from projection or extrapolation.'}
