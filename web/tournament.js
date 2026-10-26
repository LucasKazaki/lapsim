/* Logged-data presentation only: no plant, controller or invented fitness. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),canvas=$('scene-legacy'),ctx=canvas.getContext('2d'),NS='http://www.w3.org/2000/svg';
 const colors=['#5bdfd5','#ffbd66','#b2a2ff','#ff7d9f','#83ce7b','#82b9ff','#ff9c6d','#d3e28f'];
 let importedCourse=null, replayRequest=0;
 const courseLibrary=window.LapSimCourseLibrary?.mount({select:$('course'),status:$('course-library-status'),preview:$('course-preview'),changed:()=>{const chosen=courseLibrary?.selection();$('course-status').textContent=(chosen?'Next run: '+chosen.label+' Â· '+chosen.length_m.toFixed(1)+' m. ':'Next run uses the selected built-in/imported course. ')+'The displayed replay keeps its original recorded course until a new run completes.';}});
 let data=null,rounds=[],selected=[],t=0,playing=false,last=0,az=-.65,elev=.9,zoom=1,camera='orbit',job=null;
 const error=e=>{$('error').hidden=false;$('error').textContent=String(e.message||e);};
 const fmt=(n,d=3)=>n==null?'â€”':Number(n).toFixed(d);
 const controllerLabel=r=>r.campaign_label??(r.configuration?`${r.configuration.profile.profile_id} / ${r.configuration.profile.schema==='lapsim.torque-profile.v2'?'composed policy':'equal split'}`:(r.campaign_profile?r.campaign_profile.replaceAll('_',' ')+' / ':'')+r.controller.philosophy.replaceAll('_',' '));
 const recordedReplay=window.LapSimReplayLoader.create(window,document);
 const configuredStudy=()=>['configured_diagnostic','configured_full_lap_acceptance'].includes(data?.status);
 const fullLapStudy=()=>data?.status==='configured_full_lap_acceptance';
 const tenLapStudy=()=>data?.status==='ten_lap_shakedown';
 const unrankedStudy=()=>configuredStudy()||tenLapStudy();
 const roundView=r=>window.LapSimRoundView?.describe(r);
 const resultLabel=r=>['full_lap_acceptance_v1','ten_lap_acceptance_v1'].includes(r.configuration?.mode)?(r.configuration.acceptance?.passed?(r.configuration.mode==='ten_lap_acceptance_v1'?'synthetic ten-lap round / audit pass':'synthetic lap / audit pass'):r.status+' / acceptance incomplete'):(r.configuration&&r.status==='time_limit'?'bounded diagnostic':r.status);
 function option(value,text){const o=document.createElement('option');o.value=value;o.textContent=text;return o;}
 function showRecordedCourse(course){if($('recorded-course'))$('recorded-course').textContent=course?'Recorded course: '+course.label+' Â· '+course.length_m.toFixed(1)+' m Â· '+(course.input_evidence?'recorded bundle / assumed corridor':'saved fixture'):'No recorded course';}
 function clearReplay(message){if($('recorded-course'))$('recorded-course').textContent='No recorded course';if($('lap-ledger')){$('lap-ledger').hidden=true;$('lap-rows').replaceChildren();}data=null;selected=[];rounds=[];playing=false;t=0;for(const id of ['results','history','telemetry','legend','round','condition'])$(id).replaceChildren();$('best').textContent='-';$('profile').textContent='No run loaded';$('status').textContent=message;$('identity').textContent='';$('run-count').textContent='No recorded ghosts';$('play').textContent='Play';draw();}
 async function loadDemo(){
  const request=++replayRequest;
  try{
   clearReplay('Loading selected recorded run...');
   const choice=$('recorded-demo').value;
   if(choice==='awd'){const recorded=await recordedReplay.loadDefault();if(recorded){if(request===replayRequest)load(recorded);return;}}
   const url=choice==='single_rwd'?'../work/tournament-accepted-single-rwd-4082025/replay.json':'../work/tournament-accepted-4082025/replay.json';
   const r=await fetch(url);
   if(!r.ok)throw Error('Selected saved run is unavailable. Use the local server or open its replay JSON.');
   const value=await r.json();
   if(request===replayRequest)load(value);
  }catch(e){if(request===replayRequest){$('status').textContent='No recorded run loaded';error(e);}}
 }
 function load(value){
  replayRequest++;
  try{
  if(value.schema!=='lapsim.controller-tournament.v1'||!value.runs||!value.generations)throw Error('Unsupported tournament record.');
  if(typeof window.LapSimFixtureComparison?.validateObjective!=='function')throw Error('Replay validator is unavailable. Reload the local app.');
  window.LapSimFixtureComparison.validateObjective(value.specification?.objective);
  for(const r of Object.values(value.runs)){
   if(r.round?.target_laps===10&&typeof window.LapSimRoundView?.describe!=='function')throw Error('Ten-lap replay validator is unavailable. Reload the local app.');
   roundView(r);
   if(!Array.isArray(r.telemetry)||r.telemetry.length>2000)throw Error('Invalid telemetry record.');
   let prior=-1;for(const s of r.telemetry){if(![s.t_s,s.x_m,s.y_m,s.heading_rad].every(Number.isFinite)||s.t_s<=prior)throw Error('Non-finite or unordered pose samples.');prior=s.t_s;}
  }
  data=value;playing=false;t=0;$('play').textContent='â–¶ Play';$('error').hidden=true;
  const recordedCourse=Object.values(data.runs)[0]?.course;
  showRecordedCourse(recordedCourse);
  rounds=[{name:configuredStudy()?'Configured profiles':tenLapStudy()?'Topology shakedowns Â· unranked':'Baseline tournament',ids:data.baselines}];
  for(const g of data.generations)rounds.push({name:`Generation ${g.generation}`,ids:g.candidate_ids,generation:g});
  if(Object.keys(data.holdout).length)rounds.push({name:'Held-out validation',holdout:true,ids:Object.keys(data.holdout)});
  if(data.diagnostic_ids?.length)rounds.push({name:'Failed brake-fallback diagnostic',diagnostic:true,ids:data.diagnostic_ids});
  $('round').replaceChildren(...rounds.map((r,i)=>option(i,r.name)));
  $('compare').replaceChildren(option('','None'),...data.generations.map((g,i)=>option(i,`Generation ${g.generation}`)));
  $('generation').max=rounds.length-1;$('generation').value=0;
  $('status').textContent=configuredStudy()?`${Object.keys(data.runs).length} configured ${fullLapStudy()?(data.specification.mode==='ten_lap_acceptance_v1'?'ten-lap acceptance runs':'full-lap acceptance runs'):'course diagnostics'} Â· no lap ranking Â· synthetic inputs`:`${Object.keys(data.runs).length} real simulation rollouts Â· ${data.status} Â· seed ${data.specification.seed}`;
  if(tenLapStudy())$('status').textContent=`${Object.keys(data.runs).length} recorded continuous ten-lap rounds Â· synthetic topology comparison Â· no controller ranking`;
  $('profile').textContent=data.specification.profile.replaceAll('_',' ').toUpperCase();
  $('best').textContent=unrankedStudy()?'Unranked':fmt(data.best_so_far?data.candidates[data.best_so_far].summary.fitness:null);
  $('metric-label').textContent=configuredStudy()?(fullLapStudy()?'Full-lap acceptance':'Configured diagnostic'):'Best training proxy';
  $('metric-expression').textContent=configuredStudy()?'Compare matched elapsed time, progress, energy and slip':'lap seconds + 120 s/kWh Ã— net energy';
  if(data.specification.competition?.laps===10)$('metric-expression').textContent='round seconds + 120 s/kWh Ã— round net energy';
  if(tenLapStudy()){$('metric-label').textContent='Topology comparison';$('metric-expression').textContent='Total ten-lap time and energy Â· synthetic hardware differs';}
  $('history').closest('section').hidden=unrankedStudy();
  $('configured-mode').hidden=!configuredStudy();
  $('setup-title').closest('section').hidden=unrankedStudy();
  $('sweep-form').closest('section').hidden=unrankedStudy();
  $('new-search').disabled=unrankedStudy();$('sweep-run').disabled=unrankedStudy();
  for(const id of ['compare','generation'])$(id).closest('label').hidden=unrankedStudy();
  $('fixture-comparison').hidden=tenLapStudy();
  $('identity').textContent=JSON.stringify({upstream:data.specification.upstream,vehicle_profile:data.specification.profile,configured_profiles:data.specification.profiles,configured_source:data.configured_source,presentation_scope:data.projection_scope??'Full saved record',scenario_inputs:data.specification.scenario_inputs??{status:'Not recorded; setup assumptions do not establish this replay configuration'},source_hashes:data.sources,objective:data.specification.objective,resources:data.specification.resources},null,2);
  chooseRound();history();
  }catch(e){clearReplay('No recorded run loaded');error(e);throw e;}
 }
 function idsFor(round){return round.diagnostic?round.ids:round.ids.flatMap(id=>round.holdout?data.holdout[id].run_ids:data.candidates[id].run_ids);}
 function chooseRound(){
  if(!data)return;const round=rounds[+$('round').value];const previous=$('condition').value;
  const names=[...new Set(idsFor(round).map(id=>data.runs[id].case.name))];
  $('condition').replaceChildren(...names.map(n=>option(n,n.replaceAll('_',' '))));
  if(names.includes(previous))$('condition').value=previous;
  $('generation').value=$('round').value;t=0;chooseRuns();
 }
 function chooseRuns(){
  if(!data)return;const round=rounds[+$('round').value],condition=$('condition').value;
  let ids=idsFor(round).filter(id=>data.runs[id].case.name===condition);
  if($('compare').value!==''&&!round.holdout&&!round.diagnostic){const g=data.generations[+$('compare').value];ids.push(...g.candidate_ids.flatMap(c=>data.candidates[c].run_ids).filter(id=>data.runs[id].case.name===condition));}
  ids=[...new Set(ids)];
  selected=ids.map(id=>({id,run:data.runs[id]}));if(!tenLapStudy())selected.sort((a,b)=>(a.run.metrics.fitness??1e9)-(b.run.metrics.fitness??1e9));selected=selected.slice(0,8);
  showRecordedCourse(selected[0]?.run.course);
  const priorTrajectory=$('configured-trajectory').value;
  $('configured-trajectory-control').hidden=!unrankedStudy();
  $('configured-trajectory').replaceChildren(...selected.map(s=>option(s.id,controllerLabel(s.run))));
  if(selected.some(s=>s.id===priorTrajectory))$('configured-trajectory').value=priorTrajectory;
  const max=Math.max(1,...selected.map(s=>s.run.telemetry.at(-1)?.t_s||0));$('time').max=max;t=Math.min(t,max);$('time').value=t;
  $('run-count').textContent=ids.length>8?`${selected.length} of ${ids.length} ghosts (display cap)`:`${selected.length} isolated ghosts`;
  $('legend').replaceChildren(...selected.map((s,i)=>{const row=document.createElement('div');row.className='legend-row';row.style.setProperty('--swatch',colors[i]);const dot=document.createElement('span');dot.className='swatch';const name=document.createElement('span');name.textContent=controllerLabel(s.run);const result=document.createElement('small');result.textContent=['full_lap_acceptance_v1','ten_lap_acceptance_v1'].includes(s.run.configuration?.mode)?`${resultLabel(s.run)}${s.run.metrics.lap_time_s==null?'':' / '+fmt(s.run.metrics.lap_time_s,2)+' s'}`:s.run.eligible?`${fmt(s.run.metrics.lap_time_s,2)} s`:s.run.configuration&&s.run.status==='time_limit'?`${fmt(s.run.metrics.elapsed_s,2)} s diagnostic`:'INVALID';row.append(dot,name,result);return row;}));
  $('results').replaceChildren(...selected.map((s,i)=>{const r=s.run,m=r.metrics,tr=document.createElement('tr');[controllerLabel(r),resultLabel(r),fmt(m.lap_time_s),fmt(m.elapsed_s),fmt(r.telemetry.at(-1)?.progress_m),fmt(m.net_energy_kwh*1000),fmt(m.max_slip),fmt(m.max_tire_utilization),r.violations.join(', ')||`${m.limited_ticks} limited ticks`].forEach((v,j)=>{const td=document.createElement('td');td.textContent=v;if(j===0)td.style.color=colors[i];tr.append(td);});const source=document.createElement('td');if(r.configuration?.mode==='ten_lap_acceptance_v1'){const a=document.createElement('a');a.href='review.html';a.textContent='Guarded source packages and evidence';source.append(a);}else if(r.configuration&&data.configured_study){const button=document.createElement('button');button.textContent='Export simulation source';button.setAttribute('aria-label','Export configured '+r.configuration.profile.profile_id);button.onclick=async()=>{button.disabled=true;try{const value=await post('/api/torque/export-result',{study:data.configured_study,run_id:s.id});const link=document.createElement('a');link.textContent='Source ZIP saved locally';link.href=value.package_url;link.title='SHA-256 '+value.zip_sha256+'; browser transfer unverified';source.replaceChildren(link);$('status').textContent='Selected configured result reproduced exactly; simulation source saved locally.';}catch(e){error(e);button.disabled=false;}};source.append(button);}else source.textContent='â€”';tr.append(source);return tr;}));
  const ledgers=selected.map(s=>({s,view:roundView(s.run)})).filter(r=>r.view);
  if($('lap-ledger')){$('lap-ledger').hidden=!ledgers.length;$('result-time-heading').textContent=ledgers.length?'Round total (s)':'Lap (s)';$('lap-rows').replaceChildren(...ledgers.flatMap(({s,view})=>view.laps.map(lap=>{const tr=document.createElement('tr');[controllerLabel(s.run),lap.lap,fmt(lap.lap_time_s),fmt(lap.net_energy_kwh*1000),fmt(lap.soc_after*100,3)+'%'].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});return tr;})));}
  if(ledgers.length){for(const [i,{run}] of selected.entries()){const view=roundView(run);if(view){$('results').children[i].children[1].textContent=view.label;$('legend').children[i].lastChild.textContent=view.label+' / '+fmt(view.timeS,2)+' s total';}}}
  draw();telemetryPlot();
 }
 function sample(run,time){
  const rows=run.telemetry;if(!rows.length)return null;let lo=0,hi=rows.length-1;
  while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(rows[mid].t_s<=time)lo=mid;else hi=mid-1;}
  const a=rows[lo],b=rows[Math.min(lo+1,rows.length-1)],alpha=b.t_s===a.t_s?0:Math.max(0,Math.min(1,(time-a.t_s)/(b.t_s-a.t_s)));
  const heading=a.heading_rad+Math.atan2(Math.sin(b.heading_rad-a.heading_rad),Math.cos(b.heading_rad-a.heading_rad))*alpha;
  return {...a,x_m:a.x_m+(b.x_m-a.x_m)*alpha,y_m:a.y_m+(b.y_m-a.y_m)*alpha,heading_rad:heading};
 }
 let webgl=null,webglFailure=null;
 function rendererStatus(message,kind='pending'){const status=$('renderer-status');if(status.textContent!==message)status.textContent=message;if(status.dataset.kind!==kind)status.dataset.kind=kind;}
 function view(){return {cameraMode:camera,azimuth:az,elevation:elev,zoom};}
 function sceneRuns(){return unrankedStudy()?selected.filter(s=>s.id===$('configured-trajectory').value):selected;}
 $('configured-trajectory').onchange=draw;
 function setCameraMode(mode){camera=mode;for(const key of ['top','orbit','follow'])$(key).setAttribute('aria-pressed',String(key===mode));}
 function draw(){
  const visible=sceneRuns();
  const legacy=$('renderer').value==='legacy';
  $('scene').hidden=legacy;canvas.hidden=!legacy;$('scene-hud').hidden=legacy;
  $('clock').textContent=t.toFixed(2)+' s';$('time').value=t;
  const round=rounds[+$('round').value];
  $('scene-hud').textContent=visible.length?`${configuredStudy()?controllerLabel(visible[0].run):round?.name||''} / ${$('condition').value} / ${t.toFixed(2)} s / SYNTHETIC LOGGED POSES`:'';
  if(legacy){$('scene-message').hidden=true;rendererStatus('Projected Canvas2D legacy view explicitly selected.','legacy');drawLegacy();return;}
  function message(text){$('scene-message').hidden=false;$('scene-message').textContent=text;}
  if(!visible.length){if(webgl)webgl.model.setRuns([]);message('Open a recorded tournament to inspect trajectories.');rendererStatus('WebGL 3D awaits a recorded selection.');return;}
  if(webglFailure){message(webglFailure+'\nSelect Projected Canvas2D (legacy) for the previous view.');return;}
  try{
   if(!window.LapSimWebGL)throw Error('The local Three.js scene module could not be loaded.');
   if(!webgl)webgl=new window.LapSimWebGL.WebGLReplay($('scene'),{onStatus:rendererStatus});
   const rect=$('replay-stage').getBoundingClientRect();
   const result=webgl.render(visible,t,view(),rect.width,rect.height,devicePixelRatio||1);
   if(result.rendered){$('scene-message').hidden=true;}else{message(result.reason);}
  }catch(e){webglFailure=e.message;playing=false;$('play').textContent='Play';rendererStatus(webglFailure,'error');message(webglFailure+'\nNo renderer fallback was selected. Use the Renderer control to choose the labeled legacy view.');}
 }
 $('renderer').onchange=()=>{
  if($('renderer').value==='webgl'&&webglFailure){if(webgl)webgl.dispose();webgl=null;webglFailure=null;}
  draw();
 };
 function dimensions(){const r=canvas.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);if(canvas.width!==Math.round(r.width*d)||canvas.height!==Math.round(r.height*d)){canvas.width=Math.round(r.width*d);canvas.height=Math.round(r.height*d);}ctx.setTransform(d,0,0,d,0,0);return [r.width,r.height];}
 function drawLegacy(){
  const items=sceneRuns();
  const [w,h]=dimensions();ctx.clearRect(0,0,w,h);ctx.fillStyle='#0c1420';ctx.fillRect(0,0,w,h);
  if(!items.length){ctx.fillStyle='#a4b3c8';ctx.font='14px system-ui';ctx.fillText('Open a recorded tournament to inspect trajectories.',20,45);return;}
  const course=items[0].run.course,xs=course.x_m,ys=course.y_m;
  let cx=(Math.max(...xs)+Math.min(...xs))/2,cy=(Math.max(...ys)+Math.min(...ys))/2;
  if(camera==='follow'){const p=sample(items[0].run,t);cx=p.x_m;cy=p.y_m;}
  const span=Math.max(Math.max(...xs)-Math.min(...xs)+12,Math.max(...ys)-Math.min(...ys)+12);
  const scale=Math.min(w,h)*.88/span*zoom*(camera==='follow'?2:1),el=camera==='top'?Math.PI/2:elev;
  function project(x,y,z=0){const dx=x-cx,dy=y-cy,rx=dx*Math.cos(az)-dy*Math.sin(az),ry=dx*Math.sin(az)+dy*Math.cos(az);const perspective=camera==='top'?1:100/(100+ry*Math.cos(el)-z*Math.sin(el));return [w/2+rx*scale*perspective,h*.53+(-ry*Math.sin(el)-z*Math.cos(el))*scale*perspective,ry];}
  function line(points,color,width=1,alpha=1){ctx.globalAlpha=alpha;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>{const q=project(...p);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});ctx.stroke();ctx.globalAlpha=1;}
  function polygon(points,color,alpha=1){ctx.globalAlpha=alpha;ctx.fillStyle=color;ctx.beginPath();points.forEach((p,i)=>{const q=project(...p);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});ctx.closePath();ctx.fill();ctx.globalAlpha=1;}
  for(let n=-60;n<=80;n+=10){line([[n,-60,0],[n,80,0]],'#192638');line([[-60,n,0],[80,n,0]],'#192638');}
  const edges=[[],[]];for(let i=0;i<xs.length;i++){const k=Math.min(xs.length-2,i),a=Math.atan2(ys[k+1]-ys[k],xs[k+1]-xs[k]);for(let s=0;s<2;s++){const side=s?1:-1;edges[s].push([xs[i]-side*3*Math.sin(a),ys[i]+side*3*Math.cos(a),.01]);}}
  polygon([...edges[0],...edges[1].toReversed()],'#202e40');line(edges[0],'#59697e',1);line(edges[1],'#59697e',1);
  line(xs.map((x,i)=>[x,ys[i],.025]),'#35465c',1);
  const start=project(xs[0],ys[0],.05);ctx.fillStyle='#c5d4e4';ctx.font='10px system-ui';ctx.fillText('START / FINISH',start[0]+7,start[1]-9);
  items.forEach((s,i)=>line(s.run.telemetry.map(p=>[p.x_m,p.y_m,.07]),colors[i],1.3,.55));
  const boxes=[];
  items.forEach((s,i)=>{const p=sample(s.run,t);if(!p)return;const alpha=i===0?.93:.34;
   function box(ox,oy,l,b,z,height,color){const local=[[-l/2,-b/2],[l/2,-b/2],[l/2,b/2],[-l/2,b/2]],pts=[];for(const zz of [z,z+height])for(const [xx,yy]of local){const x=xx+ox,y=yy+oy;pts.push([p.x_m+x*Math.cos(p.heading_rad)-y*Math.sin(p.heading_rad),p.y_m+x*Math.sin(p.heading_rad)+y*Math.cos(p.heading_rad),zz]);}for(const face of [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]){const q=face.map(k=>pts[k]);boxes.push({points:q,color,alpha,depth:q.reduce((sum,v)=>sum+project(...v)[2],0)/4});}}
   box(0,0,2.1,.85,.23,.35,colors[i]);box(.2,0,.7,.55,.58,.23,colors[i]);
   for(const x of [-.8,.8])for(const y of [-.61,.61])box(x,y,.43,.22,.08,.32,i===0?'#aebbc9':colors[i]);
   const q=project(p.x_m,p.y_m,1.3);ctx.fillStyle=colors[i];ctx.font='10px system-ui';ctx.fillText(`${i+1}${t>s.run.telemetry.at(-1).t_s?(s.run.eligible?' FIN':' FAILED'):''}`,q[0],q[1]);
  });boxes.sort((a,b)=>b.depth-a.depth).forEach(b=>polygon(b.points,b.color,b.alpha));
  ctx.fillStyle='#dce6f5';ctx.font='12px system-ui';ctx.fillText(`${rounds[+$('round').value]?.name||''} Â· ${$('condition').value} Â· ${t.toFixed(2)} s`,15,25);ctx.fillStyle='#8498b2';ctx.font='10px system-ui';ctx.fillText('SYNTHETIC Â· logged poses Â· no car-to-car interaction',15,h-14);
  $('clock').textContent=t.toFixed(2)+' s';$('time').value=t;
 }
 function node(tag,attributes,text){const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attributes))n.setAttribute(k,v);if(text!=null)n.textContent=text;return n;}
 function history(){const svg=$('history');svg.replaceChildren();if(!data?.generations?.length)return;const width=Math.max(280,svg.clientWidth),height=210;svg.setAttribute('viewBox',`0 0 ${width} ${height}`);const values=data.generations.flatMap(g=>[g.best,g.worst,g.median,g.best_so_far]).filter(Number.isFinite);if(!values.length)return;const low=Math.min(...values)-.01,high=Math.max(...values)+.01,X=i=>65+(width-95)*i/Math.max(1,data.generations.length-1),Y=v=>170-135*(v-low)/(high-low);
  for(let i=0;i<4;i++){const v=low+(high-low)*i/3;svg.append(node('line',{x1:60,x2:width-20,y1:Y(v),y2:Y(v),stroke:'#29374b'}),node('text',{x:54,y:Y(v)+3,'text-anchor':'end'},v.toFixed(3)));}
  for(const g of data.generations){svg.append(node('text',{x:X(g.generation),y:193,'text-anchor':'middle'},`Gen ${g.generation}`));if(g.best!=null)svg.append(node('line',{x1:X(g.generation),x2:X(g.generation),y1:Y(g.best),y2:Y(g.worst),stroke:'#69829f','stroke-width':4}));}
  for(const [key,color]of [['best_so_far','#5bdfd5'],['median','#ffbd66']]){const points=data.generations.filter(g=>g[key]!=null).map(g=>`${X(g.generation)},${Y(g[key])}`).join(' ');svg.append(node('polyline',{points,fill:'none',stroke:color,'stroke-width':2}));}
  $('invalid').textContent=`${data.generations.reduce((n,g)=>n+g.invalid_count,0)} invalid population entries`;
 }
 function download(text,name,type='text/plain'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
 $('export').onclick=()=>{try{if(selected.length)download(window.LapSimTelemetry.timeseriesCsv(selected[0].run),'lapsim-timeseries.csv','text/csv');}catch(e){error(e);}};
 $('file').onchange=async()=>{try{const f=$('file').files[0];if(f.size>120000000)throw Error('Replay exceeds 120 MB.');load(JSON.parse(await f.text()));}catch(e){error(e);}};
 $('demo').onclick=loadDemo;$('recorded-demo').onchange=loadDemo;$('round').onchange=chooseRound;$('condition').onchange=chooseRuns;$('compare').onchange=chooseRuns;
 $('generation').oninput=()=>{$('round').value=$('generation').value;chooseRound();};
 $('time').oninput=()=>{t=+$('time').value;playing=false;$('play').textContent='â–¶ Play';draw();};
 $('play').onclick=()=>{playing=!playing;if(t>=+$('time').max)t=0;$('play').textContent=playing?'â…¡ Pause':'â–¶ Play';};
 for(const mode of ['top','orbit','follow'])$(mode).onclick=()=>{setCameraMode(mode);draw();};
 function cameraAction(action){
  if(window.LapSimWebGL){const v=window.LapSimWebGL.cameraInput(view(),action);az=v.azimuth;elev=v.elevation;zoom=v.zoom;setCameraMode(v.cameraMode);}
  else if(action==='reset'){az=-.65;elev=.9;zoom=1;setCameraMode('orbit');}
  else if(action==='zoom-in'||action==='zoom-out'){zoom=Math.max(.4,Math.min(4,zoom*(action==='zoom-in'?1.2:1/1.2)));}
  draw();
 }
 $('zoom-in').onclick=()=>cameraAction('zoom-in');$('zoom-out').onclick=()=>cameraAction('zoom-out');$('camera-reset').onclick=()=>cameraAction('reset');
 let pointer=null;
 for(const element of [canvas,$('scene')]){
  element.onpointerdown=e=>{pointer=[e.clientX,e.clientY];element.setPointerCapture(e.pointerId);};
  element.onpointerup=()=>pointer=null;element.onpointercancel=()=>pointer=null;element.onlostpointercapture=()=>pointer=null;
  element.onpointermove=e=>{if(!pointer)return;az+=(e.clientX-pointer[0])*.008;elev=Math.max(.25,Math.min(1.5,elev+(e.clientY-pointer[1])*.006));pointer=[e.clientX,e.clientY];setCameraMode('orbit');draw();};
  element.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.4,Math.min(4,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
  element.onkeydown=e=>{const actions={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down','+':'zoom-in','=':'zoom-in','-':'zoom-out',Home:'reset'};if(actions[e.key]){e.preventDefault();cameraAction(actions[e.key]);}};
 }
 function frame(now){if(playing){t=Math.min(+$('time').max,t+Math.min(.1,(now-last)/1000)*+$('speed').value);if(t>=+$('time').max){playing=false;$('play').textContent='â–¶ Play';}draw();}last=now;requestAnimationFrame(frame);}requestAnimationFrame(frame);
 window.addEventListener('resize',()=>{draw();history();});
 if(window.ResizeObserver)new ResizeObserver(()=>{draw();history();telemetryPlot();}).observe($('replay-stage'));
 window.addEventListener('pagehide',()=>{if(webgl){webgl.dispose();webgl=null;webglFailure=null;}});
 window.addEventListener('pageshow',()=>draw());
 async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),value=await r.json();if(!r.ok)throw Error(value.error||r.statusText);return value;}
 async function start(body){try{if(configuredStudy())throw Error('Configured profiles use the bounded comparison workflow; legacy seeded search cannot substitute a fixture.');$('error').hidden=true;job=await post('/api/run',body);if(body.kind==='sweep'){$('sweep-plot').replaceChildren();$('sweep-csv').hidden=true;}else{data=null;selected=[];$('results').replaceChildren();$('history').replaceChildren();$('legend').replaceChildren();$('best').textContent='â€”';$('status').textContent='New tournament running; no new replay is available yet.';draw();}$('cancel').disabled=false;$('sweep-run').disabled=true;$('new-search').disabled=true;$('batch-status').textContent='Batch started; waiting for first completed rollout.';poll();}catch(e){error(e);}}
 function courseInputs(){const shipped=courseLibrary?.selection();return {course:shipped?'bundle':$('course').value,course_bundle:shipped?.bundle||($('course').value==='bundle'?importedCourse:null),reverse:$('reverse-course').checked,mirror:$('mirror-course').checked};}
 $('new-search').onclick=()=>start({kind:'search',laps:+$('round-laps').value,profile:$('search-profile').value,seed:+$('search-seed').value,population:+$('population').value,generations:+$('generations').value,...courseInputs()});
 $('course-file').onchange=async()=>{try{const file=$('course-file').files[0];if(!file)return;if(file.size>4194304)throw Error('Course bundle exceeds 4 MiB.');const value=JSON.parse(await file.text());const checked=await post('/api/course/validate',value);importedCourse=value;const item=$('course').querySelector('option[value="bundle"]');item.disabled=false;item.textContent=checked.label;$('course').value='bundle';courseLibrary?.render();$('course-status').textContent=checked.label+' Â· '+checked.length_m.toFixed(1)+' m Â· assumed corridor Â· geometry '+checked.geometry_sha256.slice(0,12);$('error').hidden=true;}catch(e){error(e);}};
 $('cancel').onclick=async()=>{try{await post('/api/cancel',{});$('batch-status').textContent='Cancelled. Completed checkpoints and cached points retained.';poll();}catch(e){error(e);}};
 $('sweep-form').onsubmit=e=>{e.preventDefault();const axes=[{parameter:$('axis1').value,minimum:+$('min1').value,maximum:+$('max1').value,count:+$('count1').value}];if($('axis2').value)axes.push({parameter:$('axis2').value,minimum:+$('min2').value,maximum:+$('max2').value,count:+$('count2').value});start({kind:'sweep',axes,profile:$('sweep-profile').value,philosophy:$('philosophy').value,...courseInputs()});};
 async function poll(){try{const r=await fetch('/api/status'),s=await r.json();if(s.total){$('progress').max=s.total;$('progress').value=s.completed||0;}else if(s.active){$('progress').removeAttribute('value');}else{$('progress').max=1;$('progress').value=1;}if(s.active){$('batch-status').textContent=`Running ${s.kind} Â· ${s.completed||0}${s.total?'/'+s.total:''} completed`;setTimeout(poll,1000);return;}$('cancel').disabled=true;$('sweep-run').disabled=configuredStudy();$('new-search').disabled=configuredStudy();if(!s.output)return;if(s.exit_code!==null&&s.exit_code!==0&&!s.cancelled){$('batch-status').textContent='Batch failed; completed evidence retained.';error(Error('Batch exited with code '+s.exit_code+'. Inspect '+s.output+'/batch.log'));return;}if(s.cancelled){$('batch-status').textContent='Cancelled Â· completed results retained';}else{$('batch-status').textContent=`${s.saved_status||'finished'} Â· ${s.completed||0} completed`;}if(s.kind==='sweep'){const r=await fetch('../'+s.output+'/sweep.json');if(r.ok)sweepPlot(await r.json());$('sweep-csv').hidden=false;$('sweep-csv').href='../'+s.output+'/sweep.csv';}else if(!s.cancelled){const r=await fetch('../'+s.output+'/replay.json');if(r.ok)load(await r.json());}}catch(e){$('batch-status').textContent='Batch controls require the local launch_tournament server.';}}
 function sweepPlot(result){if(result.configuration.axes.length===2)return heatmap(result);const svg=$('sweep-plot');svg.style.height='220px';svg.replaceChildren();const width=Math.max(280,svg.clientWidth);svg.setAttribute('viewBox',`0 0 ${width} 220`);const rows=result.rows,axis=result.configuration.axes[0].parameter;const valid=rows.filter(r=>r.eligible);if(!rows.length)return;const xs=rows.map(r=>r[axis]),xmin=Math.min(...xs),xmax=Math.max(...xs),X=v=>60+(width-100)*(v-xmin)/(xmax-xmin||1);const times=valid.map(r=>r.lap_time_s),energies=valid.map(r=>r.net_energy_kwh*1000),tmin=Math.min(...times),tmax=Math.max(...times),emin=Math.min(...energies),emax=Math.max(...energies);svg.append(node('text',{x:60,y:16},'Lap seconds (cyan) / net Wh (amber), each axis independently scaled'));for(const row of rows){const x=X(row[axis]);svg.append(node('text',{x,y:207,'text-anchor':'middle'},fmt(row[axis],2)));if(!row.eligible){svg.append(node('text',{x,y:100,fill:'#ff7d9f'},'Ã— INVALID'));continue;}for(const [value,lo,hi,color]of [[row.lap_time_s,tmin,tmax,'#5bdfd5'],[row.net_energy_kwh*1000,emin,emax,'#ffbd66']]){const y=160-110*(value-lo)/(hi-lo||1);const dot=node('circle',{cx:x,cy:y,r:4,fill:color});dot.append(node('title',{},JSON.stringify(row)));svg.append(dot,node('text',{x:x+5,y:y-7},fmt(value,3)));}}svg.append(node('text',{x:width/2,y:220,'text-anchor':'middle'},`${axis} (${result.parameters[axis].unit}) Â· second-axis values in CSV / point tooltip`));}
 fetch('/api/status').then(r=>r.json()).then(s=>{for(const[key,p]of Object.entries(s.parameters)){const label=`${key} (${p.unit})`;$('axis1').append(option(key,label));$('axis2').append(option(key,label));}$('axis1').value='drive_scale';for(const i of [1,2])$('axis'+i).onchange=()=>{const p=s.parameters[$('axis'+i).value];if(!p)return;$('min'+i).value=p.low;$('max'+i).value=p.high;for(const bound of ['min','max']){$(bound+i).min=p.low;$(bound+i).max=p.high;}};}).catch(()=>{$('batch-status').textContent='Use launch_tournament.cmd for local batch controls.';});
 let fixtureComparisonRecords=null,fixtureComparisonPending=false;
 async function loadFixtureComparison(){
  if(!$('fixture-comparison').open||fixtureComparisonRecords||fixtureComparisonPending)return;
  fixtureComparisonPending=true;
  $('fixture-compare-results').replaceChildren();
  $('fixture-compare-status').textContent='Loading accepted fixture records...';
  try{
   async function read(url){const r=await fetch(url);if(!r.ok)throw Error('Accepted fixture record is unavailable.');if(Number(r.headers.get('Content-Length'))>120000000)throw Error('Fixture record exceeds 120 MB.');return r.json();}
   const awd=window.LAPSIM_TOURNAMENT||await read('../work/tournament-accepted-4082025/replay.json');
   const rwd=await read('../work/tournament-accepted-single-rwd-4082025/replay.json');
   const records=[awd,rwd],result=window.LapSimFixtureComparison.compare(records);
   $('fixture-compare-results').replaceChildren(...result.rows.map((row,index)=>{
    const tr=document.createElement('tr');tr.setAttribute('role','row');
    const labels=['Fixture','Controller','Mean lap (s)','Net energy (Wh)','Proxy (s)'];
    [row.label,row.controller.replaceAll('_',' '),fmt(row.lapTimeS),fmt(row.netEnergyWh),fmt(row.proxy)].forEach((value,i)=>{const td=document.createElement('td');td.setAttribute('role','cell');td.dataset.label=labels[i];td.textContent=value;tr.append(td);});
    const td=document.createElement('td'),button=document.createElement('button');
    button.textContent='Replay';button.id='fixture-replay-'+row.profile;button.setAttribute('aria-label','Replay '+row.label);
    button.onclick=()=>{$('recorded-demo').value=row.profile==='synthetic_single_motor_rwd'?'single_rwd':'awd';load(records[index]);$('replay-stage').scrollIntoView({block:'start'});};
    td.setAttribute('role','cell');td.append(button);tr.append(td);return tr;
   }));
   fixtureComparisonRecords=records;
   $('fixture-compare-status').textContent=`Matched recorded course: ${result.courseLabel} Â· ${fmt(result.courseLengthM)} m Â· ${result.trainingConditions} training conditions Â· seed ${result.seed}`;
  }catch(e){$('fixture-compare-status').textContent='Comparison unavailable: '+e.message;}
  finally{fixtureComparisonPending=false;}
 }
 $('fixture-comparison').ontoggle=loadFixtureComparison;
 function heatmap(result){
  const svg=$('sweep-plot');svg.replaceChildren();const width=Math.max(280,svg.clientWidth),stacked=width<680,height=stacked?460:255;svg.style.height=height+'px';svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  const [ax,ay]=result.configuration.axes.map(a=>a.parameter),xs=[...new Set(result.rows.map(r=>r[ax]))].sort((a,b)=>a-b),ys=[...new Set(result.rows.map(r=>r[ay]))].sort((a,b)=>a-b);
  for(const [panel,key,label,multiplier]of [[0,'lap_time_s','Lap time (s)',1],[1,'net_energy_kwh','Net energy (Wh)',1000]]){
   const left=stacked?0:panel*width/2,top=stacked?panel*230:0,panelWidth=stacked?width:width/2,plotWidth=panelWidth-85,cellWidth=plotWidth/Math.max(1,xs.length),cellHeight=120/Math.max(1,ys.length),valid=result.rows.filter(r=>r.eligible).map(r=>r[key]*multiplier),lo=Math.min(...valid),hi=Math.max(...valid);
   svg.append(node('text',{x:left+55,y:top+18},`${label} Â· ${ay} (${result.parameters[ay].unit})`));
   for(const row of result.rows){const x=left+55+xs.indexOf(row[ax])*cellWidth,y=top+35+ys.indexOf(row[ay])*cellHeight,value=row[key]*multiplier,fraction=(value-lo)/(hi-lo||1),color=row.eligible?`hsl(${panel?35:175} 45% ${25+fraction*22}%)`:'#61313e',rect=node('rect',{x,y,width:cellWidth-2,height:cellHeight-2,fill:color});rect.append(node('title',{},JSON.stringify(row)));svg.append(rect,node('text',{x:x+cellWidth/2,y:y+cellHeight/2+3,'text-anchor':'middle',style:'fill:#eef4fc'},row.eligible?fmt(value,3):'INVALID'));}
   ys.forEach((v,i)=>svg.append(node('text',{x:left+48,y:top+35+(i+.5)*cellHeight+3,'text-anchor':'end'},fmt(v,2))));xs.forEach((v,i)=>svg.append(node('text',{x:left+55+(i+.5)*cellWidth,y:top+174,'text-anchor':'middle'},fmt(v,2))));svg.append(node('text',{x:left+panelWidth/2,y:top+199,'text-anchor':'middle'},`${ax} (${result.parameters[ax].unit})`));
  }
 }
 function telemetryPlot(){
  const svg=$('telemetry');svg.replaceChildren();const width=Math.max(280,svg.clientWidth),height=240;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  if(!selected.length){svg.append(node('text',{x:12,y:30},'Select recorded runs to compare telemetry.'));return;}
  const key=$('signal').value,distance=$('plot-axis').value==='distance';
  const signal={speed:s=>s.u_mps,power:s=>s.pack_power_w/1000,energy:s=>s.pack_energy_j/3600,regen:s=>s.achieved_nm.reduce((a,v)=>a+Math.max(0,-v),0),friction:s=>s.friction_nm.reduce((a,v)=>a+v,0),slip:s=>Math.max(...s.slip.map(Math.abs)),yaw:s=>s.yaw_rad_s}[key];
  const series=selected.map(({run})=>run.telemetry.map(s=>[distance?s.progress_m:s.t_s,signal(s)]));
  const points=series.flat().filter(p=>p.every(Number.isFinite));if(!points.length)return;
  const xmax=Math.max(...points.map(p=>p[0]),1),values=points.map(p=>p[1]),low=Math.min(...values),high=Math.max(...values),pad=Math.max((high-low)*.08,Math.abs(high)*.01,.001),ymin=low-pad,ymax=high+pad;
  const X=x=>55+(width-75)*x/xmax,Y=y=>200-165*(y-ymin)/(ymax-ymin);
  for(let i=0;i<=4;i++){const y=ymin+(ymax-ymin)*i/4,x=xmax*i/4;svg.append(node('line',{x1:55,x2:width-20,y1:Y(y),y2:Y(y),stroke:'#29374b'}),node('text',{x:49,y:Y(y)+4,'text-anchor':'end'},fmt(y,2)),node('text',{x:X(x),y:219,'text-anchor':'middle'},fmt(x,1)));}
  series.forEach((points,i)=>{const path=node('path',{d:points.map((p,j)=>`${j?'L':'M'}${X(p[0])},${Y(p[1])}`).join(' '),fill:'none',stroke:colors[i],'stroke-width':1.7});path.append(node('title',{},selected[i].run.controller.philosophy));svg.append(path);});
  svg.append(node('text',{x:55,y:18},$('signal').selectedOptions[0].textContent),node('text',{x:width-20,y:239,'text-anchor':'end'},distance?'Progress (m)':'Time (s)'));
 }
 $('signal').onchange=telemetryPlot;$('plot-axis').onchange=telemetryPlot;
 // Stable, explicit inspection hooks for local browser QA / screenshots.
 window.lapsimReplay={load,select:(round,time=0)=>{$('round').value=round;chooseRound();t=time;draw();},state:()=>({loaded:!!data,selected:selected.length,time:t,round:$('round').value,renderer:$('renderer').value,rendererError:webglFailure,sceneObjects:webgl?.model.root.children.length||0}),draw};
 const query=new URLSearchParams(location.search);if(query.get('renderer')==='legacy')$('renderer').value='legacy';
 async function loadCampaign(code){try{if(!['open','awd'].includes(code))throw Error('Choose the recorded open or AWD campaign.');clearReplay('Loading source-bound controller campaign...');const response=await fetch('../work/ten-lap-r10/campaign-'+code+'-viewer.json');if(!response.ok)throw Error('Recorded controller campaign is unavailable.');if(Number(response.headers.get('Content-Length'))>16000000)throw Error('Campaign viewer exceeds its byte bound.');load(await response.json());}catch(e){clearReplay('No controller campaign loaded');error(e);}}
 async function initialReplay(){if(query.has('review')){try{const id=query.get('review');if(!/^[a-z0-9-]{1,64}$/.test(id))throw Error('Invalid saved review case');clearReplay('Loading saved controller experiment...');const response=await fetch('../work/review-r11/'+id+'.viewer.json');if(!response.ok)throw Error('Saved review case unavailable');if(Number(response.headers.get('Content-Length'))>8000000)throw Error('Review viewer exceeds its byte bound');load(await response.json());}catch(e){clearReplay('No saved review case loaded');error(e);}return;}if(query.has('campaign'))return loadCampaign(query.get('campaign'));if(query.has('tenlap')){try{clearReplay('Loading recorded ten-lap topology comparison...');const response=await fetch('../work/ten-lap-r10/shakedown-viewer.json');if(!response.ok)throw Error('Ten-lap shakedown evidence is unavailable.');if(Number(response.headers.get('Content-Length'))>8000000)throw Error('Ten-lap viewer exceeds its byte bound.');load(await response.json());}catch(e){clearReplay('No ten-lap evidence loaded');error(e);}return;}if(!query.has('configured'))return loadDemo();try{const id=query.get('configured');if(!/^[a-f0-9]{12}$/.test(id))throw Error('Invalid configured study identity.');clearReplay('Loading configured course comparison...');let limit=8000000,response=await fetch('../work/torque-comparison-'+id+'/viewer.json');if(response.status===404){limit=64000000;response=await fetch('../work/torque-comparison-'+id+'/replay.json');}if(!response.ok)throw Error('Configured study is unavailable.');if(Number(response.headers.get('Content-Length'))>limit)throw Error('Configured viewer record exceeds its byte bound.');load(await response.json());}catch(e){clearReplay('No configured comparison loaded');error(e);}}
 initialReplay().then(()=>{if(data){if(query.has('round'))$('round').value=query.get('round');chooseRound();t=+(query.get('time')||0);if(query.get('camera')==='top')setCameraMode('top');draw();}});
})();
