"""FSAE-inspired simulated endurance/efficiency, never official event points.

SAE 2027 V1 D12.13 and D13.3-4 supply the 275/100 formula. Our adaptation
substitutes equal simulated laps for endurance, awards 25 simulated completion
points, and has no real driver change, inspection or event penalty tally.
References are calculated separately for each geometry/hardware/equal-lap field.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence, TypeGuard

VERSION='lapsim.fsae-inspired-equal-lap.v1.2'
SOURCE='https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38'
EV_KG_CO2_PER_KWH=.65
EV_CAP_KWH_PER_KM=.308


@dataclass(frozen=True)
class ScoringRun:
    candidate_id: str
    hardware: str
    geometry_sha256: str
    laps: int
    distance_m: float
    time_s: float | None
    net_energy_kwh: float | None
    completed: bool
    valid: bool
    penalty_s: float=0.
    penalties_modeled: bool=False


def positive(value: object) -> TypeGuard[int | float]:
    return isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value) and value>0


def score_field(runs: Sequence[ScoringRun]):
    """Return component points and references for one matched available field.

    Fmax is interpreted as the best eligible observed efficiency factor.
    The caller must mark missing frozen-pool results provisional. Net energy
    already credits regen; recovered energy must never be subtracted again.
    """
    if not runs:raise ValueError('A nonempty field is required')
    if len({(r.hardware,r.geometry_sha256,r.laps) for r in runs})!=1:
        raise ValueError('Separate geometry, hardware and equal-lap fields')
    if len({r.candidate_id for r in runs})!=len(runs):raise ValueError('Duplicate field candidate')
    rows: dict[str,dict[str,Any]]={}
    finishers=[]
    unavailable_inputs=[]
    for run in runs:
        row={'candidate_id':run.candidate_id,'scoring_version':VERSION,'official_points':False,
            'completed':run.completed,'valid':run.valid,'penalty_s':run.penalty_s,'penalties_modeled':run.penalties_modeled,
            'endurance_points':None,'efficiency_points':None,'total_points':None,'efficiency_eligible':False,'reasons':[]}
        rows[run.candidate_id]=row
        if not run.completed or not run.valid:
            row.update(endurance_points=0.,efficiency_points=0.,total_points=0.)
            row['reasons'].append('Incomplete or physically invalid; never aggregate as a successful low-energy lap')
            continue
        if (type(run.laps) is not int or run.laps<1 or not positive(run.distance_m)
                or not positive(run.time_s) or not positive(run.net_energy_kwh)
                or type(run.penalty_s) not in (int,float) or not isfinite(run.penalty_s) or run.penalty_s<0):
            row['reasons'].append('Positive finite measured time, net energy, distance and valid penalties required')
            unavailable_inputs.append(run.candidate_id)
            continue
        corrected=float(run.time_s)+run.penalty_s
        if not positive(corrected):
            row['reasons'].append('Invalid corrected time')
            unavailable_inputs.append(run.candidate_id)
            continue
        energy_wh=float(run.net_energy_kwh)*1000
        co2_kg=EV_KG_CO2_PER_KWH*float(run.net_energy_kwh)
        if not positive(energy_wh) or not positive(co2_kg):
            row['reasons'].append('Energy conversion is nonfinite or unmeasurable')
            unavailable_inputs.append(run.candidate_id)
            continue
        row.update(corrected_time_s=corrected,net_energy_wh=energy_wh,
            co2_kg=co2_kg,distance_m=run.distance_m)
        finishers.append(run)
    references: dict[str,Any]={'source_url':SOURCE,'version':VERSION,'rule_edition':'SAE 2027 V1 D12.13 and D13.3-4','official_points':False,
        'fmax_interpretation':'Best eligible observed factor in the matched field',
        'scope':'Equal simulated laps replace endurance; 25 simulated completion points; no real driver change/inspection or event penalty model. Mean across six courses is a tournament choice, not a rulebook aggregation.'}
    if unavailable_inputs:
        references['unavailable_reference_candidates']=unavailable_inputs
        return {'rows':rows,'references':references,'available':False}
    if not finishers:return {'rows':rows,'references':references,'available':False}
    best=min(rows[r.candidate_id]['corrected_time_s'] for r in finishers)
    cutoff=1.45*best
    if not positive(cutoff):
        references['unavailable_reason']='Nonfinite endurance cutoff'
        return {'rows':rows,'references':references,'available':False}
    endurance_denominator=(cutoff/best)-1.
    if not positive(endurance_denominator):
        references['unavailable_reason']='Nonpositive endurance normalization denominator'
        return {'rows':rows,'references':references,'available':False}
    references.update(best_full_finisher_time_s=best,endurance_cutoff_s=cutoff)
    efficiency=[]
    for run in finishers:
        row=rows[run.candidate_id];time=row['corrected_time_s']
        row['endurance_points']=25. if time>=cutoff else 250.*((cutoff/time)-1.)/endurance_denominator+25.
        row['efficiency_points']=0.
        if time>cutoff:row['reasons'].append('Beyond 1.45 fastest full-finisher time')
        if row['net_energy_wh']/1000>EV_CAP_KWH_PER_KM*run.distance_m/1000:
            row['reasons'].append('Above EV efficiency consumption cap of 0.308 kWh/km')
        if not row['reasons']:efficiency.append(run)
    if efficiency:
        time_ref=min(efficiency,key=lambda r:rows[r.candidate_id]['corrected_time_s'])
        energy_ref=min(efficiency,key=lambda r:rows[r.candidate_id]['co2_kg'])
        try:
            averages={r.candidate_id:(rows[r.candidate_id]['corrected_time_s']/r.laps,
                rows[r.candidate_id]['co2_kg']/r.laps,r.distance_m/r.laps) for r in efficiency}
        except (OverflowError,ZeroDivisionError):
            references['unavailable_reason']='Unrepresentable per-lap divisor'
            return {'rows':rows,'references':references,'available':False}
        if any(not positive(v) for values in averages.values() for v in values):
            references['unavailable_reason']='Nonfinite or underflowed per-lap reference'
            return {'rows':rows,'references':references,'available':False}
        tref=averages[time_ref.candidate_id][0]
        cref=averages[energy_ref.candidate_id][1]
        cap_per_lap=EV_KG_CO2_PER_KWH*EV_CAP_KWH_PER_KM*averages[time_ref.candidate_id][2]/1000
        if not positive(cap_per_lap):
            references['unavailable_reason']='Nonfinite or underflowed per-lap energy cap'
            return {'rows':rows,'references':references,'available':False}
        fmin=(1/1.45)*(cref/cap_per_lap)
        factors={r.candidate_id:(tref/averages[r.candidate_id][0])*(cref/averages[r.candidate_id][1]) for r in efficiency}
        fmax=max(factors.values());denominator=fmax-fmin
        references.update(time_reference_candidate=time_ref.candidate_id,energy_reference_candidate=energy_ref.candidate_id,
            time_reference_per_lap_s=tref,co2_reference_per_lap_kg=cref,fmin=fmin,fmax=fmax)
        if not positive(denominator):
            for run in efficiency:rows[run.candidate_id]['reasons'].append('Nonpositive efficiency normalization denominator')
            return {'rows':rows,'references':references,'available':False}
        for run in efficiency:
            row=rows[run.candidate_id];points=100.*(factors[run.candidate_id]-fmin)/denominator
            if not isfinite(points) or not -1e-9<=points<=100+1e-9:
                row['reasons'].append('Efficiency points outside mathematical bounds');continue
            row.update(efficiency_eligible=True,efficiency_factor=factors[run.candidate_id],efficiency_points=max(0.,min(100.,points)))
    for run in finishers:
        row=rows[run.candidate_id]
        row['total_points']=row['endurance_points']+row['efficiency_points']
    return {'rows':rows,'references':references,'available':True}
