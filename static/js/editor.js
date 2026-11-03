// Editor (screen 12, #edit/<vlog>/<short>): a draft Short's advanced editing, opened from a Drafts card's Edit and from
// Quick review's Edit draft. Tool rail, player (Short / Thumbnail), timeline and the chosen tool's panel.
// Its own layout: the sidebar is hidden (body.ed-on) and one bar holds Back, the save state (Save / Discard while
// something is changed), ⋮ (Quick review, the vlog's own editor, Delete draft), Export (video, thumbnail) and Finish
// (saves, waits for a remake, then Schedule it or Back to Drafts).
// What works: Details (js/short-details.js: title, hook, thumbnail, hashtags, caption), AI Edit (js/ai-edit.js: cut
// pauses, filler words, by the transcript), Captions (js/captions.js: presets, look, motion, position, timing, words),
// the timeline and Trim (Twick's timeline,
// editor-app/ built into static/editor-app/, loaded the first time the editor opens: drag a part's ends, split, delete,
// reach past the moment), Undo / Redo (one history for every tool: Details, AI Edit, Captions, Trim), the Save bar at the
// bottom of the tool panel and the player. AI Edit keeps the pieces both it and Trim change, so one Save and one save
// state cover everything. The other tools are laid out but not working yet: each lists what it will do, marked
// "Soon".
// The clip comes from the clip list (js/clips.js clData), loaded first when the page is opened from its address.
const ED_TOOLS=[
  {id:"details", icon:"edit_note", name:"Details", sub:"Title, hook, thumbnail, hashtags"},
  {id:"ai", icon:"auto_awesome", name:"AI Edit", sub:"Pauses, fillers, transcript", built:true},  // js/ai-edit.js
  {id:"captions", icon:"closed_caption", name:"Captions", sub:"Words, style, timing", built:true},  // js/captions.js
  {id:"reframe", icon:"crop", name:"Reframe", sub:"Keep the subject in frame", built:true},
  {id:"trim", icon:"content_cut", name:"Trim", sub:"Cut a part, change the ends", built:true},  // the timeline
  {sep:true},
  {id:"text", icon:"title", name:"Text & Overlays", sub:"Titles, keywords, stickers", about:"Text and stickers at a moment you choose.", acts:[
    ["title","Text","Titles and keywords on screen"],
    ["touch_app","Call to action","Follow, watch the full video..."],
    ["emoji_events","Stickers","Shapes and stickers"]]},
  {id:"audio", icon:"graphic_eq", name:"Audio", sub:"Voice, volume, music", about:"Make the voice clear and the sound even.", acts:[
    ["graphic_eq","Voice clean-up","Remove background noise"],
    ["tune","Volume","Even out loud and quiet parts"],
    ["play_circle","Music","Royalty-free tracks only, so nothing gets claimed or muted"]]},
  {id:"thumb", icon:"image", name:"Thumbnail", sub:"Cover and headline", about:"The picture people see before they tap.", acts:[
    ["image","Choose the frame","Any moment of the Short"],
    ["contrast","Looks","Frame, Duotone and more"],
    ["title","Headline","The words on the thumbnail"]]},
  {id:"effects", icon:"auto_fix_high", name:"Effects", sub:"Zooms, colour, B-roll", about:"Small touches that keep people watching.", acts:[
    ["zoom_in","Zoom punch-ins","On cuts and key words"],
    ["contrast","Colour look","One grade for the whole Short"],
    ["video_library","B-roll from this video","Cut away to another moment (while the video's file is kept)"]]},
];
let edKey=null, edC=null, edTool="details", edOpened=null, edTimer=null, edBusy=false, edSaving=false;
// AI Edit's changes are saved by Details' Save (the first remake), so the one Save button covers both.
const edAE=aiEdit({box:$("edAI"), video:$("edVideo"), onChange:()=>{ edPaintSave(); edRecord(); edTlLay(); edTrimPaint(); edCap.words(); edCapTrackSoon(); },
  onHook:()=>edHook(), onLoad:()=>{ edHistReset(); edTlMount(); edCap.words(); }});
// Captions are saved by the same Save too: as their own remake, or just before a cut or a new hook remakes the Short.
const edCap=captionEdit({box:$("edCap"), video:$("edVideo"), ae:edAE, onChange:()=>{ edPaintSave(); edRecord(); edCapTrackSoon(); },
  onLoad:()=>{ edHistReset(); edCapTrackSoon(); }});
// Reframe too (the same way as the captions: one remake makes both).
const edRf=reframeEdit({box:$("edRf"), stage:$("edRfStage"), ae:edAE, caps:edCap, src:()=>edTlSrc, off:()=>edTlOff, at:()=>edSrcNow(),
  seek:t=>edSeekSrc(t), onChange:()=>{ edPaintSave(); edRecord(); }, onLoad:()=>edHistReset()});
const edD=shortDetails({box:$("edDBox"), err:$("edDErr"), pre:"ed", onChange:()=>{ edPaintSave(); edRecord(); }, extra:edAE, caps:edCap, frame:edRf,
  onLoad:()=>edHistReset(),
  onTitle:v=>{ const n=$("edMeta").querySelector(".ed-name"); if(n) n.textContent=v; }, onLook:()=>edView("t"),
  onRemaking:()=>{ $("edVideo").pause(); edBusy=true; edWatch(); edPaintSave(); edFinPaint(); }});  // edSync() follows it
sdOpen.push(edD);
async function openEditor(jid,idx){
  clearInterval(poll); edTlDrop(); edKey=jid+":"+idx; location.hash="edit/"+jid+"/"+idx; show(12);
  document.body.classList.add("ed-on");  // no sidebar: the whole screen is the editor
  $("edErr").textContent=""; edOpened=null; edView("v");
  if(!clData.some(c=>clKey(c)===edKey)){ clMode="drafts"; await loadClips(); }  // opened from its address
  edPaint();
}
// Leaving the editor (another screen): unsaved details are dropped. Buttons here ask first (edLeave).
function edClose(){ $("edVideo").pause(); edOpened=null; edBusy=false; edD.clear(); edAE.clear(); edCap.clear(); edRf.clear(); edTlDrop(); clearTimeout(edTimer); document.body.classList.remove("ed-on"); if($("edFin").open) $("edFin").close(); }
function edLeave(){
  if(!edD.dirty()) return true;
  if(!confirm("Discard your changes to this Short?\n\nThey haven't been saved.")) return false;
  edD.clear(); return true;
}
// While it's being remade, check the clip list every 3 s (Drafts does that itself, but it isn't showing).
function edWatch(){ clearTimeout(edTimer); edTimer=setTimeout(()=>{ if(!$("s12").hidden) loadClips(); },3000); }
// A new video for the Short (remade): the frame on screen stays (drawn on #edFreeze) until the new one can show at
// the same place, then fades, so the player doesn't flash black or to the thumbnail. Playing carries on.
function edSwapVideo(src){
  const v=$("edVideo"), f=$("edFreeze"), t=v.currentTime||0, playing=!v.paused;
  try{
    if(v.readyState>=2 && v.videoWidth){ f.width=v.videoWidth; f.height=v.videoHeight; f.getContext("2d").drawImage(v,0,0); f.hidden=false; f.classList.remove("go"); }
  }catch(e){ f.hidden=true; }
  const done=()=>{ f.classList.add("go"); setTimeout(()=>{ f.hidden=true; f.classList.remove("go"); },220); };
  v.addEventListener("loadedmetadata",()=>{ v.currentTime=Math.min(t,Math.max(0,(v.duration||t)-0.05));
    v.addEventListener("seeked",done,{once:true}); if(playing) v.play().catch(()=>{}); },{once:true});
  v.addEventListener("error",done,{once:true});
  v.src=src;
}
// Short or Thumbnail over the player.
const edView=v=>sdView($("edViewSw"),$("edVideo"),$("edThumb"),v);
$("edViewSw").querySelectorAll("button").forEach(b=>b.onclick=()=>edView(b.dataset.v));
// The save state beside the heading: Saved, n changes not saved (+ Save / Discard), Saving..., Remaking...
function edPaintSave(){
  const on=edD.dirty(), n=edD.count(), busy=!!(edC&&edC.remaking)||edBusy, st=$("edState");
  $("edSaveRow").hidden=!on||edSaving; $("s12").classList.toggle("dirty",on);
  $("edSave").disabled=busy; $("edSaveN").textContent=(n===1?"1 change":n+" changes")+" not saved";
  st.textContent = edSaving ? "Saving..." : on ? (n===1?"1 change":n+" changes")+" not saved" : busy ? "Remaking the Short..." :
    edC && !isDraftClip(edC) ? "Not a draft" : "Saved";
  st.classList.toggle("warn",on&&!edSaving); st.classList.toggle("busy",!on&&(busy||edSaving));
}
async function edSaveNow(){
  if(!edD.dirty() || edSaving) return;
  edSaving=true; edPaintSave(); await edD.save(); edSaving=false; edPaintSave();
  if(!edD.dirty()) edHistReset();  // saved: there's nothing to undo any more
}
function edPaint(){
  const c=clData.find(x=>clKey(x)===edKey); edC=c||null;
  if(!c){ $("edMeta").textContent=""; $("edGrid").hidden=true; $("edSmall").hidden=true; $("edFinish").disabled=$("edExport").disabled=true;
    $("edGone").hidden=false; $("edGone").textContent="This Short isn't here any more: it was deleted, or its video was. Go back to Drafts to see the others."; return; }
  const draft=isDraftClip(c);
  $("edGrid").hidden=false; $("edSmall").hidden=false;
  $("edGone").hidden=draft && !c.remaking;
  $("edGone").textContent = !draft ? "This Short isn't a draft any more (it's scheduled or posted), so it can't be edited here." : c.remaking ? "It's being remade. The new version shows here when it's done." : "";
  if(draft && edOpened!==edKey){ edOpened=edKey; edD.open(c); edAE.open(c); edCap.open(c); edRf.open(c); } else { edD.follow(c); edAE.follow(c); edCap.follow(c); edRf.follow(c); }
  const name=edD.has("title") && $("edMeta").querySelector(".ed-name") ? $("edMeta").querySelector(".ed-name").textContent : c.title;
  setHTML($("edMeta"),'<b class="ed-name">'+esc(name)+'</b><span class="ed-sub"><span class="ed-from">From '+esc(c.vlog)+'</span>'+
    '<span class="ed-len">'+fmt(c.length)+'</span></span>');
  const pic=c.thumb?"/media/"+c.job+"/"+c.thumb:"", v=$("edVideo"), src=c.file_deleted?"":"/media/"+c.job+"/"+c.video;
  $("edBlur").style.backgroundImage=pic?"url('"+pic+"')":"none";
  if(v.dataset.src!==src){  // the same Short remade: swapped under its last frame, at the same place; another Short: from its start
    const same=v.dataset.src && v.dataset.key===edKey; v.dataset.src=src; v.dataset.key=edKey;
    if(src && same) edSwapVideo(src); else if(src) v.src=src; else v.removeAttribute("src"); }
  if(v.getAttribute("poster")!==pic) v.setAttribute("poster",pic);  // a new thumbnail with the same video
  if(pic){ if($("edThumb").getAttribute("src")!==pic) $("edThumb").src=pic; } else $("edThumb").removeAttribute("src");
  $("edViewSw").hidden=!pic;
  if(!draft) edTlDrop();
  edTimeNow();
  $("edFinish").disabled=!draft; $("edExport").disabled=false;
  edPaintSave();
  setHTML($("edMore"),cmButton(c.title));
  const more=$("edMore").firstChild;
  more.onclick=()=>cardMenu(more,[
    {label:"Quick review", icon:"visibility", run:()=>{ if(!edLeave()) return; openDrafts("shorts").then(()=>{ const x=clData.find(y=>clKey(y)===edKey); if(x&&isDraftClip(x)) qrOpen(x); }); }},
    {label:"Review & post", icon:"fact_check", run:()=>{ if(edLeave()) openJob(c.job,c.idx); }, disabled:c.remaking?"It's being remade":"", title:"This video's review page: Post this, Try again, Add a Short"},
  ].concat(c.status==="draft"&&!c.remaking ? [{label:"Delete draft", icon:"delete", danger:true, run:()=>clDelete([c])}] : []));
  edRail(); edPanel();
}
function edRail(){
  setHTML($("edRail"),ED_TOOLS.map(t=>t.sep?'<hr>':'<button type="button" data-t="'+t.id+'" aria-pressed="'+(t.id===edTool)+'">'+
    '<span class="ms" aria-hidden="true">'+t.icon+'</span><span><b>'+esc(t.name)+'</b><small>'+esc(t.sub)+'</small></span></button>').join("")+
    '<button type="button" class="ed-rail-dock" id="edRailDock" title="Put the tools back beside the player"><span class="ms" aria-hidden="true">first_page</span><span><b>Tools on the side</b></span></button>');
  $("edRail").querySelectorAll("button[data-t]").forEach(b=>b.onclick=()=>{ edTool=b.dataset.t; edRail(); edPanel(); });
  $("edRailDock").onclick=()=>{ edRailTop=false; edRailApply(); };
}
// ---- Layout: the panel's edge (#edPanelGrip). Drag it to make the right-hand panel narrower or wider; the player and timeline
// take what's left, never under ED_PANEL.stage. Double-click or Enter: back to the usual width. Kept for next time (this browser only).
const ED_PANEL={min:260, max:640, base:320, stage:380};
let edPanelW=ED_PANEL.base;
try{ const v=+localStorage.getItem("pc-ed-panel"); if(v) edPanelW=v; }catch(e){}
function edPanelMax(){
  const g=$("edGrid"), rail=getComputedStyle(g).gridTemplateColumns.split(" ").length>2?edRailW+16:0;  // (two columns: the tools are above)
  return Math.min(ED_PANEL.max, Math.max(ED_PANEL.min, (g.clientWidth||1400)-rail-16-ED_PANEL.stage));
}
function edPanelApply(save){
  const w=Math.round(Math.min(edPanelMax(),Math.max(ED_PANEL.min,edPanelW))), grip=$("edPanelGrip");
  $("edGrid").style.setProperty("--panel",w+"px");
  grip.setAttribute("aria-valuenow",w); grip.setAttribute("aria-valuemin",ED_PANEL.min); grip.setAttribute("aria-valuemax",edPanelMax());
  if(save) try{ localStorage.setItem("pc-ed-panel",edPanelW=w); }catch(e){}
}
(()=>{
  const grip=$("edPanelGrip"); let drag=null;
  grip.addEventListener("pointerdown",e=>{ if(e.button) return; e.preventDefault(); grip.setPointerCapture(e.pointerId); drag=e.pointerId; grip.classList.add("drag"); });
  grip.addEventListener("pointermove",e=>{
    if(drag!==e.pointerId) return;
    edPanelW=$("edGrid").getBoundingClientRect().right-e.clientX-8; edPanelApply(true);
  });
  const end=e=>{ if(drag!==e.pointerId) return; drag=null; grip.classList.remove("drag"); };
  grip.addEventListener("pointerup",end); grip.addEventListener("pointercancel",end);
  grip.addEventListener("dblclick",()=>{ edPanelW=ED_PANEL.base; edPanelApply(true); });
  grip.addEventListener("keydown",e=>{
    if(e.key==="Enter"||e.key===" ") edPanelW=ED_PANEL.base;
    else if(e.key==="ArrowLeft") edPanelW+=20;
    else if(e.key==="ArrowRight") edPanelW-=20;
    else return;
    e.preventDefault(); edPanelApply(true);
  });
  new ResizeObserver(()=>edPanelApply(false)).observe($("edGrid"));
})();
// ---- Layout: the tools' edge (#edRailGrip). Drag it to make the tools narrower or wider (160-340 px); drag it far
// enough left and they go in a row above the player (as on a laptop), giving the player and timeline the room; drag
// back from the left edge, or "Tools on the side", to bring them back. Kept for next time (this browser only).
const ED_RAIL={min:160, max:340, top:120};
let edRailW=220, edRailTop=false;
try{ const v=JSON.parse(localStorage.getItem("pc-ed-rail")||"null"); if(v){ edRailW=Math.min(ED_RAIL.max,Math.max(ED_RAIL.min,+v.w||220)); edRailTop=!!v.top; } }catch(e){}
function edRailApply(){
  const g=$("edGrid"), grip=$("edRailGrip");
  g.style.setProperty("--rail",edRailW+"px"); g.classList.toggle("rail-top",edRailTop);
  $("edRail").classList.toggle("slim",!edRailTop && edRailW<190);
  grip.setAttribute("aria-valuenow",edRailTop?0:edRailW); grip.setAttribute("aria-valuemin",0); grip.setAttribute("aria-valuemax",ED_RAIL.max);
  try{ localStorage.setItem("pc-ed-rail",JSON.stringify({w:edRailW, top:edRailTop})); }catch(e){}
  edPanelApply(false);
}  // (the timeline and its Captions row follow the new width by themselves: ResizeObservers)
(()=>{
  const grip=$("edRailGrip"); let drag=null;
  grip.addEventListener("pointerdown",e=>{ if(e.button) return; e.preventDefault(); grip.setPointerCapture(e.pointerId); drag=e.pointerId; grip.classList.add("drag"); });
  grip.addEventListener("pointermove",e=>{
    if(drag!==e.pointerId) return;
    const x=e.clientX-$("edGrid").getBoundingClientRect().left;
    if(x<ED_RAIL.top) edRailTop=true; else { edRailTop=false; edRailW=Math.round(Math.min(ED_RAIL.max,Math.max(ED_RAIL.min,x))); }
    edRailApply();
  });
  const end=e=>{ if(drag!==e.pointerId) return; drag=null; grip.classList.remove("drag"); };
  grip.addEventListener("pointerup",end); grip.addEventListener("pointercancel",end);
  grip.addEventListener("dblclick",()=>{ edRailTop=!edRailTop; edRailApply(); });
  grip.addEventListener("keydown",e=>{
    if(e.key==="Enter"||e.key===" "){ e.preventDefault(); edRailTop=!edRailTop; }
    else if(e.key==="ArrowLeft"){ e.preventDefault(); if(edRailW-20<ED_RAIL.min) edRailTop=true; else edRailW-=20; }
    else if(e.key==="ArrowRight"){ e.preventDefault(); if(edRailTop) edRailTop=false; else edRailW=Math.min(ED_RAIL.max,edRailW+20); }
    else return;
    edRailApply();
  });
  edRailApply();
})();
// The chosen tool: Details (kept on the page, so changes stay while other tools show), or what a tool will do, each
// marked Soon (not buttons yet).
function edPanel(){
  const t=ED_TOOLS.find(x=>x.id===edTool), det=t.id==="details";
  $("edDetails").hidden=!det; $("edAIWrap").hidden=t.id!=="ai"; $("edTrimWrap").hidden=t.id!=="trim"; $("edCapWrap").hidden=t.id!=="captions"; $("edRfWrap").hidden=t.id!=="reframe"; edRfShow(t.id==="reframe"); edTrimShow(true); edPlayPaint();
  if(t.id!=="trim") edTrimLeave(); edTS.paint(); edTrimPaint();
  edCap.shown(t.id==="captions"); $("edPanel").hidden=det||!!t.built;
  if(det||t.built) return;
  $("edPanel").innerHTML='<div class="ed-p-head"><span class="ms" aria-hidden="true">'+t.icon+'</span><h2>'+esc(t.name)+'</h2><span class="cl-soon">Soon</span></div>'+
    '<p class="ed-p-about">'+esc(t.about)+'</p>'+
    '<ul class="ed-acts-list">'+t.acts.map(([i,n,s])=>'<li><span class="ms" aria-hidden="true">'+i+'</span><span><b>'+esc(n)+'</b><small>'+esc(s)+'</small></span></li>').join("")+'</ul>'+
    (t.suggest?'<div class="ed-sug"><div class="ed-sug-head"><b>AI suggestions</b><span class="cl-soon">Soon</span></div>'+
      '<p>Long pauses, captions to check and stronger hooks for this Short show up here, each with an Apply button.</p></div>':'');
}
// The time under the player: the Short as saved.
function edTimeNow(){
  const v=$("edVideo"), len=v.duration||(edC&&edC.length)||0, at=Math.min(v.currentTime||0,len);
  const p=edAE.pieces(), head=edTV.playing()||edHeadT!=null ? edHeadNow() : null, on=head!=null&&p.length?aeToFile(p,head):null;
  $("edTime").textContent = head!=null&&p.length ? (on!=null?fmt(on):"–:––")+" / "+fmt(aeLen(p)) : fmt(at)+" / "+fmt(len);  // (the Short as it will be)
  edTlFollow(); edRf.at(edSrcNow());
}
["timeupdate","seeked","loadedmetadata"].forEach(e=>$("edVideo").addEventListener(e,edTimeNow));
// The player's own Play: its video is the Short as saved. When that isn't what the playhead is on (a part stretched in and not
// saved, the vlog around the Short, or changes under Trim), the preview plays from the playhead instead, as the play button does.
// (AI Edit's waiting cuts are played by the saved video, skipping them.)
function edPlayerWrong(){
  const s=edAE.saved(), p=edAE.pieces(); if(!edTlSrc || !s || !p.length || edTool==="reframe") return false;
  if(edHeadT!=null && aeToFile(s,edHeadT)==null) return true;
  if(JSON.stringify(p)===JSON.stringify(s)) return false;
  return edTool==="trim" || aeLen(aeMinus(p,s,0,1e9))>0.05;
}
$("edVideo").addEventListener("play",()=>{
  if(edPlayerWrong()){ $("edVideo").pause(); edHeadPlay(); return; }
  if(edTV.playing()) edTV.stop(); edHeadT=null; edTV.hide(); edPlayPaint();  // the Short plays: the big moment goes
});
$("edVideo").addEventListener("pause",()=>edPlayPaint());
$("edPlayBtn").onclick=()=>edHeadPlay();
document.addEventListener("keydown",e=>{  // Space: play or pause from the playhead
  if(e.code!=="Space" || $("s12").hidden || edTool==="reframe") return;
  if(e.target.closest("input,textarea,select,button,a,video,[contenteditable],[tabindex],dialog")) return;
  e.preventDefault(); edHeadPlay();
});
// The player's own controls moved it: that's the playhead now.
let edVideoTouch=0;
["pointerdown","keydown"].forEach(k=>$("edVideo").addEventListener(k,()=>{ edVideoTouch=performance.now(); }));
$("edVideo").addEventListener("seeked",()=>{ if(performance.now()-edVideoTouch<3000){ edHeadT=null; edHeadShow(); edTS.follow(); } });
$("edVideo").addEventListener("timeupdate",()=>{ if($("edVideo").paused) edCapFollow(); });

// ---- The timeline (editor-app/main.jsx): the pieces the Short will keep (edAE.pieces()), laid end to end, on the
// clock of the Short they'll make. The player still plays the Short as saved (edAE.saved()): times go across through
// the vlog's seconds, and a part the saved video doesn't have yet (reached past the moment, or brought back) can't be
// played until it's saved.
let edTl=null, edTlLast="", edTlSel=-1, edTwickP=null, edTlFor="", edTlSrc="", edTlOff=0;  // edTlOff: the vlog second edTlSrc starts at (a clean clip)  // edTlFor: the Short (and whether it can be cut) it shows
function edTwick(){  // Twick's timeline: one script and stylesheet (about 1 MB), loaded once, when first needed
  if(window.PitTimeline) return Promise.resolve(true);
  if(!edTwickP) edTwickP=new Promise(res=>{
    const l=document.createElement("link"); l.rel="stylesheet"; l.href="/static/editor-app/style.css"; document.head.appendChild(l);
    const sc=document.createElement("script"); sc.src="/static/editor-app/timeline.js";
    sc.onload=()=>res(!!window.PitTimeline); sc.onerror=()=>{ edTwickP=null; sc.remove(); res(false); };
    document.head.appendChild(sc);
  });
  return edTwickP;
}
function edTlDrop(){
  if(edTl){ try{ edTl.destroy(); }catch(e){} }
  edCapTrackSoon();
  edHeadT=null; edTl=null; edTlLast=""; edTlSel=-1; edTlFor=""; edTlSrc=""; edTlOff=0; $("edTlNote").hidden=true; edTS.reset();
  $("edTwick").innerHTML='<p class="ed-tl-msg">'+(edC&&!isDraftClip(edC)?"Only drafts can be cut.":"Loading the timeline...")+'</p>';
  edTrimPaint();
}
// AI Edit has the Short's pieces (opened, or read again after a remake): lay them out.
async function edTlMount(){
  const key=edKey, c=edC;
  if(!c || !edAE.info()) return;
  // the same Short read again (after a save or a remake): lay the new parts out on the timeline that's there, no rebuild
  const what=c.job+":"+c.idx+":"+edAE.info().can_apply;
  if(edTl && edTlFor===what){ edTlLay(true); edTrimPaint(); edCapTrackSoon(); return; }
  const ok=await edTwick();
  if(key!==edKey || !edAE.info()) return;
  if(!ok){ $("edTwick").innerHTML='<p class="ed-tl-msg">The timeline couldn\'t load. Check your internet connection, then reload the page.</p>'; return; }
  let src="", off=0;  // the vlog's video (as "Choose on the video" plays it), else the Short's clean clip, for the pictures
  if(edAE.info().can_apply){
    try{ const r=await fetch("/api/preview/"+c.job,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({idx:c.idx})}), j=await r.json();
      if(j.status==="source"||j.status==="ready"||j.status==="clip"){ src=j.url||""; off=j.offset||0; } }catch(e){}
  }
  if(key!==edKey || !edAE.info()) return;
  edTlDrop(); edTlSrc=src; edTlOff=off;
  edTlLast=JSON.stringify(edAE.pieces());
  edTlFor=what;
  edTl=PitTimeline.mount($("edTwick"),{key:c.job+"-"+c.idx+"-"+Date.now(), src, duration:edAE.info().duration, pieces:edAE.pieces(),
    onChange:p=>{ if(!edAE.canEdit() || !edAE.setPieces(p)) edTlLay(true); },  // not taken: put it back as it was
    onSeek:t=>edTlSeek(t), onSelect:k=>{ edTlSel=k; edTrimPaint(); }, onZoom:(z,max)=>edZoomPaint(z,max),
    // dragging a part's end: on while it can be cut, snapping to the gaps between words, the player showing that moment
    canEdit:()=>edAE.canEdit(), snaps:side=>edTrimSnaps(side), onScrub:t=>edTlScrub(t)});
  edZoomPaint(1,8);
  edTimeNow(); edTrimPaint();
  if(edRfOn) edRf.shown(true);  // the vlog's video is known now: its picture
  edCapTrackSoon();
}
// Lay the timeline out again from AI Edit's pieces (after any change: closes gaps, keeps the selected part).
function edTlLay(force){
  if(!edTl) return;
  const p=edAE.pieces(), key=JSON.stringify(p);
  if(!force && key===edTlLast) return;
  edTlLast=key;
  const n=p.length; edTl.setPieces(p, edTlSel>=0 && edTlSel<n ? edTlSel : -1);
}
// Where a dragged end can snap (vlog seconds): just before each word (a start), just after it (an end), a breath away.
// The words around the moment too ("near"): a part can be stretched into them.
function edTrimSnaps(side){
  const info=edAE.info(); if(!info) return [];
  return (info.near||info.words).map(w=>side==="start" ? Math.max(0,w.s-AE_PAD) : w.e+AE_PAD);
}
// A dragged end at vlog time t: the player shows that moment, if the saved video has it (one frame at a time).
let edScrubT=null, edScrubRaf=0;
function edTlScrub(t){
  edScrubT=t; if(edScrubRaf) return;
  edScrubRaf=requestAnimationFrame(()=>{ edScrubRaf=0; const saved=edAE.saved(), at=saved?aeToFile(saved,edScrubT):null, v=$("edVideo");
    if(at!=null){ v.pause(); v.currentTime=at; } });
}
// The Video row (js/trim-strip.js) on one scale, whatever is trimmed: only the Short, or under Trim the vlog around it too;
// the parts it keeps bright and the rest dimmed; times on the Short's clock (0:00 = where the saved Short starts). A click moves
// the player. Under Trim, a drag chooses a stretch to cut out (edTrimPaint) and the player's place shows that moment big (edTV).
// Twick's timeline stays mounted, hidden, under it.
// Where the playhead is (vlog seconds): the preview playing, else a place it was moved to (which may be a part the saved video
// hasn't got: stretched in and not saved yet, or the vlog around the Short), else the saved player. Everything follows this: the
// Video row, the Captions row and the time.
let edHeadT=null;
const edHeadNow=()=>edTV.playing()?edTV.time():edHeadT!=null?edHeadT:edSrcNow();
function edHeadShow(){  // the big picture only for a place the saved video hasn't got
  const s=edAE.saved(), t=edHeadT;
  if(t!=null && edTlSrc && (!s || aeToFile(s,t)==null)) edTV.show(t, tsClock(t-edOrigin(),true)+(aeIn(edAE.pieces(),t)?" · save to see it in the player":" · not in the Short"));
  else if(!edTV.playing()) edTV.hide();
}
function edHeadTo(t){
  if(edTV.playing()) edTV.stop();
  $("edVideo").pause(); edHeadT=t; edSeekSrc(t); edHeadShow();
  edTS.follow(); edCapHand=false; edCapFollow(); edTimeNow();
}
// The play button under the player (and Space): from the playhead. The saved video when nothing has changed and it has this
// moment; otherwise the preview, which plays the Short as it will be, stretched parts and cuts included.
function edHeadPlay(){
  const v=$("edVideo");
  if(edTV.playing()){ edTV.stop(); return; }
  if(!v.paused){ v.pause(); return; }
  const src=edHeadNow(), p=edAE.pieces(), s=edAE.saved(), same=JSON.stringify(p)===JSON.stringify(s);
  if(!edTlSrc || (same && s && aeToFile(s,src)!=null) || !p.length){ edHeadT=null; v.play().catch(()=>{}); return; }
  // (before the Short's first part, or at its very end: from its start)
  edTV.play(p, src<=p[0][0]||src>=p[p.length-1][1]-0.05 ? p[0][0] : src, null, "The Short as it'll be"); edTrimPaint(); edPlayPaint();
}
function edPlayPaint(){
  const on=edTV.playing()||!$("edVideo").paused, b=$("edPlayBtn");
  b.querySelector(".ms").textContent=on?"pause":"play_arrow"; b.setAttribute("aria-label",on?"Pause":"Play from here"); b.title=on?"Pause (Space)":"Play from here (Space)";
  b.hidden=edTool==="reframe";
}
const edOrigin=()=>{ const s=edAE.saved(), i=edAE.info(); return s&&s.length?s[0][0]:i?i.start:0; };
const edTS=trimStrip({box:$("edTrimStrip"), pieces:()=>edAE.pieces(), info:()=>edAE.info(), origin:edOrigin,
  trim:()=>edTool==="trim", canEdit:()=>edAE.canEdit(), snaps:side=>edTrimSnaps(side), src:()=>edTlSrc, off:()=>edTlOff,
  now:()=>edHeadNow(), saved:()=>edAE.saved(),
  commit:p=>{ if(!edAE.canEdit() || !edAE.setPieces(p)) edTS.paint(); },
  // a click, or dragging the handle: the playhead goes there (a moment the saved video hasn't got shows big)
  seek:t=>edHeadTo(t), press:()=>edTV.unlock(),
  hover:t=>edTrimHover(t), onSel:()=>{ edTrimHover(null); edTrimPaint(); }});
const edTV=trimView({host:$("edTrimView"), src:()=>edTlSrc, off:()=>edTlOff, crop:t=>edRf.cropAt(t), size:()=>edRf.size(),
  onTime:t=>{ edTS.follow(); edCapFollow(); edTimeNow();
    if(t==null){ edHeadT=edTV.time(); const sv=edAE.saved(), f=sv?aeToFile(sv,edHeadT):null; if(f!=null) $("edVideo").currentTime=f; edHeadShow(); edPlayPaint(); edTrimPaint(); } }});
// The moment being dragged to (vlog seconds), big; when the drag ends (null) the player is back, with its controls.
function edTrimHover(t){
  if(edTool!=="trim" || edTV.playing()) return;
  if(t==null){ edHeadShow(); return; }
  edTV.show(t, tsClock(t-edOrigin(),true)+(aeIn(edAE.pieces(),t)?"":" · left out"));
}
function edTrimLeave(){ edTV.stop(); edHeadT=null; edTV.hide(); if(edTS.sel()) edTS.setSel(null); }
// Reframe takes the player's place while it's chosen (only when the tool changes); the player pauses.
let edRfOn=false;
function edRfShow(on){
  if(on===edRfOn) return; edRfOn=on;
  $("edRfStage").hidden=!on; $("edViewSw").classList.toggle("rf-off", on);
  if(on){ $("edVideo").pause(); edView("v"); }
  edRf.shown(on);
}
// The playhead in the vlog's seconds (where the saved video is), and moving it to a vlog time (where it can).
function edSrcNow(){ const saved=edAE.saved(); return saved ? aeToSrc(saved,$("edVideo").currentTime||0) : null; }
function edSeekSrc(t){
  const saved=edAE.saved(), f=saved?aeToFile(saved,t):null, at=aeToFile(edAE.pieces(),t), v=$("edVideo");
  if(f!=null){ v.pause(); v.currentTime=f; }
  $("edTlNote").hidden=f!=null;  // a part the saved video doesn't have: "Save to play the new parts"
  if(edTl && at!=null) edTl.setTime(at);
  edRf.at(t);
}
let edTrimOn=false;
function edTrimShow(on){  // on from the start (Twick's own view stays mounted under it); only acts on a change
  if(on===edTrimOn) return; edTrimOn=on;
  $("edTwick").hidden=on; $("edTrimStrip").hidden=!on; $("edZoomIn").parentNode.hidden=on;
  edTS.show(on);
  if(!on && edTl) edTl.fit();  // back from being hidden: fit the Short to the box again
}
// The player moved: the timeline's playhead follows (where the part is still kept).
function edTlFollow(){
  const saved=edAE.saved(); if(!edTl || !saved) return;
  const src=aeToSrc(saved,$("edVideo").currentTime||0), at=aeToFile(edAE.pieces(),src);
  if(at!=null){ edTl.setTime(at); $("edTlNote").hidden=true; }
  edTS.follow();
}
// A click on the timeline's ruler: the player goes there, if the saved video has that part.
function edTlSeek(t){
  if(t==null || !edAE.saved()) return;
  const src=aeToSrc(edAE.pieces(),t), at=aeToFile(edAE.saved(),src), v=$("edVideo");
  edRf.at(src);  // Reframe shows any moment of the Short as it will be, saved or not
  $("edTlNote").hidden=at!=null;
  if(at!=null && Math.abs((v.currentTime||0)-at)>0.05) v.currentTime=at;
}
// Zoom: out / Fit (the whole Short) / in. The label says how far in it is.
function edZoomPaint(z,max){
  $("edZoomOut").disabled=$("edZoomFit").disabled=!edTl||z<=1.001; $("edZoomIn").disabled=!edTl||z>=max-0.001;
  $("edZoomFit").textContent = z<=1.001 ? "Fit" : Math.round(z*10)/10+"×";
  $("edZoomFit").title = z<=1.001 ? "The whole Short fits" : "Zoomed in "+Math.round(z*10)/10+" times: click to show the whole Short";
}
$("edZoomIn").onclick=()=>edTl&&edTl.zoomIn();
$("edZoomOut").onclick=()=>edTl&&edTl.zoomOut();
$("edZoomFit").onclick=()=>edTl&&edTl.fit();

// ---- Trim, in the panel: the Short's length, then the part to cut out (the yellow box on the Video row: a drag, then
// shaped there), with its start and end to fine-tune and Cut it out, after which the Short plays without it (trimView:
// the vlog's video, with sound).
function edTrimResult(){  // the pieces once the yellow box is cut out (or null)
  const sel=edTS.sel(), info=edAE.info(); if(!sel||!info) return null;
  return aeMinus(edAE.pieces(),[[sel.a,sel.b]],0,info.duration||1e9);
}
function edTrimPaint(){
  edTS.paint();  // the Video row too: every change of the pieces comes through here (a cut, Undo, AI Edit, a save)
  const box=$("edTrim"); if(!box) return;
  const info=edAE.info(), p=edAE.pieces();
  if(!info || !p.length){ setHTML(box,'<p class="qr-wait">'+(edC&&!isDraftClip(edC)?"Only drafts can be cut.":"Getting the parts of this Short...")+'</p>'); return; }
  const can=edAE.canEdit(), len=aeLen(p), sel=edTS.sel(), o0=edOrigin(), T=t=>tsClock(t-o0,true);
  const ed=can?'':' disabled', playing=edTV.playing();
  let h=(info.can_apply?'':'<div class="ed-note ae-warn">'+esc(info.why_not)+'</div>')+
    '<div class="tr-sum" role="status"><b>'+fmt(len)+'</b> long'+(p.length>1?', '+p.length+' parts':'')+
      '<small>'+(p.length>1?'From '+T(p[0][0])+' to '+T(p[p.length-1][1])+' of the clip, with gaps':'From '+T(p[0][0])+' to '+T(p[0][1])+' of the clip')+'</small>'+
      (len<info.min?'<span class="ae-bad">At least '+info.min+' s</span>':'')+(len>info.max?'<span class="ae-bad">At most '+fmt(info.max)+'</span>':'')+'</div>';
  if(!sel) h+='<div class="tr-step"><b>Drag the handle to move through the video. Drag across a part to cut it out.</b>'+
    '<small>The part you drag across turns yellow. Drag its ends to stretch or narrow it, or drag it to move it. Then cut it out.</small></div>';
  if(sel){
    const cuts=len-aeLen(edTrimResult())>0.25;  // some of it is in the Short (a dimmed part is left out already)
    const nudge=(side,d)=>'<button type="button" class="ghost sm" data-se="'+side+'" data-d="'+d+'"'+ed+'>'+(d<0?"−":"+")+Math.abs(d)+(Math.abs(d)>=1?" s":"")+'</button>';
    const steps=side=>[-1,-0.1,0.1,1].map(d=>nudge(side,d)).join("");
    h+='<div class="tr-sel"><div class="tr-sel-h"><b>'+T(sel.a)+' → '+T(sel.b)+'</b><span>'+(sel.b-sel.a).toFixed(1)+' s</span></div>'+
      '<div class="tr-row"><span><b>Start</b></span><span class="tr-steps">'+steps("a")+'</span></div>'+
      '<div class="tr-row"><span><b>End</b></span><span class="tr-steps">'+steps("b")+'</span></div>'+
      (cuts?'':'<small class="tr-why">That part is already left out of the Short (it\'s dimmed).</small>')+
      '<div class="tr-acts">'+
        '<button type="button" class="primary" id="trCut"'+(can&&cuts?'':' disabled')+'><span class="ms" aria-hidden="true">content_cut</span>Cut it out</button>'+
        '<button type="button" class="ghost" id="trClear">Clear</button>'+
      '</div></div>';
  }
  h+='<div class="tr-acts">'+
      '<button type="button" class="ghost" id="trPlay"'+(edTlSrc?'':' disabled')+'><span class="ms" aria-hidden="true">'+(playing?"stop_circle":"play_circle")+'</span>'+(playing?"Stop":"Play the Short as it'll be")+'</button>'+
    '</div>'+
    '<div class="err" id="edTrimErr" role="alert"></div>'+
    '<p class="ae-help">The Short keeps what\'s bright; dimmed is left out; light green is what you\'ve added and not saved yet. '+
      'Delete cuts the yellow part out, Esc clears it, Alt / Option stops it snapping to the gaps between words. Undo puts a cut back; nothing changes until you save. Press Play or Space to play from the handle, and double-click a caption line under the video to change its words.</p>';
  if(!setHTML(box,h)) return;
  const err=m=>{ $("edTrimErr").textContent=m; };
  box.querySelectorAll("[data-se]").forEach(b=>b.onclick=()=>{
    const s=edTS.sel(), d=+b.dataset.d; if(!s) return;
    if(b.dataset.se==="a") s.a=Math.min(s.b-0.3,s.a+d); else s.b=Math.max(s.a+0.3,s.b+d);
    edTS.setSel(s);
  });
  // Cut it out: out of the Short (Undo puts it back), then the Short plays without it, from a few seconds before
  if($("trCut")) $("trCut").onclick=()=>{
    const s=edTS.sel(), r=edTrimResult();
    if(!r||!r.length){ err("That would cut out all of the Short. Keep a part of it."); return; }
    edTS.setSel(null); if(!edAE.setPieces(r)){ err("That can't be changed now."); return; }
    if(edTlSrc){ edTV.play(r, s.a-3, s.b+3, "Without "+T(s.a)+" to "+T(s.b)); edTrimPaint(); }
  };
  if($("trClear")) $("trClear").onclick=()=>edTS.setSel(null);
  $("trPlay").onclick=()=>{ if(edTV.playing()){ edTV.stop(); return; } edTV.play(p, p[0][0], null, "The Short as it'll be"); edTrimPaint(); };
}
document.addEventListener("keydown",e=>{  // Delete / Backspace: cut out the yellow part (else the part chosen on Twick's timeline)
  if($("s12").hidden || !edAE.canEdit() || !["Delete","Backspace"].includes(e.key)) return;
  const a=document.activeElement, tag=a&&a.tagName;
  if(tag==="INPUT"||tag==="TEXTAREA"||tag==="SELECT"||(a&&a.isContentEditable)) return;
  if(edTool==="trim" && edTS.sel()){ e.preventDefault(); if($("trCut")) $("trCut").click(); return; }
  if(edTl && edTlSel>=0){ e.preventDefault(); edTl.remove(); }
});
// The timeline's Captions row: every caption line as a chip with room for its words (and when it's said), in a strip
// that moves along as the Short plays, keeping the line being said in the middle and lit (not to the timeline's scale:
// at that scale a line is a sliver). Seeking jumps it there; the wheel scrolls it by hand until the next play or seek.
// A click picks the line in the Captions tool (Shift, Ctrl or ⌘: more lines) to give it a look of its own. Before the
// words are in: the captions' look, opening the tool.
let edCapKey="", edCapLs=[], edCapX=0, edCapHand=false, edCapUser=0, edCapRaf=0;
let edCapClick=null, edCapEditing=false;  // a line's words are being typed on its chip: nothing redraws or moves the strip until that's done
function edCapTrack(){
  if(edCapEditing) return;
  const el=$("edCapTrack"), ls=edCap.track();
  if(!ls.length){
    const s=edCap.summary(); edCapKey=""; edCapLs=[];
    el.innerHTML='<button type="button" class="ed-cap-sum" title="Open the Captions tool"><span class="ms" aria-hidden="true">tune</span><span>'+esc(s?"Captions: "+s:"Captions")+'</span></button>';
    el.firstChild.onclick=()=>edCapOpen();
    return;
  }
  const key=JSON.stringify(ls);
  if(key!==edCapKey || !el.querySelector(".ed-cap-strip")){  // drawn again only when the lines change
    edCapKey=key; edCapLs=ls;
    el.innerHTML='<div class="ed-cap-strip">'+ls.map(l=>'<button type="button" class="ed-cap-c'+(l.on?' on':'')+(l.own?' own':'')+'" data-k="'+l.key+'"'+
      ' title="'+esc(l.text)+(l.own?' (a look of its own)':'')+'. Double-click to change the words" aria-pressed="'+l.on+'"><small>'+fmt(l.s)+'</small><span>'+esc(l.text)+'</span></button>').join("")+'</div>';
    el.querySelectorAll(".ed-cap-c").forEach(b=>b.onclick=e=>{
      // A second click soon after: type the line clicked first. (That click moved the strip, so the pointer may be on another chip by now.)
      const k=+b.dataset.k, now=performance.now();
      if(edCapClick && now-edCapClick.at<450){ const was=edCapClick.k; edCapClick=null; edCapEdit(was); return; }
      edCapClick={k, at:now};
      // Under the Captions tool a click picks the line, for a look of its own. Under any other tool it goes to the line and
      // stays there: double-click edits it right here, with no trip to the Captions tool.
      const l=edCapLs.find(x=>x.key===k), sv=edAE.saved();
      if(edTool==="captions"){ edCap.pick(k, e.shiftKey||e.metaKey||e.ctrlKey); if(l && sv && aeToFile(sv,l.src)==null) edHeadTo(l.src); }
      else if(l) edHeadTo(l.src);
    });
  }
  edCapFollow();
}
// Where the player is, on the clock of the Short the pieces make (the timeline's).
function edCapNow(){
  const src=edHeadNow(); if(src==null) return 0;
  const p=edAE.pieces(), t=aeToFile(p,src);
  return t!=null ? t : aeToFile(p,(p.find(([a])=>a>src)||[src])[0]) ?? aeLen(p);
}
// The line being said is lit; the strip moves so the place being said is in the middle (as far as its ends allow).
function edCapFollow(){
  if(edCapEditing) return;
  const el=$("edCapTrack"), strip=el.querySelector(".ed-cap-strip"), ls=edCapLs; if(!strip||!ls.length) return;
  const t=edCapNow(); let k=ls.findIndex(l=>t<l.e); if(k<0) k=ls.length-1;
  const chips=strip.children, said=t>=ls[k].s-0.02;
  for(let n=0;n<chips.length;n++) chips[n].classList.toggle("now", n===k && said);
  if(edCapHand) return;
  const b=chips[k], f=said ? Math.min(1,Math.max(0,(t-ls[k].s)/Math.max(0.05,ls[k].e-ls[k].s))) : 0;
  edCapX=Math.min(Math.max(0,strip.scrollWidth-el.clientWidth), Math.max(0, b.offsetLeft+b.offsetWidth*f-el.clientWidth/2));
  strip.style.transform="translateX("+(-edCapX).toFixed(1)+"px)";
}
function edCapPlay(){ cancelAnimationFrame(edCapRaf); const v=$("edVideo");
  const go=()=>{ edCapFollow(); if(!v.paused && !$("s12").hidden) edCapRaf=requestAnimationFrame(go); }; go(); }
$("edVideo").addEventListener("play",()=>{ edCapHand=false; edCapPlay(); });
// A seek the creator makes (the player's controls, the timeline, a caption chip: pressed in the last 3 s) takes it back
// to the player; the page's own seeks (the timeline lining up the player) don't undo a scroll by hand.
const edCapTouch=()=>{ edCapUser=performance.now(); };
["pointerdown","keydown"].forEach(e=>{ $("edVideo").addEventListener(e,edCapTouch); $("edTwick").addEventListener(e,edCapTouch,true); $("edCapTrack").addEventListener(e,edCapTouch,true); $("edTrimStrip").addEventListener(e,edCapTouch,true); });
$("edVideo").addEventListener("seeked",()=>{ if(performance.now()-edCapUser<3000) edCapHand=false; edCapFollow(); });
$("edCapTrack").addEventListener("wheel",e=>{
  const strip=$("edCapTrack").querySelector(".ed-cap-strip"); if(!strip) return;
  const d=Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY; if(!d) return;
  e.preventDefault(); edCapHand=true; edCapUser=0;
  edCapX=Math.min(Math.max(0,strip.scrollWidth-$("edCapTrack").clientWidth), Math.max(0,edCapX+d));
  strip.style.transform="translateX("+(-edCapX).toFixed(1)+"px)";
},{passive:false});
// Double-click a line on the row to change its words right there: the player pauses and the strip holds still. Enter or
// clicking away keeps them (edCap.setLineText: Undo and Save as usual), Esc doesn't.
// (the strip moved after the first click, so the second can land between two chips)
$("edCapTrack").addEventListener("click",e=>{
  if(e.target.closest(".ed-cap-c") || !edCapClick || performance.now()-edCapClick.at>=450) return;
  const k=edCapClick.k; edCapClick=null; edCapEdit(k);
});
function edCapEdit(k){
  if(!edCap.canEdit()) return;
  edCapKey=""; edCapTrack();  // (the chip, drawn as it is now)
  const chip=$("edCapTrack").querySelector('.ed-cap-c[data-k="'+k+'"]'), was=edCap.lineText(k), span=chip&&chip.querySelector("span"); if(!span) return;
  $("edVideo").pause(); edCapEditing=true; chip.classList.add("typing");
  const inp=document.createElement("input"); inp.className="ed-cap-in"; inp.value=was; inp.maxLength=200; inp.setAttribute("aria-label","Words of this caption line");
  const size=()=>{ inp.style.width=Math.min(420,Math.max(60,inp.value.length*8.4+20))+"px"; }; size(); inp.oninput=size;
  span.replaceWith(inp); inp.focus(); inp.select();
  // keep it in view: the row's strip is moved by hand while this is open
  const strip=$("edCapTrack").querySelector(".ed-cap-strip"), box=$("edCapTrack");
  edCapX=Math.min(Math.max(0,strip.scrollWidth-box.clientWidth), Math.max(0,chip.offsetLeft+chip.offsetWidth/2-box.clientWidth/2));
  strip.style.transform="translateX("+(-edCapX).toFixed(1)+"px)";
  inp.addEventListener("click",ev=>ev.stopPropagation()); inp.addEventListener("dblclick",ev=>ev.stopPropagation());
  let done=false;
  const finish=keep=>{
    if(done) return; done=true; edCapEditing=false; edCapKey="";
    const t=inp.value.split(/\s+/).join(" ").trim();
    if(keep && t!==was) edCap.setLineText(k,t);
    edCapTrack();
  };
  inp.addEventListener("keydown",ev=>{ ev.stopPropagation();
    if(ev.key==="Enter"){ ev.preventDefault(); finish(true); } else if(ev.key==="Escape"){ ev.preventDefault(); finish(false); } });
  inp.addEventListener("blur",()=>finish(true));
}
let edCapT=0;
function edCapTrackSoon(){ cancelAnimationFrame(edCapT); edCapT=requestAnimationFrame(()=>setTimeout(edCapTrack,30)); }
function edCapOpen(){ if(edTool!=="captions"){ edTool="captions"; edRail(); edPanel(); } }
new ResizeObserver(edCapTrackSoon).observe($("edCapTrack"));  // wider or narrower (the window, the tools moved)
// Improve hook (AI Edit): Details' hook, opened, with Rewrite pressed.
function edHook(){
  edTool="details"; edRail(); edPanel();
  const box=$("edDBox"), change=box.querySelector(".hk-change"), rw=box.querySelector(".hk-rewrite");
  if(!change) return;
  if(box.querySelector(".hk-edit").hidden) change.click();
  if(rw && !rw.disabled) rw.click();
  change.scrollIntoView({block:"nearest"});
}
// Undo / Redo on the timeline: AI Edit's cuts not saved yet.
// ---- Undo / Redo: one history of every change not saved yet (Details, AI Edit, Captions, Trim). A step is what was
// waiting to be saved (edD.snap()), the pieces the Short keeps (edAE.pieces()) and the captions (edCap.snap()); typing in
// one field counts as one step until a pause. Saving, Discard and opening a Short start it afresh.
let edHist=[], edFut=[], edNow=null, edLast={key:"", at:0}, edRestoring=false;
const edSnap=()=>({d:edD.snap(), p:JSON.stringify(edAE.pieces()), c:edCap.snap(), r:edRf.snap()});
const edSame=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
// What changed between two steps, when it's typing (the same field again soon after is the same step), else "".
function edTyping(a,b){
  if(a.p!==b.p || !edSame(a.c,b.c) || !edSame(a.r,b.r)) return "";
  const keys=[...new Set(Object.keys(a.d).concat(Object.keys(b.d)))].filter(k=>!edSame(a.d[k],b.d[k]));
  if(keys.length!==1) return "";
  const k=keys[0];
  if(k==="title" || k==="ttext") return k;
  if(k==="text"){ const t=Object.keys({...a.d.text,...b.d.text}).filter(x=>!edSame((a.d.text||{})[x],(b.d.text||{})[x])); return t.length===1&&t[0]==="caption"?"caption":""; }
  return "";
}
function edRecord(){
  if(edRestoring || !edC) return;
  const now=edSnap();
  if(!edNow){ edNow=now; edUndoPaint(); return; }
  if(edSame(now,edNow)) return;
  const key=edTyping(edNow,now), t=Date.now();
  if(!(key && key===edLast.key && t-edLast.at<1500)) edHist.push(edNow);
  if(edHist.length>200) edHist.shift();
  edLast={key, at:t}; edNow=now; edFut=[]; edUndoPaint();
}
function edHistReset(){ edHist=[]; edFut=[]; edLast={key:"",at:0}; edNow=edC?edSnap():null; edUndoPaint(); }
function edGo(from,to){
  if(!from.length || edSaving || (edC&&edC.remaking) || edBusy) return;
  to.push(edNow); edNow=from.pop(); edLast={key:"",at:0};
  edRestoring=true;
  try{ edD.restore(edNow.d); edAE.restore(JSON.parse(edNow.p)); edCap.restore(edNow.c); edRf.restore(edNow.r); } finally{ edRestoring=false; }
  edPaintSave(); edTlLay(); edTrimPaint(); edUndoPaint();
}
function edUndoPaint(){
  const busy=edSaving||!!(edC&&edC.remaking)||edBusy;
  $("edUndo").disabled=busy||!edHist.length; $("edRedo").disabled=busy||!edFut.length;
}
$("edUndo").onclick=()=>edGo(edHist,edFut);
$("edRedo").onclick=()=>edGo(edFut,edHist);
// Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z (or Ctrl+Y) while the editor shows; inside a text field they undo the typing there.
document.addEventListener("keydown",e=>{
  if($("s12").hidden || !(e.metaKey||e.ctrlKey) || e.altKey) return;
  const k=e.key.toLowerCase(), a=document.activeElement, tag=a&&a.tagName;
  if(tag==="INPUT"||tag==="TEXTAREA"||(a&&a.isContentEditable)) return;
  if(k==="z" && !e.shiftKey){ e.preventDefault(); edGo(edHist,edFut); }
  else if((k==="z" && e.shiftKey) || k==="y"){ e.preventDefault(); edGo(edFut,edHist); }
});
const edBack=()=>openDrafts("shorts");
$("edBack").onclick=()=>{ if(edLeave()) edBack(); };
$("edSave").onclick=edSaveNow;
$("edCancel").onclick=async()=>{ const p=edD.cancel(); if(edC){ const n=$("edMeta").querySelector(".ed-name"); if(n) n.textContent=edC.title; } await p; edHistReset(); };
// Cmd/Ctrl+S saves while the editor shows.
document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==="s" && !$("s12").hidden){ e.preventDefault(); edSaveNow(); }
});
// Export: the video (with its thumbnail as the first frame) or the thumbnail.
$("edExport").onclick=()=>{
  if(!edC) return;
  const v=clDownloadItem(edC);
  cardMenu($("edExport"),[{...v, label:v.icon==="download"?"Video (MP4)":v.label},
    edC.thumb ? {label:"Thumbnail (JPG)", icon:"image", download:true, href:"/media/"+edC.job+"/"+edC.thumb+"?dl="+encodeURIComponent(thumbFileName(edC))}
              : {label:"Thumbnail (JPG)", icon:"image", disabled:"This Short has no thumbnail"}]);
};
// Finish: save what's changed, then (once a remake is done) schedule it or go back to Drafts.
$("edFinish").onclick=async()=>{
  if(!edC) return;
  if(edD.dirty()){
    await edSaveNow();
    if(edD.dirty()){ edTool="details"; edRail(); edPanel(); return; }  // didn't save: Details says why
  }
  $("edFinErr").textContent=""; $("edFin").showModal(); edFinPaint();
};
function edFinPaint(){
  if(!$("edFin").open || !edC) return;
  const busy=!!edC.remaking||edBusy;
  $("edFinTitle").textContent=busy?"Almost done":"Your Short is ready";
  $("edFinWait").hidden=!busy;
  $("edFinLede").textContent = busy ? "Your changes are saved. You can schedule it once the new version is made, or go back to Drafts: it finishes by itself."
    : '"'+edC.title+'" is saved. Schedule it for YouTube and Instagram, or keep it in Drafts for later.';
  $("edFinSched").disabled=busy||!clPickable(edC);
}
$("edFinStay").onclick=()=>$("edFin").close();
$("edFinDrafts").onclick=()=>{ $("edFin").close(); edBack(); };
// Schedule just this clip: the clip browser's dialog with only it ticked. Once it's scheduled, back to Drafts (edSync).
$("edFinSched").onclick=()=>{ $("edFin").close(); clKeptPicks=new Set(clPicked); clPicked=new Set([edKey]); clSchedDialog(); };
document.body.appendChild($("edFin"));
// After the clip list is drawn again (scheduled, deleted, remade): follow it here.
function edSync(){
  if($("s12").hidden || !edKey) return;
  const c=clData.find(x=>clKey(x)===edKey);
  if(edC && (!c || (isDraftClip(edC) && !isDraftClip(c)))){ edBack(); return; }  // deleted, or scheduled from Finish
  edPaint();
  if(edC && edC.remaking) edWatch();
  else if(edBusy && edC){ edBusy=false; edD.remadeDone(); edPaintSave(); }  // the remake is done (or a look waits for it)
  edFinPaint();
}
