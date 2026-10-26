/* Presentation of recorded lap ledgers only; never advances a simulation. */
(function(root,factory){
 'use strict';const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;else root.LapSimRoundView=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function describe(run){
  const ledger=run.round;
  if(!ledger||ledger.target_laps!==10)return null;
  const need=(ok,message)=>{if(!ok)throw Error('Invalid ten-lap ledger: '+message);};
  need(Number.isInteger(ledger.completed_laps)&&ledger.completed_laps>=0&&ledger.completed_laps<=10,'lap count');
  need(Array.isArray(ledger.laps)&&ledger.laps.length===ledger.completed_laps,'recorded lap count');
  let prior=0,energy=0;
  for(const [i,row] of ledger.laps.entries()){
   need(row.lap===i+1&&[row.finish_time_s,row.lap_time_s,row.net_energy_kwh,row.soc_after].every(Number.isFinite),'ordered finite rows');
   need(row.lap_time_s>0&&Math.abs(row.finish_time_s-prior-row.lap_time_s)<1e-8,'seam time');
   need(row.soc_after>=0&&row.soc_after<=1,'SOC');prior=row.finish_time_s;energy+=row.net_energy_kwh;
  }
  if(run.eligible){
   need(run.status==='completed'&&ledger.completed_laps===10&&run.violations.length===0,'eligible completion');
   need(Number.isFinite(run.metrics.round_time_s)&&Math.abs(prior-run.metrics.round_time_s)<1e-8,'total time');
   need(Math.abs(energy-run.metrics.net_energy_kwh)<1e-11,'total energy');
  }
  return {label:ledger.completed_laps+'/10 laps · '+run.status,timeS:run.metrics.round_time_s,
   laps:ledger.laps,thermalModel:ledger.thermal_model||'Thermal accumulation not modeled'};
 }
 return {describe};
});
