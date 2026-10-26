// Editor (screen 12, #edit/<vlog>/<short>): a draft Short's advanced editing, opened from a Drafts card's Edit and from
// Quick review's Edit draft. Tool rail, player (Short / Thumbnail), timeline and the chosen tool's panel.
// Its own layout: the sidebar is hidden (body.ed-on) and one bar holds Back, the save state (Save / Discard while
// something is changed), ⋮ (Quick review, the vlog's own editor, Delete draft), Export (video, thumbnail) and Finish
// (saves, waits for a remake, then Schedule it or Back to Drafts).
// What works: Details (js/short-details.js: title, hook, thumbnail, hashtags, caption), the player and the timeline's
// playhead (click to jump). The other tools are laid out but not working yet: each lists what it will do, marked "Soon".
// The clip comes from the clip list (js/clips.js clData), loaded first when the page is opened from its address.
const ED_TOOLS=[
  {id:"details", icon:"edit_note", name:"Details", sub:"Title, hook, thumbnail, hashtags"},
  {id:"ai", icon:"auto_awesome", name:"AI Edit", sub:"Quick improvements", about:"Let AI do the slow parts of editing.", acts:[
    ["graphic_eq","Remove pauses","Cut dead air and filler words"],
    ["timer","Make it shorter","The best 30, 45 or 60 seconds"],
    ["trending_up","Improve hook","A stronger opening line"]], suggest:true},
  {id:"captions", icon:"closed_caption", name:"Captions", sub:"Edit and style", about:"Word-by-word captions, the way you want them.", acts:[
    ["edit","Edit words","Fix any word that was heard wrong"],
    ["timer","Timing","Move a word, split or join lines"],
    ["tune","Style presets","Fonts, colours and the highlight"],
    ["straighten","Position","Top, middle or bottom"],
    ["bolt","Emphasis","Make key words pop"]]},
  {id:"reframe", icon:"crop", name:"Reframe", sub:"Keep the subject in frame", about:"Choose what stays in the 9:16 frame.", acts:[
    ["person","Follow the speaker","A crop that tracks the face"],
    ["crop","Adjust the crop","Move it by hand, over time"],
    ["groups","Split view","Two people in one frame"]]},
  {id:"trim", icon:"content_cut", name:"Trim", sub:"Cut and arrange", about:"Change where the Short starts, ends and what it skips.", acts:[
    ["first_page","Start and end","Nudge either end"],
    ["content_cut","Split and delete","Take out a part in the middle"],
    ["swipe_up","Reorder","Move parts around"],
    ["last_page","Extend","Reach past the original moment (while the vlog's video is kept)"]]},
  {sep:true},
  {id:"text", icon:"title", name:"Text & Overlays", sub:"Titles, keywords, stickers", about:"Text and stickers at a moment you choose.", acts:[
    ["title","Text","Titles and keywords on screen"],
    ["touch_app","Call to action","Follow, watch the full vlog..."],
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
    ["video_library","B-roll from this vlog","Cut away to another moment (while the vlog's video is kept)"]]},
];
let edKey=null, edC=null, edTool="details", edOpened=null, edTimer=null, edBusy=false, edSaving=false;
const edD=shortDetails({box:$("edDBox"), err:$("edDErr"), pre:"ed", onChange:()=>edPaintSave(),
  onTitle:v=>{ const n=$("edMeta").querySelector(".ed-name"); if(n) n.textContent=v; }, onLook:()=>edView("t"),
  onRemaking:()=>{ $("edVideo").pause(); edBusy=true; edWatch(); edPaintSave(); edFinPaint(); }});  // edSync() follows it
sdOpen.push(edD);
async function openEditor(jid,idx){
  clearInterval(poll); edKey=jid+":"+idx; location.hash="edit/"+jid+"/"+idx; show(12);
  document.body.classList.add("ed-on");  // no sidebar: the whole screen is the editor
  $("edErr").textContent=""; edOpened=null; edView("v");
  if(!clData.some(c=>clKey(c)===edKey)){ clMode="drafts"; await loadClips(); }  // opened from its address
  edPaint();
}
// Leaving the editor (another screen): unsaved details are dropped. Buttons here ask first (edLeave).
function edClose(){ edOpened=null; edBusy=false; edD.clear(); clearTimeout(edTimer); document.body.classList.remove("ed-on"); if($("edFin").open) $("edFin").close(); }
function edLeave(){
  if(!edD.dirty()) return true;
  if(!confirm("Discard your changes to this Short?\n\nThey haven't been saved.")) return false;
  edD.clear(); return true;
}
// While it's being remade, check the clip list every 3 s (Drafts does that itself, but it isn't showing).
function edWatch(){ clearTimeout(edTimer); edTimer=setTimeout(()=>{ if(!$("s12").hidden) loadClips(); },3000); }
// Short or Thumbnail over the player.
const edView=v=>sdView($("edViewSw"),$("edVideo"),$("edThumb"),v);
$("edViewSw").querySelectorAll("button").forEach(b=>b.onclick=()=>edView(b.dataset.v));
// The save state beside the heading: Saved, n changes not saved (+ Save / Discard), Saving..., Remaking...
function edPaintSave(){
  const on=edD.dirty(), n=edD.count(), busy=!!(edC&&edC.remaking)||edBusy, st=$("edState");
  $("edSaveRow").hidden=!on||edSaving; $("s12").classList.toggle("dirty",on);
  $("edSave").disabled=busy;
  st.textContent = edSaving ? "Saving..." : on ? (n===1?"1 change":n+" changes")+" not saved" : busy ? "Remaking the Short..." :
    edC && !isDraftClip(edC) ? "Not a draft" : "Saved";
  st.classList.toggle("warn",on&&!edSaving); st.classList.toggle("busy",!on&&(busy||edSaving));
}
async function edSaveNow(){
  if(!edD.dirty() || edSaving) return;
  edSaving=true; edPaintSave(); await edD.save(); edSaving=false; edPaintSave();
}
function edPaint(){
  const c=clData.find(x=>clKey(x)===edKey); edC=c||null;
  if(!c){ $("edMeta").textContent=""; $("edGrid").hidden=true; $("edSmall").hidden=true; $("edFinish").disabled=$("edExport").disabled=true;
    $("edGone").hidden=false; $("edGone").textContent="This Short isn't here any more: it was deleted, or its vlog was. Go back to Drafts to see the others."; return; }
  const draft=isDraftClip(c);
  $("edGrid").hidden=false; $("edSmall").hidden=false;
  $("edGone").hidden=draft && !c.remaking;
  $("edGone").textContent = !draft ? "This Short isn't a draft any more (it's scheduled or posted), so it can't be edited here." : c.remaking ? "It's being remade. The new version shows here when it's done." : "";
  if(draft && edOpened!==edKey){ edOpened=edKey; edD.open(c); } else edD.follow(c);
  const name=edD.has("title") && $("edMeta").querySelector(".ed-name") ? $("edMeta").querySelector(".ed-name").textContent : c.title;
  $("edMeta").innerHTML='<b class="ed-name">'+esc(name)+'</b><span class="ed-sub"><span class="ed-from">From '+esc(c.vlog)+'</span>'+
    '<span class="ed-len">'+fmt(c.length)+'</span></span>';
  const pic=c.thumb?"/media/"+c.job+"/"+c.thumb:"", v=$("edVideo"), src=c.file_deleted?"":"/media/"+c.job+"/"+c.video;
  $("edBlur").style.backgroundImage=pic?"url('"+pic+"')":"none";
  $("edStrip").style.backgroundImage=pic?"url('"+pic+"')":"none";
  if(v.dataset.src!==src){ v.dataset.src=src; if(src) v.src=src; else v.removeAttribute("src"); }
  if(v.getAttribute("poster")!==pic) v.setAttribute("poster",pic);  // a new thumbnail with the same video
  if(pic) $("edThumb").src=pic; else $("edThumb").removeAttribute("src");
  $("edViewSw").hidden=!pic;
  edRuler(c.length); edTimeNow();
  $("edFinish").disabled=!draft; $("edExport").disabled=false;
  edPaintSave();
  $("edMore").innerHTML=cmButton(c.title);
  const more=$("edMore").firstChild;
  more.onclick=()=>cardMenu(more,[
    {label:"Quick review", icon:"visibility", run:()=>{ if(!edLeave()) return; openDrafts("shorts").then(()=>{ const x=clData.find(y=>clKey(y)===edKey); if(x&&isDraftClip(x)) qrOpen(x); }); }},
    {label:"Open in its vlog", icon:"video_library", run:()=>{ if(edLeave()) openJob(c.job,c.idx); }, disabled:c.remaking?"It's being remade":"", title:"Try again, Add a Short and this vlog's other Shorts"},
  ].concat(c.status==="draft"&&!c.remaking ? [{label:"Delete draft", icon:"delete", danger:true, run:()=>clDelete([c])}] : []));
  edRail(); edPanel();
}
function edRail(){
  $("edRail").innerHTML=ED_TOOLS.map(t=>t.sep?'<hr>':'<button type="button" data-t="'+t.id+'" aria-pressed="'+(t.id===edTool)+'">'+
    '<span class="ms" aria-hidden="true">'+t.icon+'</span><span><b>'+esc(t.name)+'</b><small>'+esc(t.sub)+'</small></span></button>').join("");
  $("edRail").querySelectorAll("button").forEach(b=>b.onclick=()=>{ edTool=b.dataset.t; edRail(); edPanel(); });
}
// The chosen tool: Details (kept on the page, so changes stay while other tools show), or what a tool will do, each
// marked Soon (not buttons yet).
function edPanel(){
  const t=ED_TOOLS.find(x=>x.id===edTool), det=t.id==="details";
  $("edDetails").hidden=!det; $("edPanel").hidden=det;
  if(det) return;
  $("edPanel").innerHTML='<div class="ed-p-head"><span class="ms" aria-hidden="true">'+t.icon+'</span><h2>'+esc(t.name)+'</h2><span class="cl-soon">Soon</span></div>'+
    '<p class="ed-p-about">'+esc(t.about)+'</p>'+
    '<ul class="ed-acts-list">'+t.acts.map(([i,n,s])=>'<li><span class="ms" aria-hidden="true">'+i+'</span><span><b>'+esc(n)+'</b><small>'+esc(s)+'</small></span></li>').join("")+'</ul>'+
    (t.suggest?'<div class="ed-sug"><div class="ed-sug-head"><b>AI suggestions</b><span class="cl-soon">Soon</span></div>'+
      '<p>Long pauses, captions to check and stronger hooks for this Short show up here, each with an Apply button.</p></div>':'');
}
// The timeline: a mark every 10 seconds (5 for short clips), the playhead follows the player, a click jumps there.
function edRuler(len){
  const step=len<=30?5:10; let h="";
  for(let s=0;s<=len;s+=step) h+='<span style="left:'+(s/Math.max(len,1)*100)+'%">'+fmt(s)+'</span>';
  $("edRuler").innerHTML=h;
}
function edTimeNow(){
  const v=$("edVideo"), len=v.duration||(edC&&edC.length)||0, at=Math.min(v.currentTime||0,len);
  $("edTime").textContent=fmt(at)+" / "+fmt(len);
  $("edTracks").style.setProperty("--at",len?at/len:0);
}
["timeupdate","seeked","loadedmetadata"].forEach(e=>$("edVideo").addEventListener(e,edTimeNow));
$("edTracks").addEventListener("click",e=>{
  const r=$("edRuler").getBoundingClientRect(), v=$("edVideo");
  if(e.clientX<r.left || !v.duration) return;
  v.currentTime=Math.min(1,(e.clientX-r.left)/r.width)*v.duration;
});
const edBack=()=>openDrafts("shorts");
$("edBack").onclick=()=>{ if(edLeave()) edBack(); };
$("edSave").onclick=edSaveNow;
$("edCancel").onclick=()=>{ edD.cancel(); if(edC){ const n=$("edMeta").querySelector(".ed-name"); if(n) n.textContent=edC.title; } };
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
