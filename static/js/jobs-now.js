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
    if(jnLast[v.id]==="working" && v.status!=="working" && location.hash.slice(1)!==v.id){
      jnDone[v.id]=v; jobsToast(v);
    }
    jnLast[v.id]=v.status;
  }
  jnWorking=items.filter(v=>v.status==="working");
  paintJobsNow();
  if(!$("s7").hidden){ vlData=items; paintVlogs(); }  // keep the Vlogs page up to date too
  if(jnWorking.length || jnUpload!=null) jnTimer=setTimeout(refreshJobsNow,3000);
}
// The creator opened this vlog: its "ready" note has done its job.
function seenJob(id){ if(jnDone[id]){ delete jnDone[id]; paintJobsNow(); } setTimeout(refreshJobsNow,1500); }
function paintJobsNow(){
  const rows=[];
  if(jnUpload!=null) rows.push('<div class="jn up"><span class="spin" aria-hidden="true"></span><span class="jn-t"><b>Sending your vlog</b>'+
    '<small>Keep this tab open until it\'s sent</small></span><em>'+Math.round(jnUpload)+'%</em><i class="jn-bar"><i style="width:'+jnUpload+'%"></i></i></div>');
  for(const v of jnWorking){
    const pct=vlPct(v);
    rows.push('<button type="button" class="jn" data-id="'+esc(v.id)+'"><span class="spin" aria-hidden="true"></span><span class="jn-t"><b>'+esc(v.title)+'</b>'+
      '<small>'+esc(v.msg||"Working")+'</small></span><em>'+pct+'%</em><i class="jn-bar"><i style="width:'+pct+'%"></i></i></button>');
  }
  for(const v of Object.values(jnDone)){
    const ok=v.status==="ready";
    rows.push('<button type="button" class="jn '+(ok?"ok":"bad")+'" data-id="'+esc(v.id)+'"><span class="ms" aria-hidden="true">'+(ok?"check_circle":"error")+'</span>'+
      '<span class="jn-t"><b>'+esc(v.title)+'</b><small>'+(ok?v.shorts+" Short"+(v.shorts===1?"":"s")+" ready":"Stopped: open it to see why")+'</small></span></button>');
  }
  $("jobsNow").innerHTML=rows.join("");
  $("jobsNow").querySelectorAll("button.jn").forEach(b=>b.onclick=()=>startPolling(b.dataset.id));
}
function jobsToast(v){
  const ok=v.status==="ready", t=document.createElement("button");
  t.type="button"; t.className="toast"+(ok?"":" bad"); t.setAttribute("role","status");
  t.innerHTML='<span class="ms" aria-hidden="true">'+(ok?"check_circle":"error")+'</span><span><b>'+esc(v.title)+'</b>'+
    (ok?v.shorts+" Short"+(v.shorts===1?" is":"s are")+" ready":"Stopped before the Shorts were made")+'</span>';
  t.onclick=()=>{ t.remove(); startPolling(v.id); };
  document.body.appendChild(t);
  setTimeout(()=>t.classList.add("go"),7000); setTimeout(()=>t.remove(),7600);
}
