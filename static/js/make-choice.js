// + Create asks what to make (crDialog); "Make Shorts" asks from which video (mkDialog): a vlog uploaded here
// whose video Pit Crew still keeps (72 hours after the last change, web/retention.py), or a new video file
// (the usual setup page, screen 1). Making Shorts from a kept vlog reuses its transcript (web/vlog_upload.py).
let mkVlog=null, mkItems=[];
function openCreateChoice(){ $("crDialog").showModal(); }
$("crX").onclick=()=>$("crDialog").close();
$("crVlog").onclick=()=>{ $("crDialog").close(); openVlogUpload(); };
$("crShorts").onclick=()=>{ $("crDialog").close(); openMake(); };
// Clicking the dimmed page around a dialog closes it.
["crDialog","mkDialog"].forEach(d=>$(d).addEventListener("click",e=>{ if(e.target===$(d)) $(d).close(); }));
// A vlog can be used while its video is kept, nothing is running on it and it has no Shorts yet.
const mkUsable=v=>v.prep && v.status==="ready" && !v.video_deleted && !v.shorts;
function mkLeft(t){
  const h=(t*1000-Date.now())/3600000;
  if(h<1) return "less than an hour left";
  if(h<48) return Math.floor(h)+" hour"+(Math.floor(h)===1?"":"s")+" left";
  return Math.floor(h/24)+" days left";
}
async function openMake(id){
  mkVlog=null; $("mkErr").textContent=""; $("mkNote").value="";
  if(!$("mkDialog").open) $("mkDialog").showModal();
  mkStep("pick"); $("mkList").innerHTML='<p class="hint">Loading your vlogs…</p>';
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; mkItems=((await r.json()).items||[]).filter(mkUsable); }
  catch(e){ mkItems=[]; $("mkList").innerHTML='<p class="err">Couldn\'t load your vlogs. Is Pit Crew still running?</p>'; return; }
  if(id){ const v=mkItems.find(x=>x.id===id); if(v){ mkPick(v); return; } }
  mkPaintList();
}
function mkStep(s){ $("mkPick").hidden=s!=="pick"; $("mkOpts").hidden=s!=="opts"; }
function mkPaintList(){
  if(!mkItems.length){
    $("mkList").innerHTML='<div class="mk-empty"><span class="ms" aria-hidden="true">video_library</span><span>No vlog to use right now. A vlog you upload here can be used for '+VU_KEEP_H+' hours; after that, upload the video again below.</span></div>';
    return;
  }
  $("mkList").innerHTML='<p class="mk-l">Uploaded here</p>'+mkItems.map(v=>{
    const p=v.vpost||{}, up=p.state==="uploading";
    const pic=v.vthumb?'<img src="/media/'+esc(v.id)+'/'+esc(v.vthumb)+'" alt="" loading="lazy">':v.yt_thumb?'<img src="'+esc(v.yt_thumb)+'" alt="" loading="lazy" referrerpolicy="no-referrer">':'<span class="ms" aria-hidden="true">movie</span>';
    const state=up?"Uploading to YouTube "+Math.round(p.pct||0)+"%":p.state==="done"?"On YouTube":"Not on YouTube yet";
    return '<button type="button" class="mk-vlog" data-id="'+esc(v.id)+'"'+(up?' disabled title="Wait until it has finished uploading"':'')+'><span class="mk-pic">'+pic+'</span>'+
      '<span class="mk-t"><b>'+esc(v.title)+'</b><small>'+esc([v.duration?fmt(v.duration):"",state].filter(Boolean).join(" · "))+'</small></span>'+
      (v.video_expires?'<span class="mk-left"><span class="ms" aria-hidden="true">schedule</span>'+mkLeft(v.video_expires)+'</span>':'')+'</button>';
  }).join("");
  $("mkList").querySelectorAll(".mk-vlog").forEach(b=>b.onclick=()=>mkPick(mkItems.find(v=>v.id===b.dataset.id)));
}
function mkPick(v){
  mkVlog=v; mkStep("opts");
  $("mkChosen").innerHTML='<span class="ms" aria-hidden="true">movie</span><span><b>'+esc(v.title)+'</b><small>'+
    (v.vpost&&v.vpost.state==="done"?"Each Short links back to this vlog on YouTube.":"Not on YouTube yet, so the Shorts won't link to it.")+'</small></span>';
  $("mkGo").focus();
}
$("mkBack").onclick=()=>{ mkStep("pick"); mkPaintList(); };
$("mkX").onclick=()=>$("mkDialog").close();
$("mkNewFile").onclick=()=>{ $("mkDialog").close(); openCreate(); };
$("mkGo").onclick=async()=>{
  if(!mkVlog) return;
  $("mkErr").textContent=""; $("mkGo").disabled=true;
  const id=mkVlog.id;
  let r,j; try{ r=await fetch("/api/vlog/"+id+"/shorts",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({count:+$("mkCount").value,style:$("mkStyle").value,note:$("mkNote").value.trim()})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("mkGo").disabled=false;
  if(!r.ok){ $("mkErr").textContent=j.error||"Couldn't start making the Shorts."; return; }
  $("mkDialog").close(); vuStop(); startPolling(id);
};
