// Vlogs page (home): every vlog uploaded, newest first, as small square cards (web/vlogs.py).
let vlData=null;
async function openVlogs(){ clearInterval(poll); location.hash="vlogs"; show(7); await loadVlogs(); }
async function loadVlogs(){
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; vlData=(await r.json()).items||[]; }
  catch(e){ if(!vlData) $("vlErr").textContent="Couldn't load your vlogs. Is Pit Crew still running?"; return; }
  $("vlErr").textContent=""; paintVlogs();
}
const vlDate=t=>t ? new Date(t*1000).toLocaleString([], {month:"short", day:"numeric", year:new Date(t*1000).getFullYear()===new Date().getFullYear()?undefined:"numeric", hour:"numeric", minute:"2-digit"}) : "";
// Overall progress of a vlog being made: finished stages plus the current stage's share.
const vlPct=v=>v.stages ? Math.min(99, Math.round(((v.stage||0)+(v.pct||0)/100)/v.stages*100)) : 0;
function vlStats(v){
  if(v.status==="working") return "Making your Shorts";
  if(v.status==="error") return "";
  if(!v.shorts) return "No Shorts yet";
  const parts=[v.posted&&v.posted+" posted", v.scheduled&&v.scheduled+" scheduled", v.drafts&&v.drafts+" draft"+(v.drafts>1?"s":"")].filter(Boolean);
  return v.shorts+" Short"+(v.shorts>1?"s":"")+(parts.length?" · "+parts.join(" · "):"");
}
function vlCard(v){
  const cover = v.cover ? '<img src="/media/'+esc(v.id)+'/'+esc(v.cover)+'" alt="" loading="lazy">' : '<span class="ms vl-ph" aria-hidden="true">movie</span>';
  const over = v.status==="working"
    ? '<div class="vl-over"><span class="spin" aria-hidden="true"></span><b>'+vlPct(v)+'%</b><small>'+esc(v.msg||"Working")+'</small></div>'
    : v.status==="error" ? '<div class="vl-over bad"><span class="ms" aria-hidden="true">error</span><small>Stopped</small></div>' : "";
  const dur = v.duration ? '<span class="vl-dur">'+fmt(v.duration)+'</span>' : "";
  const busy = v.status==="working";
  return '<article class="vlog" data-id="'+esc(v.id)+'">'+
    '<div class="vl-top"><button type="button" class="vl-cover vl-open" aria-label="Open '+esc(v.title)+'">'+cover+over+dur+'</button>'+
      (busy||v.video_deleted?'':'<button type="button" class="vl-del" title="Delete this vlog\'s video (its Shorts stay)" aria-label="Delete the video of '+esc(v.title)+'"><span class="ms" aria-hidden="true">delete</span></button>')+'</div>'+
    '<div class="vl-body"><b class="vl-title" title="'+esc(v.title)+'">'+esc(v.title)+'</b>'+
      '<small class="vl-when">'+esc(vlDate(v.created))+'</small>'+
      (vlStats(v)?'<small class="vl-stats">'+esc(vlStats(v))+'</small>':'')+
      (v.video_deleted?'<small class="vl-gone" title="Its Shorts, thumbnails and posts are still here. Upload the vlog again to make new Shorts from it."><span class="ms" aria-hidden="true">delete</span>Video deleted</small>':'')+
      (v.status==="error"?'<small class="vl-err">'+esc(v.error||"Something went wrong.")+'</small>':'')+
      (v.youtube_url?'<a class="vl-yt" href="'+esc(v.youtube_url)+'" target="_blank" rel="noopener"><span class="ms" aria-hidden="true">smart_display</span>On YouTube</a>':'')+
    '</div>'+
    '<div class="vl-acts">'+
      '<button type="button" class="linkbtn vl-open">'+(busy?"See progress":"Shorts &amp; Reels")+'</button>'+
      '<button type="button" class="linkbtn vl-an"'+(v.posted?'':' disabled title="Post a Short to see its numbers"')+'>Analytics</button>'+
    '</div></article>';
}
function paintVlogs(){
  const g=$("vlGrid"), live=vlData.filter(v=>!v.video_deleted), gone=vlData.filter(v=>v.video_deleted);
  if(!live.length && !gone.length){
    g.innerHTML='<div class="card vl-empty"><span class="ms" aria-hidden="true">video_library</span><b>No vlogs yet</b>'+
      '<span>Upload a vlog and Pit Crew turns it into Shorts and Reels.</span><button type="button" class="primary" id="vlFirst"><span class="ms" aria-hidden="true">add</span>Upload your first vlog</button></div>';
    $("vlFirst").onclick=openCreate; return;
  }
  // Deleted vlogs leave the grid; their Shorts stay reachable under "Deleted vlogs" (open while it was open).
  const wasOpen=!!(g.querySelector(".vl-gone-list")||{}).open;
  g.innerHTML=live.map(vlCard).join("")+(gone.length?'<details class="vl-gone-list"'+(wasOpen?' open':'')+'><summary>'+
    '<span class="ms" aria-hidden="true">delete</span>Deleted vlogs ('+gone.length+')<small>Their Shorts and posts are still here</small></summary>'+
    '<div class="vlog-grid">'+gone.map(vlCard).join("")+'</div></details>':'');
  g.querySelectorAll(".vlog").forEach(el=>{
    const id=el.dataset.id;
    el.querySelectorAll(".vl-open").forEach(b=>b.onclick=()=>startPolling(id));
    el.querySelector(".vl-an").onclick=()=>openAnalytics();
    const del=el.querySelector(".vl-del"); if(del) del.onclick=()=>deleteVlogVideo(vlData.find(v=>v.id===id));
  });
}
// Deletes only the vlog's video: its Shorts, thumbnails, transcript and posts stay.
async function deleteVlogVideo(v){
  const n=v.shorts;
  if(!confirm('Delete "'+v.title+'"?\n\n'+(n?'Its '+n+' Short'+(n===1?'':'s')+', thumbnails and posts stay (under "Deleted vlogs" at the bottom of this page). ':'')+
    "You won't be able to make new Shorts from it, or change a Short's hook or moment, unless you upload the vlog again.")) return;
  let r,j; try{ r=await fetch("/api/vlogs/"+v.id+"/delete-video",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  if(!r.ok){ $("vlErr").textContent=j.error||"Couldn't delete the video."; return; }
  $("vlErr").textContent=""; if(typeof pkVideoReset==="function") pkVideoReset(v.id); loadVlogs();
}
