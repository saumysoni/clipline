// Text & Overlays, an editor tool (web/overlays.py, pipeline/overlays.py): text a creator puts on the Short at a moment they
// choose: a title, a key word, a few lines. Add text puts it at the playhead for OV_LEN seconds; then its words, a style
// (Bold, Boxed, Shadow, Outline), font, size, colours, how it comes in, and when it shows (start / end: a step either way, or
// the playhead). At most info.max on one Short.
// While it's chosen, the player's place shows the Short at the playhead as it'll look, drawn live from the vlog's video
// (its own trimView, js/trim-strip.js: framed by Reframe, with the captions drawn by Captions), with the text on top: drag
// it there to place it. The saved video isn't used for this: the saved text is burned into it, and would show twice.
// The browser draws the fonts as near as it can; "Exact frame" asks the server for the frame as it'll be made (Captions'
// preview, with the text). Times are the vlog's seconds (cuts and trims never move a text off its moment).
// Nothing is saved until the editor's Save (shortDetails() o.ovl: one remake with the captions and framing); Undo / Redo
// and Discard as every tool.
// o: {box (the panel), stage (over the player), ae (AI Edit: pieces), caps (Captions: overlay(), snap()), rf (Reframe:
//     cropAt(), size(), snap()), hook() (the hook as it'll be: drawn on the picture for its first seconds), src() / off() (the vlog's video, or a clean clip from the vlog second off()), at() (the
//     playhead, vlog seconds), seek(t), onTime(t | null) (playing; null = stopped), onChange(), onLoad()}
const OV_LEN=2.5;  // seconds a new text shows
// Where Top / Middle / Lower put a text's middle (y, 0-1): Top under the hook's banner, Lower just above the captions
// (their place and size, as Captions has them now), else where the apps' buttons start. The hook: pipeline/captions.py
// (Style Hook: 66 px, a box 18 px round it, MarginV 200 from the top, on screen HOOK_SECS).
const HOOK_SECS=2.8;
const OV_FONT={default:'800 X "Montserrat","Plus Jakarta Sans",Arial,sans-serif', anton:'400 X "Anton",Impact,"Arial Narrow",sans-serif',
  bebas:'400 X "Bebas Neue",Impact,"Arial Narrow",sans-serif', poppins:'900 X "Poppins","Plus Jakarta Sans",Arial,sans-serif',
  bangers:'400 X "Bangers",Impact,sans-serif', serif:'400 X "DM Serif Display",Georgia,serif'};
const OV_SECOND={bold:"Outline", boxed:"Box", shadow:"Shadow", hollow:""};  // what the second colour is, per style
function overlayEdit(o){
  let c=null, info=null, cur=[], gen=0, busy=false, shown=false, sel=null, t=0, rects={}, drag=null, exact=null, exGen=0, layerRaf=0;
  const copy=x=>JSON.parse(JSON.stringify(x)), same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const changed=()=>o.onChange&&o.onChange();
  const dirty=()=>!!info && !same(cur, info.overlays);
  const can=()=>!!info && info.can_apply && !busy && !(c&&c.remaking);
  const item=id=>cur.find(x=>x.id===id);
  const sizeOf=k=>(info&&info.sizes.find(s=>s[0]===k)||["m",100])[1];
  function positions(x){
    const cap=o.caps.snap(), half=sizeOf(x.size)*0.55*Math.min(3,x.text.split("\n").length);
    const low=cap&&cap.on ? (1920-cap.bottom-cap.size*1.3-30-half)/1920 : (1920*0.78-half)/1920;
    return [["Top",+((400+half)/1920).toFixed(4)],["Middle",0.45],["Lower",+Math.min(0.8,Math.max(0.5,low)).toFixed(4)]];
  }
  const fmtT=v=>{ const p=o.ae.pieces(), s=aeToFile(p,v); return s==null?"cut":fmt(s)+"."+Math.floor((s%1)*10); };
  // ---- the stage: the Short at the playhead (view), and the text's boxes to drag (layer)
  o.stage.innerHTML='<div class="tv-host ov-view"></div><div class="ov-layer" aria-label="Drag the text to place it"></div>'+
    '<p class="ov-none" hidden>The video\'s file was deleted, so the picture can\'t be shown here. You can still change the text; Exact frame shows it.</p>';
  const view=o.stage.querySelector(".ov-view"), layer=o.stage.querySelector(".ov-layer");
  const tv=trimView({host:view, src:o.src, off:o.off, crop:x=>o.rf.cropAt(x), size:()=>o.rf.size(),
    overlay:(g,x,W,H)=>{ hookDraw(g,x,W,H); o.caps.overlay(g,x,W,H); api.draw(g,x,W,H,true,tv.playing()); },
    onTime:x=>{ if(x==null) t=tv.time(); else t=x; o.onTime&&o.onTime(x); }});
  // The hook's banner, for its first seconds on the Short's clock: so text isn't put where it'll be covered.
  function hookDraw(g,x,W,H){
    const h=o.hook&&o.hook(), at=aeToFile(o.ae.pieces(),x); if(!h || at==null || at>HOOK_SECS) return;
    const k=W/1080, fs=66*k*0.9, lh=fs*1.2, pad=18*k, max=W-180*k-pad*2, rows=[];
    g.save(); g.font='800 '+Math.round(fs)+'px "Plus Jakarta Sans",Arial,sans-serif'; g.textAlign="center"; g.textBaseline="middle";
    let line=""; for(const w of h.split(/\s+/)){ const tr=line?line+" "+w:w; if(line && g.measureText(tr).width>max){ rows.push(line); line=w; } else line=tr; } rows.push(line);
    rows.forEach((r,n)=>{ const m=g.measureText(r).width, y=200*k+lh*n; g.fillStyle="#fff"; g.fillRect(W/2-m/2-pad,y-pad/2,m+pad*2,lh+pad); });
    rows.forEach((r,n)=>{ g.fillStyle="#111"; g.fillText(r,W/2,200*k+lh*n+lh/2); });
    g.restore();
  }
  function set(next, keepSel){
    if(!can()) return;
    cur=next; exGen++; exact=null;
    if(!keepSel && sel && !item(sel)) sel=null;
    paint(); repaint(); changed();
  }
  const patch=(id,p)=>set(cur.map(x=>x.id===id?{...x,...p}:x),true);
  // quiet (after a remake): what's shown stays until the new settings are in
  async function load(quiet){
    const my=++gen, cl=c, keep=quiet&&info;
    if(!keep){ info=null; cur=[]; sel=null; o.box.innerHTML='<p class="qr-wait">Getting the text...</p>'; changed(); }
    let j; try{ const r=await fetch("/api/overlays/"+cl.job+"/"+cl.idx); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ if(my===gen && !keep) o.box.innerHTML='<p class="qr-wait">'+esc(e.message||"Couldn't load the text. Check your internet connection, then try again.")+'</p>'; return; }
    if(my!==gen) return;
    info=j; cur=copy(j.overlays); if(sel && !item(sel)) sel=null;
    paint(); repaint(); changed();
    o.onLoad&&o.onLoad();
  }
  // Add text: at the playhead (inside a part the Short keeps), OV_LEN seconds, picked to change straight away
  function add(){
    if(!can() || cur.length>=info.max) return;
    const p=o.ae.pieces(); if(!p.length) return;
    let a=o.at(); if(a==null) a=p[0][0];
    if(!aeIn(p,a)){ const nx=p.find(([x])=>x>a); a=nx?nx[0]:p[0][0]; }
    a=+Math.max(0,a).toFixed(2);
    const id="t"+Date.now().toString(36).slice(-6);
    const last=cur[cur.length-1]||{};  // a second text takes the look of the one before (a series of key words)
    const x={id, text:"Your text", style:last.style||"bold", font:last.font||"default", color:last.color||"#FFFFFF", line:last.line||"#000000",
      size:last.size||"m", x:0.5, y:0, a, b:+(a+OV_LEN).toFixed(2), anim:last.anim||"pop"};
    x.y=positions(x)[0][1];
    sel=id; set([...cur,x]);
    const ta=o.box.querySelector(".ov-words"); if(ta){ ta.focus(); ta.select(); }
  }
  function choose(id, go){
    sel=sel===id&&!go?null:id; paint(); repaint();
    const x=item(id); if(go && x) o.seek(+(x.a+0.05).toFixed(2));
    o.onChange&&o.onChange();  // (the Overlays row lights the one picked)
  }
  // ---- the panel
  const seg=(k,opts,v)=>'<div class="cp-seg" role="group">'+opts.map(([label,x])=>
    '<button type="button" data-k="'+k+'" data-v="'+esc(String(x))+'" aria-pressed="'+(v===x)+'">'+esc(label)+'</button>').join("")+'</div>';
  const row=(label,body,hint)=>'<div class="cp-row"><span class="cp-lab">'+esc(label)+(hint?'<small>'+esc(hint)+'</small>':'')+'</span>'+body+'</div>';
  function styleHTML(x,s){
    const font=OV_FONT[x.font].replace("X","15px"), col=x.color, ln=x.line;
    const look=s.id==="boxed"?'background:'+ln+';padding:1px 6px;':s.id==="shadow"?'text-shadow:2px 3px 4px '+ln+'b0;':
      s.id==="hollow"?'color:transparent;-webkit-text-stroke:1.2px '+col+';':'-webkit-text-stroke:3px '+ln+';paint-order:stroke fill;';
    return '<button type="button" class="ov-style" data-style="'+s.id+'" aria-pressed="'+(x.style===s.id)+'">'+
      '<span class="ov-style-s" style="font:'+font+';color:'+col+';'+look+'">Aa</span><b>'+esc(s.name)+'</b></button>';
  }
  function paint(){
    if(!info) return;
    const ok=can(), x=sel&&item(sel), full=cur.length>=info.max, list=[...cur].sort((p,q)=>p.a-q.a);
    let h=(info.can_apply?'':'<div class="ed-note ae-warn">'+esc(info.why_not)+'</div>')+
      (c&&c.remaking||busy?'<div class="ed-fin-wait"><span class="spin" aria-hidden="true"></span><span>Remaking the Short with your edits...</span></div>':'')+
      '<div class="ov-top"><button type="button" class="primary" id="ovAdd"'+(ok&&!full?'':' disabled')+(full?' title="'+info.max+' texts at most: more crowds the picture"':'')+'>'+
        '<span class="ms" aria-hidden="true">add</span>Add text</button><small>'+cur.length+' of '+info.max+'</small></div>';
    if(!cur.length) h+='<p class="ae-help">Put a title or a key word on screen. It shows at the playhead for '+OV_LEN+' s: drag it on the picture to place it, and change when it shows below.</p>';
    else h+='<ul class="ov-list">'+list.map(y=>'<li class="'+(y.id===sel?'on':'')+'"><button type="button" class="ov-pick" data-id="'+y.id+'" aria-pressed="'+(y.id===sel)+'">'+
        '<small>'+fmtT(y.a)+'</small><span>'+esc(y.text.split("\n").join(" / "))+'</span></button>'+
        '<button type="button" class="iconbtn ov-del" data-id="'+y.id+'" aria-label="Delete this text" title="Delete"'+(ok?'':' disabled')+'><span class="ms" aria-hidden="true">delete</span></button></li>').join("")+'</ul>';
    if(x){
      const len=(x.b-x.a).toFixed(1), second=OV_SECOND[x.style];
      const step=(k,d)=>'<button type="button" class="ghost sm" data-t="'+k+'" data-d="'+d+'">'+(d<0?"−":"+")+Math.abs(d)+' s</button>';
      h+='<section class="ov-edit" aria-label="The text you picked">'+
        '<label class="small-lab" for="ovWords">Words</label>'+
        '<textarea id="ovWords" class="ov-words" rows="2" maxlength="120" spellcheck="true">'+esc(x.text)+'</textarea>'+
        '<small class="ov-hint">Up to 3 lines (Enter starts a new one).</small>'+
        '<h3 class="cp-h">Style</h3><div class="ov-styles">'+info.styles.map(s=>styleHTML(x,s)).join("")+'</div>'+
        row("Font",'<select data-k="font" aria-label="Font">'+info.fonts.map(f=>'<option value="'+esc(f.id)+'"'+(f.id===x.font?' selected':'')+'>'+esc(f.name)+'</option>').join("")+'</select>')+
        row("Size",seg("size",[["S","s"],["M","m"],["L","l"]],x.size))+
        row("Colours",'<div class="cp-cols"><label class="cp-col"><input type="color" data-k="color" value="'+esc(x.color.toLowerCase())+'"><span>Text</span></label>'+
          (second?'<label class="cp-col"><input type="color" data-k="line" value="'+esc(x.line.toLowerCase())+'"><span>'+second+'</span></label>':'')+'</div>')+
        row("Position",seg("y",positions(x),(positions(x).find(p=>Math.abs(p[1]-x.y)<0.005)||[])[1]),"Clear of the hook and the captions. Or drag it on the picture")+
        row("Comes in",seg("anim",[["At once","none"],["Pop","pop"],["Fade","fade"],["Slide up","slide"]],x.anim))+
        '<h3 class="cp-h">When it shows</h3>'+
        '<div class="tr-sum ov-when"><b>'+fmtT(x.a)+' → '+fmtT(x.b)+'</b> <span>'+len+' s</span></div>'+
        '<div class="tr-row"><span><b>Starts</b></span><span class="tr-steps">'+step("a",-0.5)+'<button type="button" class="ghost sm" data-here="a">At the playhead</button>'+step("a",0.5)+'</span></div>'+
        '<div class="tr-row"><span><b>Ends</b></span><span class="tr-steps">'+step("b",-0.5)+'<button type="button" class="ghost sm" data-here="b">At the playhead</button>'+step("b",0.5)+'</span></div>'+
        '<div class="err" id="ovErr" role="alert"></div>'+
        '<div class="ov-acts"><button type="button" class="linkbtn ov-del" data-id="'+x.id+'"><span class="ms" aria-hidden="true">delete</span>Delete this text</button>'+
          '<button type="button" class="linkbtn" id="ovDone">Done</button></div>'+
      '</section>';
    }
    if(cur.length) h+='<figure class="ov-exact" id="ovExact"><button type="button" class="ghost sm" id="ovExactBtn"'+(info.can_apply?'':' disabled')+'>'+
        '<span class="ms" aria-hidden="true">visibility</span>Exact frame</button><small>The browser draws the fonts as near as it can. This shows the frame at the playhead as it\'ll be made.</small>'+
        (exact?'<img src="'+exact+'" alt="The Short at the playhead as it will be made, with the text">':'')+'</figure>';
    const focus=document.activeElement&&document.activeElement.id==="ovWords";
    o.box.innerHTML=h;
    wire(ok);
    if(focus){ const ta=$("ovWords"); if(ta){ ta.focus(); ta.setSelectionRange(ta.value.length,ta.value.length); } }
  }
  function wire(ok){
    const box=o.box, x=sel&&item(sel);
    $("ovAdd").onclick=add;
    box.querySelectorAll(".ov-pick").forEach(b=>b.onclick=()=>choose(b.dataset.id,true));
    box.querySelectorAll(".ov-del").forEach(b=>b.onclick=()=>{ if(sel===b.dataset.id) sel=null; set(cur.filter(y=>y.id!==b.dataset.id)); });
    const ex=$("ovExactBtn"); if(ex) ex.onclick=exactFrame;
    if(!x) return;
    const ta=$("ovWords");
    // typed: kept as it is typed (a run of typing is one Undo step: js/editor.js edTyping), never empty
    ta.oninput=()=>{ const v=ta.value.split("\n").slice(0,3).join("\n").slice(0,120); if(!v.trim()) return; cur=cur.map(y=>y.id===x.id?{...y,text:v}:y); exGen++; exact=null; repaint(); changed(); paintList(); };
    ta.onblur=()=>{ if(!ta.value.trim()){ const y=item(x.id); if(y) ta.value=y.text; } };
    ta.onkeydown=e=>{ if(e.key==="Enter" && ta.value.split("\n").length>=3) e.preventDefault(); if(e.key==="Escape") ta.blur(); };
    box.querySelectorAll(".ov-style").forEach(b=>b.onclick=()=>patch(x.id,{style:b.dataset.style}));
    box.querySelectorAll("select[data-k]").forEach(s=>s.onchange=()=>patch(x.id,{[s.dataset.k]:s.value}));
    box.querySelectorAll(".ov-edit .cp-seg [data-k]").forEach(b=>b.onclick=()=>patch(x.id,{[b.dataset.k]:b.dataset.k==="y"?+b.dataset.v:b.dataset.v}));
    box.querySelectorAll("input[type=color][data-k]").forEach(i=>i.onchange=()=>patch(x.id,{[i.dataset.k]:i.value.toUpperCase()}));
    const err=m=>{ const e=$("ovErr"); if(e) e.textContent=m; };
    const when=(a,b)=>{
      a=+Math.max(0,a).toFixed(2); b=+b.toFixed(2);
      if(b-a<0.3){ err("Text needs to show for at least a third of a second."); return; }
      if(b-a>60){ err("Text can show for a minute at most."); return; }
      patch(x.id,{a,b});
    };
    box.querySelectorAll("[data-t]").forEach(b=>b.onclick=()=>{ const d=+b.dataset.d; b.dataset.t==="a"?when(x.a+d,x.b):when(x.a,x.b+d); });
    box.querySelectorAll("[data-here]").forEach(b=>b.onclick=()=>{ const h=o.at(); if(h==null) return;
      if(b.dataset.here==="a") when(h, Math.max(x.b, h+Math.min(OV_LEN,x.b-x.a))); else when(x.a, h); });
    $("ovDone").onclick=()=>choose(x.id);
    if(!ok) box.querySelectorAll(".ov-edit button,.ov-edit input,.ov-edit select,.ov-edit textarea").forEach(e=>e.disabled=true);
  }
  function paintList(){  // the list's text while typing (the rest of the panel stays, so the cursor does)
    o.box.querySelectorAll(".ov-pick").forEach(b=>{ const y=item(b.dataset.id); if(y) b.querySelector("span").textContent=y.text.split("\n").join(" / "); });
  }
  // The exact frame at the playhead: Captions' preview with the text, the captions, cuts and framing waiting to be saved.
  async function exactFrame(){
    const my=++exGen, fig=$("ovExact"); let at=o.at(); if(at==null||!fig) return;
    // just as it comes in it's still small or faint (Pop, Fade, Slide up): a moment later, where it's in place
    const x=sel&&item(sel); if(x && x.anim!=="none" && at>=x.a-0.01 && at<x.a+0.35 && x.b-x.a>0.4) at=x.a+0.35;
    fig.classList.add("busy");
    const body={captions:o.caps.snap(), overlays:cur, at:+at.toFixed(2)};
    if(o.ae.dirty()) body.pieces=o.ae.pieces();
    if(o.rf.dirty()) body.reframe=o.rf.snap().r;  // (else the saved framing)
    try{
      const r=await fetch("/api/captions/"+c.job+"/"+c.idx+"/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      if(!r.ok) throw new Error((await r.json().catch(()=>({}))).error||"");
      const url=URL.createObjectURL(await r.blob());
      if(my!==exGen){ URL.revokeObjectURL(url); return; }
      if(exact) URL.revokeObjectURL(exact);
      exact=url; paint();
    }catch(e){ const f=$("ovExact"); if(f){ f.classList.remove("busy"); const s=f.querySelector("small"); if(s) s.textContent=e.message||"Couldn't draw the frame. Try again."; } }
  }
  // ---- the stage
  function repaint(){ if(shown && !tv.playing() && o.src()) tv.show(t,""); paintLayer(); }
  // The boxes over each text on show (from where draw() last put them), the picked one outlined; drag one to move it.
  function paintLayer(){
    cancelAnimationFrame(layerRaf);
    layerRaf=requestAnimationFrame(()=>{
      const cv=view.querySelector("canvas"), on=shown && !tv.playing() && !!cv && !view.hidden;
      layer.hidden=!on; if(!on) return;
      const sr=o.stage.getBoundingClientRect(), r=cv.getBoundingClientRect();
      Object.assign(layer.style,{left:(r.left-sr.left)+"px", top:(r.top-sr.top)+"px", width:r.width+"px", height:r.height+"px"});
      const ids=Object.keys(rects), can_=can();
      layer.innerHTML='<i class="ov-safe" aria-hidden="true"></i>'+ids.map(id=>{ const b=rects[id], y=item(id); if(!y) return "";
        return '<button type="button" class="ov-box'+(id===sel?' on':'')+'" data-id="'+id+'" style="left:'+(b.x*100)+'%;top:'+(b.y*100)+'%;width:'+(b.w*100)+'%;height:'+(b.h*100)+'%"'+
          ' aria-label="'+esc(y.text)+': drag to move" title="'+(can_?'Drag to move. Click to change it':'')+'"></button>'; }).join("");
    });
  }
  layer.addEventListener("pointerdown",e=>{
    const b=e.target.closest(".ov-box");
    if(!b){ if(sel){ sel=null; paint(); repaint(); changed(); } return; }
    const y=item(b.dataset.id); if(!y) return;
    e.preventDefault();
    if(sel!==y.id){ sel=y.id; paint(); }
    if(!can()){ paintLayer(); return; }
    const r=layer.getBoundingClientRect();
    drag={id:y.id, x0:e.clientX, y0:e.clientY, fx:y.x, fy:y.y, w:r.width, h:r.height, moved:false, pid:e.pointerId, before:copy(cur)};
    layer.setPointerCapture(e.pointerId); layer.classList.add("drag");
  });
  layer.addEventListener("pointermove",e=>{
    if(!drag||drag.pid!==e.pointerId) return;
    const dx=(e.clientX-drag.x0)/drag.w, dy=(e.clientY-drag.y0)/drag.h;
    if(!drag.moved && Math.hypot(e.clientX-drag.x0,e.clientY-drag.y0)<3) return;
    drag.moved=true;
    let nx=Math.min(0.96,Math.max(0.04,drag.fx+dx)), ny=Math.min(0.96,Math.max(0.04,drag.fy+dy));
    if(!e.altKey && Math.abs(nx-0.5)<0.025) nx=0.5;  // snaps to the middle (Alt: freely)
    cur=cur.map(y=>y.id===drag.id?{...y,x:+nx.toFixed(4),y:+ny.toFixed(4)}:y);  // (one Undo step: recorded when it's let go)
    layer.classList.toggle("mid",nx===0.5);
    repaint();
  });
  const dragEnd=e=>{
    if(!drag||drag.pid!==e.pointerId) return;
    const d=drag; drag=null; layer.classList.remove("drag","mid");
    if(d.moved){ exGen++; exact=null; paint(); changed(); }
    else repaint();
  };
  layer.addEventListener("pointerup",dragEnd); layer.addEventListener("pointercancel",dragEnd);
  // Arrow keys move the picked text a little (Shift: more), while the stage shows and nothing is being typed.
  document.addEventListener("keydown",e=>{
    if(!shown || !sel || !can() || !e.key.startsWith("Arrow") || $("s12").hidden) return;
    const a=document.activeElement; if(a && (a.closest("input,textarea,select,[contenteditable]"))) return;
    const y=item(sel); if(!y) return;
    const s=e.shiftKey?0.05:0.01, d={ArrowLeft:[-s,0],ArrowRight:[s,0],ArrowUp:[0,-s],ArrowDown:[0,s]}[e.key];
    e.preventDefault();
    patch(y.id,{x:+Math.min(0.96,Math.max(0.04,y.x+d[0])).toFixed(4), y:+Math.min(0.96,Math.max(0.04,y.y+d[1])).toFixed(4)});
  });
  new ResizeObserver(()=>repaint()).observe(o.stage);
  const api={
    // The text on show at t (vlog seconds), drawn on a canvas W x H (the Short's picture): near the finished look (the
    // server burns the real one in, pipeline/overlays.py). mine: the stage's own view (records where each one is, to drag).
    // moving: playing, so it comes in as it will (Pop, Fade, Slide up); a still shows it in place, at its full size, to place it.
    draw(g,x,W,H,mine,moving){
      if(mine) rects={};
      if(!info) return;
      const k=W/1080;
      for(const y of cur){
        if(x<y.a-0.001 || x>y.b+0.001) continue;
        const fs=sizeOf(y.size)*k*0.9, lh=fs*1.12, dt=x-y.a;
        g.save();
        g.font=OV_FONT[y.font].replace("X",Math.round(fs)+"px"); g.textAlign="center"; g.textBaseline="middle"; g.lineJoin="round";
        // wrapped like libass: inside the picture less 90 px a side
        const max=W-180*k, rows=[];
        for(const part of y.text.split("\n")){ let line="";
          for(const w of part.split(" ")){ const tr=line?line+" "+w:w; if(line && g.measureText(tr).width>max){ rows.push(line); line=w; } else line=tr; }
          rows.push(line); }
        const cx=y.x*W; let cy=y.y*H;
        let alpha=1, scale=1;
        if(moving){
        if(y.anim==="pop" && dt<0.23) scale=dt<0.14?0.4+0.72*(dt/0.14):1.12-0.12*((dt-0.14)/0.09);
        if(y.anim==="fade"){ alpha=Math.min(1,dt/0.3,(y.b-x)/0.25); }
        if(y.anim==="slide" && dt<0.22){ cy+=80*k*(1-dt/0.22); alpha=Math.min(1,dt/0.15); }
        }
        g.globalAlpha=Math.max(0,alpha);
        g.translate(cx,cy); g.scale(scale,scale);
        const top=-(rows.length*lh)/2+lh/2;
        let wide=0;
        rows.forEach((r,n)=>{
          const ty=top+n*lh, m=g.measureText(r).width; wide=Math.max(wide,m);
          if(y.style==="boxed"){ g.fillStyle=y.line; const p=18*k*0.8; g.fillRect(-m/2-p,ty-lh/2,m+p*2,lh); }
        });
        rows.forEach((r,n)=>{
          const ty=top+n*lh;
          if(y.style==="bold"){ g.strokeStyle=y.line; g.lineWidth=12*k; g.strokeText(r,0,ty); g.fillStyle=y.color; g.fillText(r,0,ty); }
          else if(y.style==="hollow"){ g.strokeStyle=y.color; g.lineWidth=7*k; g.strokeText(r,0,ty); }
          else if(y.style==="shadow"){ g.shadowColor=y.line+"b0"; g.shadowBlur=6*k; g.shadowOffsetX=g.shadowOffsetY=5*k; g.fillStyle=y.color; g.fillText(r,0,ty); }
          else { g.fillStyle=y.color; g.fillText(r,0,ty); }
        });
        g.restore();
        if(mine){ const bw=wide+36*k, bh=rows.length*lh+16*k; rects[y.id]={x:(cx-bw/2)/W, y:(y.y*H-bh/2)/H, w:bw/W, h:bh/H}; }
      }
      if(mine) paintLayer();
    },
    open(clip){ c=clip; busy=false; exact=null; return load(); },
    clear(){ c=null; info=null; cur=[]; sel=null; gen++; busy=false; drag=null; tv.stop(); o.box.innerHTML=""; changed(); },
    follow(clip){
      const was=c; c=clip;
      if(!info) return;
      if(busy && !clip.remaking && was && was.video!==clip.video){ busy=false; if(!dirty()) load(true); else paint(); return; }
      if(!!(was&&was.remaking)!==!!clip.remaking) paint();
    },
    // The tool is showing: the stage takes the player's place, at the playhead.
    shown(on){
      shown=on; o.stage.hidden=!on;
      const none=on && !o.src(); o.stage.querySelector(".ov-none").hidden=!none; view.hidden=none||!on;
      if(!on){ tv.stop(); layer.hidden=true; return; }
      const a=o.at(); if(a!=null) t=a;
      repaint();
    },
    at(x){ if(x==null || tv.playing() || drag) return; if(Math.abs(x-t)<0.001 && view.querySelector("canvas")) return; t=x; if(shown) repaint(); },
    // Play from the playhead: the Short as it'll be (the kept parts, with sound), text and all.
    play(){
      if(tv.playing()){ tv.stop(); return; }
      const p=o.ae.pieces(); if(!p.length || !o.src()) return;
      layer.hidden=true;
      tv.play(p, t<=p[0][0]||t>=p[p.length-1][1]-0.05 ? p[0][0] : t, null, "");
    },
    max:()=>info?info.max:6,
    stop(){ tv.stop(); }, playing:()=>tv.playing(), time:()=>t, unlock:()=>tv.unlock(),
    name:"text", dirty, count:()=>dirty()?1:0, canEdit:can,
    // The timeline's Overlays row (js/editor.js): every text, in time order, with when it starts on the Short's clock.
    track:()=>[...cur].sort((p,q)=>p.a-q.a).map(y=>({id:y.id, at:aeToFile(o.ae.pieces(),y.a), src:y.a, text:y.text.split("\n").join(" "), on:y.id===sel})),
    pick:id=>choose(id,true), add,
    // The editor's Undo / Redo.
    snap:()=>info?copy(cur):null, saved:()=>info?copy(info.overlays):null,
    restore(x){ if(!info||!x) return; cur=copy(x); if(sel && !item(sel)) sel=null; exGen++; exact=null; paint(); repaint(); changed(); },
    reset(){ if(info){ cur=copy(info.overlays); if(sel && !item(sel)) sel=null; exact=null; paint(); repaint(); changed(); } },
    // For shortDetails(): the request that saves them (remake: make the Short again now), and once it's sent.
    step:remake=>["/api/overlays/"+c.job+"/"+c.idx,{overlays:cur, remake}],
    sent(remake){ info.overlays=copy(cur); if(remake) busy=true; paint(); changed(); },
  };
  return api;
}
