// Stop a vlog while it's being made, or Try again after it stopped (web/stop_and_retry.py); Pause and Resume while its
// Shorts are being made (web/pause.py). Used by the Making page (js/progress.js), Drafts' cards for Shorts being made
// (js/clips.js) and the vlog upload page (js/vlog-upload.js).
// kept: the vlog was already prepared for YouTube, so stopping only stops its Shorts (its upload and details stay).
// after(): what to show once it's stopped (default: Drafts, where the vlog or its Shorts were).
async function stopVlog(id, kept, errEl, after){
  if(!confirm(kept ? "Stop making Shorts from this vlog?\n\nIts YouTube upload and details stay."
                   : "Stop and delete this vlog?\n\nThe video you sent is deleted. This can't be undone.")) return;
  let r,j; try{ r=await fetch("/api/vlogs/"+id+"/stop",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ errEl.textContent=j.error||"Couldn't stop it."; return; }
  refreshJobsNow();
  if(after){ after(); return; }
  clearInterval(poll); vuStop(); openDrafts(kept?"vlogs":"shorts");
}
// Pause (after the step it's on; a vlog still waiting pauses at once) or Resume. after(): redraw what showed it.
async function pauseVlog(id, errEl, after){ await vlPauseCall(id, "pause", errEl, after); }
async function resumeVlog(id, errEl, after){ await vlPauseCall(id, "resume", errEl, after); }
async function vlPauseCall(id, what, errEl, after){
  let r,j; try{ r=await fetch("/api/vlogs/"+id+"/"+what,{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ errEl.textContent=j.error||(what==="pause"?"Couldn't pause it.":"Couldn't resume it."); return; }
  errEl.textContent=""; refreshJobsNow(); if(after) after();
}
// Runs a stopped vlog again on the video Pit Crew still has (no second upload; the transcript is reused).
async function vlogAgain(id, errEl){
  let r,j; try{ r=await fetch("/api/vlogs/"+id+"/again",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ errEl.textContent=j.error||"Couldn't start it again."; return; }
  refreshJobsNow();
  j.prep ? openVlogUpload(id) : startPolling(id);
}
