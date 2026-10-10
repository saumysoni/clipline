// Posting to Instagram from the Post page: its own schedule, the Post button, and each Reel's state in the
// list (waiting / posting / on Instagram / failed). Pit Crew's server posts each Reel at its time
// (web/instagram_posting.py), so this page only plans, shows progress, cancels and retries.
let igPoll=null;
const igPosts=()=>new Map(((job&&job.ig_posts)||[]).map(p=>[p.idx,p]));
(()=>{ const d=new Date(); d.setDate(d.getDate()+1); d.setHours(18,0,0,0); const p=x=>String(x).padStart(2,"0");
  $("igStart").value=d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+"T18:00"; })();
$("igSched").addEventListener("change",()=>{ $("igErr").textContent=""; igDock(); });
$("igStart").addEventListener("input",()=>$("igStart").classList.remove("bad"));
function igTicked(){
  const posts=igPosts();
  return [...document.querySelectorAll(".short[data-idx]:not(.pending)")].filter(el=>{
    const idx=+el.dataset.idx, p=posts.get(idx), ytDone=((job&&job.uploads)||[]).some(u=>u.idx===idx);
    return (el.querySelector(".keep input").checked || ytDone) && !(p && ["waiting","posting","done","check"].includes(p.status));
  });
}
function igDock(){
  if(!$("igBtn")) return;
  const n=igTicked().length, ready=ig.configured && ig.signed_in && ig.can_post;
  $("igCustom").hidden=$("igSched").value!=="custom";
  $("igWhenBox").hidden=!ready;
  $("igBtn").innerHTML='<span class="ms" aria-hidden="true">photo_camera</span>'+
    (!ig.configured ? "Instagram isn't set up" : !ig.signed_in ? "Connect Instagram" : !ig.can_post ? "Connect again" :
     n ? ($("igSched").value==="now" ? "Post "+(n>1?n+" ":"")+"to Instagram now" : "Schedule "+(n>1?n+" ":"")+"on Instagram") : "All planned on Instagram");
  $("igBtn").disabled = !ig.configured || (ready && !n) || document.querySelectorAll(".short.redoing").length>0;
}
$("igBtn").onclick=()=>{
  $("igErr").textContent="";
  if(!ig.signed_in || !ig.can_post){ igSignIn(); return; }
  igSchedule();
};
async function igSchedule(){
  const shorts=igTicked().map(el=>({idx:+el.dataset.idx,title:el.querySelector("input.title").value,keep:true}));
  let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
  const mode=$("igSched").value;
  if(mode==="custom" && !$("igStart").value){ $("igStart").classList.add("bad"); $("igErr").textContent="Pick the date and time for the first Reel."; return; }
  $("igBtn").disabled=true;
  let r,j;
  try{ r=await fetch("/api/instagram/schedule/"+jobId,{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({shorts,schedule:mode,tz,start:$("igStart").value,every:+$("igEvery").value,
      yt_schedule:$("sched2").value,yt_start:$("schStart").value,yt_every:+$("schEvery").value,
      ig_id:ig.ig_id})}); j=await r.json(); }  // ig_id: the account this page says it's posting to
  catch(e){ j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; r={ok:false}; }
  if(!r.ok){ $("igErr").textContent=j.error||"Couldn't plan the Reels."; if(j.field==="start") $("igStart").classList.add("bad");
    if(j.signin||j.switch) loadIg(); igDock(); return; }
  job.ig_posts=j.ig_posts; igRefresh();
}
function igLine(idx){
  const p=igPosts().get(idx); if(!p) return "";
  const when=p.when?new Date(p.when):null, at=when?when.toLocaleDateString(undefined,{weekday:"short",month:"short",day:"numeric"})+", "+when.toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"}):"";
  const st={waiting:when&&when>new Date()?"Instagram: "+at:"Instagram: posting soon", posting:"Instagram: "+(p.step||"posting")+"...",
    done:"On Instagram", error:"Instagram: "+(p.error||"failed"), check:"Instagram: "+(p.error||"check Instagram")}[p.status]||"";
  const acts = p.status==="done" && p.permalink ? '<a href="'+esc(p.permalink)+'" target="_blank" rel="noopener">Open</a>'
    : p.status==="waiting" ? '<button type="button" class="linkbtn" data-igcancel="'+idx+'">Cancel</button>'
    : ["error","check"].includes(p.status) ? '<button type="button" class="linkbtn" data-igretry="'+idx+'">Try again</button><button type="button" class="linkbtn" data-igcancel="'+idx+'">Remove</button>' : "";
  return '<small class="igst '+p.status+'"><span class="ms" aria-hidden="true">'+({done:"check_circle",error:"error",check:"help",posting:"progress_activity"}[p.status]||"schedule")+'</span>'+
    '<span class="t">'+esc(st)+'</span>'+acts+'</small>';
}
document.addEventListener("click",async e=>{
  const c=e.target.closest("[data-igcancel],[data-igretry]"); if(!c) return;
  const retry=c.hasAttribute("data-igretry"), idx=c.dataset.igretry||c.dataset.igcancel;
  c.disabled=true;
  try{ const r=await fetch("/api/instagram/"+(retry?"retry":"cancel")+"/"+jobId+"/"+idx,{method:"POST"}); const j=await r.json();
    if(r.ok) job.ig_posts=j.ig_posts; else $("igErr").textContent=j.error||"Couldn't change it."; }
  catch(err){ $("igErr").textContent="Couldn't reach Pit Crew."; }
  igRefresh();
});
// While a Reel is due or posting, check its state every few seconds.
function igRefresh(){
  if(typeof paintPostList==="function" && !$("postView").hidden) paintPostList();
  igDock();
  const busy=((job&&job.ig_posts)||[]).some(p=>p.status==="posting" || (p.status==="waiting" && (!p.when || new Date(p.when)-new Date()<120000)));
  clearTimeout(igPoll);
  if(busy) igPoll=setTimeout(async()=>{
    if(!jobId) return;
    try{ const j=await (await fetch("/api/status/"+jobId)).json(); if(j&&j.id===jobId){ job.ig_posts=j.ig_posts; } }catch(e){}
    igRefresh();
  }, 3000);
}
