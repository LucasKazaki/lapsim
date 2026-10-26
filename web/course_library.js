/* Shared course selection only; the server validates geometry and runs physics. */
(function(root){'use strict';
 function mount({select,status,preview,changed=()=>{}}){
  const entries=new Map();
  const selection=()=>entries.get(select.value)||null;
  function render(){
   const entry=selection();preview.replaceChildren();
   if(!entry){status.textContent='Built-in or imported course. Imported geometry keeps its own provenance; all corridor widths are assumptions.';return;}
   const g=entry.bundle.geometry,x=g.x_m,y=g.y_m;
   const xmin=Math.min(...x),ymin=Math.min(...y),dx=Math.max(...x)-xmin,dy=Math.max(...y)-ymin;
   preview.setAttribute('viewBox',`${xmin-4} ${-ymin-dy-4} ${dx+8} ${dy+8}`);
   const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');
   line.setAttribute('points',x.map((v,i)=>`${v},${-y[i]}`).join(' '));
   line.setAttribute('fill','none');line.setAttribute('stroke','#5bdfd5');line.setAttribute('stroke-width','1.2');
   preview.append(line);
   const evidence=entry.trajectory_source?'Existing fused GNSS/IMU XY trajectory reconstructed as tangent arcs. Original IMU curvature is not reused; no surveyed accuracy claim.':entry.image_url?`${entry.event}, ${entry.year}. IMAGE-DERIVED APPROXIMATION. ${entry.scale_basis} ${entry.direction_assumption}`:entry.classification==='map_derived_approximation'?'Upstream simulator-map approximation; event year/survey accuracy unknown.':'Original synthetic FSAE-inspired test.';
   status.textContent=`${entry.label} · ${entry.length_m.toFixed(1)} m · minimum arc radius ${entry.audit.minimum_radius_m.toFixed(1)} m. ${evidence} Assumed 6 m corridor, not the original cone boundaries. ${entry.license}. Geometry ${entry.geometry_sha256.slice(0,12)}.${entry.source_url?' Source: '+entry.source_url:''}`;
  }
  select.addEventListener('change',()=>{render();changed();});
  const ready=(async()=>{try{
   const response=await fetch('/api/course/catalog');const data=await response.json();
   if(!response.ok||data.schema!=='lapsim.course-library.v1'||!Array.isArray(data.courses))throw Error(data.error||'Unsupported course library');
   for(const entry of data.courses){
    if(!entry.bundle||entry.geometry_sha256!==entry.bundle.geometry_sha256||!['map_derived_approximation','synthetic_fsae_inspired','trajectory_derived_approximation'].includes(entry.classification))throw Error('Course identity/evidence mismatch');
    const key='library:'+entry.id;if(entries.has(key))throw Error('Duplicate course library identity');
    entries.set(key,entry);const option=document.createElement('option');option.value=key;option.textContent=entry.label;select.append(option);
   }
  }catch(error){status.textContent='Shipped course library unavailable: '+error.message+'. Existing built-ins/imports remain available.';}})();
  return {selection,render,ready};
 }
 root.LapSimCourseLibrary={mount};
 if(typeof module==='object'&&module.exports)module.exports={mount};
})(typeof window==='object'?window:globalThis);
