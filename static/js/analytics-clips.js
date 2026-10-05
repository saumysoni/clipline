// Analytics, "Your clips" part (web/analytics_clips.py): each Pit Crew clip's first-week views, one line per
// platform in posting order (hollow dots: still in their first week), "What's working", top clips. Uses the
// helpers in analytics.js (tip, niceMax, compact, full, card, table).
let anPlat="", anVlog="", acData=null;
async function loadClipStats(){
  try{ const r=await fetch("/api/analytics/clips"+(anVlog?"?vlog="+anVlog:"")); acData=r.ok?await r.json():null; }catch(e){ acData=null; }
  paintClipStats();
}
const AC_PLATS=[["youtube","YouTube","var(--c-yt)"],["instagram","Instagram","var(--c-ig)"]];
function paintClipStats(){
  const box=$("anClips"), d=acData;
  $("anBody").dataset.plat=anPlat;
  $("anBody").hidden=!!anVlog;  // one vlog: only its clips (the channel-wide numbers are for everything)
  if(!d){ box.innerHTML=""; return; }
  // platforms asked for that have any of these clips on them
  const plats=AC_PLATS.filter(([k])=>(!anPlat||anPlat===k) && d.clips.some(c=>c[k]));
  const clips=d.clips.filter(c=>plats.some(([k])=>c[k]));
  const vname=anVlog&&(d.clips[0]||{}).vlog;
  const B=['<div class="an-plat"><i style="background:var(--primary)"></i><h2>'+(anVlog?"Clips from "+esc(vname||"this vlog"):"Your clips")+'</h2><span>Shorts &amp; Reels Pit Crew posted</span>'+
    (anVlog?'<button type="button" class="linkbtn" id="acAll">Show all vlogs</button>':'')+'</div>'];
  if(!clips.length){
    B.push('<div class="an-card an-mini"><span class="ms" aria-hidden="true">movie</span><p>'+(anVlog?"None of this vlog's clips are posted yet.":"Once Pit Crew posts your clips, each one's first week shows up here, so you can see if new ones do better than old ones.")+'</p></div>');
    box.innerHTML=B.join(""); wireAc(); return;
  }
  const points=plats.reduce((a,[k])=>a+clips.filter(c=>c[k]&&c[k].first7!=null).length,0);
  B.push(card("anCmp","Each clip's first week","Views in each clip's first 7 days, oldest to newest. Hollow dots: still in their first week.",
    points>=2 ? '<div class="an-viz" id="anCmpViz"></div>'
      : '<p class="sub ac-wait"><span class="ms" aria-hidden="true">hourglass_top</span>The chart fills in as clips finish their first week (YouTube\'s numbers arrive about 2 days later). '+
        clips.length+' posted so far: '+clips.map(c=>'<b>'+esc(c.title)+'</b> ('+plats.map(([k,n])=>c[k]?n+' '+esc(acVal(c[k])):'').filter(Boolean).join(", ")+')').join(", ")+'.</p>',
    table(["Clip","Posted"].concat(plats.map(([,n])=>n+" (first 7 days)")),clips.map(c=>[c.title,c.posted_at?new Date(c.posted_at).toLocaleDateString(undefined,{month:"short",day:"numeric"}):""].concat(plats.map(([k])=>acVal(c[k])))),plats.map((_,i)=>i+2))));
  // What's working
  const W=[];
  for(const [k,name] of plats){
    const t=d[k]; if(!t) continue;
    if(!t.ready){ if(clips.some(c=>c[k])) W.push('<div class="an-ins wait"><span class="ms" aria-hidden="true">hourglass_top</span><span><b>'+name+':</b> takeaways appear once '+t.need+' clips have finished their first week (you have '+t.have+').</span></div>'); continue; }
    (t.tips||[]).forEach(i=>W.push('<div class="an-ins'+(k==="instagram"?" ig":"")+'"><span class="ms" aria-hidden="true">'+({hook:"bolt",length:"straighten",time:"schedule",vlog:"video_library",best:"emoji_events"}[i.kind]||"lightbulb")+'</span><span>'+
      (plats.length>1?'<b>'+name+':</b> ':'')+esc(i.text)+(i.basis?' <small>('+esc(i.basis)+', first week)</small>':'')+'</span></div>'));
  }
  if(W.length) B.push('<h3 class="an-sub">What\'s working</h3><div class="an-insights">'+W.join("")+'</div>');
  // Top clips by first-week views (both platforms added up on All)
  const score=c=>plats.reduce((a,[k])=>a+((c[k]&&c[k].first7)||0),0);
  const top=[...clips].filter(c=>score(c)>0).sort((a,b)=>score(b)-score(a)).slice(0,5);
  if(top.length) B.push(card("anTopClips","Top clips","By views in their first 7 days"+(plats.length>1?", YouTube and Instagram together":""),
    '<div class="tops">'+top.map((c,i)=>'<button type="button" class="top-row ac-row" data-k="'+esc(c.job+":"+c.idx)+'"><span class="rk">'+(i+1)+'</span>'+
      (c.thumb?'<img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="" loading="lazy">':'<span class="noimg"></span>')+
      '<span class="tt"><b>'+esc(c.title)+'</b><small>'+esc(c.vlog)+plats.map(([k,n])=>c[k]&&c[k].first7!=null?' · '+n+' '+compact(c[k].first7):'').join("")+'</small></span>'+
      '<span class="nm">'+compact(score(c))+'</span></button>').join("")+'</div>',""));
  box.innerHTML=B.join(""); wireCards(); wireAc();
  if($("anCmpViz")) clipChart($("anCmpViz"),clips,plats);
}
// YouTube numbers that aren't in yet just need a few days; an Instagram Reel posted before Pit Crew saved daily numbers can't be known.
const acVal=p=>!p?"–":p.first7==null?(p.media_id?"not enough history":"not in yet"):full(p.first7)+(p.complete?"":" so far");
function wireAc(){
  if($("acAll")) $("acAll").onclick=()=>{ anVlog=""; $("anVlog").value=""; location.hash="analytics"; loadClipStats(); };
  document.querySelectorAll(".ac-row").forEach(b=>b.onclick=()=>acOpen(acData.clips.find(c=>c.job+":"+c.idx===b.dataset.k)));
}
// A clip's own numbers: its YouTube detail, else its Reel on Instagram.
function acOpen(c){
  if(!c) return;
  if(c.youtube&&(anPlat!=="instagram"||!c.instagram)) openShortAnalytics(c.youtube.video_id);
  else if(c.instagram&&c.instagram.permalink) window.open(c.instagram.permalink,"_blank","noopener");
}
// One line per platform through the clips in posting order; gaps where a clip isn't on that platform (or its
// first week is unknown), hollow dots while a clip is still in its first week.
function clipChart(el,clips,plats){
  const W=Math.max(260,el.clientWidth||600), H=240, L=46, R=20, T=12, Bm=26, n=clips.length;
  const vals=plats.map(([k])=>clips.map(c=>c[k]&&c[k].first7!=null?c[k].first7:null));
  const max=niceMax(Math.max(0,...vals.flat().filter(v=>v!=null))*1.1);
  const X=i=>n<2?(L+W-R)/2:L+i*(W-L-R)/(n-1), Y=v=>T+(H-T-Bm)*(1-v/max);
  let s='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" aria-label="First-week views of each clip">';
  s+='<g class="grid">'+[0,1,2,3,4].map(k=>'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(max*k/4)+'" y2="'+Y(max*k/4)+'"/>').join("")+'</g>';
  s+='<g class="axis">'+[0,1,2,3,4].map(k=>'<text x="'+(L-8)+'" y="'+(Y(max*k/4)+4)+'" text-anchor="end">'+esc(compact(max*k/4))+'</text>').join("");
  const step=Math.max(1,Math.ceil(n/7));
  clips.forEach((c,i)=>{ if(i%step===0||i===n-1) s+='<text x="'+X(i)+'" y="'+(H-6)+'" text-anchor="middle">'+(i+1)+'</text>'; });
  s+='</g>';
  plats.forEach(([k,,color],p)=>{
    let seg=[];
    const flush=()=>{ if(seg.length>1) s+='<polyline points="'+seg.join(" ")+'" fill="none" stroke="'+color+'" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'; seg=[]; };
    vals[p].forEach((v,i)=>{ if(v==null) flush(); else seg.push(X(i).toFixed(1)+","+Y(v).toFixed(1)); }); flush();
    vals[p].forEach((v,i)=>{ if(v==null) return; const done=clips[i][k].complete;
      s+='<circle class="ac-pt" data-i="'+i+'" cx="'+X(i)+'" cy="'+Y(v)+'" r="5" fill="'+(done?color:"var(--panel)")+'" stroke="'+color+'" stroke-width="2"/>'; });
  });
  s+='<line class="xh" y1="'+T+'" y2="'+(H-Bm)+'" visibility="hidden"/></svg>';
  if(plats.length>1) s+='<div class="an-legend">'+plats.map(([,nm,color])=>'<span><i style="background:'+color+'"></i>'+nm+'</span>').join("")+'<span><i class="hollow"></i>Still in its first week</span></div>';
  el.innerHTML=s;
  const svg=el.querySelector("svg"), xh=svg.querySelector(".xh");
  const near=e=>{ const rb=svg.getBoundingClientRect(), x=(e.clientX-rb.left)*W/rb.width; return Math.max(0,Math.min(n-1,Math.round(n<2?0:(x-L)/((W-L-R)/(n-1))))); };
  svg.addEventListener("pointermove",e=>{
    const i=near(e), c=clips[i]; xh.setAttribute("x1",X(i)); xh.setAttribute("x2",X(i)); xh.setAttribute("visibility","visible");
    tip.innerHTML='<div class="t ac-t">'+(c.thumb?'<img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="">':'')+'<span><b></b><small></small></span></div>'+
      plats.map(([k,nm,color])=>'<div class="r"><i style="background:'+color+'"></i><b>'+esc(acVal(c[k]))+'</b><span>'+nm+'</span></div>').join("");
    tip.querySelector(".ac-t b").textContent=c.title;
    tip.querySelector(".ac-t small").textContent="Clip "+(i+1)+" · "+(c.posted_at?new Date(c.posted_at).toLocaleDateString(undefined,{month:"short",day:"numeric"}):"");
    tip.hidden=false;
    tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-10,e.clientX+14)+"px"; tip.style.top=Math.max(8,e.clientY-tip.offsetHeight-10)+"px";
  });
  svg.addEventListener("pointerleave",()=>{ tip.hidden=true; xh.setAttribute("visibility","hidden"); });
  svg.addEventListener("click",e=>acOpen(clips[near(e)]));
  svg.style.cursor="pointer";
}
