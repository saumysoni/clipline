// Analytics page: how the creator's Shorts are doing. Data from /api/analytics (web/analytics.py,
// youtube/analytics.py). Charts are plain SVG drawn here: thin lines with a 10% area wash, a crosshair
// tooltip, keyboard arrows, and a Table button on every chart so no number needs hovering to read.
let anDays=28, anData=null, anLoading=false;
const nf=new Intl.NumberFormat("en"), cf=new Intl.NumberFormat("en",{notation:"compact",maximumFractionDigits:1});
const full=n=>nf.format(Math.round(n||0)), compact=n=>cf.format(Math.abs(n||0)>=1000?(n||0):Math.round(n||0));
const pct=n=>(n||0).toFixed((n||0)<10?1:0)+"%";
const secs=s=>{ s=Math.round(s||0); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0"); };
let regionName=c=>c; try{ const dn=new Intl.DisplayNames(["en"],{type:"region"}); regionName=c=>{ try{ return dn.of(c)||c; }catch(e){ return c; } }; }catch(e){}
const TRAFFIC={SHORTS:"Shorts feed",YT_SEARCH:"YouTube search",SUBSCRIBER:"Home & subscriptions",RELATED_VIDEO:"Suggested videos",
  YT_CHANNEL:"Your channel page",EXT_URL:"Other websites & apps",NO_LINK_OTHER:"Direct or unknown",NOTIFICATION:"Notifications",
  PLAYLIST:"Playlists",YT_PLAYLIST_PAGE:"Playlist pages",YT_OTHER_PAGE:"Other YouTube pages",HASHTAGS:"Hashtag pages",
  SOUND_PAGE:"Sound pages",SHORTS_CONTENT_LINKS:"Related-video links",VIDEO_REMIXES:"Remixes",END_SCREEN:"End screens",
  ADVERTISING:"Ads",CAMPAIGN_CARD:"Campaign cards",NO_LINK_EMBEDDED:"Embedded players",ANNOTATION:"Annotations",
  LIVE_REDIRECT:"Live redirects",PROMOTED:"Promoted"};
const GENDER={female:"Women",male:"Men",user_specified:"Other"};

function openAnalytics(){ clearInterval(poll); location.hash="analytics"; show(6); if(!anData||anData.days!==anDays) loadAnalytics(); }
$("analyticsNav").onclick=openAnalytics;
$("anRefresh").onclick=()=>loadAnalytics(true);
$("anRange").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  if(anLoading) return;
  $("anRange").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));
  anDays=+b.dataset.days; loadAnalytics();
});

async function loadAnalytics(){
  anLoading=true; $("anBody").classList.add("loading");
  if(!$("anBody").children.length) $("anBody").innerHTML='<div class="an-card an-empty"><span class="spin" aria-hidden="true"></span><p>Getting your numbers...</p></div>';
  let r,j;
  try{ r=await fetch("/api/analytics?days="+anDays); j=await r.json(); }
  catch(e){ j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  anLoading=false; $("anBody").classList.remove("loading");
  anData={days:anDays,...j};
  renderAnalytics(j);
}

function renderAnalytics(j){
  const note=$("anNote"); note.hidden=true;
  if(j.connected===false || j.error){
    $("anAsof").textContent="";
    const B=[];
    if(j.connected===false) B.push('<div class="an-card an-empty"><span class="ms" aria-hidden="true">insights</span><h2>Connect YouTube to see your analytics</h2>'+
      '<p>Views, likes, comments, watch time, who watches and how they find your Shorts, all in one place.</p>'+
      '<button type="button" class="primary" id="anConnect"><span class="ms" aria-hidden="true">smart_display</span>Connect YouTube</button></div>');
    else { note.hidden=false; note.innerHTML='<span class="ms" aria-hidden="true">error</span><span></span>'; note.lastChild.textContent=j.error; }
    B.push(igAnalyticsHTML(j));
    $("anBody").innerHTML=B.join(""); wireCards(); igAnalyticsWire();
    if($("anConnect")) $("anConnect").onclick=()=>signIn(()=>loadAnalytics());
    return;
  }
  const y=j.youtube, t=y.totals||{}, p=y.previous||null;
  $("anLede").textContent=(y.channel&&y.channel.title ? y.channel.title+" · "+full(y.channel.subscribers)+" subscribers. " : "")+
    "Every Short on your channel, not only the ones Pit Crew made.";
  $("anAsof").textContent=(y.range.days?"Last "+y.range.days+" days":"All time")+" · YouTube's numbers are about 2 days behind";
  if(!y.full){
    note.hidden=false;
    note.innerHTML='<span class="ms" aria-hidden="true">lock_open</span><span>These are the live counts for the Shorts Pit Crew uploaded. <b>Connect YouTube once more</b> '+
      '(and switch on <b>YouTube Analytics API</b> in Google Cloud, README step 5) to see watch time, retention, trends, how viewers find you and who they are.</span>'+
      '<button type="button" class="ghost" id="anRecon">Connect again</button>';
    $("anRecon").onclick=()=>signIn(()=>{ anData=null; loadAnalytics(); });
  }
  const daily=y.daily||[], B=['<div class="an-plat"><i style="background:var(--c-yt)"></i><h2>YouTube</h2><span>Shorts</span></div>'];
  // headline + tiles
  const d=k=>p&&p[k]!=null&&p[k]>0 ? deltaHTML((t[k]-p[k])/p[k]*100) : "";
  B.push('<div class="an-top'+(daily.length>1?'':' flat')+'"><div class="an-card an-hero"><div><div class="lab">Shorts views</div><div class="big">'+full(t.views)+'</div>'+d("views")+
    (p?'<div class="vs">Arrows compare with the '+(y.range.days)+' days before</div>':'')+
    (!y.full?'<div class="vs">Lifetime views of the '+(y.shorts||[]).length+' Shorts Pit Crew uploaded</div>':'')+'</div>'+
    (daily.length>1?'<div class="spark an-viz" id="anSpark"></div>':'')+'</div><div class="an-tiles">'+
    tile("schedule","Watch time",t.watch_hours!=null?compact(t.watch_hours)+" h":"–",d("watch_hours"))+
    tile("percent","Avg. viewed",t.avg_pct!=null&&y.full?pct(t.avg_pct):"–",d("avg_pct"))+
    tile("timer","Avg. view",t.avg_secs!=null&&y.full?secs(t.avg_secs):"–",d("avg_secs"))+
    tile("person_add","Subscribers",t.subs!=null?(t.subs>0?"+":"")+compact(t.subs):"–",d("subs"))+
    tile("favorite","Likes",compact(t.likes),d("likes"))+
    tile("chat_bubble","Comments",compact(t.comments),d("comments"))+
    tile("share","Shares",t.shares!=null?compact(t.shares):"–",d("shares"))+
    tile("bolt","Engagement",pct(t.engagement),d("engagement"))+'</div></div>');
  if((y.insights||[]).length) B.push('<div class="an-insights">'+y.insights.map(i=>'<div class="an-ins"><span class="ms" aria-hidden="true">'+
    ({best:"emoji_events",subs:"person_add",trend:"trending_up",length:"straighten",day:"event",feed:"swipe_up"}[i.kind]||"lightbulb")+'</span><span>'+esc(i.text)+'</span></div>').join("")+'</div>');
  if(daily.length>1) B.push(card("anDaily","Views per day","Your Shorts' daily views",
    '<div class="an-seg" id="anMetric" style="margin-bottom:10px"><button type="button" data-m="views" aria-pressed="true">Views</button><button type="button" data-m="likes">Likes</button><button type="button" data-m="subs">Subscribers</button></div><div class="an-viz" id="anDailyViz"></div>',
    table(["Day","Views","Likes","Subscribers"],daily.map(r=>[r.day,full(r.views),full(r.likes),full(r.subs)]),[1,2,3])));
  const sh=(y.shorts||[]).filter(s=>s.title||s.views);
  B.push(card("anTop","Top Shorts",sh.length?"Click a Short for its retention curve and where its viewers came from":"No Shorts with views in this period yet",
    topsHTML(sh.slice(0,12)),table(["Short","Views","Avg. viewed","Likes","Comments"],sh.map(s=>[s.title,full(s.views),s.avg_pct!=null?pct(s.avg_pct):"–",full(s.likes),full(s.comments)]),[1,2,3,4])));
  const g2=[];
  if((y.traffic||[]).length){ const tot=y.traffic.reduce((a,r)=>a+r.views,0)||1;
    g2.push(card("anTraffic","How viewers find your Shorts","Share of views by where they came from",barsHTML(y.traffic.slice(0,8).map(r=>({nm:TRAFFIC[r.source]||r.source,v:r.views/tot*100,lab:pct(r.views/tot*100)}))),
      table(["Source","Views","Share"],y.traffic.map(r=>[TRAFFIC[r.source]||r.source,full(r.views),pct(r.views/tot*100)]),[1,2]))); }
  if((y.countries||[]).length){ const tot=y.countries.reduce((a,r)=>a+r.views,0)||1;
    g2.push(card("anGeo","Where they watch from","Top countries by views",barsHTML(y.countries.map(r=>({nm:regionName(r.code),v:r.views,lab:compact(r.views)}))),
      table(["Country","Views"],y.countries.map(r=>[regionName(r.code),full(r.views)]),[1]))); }
  if((y.ages||[]).length) g2.push(card("anAge","Age","Share of your channel's viewers",barsHTML(y.ages.map(r=>({nm:r.group,v:r.pct,lab:pct(r.pct)}))),
    table(["Age","Viewers"],y.ages.map(r=>[r.group,pct(r.pct)]),[1])));
  if((y.genders||[]).length) g2.push(card("anGender","Gender","Share of your channel's viewers",splitHTML(y.genders),
    table(["Gender","Viewers"],y.genders.map(r=>[GENDER[r.gender]||r.gender,pct(r.pct)]),[1])));
  if(g2.length) B.push('<div class="an-grid2">'+g2.join("")+'</div>');
  B.push(igAnalyticsHTML(j));
  $("anBody").innerHTML=B.join("");
  wireCards(); igAnalyticsWire();
  if($("anSpark")) lineChart($("anSpark"),{x:daily.map(r=>r.day),series:[{name:"Views",color:"var(--c-yt)",values:daily.map(r=>r.views)}],height:Math.max(70,$("anSpark").clientHeight||120),bare:true});
  if($("anDailyViz")){
    const draw=m=>lineChart($("anDailyViz"),{x:daily.map(r=>r.day),fmtX:dayLabel,series:[{name:{views:"Views",likes:"Likes",subs:"Subscribers"}[m],color:"var(--c-yt)",values:daily.map(r=>r[m])}],height:220});
    draw("views");
    $("anMetric").querySelectorAll("button").forEach(b=>b.onclick=()=>{ $("anMetric").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b)); draw(b.dataset.m); });
  }
  document.querySelectorAll(".top-row").forEach(b=>b.onclick=()=>openShortAnalytics(b.dataset.id));
}

// ---------- pieces
function tile(icon,label,val,delta){ return '<div class="an-tile"><div class="lab"><span class="ms" aria-hidden="true">'+icon+'</span>'+label+'</div><div class="val">'+esc(val)+'</div>'+delta+'</div>'; }
function deltaHTML(ch){
  if(!isFinite(ch)) return "";
  const k=Math.abs(ch)<0.5?"flat":ch>0?"up":"down";
  return '<div class="delta '+k+'"><span class="ms" aria-hidden="true">'+(k==="up"?"arrow_upward":k==="down"?"arrow_downward":"remove")+'</span>'+
    (k==="flat"?"Same":Math.abs(ch).toFixed(Math.abs(ch)<10?1:0)+"%")+'</div>';
}
function card(id,title,sub,viz,tbl){
  return '<div class="an-card" id="'+id+'"><div class="an-head"><div><h2>'+esc(title)+'</h2><p class="sub">'+esc(sub)+'</p></div>'+
    (tbl?'<button type="button" class="an-tbtn" aria-pressed="false">Table</button>':'')+'</div><div class="an-viz-wrap"><div class="an-viz-in">'+viz+'</div>'+(tbl||"")+'</div></div>';
}
function table(heads,rows,num){
  num=new Set(num||[]);
  return '<div class="an-table"><table><thead><tr>'+heads.map((h,i)=>'<th'+(num.has(i)?' class="n"':'')+'>'+esc(h)+'</th>').join("")+'</tr></thead><tbody>'+
    rows.map(r=>'<tr>'+r.map((c,i)=>'<td'+(num.has(i)?' class="n"':'')+'>'+esc(c)+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>';
}
function wireCards(){
  document.querySelectorAll(".an-card .an-tbtn").forEach(b=>b.onclick=()=>{
    const c=b.closest(".an-card"), on=!c.classList.contains("show-table");
    c.classList.toggle("show-table",on); b.setAttribute("aria-pressed",on);
    c.querySelector(".an-viz-in").hidden=on;
  });
}
function barsHTML(rows){
  const max=Math.max(...rows.map(r=>r.v),1);
  return '<div class="bars">'+rows.map(r=>'<div class="bar-row" title="'+esc(r.nm+": "+r.lab)+'"><span class="nm">'+esc(r.nm)+'</span><span class="tr"><i style="width:'+(r.v/max*100).toFixed(1)+'%"></i></span><span class="v">'+esc(r.lab)+'</span></div>').join("")+'</div>';
}
function splitHTML(gs){
  const col={female:"var(--c-g1)",male:"var(--c-g2)"}, other="var(--faint)";
  return '<div class="split">'+gs.map(g=>'<i style="flex:'+Math.max(g.pct,0.5)+';background:'+(col[g.gender]||other)+'" title="'+esc((GENDER[g.gender]||g.gender)+": "+pct(g.pct))+'"></i>').join("")+'</div>'+
    '<div class="split-lab">'+gs.map(g=>'<span style="--k:'+(col[g.gender]||other)+'">'+esc(GENDER[g.gender]||g.gender)+' <b>'+pct(g.pct)+'</b></span>').join("")+'</div>';
}
function topsHTML(sh){
  if(!sh.length) return '<p class="sub">Once your Shorts get views in this period, they show up here.</p>';
  const max=Math.max(...sh.map(s=>s.views),1);
  return '<div class="tops">'+sh.map((s,i)=>'<button type="button" class="top-row" data-id="'+esc(s.id)+'">'+
    '<span class="rk">'+(i+1)+'</span><img src="'+esc(s.thumb||"")+'" alt="" referrerpolicy="no-referrer" loading="lazy">'+
    '<span class="tt"><b>'+esc(s.title||"Untitled Short")+(s.clipline?'<span class="tag clip">Pit Crew</span>':'')+'</b>'+
    '<small>'+(s.published?new Date(s.published).toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}):"")+(s.secs?" · "+secs(s.secs):"")+'</small></span>'+
    '<span class="tr"><i style="width:'+(s.views/max*100).toFixed(1)+'%"></i></span>'+
    '<span class="vv"><b>'+compact(s.views)+'</b><small>'+(s.avg_pct?pct(s.avg_pct)+" viewed":full(s.likes)+" likes")+'</small></span></button>').join("")+'</div>';
}
function dayLabel(s){ const d=new Date(s+"T00:00:00"); return d.toLocaleDateString(undefined,{month:"short",day:"numeric"}); }

// ---------- line chart (one axis; series share it)
const tip=document.createElement("div"); tip.className="an-tip"; tip.hidden=true; document.body.appendChild(tip);
function niceMax(v){ if(v<=0) return 1; const p=Math.pow(10,Math.floor(Math.log10(v))), f=v/p; return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*p; }
function lineChart(el,o){
  const W=Math.max(240,el.clientWidth||600), H=o.height||220, bare=!!o.bare;
  const L=bare?2:46, R=bare?6:54, T=bare?6:12, Bm=bare?4:26, n=o.x.length;
  const max=niceMax(Math.max(...o.series.flatMap(s=>s.values),0)*(o.headroom||1.08));
  const X=i=>L+(n<2?0:i*(W-L-R)/(n-1)), Y=v=>T+(H-T-Bm)*(1-v/max);
  const fy=o.fmtY||compact, fx=o.fmtX||(v=>v);
  let s='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" tabindex="0" aria-label="'+esc(o.series.map(x=>x.name).join(", "))+' chart">';
  if(!bare){
    s+='<g class="grid">'+[0,1,2,3,4].map(k=>'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(max*k/4)+'" y2="'+Y(max*k/4)+'"/>').join("")+'</g>';
    s+='<g class="axis">'+[0,1,2,3,4].map(k=>'<text x="'+(L-8)+'" y="'+(Y(max*k/4)+4)+'" text-anchor="end">'+esc(fy(max*k/4))+'</text>').join("");
    const step=Math.max(1,Math.ceil(n/6));
    const near=v=>o.x.reduce((b,x,i)=>Math.abs(x-v)<Math.abs(o.x[b]-v)?i:b,0);  // index of the x closest to v
    const ticks=o.xTicks ? [...new Set(o.xTicks.map(near))] : [...Array(n).keys()].filter(i=>i%step===0);
    ticks.forEach(i=>{ s+='<text x="'+X(i)+'" y="'+(H-6)+'" text-anchor="'+(i===0?"start":i===n-1&&o.xTicks?"end":"middle")+'">'+esc(fx(o.xTicks?o.xTicks[ticks.indexOf(i)]:o.x[i]))+'</text>'; });
    s+='</g>';
  }
  o.series.forEach(se=>{
    const pts=se.values.map((v,i)=>X(i).toFixed(1)+","+Y(v).toFixed(1)).join(" ");
    s+='<polygon points="'+X(0)+","+Y(0)+" "+pts+" "+X(n-1)+","+Y(0)+'" fill="'+se.color+'" fill-opacity=".1"/>';
    s+='<polyline points="'+pts+'" fill="none" stroke="'+se.color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    const lv=se.values[n-1];
    s+='<circle cx="'+X(n-1)+'" cy="'+Y(lv)+'" r="4" fill="'+se.color+'" stroke="var(--panel)" stroke-width="2"/>';
    if(!bare) s+='<text x="'+(X(n-1)+8)+'" y="'+(Y(lv)+4)+'" style="fill:var(--muted);font-size:11px;font-weight:600">'+esc(fy(lv))+'</text>';
  });
  s+='<line class="xh" y1="'+T+'" y2="'+(H-Bm)+'" x1="'+L+'" x2="'+L+'" visibility="hidden"/><g class="hov"></g><rect x="'+L+'" y="0" width="'+(W-L-R)+'" height="'+H+'" fill="transparent"/></svg>';
  if(o.series.length>1) s+='<div class="an-legend">'+o.series.map(se=>'<span><i style="background:'+se.color+'"></i>'+esc(se.name)+'</span>').join("")+'</div>';
  el.innerHTML=s;
  if(bare) return;
  const svg=el.querySelector("svg"), xh=svg.querySelector(".xh"), hov=svg.querySelector(".hov");
  let cur=n-1;
  const at=(i,cx,cy)=>{
    cur=Math.max(0,Math.min(n-1,i)); const x=X(cur);
    xh.setAttribute("x1",x); xh.setAttribute("x2",x); xh.setAttribute("visibility","visible");
    hov.innerHTML=o.series.map(se=>'<circle cx="'+x+'" cy="'+Y(se.values[cur])+'" r="4" fill="'+se.color+'" stroke="var(--panel)" stroke-width="2"/>').join("");
    tip.innerHTML='<div class="t"></div>'+o.series.map(()=>'<div class="r"><i></i><b></b><span></span></div>').join("");
    tip.querySelector(".t").textContent=fx(o.x[cur]);
    tip.querySelectorAll(".r").forEach((r,k)=>{ r.querySelector("i").style.background=o.series[k].color; r.querySelector("b").textContent=full(o.series[k].values[cur]); r.querySelector("span").textContent=o.series[k].name; });
    tip.hidden=false;
    const rb=svg.getBoundingClientRect(), px=cx!=null?cx:rb.left+x*rb.width/W, py=cy!=null?cy:rb.top+20;
    tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-10,px+14)+"px"; tip.style.top=Math.max(8,py-tip.offsetHeight-10)+"px";
  };
  const off=()=>{ tip.hidden=true; xh.setAttribute("visibility","hidden"); hov.innerHTML=""; };
  svg.addEventListener("pointermove",e=>{ const rb=svg.getBoundingClientRect(), x=(e.clientX-rb.left)*W/rb.width; at(Math.round((x-L)/((W-L-R)/Math.max(1,n-1))),e.clientX,e.clientY); });
  svg.addEventListener("pointerleave",off); svg.addEventListener("blur",off);
  svg.addEventListener("focus",()=>at(cur));
  svg.addEventListener("keydown",e=>{ if(e.key==="ArrowLeft"){ e.preventDefault(); at(cur-1); } if(e.key==="ArrowRight"){ e.preventDefault(); at(cur+1); } });
}

// ---------- one Short
$("anDClose").onclick=()=>$("anDetail").close();
$("anDetail").addEventListener("close",()=>{ tip.hidden=true; });
async function openShortAnalytics(id){
  const s=((anData&&anData.youtube&&anData.youtube.shorts)||[]).find(x=>x.id===id)||{id};
  $("anDBody").innerHTML=shortHead(s)+'<div class="an-card an-empty"><span class="spin" aria-hidden="true"></span><p>Getting this Short\'s numbers...</p></div>';
  $("anDetail").showModal();
  let j; try{ j=await (await fetch("/api/analytics/short/"+encodeURIComponent(id)+"?days="+anDays)).json(); }catch(e){ j={error:"Couldn't reach Pit Crew."}; }
  if(j.error){ $("anDBody").innerHTML=shortHead(s)+'<p class="err"></p>'; $("anDBody").querySelector(".err").textContent=j.error; return; }
  const m={...s,...(j.short||{})}, t=j.totals||{}, B=[shortHead(m)];
  B.push('<div class="an-tiles">'+tile("visibility","Views",compact(t.views!=null?t.views:m.views),"")+tile("percent","Avg. viewed",t.averageViewPercentage!=null?pct(t.averageViewPercentage):"–","")+
    tile("timer","Avg. view",t.averageViewDuration!=null?secs(t.averageViewDuration):"–","")+tile("favorite","Likes",compact(t.likes!=null?t.likes:m.likes),"")+
    tile("chat_bubble","Comments",compact(t.comments!=null?t.comments:m.comments),"")+tile("person_add","Subscribers",t.subscribersGained!=null?"+"+compact(t.subscribersGained):"–","")+'</div>');
  if(!j.full) B.push('<p class="sub">Connect YouTube once more to see this Short\'s retention curve and where its viewers came from.</p>');
  const ret=j.retention||[], dd=j.daily||[], tr=j.traffic||[];
  if(ret.length>1) B.push(card("anRet","Audience retention","How many viewers are still watching at each point of the Short (over 100% means people rewatch)",'<div class="an-viz" id="anRetViz"></div>',
    table(["Point in the Short","Still watching"],ret.map(r=>[r.at+"%",pct(r.watching)]),[1])));
  if(dd.length>1) B.push(card("anDDaily","Views per day","",'<div class="an-viz" id="anDDailyViz"></div>',table(["Day","Views"],dd.map(r=>[r.day,full(r.views)]),[1])));
  if(tr.length){ const tot=tr.reduce((a,r)=>a+r.views,0)||1;
    B.push(card("anDTraffic","How viewers found it","",barsHTML(tr.slice(0,6).map(r=>({nm:TRAFFIC[r.source]||r.source,v:r.views/tot*100,lab:pct(r.views/tot*100)}))),
      table(["Source","Views"],tr.map(r=>[TRAFFIC[r.source]||r.source,full(r.views)]),[1]))); }
  $("anDBody").innerHTML=B.join(""); wireCards();
  if($("anRetViz")) lineChart($("anRetViz"),{x:ret.map(r=>r.at),xTicks:[0,25,50,75,100],fmtX:v=>Math.round(v)+"%",fmtY:v=>Math.round(v)+"%",series:[{name:"Still watching",color:"var(--c-yt)",values:ret.map(r=>r.watching)}],height:200});
  if($("anDDailyViz")) lineChart($("anDDailyViz"),{x:dd.map(r=>r.day),fmtX:dayLabel,series:[{name:"Views",color:"var(--c-yt)",values:dd.map(r=>r.views)}],height:180});
}
function shortHead(s){
  return '<div class="an-d-head">'+(s.thumb?'<img src="'+esc(s.thumb)+'" alt="" referrerpolicy="no-referrer">':'')+'<div><h2 id="anDTitle">'+esc(s.title||"Your Short")+'</h2>'+
    '<div class="links"><a href="https://www.youtube.com/shorts/'+esc(s.id)+'" target="_blank" rel="noopener">Watch on YouTube</a>'+
    '<a href="'+esc(studioLink(s.id))+'" target="_blank" rel="noopener">Open in Studio</a></div></div></div>';
}
window.addEventListener("resize",()=>{ if(!$("s6").hidden && anData && anData.youtube){ clearTimeout(window._anRs); window._anRs=setTimeout(()=>renderAnalytics(anData),200); } });
