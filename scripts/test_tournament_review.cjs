'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const c=require('../web/tournament-review/app.js');
const d=c.validate(JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../web/tournament-review/data.json'),'utf8')));
assert.equal(d.groups.reduce((n,g)=>n+g.runs.length,0),16);
const holdout=d.groups.find(g=>g.runs.some(r=>r.id==='holdout-p0'));
assert.deepEqual(c.winners(holdout,'time').map(r=>r.id),['holdout-p1']);
assert.deepEqual(c.winners(holdout,'energy').map(r=>r.id),['holdout-p2']);
const tech=d.groups.find(g=>g.runs.some(r=>r.id==='awd-p0-tech'));
assert.ok(c.winners(tech,'energy').every(r=>r.id!=='awd-p5-tech'),'Incomplete paired immigrant must not win');
const tied={...holdout,runs:[holdout.runs[0],{...holdout.runs[0],id:'exact-tie'}]};
assert.equal(c.winners(tied,'time').length,2);
assert.deepEqual(c.winners({...holdout,runs:holdout.runs.map(r=>({...r,accepted:false}))},'time'),[]);
const r=holdout.runs[0];assert.deepEqual(c.sample(r,-100),r.samples[0]);assert.deepEqual(c.sample(r,10000),r.samples.at(-1));
const bad=structuredClone(d);bad.groups[0].runs[0].samples[1][0]=0;assert.throws(()=>c.validate(bad));
for(const g of d.groups){assert.equal(new Set(g.runs.map(r=>r.architecture)).size,1);for(const r of g.runs)assert.equal(r.samples[0][0],0);}
console.log('PASS: 16 saved runs, heldout criteria, excluded immigrant, ties, no finishers, interpolation endpoints, invalid saved samples, hardware strata');
