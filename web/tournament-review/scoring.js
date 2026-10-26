/* Display projection matching the campaign score_field contract; no physics. */
'use strict';
const TournamentScoring=(()=>{
  const VERSION='lapsim.fsae-inspired-equal-lap-2027v1.1';
  const SOURCE='https://www.fsaeonline.com/cdsweb/gen/DownloadDocument.aspx?DocumentID=da79bcb4-0935-4f7b-83d7-0dbb8ce68d38';
  const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
  function efficiencyPoints(factor,fmin,fmax){
    if(![factor,fmin,fmax].every(Number.isFinite)||!positive(fmax-fmin))return null;
    const points=100*(factor-fmin)/(fmax-fmin);
    return Number.isFinite(points)&&points>=-1e-9&&points<=100+1e-9?Math.max(0,Math.min(100,points)):null;
  }
  function scoreField(runs){
    if(!Array.isArray(runs)||!runs.length)throw Error('A nonempty field is required');
    if(new Set(runs.map(r=>JSON.stringify([r.hardware,r.geometry_sha256,r.laps]))).size!==1)throw Error('Separate geometry, hardware and equal-lap fields');
    if(new Set(runs.map(r=>r.candidate_id)).size!==runs.length)throw Error('Duplicate field candidate');
    const rows=Object.create(null),finishers=[],unavailable=[];
    const references={source_url:SOURCE,version:VERSION,official_points:false,fmax_interpretation:'Best eligible observed factor in the matched field',scope:'Equal simulated laps replace endurance; 25 simulated completion points; no real driver change/inspection or event penalty model. Mean across six courses is a tournament choice, not a rulebook aggregation.'};
    for(const run of runs){
      const row={candidate_id:run.candidate_id,scoring_version:VERSION,official_points:false,completed:run.completed,valid:run.valid,penalty_s:run.penalty_s??0,penalties_modeled:run.penalties_modeled??false,endurance_points:null,efficiency_points:null,total_points:null,efficiency_eligible:false,reasons:[]};rows[run.candidate_id]=row;
      if(!run.completed||!run.valid){Object.assign(row,{endurance_points:0,efficiency_points:0,total_points:0});row.reasons.push('Incomplete or physically invalid; never aggregate as a successful low-energy lap');continue;}
      if(!Number.isInteger(run.laps)||run.laps<1||!positive(run.distance_m)||!positive(run.time_s)||!positive(run.net_energy_kwh)||typeof row.penalty_s!=='number'||!Number.isFinite(row.penalty_s)||row.penalty_s<0){row.reasons.push('Positive finite measured time, net energy, distance and valid penalties required');unavailable.push(run.candidate_id);continue;}
      const corrected=run.time_s+row.penalty_s;
      if(!positive(corrected)){row.reasons.push('Invalid corrected time');unavailable.push(run.candidate_id);continue;}
      const energyWh=run.net_energy_kwh*1000,co2=.65*run.net_energy_kwh;
      if(!positive(energyWh)||!positive(co2)){row.reasons.push('Energy conversion is nonfinite or unmeasurable');unavailable.push(run.candidate_id);continue;}
      Object.assign(row,{corrected_time_s:corrected,net_energy_wh:energyWh,co2_kg:co2,distance_m:run.distance_m});finishers.push(run);
    }
    if(unavailable.length){references.unavailable_reference_candidates=unavailable;return {rows,references,available:false};}
    if(!finishers.length)return {rows,references,available:false};
    const best=Math.min(...finishers.map(r=>rows[r.candidate_id].corrected_time_s)),cutoff=1.45*best;
    if(!positive(cutoff)){references.unavailable_reason='Nonfinite endurance cutoff';return {rows,references,available:false};}
    Object.assign(references,{best_full_finisher_time_s:best,endurance_cutoff_s:cutoff});
    const eligible=[];
    for(const run of finishers){const row=rows[run.candidate_id],time=row.corrected_time_s;row.endurance_points=time>=cutoff?25:250*((cutoff/time)-1)/((cutoff/best)-1)+25;row.efficiency_points=0;
      if(time>cutoff)row.reasons.push('Beyond 1.45 fastest full-finisher time');
      if(run.net_energy_kwh>.308*run.distance_m/1000)row.reasons.push('Above EV efficiency consumption cap of 0.308 kWh/km');
      if(!row.reasons.length)eligible.push(run);
    }
    if(eligible.length){
      const timeRef=eligible.reduce((a,b)=>rows[a.candidate_id].corrected_time_s<=rows[b.candidate_id].corrected_time_s?a:b),energyRef=eligible.reduce((a,b)=>rows[a.candidate_id].co2_kg<=rows[b.candidate_id].co2_kg?a:b);
      const tref=rows[timeRef.candidate_id].corrected_time_s/timeRef.laps,cref=rows[energyRef.candidate_id].co2_kg/energyRef.laps,capPerLap=.65*.308*(timeRef.distance_m/timeRef.laps)/1000;
      if(!positive(capPerLap)){references.unavailable_reason='Invalid efficiency reference capacity';return {rows,references,available:false};}
      const fmin=(1/1.45)*(cref/capPerLap),factors=Object.fromEntries(eligible.map(r=>[r.candidate_id,(tref/(rows[r.candidate_id].corrected_time_s/r.laps))*(cref/(rows[r.candidate_id].co2_kg/r.laps))])),fmax=Math.max(...Object.values(factors));
      Object.assign(references,{time_reference_candidate:timeRef.candidate_id,energy_reference_candidate:energyRef.candidate_id,time_reference_per_lap_s:tref,co2_reference_per_lap_kg:cref,fmin,fmax});
      if(!positive(fmax-fmin)){for(const run of eligible)rows[run.candidate_id].reasons.push('Nonpositive efficiency normalization denominator');return {rows,references,available:false};}
      for(const run of eligible){const row=rows[run.candidate_id],points=efficiencyPoints(factors[run.candidate_id],fmin,fmax);if(points===null){row.reasons.push('Efficiency points outside mathematical bounds');return {rows,references,available:false};}Object.assign(row,{efficiency_eligible:true,efficiency_factor:factors[run.candidate_id],efficiency_points:points});}
    }
    for(const run of finishers){const row=rows[run.candidate_id];row.total_points=row.endurance_points+row.efficiency_points;}
    return {rows,references,available:true};
  }
  function forGroup(group){
    const selected=group.runs.filter(r=>r.selection_eligible!==false);
    if(new Set(selected.map(r=>r.target_laps)).size>1)throw Error('Separate geometry, hardware and equal-lap fields');
    if(selected.some(r=>r.fsae_inspired_points!=null)){
      const rows=Object.create(null);let available=true;
      for(const run of selected){const row=run.fsae_inspired_points;if(!row||row.scoring_version!==VERSION||row.official_points!==false||typeof row.field_available!=='boolean'||!Array.isArray(row.reasons)||!row.reasons.every(v=>typeof v==='string')||!['endurance_points','efficiency_points','total_points'].every(k=>row[k]===null||Number.isFinite(row[k]))){available=false;continue;}rows[run.id]=row;if(!row.field_available)available=false;else if(![row.endurance_points,row.efficiency_points,row.total_points].every(Number.isFinite)||row.endurance_points<0||row.endurance_points>275+1e-9||row.efficiency_points<0||row.efficiency_points>100+1e-9||Math.abs(row.endurance_points+row.efficiency_points-row.total_points)>1e-9)available=false;}
      return {rows,references:group.fsae_inspired_references||{version:VERSION,official_points:false,source_url:SOURCE,scope:'Recorded canonical campaign score fields; missing or version-mismatched fields are unrankable.'},available};
    }
    const runs=selected.map(r=>({candidate_id:r.id,hardware:group.hardware_sha256,geometry_sha256:group.geometry_sha256,laps:r.target_laps,distance_m:group.length_m*r.target_laps,time_s:r.time_s,net_energy_kwh:r.energy_wh/1000,completed:r.status==='completed'&&r.completed_laps===r.target_laps,valid:r.accepted,penalty_s:r.penalty_s??0,penalties_modeled:r.penalties_modeled??false}));
    if(!runs.length)return {rows:{},references:{version:VERSION,official_points:false,source_url:SOURCE},available:false};
    return scoreField(runs);
  }
  return {VERSION,SOURCE,scoreField,forGroup,efficiencyPoints};
})();
if(typeof module!=='undefined')module.exports=TournamentScoring;
if(typeof window!=='undefined')window.TournamentScoring=TournamentScoring;
