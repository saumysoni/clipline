// The editor's Video row (js/editor.js), on one fixed scale (nothing to scroll or zoom). Under every tool but Trim it shows
// only the Short, because the vlog around it can't be used there. Under Trim it also shows the vlog around the Short, dimmed,
// to reach into. Times are the Short's own: 0:00 is where the saved Short starts (as the player counts), earlier is −.
// The playhead has a handle: drag it, or the times above the row, to move through the video. A click moves it too (a moment the
// saved video hasn't got shows big instead); there's no cut mode. Outside Trim a drag on the pictures moves it as well. Under Trim, a
// drag across the row makes the yellow box of the part to cut out. Then drag its ends to stretch or narrow it, drag inside it to
// move it (snapping to the gaps between words; Alt / Option: freely), or drag elsewhere for a new one; Esc or Clear removes it.
// Cut it out takes it out of the Short (then a preview plays without it): cut parts are blurred and striped red ("cut"), unlike
// the vlog around the Short (dimmed). The Short's own two ends have grips: drag them out into the vlog around it to
// add it, or in to shorten it. While dragging, the player's place shows that moment big (trimView, below); never just from
// pointing at the row, which would cover the player and its controls.
// Changes go to o.commit(pieces) (AI Edit's pieces: one Undo, one Save with the other tools).
const TS_SNAP=8, TS_EDGE=14, TS_MIN_SEL=0.3, TS_MARGIN=30, TS_DRAG=4;  // px, px, s, s, px (a press that moves less is a click)
const tsClock=(d,tenths)=>{ const s=Math.abs(d), m=Math.floor(s/60), r=s-m*60;
  return (d<-0.05?"−":"")+m+":"+(r<10?"0":"")+(tenths?r.toFixed(1):Math.floor(r)); };
function trimStrip(o){
  // o: box, pieces(), info() (AI Edit's: start, end, duration, min, max), origin() (vlog seconds of the Short's 0:00),
  // trim() (the Trim tool is on), canEdit(), snaps(side), src() (the vlog's video, or the Short's clean clip, which starts at
  // the vlog second off()), now() (the playhead, vlog s, or null),
  // seek(t), hover(t | null) (the pointer over the row), onSel() (the selection changed), saved() (the saved Short's
  // pieces: what's cut is what they had and these don't), commit(pieces) (a Short end dragged)
  const box=o.box;
  let win=null, winFor="", on=false, sel=null, drag=null, vid=null, vidSrc="", frames=new Map(), drawing=false, want=0;
  const r3=v=>+v.toFixed(3);
  const W=()=>box.querySelector(".ts-film").clientWidth||1;
  const pps=()=>W()/Math.max(0.1,win.b-win.a);
  const x=t=>(t-win.a)*pps();
  const pc=t=>((t-win.a)/(win.b-win.a)*100).toFixed(3)+"%";
  const rel=t=>t-o.origin();
  function frame(p){
    const info=o.info(), dur=info.duration||p[p.length-1][1];
    if(!o.trim()){  // only the Short: its parts, and what was cut from inside it
      const sv=(o.saved&&o.saved())||p;
      return {a:Math.min(sv[0][0],p[0][0]), b:Math.max(sv[sv.length-1][1],p[p.length-1][1])};
    }
    // Under Trim: the saved Short and TS_MARGIN either side, on a scale that doesn't move while it's stretched. A Short saved
    // longer gets TS_MARGIN either side again.
    const sv=(o.saved&&o.saved())||p, [r0,r1]=info.reach||[0,dur];
    return {a:Math.max(0,r0,Math.min(sv[0][0]-TS_MARGIN,p[0][0])), b:Math.min(dur,r1,Math.max(sv[sv.length-1][1]+TS_MARGIN,p[p.length-1][1]))};
  }
  function paint(){
    const info=o.info(), p=o.pieces();
    if(!on) return;
    if(!info || !p.length){ box.innerHTML='<p class="ed-tl-msg">Getting the parts of this Short...</p>'; win=null; return; }
    const key=JSON.stringify([info.start,info.end,info.duration]);
    if(key!==winFor){ winFor=key; win=null; sel=null; frames=new Map(); }
    const was=win&&win.a+":"+win.b; win=frame(p);
    if(!box.querySelector(".ts")){
      box.innerHTML='<div class="ts" role="group" aria-label="The video: the Short and the video around it">'+
        '<div class="ts-ticks" aria-hidden="true"></div>'+
        '<div class="ts-film"><canvas class="ts-pics" aria-hidden="true"></canvas><div class="ts-dims"></div><div class="ts-sel" hidden><i class="s"></i><i class="e"></i></div>'+
        '<div class="ts-hover" hidden></div><div class="ts-head" aria-hidden="true"><i class="ts-knob" title="Drag to move through the video"></i></div><div class="ts-tip" hidden></div></div></div>';
      wire();
    }
    const ts=box.querySelector(".ts");
    ts.classList.toggle("trim", o.trim()); ts.classList.toggle("ro", !o.canEdit());
    if(was!==win.a+":"+win.b) ticks();
    dims(p); marks(); follow(); pics();
  }
  function ticks(){
    const span=win.b-win.a, step=[1,2,5,10,15,30,60,120,300].find(s=>span/s<=10)||600, out=[], o0=o.origin();
    for(let t=o0+Math.ceil((win.a-o0)/step)*step; t<=win.b; t+=step) out.push('<span style="left:'+pc(t)+'">'+tsClock(t-o0)+'</span>');
    box.querySelector(".ts-ticks").innerHTML=out.join("");
  }
  // What the Short leaves out: cut by the creator (inside the saved Short: blurred, striped, "cut") or the vlog around it
  // (dimmed); a thin edge round each part it keeps; under Trim, grips on the Short's two ends.
  function dims(p){
    const out=[]; let at=win.a;
    for(const [a,b] of p){ if(a>at+0.01) out.push([at,a]); at=Math.max(at,b); }
    if(at<win.b-0.01) out.push([at,win.b]);
    const sv=(o.saved&&o.saved())||p, sa=sv[0][0], sb=sv[sv.length-1][1], seg=[];
    for(const [a,b] of out){  // split each left-out stretch at the saved Short's ends
      const cuts=[[a,Math.min(b,sa),"dim"],[Math.max(a,sa),Math.min(b,sb),"cut"],[Math.max(a,sb),b,"dim"]];
      cuts.forEach(([u,v,k])=>{ if(v>u+0.01) seg.push([u,v,k]); });
    }
    const grips=o.trim()&&o.canEdit()?'<div class="ts-grip s" style="left:'+pc(p[0][0])+'" title="Drag to start the Short earlier or later"></div>'+
      '<div class="ts-grip e" style="left:'+pc(p[p.length-1][1])+'" title="Drag to end the Short earlier or later"></div>':'';
    // Added: kept now, but not in the saved Short (it was stretched into the vlog, not saved yet): the lightest green.
    const added=[];
    for(const [a,b] of p){
      let at2=a;
      for(const [u,v] of sv){ if(v<=at2||u>=b) continue; if(u>at2+0.01) added.push([at2,u]); at2=Math.max(at2,v); }
      if(at2<b-0.01) added.push([at2,b]);
    }
    setHTML(box.querySelector(".ts-dims"), added.map(([a,b])=>'<div class="ts-add" style="left:'+pc(a)+';width:calc('+pc(b)+' - '+pc(a)+')"></div>').join("")+seg.map(([a,b,k])=>'<div class="ts-'+k+'" style="left:'+pc(a)+';width:calc('+pc(b)+' - '+pc(a)+')">'+
        (k==="cut"&&x(b)-x(a)>34?'<span>cut</span>':'')+'</div>').join("")+
      p.map(([a,b])=>'<div class="ts-keep" style="left:'+pc(a)+';width:calc('+pc(b)+' - '+pc(a)+')"></div>').join("")+grips);
  }
  function marks(){
    const s=box.querySelector(".ts-sel");
    s.hidden=!sel; if(sel){ s.style.left=pc(sel.a); s.style.width="calc("+pc(sel.b)+" - "+pc(sel.a)+")"; }
  }
  function follow(){
    const h=box.querySelector(".ts-head"); if(!h||!win) return;
    const t=o.now(); h.hidden=t==null||t<win.a||t>win.b;
    if(!h.hidden) h.style.left=pc(t);
  }
  // The pictures: one frame per cell from the vlog's video on one canvas (a hidden <video>, seeking one at a time).
  function pics(){
    const cv=box.querySelector(".ts-pics"), src=o.src(); if(!cv||!src) return;
    if(src!==vidSrc){
      vidSrc=src; frames=new Map(); if(vid) vid.removeAttribute("src");
      vid=document.createElement("video"); vid.muted=true; vid.preload="metadata"; vid.playsInline=true; vid.src=src;
      vid.addEventListener("loadedmetadata",()=>pics(),{once:true});
    }
    const dpr=window.devicePixelRatio||1, w=Math.round(W()*dpr), h=Math.round(cv.clientHeight*dpr)||1;
    if(cv.width!==w||cv.height!==h){ cv.width=w; cv.height=h; }
    want++; draw();
  }
  async function draw(){
    if(drawing) return; drawing=true;
    try{
      while(true){
        const cv=box.querySelector(".ts-pics"); if(!cv||!vid||!vid.videoWidth||!win) break;
        // cells a little wider than tall (the middle of each frame): more pictures across a zoomed-out row
        const ask=want, g=cv.getContext("2d"), cw=Math.max(8,Math.round(cv.height*1.1)), cells=Math.ceil(cv.width/cw);
        const span=win.b-win.a, at=k=>win.a+(k+0.5)*cw/cv.width*span, todo=[];
        const sw=Math.min(vid.videoWidth, vid.videoHeight*1.1), sx=(vid.videoWidth-sw)/2;
        const put=(f,k)=>g.drawImage(f,k*cw,0,cw,cv.height);
        g.fillStyle="#111"; g.fillRect(0,0,cv.width,cv.height);
        for(let k=0;k<cells;k++){ const t=Math.round(at(k)*2)/2, f=frames.get(t); if(f) put(f,k); else todo.push([k,t]); }
        todo.sort((u,v)=>Math.abs(u[1]-o.origin())-Math.abs(v[1]-o.origin()));  // the Short first, then outwards
        for(const [k,t] of todo){
          if(ask!==want) break;
          if(!frames.has(t)){
            await new Promise(res=>{ const done=()=>{ clearTimeout(tm); vid.removeEventListener("seeked",done); res(); }, tm=setTimeout(done,3000);
              vid.addEventListener("seeked",done); vid.currentTime=Math.max(0,Math.min(t-(o.off?o.off():0),(vid.duration||t+1)-0.05)); });
            const c=document.createElement("canvas"); c.width=cw; c.height=cv.height;
            try{ c.getContext("2d").drawImage(vid,sx,0,sw,vid.videoHeight,0,0,cw,cv.height); frames.set(t,c); }catch(e){ break; }
          }
          if(ask===want) put(frames.get(t),k);
        }
        if(ask===want) break;
      }
    } finally { drawing=false; }
  }
  // Where the pointer is, in vlog seconds (inside the row), snapped to a gap between words unless Alt is held.
  function timeAt(e, side){
    const r=box.querySelector(".ts-film").getBoundingClientRect(), raw=Math.min(win.b,Math.max(win.a, win.a+(e.clientX-r.left)/pps()));
    if(e.altKey || !side) return raw;
    let near=null; for(const s of o.snaps(side)){ const d=Math.abs(x(s)-x(raw)); if(d<=TS_SNAP && (!near||d<near.d)) near={s,d}; }
    return near?near.s:raw;
  }
  function tip(t, text){
    const el=box.querySelector(".ts-tip"); el.hidden=false; el.style.left=pc(t); el.textContent=text;
  }
  // near an end: TS_EDGE px, less on a narrow box (its middle always moves it)
  const atEdge=t=>sel && Math.min(Math.abs(x(t)-x(sel.a)),Math.abs(x(t)-x(sel.b)))<=Math.min(TS_EDGE, Math.max(4,(x(sel.b)-x(sel.a))/4));
  const inside=t=>sel && t>sel.a && t<sel.b;
  // the Short's own ends (its first part's start, its last part's end): "s", "e" or null
  const shortEnd=t=>{ const p=o.pieces(); if(!p.length) return null; const ds=Math.abs(x(t)-x(p[0][0])), de=Math.abs(x(t)-x(p[p.length-1][1]));
    return Math.min(ds,de)>TS_EDGE ? null : ds<=de ? "s" : "e"; };
  function startScrub(e, film){
    if(o.press) o.press();
    drag={side:"head", id:e.pointerId, was:sel&&{...sel}};
    film.setPointerCapture(e.pointerId); box.querySelector(".ts-head").classList.add("drag"); film.style.cursor="grabbing";
    const t=timeAt(e); o.seek(t); tip(t,tsClock(rel(t),true));
  }
  function wire(){
    const film=box.querySelector(".ts-film");
    box.querySelector(".ts-ticks").addEventListener("pointerdown",e=>{ if(e.button!==0 || !win) return; e.preventDefault(); startScrub(e,film); });
    film.addEventListener("pointermove",e=>{
      if(!win) return;
      if(drag && e.pointerId===drag.id){ move(e); return; }
      const t=timeAt(e), h=box.querySelector(".ts-hover"), ed=o.trim()&&o.canEdit();
      h.hidden=false; h.style.left=pc(t);
      film.style.cursor=ed&&(atEdge(t)||(!inside(t)&&shortEnd(t)))?"ew-resize":ed&&inside(t)?"grab":"pointer";
      tip(t, tsClock(rel(t),true));
    });
    film.addEventListener("pointerleave",()=>{ if(drag) return; box.querySelector(".ts-hover").hidden=true; box.querySelector(".ts-tip").hidden=true; });
    film.addEventListener("pointerdown",e=>{
      if(e.button!==0 || !win) return;
      e.preventDefault(); if(o.press) o.press();
      if(e.target.closest(".ts-knob") || !o.trim() || !o.canEdit()){ startScrub(e,film); return; }
      const t=timeAt(e), head=o.now();
      // the line itself can be taken too, unless a yellow box or the Short's end is right there
      if(head!=null && Math.abs(x(t)-x(head))<=6 && !atEdge(t) && !inside(t) && !shortEnd(t)){ startScrub(e,film); return; }
      if(atEdge(t)){  // an end of the box: stretch or narrow it
        drag={side:Math.abs(x(t)-x(sel.a))<=Math.abs(x(t)-x(sel.b))?"a":"b", id:e.pointerId, was:{...sel}};
        film.setPointerCapture(e.pointerId); return;
      }
      const se=!inside(t) && shortEnd(t);  // (inside the yellow box, the box comes first)
      if(se){  // the Short's own end: stretch it into the vlog around it, or shorten it
        drag={side:"short-"+se, id:e.pointerId, p0:o.pieces().map(q=>[...q]), p:null, x0:e.clientX, t0:t};
        film.setPointerCapture(e.pointerId); return;
      }
      if(inside(t)){  // inside it: move it along, the same length
        drag={side:"move", id:e.pointerId, was:{...sel}, t0:t, x0:e.clientX, moved:false};
        film.setPointerCapture(e.pointerId); film.style.cursor="grabbing"; return;
      }
      // elsewhere: a click moves the player, a drag makes a new yellow box
      drag={side:"new", id:e.pointerId, t0:t, x0:e.clientX, moved:false, was:sel&&{...sel}};
      film.setPointerCapture(e.pointerId);
    });
    film.addEventListener("pointerup",e=>{ if(drag && e.pointerId===drag.id){ const d=drag; drag=null;
      if(d.side==="head"){ box.querySelector(".ts-head").classList.remove("drag"); box.querySelector(".ts-tip").hidden=true; film.style.cursor=""; return; }
      if(d.side.startsWith("short-")){ box.querySelector(".ts-tip").hidden=true;
        if(d.p && Math.abs(e.clientX-d.x0)>2 && o.commit) o.commit(d.p); else{ paint(); o.seek(d.t0); }  // not moved: a click
        return; }
      if(d.x0!=null && !d.moved){ box.querySelector(".ts-tip").hidden=true; o.seek(d.t0); }  // not moved: a click
      o.onSel(); } });
    film.addEventListener("pointercancel",()=>{ if(drag){ const d=drag; drag=null; if(d.was) sel=d.was; paint(); o.onSel(); } });
    document.addEventListener("keydown",e=>{
      if(e.key!=="Escape" || !on || (!sel && !drag)) return;  // (Esc while dragging a Short end: it stays)
      const a=document.activeElement; if(a && (a.tagName==="INPUT"||a.tagName==="TEXTAREA")) return;
      e.preventDefault(); if(drag){ sel=drag.was||null; drag=null; paint(); } else sel=null; marks(); o.onSel();
    });
    new ResizeObserver(()=>{ if(on && win) pics(); }).observe(film);
  }
  function move(e){
    if(drag.side==="head"){ const t=timeAt(e); o.seek(t); tip(t,tsClock(rel(t),true)); return; }
    if(drag.side.startsWith("short-")){
      const p=drag.p0.map(q=>[...q]), n=p.length-1, info=o.info(), [r0,r1]=info.reach||[0,info.duration||win.b];
      if(drag.side==="short-s"){ const t=timeAt(e,"start"); p[0][0]=r3(Math.max(win.a, r0, Math.min(p[0][1]-0.5, t))); }
      else { const t=timeAt(e,"end"); p[n][1]=r3(Math.min(win.b, r1, Math.max(p[n][0]+0.5, t))); }
      drag.p=p; dims(p);
      const at=drag.side==="short-s"?p[0][0]:p[n][1], len=p.reduce((s2,[a,b])=>s2+b-a,0);
      tip(at,(drag.side==="short-s"?"Starts ":"Ends ")+tsClock(rel(at),true)+" · Short "+fmt(len)); o.hover(at);
      return;
    }
    if(drag.side==="new"){
      if(!drag.moved && Math.abs(e.clientX-drag.x0)<TS_DRAG) return;
      drag.moved=true;
      const raw=timeAt(e), side=raw<drag.t0?"start":"end", t=timeAt(e,side), from=timeAt({clientX:box.querySelector(".ts-film").getBoundingClientRect().left+x(drag.t0), altKey:e.altKey}, side==="start"?"end":"start");
      if(Math.abs(t-from)<TS_MIN_SEL){ sel=drag.was||null; marks(); return; }
      sel={a:r3(Math.min(t,from)), b:r3(Math.max(t,from))}; marks();
      tip(t, tsClock(rel(sel.a),true)+" → "+tsClock(rel(sel.b),true)+" · "+(sel.b-sel.a).toFixed(1)+" s"); o.hover(t);
      return;
    }
    if(drag.side==="move"){
      if(!drag.moved && Math.abs(e.clientX-drag.x0)<TS_DRAG) return;
      drag.moved=true;
      const len=drag.was.b-drag.was.a, d=timeAt(e)-drag.t0;
      let a=Math.min(win.b-len, Math.max(win.a, drag.was.a+d));
      if(!e.altKey){ const s=timeAt({clientX:box.querySelector(".ts-film").getBoundingClientRect().left+x(a), altKey:false},"start"); a=Math.min(win.b-len, Math.max(win.a, s)); }
      sel={a:r3(a), b:r3(a+len)}; marks();
      tip(sel.a, tsClock(rel(sel.a),true)+" → "+tsClock(rel(sel.b),true)+" · "+len.toFixed(1)+" s"); o.hover(sel.a);
      return;
    }
    const t=timeAt(e, drag.side==="a"?"start":"end");
    if(drag.side==="a") sel={a:r3(Math.max(win.a,Math.min(t, sel.b-TS_MIN_SEL))), b:sel.b}; else sel={a:sel.a, b:r3(Math.min(win.b,Math.max(t, sel.a+TS_MIN_SEL)))};
    marks(); tip(drag.side==="a"?sel.a:sel.b, tsClock(rel(sel.a),true)+" → "+tsClock(rel(sel.b),true)+" · "+(sel.b-sel.a).toFixed(1)+" s");
    o.hover(drag.side==="a"?sel.a:sel.b);
  }
  return {
    paint, follow,
    show(v){ on=!!v; if(on) paint(); },
    reset(){ win=null; winFor=""; sel=null; drag=null; box.innerHTML=""; },
    win:()=>win && {...win},
    sel:()=>sel && {...sel},
    setSel(s){ sel=s?{a:r3(Math.max(win?win.a:0,s.a)), b:r3(Math.min(win?win.b:1e9,s.b))}:null; if(win) marks(); o.onSel(); },
    rel,
  };
}
// The big preview while trimming: the player's place shows the vlog at a moment, framed as the Short (crop(t) = the frame
// at that time, from Reframe), and plays the Short as it will be (the parts kept now, saved or not) with its sound.
function trimView(o){
  // o: host (over the player), src() (the vlog's video, or a clip starting at the vlog second off()), crop(t) -> {x, y, z} (0-1) or null (the whole picture), size()
  // -> {width, height} of the vlog, onTime(t | null) (playing; null = stopped)
  let vid=null, vidSrc="", playing=false, raf=0, at=0, plan=null, unlocked=false;
  const cv=()=>o.host.querySelector("canvas"), off=()=>o.off?o.off():0;
  const vt=()=>vid.currentTime+off();  // the video's place, in vlog seconds
  function video(){
    const src=o.src(); if(!src) return null;
    if(src!==vidSrc){ vidSrc=src; unlocked=false; vid=document.createElement("video"); vid.preload="metadata"; vid.playsInline=true; vid.src=src;
      vid.addEventListener("seeked",()=>{ if(!playing) paint(); }); vid.addEventListener("loadedmetadata",()=>{ if(!playing) vid.currentTime=Math.max(0,at-off()); });
      vid.addEventListener("loadeddata",()=>{ if(!playing) paint(); }); }
    return vid;
  }
  function paint(){
    const c=cv(), v=vid; if(!c||!v||v.readyState<2||!v.videoWidth) return;
    const dpr=window.devicePixelRatio||1, W=c.clientWidth*dpr|0, H=c.clientHeight*dpr|0;
    if(W&&H&&(c.width!==W||c.height!==H)){ c.width=W; c.height=H; }
    const g=c.getContext("2d"); g.fillStyle="#000"; g.fillRect(0,0,c.width,c.height);
    const f=o.crop(playing?vt():at), sz=o.size(), k=v.videoWidth/(sz.width||v.videoWidth);
    if(f){ const w=rfWindow(sz.width,sz.height,f,9/16); g.drawImage(v,w.l*k,w.t*k,w.w*k,w.h*k,0,0,c.width,c.height); }
    else{ const h=c.width*v.videoHeight/v.videoWidth; g.drawImage(v,0,(c.height-h)/2,c.width,h); }
    if(o.overlay) o.overlay(g, playing?vt():at, c.width, c.height);
  }
  function open(text){
    if(!cv()) o.host.innerHTML='<canvas aria-label="The Short at this moment"></canvas><span class="tv-time"></span>';
    o.host.querySelector(".tv-time").textContent=text||""; o.host.hidden=false;
  }
  const api={
    // Called from a press. Safari only lets a video play with sound if it first played from a person's press or click, and the
    // player's own Play button (which comes here through a "play" event) doesn't count: a silent instant now means sound later.
    unlock(){
      const v=video(); if(!v||unlocked||playing) return; unlocked=true;
      const vol=v.volume; v.volume=0; const r=v.play();
      const done=()=>{ if(!playing) v.pause(); v.volume=vol; };
      if(r&&r.then) r.then(done,()=>{ unlocked=false; v.volume=vol; }); else done();
    },
    // show the moment t (vlog seconds) big
    show(t, text){ if(playing) return; const v=video(); if(!v) return; open(text); at=t;
      if(v.readyState>=1 && Math.abs(vt()-t)>0.03) v.currentTime=Math.max(0,t-off()); else paint(); },
    hide(){ if(!playing) o.host.hidden=true; },
    // play these pieces (vlog seconds) from `from` to `to`, with sound, skipping what's between them
    play(pieces, from, to, text){
      const v=video(); if(!v||!pieces.length) return;
      api.stop(); open(text);
      plan={p:pieces, to:to==null?pieces[pieces.length-1][1]:to};
      let k=pieces.findIndex(([a,b])=>from<b-0.05); if(k<0) return;
      v.currentTime=Math.max(0,Math.max(from,pieces[k][0])-off()); v.muted=false; playing=true;
      v.play().catch(()=>{ v.muted=true; v.play().catch(()=>{}); });
      const tick=()=>{
        if(!playing) return;
        const now=vt();
        if(now>=plan.to-0.02){ api.stop(); return; }
        if(now>=plan.p[k][1]-0.02){ k++; if(k>=plan.p.length){ api.stop(); return; } v.currentTime=Math.max(0,plan.p[k][0]-off()); }
        at=now; paint(); o.onTime&&o.onTime(now); raf=requestAnimationFrame(tick);
      };
      raf=requestAnimationFrame(tick);
    },
    stop(){ if(!playing) return; playing=false; cancelAnimationFrame(raf); if(vid) vid.pause(); o.onTime&&o.onTime(null); },
    playing:()=>playing, time:()=>at,
  };
  return api;
}
