// Analytics, Videos tab. Two views (anVidView):
// - "clips": each Pit Crew clip on YouTube and Instagram side by side (/api/analytics/pairs, since each clip was
//   posted): four column charts (likes, comments, shares, new subscribers vs new followers), Totals or Per 1,000
//   views, at most 6 clips per chart (Top 6 by views / Newest 6 / one vlog / chosen ones), then every clip in a list
//   (click = the clip's window on both apps), each clip's first week (analytics-clips.js) and vlogs with their Shorts.
// - "compare": any YouTube videos side by side (YouTube Studio's advanced mode): the table with every number and its
//   share of the total, and up to 8 on a day-by-day chart, lined up by calendar date or by days since posting, per
//   day or as a running total. The 3 most-viewed start ticked.
let anVidView="clips", anPairs=null, anPairPick="top", anPairVlog="", anPairChosen=[], anPairRate=false;
let anCmp=null, anCmpPick=[], anCmpSort={k:"views",dir:-1}, anCmpMetric="views", anCmpFind="", anCmpAlign="cal", anCmpCum=false;
let anCmpSeries={};  // query -> video id -> {day: {views, engaged}}
const AN_PAIR_MAX=6, AN_CMP_MAX=8;

// Forget everything the tabs loaded (Refresh, or a vlog filter change).
function anForget(){ anPairs=null; anCmp=null; anCmpSeries={}; acData=null; if(typeof anAudForget==="function") anAudForget(); $("anVlogs").dataset.q=""; }

$("anVidView").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  anVidView=b.dataset.v;
  $("anVidView").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));
  anTabLoad();
});
function anVideosLoad(){
  $("anVidClips").hidden=anVidView!=="clips"; $("anCmpBox").hidden=anVidView!=="compare";
  if(anVidView==="clips"){
    if(!anPairs) anPairsLoad(); else anPairsPaint();
    if(!acData) loadClipStats(); else paintClipStats();
    anVlogsLoad("content=all&days=0");  // this view is "since posted": never the date range
  } else {
    const q=anQuery();
    if(!anCmp||anCmp.q!==q) anCmpLoad(q); else { anCmpPaint(); anCmpChart(true); }
  }
}

// ---------- your clips on both apps
async function anPairsLoad(){
  $("anPairs").innerHTML=anWait("Getting each clip's numbers from YouTube and Instagram...","pairs");
  const j=await anGet("/api/analytics/pairs"+(anVlog?"?vlog="+anVlog:""));
  anPairs=j; if(anVlog){ anPairPick="vlog"; anPairVlog=(j.clips&&j.clips[0]||{}).job||""; }
  anPairsPaint();
}
const anPairViews=c=>((c.youtube||{}).views||0)+((c.instagram||{}).views||0);
function anPairShown(clips){
  if(anPairPick==="newest") return clips.slice(0,AN_PAIR_MAX);  // the API sends newest first
  if(anPairPick==="vlog") return clips.filter(c=>c.job===anPairVlog).slice(0,AN_PAIR_MAX);
  if(anPairPick==="choose") return clips.filter(c=>anPairChosen.includes(c.job+":"+c.idx)).slice(0,AN_PAIR_MAX);
  return [...clips].sort((a,b)=>anPairViews(b)-anPairViews(a)).slice(0,AN_PAIR_MAX);
}
const AN_PAIR_METRICS=[
  ["likes","Likes","likes","likes","A like is a quicker tap on Instagram, so compare each app with itself over time, not with the other."],
  ["comments","Comments","comments","comments","Comments mean the clip started a conversation."],
  ["shares","Shares","shares","shares","Each share puts the clip in front of someone new, so shares travel further than likes."],
  ["follows","New subscribers vs new followers","subs","follows","YouTube says which Short brought a subscriber. Instagram doesn't, so this is your account's new followers in the 2 days after each Reel."]];
function anPairVal(c,plat,key){
  const p=c[plat]; if(!p) return null;
  const v=p[key]; if(v==null) return null;
  return anPairRate ? (p.views?v/p.views*1000:null) : v;
}
const anPairFmt=v=>v==null?"–":anPairRate?(Math.round(v*10)/10).toLocaleString("en"):full(v);
function anPairsPaint(){
  const box=$("anPairs"), j=anPairs;
  if(!j) return;
  if(j.error){ box.innerHTML=anMsg("error",j.error); return; }
  const all=j.clips||[];
  if(!all.length){ box.innerHTML=anMsg("movie","Once Pit Crew posts your clips to YouTube or Instagram, each one shows up here with its numbers on both apps."); return; }
  const shown=anPairShown(all), vlogs=[...new Map(all.map(c=>[c.job,c.vlog])).entries()];
  const plats=[anShowYt()&&"youtube",anShowIg()&&"instagram"].filter(Boolean);
  const seg=(id,opts,cur)=>'<div class="an-seg" id="'+id+'" role="group">'+opts.map(([v,l])=>'<button type="button" data-v="'+v+'" aria-pressed="'+(v===cur)+'">'+esc(l)+'</button>').join("")+'</div>';
  const B=['<div class="an-card an-pair-card"><div class="an-head"><div><h2>YouTube vs Instagram, clip by clip</h2><p class="sub">'+
    (anPairRate?"Per 1,000 views, so a clip with more views doesn't win just by being bigger.":"Totals since each clip was posted. “Per 1,000 views” compares them fairly.")+'</p></div>'+
    seg("anPairRate",[["0","Totals"],["1","Per 1,000 views"]],anPairRate?"1":"0")+'</div>'+
    '<div class="an-pair-pick"><span class="sub">Clips on the charts:</span>'+seg("anPairPick",[["top","Top 6 by views"],["newest","Newest 6"],["vlog","From one vlog"],["choose","Choose clips…"]],anPairPick)+
    (anPairPick==="vlog"?'<select id="anPairVlog" aria-label="Vlog">'+vlogs.map(([id,n])=>'<option value="'+esc(id)+'"'+(id===anPairVlog?" selected":"")+'>'+esc(n)+'</option>').join("")+'</select>':'')+
    '<span class="sub">'+(all.length>AN_PAIR_MAX?"At most 6 clips per chart so the bars stay readable. Every clip is in the list below.":"")+'</span></div>'];
  if(anPairPick==="choose") B.push('<div class="an-pair-choose" role="group" aria-label="Choose up to 6 clips">'+all.map(c=>{ const k=c.job+":"+c.idx, on=anPairChosen.includes(k);
    return '<label><input type="checkbox" data-k="'+esc(k)+'"'+(on?" checked":"")+(!on&&anPairChosen.length>=AN_PAIR_MAX?" disabled":"")+'> '+esc(c.title||"Clip")+'</label>'; }).join("")+'</div>');
  if(!shown.length) B.push('<p class="sub">'+(anPairPick==="choose"?"Tick up to 6 clips above.":"No clips here yet.")+'</p>');
  else {
    B.push('<div class="an-legend-plats">'+plats.map(p=>'<span><i class="'+(p==="youtube"?"yt":"ig")+'"></i>'+(p==="youtube"?"YouTube":"Instagram")+'</span>').join("")+'</div><div class="an-pair-grid">');
    AN_PAIR_METRICS.forEach(([id,title,ykey,ikey,note])=>{
      const val=(c,p)=>anPairVal(c,p,p==="youtube"?ykey:ikey);
      const max=Math.max(1e-9,...shown.flatMap(c=>plats.map(p=>val(c,p)||0)));
      const tot=p=>shown.reduce((a,c)=>a+((c[p]||{})[p==="youtube"?ykey:ikey]||0),0);
      const pending=ikey==="follows"&&shown.some(c=>c.instagram&&c.instagram.follows!=null&&!c.instagram.follows_complete);
      B.push('<div class="an-pair-chart"><div class="an-head"><h3>'+esc(title)+'</h3><span class="sub">'+(anPairRate?"per 1,000 views":plats.map(p=>(p==="youtube"?"YouTube ":"Instagram ")+full(tot(p))).join(" · "))+'</span></div>'+
        '<div class="an-cols" role="img" aria-label="'+esc(title+(anPairRate?" per 1,000 views":"")+": "+shown.map(c=>c.title+": "+plats.map(p=>(p==="youtube"?"YouTube ":"Instagram ")+anPairFmt(val(c,p))).join(", ")).join("; "))+'">'+
        shown.map(c=>'<div class="grp">'+plats.map(p=>{ const v=val(c,p);
          return '<div class="col '+(p==="youtube"?"yt":"ig")+'"><b>'+esc(anPairFmt(v))+'</b><i style="height:'+(v==null?0:Math.max(1.5,v/max*82)).toFixed(1)+'%"></i></div>'; }).join("")+'</div>').join("")+'</div>'+
        '<div class="an-cols-lab">'+shown.map(c=>'<span title="'+esc(c.title)+'">'+esc(c.title||"Clip")+'</span>').join("")+'</div>'+
        '<p class="sub">'+esc(note+(pending?" Clips posted in the last 2 days are still counting.":""))+'</p></div>');
    });
    B.push('</div>');
  }
  B.push('</div>');
  // every clip
  B.push('<div class="an-card"><div class="an-head"><div><h2>All your clips</h2><p class="sub">Click a clip to see it on both apps.</p></div>'+
    '<button type="button" class="ghost sm" id="anPairCmp">Compare any videos</button></div><div class="pc-list" role="list">'+
    '<div class="pc-row head" role="presentation"><span></span><span>Clip</span><span class="n yt">YouTube views</span><span class="n ig">Instagram views</span></div>'+
    all.map((c,i)=>'<button type="button" class="pc-row" role="listitem" data-i="'+i+'">'+
      (c.thumb?'<img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="" loading="lazy">':'<span class="noimg"></span>')+
      '<span class="tt"><b>'+esc(c.title||"Clip")+'</b><small>'+esc(c.vlog)+(c.posted_at?" · "+new Date(c.posted_at).toLocaleDateString(undefined,{month:"short",day:"numeric"}):"")+(c.length?" · "+secs(c.length):"")+'</small></span>'+
      '<span class="n">'+(c.youtube?(c.youtube.views!=null?full(c.youtube.views):"–"):'<small>not on YouTube</small>')+'</span>'+
      '<span class="n">'+(c.instagram?(c.instagram.views!=null?full(c.instagram.views):"–"):'<small>not on Instagram</small>')+'</span></button>').join("")+'</div>'+
    ((j.problems||[]).length?'<p class="sub">'+esc((j.problems.includes("youtube")?"YouTube":"Instagram")+" didn't answer this time; press Refresh in a minute.")+'</p>':'')+'</div>');
  box.innerHTML=B.join("");
  box.querySelectorAll("#anPairRate button").forEach(b=>b.onclick=()=>{ anPairRate=b.dataset.v==="1"; anPairsPaint(); });
  box.querySelectorAll("#anPairPick button").forEach(b=>b.onclick=()=>{ const before=anPairShown(all); anPairPick=b.dataset.v;
    if(anPairPick==="vlog"&&!anPairVlog) anPairVlog=(vlogs[0]||[])[0]||"";
    if(anPairPick==="choose"&&!anPairChosen.length) anPairChosen=before.map(c=>c.job+":"+c.idx);  // start from what was showing
    anPairsPaint(); });
  if($("anPairVlog")) $("anPairVlog").onchange=e=>{ anPairVlog=e.target.value; anPairsPaint(); };
  box.querySelectorAll(".an-pair-choose input").forEach(c=>c.onchange=()=>{ const k=c.dataset.k;
    anPairChosen=c.checked?[...anPairChosen,k].slice(0,AN_PAIR_MAX):anPairChosen.filter(x=>x!==k); anPairsPaint(); });
  box.querySelectorAll(".pc-row[data-i]").forEach(b=>b.onclick=()=>openClipAnalytics(all[+b.dataset.i]));
  $("anPairCmp").onclick=()=>$("anVidView").querySelector('[data-v="compare"]').click();
}
// A clip's window: on YouTube (with its retention curve) and Instagram side by side; Instagram only when it's only there.
function openClipAnalytics(c){
  if(c.youtube) return openShortAnalytics(c.youtube.video_id,c.youtube.channel,true,c);
  $("anDBody").innerHTML=anPairWindow(c,"");
  if(!$("anDetail").open) $("anDetail").showModal();
  anPairWindowWire(c);
}
// The both-apps part of a clip's window (also put on top of a YouTube Short's window when the clip is a Reel too).
function anPairWindow(c,ytHead){
  const y=c.youtube||{}, i=c.instagram||{};
  const head=ytHead||('<div class="an-d-head">'+(c.thumb?'<img src="/media/'+esc(c.job)+'/'+esc(c.thumb)+'" alt="">':'')+'<div><h2 id="anDTitle">'+esc(c.title||"Your clip")+'</h2>'+
    '<div class="links">'+(i.permalink?'<a href="'+esc(i.permalink)+'" target="_blank" rel="noopener">Open on Instagram</a>':'')+'</div></div></div>');
  if(!c.instagram||!c.youtube) return head+(c.instagram?anIgCard(i):"");
  const ratio=y.views&&i.views?i.views/y.views:null;
  const verdict=ratio==null?"":ratio>=1.5?"This clip did better on Instagram: "+(Math.round(ratio*10)/10)+"× the views there.":
    ratio<=1/1.5?"This clip did better on YouTube: "+(Math.round(10/ratio)/10)+"× the views there.":"About the same views on both apps.";
  const m=[["Likes","likes","likes"],["Comments","comments","comments"],["Shares","shares","shares"],["New subscribers vs new followers","subs","follows"]];
  return head+(verdict?'<p class="an-verdict">'+esc(verdict)+'</p>':'')+
    '<div class="an-both"><div class="an-card an-app yt"><div class="pl"><i></i>YouTube Short</div><div class="nums"><div><span>Views</span><b>'+full(y.views)+'</b></div>'+
    '<div><span>Avg. viewed</span><b>'+(y.avg_pct!=null?pct(y.avg_pct):"–")+'</b></div><div><span>Avg. watched</span><b>'+(y.avg_secs!=null?secs(y.avg_secs):"–")+'</b></div></div></div>'+anIgCard(i)+'</div>'+
    '<div class="an-head"><h3>Side by side</h3><div class="an-seg" id="anWinRate" role="group"><button type="button" data-v="0" aria-pressed="true">Totals</button><button type="button" data-v="1" aria-pressed="false">Per 1,000 views</button></div></div>'+
    '<div class="an-pair-grid win" id="anWinPairs">'+anWinPairs(c,m,false)+'</div>';
}
function anIgCard(i){
  return '<div class="an-card an-app ig"><div class="pl"><i></i>Instagram Reel</div><div class="nums"><div><span>Views</span><b>'+(i.views!=null?full(i.views):"–")+'</b></div>'+
    '<div><span>Avg. watched</span><b>'+(i.avg_watch_s?secs(i.avg_watch_s):"–")+'</b></div><div><span>Saves</span><b>'+(i.saved!=null?full(i.saved):"–")+'</b></div></div></div>';
}
function anWinPairs(c,m,rate){
  return m.map(([title,yk,ik])=>{
    const v=(p,k)=>{ const o=c[p]||{}; if(o[k]==null) return null; return rate?(o.views?o[k]/o.views*1000:null):o[k]; };
    const a=v("youtube",yk), b=v("instagram",ik), mx=Math.max(a||0,b||0,1e-9), f=x=>x==null?"–":rate?(Math.round(x*10)/10).toLocaleString("en"):full(x);
    return '<div class="an-pair-chart sm"><h3>'+esc(title)+'</h3><div class="an-cols" role="img" aria-label="'+esc(title+": YouTube "+f(a)+", Instagram "+f(b))+'"><div class="grp">'+
      '<div class="col yt"><b>'+f(a)+'</b><i style="height:'+(a==null?0:Math.max(1.5,a/mx*80)).toFixed(1)+'%"></i></div><div class="col ig"><b>'+f(b)+'</b><i style="height:'+(b==null?0:Math.max(1.5,b/mx*80)).toFixed(1)+'%"></i></div></div></div>'+
      '<div class="an-cols-lab two"><span>YouTube</span><span>Instagram</span></div>'+
      (ik==="follows"?'<p class="sub">Instagram: your account\'s new followers in the 2 days after this Reel'+(c.instagram&&!c.instagram.follows_complete?" (still counting)":"")+'.</p>':'')+'</div>';
  }).join("");
}
function anPairWindowWire(c){
  const m=[["Likes","likes","likes"],["Comments","comments","comments"],["Shares","shares","shares"],["New subscribers vs new followers","subs","follows"]];
  $("anDBody").querySelectorAll("#anWinRate button").forEach(b=>b.onclick=()=>{
    $("anDBody").querySelectorAll("#anWinRate button").forEach(x=>x.setAttribute("aria-pressed",x===b));
    $("anWinPairs").innerHTML=anWinPairs(c,m,b.dataset.v==="1"); });
}

// ---------- vlogs and their Shorts
async function anVlogsLoad(q){
  if($("anVlogs").dataset.q===q) return;
  $("anVlogs").dataset.q=q;
  const j=await anGet("/api/analytics/vlogs?"+q);
  if($("anVlogs").dataset.q!==q) return;
  const items=(j.items||[]);
  if(!items.length||!anShowYt()){ $("anVlogs").innerHTML=""; return; }
  $("anVlogs").innerHTML=card("anVl","Vlogs and their Shorts","How each vlog did next to the Shorts made from it, and how many viewers the Shorts sent to it · since each was posted",
    '<div class="vl-links">'+items.map(v=>'<div class="vl-link">'+(v.thumb?'<img src="'+esc(v.thumb)+'" alt="" referrerpolicy="no-referrer" loading="lazy">':'<span class="noimg"></span>')+
      '<div class="vl-t"><b>'+esc(v.title||"Your vlog")+'</b><small>'+v.shorts+' Short'+(v.shorts===1?"":"s")+' posted</small></div>'+
      '<div class="vl-n"><span>Vlog views</span><b>'+compact(v.views)+'</b></div>'+
      '<div class="vl-n"><span>Its Shorts\' views</span><b>'+compact(v.shorts_views)+'</b></div>'+
      '<div class="vl-n hi"><span>Viewers sent by the Shorts</span><b>'+compact(v.sent)+'</b><small>'+(v.views?pct(v.sent/v.views*100)+" of the vlog's views":"")+'</small></div>'+
      (!v.views&&v.shorts_views?'<p class="vl-hint"><span class="ms" aria-hidden="true">info</span>No views on the vlog yet. If it\'s still private (YouTube keeps uploads from new apps private until Google\'s review), make it public in YouTube Studio so the Shorts can send people to it.</p>':'')+'</div>').join("")+'</div>'+
    '<p class="sub">"Sent by the Shorts" counts views that came from the related-video link on a Short. YouTube Analytics, about 2 days behind.</p>',
    table(["Vlog","Vlog views","Shorts","Shorts' views","Sent by Shorts"],items.map(v=>[v.title,full(v.views),full(v.shorts),full(v.shorts_views),full(v.sent)]),[1,2,3,4]));
  wireCards();
}

// ---------- Compare any videos (YouTube Studio's advanced mode)
const CMP_COLS=[["views","Views"],["engaged","Engaged views"],["likes","Likes"],["comments","Comments"],["shares","Shares"],["subs","Subscribers"],["minutes","Watch time"],["avg_secs","Avg. view"],["avg_pct","Avg. % viewed"]];
const CMP_SHARE=new Set(["views","engaged","likes","comments","shares","subs","minutes"]);  // a share of the total makes sense
async function anCmpLoad(q){
  $("anCmpBox").innerHTML=anWait("Getting every "+anWord()[0]+"'s numbers...","compare");
  const j=await anGet("/api/analytics/videos?"+q);
  if(q!==anQuery()) return;
  if(j.connected===false){ $("anCmpBox").innerHTML=anMsg("smart_display","Connect YouTube to compare your videos."); return; }
  if(j.error){ $("anCmpBox").innerHTML=anMsg("error",j.error); return; }
  anCmp={q,...j};
  const ids=new Set(anCmp.videos.map(v=>v.id));
  anCmpPick=anCmpPick.filter(id=>ids.has(id));
  if(!anCmpPick.length) anCmpPick=[...anCmp.videos].sort((a,b)=>(b.views||0)-(a.views||0)).slice(0,3).map(v=>v.id);  // the 3 most viewed to start
  anCmpPaint(); anCmpChart();
}
function anCmpVal(v,k){
  const x=v[k];
  if(x==null) return "–";
  return k==="minutes"?compact(x/60)+" h":k==="avg_secs"?secs(x):k==="avg_pct"?pct(x):full(x);
}
const anCmpDay=v=>v.published?new Date(v.published).toISOString().slice(0,10):null;
function anCmpPaint(){
  const d=anCmp, W=anWord(), tot=d.total||{};
  const cols=CMP_COLS.filter(([k])=>k!=="engaged"||tot.engaged!=null);
  let vids=d.videos.slice();
  if(anCmpFind) vids=vids.filter(v=>(v.title||"").toLowerCase().includes(anCmpFind));
  vids.sort((a,b)=>{ const k=anCmpSort.k, x=k==="title"?(a.title||""):(a[k]||0), y=k==="title"?(b.title||""):(b[k]||0); return (x>y?1:x<y?-1:0)*anCmpSort.dir; });
  const th=(k,lab,num)=>'<th'+(num?' class="n"':'')+' aria-sort="'+(anCmpSort.k===k?(anCmpSort.dir>0?"ascending":"descending"):"none")+'"><button type="button" data-k="'+k+'">'+esc(lab)+(anCmpSort.k===k?'<span class="ms" aria-hidden="true">'+(anCmpSort.dir>0?"arrow_upward":"arrow_downward")+'</span>':'')+'</button></th>';
  const cell=(v,k)=>'<td class="n"><b>'+esc(anCmpVal(v,k))+'</b>'+(CMP_SHARE.has(k)&&tot[k]&&v[k]!=null?'<small>'+pct(v[k]/tot[k]*100)+'</small>':'')+'</td>';
  const rows=vids.map(v=>{ const at=anCmpPick.indexOf(v.id), on=at>=0;
    return '<tr class="'+(on?"on":"")+'"><td class="ck"><label class="cmp-ck" style="--k:'+(on?AN_S(at):"transparent")+'"><input type="checkbox" data-id="'+esc(v.id)+'"'+(on?" checked":"")+(anCmpPick.length>=AN_CMP_MAX&&!on?" disabled":"")+' aria-label="Show '+esc(v.title||"this video")+' on the chart"></label></td>'+
      '<td class="vt"><button type="button" class="cmp-v" data-id="'+esc(v.id)+'">'+(v.thumb?'<img src="'+esc(v.thumb)+'" alt="" referrerpolicy="no-referrer" loading="lazy">':'<span class="noimg"></span>')+
      '<span><b>'+esc(v.title||"Untitled")+(v.clipline?'<span class="tag clip">Pit Crew</span>':'')+'</b><small>'+(v.published?new Date(v.published).toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}):"")+(v.secs?" · "+secs(v.secs):"")+'</small></span></button></td>'+
      cols.map(([k])=>cell(v,k)).join("")+'</tr>'; }).join("");
  // Total = the channel's (same as the Overview); "Other" = views on videos deleted, made private or not listed since.
  const total='<tr class="tot"><td></td><td class="vt"><b>Total</b><small>'+d.videos.length+' '+(d.videos.length===1?W[0]:W[1])+(d.other?' + other':'')+'</small></td>'+cols.map(([k])=>'<td class="n"><b>'+esc(CMP_SHARE.has(k)?anCmpVal(tot,k):"")+'</b></td>').join("")+'</tr>'+
    (d.other&&!anCmpFind?'<tr class="oth"><td></td><td class="vt"><b>Other '+W[1]+'</b><small>Deleted, private or no longer listed</small></td>'+cols.map(([k])=>CMP_SHARE.has(k)?cell(d.other,k):'<td></td>').join("")+'</tr>':'');
  const seg=(id,opts,cur)=>'<div class="an-seg" id="'+id+'" role="group">'+opts.map(([v,l])=>'<button type="button" data-v="'+v+'" aria-pressed="'+(v===cur)+'">'+esc(l)+'</button>').join("")+'</div>';
  $("anCmpBox").innerHTML=
    '<div class="an-card"><div class="an-head"><div><h2>'+(anCmpCum?"Total views so far":"Views per day")+' <span class="cmp-n">'+anCmpPick.length+' of 8 on the chart</span></h2><p class="sub">The 3 most-viewed start ticked; tick up to 8 below. <span id="anCmpSpan">'+anRangeText(d.range?{...d.range,custom:true}:{})+'</span>.</p></div>'+
    '<a class="ghost sm" id="anCsv" href="/api/analytics/videos.csv?'+anQuery()+'" download><span class="ms" aria-hidden="true">download</span>Download CSV</a></div>'+
    '<div class="cmp-bar">'+seg("anCmpAlign",[["cal","Calendar date"],["age","Days since posting"]],anCmpAlign)+seg("anCmpCum",[["0","Per day"],["1","Running total"]],anCmpCum?"1":"0")+
    (tot.engaged!=null?seg("anCmpMetric",[["views","Views"],["engaged","Engaged views"]],anCmpMetric):'')+
    (anCmpPick.length?'<button type="button" class="linkbtn" id="anCmpClear">Clear</button>':'')+'</div>'+
    '<div id="anCmpFar"></div><div class="an-viz" id="anCvChart">'+(anCmpPick.length?anSkel("chart","Getting each day's numbers..."):'<p class="sub">Tick '+W[1]+' below to see them here.</p>')+'</div>'+
    '<p class="sub">'+(anCmpAlign==="age"?"Day 1 is each video's posting day, so videos posted far apart start at the same point.":"YouTube's days run on US Pacific time.")+' Point at the chart for every video\'s number that day.</p></div>'+
    '<div class="an-card cmp-card"><div class="cmp-tools"><input type="search" id="anCmpFind" placeholder="Find a '+W[0]+' by title" value="'+esc(anCmpFind)+'" aria-label="Find a video"></div>'+
    (d.videos.length?'<div class="cmp-wrap"><table class="cmp"><thead><tr><th class="ck"></th>'+th("title",W[0][0].toUpperCase()+W[0].slice(1))+cols.map(([k,l])=>th(k,l,true)).join("")+'</tr></thead><tbody>'+total+rows+'</tbody></table></div>'
      :'<p class="sub">No '+W[1]+' with views in this period.</p>')+'</div>';
  $("anCmpBox").querySelectorAll(".cmp th button").forEach(b=>b.onclick=()=>{ const k=b.dataset.k; anCmpSort={k,dir:anCmpSort.k===k?-anCmpSort.dir:(k==="title"?1:-1)}; anCmpPaint(); anCmpChart(true); });
  $("anCmpBox").querySelectorAll(".cmp input[type=checkbox]").forEach(c=>c.onchange=()=>{
    const id=c.dataset.id; if(c.checked){ if(anCmpPick.length<AN_CMP_MAX) anCmpPick.push(id); } else anCmpPick=anCmpPick.filter(x=>x!==id);
    anCmpPaint(); anCmpChart(); });
  $("anCmpBox").querySelectorAll(".cmp-v").forEach(b=>b.onclick=()=>openShortAnalytics(b.dataset.id));
  $("anCmpBox").querySelectorAll("#anCmpMetric button").forEach(b=>b.onclick=()=>{ anCmpMetric=b.dataset.v; anCmpPaint(); anCmpChart(true); });
  $("anCmpBox").querySelectorAll("#anCmpAlign button").forEach(b=>b.onclick=()=>{ anCmpAlign=b.dataset.v; anCmpPaint(); anCmpChart(); });
  $("anCmpBox").querySelectorAll("#anCmpCum button").forEach(b=>b.onclick=()=>{ anCmpCum=b.dataset.v==="1"; anCmpPaint(); anCmpChart(true); });
  if($("anCmpClear")) $("anCmpClear").onclick=()=>{ anCmpPick=[]; anCmpPaint(); anCmpChart(); };
  const f=$("anCmpFind"); f.oninput=()=>{ anCmpFind=f.value.trim().toLowerCase(); const at=f.selectionStart; anCmpPaint(); anCmpChart(true); const g=$("anCmpFind"); g.focus(); g.setSelectionRange(at,at); };
}
// The chart's numbers: the page's range on a calendar, or (days since posting) each video from the day it went up.
function anCmpChartQuery(){
  if(anCmpAlign!=="age") return anQuery();
  const vids=anCmp.videos.filter(v=>anCmpPick.includes(v.id)&&anCmpDay(v)), first=vids.map(anCmpDay).sort()[0];
  const today=new Date(Date.now()-new Date().getTimezoneOffset()*6e4).toISOString().slice(0,10);
  return "content="+anContent+(first?"&start="+first+"&end="+today:"&days=0");
}
async function anCmpChart(cached){
  const box=$("anCvChart"); if(!box) return;
  const q=anCmpChartQuery(), need=anCmpPick.filter(id=>!(anCmpSeries[q]||{})[id]);
  if(need.length && !cached){
    const j=await anGet("/api/analytics/compare?"+q+"&ids="+encodeURIComponent(need.join(",")));
    if(j.error){ box.innerHTML='<p class="sub"></p>'; box.firstChild.textContent=j.error; return; }
    anCmpSeries[q]=anCmpSeries[q]||{}; (j.series||[]).forEach(s=>anCmpSeries[q][s.id]=s.days);
  }
  if(!$("anCvChart")||q!==anCmpChartQuery()) return;
  const got=anCmpPick.filter(id=>(anCmpSeries[q]||{})[id]);
  if(!got.length){ if(anCmpPick.length&&cached) anCmpChart(); else box.innerHTML='<p class="sub">Tick '+anWord()[1]+' below to see them here.</p>'; return; }
  const vid=id=>anCmp.videos.find(v=>v.id===id)||{title:id};
  const val=(id,day)=>((anCmpSeries[q][id][day]||{})[anCmpMetric])||0;
  const iso=d=>new Date(d-d.getTimezoneOffset()*6e4).toISOString().slice(0,10);
  const run=a=>{ let s=0; return a.map(v=>s+=v); };
  let x, series;
  const picked=anCmpPick.map((id,i)=>({id,i})).filter(s=>got.includes(s.id));
  if(anCmpAlign==="age"){  // day 1 = each video's posting day
    const starts={}; picked.forEach(({id})=>{ const v=vid(id), days=Object.keys(anCmpSeries[q][id]).sort(); starts[id]=anCmpDay(v)||days[0]; });
    const today=iso(new Date()), len=Math.max(2,...picked.map(({id})=>Math.round((new Date(today)-new Date(starts[id]))/864e5)+1));
    const n=Math.min(len,365); x=[...Array(n).keys()].map(i=>i+1);
    series=picked.map(({id,i})=>{ const d0=new Date(starts[id]+"T00:00:00");
      const vals=x.map(k=>{ const d=new Date(d0); d.setDate(d.getDate()+k-1); return val(id,iso(d)); }); return {id,i,vals}; });
  } else {
    const r=anCmp.range||{}, days=[];
    for(let d=new Date(r.start+"T00:00:00"), e=new Date(r.end+"T00:00:00"); d<=e; d.setDate(d.getDate()+1)) days.push(iso(d));
    // from the day the earliest ticked video went up (YouTube lists zero-view days too, so "first row" would be the
    // range start, e.g. the channel's first day on All time) to the last day YouTube has numbers for
    const pub=picked.map(({id})=>anCmpDay(vid(id))).filter(Boolean).sort()[0];
    let a=pub?days.findIndex(day=>day>=pub):days.findIndex(day=>got.some(id=>val(id,day)>0));
    let b=days.length-1; while(b>0&&!got.some(id=>anCmpSeries[q][id][days[b]])) b--;
    if(a<0) a=0; if(b<a) b=days.length-1;
    x=days.slice(a,b+1); if(x.length<2) x=days.slice(Math.max(0,a-1),b+2);
    series=picked.map(({id,i})=>({id,i,vals:x.map(day=>val(id,day))}));
  }
  if($("anCmpSpan")) $("anCmpSpan").textContent=anCmpAlign==="age"?"Day 1 is the day each video went up":
    "Shown: "+anRangeText({custom:true,start:x[0],end:x[x.length-1]})+", from the day the earliest ticked video went up";
  series.forEach(s=>{ if(anCmpCum) s.vals=run(s.vals); const top=Math.max(...s.vals);
    s.note=anCmpCum?full(s.vals[s.vals.length-1])+" total":full(top)+" peak"; });
  // videos posted far apart sit at opposite ends of a calendar: offer to line them up
  const pubs=picked.map(({id})=>anCmpDay(vid(id))).filter(Boolean).sort(), spread=pubs.length>1?(new Date(pubs[pubs.length-1])-new Date(pubs[0]))/864e5:0;
  $("anCmpFar").innerHTML=anCmpAlign==="cal"&&spread>60?'<div class="an-far"><span>These videos went up about '+Math.round(spread/30)+' months apart, so on a calendar their lines sit at opposite ends.</span><button type="button" class="ghost sm" id="anCmpLineUp">Line them up by days since posting</button></div>':"";
  if($("anCmpLineUp")) $("anCmpLineUp").onclick=()=>{ anCmpAlign="age"; anCmpPaint(); anCmpChart(); };
  lineChart(box,{x,fmtX:anCmpAlign==="age"?(k=>"Day "+k):dayLabel,height:280,series:series.map(s=>({name:(vid(s.id).title||"Untitled").slice(0,40)+" · "+s.note,color:AN_S(s.i),values:s.vals}))});
}
