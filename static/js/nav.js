// Going back to making Shorts from Analytics or On YouTube: the "Make Shorts" link and the step list return
// to the vlog that was open (its review or progress), or to Set up when none was.
function openMaking(){
  if(jobId) startPolling(jobId);
  else { location.hash=""; show(1); }
}
$("makeNav").onclick=openMaking;
$("steps").addEventListener("click",()=>{ if($("steps").classList.contains("away")) openMaking(); });
