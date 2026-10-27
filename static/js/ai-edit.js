// AI Edit, the editor's first tool (web/ai_edit.py, pipeline/ai_edit.py): which parts of the moment the Short keeps.
// The Short's words are shown as a transcript: click a word (or a pause) to cut it, Shift-click to cut a stretch.
// Quick actions do the same in one go: remove pauses, tighten the pacing, remove filler words, make it shorter (the AI
// keeps the best 30 / 45 / 60 seconds), suggested cuts (the AI, each with Apply), improve the hook (Details' Rewrite).
// Nothing is saved until the editor's Save: the change goes in as the first remake of shortDetails() (js/short-details.js,
// o.extra), so it and the other changes are made one after another. While changes wait, the player skips the parts
// that will be cut (where the current video has them) and the timeline marks them. Undo / Redo step through them.
// Times are the vlog's seconds; the server keeps the result as the Short's "pieces" (pipeline/pieces.py).
const AE_PAD=0.12, AE_PAUSE={long:0.7, tight:0.35}, AE_MIN_PIECE=0.3, AE_JOIN=0.05;  // pipeline/ai_edit.py, pieces.py
function aeNorm(ranges, s, e){  // pipeline/pieces.py normalize()
  const out=[];
  for(const [a0,b0] of [...ranges].sort((x,y)=>x[0]-y[0])){
    const a=Math.max(s,a0), b=Math.min(e,b0); if(b<=a) continue;
    if(out.length && a-out[out.length-1][1]<=AE_JOIN) out[out.length-1][1]=Math.max(out[out.length-1][1],b); else out.push([a,b]);
  }
  return out.filter(([a,b])=>b-a>=AE_MIN_PIECE).map(([a,b])=>[+a.toFixed(3),+b.toFixed(3)]);
}
function aeMinus(ranges, cuts, s, e){
  let out=ranges.map(r=>[...r]);
  for(const [c0,c1] of cuts){
    const nxt=[];
    for(const [a,b] of out){ if(c1<=a||c0>=b){ nxt.push([a,b]); continue; } if(c0>a) nxt.push([a,c0]); if(c1<b) nxt.push([c1,b]); }
    out=nxt;
  }
  return aeNorm(out,s,e);
}
const aeLen=p=>p.reduce((n,[a,b])=>n+b-a,0);
const aeIn=(p,t)=>p.some(([a,b])=>a<=t&&t<=b);
// A time in a list of pieces as a time in the video they make (or null if it isn't in them), and back.
function aeToFile(p,t){ let at=0; for(const [a,b] of p){ if(a<=t&&t<=b) return at+t-a; at+=b-a; } return null; }
function aeToSrc(p,t){ let at=0; for(const [a,b] of p){ if(t<=at+b-a) return a+Math.max(0,t-at); at+=b-a; } return p.length?p[p.length-1][1]:0; }
// o: {box, video, strip, onChange() (something changed: the editor's save state), onHook() (open Details' Rewrite)}
function aiEdit(o){
  let c=null, info=null, toks=[], gaps=[], hist=[], fut=[], gen=0, video="", busy=false, last=null, sugs=null, note="", nowTok=-1;
  const S=()=>info.start, E=()=>info.end;
  const changed=()=>{ paintSum(); paintMarks(); o.onChange&&o.onChange(); };
  const snap=()=>toks.map(t=>t.cut);
  function remember(){ hist.push(snap()); if(hist.length>100) hist.shift(); fut=[]; }
  function restore(st){ st.forEach((v,i)=>{ if(toks[i]) toks[i].cut=v; }); paintTokens(); changed(); }
  // The words and the pauses between them, from what's kept now.
  function build(){
    toks=[]; gaps=[];
    const wt=info.words.map(w=>({k:"w", w:w.w, s:w.s, e:w.e, filler:w.filler, cut:!w.kept}));
    // a gap between two words (L, R; null at the Short's start / end), and its pause chip when it's long enough
    const gap=(a,b,L,R)=>{
      let t=null;
      if(b-a>=AE_PAUSE.tight){
        const a2=L?a+AE_PAD:a, b2=R?b-AE_PAD:b;  // a breath stays next to speech; nothing before the first word / after the last
        if(b2-a2>=0.15) t={k:"p", a:a2, b:b2, len:b-a, cut:!aeIn(info.pieces,(a2+b2)/2)};
      }
      gaps.push({a,b,L,R,t}); if(t) toks.push(t);
    };
    if(!wt.length) return;
    gap(S(), wt[0].s, null, wt[0]);
    wt.forEach((w,i)=>{ toks.push(w); gap(w.e, wt[i+1]?wt[i+1].s:E(), w, wt[i+1]||null); });
  }
  // What would be kept with the cuts as they are on the page.
  function pending(){
    const cuts=[];
    for(const t of toks) if(t.k==="w" && t.cut) cuts.push([t.s,t.e]);
    for(const g of gaps){
      const lc=g.L?g.L.cut:true, rc=g.R?g.R.cut:true;
      if(lc && rc && (g.L||g.R)) cuts.push([g.a,g.b]);
      else if(g.t && g.t.cut) cuts.push([g.t.a,g.t.b]);
    }
    return aeMinus([[S(),E()]], cuts, S(), E());
  }
  const same=(p,q)=>p.length===q.length && p.every((r,i)=>Math.abs(r[0]-q[i][0])<0.02 && Math.abs(r[1]-q[i][1])<0.02);
  const dirty=()=>!!info && toks.length>0 && !same(pending(), info.pieces);
  async function load(){
    const my=++gen, cl=c; info=null; toks=[]; gaps=[]; hist=[]; fut=[]; sugs=null; note=""; last=null;
    o.box.innerHTML='<p class="qr-wait">Getting the words of this Short...</p>'; changed();
    let j; try{ const r=await fetch("/api/ai-edit/"+cl.job+"/"+cl.idx); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ if(my===gen) o.box.innerHTML='<p class="qr-wait">'+esc(e.message||"Couldn't load the words. Check your internet connection, then try again.")+'</p>'; return; }
    if(my!==gen) return;
    info=j; video=cl.video; note=j.note||""; build(); paint(); changed();
  }
  // ---- drawing
  function paint(){
    const can=info.can_apply && !busy && !(c&&c.remaking);
    const nPause=k=>toks.filter(t=>t.k==="p" && t.len>=AE_PAUSE[k]).length, nFill=toks.filter(t=>t.k==="w"&&t.filler).length;
    const len=aeLen(info.pieces);
    const short=[30,45,60].filter(n=>n<len-1);
    o.box.innerHTML=
      (info.can_apply?'':'<div class="ed-note ae-warn">'+esc(info.why_not)+'</div>')+
      (c&&c.remaking||busy?'<div class="ed-fin-wait"><span class="spin" aria-hidden="true"></span><span>Remaking the Short with your edits...</span></div>':'')+
      '<div class="ae-sum" id="aeSum" role="status"></div>'+
      (info.words.length?'':'<p class="ae-empty">There\'s no talking in this Short, so there are no words to cut by. Trim is coming next.</p>')+
      '<div class="ae-acts">'+
        aeBtn("long","graphic_eq","Remove pauses",nPause("long")?nPause("long")+" over 0.7 s":"None found",can&&nPause("long"))+
        aeBtn("tight","timer","Tighten pacing",nPause("tight")?"Every pause over 0.35 s":"Already tight",can&&nPause("tight"))+
        aeBtn("fill","content_cut","Remove filler words",nFill?nFill+" um / uh":"None found",can&&nFill)+
        aeBtn("cuts","auto_awesome","Suggest cuts","Repeats, false starts, slow parts",can&&info.words.length)+
        aeBtn("hook","bolt","Improve hook","Three new hooks to choose from",!(c&&c.remaking))+
      '</div>'+
      '<div class="ae-short"><span><span class="ms" aria-hidden="true">trending_up</span>Make it shorter</span>'+
        (short.length?short.map(n=>'<button type="button" class="ghost sm" data-short="'+n+'"'+(can?'':' disabled')+'>'+n+' s</button>').join(""):'<small>It\'s already under 30 seconds</small>')+'</div>'+
      '<div class="err" id="aeErr" role="alert"></div>'+
      '<div class="ae-note" id="aeNote"'+(note?'':' hidden')+'>'+esc(note)+'</div>'+
      '<div class="ae-sugs" id="aeSugs"></div>'+
      (info.words.length?'<div class="ae-tr-head"><b>Transcript</b>'+
        '<button type="button" class="linkbtn" id="aeAll"'+(can?'':' disabled')+'>Keep everything</button></div>'+
        '<p class="ae-help">Click a word or a pause to cut it; click again to keep it. Shift-click to cut a whole stretch.</p>'+
        '<div class="ae-tr" id="aeTr" aria-label="Transcript of this Short"></div>':'');
    o.box.querySelectorAll(".ae-act").forEach(b=>b.onclick=()=>act(b.dataset.a));
    o.box.querySelectorAll("[data-short]").forEach(b=>b.onclick=()=>shorten(+b.dataset.short,b));
    const all=$("aeAll"); if(all) all.onclick=()=>{ remember(); toks.forEach(t=>t.cut=false); paintTokens(); changed(); };
    paintTokens(); paintSugs(); paintSum();
  }
  function aeBtn(a,icon,name,sub,on){
    return '<button type="button" class="ae-act" data-a="'+a+'"'+(on?'':' disabled')+'><span class="ms" aria-hidden="true">'+icon+'</span>'+
      '<span><b>'+esc(name)+'</b><small>'+esc(sub)+'</small></span></button>';
  }
  function paintTokens(){
    const tr=$("aeTr"); if(!tr) return;
    const can=info.can_apply && !busy && !(c&&c.remaking);
    tr.innerHTML=toks.map((t,i)=>t.k==="w"
      ? '<button type="button" class="ae-w'+(t.cut?' cut':'')+(t.filler?' fill':'')+(i===nowTok?' now':'')+'" data-t="'+i+'" aria-pressed="'+t.cut+'"'+(can?'':' disabled')+'>'+esc(t.w)+'</button>'
      : '<button type="button" class="ae-p'+(t.cut?' cut':'')+'" data-t="'+i+'" aria-pressed="'+t.cut+'" title="A pause of '+t.len.toFixed(1)+' seconds"'+(can?'':' disabled')+'>'+t.len.toFixed(1)+' s</button>').join(" ");
    tr.querySelectorAll("button").forEach(b=>b.onclick=e=>click(+b.dataset.t,e.shiftKey));
  }
  function click(i,range){
    remember();
    const to=!toks[i].cut;
    if(range && last!=null){ const [a,b]=[Math.min(last,i),Math.max(last,i)]; for(let k=a;k<=b;k++) toks[k].cut=to; }
    else toks[i].cut=to;
    last=i; paintTokens(); changed();
  }
  function paintSum(){
    const el=$("aeSum"); if(!el||!info) return;
    const now=aeLen(info.pieces), then=aeLen(pending()), d=Math.round(now-then);
    el.innerHTML= dirty() ? 'Now <b>'+fmt(now)+'</b><span class="ms" aria-hidden="true">arrow_forward</span><b>'+fmt(then)+'</b> after your edits'+
      (d?' <span class="ae-d">('+(d>0?"−":"+")+Math.abs(d)+' s)</span>':'')+(then<info.min?' <span class="ae-bad">At least '+info.min+' s</span>':'')
      : 'This Short is <b>'+fmt(now)+'</b> long'+(info.pieces.length>1?' ('+info.pieces.length+' parts)':'');
  }
  // ---- quick actions
  function act(a){
    $("aeErr").textContent="";
    if(a==="hook"){ o.onHook&&o.onHook(); return; }
    if(a==="cuts"){ suggest(); return; }
    remember();
    if(a==="fill") toks.forEach(t=>{ if(t.k==="w"&&t.filler) t.cut=true; });
    else toks.forEach(t=>{ if(t.k==="p" && t.len>=AE_PAUSE[a]) t.cut=true; });
    paintTokens(); changed();
  }
  // Cuts from the AI (vlog seconds) on the page: whatever is inside them is cut.
  function cutRange(a,b){ toks.forEach(t=>{ const m=t.k==="w"?(t.s+t.e)/2:(t.a+t.b)/2; if(a<=m&&m<=b) t.cut=true; }); }
  function keepOnly(p){ toks.forEach(t=>{ const m=t.k==="w"?(t.s+t.e)/2:(t.a+t.b)/2; t.cut=!aeIn(p,m); }); }
  async function ask(body,btn,label){
    $("aeErr").textContent=""; btn.disabled=true; const was=btn.innerHTML; btn.textContent=label;
    let r,j={}; try{ r=await fetch("/api/ai-edit/"+c.job+"/"+c.idx+"/suggest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); j=await r.json().catch(()=>({})); }
    catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
    btn.disabled=false; btn.innerHTML=was;
    if(!r.ok){ $("aeErr").textContent=j.error||"Couldn't get ideas from the AI. Please try again."; return null; }
    return j;
  }
  async function shorten(n,btn){
    const my=gen, j=await ask({kind:"shorten",target:n},btn,"Choosing..."); if(!j||my!==gen) return;
    remember(); keepOnly(j.pieces); note=(j.ai?"AI: ":"")+(j.why||("Kept about "+n+" seconds."));
    $("aeNote").textContent=note; $("aeNote").hidden=false; paintTokens(); changed();
  }
  async function suggest(){
    const btn=o.box.querySelector('[data-a="cuts"]'), my=gen, j=await ask({kind:"cuts"},btn,"Reading...");
    if(!j||my!==gen) return;
    sugs=j.cuts; paintSugs();
    if(!sugs.length){ $("aeNote").textContent="The AI didn't find anything worth cutting. It's tight already."; $("aeNote").hidden=false; }
  }
  function paintSugs(){
    const box=$("aeSugs"); if(!box) return;
    if(!sugs||!sugs.length){ box.innerHTML=""; return; }
    box.innerHTML='<div class="ae-sugs-head"><b>Suggested cuts</b>'+(sugs.length>1?'<button type="button" class="linkbtn" id="aeSugAll">Apply all</button>':'')+'</div>'+
      sugs.map((x,i)=>'<div class="ae-sug"><div class="ae-sug-top"><span class="cl-pill">'+esc(x.kind)+'</span><span class="ae-sec">−'+x.seconds+' s</span></div>'+
        '<q>'+esc(x.text)+'</q><p>'+esc(x.why)+'</p><div class="ae-sug-acts"><button type="button" class="ghost sm" data-sug="'+i+'">Apply</button>'+
        '<button type="button" class="linkbtn" data-drop="'+i+'">Dismiss</button></div></div>').join("");
    box.querySelectorAll("[data-sug]").forEach(b=>b.onclick=()=>{ remember(); const x=sugs[+b.dataset.sug]; cutRange(x.start,x.end); sugs.splice(+b.dataset.sug,1); paintSugs(); paintTokens(); changed(); });
    box.querySelectorAll("[data-drop]").forEach(b=>b.onclick=()=>{ sugs.splice(+b.dataset.drop,1); paintSugs(); });
    const all=$("aeSugAll"); if(all) all.onclick=()=>{ remember(); sugs.forEach(x=>cutRange(x.start,x.end)); sugs=[]; paintSugs(); paintTokens(); changed(); };
  }
  // ---- the player and the timeline: the video is the Short as saved (info.pieces); pending cuts are skipped in it
  function paintMarks(){
    const strip=o.strip; if(!strip) return;
    strip.querySelectorAll(".ae-mark").forEach(m=>m.remove());
    if(!info || !dirty()) return;
    const cur=info.pieces, total=aeLen(cur), keep=pending();
    for(const [a,b] of aeMinus(cur, keep, S(), E())){
      const x=aeToFile(cur,a), y=aeToFile(cur,b); if(x==null||y==null||!total) continue;
      const m=document.createElement("span"); m.className="ae-mark"; m.title="Cut when you save";
      m.style.left=(x/total*100)+"%"; m.style.width=Math.max(.4,(y-x)/total*100)+"%"; strip.appendChild(m);
    }
  }
  o.video.addEventListener("timeupdate",()=>{
    if(!info || o.video.hidden) return;
    const src=aeToSrc(info.pieces,o.video.currentTime);
    if(dirty() && !o.video.paused){
      const keep=pending();
      if(!aeIn(keep,src)){  // a part that will be cut: jump to the next kept part this video has
        const next=keep.map(p=>p[0]).find(a=>a>src && aeToFile(info.pieces,a)!=null);
        if(next==null){ o.video.pause(); return; }
        o.video.currentTime=aeToFile(info.pieces,next)+0.01; return;
      }
    }
    const k=toks.findIndex(t=>t.k==="w" && t.s<=src && src<=t.e+0.05);
    if(k!==nowTok){ const tr=$("aeTr"); nowTok=k;
      if(tr){ tr.querySelectorAll(".ae-w.now").forEach(b=>b.classList.remove("now")); const b=tr.querySelector('[data-t="'+k+'"]'); if(b) b.classList.add("now"); } }
  });
  const api={
    open(clip){ c=clip; busy=false; return load(); },
    clear(){ c=null; info=null; toks=[]; gen++; busy=false; o.box.innerHTML=""; changed(); },
    // The clip list was loaded again: after a remake (a new video file), read the words and parts again.
    follow(clip){
      const was=c; c=clip;
      if(!info) return;
      if(clip.video!==video && !clip.remaking){ busy=false; if(!dirty()) load(); else video=clip.video; return; }
      if(!!(was&&was.remaking)!==!!clip.remaking) paint();
    },
    dirty, count:()=>dirty()?1:0,
    canUndo:()=>hist.length>0, canRedo:()=>fut.length>0,
    undo(){ if(!hist.length) return; fut.push(snap()); restore(hist.pop()); },
    redo(){ if(!fut.length) return; hist.push(snap()); restore(fut.pop()); },
    reset(){ if(info){ build(); hist=[]; fut=[]; sugs=null; note=""; paint(); changed(); } },
    // For shortDetails(): the remake to make on Save, and what happens once it's sent.
    step(){
      if(!dirty()) return null;
      const p=pending();
      if(aeLen(p)<info.min) return {error:"Your edits would leave less than "+info.min+" seconds. Keep a little more."};
      const whole=p.length===1 && Math.abs(p[0][0]-S())<0.02 && Math.abs(p[0][1]-E())<0.02;
      return ["/api/ai-edit/"+c.job+"/"+c.idx+"/apply",{pieces:whole?null:p}];
    },
    sent(){ info.pieces=pending(); busy=true; hist=[]; fut=[]; sugs=null; paint(); changed(); },
  };
  return api;
}
