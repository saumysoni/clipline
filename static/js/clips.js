// Shorts & Reels page: the clips that went out, or are going out now (web/clips.py), filtered by status, platform and
// vlog. Drafts and scheduled clips have their own pages (js/drafts.js, js/on-youtube.js). The clip browser (#clBrowse:
// bar + grid, Select, the dock, the schedule dialog) is shared: Drafts' Shorts & Reels tab shows it in "drafts" mode.
// Each card: play, and ⋮ (js/card-menu.js) for Edit (the vlog's editor panel for that Short), Analytics, Download. Select shows
// a tick box on every card (on both pages) to schedule several at once on YouTube and/or Instagram, or delete drafts. On Drafts a card opens Quick review (js/quick-review.js) and its
// Edit button the editor (js/editor.js); there the cards are grouped under their vlog, each group with Review & post
// (the vlog's review page), and a vlog whose Shorts are being made, are paused or stopped shows its progress instead
// (js/drafts.js dfMaking: Pause / Resume, Stop, Try again).
let clData=[], clPlat="", clVlog="", clPicked=new Set(), clTimer=null, clMode="out", clOnPaint=null, clViews={}, clViewsAt=0;
const clKey=c=>c.job+":"+c.idx;
// Where a clip belongs. Drafts: on neither platform (a draft, or its only posting failed). Scheduled: only planned.
// Shorts & Reels: everything else (on a platform, or on its way).
const CL_ON=["posted","scheduled","uploading","posting"];
const isDraftClip=c=>c.status==="draft" || (c.status==="failed" && ![c.youtube,c.instagram].some(p=>p && CL_ON.includes(p.state)));
const isScheduledClip=c=>c.status==="scheduled" && [c.youtube,c.instagram].every(p=>!p || p.state==="scheduled");
const isOutClip=c=>!isDraftClip(c) && !isScheduledClip(c);
const clInMode=c=>clMode==="drafts" ? isDraftClip(c) : isOutClip(c);
const clShowing=()=>$("clBrowse").offsetParent!==null;
// On this page a platform counts only once the clip is out there (or going out now): a planned post is on Scheduled.
const clOnPlat=(c,plat)=>!!c[plat] && !(clMode==="out" && c[plat].state==="scheduled");
async function openClips(vlog){
  clearInterval(poll); clVlog=vlog||""; location.hash="clips"+(clVlog?"/"+clVlog:"");
  show(9); await clOpen("out", $("s9").querySelector(".work"), clVlog);
}
// Puts the clip browser in box ("out": Shorts & Reels, "drafts": Drafts' tab), for one vlog or all, and loads it.
async function clOpen(mode, box, vlog){
  clMode=mode; box.appendChild($("clBrowse")); $("clBrowse").classList.toggle("drafts", mode==="drafts");
  clVlog=vlog||""; clPicked.clear(); $("clBrowse").classList.remove("selecting");
  $("clSelect").lastChild.textContent="Select"; $("clSelect").setAttribute("aria-pressed",false);
  await loadClips();
}
async function loadClips(){
  clearTimeout(clTimer);
  try{ const r=await fetch("/api/clips"); if(!r.ok) throw 0; const j=await r.json(); clData=j.items||[];
    if(j.removed_on_youtube) clToast(j.removed_on_youtube===1?"1 Short was deleted on YouTube":j.removed_on_youtube+" Shorts were deleted on YouTube",
      "So "+(j.removed_on_youtube===1?"it's a draft":"they're drafts")+" again: schedule or delete "+(j.removed_on_youtube===1?"it":"them")+" here."); }
  catch(e){ $("clErr").textContent="Couldn't load your clips. Check your internet connection, then reload the page."; return; }
  $("clErr").textContent="";
  const live=new Set(clData.map(clKey)); clPicked.forEach(k=>{ if(!live.has(k)) clPicked.delete(k); });
  paintClips(); clLoadViews();
  // Keep an eye on clips that are uploading, posting or being remade.
  if(clShowing() && clData.some(c=>c.remaking||(c.youtube&&c.youtube.state==="uploading")||(c.instagram&&c.instagram.state==="posting")))
    clTimer=setTimeout(loadClips,3000);
}
// One status pill: what the clip is doing on a platform (that platform's icon in front when the two differ).
function clPill(kind,p,icon){
  const [cls,txt] = p.waiting ? ["p-plan","Waiting"] : p.state==="scheduled" ? ["p-plan","Scheduled"] : p.state==="posted" ? ["p-done","Published"]
    : p.state==="uploading" ? ["p-going","Uploading"] : p.state==="posting" ? ["p-going","Posting"] : ["p-bad","Didn't go out"];
  const name=kind==="youtube"?"YouTube":"Instagram";
  const tip = p.waiting ? "Goes up after midnight Pacific (YouTube's daily limit)" : p.state==="uploading" ? p.msg||"" : p.state==="failed" ? p.error||"" : p.when ? whenText(p.when) : "";
  return '<span class="cl-pill '+cls+'" title="'+esc(name+(tip?": "+tip:""))+'">'+
    (icon?'<span class="ms '+(kind==="youtube"?"yt":"ig")+'" aria-hidden="true">'+(kind==="youtube"?"smart_display":"photo_camera")+'</span>':'')+txt+'</span>';
}
// A clip can be ticked while it's missing from at least one platform (and isn't being remade).
const clPickable=c=>!c.remaking && (!c.youtube || !c.instagram || c.youtube.state==="failed" || c.instagram.state==="failed");
// The card's tick box (shown after Select). One that can't be scheduled any more is greyed out and says why.
function clPickHTML(c,on){
  const can=clPickable(c), why=c.remaking?"Being remade: wait for it to finish":"Already on YouTube and Instagram";
  return '<label class="cl-pick'+(can?'':' off')+'" title="'+esc(can?"Tick to schedule or delete":why)+'"><input type="checkbox"'+(on?" checked":"")+(can?'':' disabled')+
    ' aria-label="Select '+esc(c.title)+'"></label>';
}
const clShortDate=iso=>{ const d=new Date(iso); return d.toLocaleDateString(undefined,{month:"short",day:"numeric",year:d.getFullYear()===new Date().getFullYear()?undefined:"numeric"}); };
// A card like YouTube Studio's: the thumbnail (plays the clip), title, where it is and when, its status, and ⋮
// for the rest (Edit, Analytics, Download, Delete).
function clCard(c){
  const k=clKey(c), on=clPicked.has(k);
  // On one platform but not the other (and the file is still here): post it there too, straight from the card.
  const out=p=>p && ["posted","scheduled"].includes(p.state), free=!c.remaking && !c.file_deleted;
  const toIg = free && out(c.youtube) && !c.instagram, toYt = free && out(c.instagram) && !c.youtube;
  const plats=["youtube","instagram"].filter(p=>clOnPlat(c,p));
  // where it went (a draft: the vlog it came from)
  const where = plats.length===2 ? "YouTube & Instagram" : plats[0]==="youtube" ? "YouTube Shorts" : plats[0]==="instagram" ? "Instagram Reels" : c.vlog ? "From "+c.vlog : "Draft";
  const icons = plats.map(p=>'<span class="ms '+(p==="youtube"?"yt":"ig")+'" aria-hidden="true">'+(p==="youtube"?"smart_display":"photo_camera")+'</span>').join("") || '<span class="ms" aria-hidden="true">movie</span>';
  const when = c.posted_at || plats.map(p=>c[p].when).filter(Boolean).sort()[0] || "";
  // One pill when both platforms say the same thing, else one per platform with its icon.
  const same = plats.length===2 && clPill("youtube",c.youtube,false).replace(/title="[^"]*"/,"")===clPill("instagram",c.instagram,false).replace(/title="[^"]*"/,"");
  const pills = !plats.length ? '<span class="cl-pill">Draft</span>'
    : same || plats.length===1 ? clPill(plats[0],c[plats[0]],false) : plats.map(p=>clPill(p,c[p],true)).join("");
  const soon = c.expires && c.expires*1000-Date.now()<86400000;
  const qr=clMode==="drafts";  // Drafts: the picture opens Quick review instead of the player
  return '<article class="clip'+(on?" on":"")+(qr&&qrKey===k?" qr-on":"")+'" data-k="'+esc(k)+'">'+
    '<div class="cl-thumb"><button type="button" class="cl-play" aria-label="'+(qr?"Quick review of ":"Play ")+esc(c.title)+'">'+
      // the whole vertical thumbnail in a wide box, over a blurred copy of itself (so its headline text is never cut)
      (c.thumb?'<span class="cl-blur" style="background-image:url(\'/media/'+esc(c.job)+'/'+esc(c.thumb)+'\')"></span><img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="" loading="lazy">':'')+'<span class="ms cl-pi" aria-hidden="true">'+(qr?"visibility":"play_arrow")+'</span></button>'+
      clPickHTML(c,on)+
      '<span class="cl-len">'+fmt(c.length)+'</span>'+
      (c.remaking?'<div class="cl-busy"><span class="spin" aria-hidden="true"></span>Being remade</div>':'')+'</div>'+
    '<div class="cl-body"><b class="cl-t" title="'+esc(c.title)+(c.vlog?' (from '+esc(c.vlog)+')':'')+'">'+esc(c.title)+'</b>'+
      '<div class="cl-meta">'+icons+'<span>'+esc(where)+(when?' · '+esc(clShortDate(when)):'')+'</span></div>'+
      (toIg?'<button type="button" class="cl-to" data-to="instagram"><span class="ms" aria-hidden="true">add</span>Post it on Instagram too</button>':'')+
      (toYt?'<button type="button" class="cl-to" data-to="youtube"><span class="ms" aria-hidden="true">add</span>Post it on YouTube too</button>':'')+
      (soon?'<div class="cl-warn" title="Drafts are deleted after 30 days without an edit. Post, schedule or edit it to keep it."><span class="ms" aria-hidden="true">schedule</span><span>Deleted '+esc(vlSoon(c.expires))+' unless edited or posted</span></div>':'')+'</div>'+
    '<div class="cl-foot"><div class="cl-pills">'+pills+'</div>'+clViewsHTML(k)+
      (clMode==="drafts"&&!c.remaking?'<button type="button" class="ghost sm cl-ed">Edit</button>':'')+cmButton(c.title)+'</div></article>';
}
// Views so far (YouTube + Instagram added up; each platform in the tooltip), from /api/clips/views (web/clip_views.py).
const clCompact=n=>new Intl.NumberFormat(undefined,{notation:"compact",maximumFractionDigits:1}).format(n);
function clViewsHTML(k){
  const v=clViews[k]; if(!v) return '<span class="cl-views" data-k="'+esc(k)+'" hidden></span>';
  const parts=[v.youtube!=null&&"YouTube "+v.youtube.toLocaleString()+" views", v.instagram!=null&&"Instagram "+v.instagram.toLocaleString()+" views"].filter(Boolean);
  const n=(v.youtube||0)+(v.instagram||0);
  return '<span class="cl-views" data-k="'+esc(k)+'" role="img" aria-label="'+esc(n.toLocaleString()+" views")+'" title="'+esc(parts.join(" · "))+'"><span class="ms" aria-hidden="true">visibility</span>'+clCompact(n)+'</span>';
}
// Asked after the cards are drawn (never holds them up), at most once a minute; the cards' counts are filled in place.
async function clLoadViews(){
  if(clMode!=="out" || Date.now()-clViewsAt<60000 || !clData.some(c=>c.status!=="draft")) return;
  clViewsAt=Date.now();
  try{ const r=await fetch("/api/clips/views"); if(!r.ok) throw 0; clViews=(await r.json()).views||{}; }
  catch(e){ clViewsAt=0; return; }  // no counts this time; try again on the next load
  $("clGrid").querySelectorAll(".cl-views").forEach(el=>{ el.outerHTML=clViewsHTML(el.dataset.k); });
}
// Download for a clip (the ⋮ menu, Quick review, the editor). A posted clip's file is deleted after a while
// (web/retention.py): then it's downloaded from where it was posted.
function clDownloadItem(c){
  const postedYt=c.youtube&&c.youtube.state==="posted"&&c.youtube.video_id;
  const dl=String(c.title||"Short").replace(/[\\/:*?"<>|]+/g,"").slice(0,60);
  return !c.file_deleted
    ? {label:"Download", icon:"download", download:true, title:"Download, with its thumbnail as the first frame",
       href:"/media/"+c.job+"/"+c.video+"?cover=1&thumb="+encodeURIComponent(c.thumb||"")+"&dl="+encodeURIComponent(dl+".mp4")}
    : postedYt ? {label:"Download from Studio", icon:"open_in_new", href:studioLink(c.youtube.video_id), title:"Pit Crew no longer keeps this file. Download it from YouTube Studio (⋮ › Download)."}
    : c.instagram&&c.instagram.permalink ? {label:"Open on Instagram", icon:"open_in_new", href:c.instagram.permalink, title:"Pit Crew no longer keeps this file"}
    : {label:"Download", icon:"download", disabled:"Pit Crew no longer keeps this file"};
}
// What the ⋮ menu offers for a clip. On Drafts: Quick review, Edit = the editor, and the vlog's own editor (Try again).
function clMenuItems(c){
  const postedYt=c.youtube&&c.youtube.state==="posted"&&c.youtube.video_id, posted=c.status==="posted";
  const canAn = postedYt || (c.instagram&&c.instagram.state==="posted");
  const busy = posted?"It's posted: change it in YouTube Studio or on Instagram":c.remaking?"It's being remade":"";
  const drafts = clMode==="drafts" ? [
    {label:"Quick review", icon:"visibility", run:()=>qrOpen(c)},
    {label:"Play", icon:"play_arrow", run:()=>clPlay(c), disabled:c.file_deleted?"Pit Crew no longer keeps this file":""},
    {label:"Edit", icon:"edit", run:()=>openEditor(c.job,c.idx), disabled:busy},
    {label:"Review & post", icon:"fact_check", run:()=>openJob(c.job,c.idx), disabled:busy, title:"This vlog's review page: Post this, Try again, Add a Short"},
  ] : [
    {label:"Play", icon:"play_arrow", run:()=>clPlay(c), disabled:c.file_deleted?"Pit Crew no longer keeps this file":""},
    {label:"Edit", icon:"edit", run:()=>openJob(c.job,c.idx), disabled:busy},
  ];
  // Shorts & Reels: take it down from YouTube and/or Instagram (js/clip-remove.js)
  const out = clMode==="out" && clRemovable(c).length ? [{label:"Delete", icon:"delete", danger:true, run:()=>clRemove(c)}] : [];
  return drafts.concat(clMode==="drafts" ? [] : [  // a draft has no numbers yet
    {label:"Analytics", icon:"bar_chart", disabled:canAn?"":"Post it to see its numbers",
     run:()=>{ if(postedYt) openShortAnalytics(c.youtube.video_id,c.youtube.channel); else openAnalytics(c.job,"instagram"); }},
  ]).concat([clDownloadItem(c)]).concat(out).concat(c.status==="draft"&&!c.remaking ? [{label:"Delete draft", icon:"delete", danger:true, run:()=>clDelete([c])}] : []);
}
function clFiltered(){
  const plat=clMode==="drafts" ? "" : clPlat;
  return clData.filter(c=>clInMode(c) && (!clVlog||c.job===clVlog) && (!plat||clOnPlat(c,plat)));
}
function paintClips(){
  // vlog choices (the ones with clips on this page), newest first
  const pool=clData.filter(clInMode);
  const vlogs=[...new Map(pool.concat(clData.filter(c=>c.job===clVlog)).map(c=>[c.job,c])).values()];
  $("clVlog").innerHTML='<option value="">All vlogs</option>'+vlogs.map(c=>'<option value="'+esc(c.job)+'">'+esc(c.vlog)+' · '+esc(vlDate(c.vlog_created))+(c.video_deleted?' (video deleted)':'')+'</option>').join("");
  $("clVlog").value=clVlog;
  const one=vlogs.find(c=>c.job===clVlog);
  if(clMode==="out"){
    clPlatTabs();
    $("clTitle").textContent = one ? one.vlog : "Shorts & Reels";
    $("clLede").textContent = one ? "The Shorts and Reels from this vlog that went out. Its drafts and scheduled ones are under Drafts and Scheduled."
                                  : "Clips that went out on YouTube or Instagram. Drafts and scheduled ones are under Drafts and Scheduled.";
    $("clAdd").hidden = !one || one.video_deleted;
  }
  const base=clFiltered(), list=clSorted(base);
  const [emptyB,emptyT] = pool.length ? ["Nothing here","Try another filter."]
    : clMode==="drafts" ? ["No Shorts or Reels drafts", clData.length?"Every clip Pit Crew made is posted or scheduled. Make Shorts from a vlog to get new ones.":"Upload a vlog and Pit Crew turns it into Shorts and Reels."]
    : ["Nothing posted yet", clData.length?"Your clips are under Drafts and Scheduled. They show up here once they go out.":"Upload a vlog and Pit Crew turns it into Shorts and Reels."];
  const making=clMode==="drafts" ? dfMaking().filter(v=>!clVlog||v.id===clVlog) : [];
  setHTML($("clGrid"), list.length||making.length ? (clMode==="drafts" ? clGroupsHTML(list,making) : list.map(clCard).join(""))
    : '<div class="card cl-empty"><span class="ms" aria-hidden="true">movie</span><b>'+emptyB+'</b><span>'+emptyT+'</span></div>');
  if(clMode==="drafts") clWireGroups(making);
  $("clGrid").querySelectorAll(".clip").forEach(el=>{
    const c=clData.find(x=>clKey(x)===el.dataset.k);
    const pick=el.querySelector(".cl-pick input");
    // While selecting, the picture ticks the card instead of playing it
    el.querySelector(".cl-play").onclick=()=>{
      if($("clBrowse").classList.contains("selecting")){ if(!pick.disabled){ pick.checked=!pick.checked; pick.onchange(); } return; }
      clMode==="drafts"?qrOpen(c):clPlay(c); };
    if(pick) pick.onchange=()=>{ pick.checked?clPicked.add(el.dataset.k):clPicked.delete(el.dataset.k); el.classList.toggle("on",pick.checked); clDock(); };
    const to=el.querySelector(".cl-to"); if(to) to.onclick=()=>clPostOne(c,to.dataset.to);
    const ed=el.querySelector(".cl-ed"); if(ed) ed.onclick=()=>openEditor(c.job,c.idx);
    const more=el.querySelector(".cm-more"); more.onclick=()=>cardMenu(more,clMenuItems(c));
  });
  clDock();
  if(clOnPaint) clOnPaint();
}
// ---- Drafts: the clips under their vlog (newest vlog first). A group's head: the vlog, how many drafts, and Review &
// post (its review page: Post this, Try again, Add a Short). A vlog whose Shorts are being made, are paused or stopped
// (making: from /api/vlogs, js/drafts.js) heads its group with its progress and Pause / Resume, Stop, Try again.
function clGroupsHTML(list,making){
  const groups=new Map();
  for(const v of making) groups.set(v.id,{id:v.id, at:v.created, title:v.title, v, clips:[]});
  for(const c of list){
    if(!groups.has(c.job)) groups.set(c.job,{id:c.job, at:c.vlog_created, title:c.vlog||"Your vlog", clips:[]});
    groups.get(c.job).clips.push(c);
  }
  return [...groups.values()].sort((a,b)=>(b.at||0)-(a.at||0)).map(g=>clGroupHead(g)+g.clips.map(clCard).join("")).join("");
}
function clGroupHead(g){
  const v=g.v, n=g.clips.length, k=esc(g.id);
  const sub=[n?n+" draft"+(n===1?"":"s"):"", v&&v.duration?fmt(v.duration)+" vlog":""].filter(Boolean).join(" · ");
  let body="";
  if(v && (v.status==="working" || v.status==="paused")){
    const paused=v.status==="paused", pct=vlPct(v);
    body='<div class="clg-run'+(paused?' paused':'')+'">'+
      (paused?'<span class="ms" aria-hidden="true">pause_circle</span>':'<span class="spin" aria-hidden="true"></span>')+
      '<span class="clg-run-t"><b>'+(paused?"Paused":v.pausing?"Pausing after this step":"Making your Shorts")+' · '+pct+'%</b>'+
        '<small>'+esc(paused?"What's done is kept. Resume when you're ready.":v.msg||"Working")+'</small></span>'+
      '<i class="clg-bar"><i style="width:'+pct+'%"></i></i>'+
      '<span class="clg-acts">'+
        '<button type="button" class="ghost sm clg-pause" data-k="'+k+'"'+(!paused&&v.pausing?' disabled':'')+'><span class="ms" aria-hidden="true">'+(paused?"play_arrow":"pause")+'</span>'+(paused?"Resume":"Pause")+'</button>'+
        '<button type="button" class="ghost sm clg-stop" data-k="'+k+'"><span class="ms" aria-hidden="true">stop_circle</span>Stop</button>'+
        '<button type="button" class="linkbtn clg-see" data-k="'+k+'">See progress</button></span></div>';
  }else if(v && v.status==="error"){
    body='<div class="clg-run bad"><span class="ms" aria-hidden="true">error</span>'+
      '<span class="clg-run-t"><b>Stopped</b><small>'+esc(v.error||"Something went wrong.")+'</small></span>'+
      '<span class="clg-acts"><button type="button" class="ghost sm clg-again" data-k="'+k+'"><span class="ms" aria-hidden="true">refresh</span>Try again</button>'+
        (v.removable?'<button type="button" class="ghost sm clg-rm" data-k="'+k+'"><span class="ms" aria-hidden="true">delete</span>Remove</button>':'')+
        '<button type="button" class="linkbtn clg-see" data-k="'+k+'">See why</button></span></div>';
  }
  const review = n && !(v && ["working","paused"].includes(v.status));
  return '<div class="clg" data-k="'+k+'"><div class="clg-head"><span class="clg-t"><b title="'+esc(g.title)+'">'+esc(g.title)+'</b>'+(sub?'<small>'+esc(sub)+'</small>':'')+'</span>'+
    (review?'<button type="button" class="ghost sm clg-review" data-k="'+k+'"><span class="ms" aria-hidden="true">fact_check</span>Review &amp; post</button>':'')+'</div>'+body+'</div>';
}
function clWireGroups(making){
  const g=$("clGrid"), V=id=>making.find(v=>v.id===id), err=$("clErr");
  const again=async()=>{ refreshJobsNow(); await loadDraftVlogs(); paintClips(); };
  g.querySelectorAll(".clg-review").forEach(b=>b.onclick=()=>openJob(b.dataset.k));
  g.querySelectorAll(".clg-see").forEach(b=>b.onclick=()=>startPolling(b.dataset.k));
  g.querySelectorAll(".clg-pause").forEach(b=>b.onclick=()=>{ const v=V(b.dataset.k); b.disabled=true;
    (v.status==="paused"?resumeVlog:pauseVlog)(v.id, err, async()=>{ await loadDraftVlogs(); paintClips(); }); });
  g.querySelectorAll(".clg-stop").forEach(b=>b.onclick=()=>{ const v=V(b.dataset.k);
    stopVlog(v.id, v.kind==="vlog", err, async()=>{ await loadDraftVlogs(); await loadClips(); }); });
  g.querySelectorAll(".clg-again").forEach(b=>b.onclick=async()=>{ b.disabled=true;
    let r,j; try{ r=await fetch("/api/vlogs/"+b.dataset.k+"/again",{method:"POST"}); j=await r.json(); }
    catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
    if(!r.ok){ err.textContent=j.error||"Couldn't start it again."; b.disabled=false; return; }
    err.textContent=""; again(); });
  g.querySelectorAll(".clg-rm").forEach(b=>b.onclick=async()=>{ await vlDelete([V(b.dataset.k)]); takeErr("vlErr","clErr"); await loadDraftVlogs(); paintClips(); });
}
// Select all: every clip shown (with the current filters) that can be ticked.
function clShown(){ return clSorted(clFiltered()); }
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
  $("clDock").hidden=!n || !clShowing();
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
// Platform tabs: All / YouTube Shorts / Instagram Reels, each with how many clips (for the vlog chosen, if any).
$("clPlatTabs").querySelectorAll("button").forEach(b=>b.onclick=()=>{ clPlat=b.dataset.p; paintClips(); });
function clPlatTabs(){
  const pool=clData.filter(c=>isOutClip(c) && (!clVlog||c.job===clVlog));
  $("clNAll").textContent=pool.length; $("clNYt").textContent=pool.filter(c=>clOnPlat(c,"youtube")).length; $("clNIg").textContent=pool.filter(c=>clOnPlat(c,"instagram")).length;
  $("clPlatTabs").querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.p===clPlat));
}
$("clSort").onchange=()=>{ try{ localStorage.setItem("pc-clip-sort",$("clSort").value); }catch(e){} paintClips(); };
try{ const v=localStorage.getItem("pc-clip-sort"); if(v) $("clSort").value=v; }catch(e){}
// "Recently posted first": posted clips by when they went out (newest first), then the rest in vlog order.
function clSorted(list){
  if($("clSort").value!=="posted") return list;
  const t=c=>c.posted_at?Date.parse(c.posted_at):0;
  return [...list].sort((a,b)=>t(b)-t(a));  // stable: unposted keep their vlog order at the end
}
$("clVlog").onchange=()=>{ clVlog=$("clVlog").value; if(clMode==="out") location.hash="clips"+(clVlog?"/"+clVlog:""); paintClips(); };
$("clNew").onclick=()=>openMake();  // from a vlog uploaded here, or a new video file (js/make-choice.js)
$("clUpload").onclick=()=>openCreate();  // a new video file: the setup page (screen 1)
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
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ $("clErr").textContent=j.error||"Couldn't delete them."; return; }
  drafts.forEach(c=>clPicked.delete(clKey(c)));
  clToast(j.deleted.length===1?"Draft deleted":j.deleted.length+" drafts deleted", j.kept.length?j.kept.length+" couldn't be deleted (being remade or posted).":"");
  loadClips();
}
$("clDelMany").onclick=()=>clDelete(clData.filter(c=>clPicked.has(clKey(c))));
$("clClear").onclick=()=>clSelecting(false);
// Ticking clips (to schedule or delete several) is a mode: the tick boxes only show after Select.
function clSelecting(on){
  $("clBrowse").classList.toggle("selecting",on); if(!on) clPicked.clear();
  $("clSelect").lastChild.textContent=on?"Cancel":"Select"; $("clSelect").setAttribute("aria-pressed",on);
  paintClips();
}
$("clSelect").onclick=()=>clSelecting(!$("clBrowse").classList.contains("selecting"));
// ---- schedule several
$("clSchedOpen").onclick=()=>clSchedDialog();
// One clip, to the platform it's missing from (the card's "Post it there too"): the same dialog, with only that
// platform ticked. The clips ticked before stay ticked afterwards.
let clKeptPicks=null;
function clPostOne(c,plat){
  if(plat==="instagram" && !ig.signed_in){ igSignIn(()=>clPostOne(c,plat)); return; }
  if(plat==="youtube" && !yt.signed_in){ signIn(()=>clPostOne(c,plat)); return; }
  clKeptPicks=new Set(clPicked); clPicked=new Set([clKey(c)]);
  clSchedDialog(plat,c);
}
$("clSched").addEventListener("close",()=>{ if(clKeptPicks){ clPicked=clKeptPicks; clKeptPicks=null; paintClips(); } });
function clSchedDialog(only,c){
  const n=clPicked.size;
  $("clSchedTitle").textContent = only ? "Post to "+(only==="instagram"?"Instagram":"YouTube") : "Schedule "+n+" clip"+(n===1?"":"s");
  $("clSchedLede").textContent = only ? '"'+c.title+'" as a '+(only==="instagram"?"Reel":"Short")+": right away, or at a time you choose."
    : "One plan of times for all of them, in the order they're shown. Clips already on a platform are skipped there.";
  const ytOk=!!yt.signed_in, igOk=!!(ig.signed_in&&ig.can_post);
  $("clSchedBoth").hidden=!!only;
  $("clToYt").disabled=!ytOk || only==="instagram"; $("clToYt").checked=ytOk && only!=="instagram";
  $("clToIg").disabled=!igOk || only==="youtube"; $("clToIg").checked=igOk && only==="instagram";
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
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  $("clSchedGo").disabled=false;
  if(!r.ok){ $("clSchedErr").textContent=j.error||"Couldn't schedule them."; if(j.signin==="youtube") signIn(); else if(j.signin==="instagram") igSignIn(); return; }
  clKeptPicks=null; $("clSched").close(); clPicked.clear(); $("clBrowse").classList.remove("selecting"); $("clSelect").lastChild.textContent="Select"; $("clSelect").setAttribute("aria-pressed",false);
  const parts=[j.youtube&&j.youtube+" to YouTube", j.instagram&&j.instagram+" to Instagram"].filter(Boolean);
  clToast("Scheduled "+parts.join(" and "), $("clWhen").value==="now"?"They're going out now: see them in Shorts & Reels.":"See them under Scheduled.");
  loadClips();
};
function clToast(title,text){
  const t=document.createElement("div"); t.className="toast"; t.setAttribute("role","status");
  t.innerHTML='<span class="ms" aria-hidden="true">check_circle</span><span><b>'+esc(title)+'</b>'+esc(text)+'</span>';
  document.body.appendChild(t); setTimeout(()=>t.classList.add("go"),5000); setTimeout(()=>t.remove(),5600);
}
// The one-Short analytics window lives in the Analytics page's markup; move it out so it opens from here too.
// The selection bar floats over the screen, so it can't stay inside the (animated) page either. The player and the
// schedule dialog also open from Drafts, and a dialog inside a hidden page can't show.
document.body.appendChild($("anDetail"));
document.body.appendChild($("clDock"));
document.body.appendChild($("clPlayer"));
document.body.appendChild($("clSched"));
