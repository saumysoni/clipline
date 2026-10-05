// Vlogs page (home): every vlog uploaded, newest first, as a list like YouTube's search results (web/vlogs.py):
// a landscape picture on the left, title and details on the right. Tick vlogs (or Select all) to delete several
// videos at once; their Shorts stay.
let vlData=null, vlPicked=new Set();
async function openVlogs(){ clearInterval(poll); location.hash="vlogs"; show(7); await loadVlogs(); }
async function loadVlogs(){
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; vlData=(await r.json()).items||[]; }
  catch(e){ if(!vlData) $("vlErr").textContent="Couldn't load your vlogs. Is Pit Crew still running?"; return; }
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
const vlDeletable=v=>(!v.video_deleted || v.removable) && v.status!=="working" && !v.remaking;
function vlStats(v){
  if(v.status==="working") return "";
  if(!v.shorts) return v.status==="error" ? "" : "No Shorts yet";
  return v.shorts+" Short"+(v.shorts>1?"s":"");
}
function vlBadges(v){
  const b=[];
  if(v.posted) b.push('<span class="vl-b done">'+v.posted+' posted</span>');
  if(v.scheduled) b.push('<span class="vl-b plan">'+v.scheduled+' scheduled</span>');
  if(v.drafts) b.push('<span class="vl-b">'+v.drafts+' draft'+(v.drafts>1?'s':'')+'</span>');
  return b.length?'<div class="vl-badges">'+b.join("")+'</div>':"";
}
function vlRow(v){
  // Picture: the vlog's own YouTube thumbnail, else a frame from the vlog, else a Short's thumbnail on a blur.
  const pic = v.yt_thumb ? '<img src="'+esc(v.yt_thumb)+'" alt="" loading="lazy" referrerpolicy="no-referrer">'
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
      (v.status==="working"?'<div class="vr-note">Making your Shorts · '+esc(v.msg||"")+'</div>':'')+
      (v.status==="error"?'<div class="vr-note bad vr-err"><span class="ms" aria-hidden="true">error</span><span>'+esc(v.error||"Something went wrong. Upload the vlog again.")+'</span></div>':'')+
      (v.video_expires && v.video_expires*1000-Date.now()<86400000 ? '<div class="vr-note warn" title="To keep storage free, a vlog\'s video is deleted after it hasn\'t been edited for a while. Its Shorts stay. Edit one of its Shorts to keep it longer."><span class="ms" aria-hidden="true">schedule</span>Video deleted '+esc(vlSoon(v.video_expires))+'</div>':'')+
      '<div class="vr-acts">'+
        (v.removable?'':'<button type="button" class="ghost sm vl-open">'+(busy?"See progress":"Shorts &amp; Reels")+'</button>'+
        (v.status==="ready"?'<button type="button" class="ghost sm vl-an"'+(v.posted?'':' disabled title="Post a Short to see its numbers"')+'>Analytics</button>':''))+
        (v.youtube_url?'<a class="ghost sm" href="'+esc(v.youtube_url)+'" target="_blank" rel="noopener">On YouTube<span class="ms" aria-hidden="true">open_in_new</span></a>':'')+
        (vlDeletable(v)?(v.removable?'<button type="button" class="ghost sm vl-del" title="It stopped before making any Shorts, so there\'s nothing to keep"><span class="ms" aria-hidden="true">delete</span>Remove</button>'
          :'<button type="button" class="ghost sm vl-del" title="Delete this vlog\'s video (its Shorts stay)"><span class="ms" aria-hidden="true">delete</span>Delete video</button>'):'')+
      '</div>'+
    '</div></article>';
}
function vlShown(){
  const q=$("vlFind").value.trim().toLowerCase();
  return vlData.filter(v=>!v.video_deleted).filter(v=>!q || v.title.toLowerCase().includes(q));
}
function paintVlogs(){
  const g=$("vlGrid");
  vlData.forEach(v=>{ if(!vlDeletable(v)) vlPicked.delete(v.id); });
  for(const id of [...vlPicked]) if(!vlData.some(v=>v.id===id)) vlPicked.delete(id);
  $("vlBar").hidden=!vlData.length;
  if(!vlData.length){
    g.innerHTML='<div class="card vl-empty"><span class="ms" aria-hidden="true">video_library</span><b>No vlogs yet</b>'+
      '<span>Upload a vlog and Pit Crew turns it into Shorts and Reels.</span><button type="button" class="primary" id="vlFirst"><span class="ms" aria-hidden="true">add</span>Upload your first vlog</button></div>';
    $("vlFirst").onclick=openCreate; vlBar(); return;
  }
  const list=vlShown();
  g.innerHTML = list.length ? list.map(vlRow).join("") : '<div class="card vl-empty"><span class="ms" aria-hidden="true">search</span><b>No vlog matches</b><span>Try another word from its title.</span></div>';
  g.querySelectorAll(".vrow").forEach(el=>{
    const id=el.dataset.id, v=vlData.find(x=>x.id===id);  // ready: its Shorts & Reels; still being made (or stopped): its progress
    el.querySelectorAll(".vl-open").forEach(b=>b.onclick=()=>v.status==="ready"?openClips(id):startPolling(id));
    const an=el.querySelector(".vl-an"); if(an) an.onclick=()=>openAnalytics(id);
    const del=el.querySelector(".vl-del"); if(del) del.onclick=()=>vlDelete([v]);
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
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("vlDelMany").disabled=false;
  if(!r.ok){ $("vlErr").textContent=j.error||"Couldn't delete the videos."; return; }
  $("vlErr").textContent = j.skipped.length ? j.skipped.length+" couldn't be deleted right now (being made, remade or posted). Try again when they're done." : "";
  j.deleted.forEach(id=>{ vlPicked.delete(id); if(typeof pkVideoReset==="function") pkVideoReset(id); });
  loadVlogs();
}
