// AI Edit, the editor's first tool (web/ai_edit.py, pipeline/ai_edit.py): which parts of the moment the Short keeps.
// The Short's words are shown as a transcript: click a word (or a pause) to cut it, Shift-click to cut a stretch.
// Quick actions do the same in one go: remove pauses, tighten the pacing, remove filler words, make it shorter (the AI
// keeps the best 30 / 45 / 60 seconds), improve the hook (Details' Rewrite). (The AI's suggested cuts were removed: not
// reliable enough.)
// Nothing is saved until the editor's Save: the change goes in as the first remake of shortDetails() (js/short-details.js,
// o.extra), so it and the other changes are made one after another. While changes wait, the player skips the parts
// that will be cut (where the current video has them). Undo / Redo step through them.
// It also keeps the pieces for the editor's timeline (Trim, js/editor.js: pieces() / setPieces()): one list of what the
// Short will keep, whichever tool changed it, so Undo, the save state and Save cover both. The timeline can reach past
// the moment, anywhere in the vlog; the words shown are the moment's (after a save, the moment is the new reach).
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
// o: {box, video, onChange() (something changed: the editor's save state and timeline), onHook() (open Details'
// Rewrite), onLoad(info) (the words and pieces are in: the editor lays out its timeline)}
function aiEdit(o){
  let c=null, info=null, cur=[], toks=[], gaps=[], hist=[], fut=[], gen=0, video="", busy=false, last=null, note="", nowTok=-1;
  const S=()=>info.start, E=()=>info.end, DUR=()=>Math.max(info.duration||0, E());
  const changed=()=>{ paintSum(); o.onChange&&o.onChange(); };
  const same=(p,q)=>p.length===q.length && p.every((r,i)=>Math.abs(r[0]-q[i][0])<0.02 && Math.abs(r[1]-q[i][1])<0.02);
  const mid=t=>t.k==="w"?(t.s+t.e)/2:(t.a+t.b)/2;
  const isCut=t=>!aeIn(cur,mid(t));  // a word or pause is cut when its middle isn't in a kept piece
  // What the Short will keep from now on (one step to undo), tidied: in order, inside the vlog, too-short bits dropped.
  function set(p){
    p=aeNorm(p,0,DUR());
    if(!p.length || same(p,cur)) return false;
    hist.push(cur); if(hist.length>100) hist.shift(); fut=[];
    cur=p; paintTokens(); changed(); return true;
  }
  // The words and the pauses between them (each word knows the gap on each side).
  function build(){
    toks=[]; gaps=[];
    const wt=info.words.map(w=>({k:"w", w:w.w, s:w.s, e:w.e, filler:w.filler}));
    // a gap between two words (L, R; null at the moment's start / end), and its pause chip when it's long enough
    const gap=(a,b,L,R)=>{
      let t=null;
      if(b-a>=AE_PAUSE.tight){
        const a2=L?a+AE_PAD:a, b2=R?b-AE_PAD:b;  // a breath stays next to speech; nothing before the first word / after the last
        if(b2-a2>=0.15) t={k:"p", a:a2, b:b2, len:b-a};
      }
      const g={a,b,L,R,t}; gaps.push(g); if(L) L.gr=g; if(R) R.gl=g; if(t) toks.push(t);
    };
    if(!wt.length) return;
    gap(S(), wt[0].s, null, wt[0]);
    wt.forEach((w,i)=>{ toks.push(w); gap(w.e, wt[i+1]?wt[i+1].s:E(), w, wt[i+1]||null); });
    toks.forEach((t,i)=>t.i=i);
  }
  // Cut (to=true) or keep these tokens, in one step. Cutting a word also cuts the gap beside it when the word on the
  // other side is cut too (or there's none), so no silence is left between two cuts; keeping a word brings back the
  // breath next to it (a short gap: the whole gap, if the other side is kept).
  function mark(idx, to){
    const fl=toks.map(isCut), ranges=[];
    idx.forEach(i=>fl[i]=to);
    const cutSide=w=>w?fl[w.i]:true;
    for(const i of idx){
      const t=toks[i];
      if(t.k==="p"){ ranges.push([t.a,t.b]); continue; }
      ranges.push([t.s,t.e]);
      for(const g of [t.gl,t.gr]){
        if(!g) continue;
        const other=g===t.gl?g.L:g.R;
        if(to){ if(cutSide(other)) ranges.push([g.a,g.b]); }
        else if(!g.t){ if(!other || !fl[other.i]) ranges.push([g.a,g.b]); }
        else ranges.push(g===t.gl?[g.t.b,g.b]:[g.a,g.t.a]);
      }
    }
    return set(to ? aeMinus(cur,ranges,0,DUR()) : cur.concat(ranges));
  }
  const pending=()=>cur;
  const dirty=()=>!!info && !same(cur, info.pieces);
  async function load(){
    const my=++gen, cl=c; info=null; cur=[]; toks=[]; gaps=[]; hist=[]; fut=[]; note=""; last=null;
    o.box.innerHTML='<p class="qr-wait">Getting the words of this Short...</p>'; changed();
    let j; try{ const r=await fetch("/api/ai-edit/"+cl.job+"/"+cl.idx); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ if(my===gen) o.box.innerHTML='<p class="qr-wait">'+esc(e.message||"Couldn't load the words. Check your internet connection, then try again.")+'</p>'; return; }
    if(my!==gen) return;
    info=j; cur=info.pieces.map(p=>[...p]); video=cl.video; note=j.note||""; build(); paint(); changed();
    o.onLoad&&o.onLoad(info);
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
      (info.words.length?'':'<p class="ae-empty">There\'s no talking in this Short, so there are no words to cut by. Use Trim to cut it on the timeline.</p>')+
      '<div class="ae-acts">'+
        aeBtn("long","graphic_eq","Remove pauses",nPause("long")?nPause("long")+" over 0.7 s":"None found",can&&nPause("long"))+
        aeBtn("tight","timer","Tighten pacing",nPause("tight")?"Every pause over 0.35 s":"Already tight",can&&nPause("tight"))+
        aeBtn("fill","content_cut","Remove filler words",nFill?nFill+" um / uh":"None found",can&&nFill)+
        aeBtn("hook","bolt","Improve hook","Three new hooks to choose from",!(c&&c.remaking))+
      '</div>'+
      '<div class="ae-short"><span><span class="ms" aria-hidden="true">trending_up</span>Make it shorter</span>'+
        (short.length?short.map(n=>'<button type="button" class="ghost sm" data-short="'+n+'"'+(can?'':' disabled')+'>'+n+' s</button>').join(""):'<small>It\'s already under 30 seconds</small>')+'</div>'+
      '<div class="err" id="aeErr" role="alert"></div>'+
      '<div class="ae-note" id="aeNote"'+(note?'':' hidden')+'>'+esc(note)+'</div>'+
      (info.words.length?'<div class="ae-tr-head"><b>Transcript</b>'+
        '<button type="button" class="linkbtn" id="aeAll"'+(can?'':' disabled')+'>Keep everything</button></div>'+
        '<p class="ae-help">Click a word or a pause to cut it; click again to keep it. Shift-click to cut a whole stretch.</p>'+
        '<div class="ae-tr" id="aeTr" aria-label="Transcript of this Short"></div>':'');
    o.box.querySelectorAll(".ae-act").forEach(b=>b.onclick=()=>act(b.dataset.a));
    o.box.querySelectorAll("[data-short]").forEach(b=>b.onclick=()=>shorten(+b.dataset.short,b));
    const all=$("aeAll"); if(all) all.onclick=()=>set(cur.concat([[S(),E()]]));
    paintTokens(); paintSum();
  }
  function aeBtn(a,icon,name,sub,on){
    return '<button type="button" class="ae-act" data-a="'+a+'"'+(on?'':' disabled')+'><span class="ms" aria-hidden="true">'+icon+'</span>'+
      '<span><b>'+esc(name)+'</b><small>'+esc(sub)+'</small></span></button>';
  }
  function paintTokens(){
    const tr=$("aeTr"); if(!tr) return;
    const can=info.can_apply && !busy && !(c&&c.remaking);
    tr.innerHTML=toks.map((t,i)=>{ const x=isCut(t); return t.k==="w"
      ? '<button type="button" class="ae-w'+(x?' cut':'')+(t.filler?' fill':'')+(i===nowTok?' now':'')+'" data-t="'+i+'" aria-pressed="'+x+'"'+(can?'':' disabled')+'>'+esc(t.w)+'</button>'
      : '<button type="button" class="ae-p'+(x?' cut':'')+'" data-t="'+i+'" aria-pressed="'+x+'" title="A pause of '+t.len.toFixed(1)+' seconds"'+(can?'':' disabled')+'>'+t.len.toFixed(1)+' s</button>'; }).join(" ");
    tr.querySelectorAll("button").forEach(b=>b.onclick=e=>click(+b.dataset.t,e.shiftKey));
  }
  function click(i,range){
    const to=!isCut(toks[i]), idx=[];
    if(range && last!=null){ for(let k=Math.min(last,i);k<=Math.max(last,i);k++) idx.push(k); } else idx.push(i);
    last=i; mark(idx,to);
  }
  function paintSum(){
    const el=$("aeSum"); if(!el||!info) return;
    const now=aeLen(info.pieces), then=aeLen(pending()), d=Math.round(now-then);
    el.innerHTML= dirty() ? 'Now <b>'+fmt(now)+'</b><span class="ms" aria-hidden="true">arrow_forward</span><b>'+fmt(then)+'</b> after your edits'+
      (d?' <span class="ae-d">('+(d>0?"−":"+")+Math.abs(d)+' s)</span>':'')+(then<info.min?' <span class="ae-bad">At least '+info.min+' s</span>':'')+
      (then>info.max?' <span class="ae-bad">At most '+fmt(info.max)+'</span>':'')
      : 'This Short is <b>'+fmt(now)+'</b> long'+(info.pieces.length>1?' ('+info.pieces.length+' parts)':'');
  }
  // ---- quick actions
  function act(a){
    $("aeErr").textContent="";
    if(a==="hook"){ o.onHook&&o.onHook(); return; }
    mark(toks.filter(t=>a==="fill" ? t.k==="w"&&t.filler : t.k==="p"&&t.len>=AE_PAUSE[a]).map(t=>t.i), true);
  }
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
    set(j.pieces); note=(j.ai?"AI: ":"")+(j.why||("Kept about "+n+" seconds."));
    $("aeNote").textContent=note; $("aeNote").hidden=false;
  }
  // ---- the player: the video is the Short as saved (info.pieces); pending cuts are skipped in it
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
    undo(){ if(!hist.length) return; fut.push(cur); cur=hist.pop(); paintTokens(); changed(); },
    redo(){ if(!fut.length) return; hist.push(cur); cur=fut.pop(); paintTokens(); changed(); },
    reset(){ if(info){ cur=info.pieces.map(p=>[...p]); hist=[]; fut=[]; note=""; paint(); changed(); } },
    // For the timeline (js/editor.js): the pieces the Short will keep, the ones its video has now, and a change
    info:()=>info, pieces:()=>cur, saved:()=>info?info.pieces:null, setPieces:p=>!!info && set(p),
    // The editor's Undo / Redo (js/editor.js keeps one history for every tool): put these pieces back as they were.
    restore(p){ if(!info||!p) return; cur=p.map(x=>[...x]); paintTokens(); changed(); },
    canEdit:()=>!!info && info.can_apply && !busy && !(c&&c.remaking),
    // For shortDetails(): the remake to make on Save, and what happens once it's sent.
    step(){
      if(!dirty()) return null;
      const p=pending();
      if(aeLen(p)<info.min) return {error:"Your edits would leave less than "+info.min+" seconds. Keep a little more."};
      if(aeLen(p)>info.max) return {error:"A Short can be at most 3 minutes long. Trim it a little more."};
      const whole=p.length===1 && Math.abs(p[0][0]-S())<0.02 && Math.abs(p[0][1]-E())<0.02;
      return ["/api/ai-edit/"+c.job+"/"+c.idx+"/apply",{pieces:whole?null:p}];
    },
    sent(){ info.pieces=cur.map(p=>[...p]); busy=true; hist=[]; fut=[]; paint(); changed(); },
  };
  return api;
}
