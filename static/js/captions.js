// Captions, an editor tool (web/captions.py, pipeline/captions.py): how the Short's burned-in captions look and read.
// Presets, then the look (font, size, colours, outline or box, capitals), the spoken word (highlight colour, grow, or
// none), how lines come in, where they sit, words per line, timing (earlier / later), and the words themselves: click
// a word to change it, leave it out, make it pop or start a new line there. Word changes key on the word's place in the
// vlog's transcript ("i", from AI Edit's words), so cuts and trims never move them to another word.
// A few lines can look different from the rest: pick them (a line's time here, or its block on the timeline's Captions
// row, track() / pick(); Shift, Ctrl or ⌘ adds more) and give them their own font, size, colours, capitals or place.
// That look is kept on each of their words ("styles"); a line takes its first word's (pipeline/captions.py).
// The player plays the Short as saved; the preview is one frame drawn by the server the way the Short is made (the
// vlog's frame, the same .ass file, libass), at the player's time, with the cuts waiting to be saved. What a frame can't
// show (lines coming in, the spoken word) plays as a few seconds of video from just before the line there: "Play it",
// and by itself after "Lines come in" or "Spoken word" changes. It plays PLAYS times and stops; Pause / Play, and Slow
// (half speed, to see a quick effect).
// Nothing is saved until the editor's Save (shortDetails() o.caps): on its own it remakes the Short; with a cut or a new
// hook the captions are saved first and that remake makes them. Undo / Redo (js/editor.js) step through the changes.
// o: {box, video, ae (the editor's aiEdit(): words and pieces), onChange(), onLoad()}
function captionEdit(o){
  let c=null, info=null, cur=null, gen=0, busy=false, shown=false, word=null, sel=new Set(), pv={key:"", ctl:null, timer:null, motion:false, loops:0, slow:false};
  const PLAYS=3;
  const LINE=["font","size","color","hi","line","upper","bottom"];  // pipeline/captions.py LINE_KEYS
  const copy=x=>JSON.parse(JSON.stringify(x)), same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const changed=()=>o.onChange&&o.onChange();
  const dirty=()=>!!info && !same(cur, info.captions);
  const can=()=>!!info && info.can_apply && !busy && !(c&&c.remaking);
  const STYLE=["font","size","color","hi","line","outline","shadow","box","upper","highlight","anim","words"];
  const POS=[["Top",1200],["Middle",860],["Bottom",560]];
  function set(patch){ if(!can()) return; if("anim" in patch || "highlight" in patch) pv.motion=true; cur={...cur,...patch}; paint(); changed(); }
  // quiet (after a remake): what's shown stays until the new settings are in (no "Getting...", no blink)
  async function load(quiet){
    const my=++gen, cl=c, keep=quiet&&info;
    if(!keep){ info=null; cur=null; word=null; sel=new Set(); pv.key="";
      o.box.innerHTML='<p class="qr-wait">Getting the captions...</p>'; changed(); }
    let j; try{ const r=await fetch("/api/captions/"+cl.job+"/"+cl.idx); j=await r.json(); if(!r.ok) throw new Error(j.error||""); }
    catch(e){ if(my===gen && !keep) o.box.innerHTML='<p class="qr-wait">'+esc(e.message||"Couldn't load the captions. Check your internet connection, then try again.")+'</p>'; return; }
    if(my!==gen) return;
    info=j; cur=copy(j.captions); paint(); changed();
    o.onLoad&&o.onLoad();
  }
  // ---- the words, in caption lines (pipeline/captions.py lines_of(); a word left out stays here, struck through)
  function words(){
    const ai=o.ae.info(); if(!ai) return [];
    const keep=o.ae.pieces();
    return ai.words.filter(w=>w.i!=null && aeIn(keep,(w.s+w.e)/2));
  }
  const textOf=w=>(cur.edits[w.i]!=null?cur.edits[w.i]:w.w);
  function lines(){
    const out=[], br=new Set(cur.br); let n=0;
    for(const w of words()){
      const hid=!textOf(w).trim();
      if(!hid && (!out.length || n>=cur.words || br.has(w.i))){ out.push([]); n=0; }
      if(!out.length) out.push([]);
      out[out.length-1].push(w); if(!hid) n++;
    }
    return out;
  }
  // A line's key: its first word that's shown (whose look the line takes). Lines of nothing but left-out words: none.
  const keyOf=l=>{ const w=l.find(x=>textOf(x).trim()); return w?w.i:null; };
  const lookOf=k=>({...cur, ...(cur.styles[k]||{})});
  const picked=()=>lines().filter(l=>sel.has(keyOf(l)));
  // Give the picked lines' words this look (a value equal to the rest's is dropped: "the same as the rest").
  function setLine(patch){
    const st=copy(cur.styles);
    for(const l of picked()) for(const w of l){
      const one={...(st[w.i]||{}), ...patch};
      for(const k of Object.keys(patch)) if(same(one[k],cur[k])) delete one[k];
      if(Object.keys(one).length) st[w.i]=one; else delete st[w.i];
    }
    set({styles:st});
  }
  function pick(k,add){
    if(k==null) return;
    if(add){ sel.has(k)?sel.delete(k):sel.add(k); } else sel = sel.size===1&&sel.has(k) ? new Set() : new Set([k]);
    const l=lines().find(x=>keyOf(x)===k);
    if(sel.has(k) && l) seek(l.find(w=>w.i===k).s);
    paint(); changed();
    const box=$("cpLine"); if(box) box.scrollIntoView({block:"nearest"});
  }
  // ---- drawing
  const seg=(key,opts)=>'<div class="cp-seg" role="group">'+opts.map(([label,v])=>
    '<button type="button" data-k="'+key+'" data-v="'+esc(String(v))+'" aria-pressed="'+(cur[key]===v)+'">'+esc(label)+'</button>').join("")+'</div>';
  const row=(label,body,hint)=>'<div class="cp-row"><span class="cp-lab">'+esc(label)+(hint?'<small>'+esc(hint)+'</small>':'')+'</span>'+body+'</div>';
  const range=(key,min,max,step,show)=>'<span class="cp-range"><input type="range" data-k="'+key+'" min="'+min+'" max="'+max+'" step="'+step+'" value="'+cur[key]+'" aria-label="'+esc(key)+'">'+
    '<output>'+esc(show(cur[key]))+'</output></span>';
  const color=(key,label)=>'<label class="cp-col"><input type="color" data-k="'+key+'" value="'+esc(cur[key].toLowerCase())+'"><span>'+esc(label)+'</span></label>';
  const isPreset=p=>STYLE.every(k=>same(cur[k],p.captions[k]));
  function presetHTML(p){
    const x=p.captions, up=t=>x.upper?t.toUpperCase():t;
    const sh=x.box?'background:'+x.line+'b0;':'text-shadow:0 0 '+Math.min(3,x.outline/3)+'px '+x.line+','+(x.outline?'0 0 1px '+x.line:'0 0 0 transparent')+';';
    return '<button type="button" class="cp-pre" data-p="'+esc(p.id)+'" aria-pressed="'+isPreset(p)+'">'+
      '<span class="cp-pre-s cp-f-'+esc(x.font)+'" style="color:'+x.color+';'+sh+'">'+esc(up("the "))+
        '<i style="color:'+(x.highlight==="none"?x.color:x.hi)+'">'+esc(up("best"))+'</i>'+esc(up(" view"))+'</span>'+
      '<b>'+esc(p.name)+'</b></button>';
  }
  function paint(){
    if(!info){ return; }
    const ok=can(), off=!cur.on, was=$("cpImg"), pic=was&&was.getAttribute("src"), picT=pic&&$("cpPrevT").textContent;
    o.box.innerHTML=
      (info.can_apply?'':'<div class="ed-note ae-warn">'+esc(info.why_not)+'</div>')+
      (c&&c.remaking||busy?'<div class="ed-fin-wait"><span class="spin" aria-hidden="true"></span><span>Remaking the Short with your edits...</span></div>':'')+
      '<label class="cp-on"><input type="checkbox" id="cpOn"'+(cur.on?' checked':'')+'><span><b>Show captions</b><small>Off: no captions, the hook stays</small></span></label>'+
      lineHTML()+
      '<figure class="cp-prev'+(off?' off':'')+'" id="cpPrev"><img id="cpImg" alt="Preview of the captions at the player\'s time">'+
        '<video id="cpVid" muted playsinline hidden aria-label="The captions moving, a few seconds from the line at the player\'s time"></video>'+
        '<figcaption><span id="cpPrevT">Preview at the player\'s time</span>'+
          '<button type="button" class="linkbtn" id="cpPlay" title="A few seconds of the captions moving: lines coming in, the spoken word"><span class="ms" aria-hidden="true">play_arrow</span><span>Play it</span></button>'+
          '<button type="button" class="linkbtn" id="cpSlow" aria-pressed="'+pv.slow+'" hidden title="Half speed, to see a quick effect"><span class="ms" aria-hidden="true">timer</span>Slow</button></figcaption></figure>'+
      '<div class="cp-body'+(off?' off':'')+'">'+
      '<h3 class="cp-h">Presets</h3><div class="cp-pres">'+info.presets.map(presetHTML).join("")+'</div>'+
      '<h3 class="cp-h">Look</h3>'+
      row("Font",'<select data-k="font" aria-label="Font">'+info.fonts.map(f=>'<option value="'+esc(f.id)+'"'+(f.id===cur.font?' selected':'')+'>'+esc(f.name)+'</option>').join("")+'</select>')+
      row("Size",range("size",40,160,2,v=>v))+
      row("Colours",'<div class="cp-cols">'+color("color","Text")+color("hi","Highlight")+color("line",cur.box?"Box":"Outline")+'</div>')+
      row(cur.box?"Box":"Outline",range("outline",0,14,1,v=>v?v+" px":"None"))+
      row("",'<label class="cp-chk"><input type="checkbox" data-k="box"'+(cur.box?' checked':'')+'>A box behind the words</label>'+
        '<label class="cp-chk"><input type="checkbox" data-k="upper"'+(cur.upper?' checked':'')+'>ALL CAPITALS</label>')+
      '<h3 class="cp-h">Motion</h3>'+
      row("Spoken word",seg("highlight",[["Colour","color"],["Colour + grow","grow"],["None","none"]]))+
      row("Lines come in",seg("anim",[["At once","none"],["Pop","pop"],["Punch","punch"],["Fade","fade"],["Slide up","slide"],["Word by word","words"]]))+
      '<h3 class="cp-h">Position and timing</h3>'+
      row("Position",'<div class="cp-seg" role="group">'+POS.map(([l,v])=>'<button type="button" data-pos="'+v+'" aria-pressed="'+(cur.bottom===v)+'">'+l+'</button>').join("")+'</div>'+
        range("bottom",400,1250,10,v=>Math.round((1920-v)/19.2)+"% down"),"Kept clear of the hook and the app's buttons")+
      row("Words per line",seg("words",[["1",1],["2",2],["3",3],["4",4],["5",5]]))+
      row("Timing",range("shift",-0.5,0.5,0.05,v=>!v?"As spoken":(v>0?"+":"−")+Math.abs(v).toFixed(2)+" s"),"Earlier or later than they're said")+
      '<div class="cp-wh"><h3 class="cp-h">Words</h3>'+
        (Object.keys(cur.edits).length||cur.pop.length||cur.br.length?'<button type="button" class="linkbtn" id="cpWReset">Undo every word change</button>':'')+'</div>'+
      '<p class="ae-help">Click a word to fix it, leave it out, make it pop or start a new line there.</p>'+
      '<div class="cp-lines" id="cpLines"></div>'+
      '</div>';
    if(pic){ $("cpImg").src=pic; $("cpPrevT").textContent=picT; }  // the last preview stays until the next one is drawn
    paintLines();
    const box=o.box;
    $("cpOn").onchange=e=>set({on:e.target.checked});
    box.querySelectorAll(".cp-pre").forEach(b=>b.onclick=()=>{ const p=info.presets.find(x=>x.id===b.dataset.p);
      const keep={on:cur.on, edits:cur.edits, pop:cur.pop, br:cur.br, shift:cur.shift, bottom:cur.bottom};
      set({...copy(p.captions),...keep, preset:p.id}); });
    box.querySelectorAll("select[data-k]").forEach(s=>s.onchange=()=>set({[s.dataset.k]:s.value}));
    box.querySelectorAll("input[type=range]").forEach(r=>{
      r.oninput=()=>{ const v=+r.value; r.nextElementSibling.textContent=({size:x=>x, outline:x=>x?x+" px":"None", bottom:x=>Math.round((1920-x)/19.2)+"% down",
        shift:x=>!x?"As spoken":(x>0?"+":"−")+Math.abs(x).toFixed(2)+" s"})[r.dataset.k](v); };
      r.onchange=()=>set({[r.dataset.k]:+(+r.value).toFixed(2)}); });
    box.querySelectorAll("input[type=color]").forEach(i=>i.onchange=()=>set({[i.dataset.k]:i.value.toUpperCase()}));
    box.querySelectorAll(".cp-chk input").forEach(i=>i.onchange=()=>set({[i.dataset.k]:i.checked}));
    box.querySelectorAll(".cp-seg [data-k]").forEach(b=>b.onclick=()=>{ const v=b.dataset.v; set({[b.dataset.k]:b.dataset.k==="words"?+v:v}); });
    box.querySelectorAll("[data-pos]").forEach(b=>b.onclick=()=>set({bottom:+b.dataset.pos}));
    const wr=$("cpWReset"); if(wr) wr.onclick=()=>{ word=null; set({edits:{}, pop:[], br:[]}); };
    wirePlay();
    wireLine();
    if(!ok) box.querySelectorAll(".cp-body button,.cp-body input,.cp-body select,#cpOn").forEach(x=>x.disabled=true);
    preview();
  }
  // ---- the picked lines' own look
  function lineHTML(){
    const ls=picked(); sel=new Set(ls.map(keyOf));
    if(!ls.length) return '';
    const L=lookOf(keyOf(ls[0])), own=ls.some(l=>l.some(w=>cur.styles[w.i]));
    const said=ls.map(l=>l.filter(w=>textOf(w).trim()).map(textOf).join(" ")).join(" / ");
    const sw=(k,label)=>'<label class="cp-col"><input type="color" data-lk="'+k+'" value="'+esc(L[k].toLowerCase())+'"><span>'+esc(label)+'</span></label>';
    return '<section class="cp-line-box" id="cpLine" aria-label="The lines you picked">'+
      '<div class="cp-lb-head"><b>'+(ls.length===1?"This line":ls.length+" lines")+'</b><span class="cp-lb-said" title="'+esc(said)+'">'+esc(said)+'</span>'+
        '<button type="button" class="iconbtn" id="cpLDone" aria-label="Done with these lines" title="Done"><span class="ms" aria-hidden="true">close</span></button></div>'+
      '<p class="ae-help">A look of their own; the other lines stay as they are. Shift-click lines to pick more.</p>'+
      row("Font",'<select data-lk="font" aria-label="Font of these lines">'+info.fonts.map(f=>'<option value="'+esc(f.id)+'"'+(f.id===L.font?' selected':'')+'>'+esc(f.name)+'</option>').join("")+'</select>')+
      row("Size",'<span class="cp-range"><input type="range" data-lk="size" min="40" max="160" step="2" value="'+L.size+'" aria-label="Size of these lines"><output>'+L.size+'</output></span>')+
      row("Colours",'<div class="cp-cols">'+sw("color","Text")+sw("hi","Highlight")+sw("line",cur.box?"Box":"Outline")+'</div>')+
      row("Position",'<div class="cp-seg" role="group">'+POS.map(([l,v])=>'<button type="button" data-lpos="'+v+'" aria-pressed="'+(L.bottom===v)+'">'+l+'</button>').join("")+'</div>'+
        '<span class="cp-range"><input type="range" data-lk="bottom" min="400" max="1250" step="10" value="'+L.bottom+'" aria-label="Position of these lines"><output>'+Math.round((1920-L.bottom)/19.2)+'% down</output></span>')+
      row("",'<label class="cp-chk"><input type="checkbox" data-lk="upper"'+(L.upper?' checked':'')+'>ALL CAPITALS</label>')+
      '<div class="cp-lb-acts">'+(own?'<button type="button" class="linkbtn" id="cpLReset">Same as the rest</button>':'<span></span>')+
        '<button type="button" class="ghost sm" id="cpLDone2">Done</button></div>'+
    '</section>';
  }
  function wireLine(){
    const box=$("cpLine"); if(!box) return;
    const done=()=>{ sel=new Set(); paint(); changed(); };
    $("cpLDone").onclick=done; $("cpLDone2").onclick=done;
    const r=$("cpLReset"); if(r) r.onclick=()=>setLine(Object.fromEntries(LINE.map(k=>[k,cur[k]])));
    box.querySelectorAll("select[data-lk]").forEach(x=>x.onchange=()=>setLine({[x.dataset.lk]:x.value}));
    box.querySelectorAll("input[type=range][data-lk]").forEach(x=>{
      x.oninput=()=>{ x.nextElementSibling.textContent=x.dataset.lk==="bottom"?Math.round((1920-x.value)/19.2)+"% down":x.value; };
      x.onchange=()=>setLine({[x.dataset.lk]:+x.value}); });
    box.querySelectorAll("input[type=color][data-lk]").forEach(x=>x.onchange=()=>setLine({[x.dataset.lk]:x.value.toUpperCase()}));
    box.querySelectorAll("input[type=checkbox][data-lk]").forEach(x=>x.onchange=()=>setLine({[x.dataset.lk]:x.checked}));
    box.querySelectorAll("[data-lpos]").forEach(b=>b.onclick=()=>setLine({bottom:+b.dataset.lpos}));
    if(!can()) box.querySelectorAll("button:not(#cpLDone):not(#cpLDone2),input,select").forEach(x=>x.disabled=true);
  }
  function paintLines(){
    const el=$("cpLines"); if(!el||!info) return;
    const ls=lines(), saved=o.ae.saved(), ok=can(), pop=new Set(cur.pop), br=new Set(cur.br);
    if(!o.ae.info()){ el.innerHTML='<p class="ae-empty">Getting the words...</p>'; return; }
    if(!ls.length){ el.innerHTML='<p class="ae-empty">There\'s no talking in this Short, so there are no captions to show.</p>'; return; }
    el.innerHTML=ls.map(l=>{
      const at=saved?aeToFile(saved,l[0].s):null, k=keyOf(l), styled=l.some(w=>cur.styles[w.i]);
      return '<div class="cp-line'+(sel.has(k)?' on':'')+(styled?' own':'')+'"><button type="button" class="cp-at" data-k="'+(k==null?'':k)+'"'+(k==null?' disabled':'')+
        ' title="Pick this line to give it a look of its own (Shift-click: more lines)'+(at==null?'':'')+'">'+fmt(at||0)+'</button><span>'+
        l.map(w=>{ const t=textOf(w), hid=!t.trim(), ed=cur.edits[w.i]!=null;
          return '<button type="button" class="cp-w'+(hid?' hid':'')+(ed&&!hid?' ed':'')+(pop.has(w.i)?' pop':'')+(br.has(w.i)?' br':'')+(word===w.i?' open':'')+'" data-i="'+w.i+'"'+(ok?'':' disabled')+
            ' title="'+esc(ed?'Said: "'+w.w+'"':'Change this word')+'">'+esc(hid?w.w:(cur.upper?t.toUpperCase():t))+'</button>'; }).join(" ")+
        '</span></div>'+(l.some(w=>w.i===word)?wordEditor(l.find(w=>w.i===word)):'');
    }).join("");
    el.querySelectorAll(".cp-at").forEach(b=>b.onclick=e=>pick(+b.dataset.k, e.shiftKey||e.metaKey||e.ctrlKey));
    el.querySelectorAll(".cp-w").forEach(b=>b.onclick=()=>{ const i=+b.dataset.i, w=words().find(x=>x.i===i);
      word = word===i ? null : i; if(w && word!=null) seek(w.s); paintLines();
      const inp=el.querySelector(".cp-we input"); if(inp){ inp.focus(); inp.select(); } });
    const we=el.querySelector(".cp-we"); if(!we) return;
    const w=words().find(x=>x.i===word), i=String(word);
    const edits=t=>{ const e={...cur.edits}; if(t===w.w) delete e[i]; else e[i]=t; return e; };
    const inp=we.querySelector("input");
    inp.onchange=()=>set({edits:edits(inp.value.split(/\s+/).join(" ").trim().slice(0,40)||w.w)});
    inp.onkeydown=e=>{ if(e.key==="Enter"){ e.preventDefault(); inp.blur(); } if(e.key==="Escape"){ word=null; paintLines(); } };
    const flip=(k)=>{ const s=new Set(cur[k]); s.has(word)?s.delete(word):s.add(word); set({[k]:[...s].sort((a,b)=>a-b)}); };
    we.querySelector("[data-a=pop]").onclick=()=>flip("pop");
    we.querySelector("[data-a=br]").onclick=()=>flip("br");
    we.querySelector("[data-a=hide]").onclick=()=>set({edits:edits(textOf(w).trim()?"":w.w)});
    we.querySelector("[data-a=back]").onclick=()=>{ const e={...cur.edits}; delete e[i]; set({edits:e}); };
    we.querySelector("[data-a=done]").onclick=()=>{ word=null; paintLines(); };
  }
  function wordEditor(w){
    const t=textOf(w), hid=!t.trim(), pop=cur.pop.includes(w.i), br=cur.br.includes(w.i), ed=cur.edits[w.i]!=null;
    return '<div class="cp-we" role="group" aria-label="Change this word">'+
      '<input type="text" maxlength="40" value="'+esc(hid?w.w:t)+'" aria-label="The word"'+(hid?' disabled':'')+'>'+
      '<button type="button" class="ghost sm" data-a="pop" aria-pressed="'+pop+'"><span class="ms" aria-hidden="true">bolt</span>Pop</button>'+
      '<button type="button" class="ghost sm" data-a="br" aria-pressed="'+br+'"><span class="ms" aria-hidden="true">straighten</span>New line here</button>'+
      '<button type="button" class="ghost sm" data-a="hide" aria-pressed="'+hid+'"><span class="ms" aria-hidden="true">'+(hid?"visibility":"close")+'</span>'+(hid?"Show it":"Leave out")+'</button>'+
      (ed&&!hid?'<button type="button" class="linkbtn" data-a="back">Back to "'+esc(w.w)+'"</button>':'<span data-a="back" hidden></span>')+
      '<button type="button" class="linkbtn cp-done" data-a="done">Done</button></div>';
  }
  // The player goes to a word (vlog seconds), where the saved video has it.
  function seek(src){
    const saved=o.ae.saved(), at=saved?aeToFile(saved,src):null;
    if(at!=null){ o.video.currentTime=at+0.01; preview(); }
  }
  // ---- the moving preview's buttons: Play it (asks for one) / Pause / Play; Slow. It plays PLAYS times, then stops.
  const clip=()=>{ const v=$("cpVid"); return v && !v.hidden && v.getAttribute("src") ? v : null; };
  function paintPlay(){
    const b=$("cpPlay"), v=clip(), sl=$("cpSlow"); if(!b) return;
    const on=v && !v.paused && !v.ended;
    b.firstChild.textContent=on?"pause":"play_arrow";
    b.lastChild.textContent=!v?"Play it":on?"Pause":"Play again";
    sl.hidden=!v; sl.setAttribute("aria-pressed",pv.slow);
    if(v) $("cpPrevT").textContent=$("cpPrevT").textContent.replace(/ · (playing|stopped|paused)$/,"")+(on?" · playing":v.ended?" · stopped":" · paused");
  }
  function wirePlay(){
    const v=$("cpVid");
    $("cpPlay").onclick=()=>{ const x=clip();
      if(!x){ pv.motion=true; preview(0); return; }
      if(x.paused||x.ended){ if(x.ended) pv.loops=0; x.play().catch(()=>{}); } else x.pause(); };
    $("cpSlow").onclick=()=>{ pv.slow=!pv.slow; const x=clip(); if(x){ x.playbackRate=pv.slow?0.5:1; if(x.paused||x.ended){ pv.loops=0; x.play().catch(()=>{}); } } paintPlay(); };
    v.onplay=v.onpause=paintPlay;
    v.onended=()=>{ if(++pv.loops<PLAYS){ v.currentTime=0; v.play().catch(()=>{}); } else paintPlay(); };
  }
  // ---- the preview: one frame from the server, at the player's time, a moment after the last change; or (pv.motion)
  // a few seconds of video from the start of the line there (a picked line: the first one picked)
  function preview(wait=350){
    clearTimeout(pv.timer);
    if(!shown || !info || !info.can_apply || !cur.on || !$("cpImg")) return;
    pv.timer=setTimeout(async()=>{
      const saved=o.ae.saved(); if(!saved) return;
      const motion=pv.motion; pv.motion=false;
      // at the very start nothing is said yet: show the first word instead
      const t=o.video.currentTime||0, w0=t<0.05&&words()[0];
      let at=+(w0?(w0.s+w0.e)/2:aeToSrc(saved,t)).toFixed(2);
      if(motion){
        const ls=api.track(), p=o.ae.pieces(), now=aeToFile(p,at);
        const line=ls.find(l=>sel.has(l.key)) || [...ls].reverse().find(l=>now!=null && l.s<=now+0.05) || ls[0];
        if(line) at=+Math.max(0,line.src-0.35).toFixed(2);  // from just before it: the line comes in from nothing
      }
      const body={captions:cur, at, motion};
      if(o.ae.dirty()) body.pieces=o.ae.pieces();
      const key=JSON.stringify(body), img=$("cpImg"), vid=$("cpVid");
      if(key===pv.key && (motion?vid.src:img.src)) return;
      if(pv.ctl) pv.ctl.abort();
      const ctl=pv.ctl=new AbortController(), fig=$("cpPrev");
      fig.classList.add("busy");
      try{
        const r=await fetch("/api/captions/"+c.job+"/"+c.idx+"/preview",{method:"POST",headers:{"Content-Type":"application/json"},body:key,signal:ctl.signal});
        if(!r.ok) throw new Error((await r.json().catch(()=>({}))).error||"");
        const url=URL.createObjectURL(await r.blob()), el=$(motion?"cpVid":"cpImg"), other=$(motion?"cpImg":"cpVid"); if(!el) return;
        if(el.src) URL.revokeObjectURL(el.src);
        el.src=url; pv.key=key; el.hidden=false; other.hidden=true;
        if(motion){ other.removeAttribute("src"); pv.loops=0; el.playbackRate=pv.slow?0.5:1; el.play().catch(()=>{}); }
        else { vid.pause(); vid.removeAttribute("src"); }
        paintPlay();
        $("cpPrevT").textContent=(dirty()?"Your changes, not saved yet":"As saved")+(motion?"":" · at "+fmt(w0?aeToFile(saved,at)||0:t));
        paintPlay();
      }catch(e){ if(e.name!=="AbortError" && $("cpPrevT")) $("cpPrevT").textContent=e.message||"Couldn't draw the preview."; }
      finally{ if(pv.ctl===ctl){ pv.ctl=null; const f=$("cpPrev"); if(f) f.classList.remove("busy"); } }
    },wait);
  }
  ["seeked","pause"].forEach(e=>o.video.addEventListener(e,()=>preview()));
  const api={
    open(clip){ c=clip; busy=false; return load(); },
    clear(){ c=null; info=null; cur=null; gen++; busy=false; word=null; clearTimeout(pv.timer); if(pv.ctl) pv.ctl.abort(); o.box.innerHTML=""; changed(); },
    // The clip list was loaded again: after a remake (a new video file), read the saved captions again.
    follow(clip){
      const was=c; c=clip;
      if(!info) return;
      if(busy && !clip.remaking && was && was.video!==clip.video){ busy=false; if(!dirty()) load(true); else paint(); return; }
      if(!!(was&&was.remaking)!==!!clip.remaking) paint();
    },
    // The tool is showing (previews are only asked for then), and the cuts changed (the words follow them).
    shown(on){ shown=on; if(on) preview(); },
    words(){ if(info){ paintLines(); preview(); } },
    dirty, count:()=>dirty()?1:0, canEdit:can,
    summary:()=>{
      if(!info) return "";
      if(!cur.on) return "Off";
      const n=Object.keys(cur.edits).length, m=lines().filter(l=>cur.styles[keyOf(l)]).length;
      return (info.presets.find(p=>isPreset(p))||{name:"Custom"}).name+(n?" · "+n+" word"+(n===1?"":"s")+" changed":"")+
        (m?" · "+m+" line"+(m===1?"":"s")+" styled":"");
    },
    // The timeline's Captions row (js/editor.js): each line on the clock of the Short the pieces make, and picking one.
    track(){
      if(!info || !cur.on || !o.ae.info()) return [];
      const p=o.ae.pieces(), sh=cur.shift, ls=lines().map(l=>l.filter(w=>textOf(w).trim())).filter(l=>l.length);
      const at=(t,w)=>{ const x=aeToFile(p,t); return x!=null?x:aeToFile(p,(w.s+w.e)/2); };
      return ls.map((l,k)=>{
        const s0=at(l[0].s,l[0]), e0=at(l[l.length-1].e,l[l.length-1]), nx=ls[k+1]?at(ls[k+1][0].s,ls[k+1][0]):null;
        const e=nx!=null && nx-e0<0.6 ? nx : e0;
        return {key:l[0].i, src:l[0].s, s:Math.max(0,s0+sh), e:Math.max(0,e+sh), text:l.map(w=>cur.upper?textOf(w).toUpperCase():textOf(w)).join(" "),
          own:!!cur.styles[l[0].i], on:sel.has(l[0].i)};
      }).filter(x=>x.e>x.s);
    },
    pick,
    // The editor's Undo / Redo.
    snap:()=>cur?copy(cur):null,
    restore(x){ if(!info||!x) return; cur=copy(x); paint(); changed(); },
    reset(){ if(info){ cur=copy(info.captions); word=null; paint(); changed(); } },
    // For shortDetails(): the request that saves them (remake: make the Short again now), and once it's sent.
    step:remake=>["/api/captions/"+c.job+"/"+c.idx,{captions:cur, remake}],
    sent(remake){ info.captions=copy(cur); if(remake) busy=true; paint(); changed(); },
  };
  return api;
}
