/* Presentation only: the same Python bicycle plant executes in the worker. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
  let worker=null, boot=null, defaults=null, latest=null, exactJson=null, revision=0, active=null, source=null, timeout=null;
  const status=text=>{$('basic-status').textContent=text;};
  function invalidate(){revision++;latest=null;exactJson=null;$('basic-save').disabled=true;$('basic-csv').disabled=true;$('basic-results').hidden=true;}
  function busy(value){clearTimeout(timeout);$('basic-run').disabled=value;$('basic-cancel').hidden=!value;if(value)timeout=setTimeout(()=>fail('Calculation timed out. Run again to restart the runtime.'),180000);}
  function fail(message){worker?.terminate();worker=null;boot=null;defaults=null;active=null;busy(false);invalidate();$('basic-error').hidden=false;$('basic-error').textContent=message;status('Calculation did not complete.');}
  function startRuntime(){
    if(boot)return boot;
    boot=new Promise((resolve,reject)=>{
      worker=new Worker(new URL('worker.js',location.href),{type:'module'});
      worker.onerror=event=>{reject(new Error(event.message));fail(event.message);};
      worker.onmessage=event=>{
        const m=event.data;
        if(m.type==='status')status(m.message);
        if(m.type==='ready'){
          defaults=m.capabilities.basicDynamicsDefaults;source=m.capabilities.sourceIdentity;
          if(!defaults||defaults.model_id!=='dynamic_bicycle_v1'){reject(new Error('This runtime does not support the dynamic bicycle.'));return;}
          resolve();
        }
        if(m.type==='error'){reject(new Error(m.error.message));fail(m.error.message);}
        if(m.type==='result'&&active&&m.requestId===active.id){
          const expected=active.revision;active=null;busy(false);
          if(expected!==revision){status('Inputs changed during calculation. Run the current settings.');return;}
          if(m.result.schema!=='lapsim.basic-dynamics.record.v1'||m.result.scenario.model_id!==$('basic-model').value){fail('Unexpected model result.');return;}
          latest=m.result;exactJson=m.resultJson;render();
        }
      };
      worker.postMessage({type:'init'});
    });return boot;
  }
  function node(tag,attributes,text){const e=document.createElementNS(NS,tag);for(const [key,value]of Object.entries(attributes))e.setAttribute(key,value);if(text!==undefined)e.textContent=text;return e;}
  function plot(id,points,xLabel,yLabel,equal){
    const svg=$(id);svg.replaceChildren();
    let x0=Math.min(...points.map(p=>p[0])),x1=Math.max(...points.map(p=>p[0])),y0=Math.min(...points.map(p=>p[1])),y1=Math.max(...points.map(p=>p[1]));
    let dx=Math.max(x1-x0,0.001),dy=Math.max(y1-y0,0.001),cx=(x0+x1)/2,cy=(y0+y1)/2;
    if(equal){const scale=Math.min(650/dx,190/dy);dx=650/scale;dy=190/scale;}dx*=1.08;dy*=1.08;x0=cx-dx/2;y0=cy-dy/2;
    const X=x=>70+650*(x-x0)/dx,Y=y=>215-190*(y-y0)/dy;
    for(let i=0;i<=4;i++){
      const x=x0+dx*i/4,y=y0+dy*i/4;
      svg.append(node('line',{x1:X(x),y1:25,x2:X(x),y2:215,class:'grid'}),node('line',{x1:70,y1:Y(y),x2:720,y2:Y(y),class:'grid'}));
      svg.append(node('text',{x:X(x),y:235,'text-anchor':'middle'},x.toFixed(2)),node('text',{x:60,y:Y(y)+4,'text-anchor':'end'},y.toFixed(3)));
    }
    svg.append(node('polyline',{points:points.map(p=>`${X(p[0])},${Y(p[1])}`).join(' '),class:'trace'}));
    svg.append(node('text',{x:395,y:257,'text-anchor':'middle'},xLabel),node('text',{x:16,y:120,transform:'rotate(-90 16 120)','text-anchor':'middle'},yLabel));
  }
  function render(){
    const r=latest.result,s=r.states,last=s.at(-1);
    $('basic-results').hidden=false;$('basic-save').disabled=false;$('basic-csv').disabled=false;
    $('basic-summary').textContent=`At ${r.time_s.at(-1).toFixed(2)} s: forward speed ${last.u_mps.toFixed(3)} m/s, yaw rate ${last.yaw_rate_rad_s.toFixed(4)} rad/s. ${r.plant_ticks} plant ticks.`;
    status(`Completed · ${latest.scenario.model_id} · run ${latest.run_id.slice(0,12)} · source ${source?.code_commit?.slice(0,12)??'unavailable'}${source?.dirty_worktree?' (working changes)':''}`);
    plot('basic-path',s.map(v=>[v.x_m,v.y_m]),'World X (m)','World Y (m)',true);
    plot('basic-yaw',s.map((v,i)=>[r.time_s[i],v.yaw_rate_rad_s]),'Time (s)','Yaw rate (rad/s)',false);
    const stride=Math.max(1,Math.ceil((s.length-1)/20)),rows=[];
    for(let i=0;i<s.length;i++){if(i%stride&&i!==s.length-1)continue;const tr=document.createElement('tr');for(const v of [r.time_s[i],s[i].x_m,s[i].y_m,s[i].u_mps,s[i].v_mps,s[i].yaw_rate_rad_s]){const td=document.createElement('td');td.textContent=v.toFixed(4);tr.append(td);}rows.push(tr);}
    $('basic-samples').replaceChildren(...rows);
    $('basic-provenance').textContent=JSON.stringify({scenario:latest.scenario,configuration_sha256:latest.configuration_sha256,source,runtime:latest.runtime,solver:latest.solver,units:latest.units,assumptions:latest.assumptions},null,2);
  }
  $('basic-form').addEventListener('input',()=>{invalidate();status('Settings changed. Run to calculate this maneuver.');});
  $('basic-form').addEventListener('submit',async event=>{
    event.preventDefault();if(active)return;invalidate();$('basic-error').hidden=true;busy(true);
    try{
      await startRuntime();const settings=structuredClone(defaults),values=['basic-speed','basic-steer','basic-force','basic-duration'].map(id=>Number($(id).value));
      const [speed,steer,force,duration]=values;
      if(!values.every(Number.isFinite)||speed<0||speed>30||Math.abs(steer)>15||force<0||force>1500||duration<0.1||duration>10)throw new Error('Choose finite values within the labeled ranges.');
      settings.model_id=$('basic-model').value;settings.initial_state.u_mps=speed;settings.controls.steering_angle_rad=steer*Math.PI/180;settings.controls.rear_force_request_n=force;settings.duration_s=duration;
      active={id:crypto.randomUUID(),revision};status('Calculating the dynamic bicycle in Python…');
      worker.postMessage({type:'run',mode:'basic_dynamics',requestId:active.id,settings});
    }catch(error){fail(error.message);}
  });
  $('basic-cancel').addEventListener('click',()=>{worker?.terminate();worker=null;boot=null;active=null;busy(false);invalidate();status('Calculation cancelled. Run again when ready.');});
  function download(text,type,suffix){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=`bicycle-${latest.run_id.slice(0,12)}.${suffix}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('basic-save').addEventListener('click',()=>{if(latest&&exactJson)download(exactJson,'application/json','json');});
  $('basic-csv').addEventListener('click',()=>{if(!latest)return;const r=latest.result,lines=['time_s,x_m,y_m,u_mps,v_mps,yaw_rate_rad_s'];r.states.forEach((s,i)=>lines.push([r.time_s[i],s.x_m,s.y_m,s.u_mps,s.v_mps,s.yaw_rate_rad_s].join(',')));download(lines.join('\n')+'\n','text/csv','csv');});
})();
