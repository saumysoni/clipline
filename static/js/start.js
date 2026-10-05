// Make my Shorts: sends the vlog and settings to start a job.
$("make").onclick=()=>{
  $("err1").textContent="";
  const f=$("file").files[0], link=$("link").value.trim();
  if(!f && !link){ $("err1").textContent="Choose your vlog file or paste a Google Drive link."; return; }
  const okVideo=checkVideoLink(), okYt=checkYtLink(), okMust=checkMust();
  if(!okVideo||!okYt){ $("err1").textContent="Fix the link marked in red above."; (okVideo?$("ytUrl"):$("link")).focus(); return; }
  if(!okMust){ $("err1").textContent="Fix the must-have moment marked in red above."; $("mustRows").querySelector("input.bad").focus(); return; }
  const fd=new FormData();
  if(f) fd.append("video",f); else fd.append("link",link);
  fd.append("yt_url",$("ytUrl").value.trim());
  fd.append("title",$("vTitle").value.trim());
  fd.append("description",$("vDesc").value.trim());
  fd.append("note",$("note").value.trim());
  fd.append("must",JSON.stringify(mustRows().map(r=>({start:r.start,end:r.end}))));
  fd.append("count",count);
  fd.append("style",document.querySelector("input[name=style]:checked").value);
  fd.append("schedule",$("sched").value);
  $("sched2").value=$("sched").value;
  const xhr=new XMLHttpRequest();
  xhr.open("POST","/api/start");
  $("make").disabled=true; $("upBar").hidden=false;
  jobsUpload(0);
  xhr.upload.onprogress=e=>{ if(e.lengthComputable){ $("upBar").firstElementChild.style.width=(e.loaded/e.total*100)+"%"; $("make").textContent="Sending video "+Math.round(e.loaded/e.total*100)+"%"; jobsUpload(e.loaded/e.total*100); } };
  xhr.onload=()=>{
    $("make").disabled=false; $("upBar").hidden=true; renderCount(); jobsUpload(null);
    let r={}; try{r=JSON.parse(xhr.responseText);}catch(e){}
    if(xhr.status!==200){
      if(r.field==="link") flag($("link"),$("linkHint"),r.error);
      if(r.field==="yt_url") flag($("ytUrl"),$("ytHint"),r.error);
      if(r.field==="must"){ $("mustHint").textContent=r.error; $("mustHint").classList.add("bad"); }
      $("err1").textContent=r.error||"Something went wrong starting the job."; return;
    }
    startPolling(r.id);
  };
  xhr.onerror=()=>{ $("make").disabled=false; renderCount(); jobsUpload(null); $("err1").textContent="Couldn't reach Pit Crew. Is the app window still open?"; };
  xhr.send(fd);
};
