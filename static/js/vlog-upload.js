// New vlog (screen 10): upload a whole vlog to YouTube with AI help (web/vlog_upload.py).
// Pick the video, Pit Crew prepares a title, description with chapters, tags and a thumbnail, the creator checks
// them and uploads. Afterwards it offers to make the vlog's Shorts & Reels (js/make-choice.js).
let vuId=null, vuJob=null, vuPoll=null, vuSaveT=null, vuFilled=null, vuAsked=new Set();
const VU_KEEP_H=72;  // web/retention.py KEEP_ORIGINAL_HOURS: the video is kept this long after the last change
function openVlogUpload(id){
  clearInterval(poll); vuStop(); jobId=null;
  vuId=id||null; vuJob=null; vuFilled=null; $("vuH").textContent="Upload a vlog to YouTube";
  location.hash = "vlog/"+(id||"new"); show(10);
  ["vuErr1","vuErr2","vuErr3"].forEach(e=>$(e).textContent="");
  if(!id){ vuReset(); vuView("pick"); return; }
  seenJob(id); vuView("work"); $("vuTasks").innerHTML=""; vuTick(); vuPoll=setInterval(vuTick,1500);
}
function vuStop(){ clearInterval(vuPoll); vuPoll=null; }
// Which part of the page shows: pick (choose the video), work (being prepared), edit (check and upload), done.
function vuView(v){
  $("vuPick").hidden=v!=="pick"; $("vuWork").hidden=v!=="work"; $("vuEdit").hidden=v!=="edit";
  $("vuDone").hidden=v!=="done"; if(v!=="done") $("vuNext").hidden=true;
  $("vuLede").hidden=v==="done";
}
function vuReset(){
  $("vuFile").value=""; $("vuLink").value=""; $("vuNote").value="";
  $("vuDrop").classList.remove("has"); $("vuDropIc").textContent="cloud_upload";
  $("vuDropText").textContent="Drop your vlog here"; $("vuDropSub").textContent="or click to choose the video file";
  $("vuGo").disabled=false; $("vuSendBar").hidden=true;
}
// ---- 1. Choose the video
function vuSetFile(f){
  if(!f) return; const dt=new DataTransfer(); dt.items.add(f); $("vuFile").files=dt.files;
  $("vuDrop").classList.add("has"); $("vuDropIc").textContent="check"; $("vuDropText").textContent=f.name;
  $("vuDropSub").textContent=(f.size/1e9).toFixed(2)+" GB · click to choose a different file"; $("vuErr1").textContent="";
}
$("vuFile").onchange=e=>vuSetFile(e.target.files[0]);
["dragover","dragenter"].forEach(ev=>$("vuDrop").addEventListener(ev,e=>{ e.preventDefault(); $("vuDrop").style.borderColor="var(--primary)"; }));
$("vuDrop").addEventListener("dragleave",()=>{ $("vuDrop").style.borderColor=""; });
$("vuDrop").addEventListener("drop",e=>{ e.preventDefault(); $("vuDrop").style.borderColor=""; vuSetFile(e.dataTransfer.files[0]); });
$("vuDrop").addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); $("vuFile").click(); } });
$("vuGo").onclick=()=>{
  $("vuErr1").textContent="";
  const f=$("vuFile").files[0], link=$("vuLink").value.trim();
  if(!f && !link){ $("vuErr1").textContent="Choose your vlog file or paste a Google Drive link."; return; }
  const fd=new FormData();
  if(f) fd.append("video",f); else fd.append("link",link);
  fd.append("note",$("vuNote").value.trim());
  const xhr=new XMLHttpRequest(), label=$("vuGo").innerHTML;
  xhr.open("POST","/api/vlog/start");
  $("vuGo").disabled=true; $("vuSendBar").hidden=false; jobsUpload(0);
  xhr.upload.onprogress=e=>{ if(!e.lengthComputable) return; const p=e.loaded/e.total*100;
    $("vuSendBar").firstElementChild.style.width=p+"%"; $("vuGo").textContent="Sending video "+Math.round(p)+"%"; jobsUpload(p); };
  const done=()=>{ $("vuGo").disabled=false; $("vuGo").innerHTML=label; $("vuSendBar").hidden=true; jobsUpload(null); };
  xhr.onload=()=>{
    done(); let r={}; try{ r=JSON.parse(xhr.responseText); }catch(e){}
    if(xhr.status!==200){ $("vuErr1").textContent=r.error||"Something went wrong sending the vlog."; if(r.field==="link") $("vuLink").focus(); return; }
    openVlogUpload(r.id);
  };
  xhr.onerror=()=>{ done(); $("vuErr1").textContent="Couldn't reach Pit Crew. Is the app window still open?"; };
  xhr.send(fd);
};
// ---- 2. Being prepared, then the page to check and upload
async function vuTick(){
  const id=vuId; if(!id) return;
  let r; try{ r=await fetch("/api/status/"+id); }catch(e){ return; }
  if(id!==vuId || $("s10").hidden) return;
  if(r.status===404){ vuStop(); openVlogs(); return; }
  const j=await r.json(); vuJob=j;
  if(j.kind!=="vlog" || j.count){ vuStop(); startPolling(id); return; }  // its Shorts are being made (or done)
  if(j.status==="working"){ vuView("work"); vuTasks(j); return; }
  if(j.status==="error"){
    vuStop(); vuView("work"); vuTasks(j);
    $("vuErr2").innerHTML=esc("Stopped: "+(j.error||"Something went wrong."))+' <button type="button" class="ghost sm" id="vuAgain">Start over</button>';
    $("vuAgain").onclick=()=>openVlogUpload(); return;
  }
  const p=j.vpost||{};
  if(p.state==="done"){ vuStop(); vuPaintDone(j); return; }
  vuView("edit"); if(vuFilled!==id) vuFill(j);
  vuPaintPost(j);
  if(p.state!=="uploading") vuStop();
}
function vuTasks(j){
  const at=j.stage||0;
  $("vuTasks").innerHTML=(j.stages||[]).map((s,i)=>{
    const cls=i<at?"done":i===at&&j.status==="working"?"active":"";
    const sub=i===at && j.status==="working" && j.msg && j.msg!==s ? '<span class="sub">'+esc(j.msg)+(j.pct?" · "+Math.round(j.pct)+"%":"")+'</span>' : "";
    return '<li class="'+cls+'"><span class="tick">'+(i<at?'<span class="ms" aria-hidden="true">check</span>':i===at?"":(i+1))+'</span>'+esc(s)+sub+'</li>';
  }).join("");
}
// Fills the fields once per vlog, so a poll never overwrites what the creator is typing.
function vuFill(j){
  vuFilled=j.id; const d=j.vdraft||{};
  $("vuT").value=d.title||""; $("vuD").value=d.description||""; $("vuTags").value=(d.tags||[]).join(", ");
  $("vuSaved").textContent="";
  vuIdeas(d); vuThumb(d); vuCounts(); vuPaintAcct();
  if(!$("vuStart").value){
    const t=new Date(Date.now()+86400000); t.setHours(18,0,0,0);
    $("vuStart").value=new Date(t-t.getTimezoneOffset()*60000).toISOString().slice(0,16);
  }
  $("vuWhen").hidden=$("vuPrivacy").value!=="schedule";
  const left=Math.max(1,Math.round(((j.last_edit_at||Date.now()/1000)+VU_KEEP_H*3600-Date.now()/1000)/3600));
  $("vuKeep").innerHTML='<span class="ms" aria-hidden="true">schedule</span><span>Pit Crew keeps this video for '+(left>=VU_KEEP_H?VU_KEEP_H+" hours":"about "+left+" more hour"+(left===1?"":"s"))+
    ', so you can make its Shorts &amp; Reels without uploading it again.</span>';
}
function vuIdeas(d){
  const ideas=d.titles||[];
  $("vuIdeas").innerHTML = d.ai_failed
    ? '<span class="vu-note"><span class="ms" aria-hidden="true">info</span>Pit Crew couldn\'t write the details this time. Write your own, or start over later.</span>'
    : ideas.length>1 ? '<span class="vu-ideas-l">Ideas</span>'+ideas.map(t=>'<button type="button" class="vu-idea" aria-pressed="'+(t===$("vuT").value)+'">'+esc(t)+'</button>').join("") : "";
  $("vuIdeas").querySelectorAll(".vu-idea").forEach(b=>b.onclick=()=>{ $("vuT").value=b.textContent; vuChanged(); });
}
function vuThumb(d){
  if(!d.thumb){ $("vuThumb").removeAttribute("src"); return; }
  const src="/media/"+vuId+"/"+d.thumb;
  $("vuThumb").src=src; $("vuThumbDl").href=src; $("vuThumbDl").setAttribute("download","thumbnail.jpg");
  $("vuLook").querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.look===(d.look||"frame")));
}
const vuTagList=()=>$("vuTags").value.split(",").map(t=>t.trim()).filter(Boolean);
function vuCounts(){
  const t=$("vuT").value.length, dl=$("vuD").value.length, tg=vuTagList().join(",").length;
  $("vuTCount").textContent=t+"/100";
  $("vuDCount").textContent=dl+"/5000 characters";
  $("vuTagsCount").textContent=tg+"/500 characters"+(tg>500?": YouTube keeps the first 500":"");
  $("vuTagsCount").classList.toggle("bad",tg>500);
  $("vuIdeas").querySelectorAll(".vu-idea").forEach(b=>b.setAttribute("aria-pressed",b.textContent===$("vuT").value));
}
// Saves as the creator types (a second after they stop), so leaving the page loses nothing.
function vuChanged(){
  vuCounts(); $("vuSaved").textContent="Saving…"; clearTimeout(vuSaveT);
  vuSaveT=setTimeout(vuSave,900);
}
async function vuSave(){
  clearTimeout(vuSaveT); const id=vuId; if(!id) return;
  try{
    const r=await fetch("/api/vlog/"+id+"/draft",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title:$("vuT").value,description:$("vuD").value,tags:vuTagList()})});
    if(id===vuId) $("vuSaved").textContent=r.ok?"Saved":"Not saved";
  }catch(e){ if(id===vuId) $("vuSaved").textContent="Not saved"; }
}
["vuT","vuD","vuTags"].forEach(f=>$(f).addEventListener("input",vuChanged));
$("vuLook").querySelectorAll("button").forEach(b=>b.onclick=async()=>{
  if(b.getAttribute("aria-pressed")==="true" || !vuId) return;
  const id=vuId; $("vuLook").classList.add("busy"); $("vuErr3").textContent="";
  let r,j; try{ r=await fetch("/api/vlog/"+id+"/look",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({look:b.dataset.look})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("vuLook").classList.remove("busy"); if(id!==vuId) return;
  if(!r.ok){ $("vuErr3").textContent=j.error||"Couldn't change the thumbnail."; return; }
  vuThumb({thumb:j.thumb, look:b.dataset.look});
});
$("vuPrivacy").onchange=()=>{ $("vuWhen").hidden=$("vuPrivacy").value!=="schedule"; vuPaintPost(vuJob); };
// The channel line (the same channel the Shorts post to; Switch channel changes both).
function vuPaintAcct(){
  const a=$("vuAcct"), name=yt.channel?yt.channel.title:"your channel";
  if(!yt.configured){ a.innerHTML='<span class="ms" aria-hidden="true">info</span><span>YouTube isn\'t set up yet: the Google client file is missing from the app\'s folder (README step 5).</span>'; return; }
  if(!yt.signed_in){
    a.innerHTML='<span class="ms" aria-hidden="true">smart_display</span><span>YouTube isn\'t connected yet.</span><button type="button" class="linkbtn" id="vuIn">Connect YouTube</button>';
    $("vuIn").onclick=()=>signIn(); return;
  }
  a.innerHTML=(yt.channel&&yt.channel.thumb?'<img src="'+esc(yt.channel.thumb)+'" alt="" referrerpolicy="no-referrer">':'<span class="ms" aria-hidden="true">smart_display</span>')+
    '<span>Uploading to <b>'+esc(name)+'</b>'+(yt.offline?' (offline right now)':'')+'</span>'+
    '<button type="button" class="linkbtn" id="vuSwitch">'+((yt.channels||[]).length>1?"Change channel":"Switch channel")+'</button>';
  $("vuSwitch").onclick=()=>openSwitcher("yt",$("vuSwitch"));
}
// The upload button, bar and message for where the upload is.
function vuPaintPost(j){
  if(!j) return;
  const p=j.vpost||{}, up=p.state==="uploading";
  ["vuT","vuD","vuTags","vuPrivacy","vuStart"].forEach(f=>$(f).disabled=up);
  $("vuLook").querySelectorAll("button").forEach(b=>b.disabled=up);
  $("vuIdeas").querySelectorAll("button").forEach(b=>b.disabled=up);
  $("vuUpload").disabled=up; $("vuUpBar").hidden=!up;
  if(up){
    const pct=Math.round(p.pct||0);
    $("vuUpBar").firstElementChild.style.width=pct+"%";
    $("vuUpload").innerHTML='<span class="spin" aria-hidden="true"></span>Uploading '+pct+'%';
    $("vuUpMsg").textContent="You can leave this page; the upload carries on while Pit Crew is running.";
  } else {
    const s=$("vuPrivacy").value==="schedule";
    $("vuUpload").innerHTML='<span class="ms" aria-hidden="true">'+(s?"event":"cloud_upload")+'</span>'+(s?"Schedule on YouTube":"Upload to YouTube");
    $("vuUpMsg").textContent="";
  }
  if(p.state==="error" && !$("vuErr3").textContent) $("vuErr3").textContent="The upload stopped: "+(p.error||"Something went wrong.")+" Press Upload to try again.";
}
$("vuUpload").onclick=async()=>{
  $("vuErr3").textContent="";
  if(!$("vuT").value.trim()){ $("vuErr3").textContent="Give the vlog a title."; $("vuT").focus(); return; }
  if(!yt.signed_in){ signIn(()=>$("vuUpload").click()); $("vuErr3").textContent="Connect YouTube in the window that opened; the upload starts once you're connected."; return; }
  const privacy=$("vuPrivacy").value;
  if(privacy==="schedule" && !$("vuStart").value){ $("vuErr3").textContent="Choose when it goes public."; $("vuStart").focus(); return; }
  let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
  clearTimeout(vuSaveT); $("vuUpload").disabled=true;
  let r,j; try{ r=await fetch("/api/vlog/"+vuId+"/upload",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({title:$("vuT").value,description:$("vuD").value,tags:vuTagList(),privacy,start:$("vuStart").value,tz,channel:yt.channel&&yt.channel.id})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("vuUpload").disabled=false;
  if(!r.ok){
    $("vuErr3").textContent=j.error||"Couldn't start the upload.";
    if(j.signin) signIn(()=>$("vuUpload").click());
    if(j.field==="title") $("vuT").focus(); if(j.field==="start") $("vuStart").focus();
    return;
  }
  $("vuSaved").textContent="Saved";
  vuJob={...vuJob, vpost:{state:"uploading",pct:0}}; vuPaintPost(vuJob);
  vuStop(); vuPoll=setInterval(vuTick,1500); setTimeout(refreshJobsNow,500);
};
// ---- 3. On YouTube, then the offer to make its Shorts & Reels
function vuPaintDone(j){
  vuView("done");
  const p=j.vpost||{}, v=j.vlog||{}, when=p.when?new Date(p.when):null, later=p.privacy==="schedule" && when && when>new Date();
  const at=when?when.toLocaleString([], {weekday:"long", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}):"";
  $("vuH").textContent=(v.title||(j.vdraft||{}).title||"Your vlog");
  $("vuDoneH").textContent = later ? "Your vlog is scheduled" : p.privacy==="unlisted" ? "Your vlog is on YouTube, unlisted"
    : p.privacy==="private" ? "Your vlog is on YouTube, private" : "Your vlog is on YouTube";
  $("vuDoneSub").textContent = later ? "It goes public on "+at+(v.channel?" on "+v.channel:"")+"."
    : p.privacy==="unlisted" ? "Only people with the link can watch it."
    : p.privacy==="private" ? "Only you can see it. Change that in YouTube Studio when you're ready."
    : (v.channel?"Live on "+v.channel+".":"It's live.")+" YouTube may take a few minutes to finish processing it.";
  $("vuLinks").innerHTML=(v.youtube_url?'<a class="ghost sm" href="'+esc(v.youtube_url)+'" target="_blank" rel="noopener">Watch on YouTube<span class="ms" aria-hidden="true">open_in_new</span></a>':'')+
    (p.video_id?'<a class="ghost sm" href="'+esc(studioLink(p.video_id))+'" target="_blank" rel="noopener">Open in Studio<span class="ms" aria-hidden="true">open_in_new</span></a>':'');
  $("vuDoneNote").textContent=p.note||"";
  const can=!j.video_deleted_at && !(j.shorts||[]).filter(s=>!s.pending).length;
  $("vuNext").hidden=!can || vuAsked.has(j.id);
}
$("vuLater").onclick=()=>{
  vuAsked.add(vuId); $("vuNext").hidden=true;
  $("vuDoneNote").textContent=[$("vuDoneNote").textContent, "You can make its Shorts & Reels any time in the next "+VU_KEEP_H+" hours: Shorts & Reels, then Make Shorts."].filter(Boolean).join(" ");
};
$("vuMakeNow").onclick=()=>openMake(vuId);
$("vuBack").onclick=()=>openVlogs();
