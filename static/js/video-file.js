// Choosing the vlog file (click or drag and drop).
// The video's length, so must-have moments past the end are caught before uploading (if the browser can read it).
function readDuration(f){
  videoDuration=null;
  try{
    const v=document.createElement("video"); v.preload="metadata";
    v.onloadedmetadata=()=>{ if(isFinite(v.duration)) videoDuration=v.duration; URL.revokeObjectURL(v.src); if(mustRows().length) checkMust(); };
    v.src=URL.createObjectURL(f);
  }catch(e){}
}
function setFile(f){ if(!f) return; readDuration(f); const dt=new DataTransfer(); dt.items.add(f); $("file").files=dt.files;
  $("drop").classList.add("has"); $("dropIcon").textContent="check";
  $("dropText").textContent = f.name;
  $("dropSub").textContent = (f.size/1e9).toFixed(2)+" GB · click to choose a different file";
  paintPlan(); }
$("file").onchange=e=>{ setFile(e.target.files[0]); checkVideoLink(); };
["dragover","dragenter"].forEach(ev=>$("drop").addEventListener(ev,e=>{e.preventDefault();$("drop").style.borderColor="var(--primary)";}));
$("drop").addEventListener("dragleave",()=>{ $("drop").style.borderColor=""; });
$("drop").addEventListener("drop",e=>{e.preventDefault();$("drop").style.borderColor="";setFile(e.dataTransfer.files[0]);checkVideoLink();});
