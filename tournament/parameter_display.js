'use strict';
const ParameterDisplay=(()=>{
  const percentages=new Set(['coast_fraction','front_bias','regen_fraction','regen_region','soc_threshold']);
  const units={drive_scale:'× demand',slip_target:'slip ratio',hysteresis_release:'ratio',corner_threshold_rad:'rad',yaw_kp:'Nm·s/rad',yaw_ki:'Nm/rad'};
  function format(name,value){if(typeof value!=='number'||!Number.isFinite(value))return 'Unavailable';if(percentages.has(name))return (value*100).toFixed(1)+'%';return Number(value.toPrecision(3)).toString()+(units[name]?' '+units[name]:'');}
  function label(name){return name.replaceAll('_',' ');}
  function origin(run){return run.policy_origin?.label||'Origin unavailable in this saved projection';}
  return {format,label,origin};
})();
if(typeof module!=='undefined')module.exports=ParameterDisplay;
if(typeof window!=='undefined')window.ParameterDisplay=ParameterDisplay;
