// Shorts & Reels page: every clip from every vlog (web/clips.py), filtered by status, platform and vlog.
// Each card: play, Analytics, Download, Edit (opens the vlog's editor panel for that Short). Tick clips to
// schedule several at once on YouTube and/or Instagram.
let clData=[], clStatus="", clVlog="", clPicked=new Set(), clTimer=null;
const clKey=c=>c.job+":"+c.idx;
async function openClips(vlog){
  clearInterval(poll); clVlog=vlog||""; clStatus=""; location.hash="clips"+(clVlog?"/"+clVlog:"");
  show(9); $("s9").classList.remove("selecting"); clPicked.clear(); $("clSelect").lastChild.textContent="Select"; $("clSelect").setAttribute("aria-pressed",false);
  await loadClips();
}
async function loadClips(){
  clearTimeout(clTimer);
  try{ const r=await fetch("/api/clips"); if(!r.ok) throw 0; const j=await r.json(); clData=j.items||[];
    if(j.removed_on_youtube) clToast(j.removed_on_youtube===1?"1 Short was deleted on YouTube":j.removed_on_youtube+" Shorts were deleted on YouTube",
      "So "+(j.removed_on_youtube===1?"it's a draft":"they're drafts")+" again: schedule or delete "+(j.removed_on_youtube===1?"it":"them")+" here."); }
  catch(e){ $("clErr").textContent="Couldn't load your clips. Is Pit Crew still running?"; return; }
  $("clErr").textContent="";
  const live=new Set(clData.map(clKey)); clPicked.forEach(k=>{ if(!live.has(k)) clPicked.delete(k); });
  paintClips();
  // Keep an eye on clips that are uploading, posting or being remade.
  if(!$("s9").hidden && clData.some(c=>c.remaking||(c.youtube&&c.youtube.state==="uploading")||(c.instagram&&c.instagram.state==="posting")))
    clTimer=setTimeout(loadClips,3000);
}
function clPlatLine(kind,p){
  const isYt=kind==="youtube", name=isYt?"YouTube":"Instagram", icon=isYt?"smart_display":"photo_camera";
  const txt = p.state==="scheduled" ? whenText(p.when).replace("Scheduled for ","")
    : p.state==="posted" ? (p.when?whenText(p.when).replace("Went out ","Posted "):"Posted")
    : p.state==="uploading" ? (p.msg||"Uploading")+"..." : p.state==="posting" ? "Posting now..." : "Didn't go out";
  const cls = p.state==="failed" ? "bad" : p.state==="posted" ? "done" : "plan";
  return '<div class="cl-pl '+cls+'" title="'+esc(p.error||"")+'"><span class="ms '+(isYt?"yt":"ig")+'" aria-hidden="true">'+icon+'</span><span><b>'+name+'</b> · '+esc(txt)+'</span></div>';
}
// A clip can be ticked while it's missing from at least one platform (and isn't being remade).
const clPickable=c=>!c.remaking && (!c.youtube || !c.instagram || c.youtube.state==="failed" || c.instagram.state==="failed");
function clCard(c){
  const k=clKey(c), on=clPicked.has(k), postedYt=c.youtube&&c.youtube.state==="posted"&&c.youtube.video_id;
  const posted=c.status==="posted", dl=String(c.title||"Short").replace(/[\\/:*?"<>|]+/g,"").slice(0,60);
  const plats=(c.youtube?clPlatLine("youtube",c.youtube):"")+(c.instagram?clPlatLine("instagram",c.instagram):"")||
    '<div class="cl-pl draft"><span class="ms" aria-hidden="true">edit</span><span>Draft · not posted yet</span></div>';
  const canAn = postedYt || (c.instagram&&c.instagram.state==="posted");
  const soon = c.expires && c.expires*1000-Date.now()<86400000;
  // A posted clip's file is deleted after a while (web/retention.py): then it's downloaded from where it was posted.
  const dlHTML = !c.file_deleted
    ? '<a class="cl-dl" href="/media/'+esc(c.job)+'/'+esc(c.video)+'?cover=1&thumb='+encodeURIComponent(c.thumb||"")+'&dl='+encodeURIComponent(dl+".mp4")+'" download title="Download, with its thumbnail as the first frame">Download</a>'
    : postedYt ? '<a class="cl-dl" href="'+esc(studioLink(c.youtube.video_id))+'" target="_blank" rel="noopener" title="Pit Crew no longer keeps this file. Download it from YouTube Studio (⋮ › Download).">Studio</a>'
    : c.instagram&&c.instagram.permalink ? '<a class="cl-dl" href="'+esc(c.instagram.permalink)+'" target="_blank" rel="noopener" title="Pit Crew no longer keeps this file">Instagram</a>'
    : '<span class="cl-dl off" title="Pit Crew no longer keeps this file">Download</span>';
  return '<article class="clip'+(on?" on":"")+'" data-k="'+esc(k)+'">'+
    '<div class="cl-thumb"><button type="button" class="cl-play" aria-label="Play '+esc(c.title)+'">'+
      (c.thumb?'<img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="" loading="lazy">':'')+'<span class="ms cl-pi" aria-hidden="true">play_arrow</span></button>'+
      (clPickable(c)?'<label class="cl-pick" title="Tick to schedule"><input type="checkbox"'+(on?" checked":"")+' aria-label="Select '+esc(c.title)+'"></label>':'')+
      '<span class="cl-len">'+fmt(c.length)+'</span>'+
      (c.status==="draft"&&!c.remaking?'<button type="button" class="cl-del" title="Delete this draft" aria-label="Delete the draft '+esc(c.title)+'"><span class="ms" aria-hidden="true">delete</span></button>':'')+
      (c.remaking?'<div class="cl-busy"><span class="spin" aria-hidden="true"></span>Being remade</div>':'')+'</div>'+
    '<div class="cl-body"><b class="cl-t" title="'+esc(c.title)+'">'+esc(c.title)+'</b><small class="cl-v">'+esc(c.vlog)+'</small>'+plats+
      (soon?'<div class="cl-pl warn" title="Drafts are deleted after 30 days without an edit. Post, schedule or edit it to keep it."><span class="ms" aria-hidden="true">schedule</span><span>Deleted '+esc(vlSoon(c.expires))+' unless edited or posted</span></div>':'')+'</div>'+
    '<div class="cl-acts">'+
      '<button type="button" class="linkbtn cl-an"'+(canAn?'':' disabled title="Post it to see its numbers"')+'>Analytics</button>'+
      dlHTML+
      '<button type="button" class="linkbtn cl-ed"'+(posted?' disabled title="It\'s posted: change it in YouTube Studio or on Instagram"':c.remaking?' disabled':'')+'>Edit</button>'+
    '</div></article>';
}
function clFiltered(){
  const plat=$("clPlat").value;
  return clData.filter(c=>(!clVlog||c.job===clVlog) && (!plat||c[plat]));
}
function paintClips(){
  // vlog choices, newest first
  const vlogs=[...new Map(clData.map(c=>[c.job,c])).values()];
  $("clVlog").innerHTML='<option value="">All vlogs</option>'+vlogs.map(c=>'<option value="'+esc(c.job)+'">'+esc(c.vlog)+' · '+esc(vlDate(c.vlog_created))+(c.video_deleted?' (video deleted)':'')+'</option>').join("");
  $("clVlog").value=clVlog;
  const one=vlogs.find(c=>c.job===clVlog);
  $("clTitle").textContent = one ? one.vlog : "Your Shorts & Reels";
  $("clLede").textContent = one ? "The Shorts and Reels from this vlog. Use Select to schedule or delete several at once."
                                : "Every clip Pit Crew made, from all your vlogs. Use Select to schedule or delete several at once.";
  $("clAdd").hidden = !one || one.video_deleted;
  // status chips with counts
  const base=clFiltered(), n=st=>base.filter(c=>!st||c.status===st).length;
  const chips=[["","All"],["draft","Drafts"],["scheduled","Scheduled"],["posted","Posted"],["failed","Failed"]].filter(([st])=>!st||st!=="failed"||n("failed"));
  if(clStatus && !n(clStatus)) clStatus="";
  $("clChips").innerHTML=chips.map(([st,lab])=>'<button type="button" class="cl-chip" data-st="'+st+'" aria-pressed="'+(clStatus===st)+'">'+lab+' <span>'+n(st)+'</span></button>').join("");
  $("clChips").querySelectorAll(".cl-chip").forEach(b=>b.onclick=()=>{ clStatus=b.dataset.st; paintClips(); });
  const list=clSorted(base.filter(c=>!clStatus||c.status===clStatus));
  $("clGrid").innerHTML = list.length ? list.map(clCard).join("") : '<div class="card cl-empty"><span class="ms" aria-hidden="true">movie</span><b>'+
    (clData.length?"Nothing here":"No clips yet")+'</b><span>'+(clData.length?"Try another filter.":"Upload a vlog and Pit Crew turns it into Shorts and Reels.")+'</span></div>';
  $("clGrid").querySelectorAll(".clip").forEach(el=>{
    const c=clData.find(x=>clKey(x)===el.dataset.k);
    el.querySelector(".cl-play").onclick=()=>clPlay(c);
    const pick=el.querySelector(".cl-pick input");
    if(pick) pick.onchange=()=>{ pick.checked?clPicked.add(el.dataset.k):clPicked.delete(el.dataset.k); el.classList.toggle("on",pick.checked); clDock(); };
    el.querySelector(".cl-an").onclick=()=>{
      if(c.youtube&&c.youtube.video_id&&c.youtube.state==="posted") openShortAnalytics(c.youtube.video_id,c.youtube.channel); else openAnalytics(c.job,"instagram");
    };
    el.querySelector(".cl-ed").onclick=()=>openJob(c.job,c.idx);
    const del=el.querySelector(".cl-del"); if(del) del.onclick=()=>clDelete([c]);
  });
  clDock();
}
// Select all: every clip shown (with the current filters) that can be ticked.
function clShown(){ return clSorted(clFiltered().filter(c=>!clStatus||c.status===clStatus)); }
$("clAll").onchange=()=>{
  const can=clShown().filter(clPickable);
  if($("clAll").checked) can.forEach(c=>clPicked.add(clKey(c))); else can.forEach(c=>clPicked.delete(clKey(c)));
  paintClips();
};
function clDock(){
  const n=clPicked.size;
  const can=clShown().filter(clPickable), all=can.length>0 && can.every(c=>clPicked.has(clKey(c)));
  $("clAll").checked=all; $("clAll").indeterminate=!all && can.some(c=>clPicked.has(clKey(c))); $("clAll").disabled=!can.length;
  $("clAllT").textContent = n ? n+" selected" : "Select all";
  $("clDock").hidden=!n || $("s9").hidden;
  $("clSel").textContent=n+" clip"+(n===1?"":"s")+" selected";
  const drafts=clData.filter(c=>clPicked.has(clKey(c))&&c.status==="draft").length;
  $("clDelMany").hidden=!drafts; $("clDelMany").lastChild.textContent=drafts===n?"Delete":"Delete "+drafts+" draft"+(drafts===1?"":"s");
}
function clPlay(c){
  $("clPlayTitle").textContent=c.title; $("clVideo").poster=c.thumb?"/media/"+c.job+"/"+c.thumb:"";
  $("clVideo").src="/media/"+c.job+"/"+c.video; $("clPlayer").showModal(); $("clVideo").play().catch(()=>{});
}
$("clPlayX").onclick=()=>$("clPlayer").close();
$("clPlayer").addEventListener("close",()=>{ $("clVideo").pause(); $("clVideo").removeAttribute("src"); $("clVideo").load(); });
$("clPlat").onchange=paintClips;
$("clSort").onchange=()=>{ try{ localStorage.setItem("pc-clip-sort",$("clSort").value); }catch(e){} paintClips(); };
try{ const v=localStorage.getItem("pc-clip-sort"); if(v) $("clSort").value=v; }catch(e){}
// "Recently posted first": posted clips by when they went out (newest first), then the rest in vlog order.
function clSorted(list){
  if($("clSort").value!=="posted") return list;
  const t=c=>c.posted_at?Date.parse(c.posted_at):0;
  return [...list].sort((a,b)=>t(b)-t(a));  // stable: unposted keep their vlog order at the end
}
$("clVlog").onchange=()=>{ clVlog=$("clVlog").value; location.hash="clips"+(clVlog?"/"+clVlog:""); paintClips(); };
$("clNew").onclick=()=>openCreate();
$("clAdd").onclick=()=>openJob(clVlog,"add");
// Deletes drafts only (posted and scheduled clips stay); their files go too, so it can't be undone.
async function clDelete(list){
  const drafts=list.filter(c=>c.status==="draft");
  if(!drafts.length) return;
  const one=drafts.length===1;
  if(!confirm(one?'Delete the draft "'+drafts[0].title+'"?\n\nIts video and thumbnail are deleted. This can\'t be undone.'
                 :'Delete '+drafts.length+' drafts?\n\nTheir videos and thumbnails are deleted. This can\'t be undone.'+
                  (drafts.length<list.length?' Posted and scheduled clips you ticked stay.':''))) return;
  let r,j; try{ r=await fetch("/api/clips/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:drafts.map(c=>({job:c.job,idx:c.idx}))})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  if(!r.ok){ $("clErr").textContent=j.error||"Couldn't delete them."; return; }
  drafts.forEach(c=>clPicked.delete(clKey(c)));
  clToast(j.deleted.length===1?"Draft deleted":j.deleted.length+" drafts deleted", j.kept.length?j.kept.length+" couldn't be deleted (being remade or posted).":"");
  loadClips();
}
$("clDelMany").onclick=()=>clDelete(clData.filter(c=>clPicked.has(clKey(c))));
$("clClear").onclick=()=>clSelecting(false);
// Ticking clips (to schedule or delete several) is a mode: the tick boxes only show after Select.
function clSelecting(on){
  $("s9").classList.toggle("selecting",on); if(!on) clPicked.clear();
  $("clSelect").lastChild.textContent=on?"Cancel":"Select"; $("clSelect").setAttribute("aria-pressed",on);
  paintClips();
}
$("clSelect").onclick=()=>clSelecting(!$("s9").classList.contains("selecting"));
// ---- schedule several
$("clSchedOpen").onclick=()=>{
  const n=clPicked.size;
  $("clSchedTitle").textContent="Schedule "+n+" clip"+(n===1?"":"s");
  $("clSchedLede").textContent="One plan of times for all of them, in the order they're shown. Clips already on a platform are skipped there.";
  const ytOk=!!yt.signed_in, igOk=!!(ig.signed_in&&ig.can_post);
  $("clToYt").disabled=!ytOk; $("clToYt").checked=ytOk;
  $("clToIg").disabled=!igOk; $("clToIg").checked=false;
  $("clYtWho").textContent = ytOk ? "to "+((yt.channel&&yt.channel.title)||"your channel") : "Not connected: connect it from Channels first";
  $("clIgWho").textContent = igOk ? "to @"+(ig.username||"") : ig.signed_in ? "@"+(ig.username||"")+" is a personal account" : "Not connected";
  if(!$("clStart").value){ const d=new Date(Date.now()+86400000); d.setHours(18,0,0,0); $("clStart").value=localInput(d); }
  $("clStart").min=localInput(new Date(Date.now()+16*60000));
  $("clCustom").hidden=$("clWhen").value!=="custom"; $("clSchedErr").textContent="";
  $("clSched").showModal();
};
$("clWhen").onchange=()=>{ $("clCustom").hidden=$("clWhen").value!=="custom"; };
$("clSchedX").onclick=()=>$("clSched").close();
$("clSchedGo").onclick=async()=>{
  const toYt=$("clToYt").checked, toIg=$("clToIg").checked;
  if(!toYt&&!toIg){ $("clSchedErr").textContent="Pick YouTube, Instagram or both."; return; }
  const order=clFiltered().filter(c=>clPicked.has(clKey(c)));  // the order on screen
  for(const k of clPicked) if(!order.some(c=>clKey(c)===k)){ const c=clData.find(x=>clKey(x)===k); if(c) order.push(c); }
  let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
  $("clSchedGo").disabled=true;
  let r,j;
  try{ r=await fetch("/api/clips/schedule",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      items:order.map(c=>({job:c.job,idx:c.idx})), youtube:toYt, instagram:toIg, schedule:$("clWhen").value, tz,
      start:$("clStart").value, every:+$("clEvery").value, channel:yt.channel&&yt.channel.id, ig_id:ig.ig_id})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("clSchedGo").disabled=false;
  if(!r.ok){ $("clSchedErr").textContent=j.error||"Couldn't schedule them."; if(j.signin==="youtube") signIn(); else if(j.signin==="instagram") igSignIn(); return; }
  $("clSched").close(); clPicked.clear(); $("s9").classList.remove("selecting"); $("clSelect").lastChild.textContent="Select"; $("clSelect").setAttribute("aria-pressed",false);
  const parts=[j.youtube&&j.youtube+" to YouTube", j.instagram&&j.instagram+" to Instagram"].filter(Boolean);
  clToast("Scheduled "+parts.join(" and "), $("clWhen").value==="now"?"They're going out now.":"See them under Scheduled.");
  loadClips();
};
function clToast(title,text){
  const t=document.createElement("div"); t.className="toast"; t.setAttribute("role","status");
  t.innerHTML='<span class="ms" aria-hidden="true">check_circle</span><span><b>'+esc(title)+'</b>'+esc(text)+'</span>';
  document.body.appendChild(t); setTimeout(()=>t.classList.add("go"),5000); setTimeout(()=>t.remove(),5600);
}
// The one-Short analytics window lives in the Analytics page's markup; move it out so it opens from here too.
// The selection bar floats over the screen, so it can't stay inside the (animated) page either.
document.body.appendChild($("anDetail"));
document.body.appendChild($("clDock"));
