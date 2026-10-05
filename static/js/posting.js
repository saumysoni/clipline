// Posting: the Post view (after review), uploading, marking posted Shorts, updating them on YouTube.
// Step 3 has two views: #reviewView (the cards) and #postView (when and where). The cards stay in the
// page while posting, so the titles and ticks are read from them.
function showPost(on){
  closeTile();
  $("reviewView").hidden=on; $("postView").hidden=!on;
  if(on){ document.querySelectorAll("#reel video").forEach(v=>v.pause()); paintPostList(); if(typeof igRefresh==="function") igRefresh(); }
  $("err3r").textContent="";
  window.scrollTo(0,0); dock();
}
function paintPostList(){
  const ups=new Map((job&&job.uploads||[]).map(u=>[u.idx,u]));
  const rows=[...document.querySelectorAll(".short[data-idx]:not(.pending)")].filter(el=>el.querySelector(".keep input").checked || ups.has(+el.dataset.idx));
  $("postCount").textContent = rows.length===1 ? "1 Short" : rows.length+" Shorts";
  $("postList").innerHTML = rows.length ? rows.map(el=>{
    const s=job.shorts.find(x=>x.idx===+el.dataset.idx)||{}, u=ups.get(s.idx);
    return '<li><img src="/media/'+job.id+'/'+esc(s.thumb||"")+'" alt=""><span><b>'+esc(el.querySelector("input.title").value)+'</b>'+
      '<small'+(u?' class="done"':'')+'>'+(u ? "YouTube: "+esc(whenText(u.when)) : fmt(s.end-s.start)+" long")+'</small>'+(typeof igLine==="function"?igLine(s.idx):"")+'</span></li>';
  }).join("") : '<li class="post-empty">No Shorts ticked. Go back to review and tick the ones to post.</li>';
}
function dock(){
  const total=document.querySelectorAll(".short[data-idx]:not(.pending)").length, k=document.querySelectorAll(".short .keep input:checked").length;
  const busy=document.querySelectorAll(".short.redoing").length;
  $("dockText").textContent = busy ? "Making "+(busy===1?"a Short":busy+" Shorts")+"..." : k ? k+" of "+total+" will be posted" : "Tick at least one Short";
  $("nextBtn").disabled = !k || busy>0;
  const now=$("sched2").value==="now", n=k===1 ? "1 Short" : k+" Shorts";
  $("customWhen").hidden = $("sched2").value!=="custom";
  $("schedBtn").innerHTML = '<span class="ms" aria-hidden="true">smart_display</span>Upload '+(k>1?k+" ":"")+'to YouTube';
  $("schedBtn").title = !yt.signed_in ? "You'll connect YouTube first" : now ? "Posts "+n+" now" : "Schedules "+n;
  $("schedBtn").disabled = !k || busy>0 || POSTING_NOW();
  if(typeof igDock==="function") igDock();
}
function POSTING_NOW(){ return !!job && ["starting","connecting","uploading"].includes(job.upload_status); }
// The custom schedule starts tomorrow at 6 PM unless the creator picks something else.
(()=>{ const d=new Date(); d.setDate(d.getDate()+1); d.setHours(18,0,0,0);
  const p=x=>String(x).padStart(2,"0");
  $("schStart").value=d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+"T18:00";
  const m=new Date(Date.now()+16*60000); $("schStart").min=m.getFullYear()+"-"+p(m.getMonth()+1)+"-"+p(m.getDate())+"T"+p(m.getHours())+":"+p(m.getMinutes()); })();
$("nextBtn").onclick=()=>showPost(true);
$("backReview").onclick=()=>{ if(!POSTING_NOW()) showPost(false); };
$("sched2").addEventListener("change",()=>{ $("err3").textContent=""; dock(); });
$("schStart").addEventListener("input",()=>$("schStart").classList.remove("bad"));
$("schedBtn").onclick=()=>{
  $("err3").textContent="";
  if(!yt.signed_in){ signIn(); return; }  // sign in first; then they press Upload themselves
  postShorts();
};
async function postShorts(){
  const shorts=[...document.querySelectorAll(".short[data-idx]:not(.pending)")].map(el=>({idx:+el.dataset.idx,title:el.querySelector("input.title").value,keep:el.querySelector(".keep input").checked}));
  let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
  const mode=$("sched2").value;
  if(mode==="custom" && !$("schStart").value){ $("schStart").classList.add("bad"); $("err3").textContent="Pick the date and time for the first Short."; return; }
  $("schedBtn").disabled=true;
  let r, j;
  try{
    r=await fetch("/api/schedule/"+jobId,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({shorts,schedule:mode,tz,start:$("schStart").value,every:+$("schEvery").value})});
    j=await r.json();
  }catch(e){ $("schedBtn").disabled=false; $("err3").textContent="Couldn't reach Pit Crew. Is the app window still open?"; return; }
  if(!r.ok){
    $("schedBtn").disabled=false; $("err3").textContent=j.error||"Couldn't start posting.";
    if(j.field==="start") $("schStart").classList.add("bad");
    if(j.signin){ yt.signed_in=false; paintAccount(); }
    return;
  }
  job.upload_status="starting"; onReview=false;
  $("upPanel").hidden=false; $("upMsg").textContent="Connecting to YouTube"; $("upPct").style.width="0%";
  clearInterval(poll); poll=setInterval(tick,1000);
}
function renderUpload(){
  if($("reel").children.length===0) renderResults();
  if($("s3").hidden && job.upload_status!=="done") show(3);
  if($("postView").hidden && job.upload_status!=="done") showPost(true);
  $("upPanel").hidden=false; $("upMsg").textContent=job.upload_msg||""; $("upPct").style.width=(job.upload_pct||0)+"%";
  markPosted(); paintPostList();
  if(job.upload_status==="error"){ clearInterval(poll); $("err3").textContent="Posting stopped: "+job.upload_msg; }
  if(job.upload_status==="done"){ clearInterval(poll); renderDone(); }
}
// Shorts already on YouTube (after a stop halfway) can't be ticked again, so nothing is posted twice.
function whenText(iso){
  if(!iso) return "Posted";
  const d=new Date(iso);
  return (d>new Date() ? "Scheduled for " : "Went out ")+d.toLocaleDateString(undefined,{weekday:"short",month:"short",day:"numeric"})+", "+d.toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"});
}
function markPosted(){
  const ups=new Map((job.uploads||[]).map(u=>[u.idx,u]));
  document.querySelectorAll(".short[data-idx]:not(.pending)").forEach(el=>{
    const u=ups.get(+el.dataset.idx), info=el.querySelector(".ytinfo");
    if(!u){ if(info) info.remove(); return; }
    const box=el.querySelector(".keep input"), lab=el.querySelector(".keep");
    box.checked=false; box.disabled=true; lab.classList.add("posted");
    lab.lastChild.textContent=" On YouTube";
    const s=job.shorts.find(x=>x.idx===u.idx)||{}, title=el.querySelector("input.title");
    const newVideo = u.video && s.video!==u.video, newTitle = title && title.value.trim()!==u.title;
    const html='<span><b>On YouTube</b> · '+esc(whenText(u.when))+'</span>'+
      '<small>'+(newVideo ? "You've edited this Short since it was uploaded. Update replaces the YouTube copy with this one, at the same time."
        : newTitle ? "Update changes the title on YouTube." : "Edit the title, hook or moment here, then update it on YouTube.")+'</small>'+
      '<button type="button" class="ghost upd"'+(newVideo||newTitle?'':' disabled')+'><span class="ms" aria-hidden="true">sync</span>'+(newVideo?"Replace on YouTube":"Update on YouTube")+'</button>'+
      '<div class="err" role="alert"></div>';
    let box2=info;
    if(!box2){ box2=document.createElement("div"); box2.className="ytinfo"; el.querySelector(".row").after(box2);
      if(title) title.addEventListener("input",()=>markPosted()); }
    const keepErr=box2.querySelector(".err") ? box2.querySelector(".err").textContent : "";
    if(box2.dataset.html!==html){ box2.innerHTML=html; box2.dataset.html=html; box2.querySelector(".err").textContent=keepErr;
      box2.querySelector(".upd").onclick=()=>repost(u.idx,box2,newVideo); }
  });
  dock();
}
async function repost(idx,box,replace){
  const err=box.querySelector(".err"), btn=box.querySelector(".upd"); err.textContent="";
  if(!yt.signed_in){ signIn(); return; }
  if(replace && !confirm("Replace this Short on YouTube?\n\nPit Crew uploads the edited version with the same time, then deletes the old upload.")) return;
  const el=document.querySelector('.short[data-idx="'+idx+'"]');
  btn.disabled=true; btn.lastChild.textContent = replace ? "Replacing..." : "Updating...";
  let r,j;
  try{ r=await fetch("/api/repost/"+jobId+"/"+idx,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:el.querySelector("input.title").value})}); j=await r.json(); }
  catch(e){ j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; r={ok:false}; }
  if(!r.ok){ err.textContent=j.error||"Couldn't update it."; box.dataset.html=""; tick(); return; }
  if(j.done==="title"){ const u=(job.uploads||[]).find(x=>x.idx===idx); if(u) u.title=el.querySelector("input.title").value.trim(); box.dataset.html=""; markPosted(); box.querySelector("small").textContent="Title updated on YouTube."; return; }
  onReview=false; job.upload_status="starting";
  $("upPanel").hidden=false; $("upMsg").textContent="Connecting to YouTube"; $("upPct").style.width="0%";
  clearInterval(poll); poll=setInterval(tick,1000);
}
