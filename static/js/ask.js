// Ask your vlog (web/ask.py): search everything said or seen across vlogs (Vlogs page), and "Ask about this vlog"
// on a vlog's Shorts & Reels view. Every moment found can be watched (here while the video is kept, else on
// YouTube if the vlog is there) and turned into a Short (while the video is kept).
let addPrefill=null, askTimer=null, mpStop=null;
// The player lives in the Shorts & Reels markup; it opens from the Vlogs page too.
document.body.appendChild($("clPlayer"));
const mmss=t=>fmt(t);
function momentHTML(job,m,st,label){
  const canWatch=st.play_url||st.youtube_url, canMake=st.video;
  return '<li class="ask-m" data-job="'+esc(job)+'" data-s="'+m.start+'" data-e="'+(m.end||m.start+20)+'">'+
    '<span class="ask-t">'+mmss(m.start)+(m.end?'–'+mmss(m.end):'')+'</span>'+
    '<span class="ask-x">'+(m.kind?'<span class="ms" aria-hidden="true" title="'+(m.kind==="seen"?"Seen in the video":"Said in the vlog")+'">'+(m.kind==="seen"?"visibility":"chat_bubble")+'</span>':'')+label+'</span>'+
    '<span class="ask-acts">'+
      '<button type="button" class="linkbtn ask-watch"'+(canWatch?'':' disabled title="The video was deleted and the vlog isn\'t on YouTube"')+'>'+(st.play_url?"Watch":st.youtube_url?"Watch on YouTube":"Watch")+'</button>'+
      '<button type="button" class="linkbtn ask-make"'+(canMake?'':' disabled title="Needs the vlog\'s video, which was deleted. Upload the vlog again."')+'>Make a Short</button>'+
    '</span></li>';
}
function wireMoments(box,stFor,title){
  box.querySelectorAll(".ask-m").forEach(li=>{
    const job=li.dataset.job, s=+li.dataset.s, e=+li.dataset.e, st=stFor(job);
    li.querySelector(".ask-watch").onclick=()=>playMoment(st,job,s,e,title(job));
    li.querySelector(".ask-make").onclick=()=>{ addPrefill={start:s,end:Math.min(e,s+60)}; openJob(job,"add"); };
  });
}
// Plays a moment of the vlog here (stopping at its end), or opens it on YouTube at that second.
function playMoment(st,job,start,end,title){
  if(!st.play_url){ if(st.youtube_url) window.open(st.youtube_url+(st.youtube_url.includes("?")?"&":"?")+"t="+Math.floor(start),"_blank","noopener"); return; }
  const v=$("clVideo");
  $("clPlayTitle").textContent=title+" · "+mmss(start); v.poster=""; mpStop=end;
  v.src=st.play_url; $("clPlayer").classList.add("wide"); $("clPlayer").showModal();
  v.addEventListener("loadedmetadata",()=>{ v.currentTime=start; v.play().catch(()=>{}); },{once:true});
  v.onerror=()=>{ $("clPlayTitle").textContent="This browser can't play the vlog's video. Try Safari, or upload it again as MP4."; };
}
$("clVideo").addEventListener("timeupdate",()=>{ const v=$("clVideo"); if(mpStop!=null && v.currentTime>=mpStop){ v.pause(); mpStop=null; } });
$("clPlayer").addEventListener("close",()=>{ mpStop=null; $("clPlayer").classList.remove("wide"); });
// ---- search every vlog (Vlogs page)
$("vlSearchForm").onsubmit=async e=>{
  e.preventDefault();
  const q=$("vlSearch").value.trim(), box=$("vlResults");
  if(!q){ box.hidden=true; return; }
  box.hidden=false; box.innerHTML='<p class="ask-wait"><span class="spin" aria-hidden="true"></span>Searching your vlogs by meaning...</p>';
  let j; try{ j=await (await fetch("/api/search?q="+encodeURIComponent(q))).json(); }catch(x){ j={items:[]}; }
  const items=j.items||[];
  if(!items.length){ box.innerHTML='<p class="ask-none">Nothing found for "'+esc(q)+'". Try other words, or ask a vlog directly from its Shorts &amp; Reels.</p>'; return; }
  const hi=t=>{ let h=esc(t); (j.words||[]).forEach(w=>{ h=h.replace(new RegExp("\\b("+w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"[\\w']*)","gi"),"<mark>$1</mark>"); }); return h; };
  const byVlog=new Map(); items.forEach(r=>{ if(!byVlog.has(r.job)) byVlog.set(r.job,[]); byVlog.get(r.job).push(r); });
  box.innerHTML='<div class="ask-head"><b>'+items.length+' moment'+(items.length===1?'':'s')+' in '+byVlog.size+' vlog'+(byVlog.size===1?'':'s')+'</b>'+
    (j.mode==="words"?'<small class="ask-mode">Matched by words: the AI couldn\'t be reached for a search by meaning</small>':'')+'<button type="button" class="linkbtn" id="vlSearchX">Clear</button></div>'+
    [...byVlog.values()].map(rows=>'<div class="ask-group"><h3>'+esc(rows[0].vlog)+'</h3><ul class="ask-list">'+
      rows.slice(0,8).map(r=>momentHTML(r.job,{start:r.t,kind:r.kind},r,'<span class="ask-q"><span class="ask-qt">“'+hi(r.text)+'”</span>'+(r.why?'<small class="ask-why">'+esc(r.why)+'</small>':'')+'</span>')).join("")+'</ul></div>').join("");
  $("vlSearchX").onclick=()=>{ box.hidden=true; $("vlSearch").value=""; };
  wireMoments(box,job=>items.find(r=>r.job===job),job=>items.find(r=>r.job===job).vlog);
};
// ---- Ask about this vlog (Shorts & Reels, one vlog)
let askSt=null, askJob="";
async function paintAsk(job){
  const box=$("clAsk"); clearTimeout(askTimer);
  if(!job){ box.hidden=true; askJob=""; return; }
  if(askJob!==job){ askJob=job; box.innerHTML=""; }
  try{ askSt=await (await fetch("/api/vlogs/"+job+"/ask")).json(); }catch(e){ return; }
  if(clVlog!==job) return;
  box.hidden=false;
  const s=askSt, note = s.scenes==="ready" ? "Searches what you said and what's seen in the video."
    : s.scenes==="making" ? '<span class="spin" aria-hidden="true"></span> Looking through the video ('+(s.scenes_pct||0)+'%). Until it\'s done, answers use only what you said.'
    : s.can_make ? 'Answers use what you said. <button type="button" class="linkbtn" id="askScenes">Read the video too</button> so they include what\'s seen (about a minute).'
    : !s.video ? "Answers use what you said (the video was deleted before Pit Crew looked through it)."
    : s.scenes ? esc(s.scenes) : "Answers use what you said.";
  if(!box.querySelector("#askForm")){
    box.innerHTML='<div class="ask-top"><span class="ms" aria-hidden="true">forum</span><div><b>Ask about this vlog</b><small id="askNote"></small></div></div>'+
      '<form id="askForm" class="ask-search"><input id="askQ" type="text" maxlength="300" aria-label="Your question" placeholder="When was I climbing the mountain? Where did we talk about the budget?"><button class="primary" type="submit">Ask</button></form>'+
      '<div id="askOut" class="ask-results"></div>';
    $("askForm").onsubmit=askSubmit;
  }
  $("askNote").innerHTML=note;
  if($("askScenes")) $("askScenes").onclick=async()=>{ await fetch("/api/vlogs/"+job+"/scenes",{method:"POST"}); paintAsk(job); };
  if(s.scenes==="making") askTimer=setTimeout(()=>paintAsk(job),3000);
}
async function askSubmit(e){
  e.preventDefault();
  const q=$("askQ").value.trim(), out=$("askOut"), job=askJob;
  if(!q) return;
  out.innerHTML='<p class="ask-wait"><span class="spin" aria-hidden="true"></span>Looking through the vlog...</p>';
  let r,j; try{ r=await fetch("/api/vlogs/"+job+"/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})}); j=await r.json(); }
  catch(x){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  if(!r.ok){ out.innerHTML='<p class="err"></p>'; out.firstChild.textContent=j.error||"Couldn't answer that."; return; }
  out.innerHTML='<p class="ask-answer">'+esc(j.answer||(j.found?"":"Couldn't find that in this vlog."))+'</p>'+
    (j.moments.length?'<ul class="ask-list">'+j.moments.map(m=>momentHTML(job,m,j,esc(m.what||""))).join("")+'</ul>':'');
  const title=(clData.find(c=>c.job===job)||{}).vlog||"Your vlog";
  wireMoments(out,()=>j,()=>title);
}
