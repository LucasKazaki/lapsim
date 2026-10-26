/* Logged-pose presentation only. Three.js owns graphics, never simulation. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./vendor/three-0.160.0.min.js'));
  } else {
    root.LapSimWebGL = factory(root.THREE);
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (THREE) {
  'use strict';
  if (!THREE) throw new Error('The local Three.js dependency is unavailable.');
  const LIMITS = Object.freeze({ghosts:8, samples:2000, coursePoints:5000,
    pixelRatio:2, bufferPixels:4000000, cssDimension:32768, coordinateM:100000});
  const BREAKPOINTS = Object.freeze({mobileMax:700, compactMax:1000, wideMin:1800});
  const COLORS = Object.freeze(['#5bdfd5','#ffbd66','#b2a2ff','#ff7d9f','#83ce7b','#82b9ff','#ff9c6d','#d3e28f']);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));

  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') {
      return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}';
    }
    return JSON.stringify(value);
  }

  function layoutMode(width) {
    if (!finite(width) || width <= 0) throw new Error('Viewport width must be finite and positive.');
    return width <= BREAKPOINTS.mobileMax ? 'mobile' : width <= BREAKPOINTS.compactMax ? 'compact' : 'desktop';
  }

  function viewportPolicy(width, height, dpr = 1) {
    if (!finite(width) || !finite(height) || width <= 0 || height <= 0 ||
        width > LIMITS.cssDimension || height > LIMITS.cssDimension) {
      return {suspended:true, reason:'Canvas is hidden or outside the supported size range.'};
    }
    const cssWidth = Math.max(1, Math.floor(width));
    const cssHeight = Math.max(1, Math.floor(height));
    const requested = finite(dpr) && dpr > 0 ? dpr : 1;
    const pixelRatio = Math.min(requested, LIMITS.pixelRatio,
      Math.sqrt(LIMITS.bufferPixels / (cssWidth * cssHeight)));
    return {suspended:false, width:cssWidth, height:cssHeight, pixelRatio,
      bufferWidth:Math.max(1, Math.floor(cssWidth * pixelRatio)),
      bufferHeight:Math.max(1, Math.floor(cssHeight * pixelRatio)), aspect:cssWidth/cssHeight};
  }

  function cameraInput(view, action) {
    const next = {...view};
    if (action === 'reset') return {cameraMode:'orbit', azimuth:-.65, elevation:.9, zoom:1};
    if (action === 'zoom-in') next.zoom = (next.zoom || 1) * 1.2;
    else if (action === 'zoom-out') next.zoom = (next.zoom || 1) / 1.2;
    else if (action === 'left') { next.azimuth = (next.azimuth || 0) - .12; next.cameraMode='orbit'; }
    else if (action === 'right') { next.azimuth = (next.azimuth || 0) + .12; next.cameraMode='orbit'; }
    else if (action === 'up') { next.elevation = (next.elevation || .9) + .08; next.cameraMode='orbit'; }
    else if (action === 'down') { next.elevation = (next.elevation || .9) - .08; next.cameraMode='orbit'; }
    else throw new Error('Unknown camera action.');
    next.zoom = clamp(next.zoom || 1, .4, 4);
    next.elevation = clamp(next.elevation || .9, .25, 1.5);
    return next;
  }

  function validateRun(run) {
    if (!run || !Array.isArray(run.telemetry) || !run.telemetry.length || run.telemetry.length > LIMITS.samples) {
      throw new Error('Replay requires 1-2000 logged samples per run.');
    }
    let last = -Infinity;
    for (const row of run.telemetry) {
      if (![row.t_s,row.x_m,row.y_m,row.heading_rad].every(finite) || row.t_s < 0 || row.t_s <= last ||
          Math.abs(row.x_m) > LIMITS.coordinateM || Math.abs(row.y_m) > LIMITS.coordinateM) {
        throw new Error('Replay poses must be finite, bounded and strictly ordered by time.');
      }
      last = row.t_s;
    }
    validateCourse(run.course);
    const car=run.car || {};
    for(const key of ['cg_to_front_axle_m','cg_to_rear_axle_m','front_track_m','rear_track_m','wheel_radius_m']) {
      if(!finite(car[key]) || car[key]<=0 || car[key]>10)throw new Error('Logged car geometry requires positive bounded SI values: '+key);
    }
  }

  function validateCourse(course) {
    if (!course || !Array.isArray(course.x_m) || !Array.isArray(course.y_m) ||
        course.x_m.length !== course.y_m.length || course.x_m.length < 3 || course.x_m.length > LIMITS.coursePoints ||
        ![...course.x_m,...course.y_m].every(value => finite(value) && Math.abs(value) <= LIMITS.coordinateM)) {
      throw new Error('Course requires matching bounded finite XY arrays with 3-5000 points.');
    }
    for (let i=1; i<course.x_m.length; i++) {
      if (Math.hypot(course.x_m[i]-course.x_m[i-1], course.y_m[i]-course.y_m[i-1]) <= 1e-10) {
        throw new Error('Course contains a repeated zero-length cell.');
      }
    }
  }

  function sameConditions(items) {
    if (!Array.isArray(items) || items.length > LIMITS.ghosts) throw new Error('At most eight isolated ghosts may be displayed.');
    const ids = new Set();
    const signature = item => stable({case:item.run.case, car:item.run.car, actuation:item.run.actuation,
      driver:item.run.driver, environment:item.run.environment, course:item.run.course,
      clocks:item.run.clocks, profile:item.run.profile});
    let first;
    for (const item of items) {
      if (!item || typeof item.id !== 'string' || !item.id || item.id.length > 128 || ids.has(item.id)) {
        throw new Error('Ghost run identifiers must be unique and bounded.');
      }
      ids.add(item.id);
      validateRun(item.run);
      const current = signature(item);
      if (first !== undefined && first !== current) throw new Error('Cannot overlay runs with different conditions, car, driver, clocks or course.');
      first = current;
    }
  }

  function samplePose(run, time) {
    if (!finite(time)) throw new Error('Display time must be finite.');
    const rows=run.telemetry;
    if (!rows || !rows.length) throw new Error('Missing logged poses.');
    let lo=0, hi=rows.length-1;
    while (lo<hi) {
      const mid=Math.ceil((lo+hi)/2);
      if (rows[mid].t_s<=time) lo=mid;
      else hi=mid-1;
    }
    const a=rows[lo], b=rows[Math.min(lo+1,rows.length-1)];
    const alpha=b.t_s===a.t_s?0:clamp((time-a.t_s)/(b.t_s-a.t_s),0,1);
    return {...a, x_m:a.x_m+(b.x_m-a.x_m)*alpha, y_m:a.y_m+(b.y_m-a.y_m)*alpha,
      heading_rad:a.heading_rad+Math.atan2(Math.sin(b.heading_rad-a.heading_rad),Math.cos(b.heading_rad-a.heading_rad))*alpha,
      source_time_a_s:a.t_s, source_time_b_s:b.t_s, display_alpha:alpha,
      terminal:time>=rows[rows.length-1].t_s};
  }

  function worldPosition(x, y, height=0) { return new THREE.Vector3(x,height,-y); }

  function lineFrom(points, color, opacity=1) {
    const geometry=new THREE.BufferGeometry().setFromPoints(points);
    const material=new THREE.LineBasicMaterial({color, transparent:opacity<1, opacity, depthTest:true, depthWrite:false});
    return new THREE.Line(geometry, material);
  }

  function roadGeometry(course, halfWidth) {
    const n=course.x_m.length, vertices=[], indices=[], left=[], right=[];
    const closed=Math.hypot(course.x_m[0]-course.x_m[n-1],course.y_m[0]-course.y_m[n-1])<.01;
    for (let i=0;i<n;i++) {
      const before=i===0?(closed?n-2:0):i-1;
      const after=i===n-1?(closed?1:n-1):i+1;
      const dx=course.x_m[after]-course.x_m[before], dy=course.y_m[after]-course.y_m[before];
      const length=Math.hypot(dx,dy);
      if (length<1e-10) throw new Error('Course tangent is undefined.');
      const nx=-dy/length, ny=dx/length;
      const a=worldPosition(course.x_m[i]+halfWidth*nx,course.y_m[i]+halfWidth*ny);
      const b=worldPosition(course.x_m[i]-halfWidth*nx,course.y_m[i]-halfWidth*ny);
      vertices.push(a.x,a.y,a.z,b.x,b.y,b.z);
      left.push(a.clone().setY(.015)); right.push(b.clone().setY(.015));
      if (i<n-1) { const k=i*2; indices.push(k,k+1,k+2,k+1,k+3,k+2); }
    }
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
    geometry.setIndex(indices); geometry.computeVertexNormals();
    return {geometry,left,right};
  }

  function makeCar(run, color, index) {
    const group=new THREE.Group(); group.name='logged-car-'+index;
    const ghost=index>0, opacity=ghost?.32:1;
    const body=new THREE.MeshStandardMaterial({color,metalness:.15,roughness:.6,
      transparent:ghost,opacity,depthTest:true,depthWrite:!ghost});
    const tires=new THREE.MeshStandardMaterial({color:ghost?color:'#26313f',roughness:.9,
      transparent:ghost,opacity,depthTest:true,depthWrite:!ghost});
    const metal=new THREE.MeshStandardMaterial({color:ghost?color:'#b9c6d6',metalness:.5,roughness:.4,
      transparent:ghost,opacity,depthTest:true,depthWrite:!ghost});
    const car=run.car, front=car.cg_to_front_axle_m, rear=car.cg_to_rear_axle_m;
    const frontTrack=car.front_track_m, rearTrack=car.rear_track_m, radius=car.wheel_radius_m;
    const length=front+rear+.55, bodyWidth=Math.min(frontTrack,rearTrack)*.65;
    function box(l,h,w,x,y,z,material=body) {
      const mesh=new THREE.Mesh(new THREE.BoxGeometry(l,h,w),material);
      mesh.position.set(x,y,z); group.add(mesh); return mesh;
    }
    // Body, nose, wings, seat and roll hoop are illustrative procedural shapes.
    box(length,.30,bodyWidth,0,.35,0);
    box(.55,.16,bodyWidth*.6,front+.12,.28,0);
    box(.15,.08,frontTrack+.2,front+.3,.19,0);
    box(.18,.08,rearTrack+.15,-rear-.2,.68,0);
    box(.48,.28,.48,-.08,.6,0,tires);
    box(.07,.48,.07,-.35,.68,-.30,metal); box(.07,.48,.07,-.35,.68,.30,metal);
    box(.07,.07,.66,-.35,.91,0,metal);
    const wheelGeometry=new THREE.CylinderGeometry(radius,radius,.22,16,1);
    const rimGeometry=new THREE.CylinderGeometry(radius*.55,radius*.55,.235,12,1);
    for (const [x,track] of [[front,frontTrack],[-rear,rearTrack]]) {
      for (const side of [-1,1]) {
        const wheel=new THREE.Mesh(wheelGeometry,tires); wheel.rotation.x=Math.PI/2;
        wheel.position.set(x,radius,side*track/2); group.add(wheel);
        const rim=new THREE.Mesh(rimGeometry,metal); rim.rotation.x=Math.PI/2;
        rim.position.copy(wheel.position); group.add(rim);
      }
    }
    group.traverse(node=>{if(node.isMesh)node.renderOrder=ghost?10+index:1;});
    group.userData={ghost,opacity,illustrativeBody:true,physicalModel:'unchanged planar telemetry',runId:null};
    return group;
  }

  function disposeTree(root) {
    const geometries=new Set(),materials=new Set();
    root.traverse(node=>{
      if(node.geometry)geometries.add(node.geometry);
      const list=Array.isArray(node.material)?node.material:[node.material];
      for(const material of list)if(material)materials.add(material);
    });
    for(const geometry of geometries)geometry.dispose();
    for(const material of materials)material.dispose();
  }

  class SceneModel {
    constructor() {
      this.scene=new THREE.Scene(); this.scene.background=new THREE.Color('#0c1420');
      this.scene.name='LapSim logged-telemetry scene';
      this.scene.add(new THREE.HemisphereLight('#c3ddff','#253b36',2));
      const sun=new THREE.DirectionalLight('#fff1d8',3); sun.position.set(12,30,18); this.scene.add(sun);
      this.perspective=new THREE.PerspectiveCamera(50,1,.1,10000);
      this.topDown=new THREE.OrthographicCamera(-10,10,10,-10,.1,10000);
      this.topDown.up.set(0,0,-1);
      this.root=new THREE.Group(); this.root.name='replay-objects'; this.scene.add(this.root);
      this.items=[];this.cars=[];this.traces=[];this.road=null;this.bounds=null;this.revision=0;this.disposed=false;
    }

    clear() {
      disposeTree(this.root); this.root.clear();
      this.items=[];this.cars=[];this.traces=[];this.road=null;this.bounds=null;this.revision++;
    }

    setRuns(items) {
      if(this.disposed)throw new Error('Scene has been disposed.');
      if(Array.isArray(items)&&items.length===this.items.length&&items.every((v,i)=>v.id===this.items[i].id&&v.run===this.items[i].run))return false;
      this.clear();
      sameConditions(items);
      if(!items.length)return true;
      const first=items[0].run, halfWidth=first.driver && first.driver.assumed_half_width_m;
      if(!finite(halfWidth)||halfWidth<=0||halfWidth>100)throw new Error('A declared finite assumed corridor width is required.');
      const road=roadGeometry(first.course,halfWidth);
      this.road=new THREE.Mesh(road.geometry,new THREE.MeshStandardMaterial({color:'#26374b',roughness:1,side:THREE.DoubleSide}));
      this.road.name='assumed-corridor';this.road.userData={assumedHalfWidthM:halfWidth,surveyed:false};
      this.root.add(this.road,lineFrom(road.left,'#7489a3'),lineFrom(road.right,'#7489a3'));
      const center=first.course.x_m.map((x,i)=>worldPosition(x,first.course.y_m[i],.014));
      const centerLine=lineFrom(center,'#48617b',.65);centerLine.name='saved-course-centerline';this.root.add(centerLine);
      const bounds=new THREE.Box3();
      for(const p of [...road.left,...road.right])bounds.expandByPoint(p);
      items.forEach((item,i)=>{
        const car=makeCar(item.run,COLORS[i],i);car.userData.runId=item.id;this.cars.push(car);this.root.add(car);
        const points=item.run.telemetry.map(row=>worldPosition(row.x_m,row.y_m,.025));
        for(const p of points)bounds.expandByPoint(p);
        const trace=lineFrom(points,COLORS[i],.65);trace.name='logged-trace-'+item.id;
        trace.userData={runId:item.id,sourceSampleCount:item.run.telemetry.length};this.traces.push(trace);this.root.add(trace);
      });
      bounds.expandByVector(new THREE.Vector3(2.2,1.5,2.2));this.bounds=bounds;
      const size=bounds.getSize(new THREE.Vector3()),centerOfBounds=bounds.getCenter(new THREE.Vector3());
      const ground=new THREE.Mesh(new THREE.PlaneGeometry(size.x*1.7,size.z*1.7),new THREE.MeshStandardMaterial({color:'#10202a',roughness:1}));
      ground.rotation.x=-Math.PI/2;ground.position.set(centerOfBounds.x,-.08,centerOfBounds.z);ground.name='illustrative-flat-ground';this.root.add(ground);
      const grid=new THREE.GridHelper(Math.max(size.x,size.z)*1.6,20,'#244258','#1b3040');
      grid.position.set(centerOfBounds.x,-.06,centerOfBounds.z);this.root.add(grid);
      this.items=items.slice();this.updatePoses(0);return true;
    }

    updatePoses(time) {
      this.items.forEach((item,i)=>{
        const pose=samplePose(item.run,time),car=this.cars[i];
        car.position.copy(worldPosition(pose.x_m,pose.y_m));car.rotation.y=pose.heading_rad;
        car.userData.pose=pose;car.userData.finished=pose.terminal;car.userData.status=item.run.status;
      });
      this.scene.updateMatrixWorld(true);
    }

    updateCamera(view,width,height) {
      if(!finite(width)||!finite(height)||width<=0||height<=0)throw new Error('Camera requires positive finite dimensions.');
      const mode=view.cameraMode || 'orbit';
      if(!['orbit','top','follow'].includes(mode))throw new Error('Unknown camera mode.');
      const aspect=width/height,zoom=clamp(finite(view.zoom)?view.zoom:1,.4,4);
      const bounds=this.bounds || new THREE.Box3(new THREE.Vector3(-5,0,-5),new THREE.Vector3(5,1,5));
      const size=bounds.getSize(new THREE.Vector3()),target=bounds.getCenter(new THREE.Vector3());target.y=.35;
      if(mode==='follow'&&this.cars.length)target.copy(this.cars[0].position).setY(.35);
      if(mode==='top') {
        const halfHeight=Math.max(size.z/2,size.x/(2*aspect))*1.08/zoom;
        const camera=this.topDown;
        camera.left=-halfHeight*aspect;camera.right=halfHeight*aspect;camera.top=halfHeight;camera.bottom=-halfHeight;
        camera.position.set(target.x,Math.max(size.x,size.z)*4+10,target.z);
        camera.far=Math.max(1000,camera.position.y-target.y+size.y+100);
        camera.lookAt(target);camera.updateProjectionMatrix();camera.updateMatrixWorld(true);return camera;
      }
      const camera=this.perspective;
      camera.aspect=aspect;
      const halfVertical=THREE.MathUtils.degToRad(camera.fov/2);
      const halfAngle=Math.min(halfVertical,Math.atan(Math.tan(halfVertical)*aspect));
      const radius=mode==='follow'?6:size.length()/2;
      const distance=radius*1.1/Math.sin(halfAngle)/zoom;
      const az=finite(view.azimuth)?view.azimuth:-.65,el=clamp(finite(view.elevation)?view.elevation:.9,.25,1.5);
      camera.position.set(target.x+distance*Math.cos(el)*Math.sin(az),target.y+distance*Math.sin(el),target.z+distance*Math.cos(el)*Math.cos(az));
      camera.far=Math.max(1000,distance+radius*3+100);
      camera.lookAt(target);camera.updateProjectionMatrix();camera.updateMatrixWorld(true);return camera;
    }

    dispose() {
      if(this.disposed)return;
      this.clear();this.scene.clear();this.disposed=true;
    }
  }

  class WebGLReplay {
    constructor(canvas,{rendererFactory,onStatus=()=>{}}={}) {
      this.canvas=canvas;this.model=new SceneModel();this.onStatus=onStatus;this.contextLost=false;this.lastSize=null;this.disposed=false;
      try {
        const options={canvas,antialias:true,alpha:false,depth:true,powerPreference:'default',preserveDrawingBuffer:false};
        this.renderer=rendererFactory?rendererFactory(options):new THREE.WebGLRenderer(options);
        this.renderer.outputColorSpace=THREE.SRGBColorSpace;
        this.renderer.debug.checkShaderErrors=true;
        this.renderer.debug.onShaderError=()=>{throw new Error('WebGL shader compilation/linking failed.');};
      } catch(error) {
        this.model.dispose();throw new Error('WebGL initialization failed: '+error.message);
      }
      this.lost=event=>{event.preventDefault();this.contextLost=true;onStatus('WebGL context lost. Select the labeled legacy view or reload.','error');};
      this.restored=()=>{this.contextLost=false;onStatus('WebGL context restored; awaiting a rendered frame.','pending');};
      canvas.addEventListener('webglcontextlost',this.lost);canvas.addEventListener('webglcontextrestored',this.restored);
    }

    render(items,time,view,width,height,dpr) {
      if(this.disposed)throw new Error('WebGL renderer has been disposed.');
      if(this.contextLost)throw new Error('WebGL context is unavailable; no renderer fallback was selected.');
      const viewport=viewportPolicy(width,height,dpr);
      if(viewport.suspended)return {rendered:false,...viewport};
      this.model.setRuns(items);this.model.updatePoses(time);
      const sizeKey=[viewport.width,viewport.height,viewport.pixelRatio].join(':');
      if(sizeKey!==this.lastSize){this.renderer.setPixelRatio(viewport.pixelRatio);this.renderer.setSize(viewport.width,viewport.height,false);this.lastSize=sizeKey;}
      const camera=this.model.updateCamera(view,viewport.width,viewport.height);
      this.renderer.render(this.model.scene,camera);
      const version=this.renderer.capabilities.isWebGL2?'WebGL2':'WebGL1';
      this.onStatus('Three.js r160 / '+version+' / '+viewport.bufferWidth+' x '+viewport.bufferHeight+' drawing buffer','ready');
      return {rendered:true,viewport,camera,scene:this.model.scene};
    }

    dispose() {
      if(this.disposed)return;
      this.canvas.removeEventListener('webglcontextlost',this.lost);this.canvas.removeEventListener('webglcontextrestored',this.restored);
      this.model.dispose();this.renderer.dispose();this.disposed=true;
    }
  }

  return Object.freeze({LIMITS,BREAKPOINTS,COLORS,layoutMode,viewportPolicy,cameraInput,
    validateRun,sameConditions,samplePose,worldPosition,roadGeometry,SceneModel,WebGLReplay});
}));
