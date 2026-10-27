// Shorts & Reels › ⋮ › Delete (web/clip_remove.py): take a clip down from where it went out. Ticked YouTube: Pit Crew
// deletes the Short. Ticked Instagram: apps can't delete Reels, so the dialog walks the creator through deleting it in
// Instagram, then asks Pit Crew to check it's gone. A clip on neither platform afterwards is a draft again.
let rmC=null;
// The platforms a clip is out on (posted): what Delete can take it off.
const clRemovable=c=>[c.youtube&&c.youtube.state==="posted"&&c.youtube.video_id&&"youtube",
  c.instagram&&c.instagram.state==="posted"&&"instagram"].filter(Boolean);
function clRemove(c){
  rmC=c; const on=clRemovable(c);
  $("clRmTitle").textContent="Delete this clip?"; $("clRmLede").textContent='"'+c.title+'"';
  $("clRmPick").hidden=false; $("clRmIgSteps").hidden=true; $("clRmErr").textContent="";
  $("clRmYtRow").hidden=!on.includes("youtube"); $("clRmYt").checked=on.includes("youtube");
  $("clRmIgRow").hidden=!on.includes("instagram"); $("clRmIg").checked=on.includes("instagram");
  const ch=c.youtube&&c.youtube.channel_title;
  $("clRmYtWho").textContent="Pit Crew deletes it"+(ch?" from "+ch:"")+". This can't be undone.";
  $("clRmX").textContent="Cancel"; $("clRmGo").textContent="Delete"; $("clRmGo").disabled=false;
  $("clRm").showModal();
}
async function rmPost(path){
  let r,j={}; try{ r=await fetch("/api/clips/"+rmC.job+"/"+rmC.idx+path,{method:"POST"}); j=await r.json().catch(()=>({})); }
  catch(e){ $("clRmErr").textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; return null; }
  if(!r.ok){ $("clRmErr").textContent=j.error||"Something went wrong. Please try again."; return null; }
  return j;
}
// Step 2 (Instagram ticked): the steps to delete it in Instagram, then the check.
function rmIgSteps(ytDone){
  $("clRmTitle").textContent=ytDone?"Deleted on YouTube. Now Instagram":"Delete it in Instagram";
  $("clRmPick").hidden=true; $("clRmIgSteps").hidden=false;
  $("clRmOpen").href=rmC.instagram.permalink||"https://www.instagram.com/";
  $("clRmX").textContent="Later"; $("clRmGo").textContent="I've deleted it";
}
$("clRmGo").onclick=async()=>{
  const go=$("clRmGo"); $("clRmErr").textContent="";
  if(!$("clRmIgSteps").hidden){  // checking Instagram
    go.disabled=true; const j=await rmPost("/instagram-gone"); go.disabled=false;
    if(!j) return;
    if(!j.gone){ $("clRmErr").textContent="It's still on Instagram. Delete it there (⋯ › Delete), then press I've deleted it again."; return; }
    $("clRm").close(); clToast("Removed from Instagram",""); loadClips(); return;
  }
  const yt=$("clRmYt").checked&&!$("clRmYtRow").hidden, ig=$("clRmIg").checked&&!$("clRmIgRow").hidden;
  if(!yt&&!ig){ $("clRmErr").textContent="Tick where to delete it."; return; }
  if(yt){
    go.disabled=true; go.textContent="Deleting..."; const j=await rmPost("/delete-youtube"); go.disabled=false; go.textContent="Delete";
    if(!j) return;
    loadClips();
    if(!ig){ $("clRm").close(); clToast("Deleted on YouTube",""); return; }
  }
  rmIgSteps(yt);
};
$("clRmX").onclick=()=>$("clRm").close();
document.body.appendChild($("clRm"));
