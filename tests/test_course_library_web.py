"""Actual shared browser selector contract in Node; no plant/browser job."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_actual_picker_selects_embedded_bundle_and_clears_old_map():
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    root=Path(__file__).resolve().parents[1]
    script=r"""
    const assert=require('node:assert/strict'),fs=require('node:fs');
    const mount=require(process.argv[1]).mount;
    const catalog=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
    catalog.courses=catalog.courses.map(e=>({...e,bundle:JSON.parse(fs.readFileSync(process.argv[3]+'/'+e.id+'.json','utf8'))}));
    const make=()=>({children:[],attrs:{},append(x){this.children.push(x)},replaceChildren(){this.children=[]},setAttribute(k,v){this.attrs[k]=v}});
    global.document={createElement:make,createElementNS:make};
    global.fetch=async()=>({ok:true,json:async()=>catalog});
    const select=make();select.value='autocross';select.addEventListener=(event,fn)=>select.changed=fn;
    const status=make(),preview=make();let changes=0;
    const picker=mount({select,status,preview,changed:()=>changes++});
    (async()=>{
      await picker.ready;assert.equal(select.children.length,catalog.courses.length);
      select.value='library:'+catalog.courses[0].id;select.changed();
      assert.deepEqual(picker.selection().bundle,catalog.courses[0].bundle);
      assert(status.textContent.includes('event year/survey accuracy unknown'));
      assert(status.textContent.includes('not the original cone boundaries'));
      assert.equal(preview.children.length,1);
      select.value='stadium';select.changed();assert.equal(picker.selection(),null);
      assert.equal(preview.children.length,0);assert.equal(changes,2);
      console.log('Shared selector/identity/provenance/stale-map checks passed');
    })().catch(e=>{console.error(e);process.exitCode=1});
    """
    result=subprocess.run([node,'-e',script,str(root/'web/course_library.js'),
        str(root/'configs/courses/catalog.json'),str(root/'configs/courses')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
