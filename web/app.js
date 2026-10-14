/* Browser presentation only. Vehicle physics runs in the Python worker. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const STARTUP_LIMIT_MS = 180000;
  const RUN_LIMIT_MS = 120000;
  const definitions = {
    'vehicle.speed_mps': {label:'Speed',unit:'m/s',factor:1},
    'battery.power_w': {label:'Battery power',unit:'kW',factor:0.001},
    'vehicle.longitudinal_acceleration_mps2': {label:'Longitudinal acceleration',unit:'m/s²',factor:1},
    'battery.state_of_charge': {label:'State of charge',unit:'%',factor:100}
  };
  const fallbackProfiles = [
    {id:'prius_2026_le',label:'Prius LE benchmark',description:'Simplified power-equivalent benchmark; the hybrid transaxle is not modeled. Tire and chassis estimates remain assumptions.'},
    {id:'repository_baseline',label:'Repository car baseline',description:'Repository component defaults. This is an engineering baseline, not an as-built team car.'}
  ];
  const fallbackCourses = [
    {id:'synthetic_rounded_rectangle_v1',label:'Synthetic loop · demo',description:'A coherent analytic loop. Geometry and grip are scenario assumptions.',synthetic:true,lengthM:120+24*Math.PI},
    {id:'synthetic_fsae_endurance_style_v1',label:'Synthetic FSAE-style · practice',description:'A coherent analytic endurance-style loop. It is a synthetic scenario, not an official event course.',synthetic:true,lengthM:660+50*Math.PI}
  ];
  let catalog = {profiles:fallbackProfiles,courses:fallbackCourses};
  let worker = null, generation = 0, boot = null, ready = false;
  let active = null, sequence = 0, clockTimer = null, latest = null, reference = null;
  let geometry = null, chartTransform = null, tableCells = [], sampleIndex = 0;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const number = (value, decimals=1) => finite(value) ? value.toLocaleString(undefined,{minimumFractionDigits:decimals,maximumFractionDigits:decimals}) : '—';
  const series = (result,key) => result?.telemetry?.channels?.[key]?.values ?? [];
  const stations = result => result?.telemetry?.sampleDistanceM ?? [];
  const times = result => result?.telemetry?.sampleTimeS ?? [];
  const selectedProfile = id => catalog.profiles.find(entry => entry.id === (id ?? $('vehicle-profile').value));
  const selectedCourse = id => catalog.courses.find(entry => entry.id === (id ?? $('course').value));

  function runtimeStatus(message, state='') {
    $('runtime-label').textContent = message;
    $('runtime-dot').className = `status-dot ${state}`;
  }
  function resultStatus(message, state='') {
    $('result-state').textContent = message;
    $('result-state').className = `quiet-badge ${state}`;
  }
  function progress(title, message, completed, total) {
    $('progress-title').textContent = title;
    $('progress-description').textContent = message;
    if (finite(completed) && finite(total) && total > 0) {
      $('run-progress').max = total;
      $('run-progress').value = Math.max(0,Math.min(total,completed));
    } else $('run-progress').removeAttribute('value');
  }
  function stopWorker(reason) {
    ++generation;
    worker?.terminate();
    worker = null;
    ready = false;
    if (boot) {
      clearTimeout(boot.timer);
      boot.reject(new Error(reason ?? 'Engine stopped.'));
      boot = null;
    }
  }
  function finishActive() {
    if (active) clearTimeout(active.timer);
    active = null;
    clearInterval(clockTimer);
    clockTimer = null;
    $('run-settings').disabled = false;
    $('run-button').disabled = false;
    $('run-button').querySelector('span').textContent = 'Run simulation';
    $('cancel-button').hidden = true;
    $('progress-panel').hidden = true;
  }
  function showError(message, title='The run could not finish') {
    finishActive();
    $('run-error').hidden = false;
    $('error-title').textContent = title;
    const raw=String(message ?? 'The simulator encountered an unexpected error.');
    let summary=raw;
    if (/Traceback|PythonError|at https?:|ModuleNotFoundError|ImportError/.test(raw)) {
      summary=/ModuleNotFoundError|ImportError/.test(raw)
        ? 'A required simulator component could not load. Reload this page and try again.'
        : 'The physics engine could not complete this calculation. Try a coarser grid or another setup; the technical details are available below.';
    } else if (raw.length>260 || raw.includes('\n')) {
      const lines=raw.split('\n').map(line=>line.trim()).filter(Boolean);
      summary=lines.at(-1)?.slice(0,260) ?? 'The simulation could not finish. Try again.';
    }
    $('error-description').textContent=summary;
    $('error-details').hidden=summary===raw;
    $('error-details').open=false;
    $('error-technical').textContent=raw;
    resultStatus(latest ? 'Previous result retained' : 'Needs attention','warning');
    runtimeStatus(ready ? 'Engine ready' : 'Engine stopped · retry to reload',ready ? 'ready' : 'error');
  }
  function populateSelect(id, entries) {
    if (!Array.isArray(entries) || !entries.length) return;
    const select = $(id), previous = select.value;
    select.replaceChildren(...entries.map(entry => {
      const option = document.createElement('option');
      option.value = entry.id;
      option.textContent = entry.label ?? entry.id;
      return option;
    }));
    if (entries.some(entry => entry.id === previous)) select.value = previous;
  }
  function acceptCapabilities(capabilities) {
    if (capabilities?.protocolVersion !== 1) throw new Error('The browser engine protocol has changed. Reload this page to get matching files.');
    catalog = {...catalog,...capabilities};
    populateSelect('vehicle-profile',catalog.profiles);
    populateSelect('course',catalog.courses);
    updateSetupNotes();
  }
  function ensureWorker() {
    if (ready && worker) return Promise.resolve();
    if (boot) return boot.promise;
    const token = ++generation;
    let resolve, reject;
    const promise = new Promise((yes,no) => {resolve=yes;reject=no;});
    const timer = setTimeout(() => {
      if (token !== generation) return;
      stopWorker('The engine download took too long. Check the connection and try again.');
    },STARTUP_LIMIT_MS);
    boot = {promise,resolve,reject,timer};
    try {
      worker = new Worker('./worker.js',{type:'module'});
      worker.onmessage = event => {
        if (token !== generation) return;
        const message = event.data;
        if (!message || typeof message !== 'object') return;
        if (message.type === 'status') {
          runtimeStatus(message.message ?? 'Loading the engine…','busy');
          if (active) progress('Preparing the engine',message.message ?? 'Loading Python physics…');
        } else if (message.type === 'ready') {
          try {
            acceptCapabilities(message.capabilities);
            ready = true;
            runtimeStatus('Python physics ready','ready');
            const pending = boot;
            boot = null;
            if (pending) {clearTimeout(pending.timer);pending.resolve();}
          } catch (error) {stopWorker(error.message);}
        } else if (message.type === 'progress' && active?.id === message.requestId) {
          const phase = String(message.phase).startsWith('constraints') ? 'Finding feasible speeds' : 'Solving the lap';
          const pass = finite(message.passNumber) ? ` · pass ${message.passNumber}${finite(message.maximumPasses) ? ` of ${message.maximumPasses}` : ''}` : '';
          const cellText = finite(message.completedCells) && finite(message.totalCells) ? `${message.completedCells} / ${message.totalCells} cells` : 'Calculating path and component limits';
          const distance = finite(message.distanceM) ? ` · ${number(message.distanceM)} m` : '';
          progress(phase,`${cellText}${pass}${distance}`,message.completedCells,message.totalCells);
        } else if (message.type === 'result' && active?.id === message.requestId) {
          const settings = active.settings;
          finishActive();
          renderResult(message.result,settings);
          runtimeStatus('Python physics ready','ready');
        } else if (message.type === 'error') {
          const error = message.error?.message ?? 'The physics engine returned an error.';
          if (boot && message.requestId == null) stopWorker(error);
          else if (active?.id === message.requestId) showError(error);
        }
      };
      worker.onerror = event => {
        if (token !== generation) return;
        event.preventDefault();
        const loading = !!boot;
        stopWorker(event.message || 'The browser physics engine could not load. Check your connection and reload the page.');
        if (!loading && active) showError(event.message || 'The browser engine stopped unexpectedly.');
      };
      worker.onmessageerror = () => {
        if (token !== generation) return;
        const loading = !!boot;
        stopWorker('The browser could not read an engine response. Please retry.');
        if (!loading && active) showError('The browser could not read the engine response. Please retry.');
      };
      worker.postMessage({type:'init'});
    } catch (error) {stopWorker(error.message);}
    return promise;
  }

  function settingsFromForm() {
    const settings = {
      vehicleProfile:$('vehicle-profile').value,courseId:$('course').value,
      gripMultiplier:Number($('grip').value),torqueFraction:Number($('torque').value),
      brakePressurePsi:Number($('brake-pressure').value),regenEnabled:$('regen').checked,
      maxCellLengthM:Number($('cell-size').value),
      initialSpeedMps:$('start-mode').value === 'custom' ? Number($('start-speed').value) : null
    };
    const ranges = {gripMultiplier:[0.2,1.5],torqueFraction:[0,1],brakePressurePsi:[10,500],maxCellLengthM:[0.5,10],initialSpeedMps:[0,40]};
    for (const [key,[min,max]] of Object.entries(ranges)) {
      if (settings[key] === null && key === 'initialSpeedMps') continue;
      if (!finite(settings[key]) || settings[key] < min || settings[key] > max) throw new Error(`${key} must be between ${min} and ${max}.`);
    }
    const length = selectedCourse(settings.courseId)?.lengthM;
    if (finite(length) && Math.ceil(length/settings.maxCellLengthM) > 1200) throw new Error('This grid exceeds the browser limit of 1,200 cells. Choose a larger maximum cell length.');
    return settings;
  }
  async function run(event) {
    event?.preventDefault();
    if (active) return;
    $('input-error').hidden = true;
    if (!$('run-form').reportValidity()) return;
    let settings;
    try {settings=settingsFromForm();}
    catch (error) {$('input-error').textContent=error.message;$('input-error').hidden=false;return;}
    const id = `web-${++sequence}`;
    active = {id,settings,started:performance.now(),timer:null};
    $('run-error').hidden = true;
    $('run-settings').disabled = true;
    $('run-button').disabled = true;
    $('run-button').querySelector('span').textContent = 'Running…';
    $('cancel-button').hidden = false;
    $('progress-panel').hidden = false;
    resultStatus(latest ? 'Running · previous result' : 'Running');
    progress(ready ? 'Preparing the lap' : 'Preparing the engine',ready ? 'Checking the selected vehicle and course…' : 'First launch downloads Python, NumPy, SciPy, and the simulator.');
    $('progress-elapsed').textContent = '0 s';
    clockTimer = setInterval(() => {if (active) $('progress-elapsed').textContent=`${Math.floor((performance.now()-active.started)/1000)} s`;},500);
    try {
      await ensureWorker();
      if (active?.id !== id) return;
      active.timer = setTimeout(() => {
        if (active?.id !== id) return;
        stopWorker('Calculation stopped at the browser time limit.');
        showError('This calculation exceeded the two-minute browser limit. Choose the 5 m preview grid and try again.','Calculation time limit reached');
      },RUN_LIMIT_MS);
      progress('Solving the lap','Calculating feasible path speeds and component limits…');
      worker.postMessage({type:'run',requestId:id,settings});
    } catch (error) {if (active?.id === id) showError(error.message,'The engine could not start');}
  }
  function cancel() {
    if (!active) return;
    stopWorker('Calculation cancelled.');
    finishActive();
    runtimeStatus('Engine stopped · starts again on next run');
    resultStatus(latest ? 'Cancelled · previous result' : 'Cancelled','warning');
  }

  function updateSetupNotes() {
    $('profile-note').textContent = selectedProfile()?.description ?? 'Select a vehicle profile.';
    const course=selectedCourse();
    const courseHints={
      synthetic_rounded_rectangle_v1:`Coherent synthetic loop · ${number(course?.lengthM)} m. Geometry and grip are scenario assumptions.`,
      synthetic_fsae_endurance_style_v1:`Coherent synthetic practice loop · ${number(course?.lengthM)} m. This is an assumed course, not an official event layout.`,
      team_endurance_fused_gnss_imu:`Fused course reference · ${number(course?.lengthM,0)} m. Its x/y coordinates and prescribed curvature disagree; racing-line feasibility is unverified.`
    };
    $('course-note').textContent=courseHints[course?.id] ?? (course?'Source course geometry. Inspect its assumptions in the research documentation.':'Select a course.');
    $('start-speed-field').hidden = $('start-mode').value !== 'custom';
    $('start-speed').required = $('start-mode').value === 'custom';
    $('start-speed').disabled = $('start-mode').value !== 'custom';
    $('torque-value').textContent = `${Math.round(Number($('torque').value)*100)}%`;
    if (!latest) drawPreview();
  }
  function changed() {
    updateSetupNotes();
    if (latest && !active) resultStatus('Inputs changed · run again','warning');
  }
  function svg(tag,attributes={},text) {
    const element = document.createElementNS(NS,tag);
    for (const [key,value] of Object.entries(attributes)) element.setAttribute(key,value);
    if (text != null) element.textContent = text;
    return element;
  }
  // Only the analytic preview geometry is drawn here. Every performance value
  // and final course boundary is supplied by the Python simulation.
  function previewGeometry(courseId) {
    const motif = courseId === 'synthetic_fsae_endurance_style_v1'
      ? [[60,0],[15*Math.PI/6,1/15],[45,0],[15*Math.PI/6,-1/15],[60,0],[15*Math.PI/2,1/15]]
      : [[40,0],[6*Math.PI,1/12],[20,0],[6*Math.PI,1/12],[40,0],[6*Math.PI,1/12],[20,0],[6*Math.PI,1/12]];
    const segments = courseId === 'synthetic_fsae_endurance_style_v1' ? Array(4).fill(motif).flat() : motif;
    let x=0,y=0,heading=0,distance=0;
    const result = {xM:[x],yM:[y],distanceM:[distance]};
    for (const [length,curvature] of segments) {
      const count = Math.ceil(length/2), step=length/count;
      for (let index=0;index<count;index++) {
        if (curvature === 0) {x+=step*Math.cos(heading);y+=step*Math.sin(heading);}
        else {
          const next=heading+step*curvature;
          x+=(Math.sin(next)-Math.sin(heading))/curvature;
          y+=(Math.cos(heading)-Math.cos(next))/curvature;
          heading=next;
        }
        distance+=step;result.xM.push(x);result.yM.push(y);result.distanceM.push(distance);
      }
    }
    return result;
  }
  function drawPreview() {
    const course = selectedCourse();
    if (!course || !course.synthetic) {
      $('course-path').setAttribute('d','');document.querySelector('.course-shadow').setAttribute('d','');
      $('course-start').toggleAttribute('hidden',true);$('course-start-label').toggleAttribute('hidden',true);$('course-cursor').toggleAttribute('hidden',true);
      $('course-caption').textContent='Reference map appears after a run';
      $('course-kind').textContent='Measured reference';
      $('course-length').textContent=`${number(course?.lengthM)} m`;
      return;
    }
    drawGeometry(previewGeometry(course.id),course,true);
  }
  function drawGeometry(data,course,preview=false) {
    if (!Array.isArray(data?.xM) || !Array.isArray(data?.yM) || !data.xM.length) return;
    const points = data.xM.map((x,index) => [x,data.yM[index]]).filter(([x,y]) => finite(x)&&finite(y));
    if (!points.length) return;
    const xs=points.map(point=>point[0]),ys=points.map(point=>point[1]);
    const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
    const scale=Math.min(290/Math.max(1,xmax-xmin),175/Math.max(1,ymax-ymin));
    const project=(x,y)=>[180+(x-(xmin+xmax)/2)*scale,130-(y-(ymin+ymax)/2)*scale];
    const path=points.map(([x,y],index)=>`${index?'L':'M'}${project(x,y).map(value=>value.toFixed(2)).join(',')}`).join(' ');
    $('course-path').setAttribute('d',path);document.querySelector('.course-shadow').setAttribute('d',path);
    const start=project(...points[0]);
    $('course-start').toggleAttribute('hidden',false);$('course-start').setAttribute('cx',start[0]);$('course-start').setAttribute('cy',start[1]);
    $('course-start-label').toggleAttribute('hidden',false);$('course-start-label').setAttribute('x',start[0]);$('course-start-label').setAttribute('y',Math.max(13,start[1]-14));
    $('course-start-label').textContent=course?.synthetic ? 'LAP START' : 'REFERENCE START';
    $('course-cursor').toggleAttribute('hidden',true);
    $('course-length').textContent=`${number(data.distanceM?.at(-1) ?? course?.lengthM)} m`;
    $('course-kind').textContent=course?.synthetic ? 'Synthetic' : 'Measured reference';
    $('course-caption').textContent=preview ? 'Analytic centerline · preview' : course?.synthetic ? 'Prescribed centerline · from source' : 'Reference x/y · curvature differs';
    $('course-svg-title').textContent=`${course?.label ?? 'Course'}: ${preview?'analytic preview':course?.synthetic?'source centerline':'reference coordinates, not an integrated vehicle pose'}`;
    geometry={data,project,synthetic:course?.synthetic};
  }

  function context(result) {
    const settings=result.settings ?? {};
    return `${selectedProfile(settings.vehicleProfile)?.label ?? settings.vehicleProfile ?? 'Vehicle'} · ${selectedCourse(settings.courseId)?.label ?? settings.courseId ?? 'Course'} · ${number(settings.torqueFraction*100,0)}% demand · ${number(settings.maxCellLengthM)} m maximum cells`;
  }
  function renderResult(result,requestedSettings) {
    if (!result || !['completed','failed'].includes(result.status) || !result.telemetry?.channels) {
      showError('The engine returned an incomplete result format. Reload to use matching site files.');return;
    }
    latest={...result,settings:result.settings ?? requestedSettings};
    const completed=latest.status==='completed';
    $('result-context').textContent=context(latest);
    $('time-label').textContent=completed?'Lap time':'Accepted elapsed';
    $('metric-time').textContent=number(completed?latest.elapsedTimeS:latest.acceptedTimeS,2);
    $('time-detail').textContent=completed?'s · one simulated lap':'s · accepted prefix';
    $('energy-label').textContent=completed?'Pack energy':'Accepted energy';
    $('energy-detail').textContent=completed?'kWh · terminal net':'kWh · accepted prefix net';
    $('metric-energy').textContent=number(latest.energyKwh,3);
    const speeds=series(latest,'vehicle.speed_mps').filter(finite);
    if (speeds.length && finite(latest.startingSpeedMps)) speeds.push(latest.startingSpeedMps);
    $('metric-speed').textContent=number(speeds.length?Math.max(...speeds):null);
    $('metric-soc').textContent=number(finite(latest.socFinal)?latest.socFinal*100:null);
    $('soc-label').textContent=completed?'Final charge':'Attempt charge';
    $('soc-detail').textContent=completed?'% SOC':'% SOC · includes rejected attempt';
    resultStatus(completed?'Completed':'Incomplete lap',completed?'success':'warning');
    const note=[];
    if (!completed) note.push(`Incomplete lap: ${latest.failureReason ?? 'the vehicle could not finish'}. Accepted ${number(latest.acceptedDistanceM)} m; this result is not a ranked lap time.`);
    if (finite(latest.seamSpeedDeltaMps) && Math.abs(latest.seamSpeedDeltaMps)>0.1) note.push(`The lap has a ${number(latest.seamSpeedDeltaMps)} m/s start-to-finish speed difference; it is not a periodic steady-state lap.`);
    note.push(selectedProfile(latest.settings.vehicleProfile)?.description ?? 'Vehicle inputs remain source model assumptions.');
    if (!selectedCourse(latest.settings.courseId)?.synthetic) note.push('Measured-course x/y and prescribed curvature disagree. The map is a reference, not proof of a feasible racing line.');
    if (latest.settings.regenEnabled) note.push('The supplied pack accepts no charge power; permitting regeneration adds no recovery capacity.');
    if (Array.isArray(latest.warnings)) for (const warning of latest.warnings) {
      const text=typeof warning==='string'?warning:warning?.message;
      if (text && !note.includes(text)) note.push(text);
    }
    $('result-note').querySelector('p').textContent=note.join(' ');
    $('result-actions').hidden=false;
    $('save-run').disabled=typeof latest.runRecordJson!=='string';
    $('save-run').title=$('save-run').disabled?'Exact source record unavailable. Reload this page before exporting.':'';
    $('pin-run').disabled=!completed;
    drawGeometry(latest.courseGeometry,selectedCourse(latest.settings.courseId));
    buildChannels();
    sampleIndex=0;
    const length=stations(latest).length;
    $('sample-slider').max=Math.max(0,length-1);
    $('sample-slider').value=0;
    $('sample-slider').disabled=length<2;
    $('inspect-panel').hidden=length===0;
    drawChart();
    inspectSample();
    updateComparison();
  }
  function buildChannels() {
    const selected=$('chart-channel').value;
    const channels=latest.telemetry.channels;
    const options=Object.keys(definitions).filter(key=>channels[key]).map(key=>{
      const option=document.createElement('option');option.value=key;option.textContent=`${definitions[key].label} · ${definitions[key].unit}`;return option;
    });
    const others=document.createElement('optgroup');others.label='All other source channels';
    tableCells=[];
    const rows=[];
    for (const [key,channel] of Object.entries(channels)) {
      if (!Array.isArray(channel?.values)) continue;
      const row=document.createElement('tr'),name=document.createElement('td'),value=document.createElement('td');
      name.textContent=key;name.title=channel.origin ?? channel.description ?? '';
      row.append(name,value);rows.push(row);tableCells.push({key,unit:channel.unit || 'unit not declared',cell:value});
      if (!definitions[key] && channel.values.some(finite)) {
        const option=document.createElement('option');option.value=key;option.textContent=`${key} · ${channel.unit ?? 'unit not declared'}`;others.append(option);
      }
    }
    $('channel-table').replaceChildren(...rows);
    $('channel-count').textContent=`${rows.length} channels`;
    $('chart-channel').replaceChildren(...options,...(others.children.length?[others]:[]));
    $('chart-channel').disabled=$('chart-channel').options.length===0;
    if ($('chart-channel').disabled) {
      const option=document.createElement('option');option.value='';option.textContent='No accepted telemetry';$('chart-channel').append(option);
    }
    if ([...$('chart-channel').options].some(option=>option.value===selected)) $('chart-channel').value=selected;
  }
  function comparable() {
    return reference && latest && reference !== latest && reference.settings.courseId===latest.settings.courseId;
  }
  function updateComparison() {
    $('clear-comparison').hidden=!reference;
    $('reference-legend').hidden=!comparable();
    if (!reference) {$('comparison-note').textContent='Pin a completed run, then change an input.';return;}
    $('comparison-note').textContent=reference===latest?'Comparison saved on this page. Change an input and run again.':comparable()?`Comparison: ${number(reference.elapsedTimeS,2)} s · ${number(reference.settings.torqueFraction*100,0)}% demand`:'Comparison held. Select the same course to overlay its trace.';
  }
  function drawChart() {
    const key=$('chart-channel').value,channel=latest?.telemetry?.channels?.[key];
    const element=$('telemetry-svg');
    function emptyChart() {
      $('chart-empty').hidden=false;$('chart-content').hidden=true;
      const noAcceptedSamples=stations(latest).length===0;
      $('chart-empty').querySelector('p').textContent=noAcceptedSamples?'No accepted samples to plot.':'No valid samples for this channel.';
      $('chart-empty').querySelector('span').textContent=noAcceptedSamples?'The calculation stopped before a valid telemetry sample. See the failure reason above.':'Choose another recorded channel to inspect its trace. Missing values are preserved in the downloadable run record.';
    }
    if (!channel) {emptyChart();return;}
    const config=definitions[key] ?? {label:key,unit:channel.unit ?? 'unit not declared',factor:1};
    const pointSeries=result=>stations(result).map((distance,index)=>{
      const value=series(result,key)[index];
      return [distance,finite(value)?value*config.factor:null,index];
    }).filter(([x,y])=>finite(x)&&finite(y));
    const points=pointSeries(latest),refPoints=comparable()?pointSeries(reference):[];
    if (!points.length) {emptyChart();return;}
    $('chart-empty').hidden=true;$('chart-content').hidden=false;
    const all=points.concat(refPoints),values=all.map(point=>point[1]);
    let ymin=Math.min(...values),ymax=Math.max(...values);
    if (key==='vehicle.speed_mps') ymin=Math.min(0,ymin);
    if (key==='battery.power_w'||key==='vehicle.longitudinal_acceleration_mps2') {ymin=Math.min(0,ymin);ymax=Math.max(0,ymax);}
    const padding=Math.max((ymax-ymin)*0.08,Math.abs(ymax)*0.02,0.01);
    ymin-=padding;ymax+=padding;
    const xmax=Math.max(...all.map(point=>point[0]),1),left=57,right=606,top=20,bottom=209;
    const px=x=>left+x/xmax*(right-left),py=y=>bottom-(y-ymin)/(ymax-ymin)*(bottom-top);
    chartTransform={px,top,bottom};
    const title=svg('title',{id:'chart-svg-title'},`${config.label} in ${config.unit} versus distance in metres. ${points.length} accepted samples. Use the sample slider below to inspect exact values.`);
    const nodes=[title];
    for (let tick=0;tick<5;tick++) {
      const y=ymin+(ymax-ymin)*tick/4,pos=py(y);
      nodes.push(svg('line',{class:'plot-grid',x1:left,x2:right,y1:pos,y2:pos}));
      nodes.push(svg('text',{class:'plot-axis',x:left-9,y:pos+4,'text-anchor':'end'},number(y,Math.abs(ymax-ymin)<3?2:1)));
    }
    for (let tick=0;tick<5;tick++) nodes.push(svg('text',{class:'plot-axis',x:px(xmax*tick/4),y:bottom+23,'text-anchor':tick===0?'start':tick===4?'end':'middle'},number(xmax*tick/4,0)));
    nodes.push(svg('text',{class:'plot-axis',x:right,y:251,'text-anchor':'end'},'Distance · m'));
    nodes.push(svg('text',{class:'plot-axis',x:left,y:11},config.unit));
    const path=data=>data.map(([x,y,sourceIndex],index)=>`${index&&data[index-1][2]===sourceIndex-1?'L':'M'}${px(x).toFixed(2)},${py(y).toFixed(2)}`).join(' ');
    if (refPoints.length) nodes.push(svg('path',{class:'plot-line plot-reference',d:path(refPoints)}));
    nodes.push(svg('path',{class:'plot-line',d:path(points)}));
    nodes.push(svg('line',{id:'plot-cursor',class:'plot-cursor',x1:px(stations(latest)[sampleIndex]),x2:px(stations(latest)[sampleIndex]),y1:top,y2:bottom}));
    element.replaceChildren(...nodes);
    $('chart-unit').textContent=config.label;
    $('reference-legend').hidden=!refPoints.length;
  }
  function inspectSample() {
    if (!latest) return;
    const distances=stations(latest);
    sampleIndex=Math.max(0,Math.min(distances.length-1,Number($('sample-slider').value)));
    const distance=distances[sampleIndex];
    $('sample-station').textContent=`${number(distance)} m`;
    $('sample-slider').setAttribute('aria-valuetext',`${number(distance)} metres; sample ${sampleIndex+1} of ${distances.length}`);
    $('sample-time').textContent=`${number(times(latest)[sampleIndex],2)} s`;
    $('sample-speed').textContent=`${number(series(latest,'vehicle.speed_mps')[sampleIndex],2)} m/s`;
    const power=series(latest,'battery.power_w')[sampleIndex];
    $('sample-power').textContent=`${number(finite(power)?power/1000:null,2)} kW`;
    $('sample-acceleration').textContent=`${number(series(latest,'vehicle.longitudinal_acceleration_mps2')[sampleIndex],2)} m/s²`;
    for (const {key,unit,cell} of tableCells) {
      const value=series(latest,key)[sampleIndex];
      cell.textContent=`${finite(value)?value.toLocaleString(undefined,{maximumSignificantDigits:10}):value==null?'—':String(value)} ${unit}`.trim();
    }
    const cursor=$('plot-cursor');
    if (cursor && chartTransform && finite(distance)) {const x=chartTransform.px(distance);cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);}
    // The marker is a station on the prescribed centerline. It is never the
    // integrated pose, especially where measured x/y and curvature disagree.
    if (geometry?.synthetic && finite(distance)) {
      const data=geometry.data,ds=data.distanceM;
      let upper=ds.findIndex(station=>station>=distance);
      if (upper<0) upper=ds.length-1;
      const lower=Math.max(0,upper-1),span=ds[upper]-ds[lower];
      const fraction=span>0?(distance-ds[lower])/span:0;
      const x=data.xM[lower]+(data.xM[upper]-data.xM[lower])*fraction,y=data.yM[lower]+(data.yM[upper]-data.yM[lower])*fraction;
      const projected=geometry.project(x,y);
      $('course-cursor').toggleAttribute('hidden',false);$('course-cursor').setAttribute('cx',projected[0]);$('course-cursor').setAttribute('cy',projected[1]);
    } else $('course-cursor').toggleAttribute('hidden',true);
  }
  function download() {
    if (typeof latest?.runRecordJson!=='string') {
      showError('The exact saved run record is unavailable. Reload this page to use matching engine files.','Run export unavailable');return;
    }
    // Preserve Python's exact serialization: rewriting floats in JavaScript
    // changes the standard record content hash and makes native replay fail.
    const blob=new Blob([latest.runRecordJson],{type:'application/json'});
    const url=URL.createObjectURL(blob),link=document.createElement('a');
    const id=String(latest.runRecord.run_id ?? new Date().toISOString()).replace(/[^a-zA-Z0-9_-]/g,'-');
    link.href=url;link.download=`lapsim-${id}.json`;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  $('run-form').addEventListener('submit',run);
  $('cancel-button').addEventListener('click',cancel);
  $('retry-button').addEventListener('click',()=>run());
  $('run-settings').addEventListener('input',changed);
  $('run-settings').addEventListener('change',changed);
  $('drive-style').addEventListener('change',()=>{
    if ($('drive-style').value!=='custom') $('torque').value=$('drive-style').value;
    changed();
  });
  $('torque').addEventListener('input',()=>{
    const value=$('torque').value;
    $('drive-style').value=['0.55','0.8','1'].includes(value)?value:'custom';
  });
  $('chart-channel').addEventListener('change',()=>{drawChart();inspectSample();});
  $('sample-slider').addEventListener('input',inspectSample);
  $('save-run').addEventListener('click',download);
  $('pin-run').addEventListener('click',()=>{if (latest?.status==='completed') {reference=latest;updateComparison();drawChart();}});
  $('clear-comparison').addEventListener('click',()=>{reference=null;updateComparison();drawChart();});
  window.addEventListener('pagehide',()=>{stopWorker('Page closed.');clearInterval(clockTimer);});
  updateSetupNotes();
  // Read-only diagnostics for release checks; this does not provide a second
  // simulation path or alter any physics result.
  window.LAPSIM_WEB=Object.freeze({getState:()=>({running:!!active,ready,result:latest,comparison:reference,capabilities:catalog})});
})();
