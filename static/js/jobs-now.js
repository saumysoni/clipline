// Progress card under + Create, on every page: the vlog being sent, vlogs being made, and "Shorts ready" when
// one finishes (with a short pop-up). Asks /api/vlogs every 3 seconds while something is being made.
let jnTimer=null, jnUpload=null, jnWorking=[], jnLast={}, jnDone={};
// The browser is still sending the video (pct), or null when it's done.
function jobsUpload(pct){ jnUpload=pct; paintJobsNow(); }
async function refreshJobsNow(){
  clearTimeout(jnTimer);
  let items;
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; items=(await r.json()).items||[]; }
  catch(e){ jnTimer=setTimeout(refreshJobsNow,10000); return; }
  for(const v of items){
    const was=jnLast[v.id], now=jnState(v);
    if((was==="working"||was==="uploading") && now!==was && !jnHere(v.id)){ v.was=was; jnDone[v.id]=v; jobsToast(v); }
    jnLast[v.id]=now;
  }
  jnWorking=items.filter(v=>["working","uploading"].includes(jnState(v)));
  paintJobsNow();
  if(!$("s7").hidden){ vlData=items; paintVlogs(); }  // keep the Vlogs page up to date too
  if(jnWorking.length || jnUpload!=null) jnTimer=setTimeout(refreshJobsNow,3000);
}
// A vlog's state for this card: working (being made or prepared), uploading (a vlog being sent to YouTube), or its status.
const jnState=v=>v.vpost&&v.vpost.state==="uploading"?"uploading":v.status;
// The creator is looking at it already (its progress, or its upload page).
const jnHere=id=>[id,"vlog/"+id].includes(location.hash.slice(1));
// Opens a vlog where it belongs: an upload (before any Shorts) on its upload page, anything else on its progress.
const jnOpen=v=>v.prep?openVlogUpload(v.id):startPolling(v.id);
// What the card and the pop-up say once something has finished.
function jnDoneText(v){
  const ok=v.status==="ready";
  if(v.was==="uploading"){ const up=v.vpost&&v.vpost.state==="done"; return [up, up?(v.vpost.privacy==="schedule"?"Scheduled on YouTube":"Uploaded to YouTube"):"The upload to YouTube stopped"]; }
  if(v.prep) return [ok, ok?"Ready: check the details and upload":"Stopped before it was ready"];
  return [ok, ok?v.shorts+" Short"+(v.shorts===1?"":"s")+" ready":"Stopped: open it to see why"];
}
// The creator opened this vlog: its "ready" note has done its job.
function seenJob(id){ if(jnDone[id]){ delete jnDone[id]; paintJobsNow(); } setTimeout(refreshJobsNow,1500); }
function paintJobsNow(){
  const rows=[];
  if(jnUpload!=null) rows.push('<div class="jn up"><span class="spin" aria-hidden="true"></span><span class="jn-t"><b>Sending your vlog</b>'+
    '<small>Keep this tab open. If it closes, choose the same file to carry on</small></span><em>'+Math.round(jnUpload)+'%</em><i class="jn-bar"><i style="width:'+jnUpload+'%"></i></i></div>');
  for(const v of jnWorking){
    const up=jnState(v)==="uploading", pct=up?Math.min(99,Math.round(v.vpost.pct||0)):vlPct(v);
    rows.push('<button type="button" class="jn" data-id="'+esc(v.id)+'"><span class="spin" aria-hidden="true"></span><span class="jn-t"><b>'+esc(v.title)+'</b>'+
      '<small>'+esc(up?"Uploading to YouTube":v.msg||"Working")+'</small></span><em>'+pct+'%</em><i class="jn-bar"><i style="width:'+pct+'%"></i></i></button>');
  }
  for(const v of Object.values(jnDone)){
    const [ok,text]=jnDoneText(v);
    rows.push('<button type="button" class="jn '+(ok?"ok":"bad")+'" data-id="'+esc(v.id)+'"><span class="ms" aria-hidden="true">'+(ok?"check_circle":"error")+'</span>'+
      '<span class="jn-t"><b>'+esc(v.title)+'</b><small>'+esc(text)+'</small></span></button>');
  }
  $("jobsNow").innerHTML=rows.join("");
  const all=[...jnWorking,...Object.values(jnDone)];
  $("jobsNow").querySelectorAll("button.jn").forEach(b=>b.onclick=()=>{ const v=all.find(x=>x.id===b.dataset.id); v?jnOpen(v):startPolling(b.dataset.id); });
}
function jobsToast(v){
  const [ok,text]=jnDoneText(v), t=document.createElement("button");
  t.type="button"; t.className="toast"+(ok?"":" bad"); t.setAttribute("role","status");
  t.innerHTML='<span class="ms" aria-hidden="true">'+(ok?"check_circle":"error")+'</span><span><b>'+esc(v.title)+'</b>'+esc(text)+'</span>';
  t.onclick=()=>{ t.remove(); jnOpen(v); };
  document.body.appendChild(t);
  setTimeout(()=>t.classList.add("go"),7000); setTimeout(()=>t.remove(),7600);
}
