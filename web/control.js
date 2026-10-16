/* Presentation only. Python owns the controller, clocks, plant and energy. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
  let worker=null,boot=null,latest=null,exactJson=null,active=null,revision=0,generation=0,timer=null;
  const status=text=>{$('control-status').textContent=text;};
  function imported(value){for(const element of $('control-form').elements)if(element.id!=='control-cancel')element.disabled=value;}
  function invalidate(){revision++;latest=null;exactJson=null;$('control-results').hidden=true;$('control-save').disabled=true;$('control-csv').disabled=true;}
  function busy(value){clearTimeout(timer);$('control-run').disabled=value;$('control-open').disabled=value;$('control-new').disabled=value;$('control-cancel').hidden=!value;if(value)timer=setTimeout(()=>fail('The comparison timed out. Run again to restart Python.'),180000);}
  function fail(message){generation++;worker?.terminate();worker=null;boot=null;active=null;busy(false);invalidate();$('control-error').textContent=message;$('control-error').hidden=false;status('Comparison did not complete.');}
  function ready(){
    if(boot)return boot;
    const owner=++generation;
    boot=new Promise((resolve,reject)=>{
      worker=new Worker(new URL('worker.js',location.href),{type:'module'});
      worker.onerror=e=>{if(owner===generation){reject(new Error(e.message));fail(e.message);}};
      worker.onmessage=e=>{
        if(owner!==generation)return;
        const m=e.data;
        if(m.type==='status')status(m.message);
        if(m.type==='ready'){if(!m.capabilities.controlStudyBackends?.includes('python_reference')){reject(new Error('This runtime lacks the controller study.'));return;}resolve();}
        if(m.type==='error'){reject(new Error(m.error.message));fail(m.error.message);}
        if(m.type==='result'&&active&&m.requestId===active.id){
          const expected=active.revision,wasImported=active.imported;active=null;busy(false);
          if(expected!==revision){status('Inputs changed. Run the current settings.');return;}
          if(m.result.schema!=='lapsim.control-comparison.v1'||['A','B'].some(k=>m.result.runs[k].scenario.controller_backend_id!=='python_reference')){fail('Unexpected study/backend record.');return;}
          latest=m.result;exactJson=m.resultJson;render();
          if(wasImported){imported(true);status(`Imported comparison · both stored scenarios replayed · run ${latest.run_id.slice(0,12)}. Choose New preset to edit.`);}
        }
      };
      worker.postMessage({type:'init'});
    });return boot;
  }
  function node(tag,attrs,text){const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
  function plot(id,series,yLabel){
    const svg=$(id);svg.replaceChildren();const points=series.flat();
    const width=Math.max(280,Math.round(svg.parentElement.clientWidth));svg.setAttribute('viewBox',`0 0 ${width} 260`);
    let x0=Math.min(...points.map(p=>p[0])),x1=Math.max(...points.map(p=>p[0])),y0=Math.min(...points.map(p=>p[1])),y1=Math.max(...points.map(p=>p[1]));
    const dx=Math.max(.001,x1-x0),dy=Math.max(.001,y1-y0),mid=(y0+y1)/2; y0=mid-dy*.56;y1=mid+dy*.56;
    if(Math.min(...points.map(p=>p[1]))>=0)y0=Math.max(0,y0);
    const X=x=>62+(width-90)*(x-x0)/dx,Y=y=>215-190*(y-y0)/(y1-y0),ticks=width<450?2:4;
    const format=v=>v!==0&&(Math.abs(v)<.001||Math.abs(v)>=100000)?v.toExponential(1):Number(v.toPrecision(3)).toString();
    for(let i=0;i<=ticks;i++){
      const x=x0+dx*i/ticks,y=y0+(y1-y0)*i/ticks;
      svg.append(node('line',{x1:X(x),y1:25,x2:X(x),y2:215,class:'grid'}),node('line',{x1:62,y1:Y(y),x2:width-28,y2:Y(y),class:'grid'}));
      svg.append(node('text',{x:X(x),y:235,'text-anchor':'middle'},x.toFixed(2)),node('text',{x:54,y:Y(y)+4,'text-anchor':'end'},format(y)));
    }
    series.forEach((line,i)=>svg.append(node('polyline',{points:line.map(p=>`${X(p[0])},${Y(p[1])}`).join(' '),class:i?'trace-b':'trace-a'})));
    svg.append(node('text',{x:width/2,y:257,'text-anchor':'middle'},'Time (s)'),node('text',{x:14,y:120,transform:'rotate(-90 14 120)','text-anchor':'middle'},yLabel));
  }
  function render(){
    const runs=['A','B'].map(k=>latest.runs[k]),observations=runs.map(r=>r.result.observations);
    $('control-results').hidden=false;$('control-save').disabled=false;$('control-csv').disabled=false;
    const source=runs[0].runtime.source;
    status(`Completed · Python reference · run ${latest.run_id.slice(0,12)} · source ${source.code_commit?.slice(0,12)??'unavailable'}${source.dirty_worktree?' (working changes)':''}`);
    $('control-summary').textContent=`Each strategy: ${runs[0].result.controller_calls} controller calls, ${runs[0].result.plant_ticks} plant ticks. Inspect both outcomes; lower slip may also reduce driver-demand tracking.`;
    plot('control-speed-plot',observations.map(rows=>rows.map(row=>[row.time_us/1e6,row.state.plant.u_mps])),'u (m/s)');
    plot('control-slip-plot',observations.map(rows=>rows.map(row=>[row.time_us/1e6,Math.max(...row.plant.wheels.slice(2).map(w=>Math.abs(w.slip_ratio)))])),'Rear |slip|');
    plot('control-energy-plot',observations.map(rows=>rows.map(row=>[row.time_us/1e6,rows[0].state.pack_energy_j-row.state.pack_energy_j])),'Pack draw (J)');
    const labels={distance_x_m:'World X (m)',final_speed_mps:'Final forward speed (m/s)',peak_observed_rear_slip:'Peak observed rear |slip|',pack_draw_j:'Pack draw (J)',unmet_command_impulse_nm_s:'Unmet propulsion impulse (N·m·s)',unmet_regen_impulse_nm_s:'Rejected regeneration (N·m·s)',absolute_contact_force_error_ns:'Raw driver/contact proxy error (N·s)',limited_control_ticks:'Limited controller ticks',inhibited_control_ticks:'Inhibited controller ticks',energy_residual_j:'Energy balance residual (J)'};
    const format=v=>v!==0&&(Math.abs(v)<.0001||Math.abs(v)>=1000000)?v.toExponential(2):Number(v.toPrecision(5)).toString();
    const rows=Object.entries(labels).map(([key,label])=>{const tr=document.createElement('tr');const th=document.createElement('th');th.scope='row';th.textContent=label;tr.append(th);for(const k of ['A','B']){const td=document.createElement('td');td.textContent=format(Number(latest.metrics[k][key]));tr.append(td);}return tr;});$('control-metrics').replaceChildren(...rows);
    const stages=[];
    for(const label of ['A','B']){
      const run=latest.runs[label],events=run.result.controller_events;
      let eventIndex=0;
      for(const row of run.result.observations){
        while(eventIndex+1<events.length&&events[eventIndex+1].time_us<=row.time_us)eventIndex++;
        const event=events[eventIndex],tr=document.createElement('tr');
        const values=[label,row.time_us/1e6,event.requested_propulsive_nm,event.core.allocator.wheel_torque_nm.reduce((a,b)=>a+b,0),event.core.guard.output_nm.reduce((a,b)=>a+b,0),row.limited_command_nm.reduce((a,b)=>a+b,0),row.actual_actuator.wheel_torques_nm.reduce((a,b)=>a+b,0),row.plant.wheels.reduce((a,w)=>a+w.body_force_x_n,0)];
        values.forEach(value=>{const td=document.createElement('td');td.textContent=typeof value==='number'?format(value):value;tr.append(td);});stages.push(tr);
      }
    }
    $('control-stages').replaceChildren(...stages);
    $('control-provenance').textContent=JSON.stringify({comparison_policy:latest.comparison_policy,strategies:Object.fromEntries(['A','B'].map(k=>[k,{scenario:latest.runs[k].scenario,units:latest.runs[k].units,runtime:latest.runs[k].runtime,controller_source:latest.runs[k].controller_source,assumptions:latest.runs[k].assumptions}]))},null,2);
  }
  $('control-form').addEventListener('input',()=>{invalidate();status('Settings changed. Run a new matched comparison.');});
  $('control-form').addEventListener('submit',async e=>{
    e.preventDefault();if(active)return;invalidate();$('control-error').hidden=true;const expected=revision;
    const settings={case_id:$('control-case').value,duration_s:Number($('control-duration').value),speed_mps:Number($('control-speed').value),steering_deg:Number($('control-steer').value)};
    busy(true);
    try{await ready();if(expected!==revision){busy(false);status('Settings changed while Python loaded. Run the current settings.');return;}
      active={id:crypto.randomUUID(),revision:expected};status('Running both causal controller/plant loops in Python…');
      worker.postMessage({type:'run',mode:'closed_loop_comparison',requestId:active.id,settings});
    }catch(error){fail(error.message);}
  });
  $('control-cancel').addEventListener('click',()=>{generation++;worker?.terminate();worker=null;boot=null;active=null;busy(false);invalidate();status('Comparison cancelled. Run again when ready.');});
  $('control-open').addEventListener('click',()=>{$('control-file').value='';$('control-file').click();});
  $('control-file').addEventListener('change',async()=>{
    const file=$('control-file').files[0];if(!file)return;
    invalidate();imported(false);$('control-error').hidden=true;const expected=revision;
    busy(true);
    try{
      if(file.size>40000000)throw new Error('Comparison exceeds 40 MB.');
      const recordJson=await file.text();await ready();if(expected!==revision){busy(false);return;}
      active={id:crypto.randomUUID(),revision:expected,imported:true};status('Replaying both saved scenarios in Python…');
      worker.postMessage({type:'run',mode:'closed_loop_comparison_replay',requestId:active.id,recordJson});
    }catch(error){fail(error.message);}
  });
  $('control-new').addEventListener('click',()=>{imported(false);$('control-form').reset();invalidate();$('control-error').hidden=true;status('New preset · ready for a matched comparison.');});
  function download(text,type,suffix){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=`control-${latest.run_id.slice(0,12)}.${suffix}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('control-save').addEventListener('click',()=>{if(latest&&exactJson)download(exactJson,'application/json','json');});
  $('control-csv').addEventListener('click',()=>{
    if(!latest)return;const rows=['strategy,time_s,x_m,y_m,u_mps,yaw_rate_rad_s,rear_max_abs_slip,pack_draw_j,limited_total_nm,actual_total_nm,rear_contact_force_x_n'];
    for(const k of ['A','B']){const samples=latest.runs[k].result.observations,initial=samples[0].state.pack_energy_j;samples.forEach(row=>rows.push([k,row.time_us/1e6,row.state.plant.x_m,row.state.plant.y_m,row.state.plant.u_mps,row.state.plant.yaw_rate_rad_s,Math.max(...row.plant.wheels.slice(2).map(w=>Math.abs(w.slip_ratio))),initial-row.state.pack_energy_j,row.limited_command_nm.reduce((a,b)=>a+b,0),row.actual_actuator.wheel_torques_nm.reduce((a,b)=>a+b,0),row.plant.wheels.slice(2).reduce((a,w)=>a+w.local_force_x_n,0)].join(',')));}
    download(rows.join('\n')+'\n','text/csv','csv');
  });
  window.addEventListener('resize',()=>{if(latest)render();});
})();
