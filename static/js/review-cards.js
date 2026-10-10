// Step 3: Try again, Add a Short, and drawing / refreshing the cards.
// "Post this" starts unticked: the creator picks the Shorts to post. The ticks live here ("jobid:idx"), so a card
// redrawn after Try again or a new hook keeps its tick.
const reviewPicked=new Set();
const ADD_CARD='<article class="short addcard" id="addCard">'+
  '<button type="button" class="phone" id="addOpen"><span class="add-ic"><span class="ms" aria-hidden="true">add</span></span><b>Add a Short</b><span>A moment Pit Crew missed</span></button>'+
  '<div class="redo" hidden>'+
    '<textarea rows="3" maxlength="500" aria-label="Describe the moment you want" placeholder="Describe the moment, for example: when we see the bear. Or type the exact times below."></textarea>'+
    '<div class="pick-row"><button type="button" class="ghost pick"><span class="ms" aria-hidden="true">movie</span>Choose on the video</button></div><span class="small-lab">Or type the exact times</span>'+timesHTML()+
    '<div class="redo-row"><button type="button" class="primary go">Make this Short</button><button type="button" class="ghost cancel">Cancel</button></div>'+
  '</div>'+
  '<div class="err rerr" role="alert"></div>'+
  '<button type="button" class="tile-x" aria-label="Close"><span class="ms" aria-hidden="true">close</span></button>'+
'</article>';
// Reads a moment form (description and/or From/To). Returns null and shows why if the times don't make sense.
function readMoment(box,errEl){
  const note=box.querySelector("textarea").value.trim(), start=box.querySelector(".t0").value.trim(), end=box.querySelector(".t1").value.trim();
  const bad=(start||end) ? momentProblem(start,end,"moment") : "";
  box.querySelectorAll(".times-row input").forEach(i=>i.classList.toggle("bad",!!bad));
  if(bad){ errEl.textContent=bad; return null; }
  return {note,start,end};
}
async function sendMoment(url,body,errEl){
  let r, j={};
  try{
    r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    try{ j=await r.json(); }catch(e){}
  }catch(e){ errEl.textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; return false; }
  if(!r.ok){ errEl.textContent=j.error||"Something went wrong. Please try again."; return false; }
  clearInterval(poll); poll=setInterval(tick,1000); tick();
  return true;
}
function wire(el){
  if(el.classList.contains("pending")) return;
  el.querySelectorAll(".toggle button").forEach(b=>b.onclick=()=>{
    el.querySelectorAll(".toggle button").forEach(x=>x.setAttribute("aria-pressed",x===b));
    el.classList.toggle("thumb",b.dataset.v==="t"); if(b.dataset.v==="t") el.querySelector("video").pause();
  });
  el.querySelector(".keep input").onchange=e=>{
    const k=job.id+":"+el.dataset.idx; e.target.checked?reviewPicked.add(k):reviewPicked.delete(k);
    el.classList.toggle("on",e.target.checked); dock();
  };
  el.querySelector("video").addEventListener("play",e=>document.querySelectorAll("#reel video").forEach(v=>{ if(v!==e.target) v.pause(); }));
  const redo=el.querySelector(".redo"), err=el.querySelector(".rerr");
  el.querySelector(".retry").onclick=()=>{
    if(job.video_deleted_at){  // nothing to cut a new moment from: say so instead of a button that does nothing
      err.textContent="This vlog's video was deleted from Pit Crew (it's kept for 72 hours after the last edit), so Try again can't cut a new moment. Upload the vlog again to remake this Short.";
      return;
    }
    redo.hidden=!redo.hidden; if(!redo.hidden) redo.querySelector("textarea").focus();
  };
  el.querySelector(".pick").onclick=()=>openPicker(redo,+el.dataset.idx);
  wireHook(el,job.shorts.find(x=>x.idx===+el.dataset.idx));
  wireLook(el,job.shorts.find(x=>x.idx===+el.dataset.idx));
  wirePostText(el,job.shorts.find(x=>x.idx===+el.dataset.idx));
  wireTile(el);
  el.querySelector(".cancel").onclick=()=>{ redo.hidden=true; err.textContent=""; };
  el.querySelector(".go").onclick=async()=>{
    err.textContent="";
    const m=readMoment(redo,err); if(!m) return;
    if(await sendMoment("/api/retry/"+jobId+"/"+el.dataset.idx,m,err)){ redo.hidden=true; el.querySelector("video").pause(); }
  };
}
function wireAdd(){
  const card=$("addCard"), form=card.querySelector(".redo"), err=card.querySelector(".rerr");
  $("addOpen").onclick=()=>{ openTile(card); form.hidden=false; form.querySelector("textarea").focus(); };
  card.querySelector(".tile-x").onclick=()=>{ form.hidden=true; err.textContent=""; closeTile(); };
  card.querySelector(".pick").onclick=()=>openPicker(form,null);
  card.querySelector(".cancel").onclick=()=>{ form.hidden=true; err.textContent=""; closeTile(); };
  card.querySelector(".go").onclick=async()=>{
    err.textContent="";
    const m=readMoment(form,err); if(!m) return;
    if(!m.note&&!m.start){ err.textContent="Describe the moment you want, or type its From and To times."; return; }
    if(await sendMoment("/api/add/"+jobId,m,err)){
      form.hidden=true; form.querySelector("textarea").value=""; form.querySelectorAll("input").forEach(i=>i.value=""); closeTile();
    }
  };
}
function paintState(el,s){
  el.classList.toggle("redoing",!!s.retrying);
  el.classList.toggle("on",reviewPicked.has(job.id+":"+s.idx));
  el.querySelector(".bmsg").textContent = s.retrying ? (s.retry_msg||"Making this Short") : "";
  if(s.pending) return;
  const gone=!!job.video_deleted_at;  // the vlog's video is deleted: nothing can be re-cut (titles and looks still work)
  el.querySelector(".retry").disabled = !!s.retrying;  // a deleted video is explained on click instead
  el.querySelectorAll(".hk-change,.hk-apply,.hk-rewrite").forEach(b=>b.disabled=!!s.retrying || gone);
  if(gone) el.querySelector(".retry").title="Needs the vlog's video, which was deleted";
  const rerr=el.querySelector(".rerr");
  if(s.retry_error) rerr.textContent="Try again stopped: "+s.retry_error;
  else if(!gone || rerr.textContent.startsWith("Try again stopped")) rerr.textContent="";
}
function paintTitle(){
  const n=job.shorts.filter(s=>!s.pending).length;
  $("resTitle").textContent = n===1 ? "Your Short is ready" : "Your "+n+" Shorts are ready";
  // Fewer Shorts than asked for: say why and what to do, until Add a Short makes up the difference.
  const asked=job.count||0, few=job.shorts.length<asked;
  $("fewNote").hidden=!few;
  if(few) $("fewNote").innerHTML='<span class="ms" aria-hidden="true">lightbulb</span><span>'+"Found "+n+" good moment"+(n===1?"":"s")+" out of the "+asked+" you asked for. "+
    (job.little_speech ? "Pit Crew picks moments from what's said, and this vlog doesn't have much talking. "
                       : "The rest of the vlog didn't have strong stand-alone moments. ")+
    "Use <b>Add a Short</b> at the end to pick more moments yourself, by describing them or by their times.</span>";
  $("goneNote").hidden=!job.video_deleted_at;
  $("addCard").hidden=!!job.video_deleted_at;
  const err=$("addCard").querySelector(".rerr");
  if(job.add_error) err.textContent="Couldn't add the Short: "+job.add_error;
  else if(err.textContent.startsWith("Couldn't add the Short")) err.textContent="";
}
function renderResults(){
  if(job.schedule && $("sched2").querySelector('option[value="'+job.schedule+'"]')) $("sched2").value=job.schedule;
  $("reel").innerHTML = job.shorts.map(cardHTML).join("")+ADD_CARD;
  document.querySelectorAll(".short[data-idx]").forEach(el=>{
    const s=job.shorts.find(x=>x.idx===+el.dataset.idx);
    wire(el); paintState(el,s);
  });
  wireAdd(); paintTitle(); dock();
}
// While Shorts are being made, refresh only the cards that changed, so edited titles and ticks stay.
function refreshResults(){
  const ids=new Set(job.shorts.map(s=>String(s.idx)));
  document.querySelectorAll(".short[data-idx]").forEach(el=>{ if(!ids.has(el.dataset.idx)) el.remove(); });
  job.shorts.forEach(s=>{
    let el=document.querySelector('.short[data-idx="'+s.idx+'"]');
    if(!el || el.dataset.video!==(s.pending?"":s.video+"|"+s.thumb)){
      if(el){ el.insertAdjacentHTML("afterend",cardHTML(s)); el.remove(); }
      else $("addCard").insertAdjacentHTML("beforebegin",cardHTML(s));
      el=document.querySelector('.short[data-idx="'+s.idx+'"]'); wire(el);
    }
    paintState(el,s);
  });
  paintTitle(); dock();
}
