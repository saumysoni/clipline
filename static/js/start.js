// Make my Shorts: sends the vlog and settings to start a job.
$("make").onclick=async()=>{
  $("err1").textContent="";
  const f=$("file").files[0], link=$("link").value.trim();
  if(!f && !link){ $("err1").textContent="Choose your vlog file or paste a Google Drive link."; return; }
  const okVideo=checkVideoLink(), okYt=checkYtLink(), okMust=checkMust();
  if(!okVideo||!okYt){ $("err1").textContent="Fix the link marked in red above."; (okVideo?$("ytUrl"):$("link")).focus(); return; }
  if(!okMust){ $("err1").textContent="Fix the must-have moment marked in red above."; $("mustRows").querySelector("input.bad").focus(); return; }
  const fd=new FormData();
  if(!f) fd.append("link",link);
  fd.append("yt_url",$("ytUrl").value.trim());
  fd.append("title",$("vTitle").value.trim());
  fd.append("description",$("vDesc").value.trim());
  fd.append("note",$("note").value.trim());
  fd.append("must",JSON.stringify(mustRows().map(r=>({start:r.start,end:r.end}))));
  fd.append("count",count);
  fd.append("style",document.querySelector("input[name=style]:checked").value);
  fd.append("schedule",$("sched").value);
  try{ fd.append("tz",Intl.DateTimeFormat().resolvedOptions().timeZone||""); }catch(e){}
  $("sched2").value=$("sched").value;
  if(!await stillSignedIn($("err1"))) return;
  $("make").disabled=true; $("upBar").hidden=false;
  const ended=()=>{ $("make").disabled=false; $("upBar").hidden=true; renderCount(); jobsUpload(null); };
  if(f){  // the video goes first, in pieces (js/video-upload.js); a rejected start below keeps it for the next press
    const long=await videoTooLong(f); if(long){ ended(); $("err1").textContent=long; return; }
    jobsUpload(0);
    try{ fd.append("upload", await sendVideo(f, p=>{ $("upBar").firstElementChild.style.width=p+"%"; $("make").textContent="Sending video "+Math.floor(p)+"%"; jobsUpload(p); },
                                             note=>{ $("err1").textContent=note; })); }
    catch(e){ ended(); $("err1").textContent=e.message; return; }
  }
  let r,j={}; try{ r=await fetch("/api/start",{method:"POST",body:fd}); j=await r.json(); }
  catch(e){ ended(); $("err1").textContent="Couldn't reach Pit Crew. Check your internet connection, then press the button again (the video is already sent)."; return; }
  ended();
  if(r.status===401) return;  // the sign-in screen is showing (js/account.js)
  if(!r.ok){
    if(j.upload_gone && f) upRemember(f,null);
    if(j.field==="link") flag($("link"),$("linkHint"),j.error);
    if(j.field==="yt_url") flag($("ytUrl"),$("ytHint"),j.error);
    if(j.field==="must"){ $("mustHint").textContent=j.error; $("mustHint").classList.add("bad"); }
    $("err1").textContent=j.error||"Something went wrong starting the job."; return;
  }
  if(f) upRemember(f,null);
  startPolling(j.id);
};
