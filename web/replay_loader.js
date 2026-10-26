/* Load the legacy recorded fixture only when a viewer explicitly requests it. */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.LapSimReplayLoader=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function create(host,document){
  let pending=null;
  return {loadDefault(){
   if(host.LAPSIM_TOURNAMENT)return Promise.resolve(host.LAPSIM_TOURNAMENT);
   if(!pending)pending=new Promise(resolve=>{
    const script=document.createElement('script');
    script.src='../work/tournament-accepted-4082025/replay-data.js';
    script.onload=()=>resolve(host.LAPSIM_TOURNAMENT||null);
    script.onerror=()=>resolve(null);
    document.head.appendChild(script);
   });
   return pending;
  }};
 }
 return {create};
});
