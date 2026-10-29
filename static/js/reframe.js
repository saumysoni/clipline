// Reframe, the editor's tool for what of the wide vlog the 9:16 Short shows (web/reframe.py, pipeline/smart_reframe.py).
// While it's chosen, the player's place shows the vlog's picture at the playhead with the frame on it (drag it, zoom it)
// and, beside it, the Short as it will look, drawn live from the vlog's video. Layouts: Fill (the frame: one place, or
// moves over time that glide or cut; Follow the speaker makes the moves from the face), Fit (the whole picture over a
// blur), Split (two views stacked). Nothing is saved until the editor's Save (shortDetails() o.frame: one remake with the
// captions); Undo / Redo / Discard as every tool. Times are the vlog's seconds (cuts and trims never move a move).
// "Check with captions" asks the server for the exact frame (Captions' preview, with the hook and captions).
// Smart framing (Fill): Auto layout per shot (a new shot at each scene change: Fill on a face, else Fit, each one
// flippable), Track something (click it in the picture: the frame follows it from the playhead), Zoom on emphasis
// (punch-ins: in at a sentence's start or a word made to Pop in Captions, out at the next, Subtle / Punchy). They only
// write the settings (moves, shots, punch), so everything they do can be changed by hand.
const RF_PUNCH={subtle:0.08, punchy:0.16}, RF_PUNCH_GAP=2.5;  // how far in; seconds between punch-ins at least
function rfFraming(moves,t,cut,glide){  // pipeline/smart_reframe.py framing_at()
  if(!moves.length) return null;
  if(t<moves[0].t) return {...moves[0]};
  let k=0; while(k+1<moves.length && moves[k+1].t<=t) k++;
  const a=moves[k], b=moves[k+1];
  if(cut||!b||b.jump) return {...a};
  const s=Math.max(a.t,b.t-glide); if(t<=s) return {...a};
  let f=(t-s)/Math.max(1e-6,b.t-s); f=f*f*(3-2*f);
  return {t, x:a.x+(b.x-a.x)*f, y:a.y+(b.y-a.y)*f, z:a.z+(b.z-a.z)*f};
}
function rfWindow(W,H,v,aspect){  // window(): the part of the picture a frame shows, in its pixels
  let ch=H/v.z, cw=ch*aspect;
  if(cw>W){ cw=W/v.z; ch=cw/aspect; }
  return {l:Math.min(Math.max(v.x*W-cw/2,0),W-cw), t:Math.min(Math.max(v.y*H-ch/2,0),H-ch), w:cw, h:ch};
}
function reframeEdit(o){
  // o: box (the panel), stage (over the player), ae (AI Edit: pieces, info), caps (Captions: snap(), for the exact frame),
  // src() (the vlog's video, or the Short's clean clip, starting at the vlog second off()), at() (the playhead in vlog seconds), seek(t) (move the playhead there), onChange(), onLoad()
  let c=null, info=null, cur=null, gen=0, busy=false, shown=false, t=0, vid=null, vidSrc="", playing=false, raf=0;
  let pick="top", overTime=false, drag=null, note="", following=false, exact=null, exGen=0, tracking=false, smart="";
  const copy=x=>JSON.parse(JSON.stringify(x)), same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const changed=()=>o.onChange&&o.onChange();
  const off=()=>o.off?o.off():0, vt=()=>vid.currentTime+off();  // the video's place, in vlog seconds
  const dirty=()=>!!info && !same(cur, info.reframe);
  const can=()=>!!info && info.can_apply && !info.vertical && !busy && !(c&&c.remaking);
  const eff=()=>cur||{layout:"fill", moves:[], cut:false};
  const start=()=>{ const p=o.ae.pieces(); return p.length?p[0][0]:0; };
  const r2=v=>Math.round(v*100)/100, r4=v=>Math.round(v*10000)/10000;
  // The frame (Fill) at vlog time tt: the moves', else the one Pit Crew found (the face, full height)
  const frameAt=tt=>{ const e=eff(); return rfFraming(e.moves,tt,e.cut,info.glide) || {x:info.face, y:0.5, z:1}; };
  // what the Short shows at tt: the frame with a punch-in, and whether a Fit shot shows instead (pipeline punch_at, fit_at)
  const punchAt=tt=>{ const p=eff().punch; if(!p) return 1; const n=p.at.filter(a=>a<=tt).length; return n%2?1+p.amount:1; };
  const fitAt=tt=>{ const sh=eff().shots; if(!sh) return false; let f=false; sh.forEach(x=>{ if(x.t<=tt) f=x.fit; }); return f; };
  const viewAt=tt=>{ const f=frameAt(tt); return {...f, z:f.z*punchAt(tt)}; };
  const empty=n=>n.layout==="fill" && !n.moves.length && !(n.shots&&n.shots.some(x=>x.fit)) && !n.punch;
  function set(next, keepNote){
    if(!can()) return;
    exGen++;
    cur=next && empty(next) ? null : next;  // the server's rule (clean_reframe)
    if(!keepNote) note=""; exact=null; paint(); changed();
  }
  async function load(quiet){
    const my=++gen, cl=c, keep=quiet&&info;
    if(!keep){ info=null; cur=null; o.box.innerHTML='<p class="qr-wait">Getting the framing...</p>'; changed(); }
    let j; try{ const r=await fetch("/api/reframe/"+cl.job+"/"+cl.idx); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ if(my===gen && !keep) o.box.innerHTML='<p class="qr-wait">'+esc(e.message||"Couldn't load the framing. Check your internet connection, then try again.")+'</p>'; return; }
    if(my!==gen) return;
    info=j; cur=j.reframe?copy(j.reframe):null; overTime=!!(cur&&cur.moves.length>1);
    paint(); changed(); o.onLoad&&o.onLoad();
  }
  // ---- the panel
  function paint(){
    if(!info){ return; }
    const e=eff(), ed=can(), here=frameAt(t);
    const seg=(name,opts,val)=>'<div class="rf-seg" role="group" aria-label="'+name+'">'+opts.map(([v,label,icon,sub])=>
      '<button type="button" data-'+name.toLowerCase()+'="'+v+'" aria-pressed="'+(val===v)+'"'+(ed?'':' disabled')+'>'+
      (icon?'<span class="ms" aria-hidden="true">'+icon+'</span>':'')+'<b>'+label+'</b>'+(sub?'<small>'+sub+'</small>':'')+'</button>').join("")+'</div>';
    const zoom=(z,id)=>'<label class="rf-zoom"><span>Zoom</span><input type="range" id="'+id+'" min="1" max="'+info.zoom_max+'" step="0.05" value="'+z+'"'+(ed?'':' disabled')+
      '><output>'+(Math.round(z*10)/10)+'×</output></label>';
    let h='';
    if(!info.can_apply) h+='<div class="ed-note ae-warn">'+esc(info.why_not)+'</div>';
    if(info.vertical){ o.box.innerHTML='<p class="ae-help">This vlog is already vertical, so it fills the Short as it is. There\'s nothing to reframe.</p>'; stage(); return; }
    h+=seg("Layout",[["fill","Fill","crop_portrait","Crop to what matters"],["fit","Fit","fit_screen","All of the picture"],["split","Split","view_agenda","Two views stacked"]],e.layout);
    if(e.layout==="fill"){
      const busyAs=k=>smart===k;
      h+='<div class="rf-smart" role="group" aria-label="Smart framing">'+
        '<button type="button" class="ghost" id="rfAuto"'+(ed&&!smart?'':' disabled')+'><span class="ms" aria-hidden="true">auto_awesome</span>'+(busyAs("auto")?"Finding the shots...":"Auto layout per shot")+'</button>'+
        '<button type="button" class="ghost" id="rfFollow"'+(ed&&!smart?'':' disabled')+'><span class="ms" aria-hidden="true">face</span>'+(busyAs("follow")?"Following the speaker...":"Follow the speaker")+'</button>'+
        '<button type="button" class="ghost'+(tracking?' on':'')+'" id="rfTrack"'+(ed&&(!smart||tracking)?'':' disabled')+' aria-pressed="'+tracking+'"><span class="ms" aria-hidden="true">touch_app</span>'+
          (busyAs("track")?"Following it...":tracking?"Click it in the picture (or here to cancel)":"Track something")+'</button>'+
        '</div>';
      if(e.shots){
        const p=o.ae.pieces();
        h+='<div class="rf-shots"><div class="rf-shots-h"><b>Shots</b><button type="button" class="ghost sm" id="rfShotsOff"'+(ed?'':' disabled')+'>Fill them all</button></div>'+
          e.shots.map((x,k)=>{ const at=aeToFile(p,x.t), here=x.t<=t&&(!e.shots[k+1]||e.shots[k+1].t>t);
            return '<div class="rf-shot'+(here?' on':'')+'"><button type="button" class="rf-go" data-shotgo="'+k+'">'+(at!=null?fmt(at):'<i>cut out</i>')+'</button>'+
            '<span class="rf-seg mini" role="group" aria-label="Shot '+(k+1)+'"><button type="button" data-shot="'+k+'" data-fit="0" aria-pressed="'+!x.fit+'"'+(ed?'':' disabled')+'>Fill</button>'+
            '<button type="button" data-shot="'+k+'" data-fit="1" aria-pressed="'+x.fit+'"'+(ed?'':' disabled')+'>Fit</button></span></div>'; }).join("")+'</div>';
      }
      const lvl=e.punch?(e.punch.amount>=RF_PUNCH.punchy-0.001?"punchy":"subtle"):"off";
      h+='<div class="rf-lab">Zoom on emphasis <small>in at a sentence or a word that Pops, out at the next</small></div>'+
        seg("Punch",[["off","Off"],["subtle","Subtle"],["punchy","Punchy"]],lvl);
      h+=zoom(r2(here.z),"rfZoom")+(info.zoom_max<2.4?'<p class="ae-help">This vlog is low resolution, so the zoom stops at '+info.zoom_max+'× (any further would look soft).</p>':'');
      h+='<label class="rf-check"><input type="checkbox" id="rfOver"'+(overTime?' checked':'')+(ed?'':' disabled')+'><span><b>Moves over time</b>'+
        '<small>Drag the frame at a moment (move the playhead on the timeline): it moves there then.</small></span></label>';
      if(overTime){
        const p=o.ae.pieces();
        h+=seg("Moves",[["glide","Glide"],["cut","Cut"]],e.cut?"cut":"glide");
        h+='<div class="rf-moves">'+(e.moves.length?e.moves.map((m,k)=>{ const at=aeToFile(p,m.t);
          return '<div class="rf-move'+(Math.abs(m.t-t)<0.15?' on':'')+'"><button type="button" class="rf-go" data-go="'+k+'" title="Go there">'+
            (at!=null?fmt(at):'<i>cut out</i>')+'</button><span>'+(m.x<0.4?"Left":m.x>0.6?"Right":"Middle")+(m.z>1.01?' · '+Math.round(m.z*10)/10+'×':'')+'</span>'+
            '<button type="button" class="iconbtn" data-rm="'+k+'" aria-label="Remove this move" title="Remove"'+(ed?'':' disabled')+'><span class="ms" aria-hidden="true">close</span></button></div>'; }).join("")
          :'<p class="ae-help">No moves yet: drag the frame on the picture.</p>')+'</div>';
      }
    }
    if(e.layout==="split"){
      const v=e[pick]||{};
      h+=seg("View",[["top","Top view"],["bottom","Bottom view"]],pick)+zoom(v.z||1,"rfZoom");
    }
    if(e.layout==="fit") h+='<p class="ae-help">The whole picture across the Short, with a blurred copy of it above and below.</p>';
    h+='<div class="rf-acts"><button type="button" class="ghost" id="rfPlay"'+(o.src()?'':' disabled')+'><span class="ms" aria-hidden="true">'+(playing?"pause":"play_arrow")+'</span>'+(playing?"Pause":"Play it")+'</button>'+
      '<button type="button" class="ghost" id="rfExact"'+(info.can_apply?'':' disabled')+'><span class="ms" aria-hidden="true">visibility</span>Check with captions</button></div>';
    if(cur) h+='<button type="button" class="ghost sm rf-reset" id="rfReset"'+(ed?'':' disabled')+'>Back to Pit Crew\'s framing</button>';
    h+='<p class="rf-note" role="status">'+esc(note)+'</p>';
    h+='<p class="ae-help">'+(e.layout==="fit"?'':'Drag the frame on the picture to choose what the Short shows'+(e.layout==="split"?' in each view.':'; the picture on the right is the Short.'))+' Nothing changes until you save.</p>';
    if(setHTML(o.box,h)) wire();
    stage();
  }
  function wire(){
    const q=s=>o.box.querySelector(s);
    o.box.querySelectorAll("[data-layout]").forEach(b=>b.onclick=()=>{
      const l=b.dataset.layout, e=eff();
      set(l==="split"?{layout:"split", moves:[], cut:false, top:e.top||{x:0.3,y:0.5,z:1}, bottom:e.bottom||{x:0.7,y:0.5,z:1}}:
          l==="fit"?{layout:"fit", moves:[], cut:false}:{layout:"fill", moves:e.layout==="fill"?e.moves:[], cut:e.cut});
    });
    o.box.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{ pick=b.dataset.view; paint(); });
    o.box.querySelectorAll("[data-moves]").forEach(b=>b.onclick=()=>set({...eff(), cut:b.dataset.moves==="cut"}));
    o.box.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>o.seek(eff().moves[+b.dataset.go].t));
    o.box.querySelectorAll("[data-rm]").forEach(b=>b.onclick=()=>{ const e=eff(); set({...e, moves:e.moves.filter((m,k)=>k!==+b.dataset.rm)}); });
    const z=q("#rfZoom");
    if(z){
      z.oninput=()=>{ z.nextElementSibling.textContent=(Math.round(z.value*10)/10)+"×"; drag={zoom:+z.value}; stage(); };
      z.onchange=()=>{ drag=null; place({z:+z.value}); };
    }
    const ov=q("#rfOver");
    if(ov) ov.onchange=()=>{
      overTime=ov.checked;
      if(!overTime){ const f=frameAt(t); set({...eff(), moves:[{t:r2(start()), x:r4(f.x), y:r4(f.y), z:r2(f.z)}]}); }  // one frame: as it is here
      else paint();
    };
    if(q("#rfFollow")) q("#rfFollow").onclick=follow;
    if(q("#rfAuto")) q("#rfAuto").onclick=auto;
    if(q("#rfTrack")) q("#rfTrack").onclick=()=>{ tracking=!tracking; note=tracking?"Click what the frame should follow, in the picture on the left. It follows it from the playhead on.":""; paint(); };
    if(q("#rfShotsOff")) q("#rfShotsOff").onclick=()=>{ const e={...eff()}; delete e.shots; set(e); };
    o.box.querySelectorAll("[data-shot]").forEach(b=>b.onclick=()=>{ const e=eff(), k=+b.dataset.shot;
      set({...e, shots:e.shots.map((x,j)=>j===k?{...x, fit:b.dataset.fit==="1"}:x)}); });
    o.box.querySelectorAll("[data-shotgo]").forEach(b=>b.onclick=()=>o.seek(eff().shots[+b.dataset.shotgo].t+0.05));
    o.box.querySelectorAll("[data-punch]").forEach(b=>b.onclick=()=>{ const e={...eff()}, v=b.dataset.punch;
      if(v==="off"){ delete e.punch; set(e); return; }
      const at=punchTimes(); if(!at.length){ note="No sentences to zoom on in this Short yet."; paint(); return; }
      set({...e, punch:{amount:RF_PUNCH[v], at}}, true); note=at.length+" punch-ins: in at the first, out at the next. Play it to see them."; paint(); });
    q("#rfPlay").onclick=()=>playing?stop():play();
    q("#rfExact").onclick=exactFrame;
    if(q("#rfReset")) q("#rfReset").onclick=()=>{ overTime=false; set(null); };
  }
  // A new place for the frame (Fill: the one frame, or a move at the playhead; Split: the view picked)
  function place(p){
    const e=eff();
    if(e.layout==="split"){ set({...e, [pick]:{...e[pick], ...p}}); return; }
    if(e.layout!=="fill") return;
    const f={...frameAt(t), ...p}, m={t:r2(overTime?t:start()), x:r4(f.x), y:r4(f.y), z:r2(f.z)};
    if(!overTime){ set({...e, moves:[m]}); return; }
    const moves=e.moves.filter(x=>Math.abs(x.t-m.t)>=0.15).concat([m]).sort((a,b)=>a.t-b.t);
    set({...e, moves});
  }
  // Zoom on emphasis: where a sentence starts (after a pause or a full stop) or a word Pops (Captions), RF_PUNCH_GAP apart
  function punchTimes(){
    const ai=o.ae.info(); if(!ai) return [];
    const keep=o.ae.pieces(), ws=ai.words.filter(w=>aeIn(keep,(w.s+w.e)/2));
    const pops=new Set(((o.caps.snap&&o.caps.snap())||{}).pop||[]), out=[]; let last=-1e9;
    ws.forEach((w,k)=>{ const prev=ws[k-1], starts=!prev || w.s-prev.e>0.45 || /[.!?]["')]?$/.test(prev.w);
      if((starts||pops.has(w.i)) && w.s-last>=RF_PUNCH_GAP){ out.push(r2(w.s)); last=w.s; } });
    return out;
  }
  async function smartCall(kind, body){
    smart=kind; note=""; paint();
    let j={}; try{ const r=await fetch("/api/reframe/"+c.job+"/"+c.idx+"/"+kind,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({pieces:o.ae.pieces(), ...body})}); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ smart=""; note=e.message||"Couldn't reach Pit Crew. Check your internet connection, then try again."; paint(); return null; }
    smart=""; return j;
  }
  async function auto(){
    if(!can()) return;
    const j=await smartCall("auto",{}); if(!j) return;
    if(!j.shots.length){ note=j.note; paint(); return; }
    const fits=j.shots.filter(x=>x.fit).length, e=eff();
    overTime=true;
    note=j.shots.length+" shot"+(j.shots.length>1?"s":"")+": "+(j.shots.length-fits)+" framed on a face, "+fits+" shown whole. Flip any of them below.";
    set({layout:"fill", moves:j.moves, cut:false, shots:j.shots, ...(e.punch?{punch:e.punch}:{})}, true);
  }
  async function track(x, y){
    tracking=false;
    const at=t, j=await smartCall("track",{at, x, y, z:frameAt(t).z}); if(!j) return;
    if(j.moves.length<2){ note=j.note; paint(); return; }
    const e=eff(), keep=e.moves.filter(m=>m.t<at-0.05 || m.t>j.until+0.05);
    overTime=true; note="Following it for "+Math.round(j.until-at)+" s. Drag the frame at any moment to change it.";
    set({...e, layout:"fill", moves:keep.concat(j.moves).sort((a,b)=>a.t-b.t)}, true);
  }
  async function follow(){
    if(!can()) return;
    following=true; smart="follow"; note=""; paint();
    const z=frameAt(t).z;
    let j={}; try{ const r=await fetch("/api/reframe/"+c.job+"/"+c.idx+"/follow",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({pieces:o.ae.pieces(), z})}); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ following=false; smart=""; note=e.message||"Couldn't reach Pit Crew. Check your internet connection, then try again."; paint(); return; }
    following=false; smart="";
    if(!j.moves.length){ note=j.note; paint(); return; }
    overTime=j.moves.length>1; note=j.moves.length>1?"Following the speaker: "+j.moves.length+" moves. Drag the frame at any moment to change one.":"The speaker stays in one place: the frame is on them.";
    const e=eff(); set({...e, layout:"fill", moves:j.moves, cut:e.cut}, true);
  }
  async function exactFrame(){
    const ask=++exGen; const b=o.box.querySelector("#rfExact"); if(b) b.disabled=true;
    try{
      const body={captions:o.caps.snap(), at:t, reframe:cur};
      if(JSON.stringify(o.ae.pieces())!==JSON.stringify(o.ae.saved())) body.pieces=o.ae.pieces();
      const r=await fetch("/api/captions/"+c.job+"/"+c.idx+"/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      if(!r.ok) throw new Error((await r.json().catch(()=>({}))).error||"");
      if(ask!==exGen) return;
      exact=URL.createObjectURL(await r.blob()); note="The exact frame, with the hook and captions. Change anything to go back to the live picture.";
    }catch(e){ note=e.message||"Couldn't draw that frame. Try again."; }
    if(b) b.disabled=false; paint();
  }
  // ---- the stage: the vlog's picture with the frame(s) on it, and the Short as it'll look
  function video(){
    const src=o.src(); if(!src) return null;
    if(src!==vidSrc){ vidSrc=src; vid=document.createElement("video"); vid.muted=true; vid.preload="auto"; vid.playsInline=true; vid.src=src;
      vid.addEventListener("seeked",()=>draw()); vid.addEventListener("loadeddata",()=>{ vid.currentTime=Math.max(0,t-off()); }); }
    return vid;
  }
  function stage(){
    const el=o.stage; if(!shown||!info){ return; }
    if(!el.querySelector(".rf-stage")){
      el.innerHTML='<div class="rf-stage"><div class="rf-src"><canvas class="rf-pic"></canvas><div class="rf-boxes"></div></div>'+
        '<div class="rf-out"><canvas class="rf-res" width="270" height="480"></canvas><img class="rf-exact" alt="The Short at this moment, with captions" hidden></div></div>';
      wireStage(el.querySelector(".rf-src"));
      new ResizeObserver(()=>{ if(shown&&info){ layout(); draw(); } }).observe(el);
    }
    layout();
    const e=eff(), boxes=el.querySelector(".rf-boxes"), ed=can()&&e.layout!=="fit";
    const whole=e.layout==="fit" || (e.layout==="fill" && fitAt(t));
    const views=e.layout==="split"?[["top",e.top,9/8],["bottom",e.bottom,9/8]]:whole?[]:[["fill",viewAt(t),9/16]];
    if(drag&&drag.zoom!=null) views.forEach(v=>{ if(v[0]===(e.layout==="split"?pick:"fill")) v[1]={...v[1], z:drag.zoom}; });
    if(drag&&drag.view) views.forEach(v=>{ if(v[0]===drag.view) v[1]={...v[1], x:drag.x, y:drag.y}; });
    setHTML(boxes, views.map(([k,v,a])=>{ const w=rfWindow(info.width,info.height,v,a);
      return '<div class="rf-box'+(k===pick||k==="fill"?' on':'')+(ed?'':' ro')+'" data-view="'+k+'" style="left:'+(w.l/info.width*100).toFixed(3)+'%;top:'+(w.t/info.height*100).toFixed(3)+
        '%;width:'+(w.w/info.width*100).toFixed(3)+'%;height:'+(w.h/info.height*100).toFixed(3)+'%">'+(k==="fill"?'':'<span>'+(k==="top"?"Top":"Bottom")+'</span>')+'</div>'; }).join(""));
    el.querySelector(".rf-src").classList.toggle("fit", whole);
    el.querySelector(".rf-src").classList.toggle("tracking", tracking);
    const img=el.querySelector(".rf-exact");
    if(exact){ img.src=exact; img.hidden=false; } else img.hidden=true;
    const v=video(); if(v && v.readyState>=1 && Math.abs(vt()-t)>0.04 && !playing) v.currentTime=Math.max(0,t-off());
    draw();
  }
  // Both pictures as big as the player's place allows: the Short full height, the vlog's picture in the rest.
  function layout(){
    const el=o.stage, W=el.clientWidth-28, H=el.clientHeight-28; if(W<=0||H<=0) return;
    const ow=Math.round(H*9/16), a=info.width/info.height, sw=Math.max(80,Math.min(W-16-ow, H*a)), sh=sw/a;
    const out=el.querySelector(".rf-out"), src=el.querySelector(".rf-src");
    out.style.width=ow+"px"; out.style.height=H+"px"; src.style.width=Math.round(sw)+"px"; src.style.height=Math.round(sh)+"px";
  }
  function wireStage(src){
    src.addEventListener("pointerdown",ev=>{
      if(tracking && can() && ev.button===0){  // Track something: what's under the click
        ev.preventDefault(); const r=src.getBoundingClientRect();
        track(Math.min(1,Math.max(0,(ev.clientX-r.left)/r.width)), Math.min(1,Math.max(0,(ev.clientY-r.top)/r.height))); return;
      }
      const b=ev.target.closest(".rf-box"); if(!b || !can() || ev.button!==0) return;
      ev.preventDefault();
      const r=src.getBoundingClientRect(), e=eff(), k=b.dataset.view, v=k==="fill"?frameAt(t):e[k];
      if(k!=="fill") pick=k;
      drag={view:k, x0:ev.clientX, y0:ev.clientY, fx:v.x, fy:v.y, x:v.x, y:v.y, r, id:ev.pointerId};
      src.setPointerCapture(ev.pointerId); src.classList.add("dragging");
    });
    src.addEventListener("pointermove",ev=>{
      if(!drag||!drag.view||ev.pointerId!==drag.id) return;
      drag.x=Math.min(1,Math.max(0,drag.fx+(ev.clientX-drag.x0)/drag.r.width));
      drag.y=Math.min(1,Math.max(0,drag.fy+(ev.clientY-drag.y0)/drag.r.height));
      // the frame stops at the picture's edges: keep the numbers where it stops (so dragging back moves it at once)
      const e=eff(), v=drag.view==="fill"?frameAt(t):e[drag.view], a=drag.view==="fill"?9/16:9/8;
      const w=rfWindow(info.width,info.height,{...v,x:drag.x,y:drag.y},a);
      drag.x=(w.l+w.w/2)/info.width; drag.y=(w.t+w.h/2)/info.height;
      stage();
    });
    const end=ev=>{ if(!drag||!drag.view) return; const d=drag; drag=null; src.classList.remove("dragging");
      if(ev.type==="pointercancel"){ stage(); return; }
      if(Math.abs(d.x-d.fx)<1e-4 && Math.abs(d.y-d.fy)<1e-4){ stage(); return; }
      if(d.view!=="fill") pick=d.view;
      place({x:d.x, y:d.y}); };
    src.addEventListener("pointerup",end); src.addEventListener("pointercancel",end);
  }
  function draw(){
    const el=o.stage, cv=el.querySelector(".rf-pic"), rc=el.querySelector(".rf-res"), v=vid; if(!cv||!info) return;
    const W=cv.clientWidth*(window.devicePixelRatio||1)|0, H=cv.clientHeight*(window.devicePixelRatio||1)|0;
    if(W&&H&&(cv.width!==W||cv.height!==H)){ cv.width=W; cv.height=H; }
    const RW0=rc.clientWidth*(window.devicePixelRatio||1)|0, RH0=rc.clientHeight*(window.devicePixelRatio||1)|0;
    if(RW0&&RH0&&(rc.width!==RW0||rc.height!==RH0)){ rc.width=RW0; rc.height=RH0; }
    const g=cv.getContext("2d"), out=rc.getContext("2d");
    g.fillStyle="#111"; g.fillRect(0,0,cv.width,cv.height); out.fillStyle="#111"; out.fillRect(0,0,rc.width,rc.height);
    if(!v||v.readyState<2||!v.videoWidth) return;
    g.drawImage(v,0,0,cv.width,cv.height);
    const k=v.videoWidth/info.width, e=eff(), at=playing?vt():t, RW=rc.width, RH=rc.height;
    const crop=(view,a,dy,dh)=>{ const w=rfWindow(info.width,info.height,view,a); out.drawImage(v,w.l*k,w.t*k,w.w*k,w.h*k,0,dy,RW,dh); };
    if(e.layout==="fit" || (e.layout==="fill" && fitAt(at))){
      out.save(); out.filter="blur(10px) brightness(.88)"; const s=Math.max(RW/v.videoWidth,RH/v.videoHeight);
      out.drawImage(v,(RW-v.videoWidth*s)/2,(RH-v.videoHeight*s)/2,v.videoWidth*s,v.videoHeight*s); out.restore();
      const h=RW*v.videoHeight/v.videoWidth; out.drawImage(v,0,(RH-h)/2,RW,h);
    } else if(e.layout==="split"){
      const tv={...e.top}, bv={...e.bottom};
      if(drag&&drag.view==="top"){ tv.x=drag.x; tv.y=drag.y; } if(drag&&drag.view==="bottom"){ bv.x=drag.x; bv.y=drag.y; }
      if(drag&&drag.zoom!=null){ (pick==="top"?tv:bv).z=drag.zoom; }
      crop(tv,9/8,0,RH/2); crop(bv,9/8,RH/2,RH/2);
    } else {
      let f=viewAt(at); if(drag&&drag.view==="fill"){ f={...f, x:drag.x, y:drag.y}; } if(drag&&drag.zoom!=null) f={...f, z:drag.zoom};
      crop(f,9/16,0,RH);
    }
  }
  // Play it: the vlog's video through the parts the Short keeps (the cuts waiting too), the frame moving with it
  function play(){
    const v=video(); if(!v) return;
    const p=o.ae.pieces(); if(!p.length) return;
    let k=p.findIndex(([a,b])=>t>=a&&t<b-0.1); if(k<0){ k=0; t=p[0][0]; }
    v.currentTime=Math.max(0,t-off()); playing=true; exact=null; paint(); let t0=t;
    v.play().catch(()=>{});
    const tick=()=>{
      if(!playing) return;
      const now=vt();
      if(now>=p[k][1]){ k++; if(k>=p.length){ stop(); return; } v.currentTime=Math.max(0,p[k][0]-off()); }
      t=now; const boxes=o.stage.querySelector(".rf-boxes");
      if(eff().layout==="fill" && fitAt(now)!==fitAt(t0)){ t0=now; t=now; stage(); }
      if(eff().layout==="fill" && boxes && boxes.firstChild){ const w=rfWindow(info.width,info.height,viewAt(now),9/16);
        boxes.firstChild.style.left=(w.l/info.width*100).toFixed(3)+"%"; boxes.firstChild.style.top=(w.t/info.height*100).toFixed(3)+"%";
        boxes.firstChild.style.width=(w.w/info.width*100).toFixed(3)+"%"; boxes.firstChild.style.height=(w.h/info.height*100).toFixed(3)+"%"; }
      draw(); raf=requestAnimationFrame(tick);
    };
    raf=requestAnimationFrame(tick);
  }
  function stop(){ playing=false; cancelAnimationFrame(raf); if(vid) vid.pause(); if(info) paint(); }
  const api={
    open(clip){ c=clip; busy=false; stop(); t=0; note=""; exact=null; return load(); },
    clear(){ c=null; info=null; cur=null; gen++; busy=false; stop(); o.box.innerHTML=""; o.stage.innerHTML=""; changed(); },
    follow(clip){
      const was=c; c=clip;
      if(!info) return;
      if(busy && !clip.remaking && was && was.video!==clip.video){ busy=false; if(!dirty()) load(true); else paint(); return; }
      if(!!(was&&was.remaking)!==!!clip.remaking) paint();
    },
    shown(on){ shown=on; if(!on){ stop(); return; } t=o.at(); stage(); paint(); },
    // the playhead moved (vlog seconds): the picture and the frame there
    at(tt){ if(tt==null||playing) return; if(Math.abs(tt-t)<0.01) return; t=tt; if(shown&&info){ exact=null; paint(); } },
    name:"framing", dirty, count:()=>dirty()?1:0, canEdit:can,
    summary:()=>{ if(!info) return ""; const e=eff(); return !cur?"Pit Crew's framing":e.layout==="fit"?"Fit":e.layout==="split"?"Split":e.shots?"Auto layout":e.moves.length>1?e.moves.length+" moves":"Your framing"; },
    snap:()=>info?{r:cur?copy(cur):null, over:overTime}:null,
    restore(x){ if(!info||!x) return; cur=x.r?copy(x.r):null; overTime=x.over; exact=null; paint(); changed(); },
    reset(){ if(info){ cur=info.reframe?copy(info.reframe):null; overTime=!!(cur&&cur.moves.length>1); exact=null; note=""; paint(); changed(); } },
    step:remake=>["/api/reframe/"+c.job+"/"+c.idx,{reframe:cur, remake}],
    sent(remake){ info.reframe=cur?copy(cur):null; if(remake) busy=true; paint(); changed(); },
    time:()=>t,
    // for Trim's big preview: the frame (Fill) at vlog time tt, null for the whole picture; the vlog's picture size
    cropAt:tt=>{ if(!info||info.vertical) return null; return eff().layout==="fill" && !fitAt(tt) ? viewAt(tt) : null; },
    size:()=>info?{width:info.width, height:info.height}:{width:0, height:0},
  };
  return api;
}
