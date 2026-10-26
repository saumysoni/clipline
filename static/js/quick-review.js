// Quick review (Drafts' Shorts & Reels tab): clicking a draft clip opens this panel beside the cards. It plays the clip
// (or shows its thumbnail) and has the simple editing (js/short-details.js: hook, thumbnail look, hashtags, YouTube title,
// Instagram caption), saved with Save. Edit draft opens the editor (js/editor.js).
// A saved hook or look remakes the Short: Drafts' clip list already checks every 3 s while one is being remade
// (js/clips.js loadClips), and qrSync() (called after each repaint) follows it.
let qrKey=null, qrC=null;
const qrD=shortDetails({box:$("qrEdit"), err:$("qrErr"), pre:"qr", onChange:()=>qrPaintSave(),
  onGone:()=>qrClose(), onLook:()=>qrView("t"),
  onRemaking:()=>{ $("qrVideo").pause(); qrC={...qrC,remaking:true}; qrTop(qrC); }});
sdOpen.push(qrD);
// Before leaving the open clip (close, another clip, the editor, Schedule): unsaved changes are dropped only if asked.
function qrLeave(){
  if(!qrKey || !qrD.dirty()) return true;
  if(!confirm("Discard your changes to this Short?\n\nThey haven't been saved.")) return false;
  qrD.clear(); return true;
}
function qrOpen(c){
  if(qrKey===clKey(c)) return;
  if(!qrLeave()) return;
  qrKey=clKey(c); qrC=c;
  $("qrPanel").hidden=false; $("qrShade").hidden=false; document.body.classList.add("qr-open");
  qrView("v"); qrMark(); qrTop(c); qrD.open(c);
  $("qrX").focus({preventScroll:true});
}
// Closes it: unsaved changes are dropped (user actions ask first through qrLeave()).
function qrClose(){
  if(!qrKey) return;
  qrKey=qrC=null; qrD.clear();
  $("qrPanel").hidden=true; $("qrShade").hidden=true; document.body.classList.remove("qr-open");
  const v=$("qrVideo"); v.pause(); v.removeAttribute("src"); v.load();
  qrMark(); clDock();
}
// The open clip's card is outlined.
function qrMark(){ document.querySelectorAll("#clGrid .clip").forEach(el=>el.classList.toggle("qr-on",el.dataset.k===qrKey)); }
// Short or Thumbnail over the player.
const qrView=v=>sdView($("qrViewSw"),$("qrVideo"),$("qrThumb"),v);
$("qrViewSw").querySelectorAll("button").forEach(b=>b.onclick=()=>qrView(b.dataset.v));
// Where a draft stands on one platform: not published, or its posting failed.
function qrPlat(c,p){
  const name=p==="youtube"?"YouTube":"Instagram", bad=c[p]&&c[p].state==="failed";
  return '<span class="qr-plat'+(bad?" bad":"")+'"'+(bad&&c[p].error?' title="'+esc(c[p].error)+'"':'')+'><span class="ms '+(p==="youtube"?"yt":"ig")+'" aria-hidden="true">'+
    (p==="youtube"?"smart_display":"photo_camera")+'</span>'+name+': '+(bad?"didn't go out":"not published")+'</span>';
}
// Everything that comes with the clip list: player, thumbnail, title, vlog, status, buttons.
function qrTop(c){
  const pic=c.thumb?"/media/"+c.job+"/"+c.thumb:"", v=$("qrVideo");
  $("qrBlur").style.backgroundImage=pic?"url('"+pic+"')":"none";
  if(pic) $("qrThumb").src=pic; else $("qrThumb").removeAttribute("src");
  $("qrViewSw").hidden=!pic;
  const src=c.file_deleted?"":"/media/"+c.job+"/"+c.video;
  if(v.dataset.src!==src){ v.dataset.src=src; if(src) v.src=src; else v.removeAttribute("src"); }
  if(v.getAttribute("poster")!==pic) v.setAttribute("poster",pic);  // a new thumbnail with the same video
  if(!qrD.has("title")) $("qrTitle").textContent=c.title;
  $("qrLen").textContent=fmt(c.length);
  $("qrFrom").innerHTML='<span class="ms" aria-hidden="true">video_library</span><span>From '+esc(c.vlog)+'</span>';
  $("qrStatus").innerHTML='<span class="cl-pill">Draft</span>'+qrPlat(c,"youtube")+qrPlat(c,"instagram");
  const soon=c.expires && c.expires*1000-Date.now()<86400000;
  $("qrWarn").hidden=!soon;
  if(soon) $("qrWarn").innerHTML='<span class="ms" aria-hidden="true">schedule</span><span>Deleted '+esc(vlSoon(c.expires))+' unless edited or posted</span>';
  $("qrBusy").hidden=!c.remaking;
  $("qrEditBtn").disabled=!!c.remaking; $("qrSched").disabled=!!c.remaking||!clPickable(c); $("qrSave").disabled=!!c.remaking;
  const dl=clDownloadItem(c), a=$("qrDl");
  if(dl.href && !dl.disabled){ a.href=dl.href; a.toggleAttribute("download",!!dl.download); a.removeAttribute("aria-disabled"); a.title=dl.title||""; }
  else{ a.removeAttribute("href"); a.setAttribute("aria-disabled","true"); a.title=dl.disabled||""; }
}
// The Save / Cancel row shows while something is changed.
function qrPaintSave(){
  const on=qrD.dirty(), n=qrD.count();
  $("qrSaveRow").hidden=!on; $("qrPanel").classList.toggle("dirty",on);
  $("qrSaveN").textContent=on?(n===1?"1 change":n+" changes")+" not saved":"";
}
// After the clip list is drawn again: follow the open clip (closed when it's no longer a draft, redrawn after a remake).
function qrSync(){
  if(!qrKey) return;
  const c=clData.find(x=>clKey(x)===qrKey);
  if(!c || !isDraftClip(c) || !clShowing()){ qrClose(); return; }
  const was=qrC; qrC=c; qrD.follow(c); qrMark(); qrTop(c);
  if(was.remaking && !c.remaking) qrD.remadeDone();
}
const qrTryClose=()=>{ if(qrLeave()) qrClose(); };
$("qrX").onclick=qrTryClose;
$("qrShade").onclick=qrTryClose;
$("qrSave").onclick=async()=>{ const b=$("qrSave"); b.disabled=true; b.lastChild.textContent="Saving..."; await qrD.save(); b.disabled=!!(qrC&&qrC.remaking); b.lastChild.textContent="Save"; };
$("qrCancel").onclick=()=>{ qrD.cancel(); if(qrC) $("qrTitle").textContent=qrC.title; };
// the panel's heading follows the title as it's typed
$("qrEdit").addEventListener("input",e=>{ if(e.target.matches("input.title")) $("qrTitle").textContent=e.target.value; });
$("qrEditBtn").onclick=()=>{ if(qrC && qrLeave()) openEditor(qrC.job,qrC.idx); };
// Schedule just this clip: the clip browser's dialog, with only it ticked (the ticks from before come back after).
$("qrSched").onclick=()=>{ if(!qrC || !qrLeave()) return; clKeptPicks=new Set(clPicked); clPicked=new Set([qrKey]); clSchedDialog(); };
// Escape closes it, unless a dialog or the ⋮ menu is open (they close first). Capture: before the ⋮ menu's own handler.
document.addEventListener("keydown",e=>{
  if(e.key==="Escape" && qrKey && !document.querySelector("dialog[open]") && !cmFor) qrTryClose();
},true);
document.body.appendChild($("qrPanel")); document.body.appendChild($("qrShade"));
