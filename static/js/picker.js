// Choose on the video: the scene picker dialog.
// ---- choose a scene on the video (plays preview.mp4, a small copy every browser can play)
let pkBox=null, pkIdx=null, pkStart=null, pkEnd=null, pkStopAt=null, pkLoad=0;
const fmtExact=t=>{ const m=Math.floor(t/60), r=(t-m*60).toFixed(1); return m+":"+r.padStart(4,"0"); };
function openPicker(box,idx){
  pkBox=box; pkIdx=idx;
  pkStart=parseTime(box.querySelector(".t0").value); pkEnd=parseTime(box.querySelector(".t1").value);
  $("pkErr").textContent="";
  $("pkTitle").textContent = idx ? "Choose a new moment for Short "+idx : "Choose a moment for a new Short";
  $("picker").showModal(); paintPick(); loadPreview(false);
}
async function loadPreview(retry){
  const v=$("pkVideo"), mine=++pkLoad;
  if(v.dataset.job===jobId && v.getAttribute("src")){ if(pkStart!=null) v.currentTime=pkStart; return; }
  v.removeAttribute("src"); v.load();
  $("pkWait").hidden=false; $("pkWait").innerHTML='<span class="spin" aria-hidden="true"></span> Getting your vlog ready to play. For a long vlog this takes a minute or two.';
  while($("picker").open && mine===pkLoad){
    let j;
    try{ const r=await fetch("/api/preview/"+jobId,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({retry})}); j=await r.json(); }
    catch(e){ j={status:"error",error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
    retry=false;
    if(mine!==pkLoad) return;
    if(j.status==="ready"){
      v.dataset.job=jobId; v.src=j.url; $("pkWait").hidden=true;
      v.addEventListener("loadedmetadata",()=>{ if(pkStart!=null) v.currentTime=pkStart; paintPick(); },{once:true});
      return;
    }
    if(j.status==="error"){
      $("pkWait").innerHTML=esc(j.error)+' <button type="button" class="linkbtn" id="pkRetry">Try again</button>';
      $("pkRetry").onclick=()=>loadPreview(true); return;
    }
    await new Promise(r=>setTimeout(r,1500));
  }
}
function pkDuration(){ const d=$("pkVideo").duration; return isFinite(d)&&d>0 ? d : (job.duration||0); }
function paintPick(){
  const d=pkDuration(), pct=t=>(Math.max(0,Math.min(t,d))/d*100)+"%";
  $("pkTotal").textContent = d ? fmt(d) : "";
  let html="";
  if(d){
    job.shorts.filter(s=>!s.pending && s.idx!==pkIdx).forEach(s=>{
      html+='<div class="used" style="left:'+pct(s.start)+';width:'+((s.end-s.start)/d*100)+'%" title="Short '+s.idx+'">'+s.idx+'</div>';
    });
    if(pkStart!=null) html+='<div class="sel" style="left:'+pct(pkStart)+';width:'+(pkEnd!=null?((pkEnd-pkStart)/d*100):0.6)+'%"></div>';
    html+='<div class="head" style="left:'+pct($("pkVideo").currentTime||0)+'"></div>';
  }
  $("pkTrack").innerHTML=html;
  $("pkSel").textContent = (pkStart!=null ? fmtExact(pkStart) : "start?")+" to "+(pkEnd!=null ? fmtExact(pkEnd) : "end?")+
    (pkStart!=null&&pkEnd!=null ? " ("+Math.round(pkEnd-pkStart)+"s)" : "");
}
$("pkVideo").addEventListener("timeupdate",()=>{
  const v=$("pkVideo");
  if(pkStopAt!=null && v.currentTime>=pkStopAt){ v.pause(); pkStopAt=null; }
  paintPick();
});
$("pkVideo").addEventListener("seeking",paintPick);
$("pkTrack").onclick=e=>{
  const d=pkDuration(), r=$("pkTrack").getBoundingClientRect(); if(!d) return;
  $("pkVideo").currentTime=Math.max(0,Math.min(d,(e.clientX-r.left)/r.width*d)); pkStopAt=null;
};
$("pkBack").onclick=()=>{ $("pkVideo").currentTime=Math.max(0,$("pkVideo").currentTime-1); };
$("pkFwd").onclick=()=>{ $("pkVideo").currentTime=Math.min(pkDuration(),$("pkVideo").currentTime+1); };
$("pkSetStart").onclick=()=>{
  pkStart=$("pkVideo").currentTime; if(pkEnd!=null && pkEnd<=pkStart) pkEnd=null;
  $("pkErr").textContent=""; paintPick();
};
$("pkSetEnd").onclick=()=>{
  const t=$("pkVideo").currentTime;
  if(pkStart!=null && t<=pkStart){ $("pkErr").textContent="The end has to be after the start. Move further into the video first."; return; }
  pkEnd=t; $("pkErr").textContent=""; paintPick();
};
$("pkPlaySel").onclick=()=>{
  if(pkStart==null){ $("pkErr").textContent="Set the start first."; return; }
  const v=$("pkVideo"); v.currentTime=pkStart; pkStopAt=pkEnd; v.play();
};
$("pkUse").onclick=()=>{
  if(pkStart==null||pkEnd==null){ $("pkErr").textContent="Set both the start and the end of the moment."; return; }
  const a=fmtExact(pkStart), b=fmtExact(pkEnd), bad=momentProblem(a,b,"moment");
  if(bad){ $("pkErr").textContent=bad; return; }
  pkBox.querySelector(".t0").value=a; pkBox.querySelector(".t1").value=b;
  pkBox.querySelectorAll(".times-row input").forEach(i=>i.classList.remove("bad"));
  $("picker").close(); pkBox.querySelector(".go").focus();
};
$("pkCancel").onclick=()=>$("picker").close();
$("picker").addEventListener("close",()=>{ $("pkVideo").pause(); pkStopAt=null; pkLoad++; });
