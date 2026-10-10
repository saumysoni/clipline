// Stop a vlog while it's being made, or Try again after it stopped (web/stop_and_retry.py). Used by the Making page
// (js/progress.js) and the vlog upload page (js/vlog-upload.js).
// kept: the vlog was already prepared for YouTube, so stopping only stops its Shorts (its upload and details stay).
async function stopVlog(id, kept, errEl){
  if(!confirm(kept ? "Stop making Shorts from this vlog?\n\nIts YouTube upload and details stay."
                   : "Stop and delete this vlog?\n\nThe video you sent is deleted. This can't be undone.")) return;
  let r,j; try{ r=await fetch("/api/vlogs/"+id+"/stop",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ errEl.textContent=j.error||"Couldn't stop it."; return; }
  clearInterval(poll); vuStop(); refreshJobsNow(); openVlogs();
}
// Runs a stopped vlog again on the video Pit Crew still has (no second upload; the transcript is reused).
async function vlogAgain(id, errEl){
  let r,j; try{ r=await fetch("/api/vlogs/"+id+"/again",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ errEl.textContent=j.error||"Couldn't start it again."; return; }
  refreshJobsNow();
  j.prep ? openVlogUpload(id) : startPolling(id);
}
