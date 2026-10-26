'use strict';
// Exercise production controls and prove this release has no external file path.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'data.json'),'utf8'));
const source=fs.readFileSync(path.join(__dirname,'app.js'),'utf8'),html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
assert.doesNotMatch(html,/<input[^>]+type=["']file["']/i,'External file input must be absent');
assert.doesNotMatch(source,/\$\(['"]load['"]\)|file\.text\(|target\.files|FileReader/,'External file handler must be absent');
assert.match(html,/bundled saved results only/i);
assert.match(html,/<option value="points" selected>/,'Combined simulated points must be the actual default');
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.style={};this.events={};this.hidden=false;this.width=1000;this.height=640;}
  append(...nodes){this.children.push(...nodes);}
  set value(v){this._value=String(v);}get value(){return this._value;}
  replaceChildren(...nodes){this.children=nodes;if(this.tag==='select')this.value=nodes[0]?.value||'';}
  addEventListener(name,fn){this.events[name]=fn;}
  get selectedOptions(){return this.children.filter(n=>n.value===this.value);}
  getContext(){return new Proxy({},{get:()=>()=>{}});}
}
const elements=new Map();let frame;
for(const id of ['course','criterion','strategy','speed'])elements.set(id,new Element('select'));
for(const [value,textContent] of [['points','Simulated endurance + efficiency (275 + 100)'],['time','Fastest completed round'],['energy','Lowest net energy'],['proxy','Historical engineering proxy']]){const o=new Element('option');Object.assign(o,{value,textContent});elements.get('criterion').append(o);}
elements.get('criterion').value='points';elements.get('speed').value='12';
const htmlIds=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
const get=id=>{assert.ok(htmlIds.has(id),'Production handler requested missing HTML element: '+id);assert.notEqual(id,'load','No file control may be requested or wired');if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
vm.runInNewContext(source,{document:{getElementById:get,createElement:tag=>new Element(tag)},window:{LAPSIM_REVIEW:data,TournamentScoring:require('./scoring.js'),ParameterDisplay:require('./parameter_display.js')},requestAnimationFrame:fn=>{frame=fn;},console});
assert.equal(get('error').textContent,'');assert.equal(get('winner').textContent,'awd-p0-fsg');
assert.match(get('reason').textContent,/endurance.*efficiency.*375.*not official/i);
assert.match(get('score-note').textContent,/lapsim.fsae-inspired-equal-lap-2027v1.1/);
assert.match(get('score-note').textContent,/awd-p4-fsg.*awd-p3-fsg/);
const policy=get('policies').children[0],parameterList=policy.children.find(n=>n.tag==='dl'),exact=policy.children.find(n=>n.tag==='details');
assert.ok(parameterList.children.some(n=>/^\d+\.\d%$/.test(n.textContent)),'Percent parameters are readable');
assert.equal(JSON.parse(exact.children.find(n=>n.tag==='pre').textContent).parameters.yaw_kp,data.groups[0].runs[0].policy.parameters.yaw_kp,'Raw executed precision is retained in details');
assert.match(policy.children[1].textContent,/baseline/i);
assert.equal(data.groups.reduce((n,g)=>n+g.runs.length,0),16);
for(let i=0;i<data.groups.length;i++){get('course').value=i;get('course').events.change();assert.equal(get('results').children.length,data.groups[i].runs.length);assert.equal(get('score-results').children.length,data.groups[i].runs.length);for(const criterion of ['points','time','energy','proxy']){get('criterion').value=criterion;get('criterion').events.change();assert.notEqual(get('winner').textContent,'awd-p5-tech');}for(const row of get('score-results').children){assert.equal(row.children[6].textContent,'Unavailable','No recorded recovered-energy telemetry');assert.equal(row.children[7].textContent,'Not modeled','No event penalty model');}}
get('course').value='2';get('course').events.change();get('criterion').value='energy';get('criterion').events.change();assert.equal(get('winner').textContent,'holdout-p2');
get('criterion').value='time';get('criterion').events.change();assert.equal(get('winner').textContent,'holdout-p1');
get('criterion').value='points';get('criterion').events.change();assert.equal(get('winner').textContent,'holdout-p0');
get('strategy').value='holdout-p1';get('strategy').events.change();assert.match(get('live').textContent,/holdout-p1/);
frame(0);get('play').events.click();frame(1000);assert.ok(Number.parseFloat(get('clock').textContent)>0,'Replay advances from saved samples');
get('scrub').value='20';get('scrub').events.input();assert.equal(get('clock').textContent,'20.00 s');
get('restart').events.click();assert.equal(get('clock').textContent,'0.00 s');
get('reset').events.click();assert.equal(get('course').value,'0');assert.equal(get('criterion').value,'points');assert.equal(get('winner').textContent,'awd-p0-fsg');assert.equal(get('play').textContent,'Play');
const refreshed=structuredClone(data),failed={...structuredClone(data.groups[0].runs[0]),id:'first-lap-failure',accepted:false,selection_eligible:false,status:'failed',completed_laps:0,laps:[]};refreshed.groups[0].runs.push(failed);
vm.runInNewContext(source,{document:{getElementById:get,createElement:tag=>new Element(tag)},window:{LAPSIM_REVIEW:refreshed,TournamentScoring:require('./scoring.js'),ParameterDisplay:require('./parameter_display.js')},requestAnimationFrame:fn=>{frame=fn;},console});
assert.equal(get('error').textContent,'');assert.equal(get('results').children.length,6);assert.match(get('results').children.at(-1).children[1].textContent,/failed/i);assert.notEqual(get('winner').textContent,'first-lap-failure');
console.log('PASS: bundled-only production controls; 16 runs, 5 strata, default combined points, all criteria, honest missing telemetry, rounded/exact parameters, heldout extremes, immigrant exclusion, strategy, replay, scrub, restart and reset.');
