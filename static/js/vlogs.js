// Vlogs page (home): every vlog uploaded (to make Shorts, or to YouTube with js/vlog-upload.js), newest first, as a list like YouTube's search results (web/vlogs.py):
// a landscape picture on the left, title and details on the right. Tick vlogs (or Select all) to delete several
// videos at once; their Shorts stay.
let vlData=null, vlPicked=new Set();
// Vlogs waiting to go up live on their own pages: Drafts (prepared, not uploaded; js/drafts.js) and Scheduled (uploaded,
// goes public later; js/on-youtube.js). This page shows the rest.
// Draft: a vlog upload (not a Shorts-only video) that's ready, not on YouTube yet, and whose video is kept (so it can be).
const isDraftVlog=v=>v.kind==="vlog" && v.prep && v.status==="ready" && !v.video_deleted && !(v.vpost && v.vpost.state==="done");
// Scheduled: uploaded (or being sent) with a time to go public that hasn't come yet (the "Vlog goes public" badge).
const isScheduledVlog=v=>{ const p=v.vpost||{}; return v.kind==="vlog" && p.privacy==="schedule" && ["done","uploading"].includes(p.state) && !!p.when && new Date(p.when)>new Date(); };
async function openVlogs(){ clearInterval(poll); location.hash="vlogs"; show(7); vlSelecting(false); await loadVlogs(); }
async function loadVlogs(){
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; vlData=(await r.json()).items||[]; }
  catch(e){ if(!vlData) $("vlErr").textContent="Couldn't load your vlogs. Check your internet connection, then reload the page."; return; }
  $("vlErr").textContent=""; paintVlogs();
}
// "today at 6:00 PM" / "tomorrow at 9:30 AM" for a time within the next day or two
function vlSoon(t){
  const d=new Date(t*1000), now=new Date(), day=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime();
  const n=Math.round((day(d)-day(now))/86400000), at=d.toLocaleTimeString([], {hour:"numeric", minute:"2-digit"});
  return (n<=0?"today":n===1?"tomorrow":d.toLocaleDateString([], {weekday:"long"}))+" at "+at;
}
const vlDate=t=>t ? new Date(t*1000).toLocaleString([], {month:"short", day:"numeric", year:new Date(t*1000).getFullYear()===new Date().getFullYear()?undefined:"numeric", hour:"numeric", minute:"2-digit"}) : "";
// Overall progress of a vlog being made: finished stages plus the current stage's share.
const vlPct=v=>v.stages ? Math.min(99, Math.round(((v.stage||0)+(v.pct||0)/100)/v.stages*100)) : 0;
// A vlog's video can be deleted when it's still here and nothing is running on it.
// (a vlog that stopped before making any Shorts is removed completely instead: there's nothing to keep)
const vlDeletable=v=>(!v.video_deleted || v.removable) && v.status!=="working" && !v.remaking && !vlUploading(v);
const vlUploading=v=>!!(v.vpost && v.vpost.state==="uploading");
function vlStats(v){
  if(v.status==="working") return "";
  if(!v.shorts) return v.status==="error" ? "" : "No Shorts yet";
  return v.shorts+" Short"+(v.shorts>1?"s":"");
}
function vlBadges(v){
  const b=[];
  if(v.kind==="vlog" && v.status==="ready"){  // a vlog uploaded with Pit Crew: where it is on YouTube
    const p=v.vpost||{}, when=p.when?new Date(p.when):null;
    if(p.state==="uploading") b.push('<span class="vl-b plan">Uploading to YouTube '+Math.round(p.pct||0)+'%</span>');
    else if(p.state==="done" && p.privacy==="schedule" && when>new Date()) b.push('<span class="vl-b plan">Vlog goes public '+esc(vlDate(when/1000))+'</span>');
    else if(p.state==="done") b.push('<span class="vl-b done">Vlog on YouTube'+(["unlisted","private"].includes(p.privacy)?" · "+p.privacy:"")+'</span>');
    else if(p.state==="error") b.push('<span class="vl-b bad">Upload stopped</span>');
    else b.push('<span class="vl-b">Not uploaded yet</span>');
  }
  return b.length?'<div class="vl-badges">'+b.join("")+'</div>':"";
}
function vlRow(v){
  // Picture: the thumbnail Pit Crew made for the vlog, else its own YouTube thumbnail, else a frame from the vlog,
  // else a Short's thumbnail on a blur.
  const pic = v.vthumb ? '<img src="/media/'+esc(v.id)+'/'+esc(v.vthumb)+'" alt="" loading="lazy">'
    : v.yt_thumb ? '<img src="'+esc(v.yt_thumb)+'" alt="" loading="lazy" referrerpolicy="no-referrer">'
    : v.poster ? '<img src="/media/'+esc(v.id)+'/'+esc(v.poster)+'" alt="" loading="lazy">'
    : v.cover ? '<span class="vl-blur" style="background-image:url(\'/media/'+esc(v.id)+'/'+esc(v.cover)+'\')"></span><img class="vl-tall" src="/media/'+esc(v.id)+'/'+esc(v.cover)+'" alt="" loading="lazy">'
    : v.status==="error" ? '' : '<span class="ms vl-ph" aria-hidden="true">movie</span>';
  const over = v.status==="working"
    ? '<div class="vl-over"><span class="spin" aria-hidden="true"></span><b>'+vlPct(v)+'%</b><small>'+esc(v.msg||"Working")+'</small></div>'
    : v.status==="error" ? '<div class="vl-over bad"><span class="ms" aria-hidden="true">error</span><small>Stopped</small></div>' : "";
  const busy=v.status==="working", on=vlPicked.has(v.id);
  const meta=[vlDate(v.created), v.duration?fmt(v.duration)+" long":"", vlStats(v)].filter(Boolean).join(" · ");
  return '<article class="vrow'+(on?" on":"")+'" data-id="'+esc(v.id)+'">'+
    '<label class="vr-pick"'+(vlDeletable(v)?'':' hidden')+'><input type="checkbox"'+(on?' checked':'')+' aria-label="Select '+esc(v.title)+'"></label>'+
    '<button type="button" class="vr-thumb vl-open" aria-label="Open '+esc(v.title)+'">'+pic+over+
      (v.duration?'<span class="vl-dur">'+fmt(v.duration)+'</span>':'')+'</button>'+
    '<div class="vr-body">'+
      '<button type="button" class="vr-title vl-open" title="'+esc(v.title)+'">'+esc(v.title)+'</button>'+
      '<div class="vr-meta">'+esc(meta)+'</div>'+
      vlBadges(v)+
      (v.status==="working"?'<div class="vr-note">'+(v.prep?"Getting your upload ready":"Making your Shorts")+' · '+esc(v.msg||"")+'</div>':'')+
      (v.status==="error"?'<div class="vr-note bad vr-err"><span class="ms" aria-hidden="true">error</span><span>'+esc(v.error||"Something went wrong. Upload the vlog again.")+'</span></div>':'')+
      (v.video_expires && v.video_expires*1000-Date.now()<86400000 ? '<div class="vr-note warn" title="To keep storage free, a vlog\'s video is deleted after it hasn\'t been edited for a while. Its Shorts stay. Edit one of its Shorts to keep it longer."><span class="ms" aria-hidden="true">schedule</span>Video deleted '+esc(vlSoon(v.video_expires))+'</div>':'')+
      '<div class="vr-acts">'+
        (v.removable?'' : v.prep ? vlPrepActs(v) : vlShortsActs(v)+
        (v.status==="ready"?'<button type="button" class="ghost sm vl-an"'+(v.posted?'':' disabled title="Post a Short to see its numbers"')+'>Analytics</button>':''))+
        (v.youtube_url?'<a class="ghost sm" href="'+esc(v.youtube_url)+'" target="_blank" rel="noopener">On YouTube<span class="ms" aria-hidden="true">open_in_new</span></a>':'')+
        (vlDeletable(v)?(v.removable?'<button type="button" class="ghost sm vl-del" title="It stopped before making any Shorts, so there\'s nothing to keep"><span class="ms" aria-hidden="true">delete</span>Remove</button>'
          :'<button type="button" class="ghost sm vl-del" title="Delete this vlog\'s video (its Shorts stay)"><span class="ms" aria-hidden="true">delete</span>Delete video</button>'):'')+
      '</div>'+
    '</div></article>';
}
// Its Shorts, by where they are: "5 drafts" (Drafts), "1 scheduled" (Scheduled), "2 posted" (Shorts & Reels).
function vlShortsActs(v){
  if(v.status!=="ready" || !v.shorts) return '<button type="button" class="ghost sm vl-open">'+(v.status==="working"?"See progress":"Shorts &amp; Reels")+'</button>';
  const go=(where,n,word,icon)=>n?'<button type="button" class="ghost sm vl-go" data-go="'+where+'"><span class="ms" aria-hidden="true">'+icon+'</span>'+n+' '+word+'</button>':'';
  return go("drafts",v.drafts,v.drafts===1?"draft":"drafts","edit_note")+go("scheduled",v.scheduled,"scheduled","calendar_month")+go("posted",v.posted,"posted","check_circle");
}
// Where a vlog opens: its upload page while it's being prepared for YouTube, its progress while Shorts are being made
// (or why it stopped), else its Shorts: the ones that went out, else its drafts, else Scheduled.
function vlOpen(v){
  if(v.prep) return openVlogUpload(v.id);
  if(v.status!=="ready") return startPolling(v.id);
  if(!v.posted && v.drafts) return openDrafts("shorts",v.id);
  if(!v.posted && v.scheduled) return openPosted("shorts");
  openClips(v.id);
}
// Wires a row's buttons (here, and on Drafts and Scheduled); after() reloads that page once something changed, and a
// delete's problem is shown in errId.
function vlWire(el,v,after,errId){
  el.querySelectorAll(".vl-open").forEach(b=>b.onclick=()=>vlOpen(v));
  el.querySelectorAll(".vl-go").forEach(b=>b.onclick=()=>b.dataset.go==="drafts"?openDrafts("shorts",v.id):b.dataset.go==="scheduled"?openPosted("shorts"):openClips(v.id));
  const mk=el.querySelector(".vl-make"); if(mk) mk.onclick=()=>openMake(v.id);
  const an=el.querySelector(".vl-an"); if(an) an.onclick=()=>openAnalytics(v.id);
  const del=el.querySelector(".vl-del"); if(del) del.onclick=async()=>{ await vlDelete([v]); if(errId!=="vlErr"){ await after(); takeErr("vlErr",errId); } };
}
// A vlog uploaded with Pit Crew that has no Shorts yet: its upload page, and Make Shorts while its video is kept.
function vlPrepActs(v){
  if(v.status!=="ready") return '<button type="button" class="ghost sm vl-open">'+(v.status==="working"?"See progress":"See why")+'</button>';
  const done=v.vpost&&v.vpost.state==="done";
  return '<button type="button" class="ghost sm vl-open">'+(done?"Upload details":vlUploading(v)?"See upload":"Check and upload")+'</button>'+
    (!v.video_deleted && !vlUploading(v)?'<button type="button" class="ghost sm vl-make"><span class="ms" aria-hidden="true">auto_awesome</span>Make Shorts</button>':'');
}
function vlShown(){
  const q=$("vlFind").value.trim().toLowerCase();
  return vlBase().filter(v=>!q || v.title.toLowerCase().includes(q));
}
function vlBase(){ return vlData.filter(v=>!v.video_deleted && !isDraftVlog(v) && !isScheduledVlog(v)); }
function paintVlogs(){
  const g=$("vlGrid");
  vlData.forEach(v=>{ if(!vlDeletable(v)) vlPicked.delete(v.id); });
  for(const id of [...vlPicked]) if(!vlData.some(v=>v.id===id)) vlPicked.delete(id);
  $("vlBar").hidden=!vlData.length;
  if(!vlData.length){
    g.innerHTML='<div class="card vl-empty"><span class="ms" aria-hidden="true">video_library</span><b>No vlogs yet</b>'+
      '<span>Upload a vlog to YouTube with a ready title, description, chapters and thumbnail, then turn it into Shorts and Reels.</span><button type="button" class="primary" id="vlFirst"><span class="ms" aria-hidden="true">add</span>Upload your first vlog</button></div>';
    $("vlFirst").onclick=()=>openVlogUpload(); vlBar(); return;
  }
  if(!vlBase().length){  // every vlog is still a draft or scheduled
    $("vlBar").hidden=true;
    g.innerHTML='<div class="card vl-empty"><span class="ms" aria-hidden="true">video_library</span><b>Nothing here yet</b>'+
      '<span>Vlogs you\'re still preparing are under Drafts, and ones set to go public later are under Scheduled.</span></div>';
    vlBar(); return;
  }
  const list=vlShown();
  g.innerHTML = list.length ? list.map(vlRow).join("") : '<div class="card vl-empty"><span class="ms" aria-hidden="true">search</span><b>No vlog matches</b><span>'+
    'Try another word from its title.</span></div>';
  g.querySelectorAll(".vrow").forEach(el=>{
    const id=el.dataset.id, v=vlData.find(x=>x.id===id);
    vlWire(el,v,loadVlogs,"vlErr");
    const pick=el.querySelector(".vr-pick input");
    pick.onchange=()=>{ pick.checked?vlPicked.add(id):vlPicked.delete(id); el.classList.toggle("on",pick.checked); vlBar(); };
  });
  vlBar();
}
// The bar above the list: Select all (the vlogs shown whose video can be deleted), how many are ticked, Delete.
function vlBar(){
  const can=(vlData?vlShown():[]).filter(vlDeletable), n=vlPicked.size, all=can.length>0 && can.every(v=>vlPicked.has(v.id));
  $("vlAll").checked=all; $("vlAll").indeterminate=n>0 && !all; $("vlAll").disabled=!can.length;
  $("vlAllT").textContent = n ? n+" selected" : "Select all";
  $("vlDelMany").hidden=!n;
  const rm=vlData?vlData.filter(v=>vlPicked.has(v.id)&&v.removable).length:0;
  $("vlDelMany").lastChild.textContent = rm===n ? (n===1?"Remove":"Remove "+n) : n===1 ? "Delete video" : "Delete "+n;
}
$("vlAll").onchange=()=>{
  const can=vlShown().filter(vlDeletable);
  if($("vlAll").checked) can.forEach(v=>vlPicked.add(v.id)); else vlPicked.clear();
  paintVlogs();
};
// Ticking vlogs (to delete several) is a mode: the tick boxes only show after Select.
function vlSelecting(on){
  $("s7").classList.toggle("selecting",on); if(!on) vlPicked.clear();
  $("vlSelect").lastChild.textContent=on?"Cancel":"Select"; $("vlSelect").setAttribute("aria-pressed",on);
  if(vlData) paintVlogs();
}
$("vlSelect").onclick=()=>vlSelecting(!$("s7").classList.contains("selecting"));
$("vlFind").oninput=()=>{ if(vlData) paintVlogs(); };
$("vlDelMany").onclick=()=>vlDelete(vlData.filter(v=>vlPicked.has(v.id)));
// Deletes only the vlogs' videos: their Shorts, thumbnails, transcripts and posts stay.
async function vlDelete(list){
  list=list.filter(vlDeletable); if(!list.length) return;
  const rm=list.filter(v=>v.removable), del=list.filter(v=>!v.removable), shorts=del.reduce((a,v)=>a+(v.shorts||0),0);
  const lines=[];
  if(del.length) lines.push((del.length===1?'The video of "'+del[0].title+'" is deleted':'The videos of '+del.length+' vlogs are deleted')+
    (shorts?'; '+(del.length===1?'its ':'their ')+shorts+' Short'+(shorts===1?'':'s')+', thumbnails and posts stay (in Shorts & Reels)':'')+
    ". New Shorts, or changing a Short's hook or moment, will need the vlog uploaded again.");
  if(rm.length) lines.push((rm.length===1?'"'+rm[0].title+'" stopped':rm.length+' vlogs stopped')+" before making any Shorts, so "+(rm.length===1?"it's":"they're")+" removed from the list.");
  if(!confirm((list.length===1?(rm.length?'Remove "'+list[0].title+'"?':'Delete the video of "'+list[0].title+'"?'):'Delete '+list.length+' vlogs?')+'\n\n'+lines.join('\n\n'))) return;
  $("vlDelMany").disabled=true;
  let r,j; try{ r=await fetch("/api/vlogs/delete-videos",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids:list.map(v=>v.id)})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  $("vlDelMany").disabled=false;
  if(!r.ok){ $("vlErr").textContent=j.error||"Couldn't delete the videos."; return; }
  $("vlErr").textContent = j.skipped.length ? j.skipped.length+" couldn't be deleted right now (being made, remade or posted). Try again when they're done." : "";
  j.deleted.forEach(id=>{ vlPicked.delete(id); if(typeof pkVideoReset==="function") pkVideoReset(id); });
  if(!vlPicked.size) vlSelecting(false);
  loadVlogs();
}
