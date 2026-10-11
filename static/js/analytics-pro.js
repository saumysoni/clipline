// Analytics tabs beyond the Overview (web/analytics_more.py): Compare (YouTube Studio's advanced mode: every video in
// the period with all its numbers and share of the total, tick up to 8 to see them day by day), Audience (devices,
// subscribers, where they watch, search terms, cities...), Instagram (the account: reach, followers, who they are and
// when they're online), plus two Overview cards: "This week" and "Vlogs and their Shorts". Uses the helpers in
// analytics.js (card, table, barsHTML, lineChart, tile, deltaHTML, full, compact, pct, secs, tip) and its filters
// (anQuery(), anContent, anWord()).
let anTab="overview", anCmp=null, anCmpPick=[], anCmpSort={k:"views",dir:-1}, anCmpMetric="views", anCmpFind="", anAud=null, anIg=null, anIgDays=30;
const anTabPick=pageTabs("anTabs",t=>{ anTab=t; anTabShown(); anProLoad(); });
// Series colours (css/analytics-pro.css --s1..--s8, validated): fixed order, and a video keeps its colour while ticked.
const AN_S=n=>"var(--s"+(n+1)+")";
function anTabShown(){
  $("anPlat").hidden=anTab!=="overview";               // YouTube vs Instagram only splits the Overview
  $("anContent").hidden=anTab==="instagram";
  $("anVlog").hidden=anTab!=="overview";
}
// Called after the Overview loads and when a tab opens: fills whatever is showing (each tab loads once per range).
function anProLoad(){
  const q=anQuery();
  if(anTab==="overview"){ anWeekLoad(); anVlogsLoad(q); }
  if(anTab==="compare" && (!anCmp||anCmp.q!==q)) anCmpLoad(q);
  if(anTab==="audience" && (!anAud||anAud.q!==q)) anAudLoad(q);
  if(anTab==="instagram" && !anIg) anIgLoad();
}
const anWait=t=>'<div class="an-card an-empty"><span class="spin" aria-hidden="true"></span><p>'+esc(t)+'</p></div>';
const anMsg=(icon,t,html)=>'<div class="an-card an-mini"><span class="ms" aria-hidden="true">'+icon+'</span><p>'+esc(t)+'</p>'+(html||"")+'</div>';
async function anGet(url){
  try{ const r=await fetch(url), j=await r.json(); return r.ok?j:{error:j.error||"Couldn't load these numbers. Try Refresh."}; }
  catch(e){ return {error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
}

// ---------- donut: parts of a whole (devices, subscribers, followers...). Up to 5 slices, the rest folded into "Other".
function donutHTML(rows,o){
  o=o||{};
  rows=rows.filter(r=>r.v>0).sort((a,b)=>b.v-a.v);
  if(rows.length>5){ const rest=rows.slice(4).reduce((a,r)=>a+r.v,0); rows=rows.slice(0,4).concat([{nm:"Other",v:rest,other:true}]); }
  const tot=rows.reduce((a,r)=>a+r.v,0)||1, R=58, r0=40, C=70;
  let a0=-Math.PI/2, arcs="";
  const gap=rows.length>1?0.035:0;
  rows.forEach((r,i)=>{
    const a1=a0+2*Math.PI*r.v/tot, s=a0+gap/2, e=Math.max(s+0.001,a1-gap/2), big=e-s>Math.PI?1:0;
    const p=(ang,rad)=>(C+rad*Math.cos(ang)).toFixed(2)+","+(C+rad*Math.sin(ang)).toFixed(2);
    const col=r.other?"var(--faint)":AN_S(i);
    arcs+='<path class="dn-arc" data-i="'+i+'" fill="'+col+'" d="M'+p(s,R)+" A"+R+","+R+" 0 "+big+" 1 "+p(e,R)+" L"+p(e,r0)+" A"+r0+","+r0+" 0 "+big+" 0 "+p(s,r0)+'Z"/>';
    r.col=col; r.share=r.v/tot*100; a0=a1;
  });
  const lead=rows[0];
  return '<div class="donut" data-rows=\''+esc(JSON.stringify(rows.map(r=>({nm:r.nm,lab:r.lab||pct(r.share),share:r.share,col:r.col}))))+'\'>'+
    '<svg viewBox="0 0 140 140" role="img" aria-label="'+esc(rows.map(r=>r.nm+" "+pct(r.share)).join(", "))+'">'+arcs+
    '<text x="70" y="68" text-anchor="middle" class="dn-big">'+esc(lead?pct(lead.share):"")+'</text>'+
    '<text x="70" y="86" text-anchor="middle" class="dn-sm">'+esc(lead?(lead.nm.length>14?lead.nm.slice(0,13)+"…":lead.nm):"")+'</text></svg>'+
    '<ul class="dn-leg">'+rows.map((r,i)=>'<li data-i="'+i+'"><i style="background:'+r.col+'"></i><span>'+esc(r.nm)+'</span><b>'+esc(pct(r.share))+'</b>'+(r.lab?'<small>'+esc(r.lab)+'</small>':'')+'</li>').join("")+'</ul></div>';
}
function wireDonuts(root){
  (root||document).querySelectorAll(".donut").forEach(d=>{
    const rows=JSON.parse(d.dataset.rows||"[]");
    const on=(i,e)=>{ d.querySelectorAll(".dn-arc").forEach(a=>a.classList.toggle("dim",+a.dataset.i!==i)); d.querySelectorAll(".dn-leg li").forEach(l=>l.classList.toggle("on",+l.dataset.i===i));
      const r=rows[i]; tip.innerHTML='<div class="r"><i></i><b></b><span></span></div>'; tip.querySelector("i").style.background=r.col; tip.querySelector("b").textContent=pct(r.share); tip.querySelector("span").textContent=r.nm+(r.lab&&r.lab!==pct(r.share)?" · "+r.lab:"");
      tip.hidden=false; tip.style.left=Math.min(innerWidth-tip.offsetWidth-10,e.clientX+14)+"px"; tip.style.top=Math.max(8,e.clientY-tip.offsetHeight-10)+"px"; };
    const off=()=>{ tip.hidden=true; d.querySelectorAll(".dim,.on").forEach(x=>x.classList.remove("dim","on")); };
    d.querySelectorAll(".dn-arc,.dn-leg li").forEach(el=>{ el.addEventListener("pointermove",e=>on(+el.dataset.i,e)); el.addEventListener("pointerleave",off); });
  });
}
// A 24-column chart (followers online by hour, in the viewer's own time).
function hoursHTML(byHour){
  const max=Math.max(...byHour,1), best=byHour.indexOf(max);
  const h=i=>{ const d=new Date(); d.setHours(i,0,0,0); return d.toLocaleTimeString(undefined,{hour:"numeric"}); };
  return '<div class="hours">'+byHour.map((v,i)=>'<div class="hr'+(i===best?" best":"")+'" title="'+esc(h(i)+": "+full(v)+" followers online")+'"><i style="height:'+(v/max*100).toFixed(1)+'%"></i><span>'+(i%3===0?esc(h(i)):"")+'</span></div>').join("")+'</div>'+
    '<p class="sub">Most of your followers are online around <b>'+esc(h(best))+'</b> (your time).</p>';
}

// ---------- This week (Overview, top)
let anWeekAt=0;
async function anWeekLoad(){
  if(Date.now()-anWeekAt<6e5 && $("anWeek").innerHTML) return;
  anWeekAt=Date.now();
  const j=await anGet("/api/analytics/week"), y=j.youtube, i=j.instagram;
  if(j.error || (!y && !i)){ $("anWeek").innerHTML=""; return; }
  const bits=[], says=[];
  if(y && y.views!=null){
    const ch=y.prev?(y.views-y.prev)/y.prev*100:null;
    bits.push('<div class="wk-n"><span>YouTube views</span><b>'+compact(y.views)+'</b>'+(ch!=null?deltaHTML(ch):"")+'</div>');
    if(y.subs!=null) bits.push('<div class="wk-n"><span>New subscribers</span><b>'+(y.subs>0?"+":"")+compact(y.subs)+'</b></div>');
    if(y.watch_hours!=null) bits.push('<div class="wk-n"><span>Watch time</span><b>'+compact(y.watch_hours)+' h</b></div>');
    if(ch!=null) says.push("YouTube views are "+(Math.abs(ch)<1?"about the same as":(ch>0?"up ":"down ")+Math.abs(ch).toFixed(0)+"% on")+" the week before.");
    if(y.best && y.best.views) says.push("Best this week: “"+y.best.title+"” with "+compact(y.best.views)+" views.");
  }
  if(i && (i.views!=null || i.reach!=null)){
    if(i.views!=null) bits.push('<div class="wk-n ig"><span>Instagram views</span><b>'+compact(i.views)+'</b></div>');
    if(i.reach!=null) bits.push('<div class="wk-n ig"><span>Accounts reached</span><b>'+compact(i.reach)+'</b></div>');
    if(i.follows) bits.push('<div class="wk-n ig"><span>New followers</span><b>+'+compact(i.follows)+'</b></div>');
  }
  $("anWeek").innerHTML='<div class="an-card wk"><div class="wk-head"><span class="ms" aria-hidden="true">calendar_view_week</span><h2>This week</h2><span class="sub">Last 7 days, YouTube Shorts and videos'+(i?" plus Instagram":"")+'</span></div>'+
    '<div class="wk-row">'+bits.join("")+'</div>'+(says.length?'<p class="wk-say">'+esc(says.join(" "))+'</p>':'')+'</div>';
}

// ---------- Vlogs and their Shorts (Overview, after YouTube)
async function anVlogsLoad(q){
  if($("anVlogs").dataset.q===q) return;
  $("anVlogs").dataset.q=q;
  const j=await anGet("/api/analytics/vlogs?"+q);
  if(q!==anQuery()) return;
  const items=(j.items||[]);
  if(!items.length){ $("anVlogs").innerHTML=""; return; }
  $("anVlogs").innerHTML=card("anVl","Vlogs and their Shorts","How each vlog did next to the Shorts made from it, and how many viewers the Shorts sent to it",
    '<div class="vl-links">'+items.map(v=>'<div class="vl-link">'+(v.thumb?'<img src="'+esc(v.thumb)+'" alt="" referrerpolicy="no-referrer" loading="lazy">':'<span class="noimg"></span>')+
      '<div class="vl-t"><b>'+esc(v.title||"Your vlog")+'</b><small>'+v.shorts+' Short'+(v.shorts===1?"":"s")+' posted</small></div>'+
      '<div class="vl-n"><span>Vlog views</span><b>'+compact(v.views)+'</b></div>'+
      '<div class="vl-n"><span>Its Shorts\' views</span><b>'+compact(v.shorts_views)+'</b></div>'+
      '<div class="vl-n hi"><span>Viewers sent by the Shorts</span><b>'+compact(v.sent)+'</b><small>'+(v.views?pct(v.sent/v.views*100)+" of the vlog's views":"")+'</small></div></div>').join("")+'</div>'+
    '<p class="sub">"Sent by the Shorts" counts views that came from the related-video link on a Short. YouTube Analytics, about 2 days behind.</p>',
    table(["Vlog","Vlog views","Shorts","Shorts' views","Sent by Shorts"],items.map(v=>[v.title,full(v.views),full(v.shorts),full(v.shorts_views),full(v.sent)]),[1,2,3,4]));
  wireCards();
}

// ---------- Compare (YouTube Studio's advanced mode)
const CMP_COLS=[["views","Views"],["engaged","Engaged views"],["likes","Likes"],["comments","Comments"],["shares","Shares"],["subs","Subscribers"],["minutes","Watch time"],["avg_secs","Avg. view"],["avg_pct","Avg. % viewed"]];
const CMP_SHARE=new Set(["views","engaged","likes","comments","shares","subs","minutes"]);  // a share of the total makes sense
async function anCmpLoad(q){
  $("anCmpBox").innerHTML=anWait("Getting every "+anWord()[0]+"'s numbers...");
  const j=await anGet("/api/analytics/videos?"+q);
  if(q!==anQuery()) return;
  if(j.connected===false){ $("anCmpBox").innerHTML=anMsg("smart_display","Connect YouTube to compare your videos."); return; }
  if(j.error){ $("anCmpBox").innerHTML=anMsg("error",j.error); return; }
  anCmp={q,...j};
  const ids=new Set(anCmp.videos.map(v=>v.id));
  anCmpPick=anCmpPick.filter(id=>ids.has(id));
  if(!anCmpPick.length) anCmpPick=anCmp.videos.slice(0,3).map(v=>v.id);
  anCmpPaint(); anCmpChart();
}
function anCmpVal(v,k){
  const x=v[k];
  if(x==null) return "–";
  return k==="minutes"?compact(x/60)+" h":k==="avg_secs"?secs(x):k==="avg_pct"?pct(x):full(x);
}
function anCmpPaint(){
  const d=anCmp, W=anWord(), tot=d.total||{};
  const cols=CMP_COLS.filter(([k])=>k!=="engaged"||tot.engaged!=null);
  let vids=d.videos.slice();
  if(anCmpFind) vids=vids.filter(v=>(v.title||"").toLowerCase().includes(anCmpFind));
  vids.sort((a,b)=>{ const k=anCmpSort.k, x=k==="title"?(a.title||""):(a[k]||0), y=k==="title"?(b.title||""):(b[k]||0); return (x>y?1:x<y?-1:0)*anCmpSort.dir; });
  const th=(k,lab,num)=>'<th'+(num?' class="n"':'')+' aria-sort="'+(anCmpSort.k===k?(anCmpSort.dir>0?"ascending":"descending"):"none")+'"><button type="button" data-k="'+k+'">'+esc(lab)+(anCmpSort.k===k?'<span class="ms" aria-hidden="true">'+(anCmpSort.dir>0?"arrow_upward":"arrow_downward")+'</span>':'')+'</button></th>';
  const cell=(v,k)=>'<td class="n"><b>'+esc(anCmpVal(v,k))+'</b>'+(CMP_SHARE.has(k)&&tot[k]&&v[k]!=null?'<small>'+pct(v[k]/tot[k]*100)+'</small>':'')+'</td>';
  const rows=vids.map(v=>{ const at=anCmpPick.indexOf(v.id), on=at>=0;
    return '<tr class="'+(on?"on":"")+'"><td class="ck"><label class="cmp-ck" style="--k:'+(on?AN_S(at):"transparent")+'"><input type="checkbox" data-id="'+esc(v.id)+'"'+(on?" checked":"")+(anCmpPick.length>=8&&!on?" disabled":"")+' aria-label="Show '+esc(v.title||"this video")+' on the chart"></label></td>'+
      '<td class="vt"><button type="button" class="cmp-v" data-id="'+esc(v.id)+'">'+(v.thumb?'<img src="'+esc(v.thumb)+'" alt="" referrerpolicy="no-referrer" loading="lazy">':'<span class="noimg"></span>')+
      '<span><b>'+esc(v.title||"Untitled")+(v.clipline?'<span class="tag clip">Pit Crew</span>':'')+'</b><small>'+(v.published?new Date(v.published).toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}):"")+(v.secs?" · "+secs(v.secs):"")+'</small></span></button></td>'+
      cols.map(([k])=>cell(v,k)).join("")+'</tr>'; }).join("");
  const total='<tr class="tot"><td></td><td class="vt"><b>Total</b><small>'+d.videos.length+' '+(d.videos.length===1?W[0]:W[1])+'</small></td>'+cols.map(([k])=>'<td class="n"><b>'+esc(CMP_SHARE.has(k)?anCmpVal(tot,k):"")+'</b></td>').join("")+'</tr>';
  $("anCmpBox").innerHTML=
    '<div class="an-card"><div class="an-head"><div><h2>Compare your '+W[1]+'</h2><p class="sub">Tick up to 8 to see them day by day. Each number shows its share of the total. '+anRangeText(d.range?{...d.range,custom:true}:{})+'.</p></div>'+
    '<a class="ghost sm" id="anCsv" href="/api/analytics/videos.csv?'+anQuery()+'" download><span class="ms" aria-hidden="true">download</span>Download CSV</a></div>'+
    '<div class="cmp-bar"><div class="an-seg" id="anCmpMetric"><button type="button" data-m="views" aria-pressed="'+(anCmpMetric==="views")+'">Views</button>'+(tot.engaged!=null?'<button type="button" data-m="engaged" aria-pressed="'+(anCmpMetric==="engaged")+'">Engaged views</button>':'')+'</div>'+
    '<span class="cmp-n">'+anCmpPick.length+' of 8 on the chart</span>'+(anCmpPick.length?'<button type="button" class="linkbtn" id="anCmpClear">Clear</button>':'')+'</div>'+
    '<div class="an-viz" id="anCvChart">'+(anCmpPick.length?'<p class="sub">Getting each day\'s numbers...</p>':'<p class="sub">Tick '+W[1]+' below to see them here.</p>')+'</div></div>'+
    '<div class="an-card cmp-card"><div class="cmp-tools"><input type="search" id="anCmpFind" placeholder="Find a '+W[0]+' by title" value="'+esc(anCmpFind)+'" aria-label="Find a video"></div>'+
    (d.videos.length?'<div class="cmp-wrap"><table class="cmp"><thead><tr><th class="ck"></th>'+th("title",W[0][0].toUpperCase()+W[0].slice(1))+cols.map(([k,l])=>th(k,l,true)).join("")+'</tr></thead><tbody>'+total+rows+'</tbody></table></div>'
      :'<p class="sub">No '+W[1]+' with views in this period.</p>')+'</div>';
  $("anCmpBox").querySelectorAll(".cmp th button").forEach(b=>b.onclick=()=>{ const k=b.dataset.k; anCmpSort={k,dir:anCmpSort.k===k?-anCmpSort.dir:(k==="title"?1:-1)}; anCmpPaint(); anCmpChart(true); });
  $("anCmpBox").querySelectorAll(".cmp input[type=checkbox]").forEach(c=>c.onchange=()=>{
    const id=c.dataset.id; if(c.checked){ if(anCmpPick.length<8) anCmpPick.push(id); } else anCmpPick=anCmpPick.filter(x=>x!==id);
    anCmpPaint(); anCmpChart(); });
  $("anCmpBox").querySelectorAll(".cmp-v").forEach(b=>b.onclick=()=>openShortAnalytics(b.dataset.id));
  $("anCmpBox").querySelectorAll("#anCmpMetric button").forEach(b=>b.onclick=()=>{ anCmpMetric=b.dataset.m; anCmpPaint(); anCmpChart(true); });
  if($("anCmpClear")) $("anCmpClear").onclick=()=>{ anCmpPick=[]; anCmpPaint(); anCmpChart(); };
  const f=$("anCmpFind"); f.oninput=()=>{ anCmpFind=f.value.trim().toLowerCase(); const at=f.selectionStart; anCmpPaint(); anCmpChart(true); const g=$("anCmpFind"); g.focus(); g.setSelectionRange(at,at); };
}
let anCmpSeries={};  // video id -> {day: {views, engaged}} (kept per range)
async function anCmpChart(cached){
  const box=$("anCvChart"); if(!box) return;
  const q=anQuery(), need=anCmpPick.filter(id=>!(anCmpSeries[q]||{})[id]);
  if(need.length && !cached){
    const j=await anGet("/api/analytics/compare?"+q+"&ids="+encodeURIComponent(need.join(",")));
    if(j.error){ box.innerHTML='<p class="sub"></p>'; box.firstChild.textContent=j.error; return; }
    anCmpSeries[q]=anCmpSeries[q]||{}; (j.series||[]).forEach(s=>anCmpSeries[q][s.id]=s.days);
  }
  if(!$("anCvChart")) return;
  const got=anCmpPick.filter(id=>(anCmpSeries[q]||{})[id]);
  if(!got.length){ if(anCmpPick.length&&cached) anCmpChart(); return; }
  const r=anCmp.range||{}, days=[];
  for(let d=new Date(r.start+"T00:00:00"), e=new Date(r.end+"T00:00:00"); d<=e; d.setDate(d.getDate()+1)) days.push(new Date(d-d.getTimezoneOffset()*6e4).toISOString().slice(0,10));
  // all time: start at the first day any picked video has numbers
  const first=days.findIndex(day=>got.some(id=>anCmpSeries[q][id][day])), x=days.slice(Math.max(0,first));
  const vid=id=>anCmp.videos.find(v=>v.id===id)||{title:id};
  lineChart(box,{x,fmtX:dayLabel,height:260,series:anCmpPick.map((id,i)=>({id,i})).filter(s=>got.includes(s.id)).map(({id,i})=>({
    name:(vid(id).title||"Untitled").slice(0,40),color:AN_S(i),values:x.map(day=>((anCmpSeries[q][id][day]||{})[anCmpMetric])||0)}))});
}

// ---------- Audience
async function anAudLoad(q){
  $("anAudBox").innerHTML=anWait("Getting who watches...");
  const j=await anGet("/api/analytics/audience?"+q);
  if(q!==anQuery()) return;
  if(j.connected===false){ $("anAudBox").innerHTML=anMsg("smart_display","Connect YouTube to see who watches your videos."); return; }
  if(j.error){ $("anAudBox").innerHTML=anMsg("error",j.error); return; }
  anAud={q,...j};
  const y=(anData&&anData.youtube)||{}, B=[], W=anWord();
  const share=(rows,key)=>{ const t=rows.reduce((a,r)=>a+(r[key]||0),0)||1; return rows.map(r=>({nm:r.label,v:r[key]||0,lab:full(r[key])+" "+(key==="shares"?"shares":"views"),pct:(r[key]||0)/t*100})); };
  const dn=(id,title,sub,rows,key)=>rows.length?card(id,title,sub,donutHTML(share(rows,key)),table(["",key==="shares"?"Shares":"Views","Share"],share(rows,key).map(r=>[r.nm,full(r.v),pct(r.pct)]),[1,2])):"";
  const bars=(id,title,sub,rows,key,lab)=>rows.length?card(id,title,sub,barsHTML(rows.slice(0,10).map(r=>({nm:lab?lab(r):r.label,v:r[key]||0,lab:compact(r[key])}))),table(["",key==="shares"?"Shares":"Views"],rows.map(r=>[lab?lab(r):r.label,full(r[key])]),[1])):"";
  const g1=[dn("anAuDev","Devices","What they watch your "+W[1]+" on",j.devices||[],"views"),
    j.subscribed&&j.subscribed.length?card("anAuSub","Subscribers vs everyone else","Share of views from people subscribed to you",
      donutHTML(share(j.subscribed,"views")),table(["","Views","Watch time"],j.subscribed.map(r=>[r.label,full(r.views),compact((r.minutes||0)/60)+" h"]),[1,2])):"",
    dn("anAuPlay","Where they watch","Where on YouTube (or off it) your "+W[1]+" are played",j.playback||[],"views"),
    (y.genders||[]).length?card("anAuGen","Gender","Share of your channel's viewers",donutHTML(y.genders.map(g=>({nm:GENDER[g.gender]||g.gender,v:g.pct}))),table(["","Viewers"],y.genders.map(g=>[GENDER[g.gender]||g.gender,pct(g.pct)]),[1])):""].filter(Boolean);
  if(g1.length) B.push('<div class="an-grid2">'+g1.join("")+'</div>');
  const g2=[(y.countries||[]).length?bars("anAuCountry","Countries","Top countries by views",y.countries.map(r=>({label:regionName(r.code),views:r.views})),"views"):"",
    bars("anAuCity","Cities","Top cities by views",j.cities||[],"views"),
    (y.ages||[]).length?card("anAuAge","Age","Share of your channel's viewers",barsHTML(y.ages.map(r=>({nm:r.group,v:r.pct,lab:pct(r.pct)}))),table(["Age","Viewers"],y.ages.map(r=>[r.group,pct(r.pct)]),[1])):"",
    bars("anAuOs","Operating systems","",j.os||[],"views")].filter(Boolean);
  if(g2.length) B.push('<div class="an-grid2">'+g2.join("")+'</div>');
  const g3=[(y.traffic||[]).length?(()=>{ const tot=y.traffic.reduce((a,r)=>a+r.views,0)||1; return card("anAuTraffic","How they find you","Share of views by where they came from",barsHTML(y.traffic.slice(0,8).map(r=>({nm:TRAFFIC[r.source]||r.source,v:r.views/tot*100,lab:pct(r.views/tot*100)}))),table(["Source","Views"],y.traffic.map(r=>[TRAFFIC[r.source]||r.source,full(r.views)]),[1])); })():"",
    bars("anAuSearch","What they searched","YouTube searches that led to your "+W[1],j.search||[],"views"),
    bars("anAuShare","Where they share","Shares by app or site",j.sharing||[],"shares",r=>({WHATSAPP:"WhatsApp",FACEBOOK:"Facebook",TWITTER:"X (Twitter)",COPY_PASTE:"Copied the link",EMAIL:"Email",TEXT_MESSAGE:"Text message",OTHER:"Other",REDDIT:"Reddit",INSTAGRAM:"Instagram",TELEGRAM:"Telegram",LINKEDIN:"LinkedIn",DISCORD:"Discord"})[r.key]||String(r.label).replace(/_/g," ").toLowerCase().replace(/^\w/,c=>c.toUpperCase()))].filter(Boolean);
  if(g3.length) B.push('<div class="an-grid2">'+g3.join("")+'</div>');
  $("anAudBox").innerHTML=B.length?B.join(""):anMsg("groups","YouTube doesn't have audience numbers for this period yet. They appear once enough people have watched.");
  wireCards(); wireDonuts($("anAudBox"));
}

// ---------- Instagram account
async function anIgLoad(){
  $("anIgBox").innerHTML=anWait("Getting your Instagram account's numbers...");
  const j=await anGet("/api/analytics/instagram?days="+anIgDays);
  anIg=j;
  if(j.error){ $("anIgBox").innerHTML=anMsg("error",j.error); return; }
  if(!j.connected){ $("anIgBox").innerHTML=anMsg("photo_camera","Connect a professional Instagram account to see its reach, followers and who they are.",'<button type="button" class="ghost" id="anIgC">Connect Instagram</button>');
    $("anIgC").onclick=()=>igSignIn(()=>{ anIg=null; anIgLoad(); }); return; }
  const t=j.totals||{}, B=[];
  const fol=j.follows||{}, rb=j.reach_by||{}, vb=j.views_by||{};
  B.push('<div class="an-plat"><i style="background:var(--c-ig)"></i><h2>Instagram account</h2><span>Last '+j.days+' days</span>'+
    '<div class="an-seg ig-days"><button type="button" data-d="7" aria-pressed="'+(j.days===7)+'">7 days</button><button type="button" data-d="30" aria-pressed="'+(j.days===30)+'">30 days</button></div></div>');
  const tl=(i,l,v)=>v==null?"":tile(i,l,compact(v),"");
  B.push('<div class="an-tiles ig">'+tl("visibility","Views",t.views)+tl("groups","Accounts reached",t.reach)+tl("touch_app","Accounts engaged",t.accounts_engaged)+
    tl("bolt","Interactions",t.total_interactions)+tl("favorite","Likes",t.likes)+tl("chat_bubble","Comments",t.comments)+tl("send","Shares",t.shares)+tl("bookmark","Saves",t.saves)+
    (fol.FOLLOWER!=null?tile("person_add","New followers","+"+compact(fol.FOLLOWER),""):"")+(fol.NON_FOLLOWER!=null?tile("person_remove","Unfollows",compact(fol.NON_FOLLOWER),""):"")+
    tl("link","Profile link taps",t.profile_links_taps)+'</div>');
  if((j.reach_daily||[]).length>1) B.push(card("anIgReach","Accounts reached per day","Unique accounts that saw your posts each day",'<div class="an-viz" id="anIgReachViz"></div>',
    table(["Day","Accounts reached"],j.reach_daily.map(r=>[r.day,full(r.reach)]),[1])));
  const FT={FOLLOWER:"Your followers",NON_FOLLOWER:"Not following you",UNKNOWN:"Unknown"};
  const g1=[];
  const dnr=(id,title,sub,obj)=>{ const rows=Object.entries(obj).map(([k,v])=>({nm:FT[k]||k,v})); return rows.some(r=>r.v>0)?card(id,title,sub,donutHTML(rows),table(["","Accounts"],rows.map(r=>[r.nm,full(r.v)]),[1])):""; };
  g1.push(dnr("anIgRb","Who you reached","Accounts reached: followers vs new people",rb));
  g1.push(dnr("anIgVb","Who watched","Views from followers vs everyone else",vb));
  const online=j.online||{};
  if(Object.keys(online).length){  // Instagram gives hours in UTC: show them in the creator's time
    const off=-new Date().getTimezoneOffset()/60, by=Array(24).fill(0);
    Object.entries(online).forEach(([h,n])=>{ by[((+h+Math.round(off))%24+24)%24]+=n; });
    g1.push(card("anIgOnline","When your followers are online","Followers online at each hour of the day, in your time",hoursHTML(by),table(["Hour","Followers online"],by.map((n,i)=>[String(i).padStart(2,"0")+":00",full(n)]),[1])));
  }
  if(g1.filter(Boolean).length) B.push('<div class="an-grid2">'+g1.filter(Boolean).join("")+'</div>');
  const F=j.followers||{}, E=j.engaged||{}, demo=[];
  const rowsOf=(o,lab)=>Object.entries(o||{}).map(([k,v])=>({label:lab?lab(k):k,v})).sort((a,b)=>b.v-a.v);
  const dbars=(id,title,o,lab)=>{ const rows=rowsOf(o,lab); return rows.length?card(id,title,"",barsHTML(rows.slice(0,8).map(r=>({nm:r.label,v:r.v,lab:compact(r.v)}))),table(["","Followers"],rows.map(r=>[r.label,full(r.v)]),[1])):""; };
  demo.push(dbars("anIgCountry","Followers by country",F.country,c=>regionName(c)));
  demo.push(dbars("anIgCity","Followers by city",F.city));
  demo.push(dbars("anIgAge","Followers by age",F.age));
  const gen=rowsOf(F.gender,k=>({F:"Women",M:"Men",U:"Other"})[k]||k);
  if(gen.length) demo.push(card("anIgGen","Followers by gender","",donutHTML(gen.map(r=>({nm:r.label,v:r.v}))),table(["","Followers"],gen.map(r=>[r.label,full(r.v)]),[1])));
  const d2=demo.filter(Boolean);
  B.push('<h3 class="an-sub">Who your followers are</h3>'+(d2.length?'<div class="an-grid2">'+d2.join("")+'</div>':
    anMsg("groups","Instagram shares who your followers are (country, city, age, gender) once the account has at least 100 followers.")));
  const ec=rowsOf(E.country,c=>regionName(c));
  if(ec.length) B.push(card("anIgEng","Who engages","Countries of the accounts that liked, commented, shared or saved this month",barsHTML(ec.slice(0,8).map(r=>({nm:r.label,v:r.v,lab:compact(r.v)}))),table(["Country","Accounts"],ec.map(r=>[r.label,full(r.v)]),[1])));
  B.push('<p class="sub">From Instagram\'s account insights. Instagram keeps these for 90 days and gives at most 30 days at a time. Your Reels, one by one, are on the Overview tab.</p>');
  $("anIgBox").innerHTML=B.join("");
  wireCards(); wireDonuts($("anIgBox"));
  $("anIgBox").querySelectorAll(".ig-days button").forEach(b=>b.onclick=()=>{ anIgDays=+b.dataset.d; anIg=null; anIgLoad(); });
  if($("anIgReachViz")) lineChart($("anIgReachViz"),{x:j.reach_daily.map(r=>r.day),fmtX:dayLabel,height:220,series:[{name:"Accounts reached",color:"var(--c-ig)",values:j.reach_daily.map(r=>r.reach)}]});
}

// Refresh reloads every tab; a new range or content drops what the tabs had.
$("anRefresh").addEventListener("click",()=>{ anCmp=null; anAud=null; anIg=null; anCmpSeries={}; anWeekAt=0; $("anVlogs").dataset.q=""; });
anTabShown();
