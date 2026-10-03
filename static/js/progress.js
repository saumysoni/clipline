// Step 2: polling the job and drawing the progress.
// ---- progress
function startPolling(id){
  jobId=id; location.hash=id; show(2); clearInterval(poll);
  poll=setInterval(tick,1000); tick();
}
async function tick(){
  let r; try{ r=await fetch("/api/status/"+jobId); }catch(e){ return; }
  if(r.status===404){ clearInterval(poll); location.hash=""; show(1); return; }
  job=await r.json();
  if(job.upload_status && job.upload_status!=="error" && !(job.upload_status==="done" && onReview)){ renderUpload(); return; }
  if(job.status==="ready"){
    if($("s3").hidden || !$("reel").children.length){ renderResults(); show(3); showPost(job.upload_status==="error"); } else refreshResults();
    if((job.uploads||[]).length) markPosted();
    if(focusIdx!=null){ const el=document.querySelector('.short[data-idx="'+focusIdx+'"]'); focusIdx=null; if(el) el.scrollIntoView({block:"center"}); }
    if(job.upload_status==="error"){ markPosted(); if(!$("err3").textContent) $("err3").textContent="Posting stopped: "+job.upload_msg; }
    if(!job.shorts.some(s=>s.retrying)) clearInterval(poll);
    return;
  }
  renderProgress();
}
function renderProgress(){
  $("tasks").innerHTML = job.stages.map((s,i)=>{
    const cls = i<job.stage ? "done" : i===job.stage ? "active" : "";
    const sub = i===job.stage && job.msg && job.msg!==s ? '<span class="sub">'+esc(job.msg)+'</span>' : "";
    return '<li class="'+cls+'"><span class="tick">'+(i<job.stage?'<span class="ms" aria-hidden="true">check</span>':i===job.stage?"":(i+1))+'</span>'+esc(s)+sub+'</li>';
  }).join("");
  if(job.duration){
    $("timeline").hidden=false; $("totalTime").textContent=fmt(job.duration);
    $("track").innerHTML=(job.moments_found||[]).map((m,i)=>'<div class="seg" style="left:'+(m.start/job.duration*100)+'%;width:'+Math.max(1.2,(m.end-m.start)/job.duration*100)+'%"><i>'+(i+1)+'</i></div>').join("");
  }
  $("err2").textContent = job.status==="error" ? "Stopped: "+job.error : "";
  if(job.status==="error"){ clearInterval(poll); $("err2").insertAdjacentHTML("beforeend",' <button class="ghost" style="margin-left:8px" onclick="location.hash=\'\';location.reload()">Start over</button>'); }
}
