(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const MAX_BYTES = 20_000_000;
  const names = {ready:'Ready',limited:'Limited',inhibited:'Inhibited',recovery_pending:'Recovery pending'};
  const number = value => value.toLocaleString(undefined,{maximumFractionDigits:3});
  const phrase = value => value ? value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()) : 'Within the reference limits';
  let receipt = null, cursor = null, chartX = null, loadGeneration = 0;
  function node(tag, attributes, content) {
    const element = document.createElementNS(NS, tag);
    for (const [key,value] of Object.entries(attributes ?? {})) element.setAttribute(key,value);
    if (content !== undefined) element.textContent = content;
    return element;
  }
  function error(message) {
    $('load-error').hidden = false;
    $('load-error').textContent = message;
    $('load-status').textContent = 'The selected replay could not be opened. Previous evidence is retained.';
  }
  function accept(text, filename) {
    if (new TextEncoder().encode(text).byteLength > MAX_BYTES) throw new Error('Choose a replay smaller than 20 MB.');
    const next = BenchData.validateReceipt(JSON.parse(text));
    receipt = next;
    $('load-error').hidden = true;
    $('empty').hidden = true;
    $('replay').hidden = false;
    $('receipt-title').textContent = receipt.label;
    $('provenance').textContent = receipt.provenance;
    $('file-name').textContent = filename;
    const summary = BenchData.summarize(receipt);
    for (const id of ['cycles','allowed','held','recovering']) $(id).textContent = number(summary[id]);
    $('cycle-slider').max = receipt.records.length - 1;
    $('cycle-slider').value = '0';
    $('scenario-hash').textContent = receipt.scenario_sha256;
    $('period').textContent = `${receipt.config.period_ms} ms · synthetic policy`;
    $('qualification').textContent = `${receipt.config.fault.valid_samples_to_recover} consecutive healthy, unsaturated cycles`;
    $('sources').replaceChildren(...Object.entries(receipt.source_sha256).map(([name,hash]) => {
      const row = document.createElement('tr');
      const file = document.createElement('td'), digest = document.createElement('td');
      file.textContent = name; digest.textContent = hash; digest.className = 'hash';
      row.append(file,digest); return row;
    }));
    renderEvents(); drawTrace(); inspect(0);
    $('load-status').textContent = `${receipt.label} opened. ${summary.cycles} cycles; ${summary.held} held at zero.`;
  }
  function drawTrace() {
    const svg = $('trace');
    svg.replaceChildren(node('desc',{id:'trace-description'}));
    const chartWidth=Math.max(280,Math.round(svg.getBoundingClientRect().width));
    svg.setAttribute('viewBox',`0 0 ${chartWidth} 280`);
    const rows = receipt.records, left=55, right=chartWidth-16, top=20, bottom=235;
    // Normalize first so extreme finite diagnostic requests cannot overflow
    // the axis range. The chart is indexed by cycle; exact time stays visible.
    const totals = rows.map(r=>r.command_nm.reduce((a,b)=>a+b,0));
    const requests = rows.map(r=>r.allocator.requested_nm);
    const scale = Math.max(1,...requests.map(Math.abs),...totals.map(Math.abs));
    const low = Math.min(0,...requests.map(v=>v/scale));
    const high = Math.max(1/scale,...requests.map(v=>v/scale),...totals.map(v=>v/scale));
    chartX = index => rows.length===1 ? (left+right)/2 : left+(right-left)*index/(rows.length-1);
    const y = value => bottom-(value/scale-low)/(high-low)*(bottom-top);
    rows.forEach((row,index)=>{
      if (!row.command_allowed) svg.append(node('rect',{
        x:index===rows.length-1?right-2:chartX(index),y:top,
        width:index===rows.length-1?2:chartX(index+1)-chartX(index),height:bottom-top,class:'hold-band'}));
    });
    for (let step=0;step<=4;step++) {
      const ratio=low+(high-low)*step/4, position=bottom-(bottom-top)*step/4;
      svg.append(node('line',{x1:left,x2:right,y1:position,y2:position,class:'trace-grid'}));
      const value=ratio*scale;
      svg.append(node('text',{x:left-12,y:position+4,'text-anchor':'end',class:'trace-label'},
        Math.abs(value)>1e6 ? value.toExponential(1) : number(value)));
    }
    // Commands are discrete outputs held until the next observed cycle. A
    // step plot preserves immediate fault zeroing instead of implying a ramp.
    const line = values => values.map((value,index)=>index
      ? `L${chartX(index)},${y(values[index-1])} L${chartX(index)},${y(value)}`
      : `M${chartX(index)},${y(value)}`).join(' ');
    svg.append(node('path',{d:line(requests),class:'request-line'}));
    svg.append(node('path',{d:line(totals),class:'command-line'}));
    if(rows.length===1) svg.append(node('circle',{cx:chartX(0),cy:y(totals[0]),r:4,fill:'var(--accent)'}));
    cursor=node('line',{x1:left,x2:left,y1:top,y2:bottom,class:'trace-cursor'}); svg.append(cursor);
    svg.append(node('text',{x:left,y:bottom+30,class:'trace-label'},'Cycle 0'));
    svg.append(node('text',{x:right,y:bottom+30,'text-anchor':'end',class:'trace-label'},`Cycle ${rows.length-1}`));
    $('trace-description').textContent=`${rows.length} cycles. Dashed line: total driver request; solid line: proposed total. Shaded intervals are held at zero. Inspect exact values with the cycle slider below.`;
  }
  function inspect(index) {
    const row=receipt.records[index];
    $('cycle-slider').value=index;
    const time=row.now_ms===null?'invalid timestamp':`${number(row.now_ms)} ms`;
    $('cycle-label').textContent=`Cycle ${index} of ${receipt.records.length-1} · ${time}`;
    $('cycle-slider').setAttribute('aria-valuetext',`Cycle ${index}, ${time}, ${names[row.fault.next_state]}, ${phrase(row.command_reason)}`);
    $('state').textContent=names[row.fault.next_state];
    $('state').className=`state${row.command_allowed?'':' held'}`;
    $('command-permission').textContent=row.command_allowed?'Command allowed':'Proposed command held at zero';
    $('reason').textContent=phrase(row.command_reason);
    $('request-value').textContent=`${number(row.allocator.requested_nm)} N·m`;
    $('delivery-value').textContent=`${number(row.allocator.delivered_nm)} N·m`;
    $('allocator-state').textContent=phrase(row.allocator.status);
    $('guard-state').textContent=phrase(row.guard.status);
    $('pedal-latch').textContent=row.guard.pedal_overlap_latched?'Latched':'Clear';
    $('generation').textContent=number(row.fault.generation);
    row.command_nm.forEach((value,wheel)=>{
      const unit=document.createElement('small'); unit.textContent=' N·m';
      $(`wheel-${wheel}`).replaceChildren(document.createTextNode(number(value)),unit);
    });
    cursor.setAttribute('x1',chartX(index));cursor.setAttribute('x2',chartX(index));
    $('events').querySelectorAll('tr').forEach(tr=>{
      tr.classList.toggle('selected',Number(tr.dataset.cycle)===index);
      const button=tr.querySelector('button');
      if(Number(tr.dataset.cycle)===index) button.setAttribute('aria-current','true');
      else button.removeAttribute('aria-current');
    });
  }
  function renderEvents() {
    $('events').replaceChildren(...BenchData.eventIndices(receipt).map(index=>{
      const row=receipt.records[index], tr=document.createElement('tr'); tr.dataset.cycle=index;
      const cell=document.createElement('td'), button=document.createElement('button');button.type='button';
      button.textContent=`${index} · ${row.now_ms===null?'invalid':number(row.now_ms)+' ms'}`;
      button.setAttribute('aria-label',`Inspect cycle ${index}, ${names[row.fault.next_state]}`);
      button.addEventListener('click',()=>{inspect(index);$('cycle-slider').focus();});cell.append(button);tr.append(cell);
      for (const value of [names[row.fault.next_state],row.command_allowed?'Allowed':'Held at zero',phrase(row.command_reason)]) {
        const td=document.createElement('td');td.textContent=value;tr.append(td);
      }
      return tr;
    }));
  }
  $('cycle-slider').addEventListener('input',()=>inspect(Number($('cycle-slider').value)));
  window.addEventListener('resize',()=>{
    if(receipt){drawTrace();inspect(Number($('cycle-slider').value));}
  });
  $('receipt-file').addEventListener('change',async event=>{
    const file=event.target.files?.[0]; if(!file)return;
    const token=++loadGeneration;
    try{
      if(file.size>MAX_BYTES)throw new Error('Choose a replay smaller than 20 MB.');
      const text=await file.text();if(token===loadGeneration)accept(text,file.name);
    }catch(cause){if(token===loadGeneration)error(cause.message);}
    finally{event.target.value='';}
  });
  $('demo-button').addEventListener('click',async()=>{
    const token=++loadGeneration; $('demo-button').disabled=true;
    try{
      const embedded=document.getElementById('embedded-replay');
      if(embedded){
        accept(embedded.textContent,'Embedded replay');
        return;
      }
      const response=await fetch('./examples/enme408-synthetic-replay.json');
      if(!response.ok)throw new Error('The example could not load. Choose a local replay file or reload the site.');
      const text=await response.text();if(token===loadGeneration)accept(text,'Synthetic example · 18 cycles');
    }catch(cause){if(token===loadGeneration)error(location.protocol==='file:'?'Use Choose replay file, or serve this folder locally to load the example.':cause.message);}
    finally{$('demo-button').disabled=false;}
  });
  if(document.getElementById('embedded-replay'))$('demo-button').textContent='Load embedded replay';
  $('print-button').addEventListener('click',()=>window.print());
})();
