// Checking pasted links (Drive vs YouTube) and filling in the vlog's title/description.
// ---- link checks (the same rules as link_kind() in youtube_upload.py, which checks again on the server)
function linkKind(url){
  url=(url||"").trim(); if(!url) return "";
  let u; try{ u=new URL(url.includes("://")?url:"https://"+url); }catch(e){ return "other"; }
  const host=u.hostname.toLowerCase();
  if(host==="youtu.be"||host.endsWith("youtube.com")||host.endsWith("youtube-nocookie.com"))
    return /^[A-Za-z0-9_-]{11}$/.test(url) || /(?:v=|youtu\.be\/|\/shorts\/|\/live\/|\/embed\/|\/v\/)[A-Za-z0-9_-]{11}/.test(url) ? "youtube" : "youtube_page";
  if(host==="drive.google.com"||host==="docs.google.com"){
    if(u.pathname.includes("/folders/")) return "drive_folder";
    if(u.pathname.includes("/file/d/")||u.searchParams.has("id")) return "drive_file";
    return "drive_page";
  }
  return "other";
}
const VIDEO_LINK_PROBLEMS={
  youtube:"That's a YouTube link. Pit Crew can't download videos from YouTube (YouTube's rules don't allow it). Upload the original video file or use a Google Drive link instead.",
  youtube_page:"That's a YouTube link. Pit Crew can't download videos from YouTube, so upload the original video file or use a Google Drive link instead.",
  drive_folder:"That's a link to a Drive folder. Open the folder, right-click the video, choose Share, then Copy link, and paste that link instead.",
  drive_page:"That's a link to a Drive page, not to one video. In Drive, right-click the video, choose Share, then Copy link, and paste that link instead.",
  other:"That doesn't look like a Google Drive link. Paste a link that starts with https://drive.google.com, or upload the video file instead."};
const YT_LINK_PROBLEMS={
  drive_file:"That's a Google Drive link. This box is for the vlog's YouTube link.",
  drive_folder:"That's a Google Drive link. This box is for the vlog's YouTube link.",
  drive_page:"That's a Google Drive link. This box is for the vlog's YouTube link.",
  youtube_page:"That's a YouTube link, but not to one video (maybe a channel or playlist). Open the vlog on YouTube and copy its link from the Share button.",
  other:"That doesn't look like a YouTube video link. Open the vlog on YouTube and copy its link from the Share button."};
// Shows the problem under a box (with a "move it" button when the link just went in the wrong box).
function flag(input,hint,msg,move){
  input.classList.toggle("bad",!!msg);
  hint.classList.toggle("bad",!!msg);
  hint.textContent=msg||"";
  if(msg&&move){
    const b=document.createElement("button"); b.type="button"; b.className="linkbtn"; b.textContent=move.label;
    b.onclick=move.run; hint.append(" ",b);
  }
  return !msg;
}
function checkVideoLink(){
  if($("file").files[0]) return flag($("link"),$("linkHint"),"");
  const v=$("link").value.trim(), kind=linkKind(v);
  return flag($("link"),$("linkHint"),VIDEO_LINK_PROBLEMS[kind],
    kind==="youtube"&&!$("ytUrl").value.trim() ? {label:"Use it for the title and description instead",
      run:()=>{ $("ytUrl").value=v; $("link").value=""; checkVideoLink(); fillVlogInfo(); }} : null);
}
function checkYtLink(){
  const v=$("ytUrl").value.trim(), kind=linkKind(v);
  return flag($("ytUrl"),$("ytHint"),YT_LINK_PROBLEMS[kind],
    kind==="drive_file"&&!$("link").value.trim() ? {label:"Use it as the vlog's video instead",
      run:()=>{ $("link").value=v; $("ytUrl").value=""; checkYtLink(); checkVideoLink(); }} : null);
}
$("link").addEventListener("input",()=>{ checkVideoLink(); paintPlan(); });
document.querySelectorAll("input[name=style]").forEach(r=>r.addEventListener("change",paintPlan));
$("sched").addEventListener("change",paintPlan);
$("ytUrl").addEventListener("input",()=>{ if(!$("ytUrl").value.trim()||$("ytUrl").classList.contains("bad")) checkYtLink(); });

async function fillVlogInfo(){
  const url=$("ytUrl").value.trim(); if(!url) return;
  if(!checkYtLink()) return;
  $("ytHint").textContent="Reading the video's details from YouTube...";
  try{
    const r=await fetch("/api/vlog-info?url="+encodeURIComponent(url)); const j=await r.json();
    if(!r.ok){ $("ytHint").textContent=j.error||"Couldn't read that link."; return; }
    if(j.title) $("vTitle").value=j.title;
    if(j.description) $("vDesc").value=j.description;
    $("vTitle").dataset.tags=JSON.stringify(j.tags||[]);
    $("ytHint").textContent = j.complete ? "Filled in from YouTube. Edit anything you like."
      : "Got the title. Click Connect YouTube, then paste the link again to fetch the description too (or paste it below).";
  }catch(e){ $("ytHint").textContent="Couldn't reach Pit Crew to read that link."; }
}
$("ytFill").onclick=fillVlogInfo;
$("ytUrl").addEventListener("paste",()=>setTimeout(fillVlogInfo,50));
$("ytUrl").addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); fillVlogInfo(); } });
