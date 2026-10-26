'use strict';
// Exercise the production file-load handler and observe retained UI state.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'data.json'),'utf8'));
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.style={};this.events={};this.hidden=false;this.width=1000;this.height=640;}
  append(...nodes){this.children.push(...nodes);}
  set value(v){this._value=String(v);}
  get value(){return this._value;}
  replaceChildren(...nodes){this.children=nodes;if(this.tag==='select')this.value=nodes[0]?.value||'';}
  addEventListener(name,fn){this.events[name]=fn;}
  get selectedOptions(){return this.children.filter(n=>n.value===this.value);}
  getContext(){return new Proxy({},{get:()=>()=>{}});}
}
const elements=new Map();
for(const id of ['course','criterion','strategy','speed'])elements.set(id,new Element('select'));
for(const [value,textContent] of [['time','Fastest completed round'],['energy','Lowest net energy'],['proxy','Legacy proxy']]){const o=new Element('option');Object.assign(o,{value,textContent});elements.get('criterion').append(o);}
elements.get('criterion').value='time';elements.get('speed').value='12';
const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const context={document:{getElementById:get,createElement:tag=>new Element(tag)},window:{LAPSIM_REVIEW:data},requestAnimationFrame:()=>{},console};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'app.js'),'utf8'),context);
assert.equal(get('error').textContent,'');
assert.equal(get('winner').textContent,'awd-p4-fsg');
get('course').value='2';get('course').events.change();get('criterion').value='energy';get('criterion').events.change();
assert.equal(get('winner').textContent,'holdout-p2');
const prior={course:get('course').value,winner:get('winner').textContent,rows:get('results').children,source:get('source').textContent};
async function load(candidate){await get('load').events.change({target:{files:[{size:1000,text:async()=>JSON.stringify(candidate)}]}});}
(async()=>{
  const mutations=[
    d=>{d.groups[0].runs=[];},
    ...['metrics','policy','laps','mode_occupancy'].map(field=>d=>{delete d.groups[0].runs[0][field];}),
    d=>{d.groups[0].runs[0].policy.structure=null;},
    d=>{d.groups[0].runs[0].samples[0]='0123456789';},
    d=>{d.excluded[0].reasons='invalid';}
    ,d=>{d.groups[0].runs[0].effective_policy_sha256={toString:null};}
    ,d=>{d.groups[0].provenance.provenance.source_name={toString:null};}
    ,d=>{d.groups[0].provenance.provenance.review_note={toString:null};}
    ,d=>{d.groups[0].provenance.scope={toString:null};}
  ];
  for(const mutate of mutations){const bad=structuredClone(data);mutate(bad);await load(bad);assert.match(get('error').textContent,/^Load rejected:/);assert.equal(get('error').hidden,false);assert.equal(get('course').value,prior.course);assert.equal(get('winner').textContent,prior.winner);assert.equal(get('results').children,prior.rows);assert.equal(get('source').textContent,prior.source);}
  await load(structuredClone(data));assert.equal(get('error').hidden,true);assert.equal(get('course').value,'0');assert.equal(get('winner').textContent,'awd-p3-fsg');
  console.log('PASS: 12 malformed file loads preserve selected course, winner, table and evidence; valid reload succeeds.');
})().catch(error=>{console.error(error);process.exitCode=1;});
