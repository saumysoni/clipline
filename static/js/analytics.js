// Analytics page: how the creator's videos are doing on YouTube and Instagram. Four tabs: Overview (this file:
// Pit Crew's read, the paired numbers, one chart, what to try next), Videos (analytics-videos.js), Audience
// (analytics-audience.js) and Grow (analytics-grow.js). The Both / YouTube / Instagram switch (anPlat) applies to
// every tab. Charts are plain SVG drawn here (lineChart): one axis, a crosshair tooltip, keyboard arrows, and a
// Table button on every chart so no number needs hovering to read.
let anDays=0, anData=null, anLoading=false, anContent="shorts", anStart="", anEnd="", anPlat="", anTab="overview", anVlog="";
let anIgAcct=null, anRead=null;  // Instagram account numbers for the range (anIgAcct.q), Pit Crew's read (one per day for the whole page)
// The range and content the page asks for: ?days=28 (or ?start=&end= for Custom) and ?content=shorts|videos|all.
const anQuery=()=>"content="+anContent+(anStart&&anEnd?"&start="+anStart+"&end="+anEnd:"&days="+anDays);
// Words for what's shown: Shorts, videos, or both.
const anWord=()=>({shorts:["Short","Shorts"],videos:["video","videos"],all:["video","videos"]})[anContent];
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
// Series colours (css/analytics-pro.css --s1..--s8, validated): fixed order, and a video keeps its colour while ticked.
const AN_S=n=>"var(--s"+(n+1)+")";
const AN_YT="var(--c-yt)", AN_IG="var(--c-ig)";
const anShowYt=()=>anPlat!=="instagram", anShowIg=()=>anPlat!=="youtube";
const anWait=(t,kind)=>anSkel(kind,t);  // loading skeleton shaped like what's coming (analytics-loading.js)
const anMsg=(icon,t,html)=>'<div class="an-card an-mini"><span class="ms" aria-hidden="true">'+icon+'</span><p>'+esc(t)+'</p>'+(html||"")+'</div>';
// The Instagram account's numbers cover the last 7 or 30 days (Instagram gives at most 30 at a time).
// Instagram account numbers for the page's range: the same days or dates when Instagram has them (it keeps 90 days);
// on All time the account numbers are the last 30 days (for who/when), and the Overview's tiles use each Reel's
// lifetime totals instead (anData.instagram), so both apps are "all time".
const anIgQ=()=>anStart?"start="+anStart+"&end="+anEnd:"days="+(anDays||30);
const anIgLifetime=()=>!anStart&&!anDays;
function anIgRangeText(j){
  if(!j) return "";
  if(j.note==="old") return "Instagram keeps only the last 90 days";
  if(j.note==="cut") return "last 90 days only (Instagram keeps 90 days)";
  if(anStart&&j.since) return anRangeText({custom:true,start:j.since,end:j.until});
  return "last "+j.days+" days";
}

// vlog: open on one vlog's clips (its card's Analytics button); platform: "youtube" / "instagram" to start on one.
function openAnalytics(vlog,platform){
  clearInterval(poll); anVlog=typeof vlog==="string"?vlog:"";
  if(platform!==undefined) anSetPlat(platform);
  location.hash="analytics"+(anVlog?"/"+anVlog:""); show(6);
  if(anVlog) anTabPick("videos");
  if(!anData||anData.q!==anQuery()) loadAnalytics(); else anTabLoad();
}
function anSetPlat(p){ anPlat=p||""; $("anPlat").querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.p===anPlat)); }
$("anPlat").querySelectorAll("button").forEach(b=>b.onclick=()=>{ anSetPlat(b.dataset.p); anRepaint(); });
$("analyticsNav").onclick=openAnalytics;
$("anRefresh").onclick=()=>{ anIgAcct=null; anRead=null; if(typeof anForget==="function") anForget(); loadAnalytics(); };
// Time range: "All time" (the default) or "Custom ▾", which opens 7 / 28 / 90 days / a year, or two dates.
function anRangeShow(){  // the two buttons reflect the range in use
  const custom=!!(anStart||anDays);
  $("anAll").setAttribute("aria-pressed",!custom); $("anRangeMore").setAttribute("aria-pressed",custom);
  $("anRangeLbl").textContent=custom?anRangeText({custom:!!anStart,start:anStart,end:anEnd,days:anDays}):"Custom";
  $("anRangePop").querySelectorAll("[data-days]").forEach(b=>b.setAttribute("aria-pressed",!anStart&&+b.dataset.days===anDays));
}
function anRangePop(open){
  $("anRangePop").hidden=!open; $("anRangeMore").setAttribute("aria-expanded",open);
  if(open){
    const iso=d=>new Date(d-d.getTimezoneOffset()*6e4).toISOString().slice(0,10), t=new Date();
    $("anTo").max=$("anFrom").max=iso(t);
    if(!$("anTo").value){ $("anTo").value=anEnd||iso(t); $("anFrom").value=anStart||iso(new Date(Date.now()-27*864e5)); }
    ($("anRangePop").querySelector('[aria-pressed="true"]')||$("anRangePop").querySelector("[data-days]")).focus();
  }
}
function anRangeSet(days,start,end){
  if(anLoading) return;
  anDays=days; anStart=start||""; anEnd=end||""; anRangePop(false); anRangeShow(); loadAnalytics();
}
$("anAll").onclick=()=>anRangeSet(0);
$("anRangeMore").onclick=e=>{ e.stopPropagation(); anRangePop($("anRangePop").hidden); };
$("anRangePop").querySelectorAll("[data-days]").forEach(b=>b.onclick=()=>anRangeSet(+b.dataset.days));
$("anApply").onclick=()=>{
  const f=$("anFrom").value, t=$("anTo").value;
  if(!f||!t){ (f?$("anTo"):$("anFrom")).focus(); return; }
  anRangeSet(0,f<=t?f:t,f<=t?t:f);
};
$("anRangePop").onclick=e=>e.stopPropagation();
document.addEventListener("click",()=>{ if(!$("anRangePop").hidden) anRangePop(false); });
$("anRangePop").addEventListener("keydown",e=>{ if(e.key==="Escape"){ anRangePop(false); $("anRangeMore").focus(); } });
$("anContent").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  if(anLoading) return;
  $("anContent").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));
  anContent=b.dataset.c; loadAnalytics();
});
// Tabs: each loads what it needs the first time it's shown for this range.
const anTabPick=pageTabs("anTabs",t=>{ anTab=t; anTabLoad(); });
function anTabLoad(){
  anTab=["overview","videos","audience","grow"].find(t=>!$(({overview:"anPanOverview",videos:"anPanVideos",audience:"anPanAudience",grow:"anPanGrow"})[t]).hidden)||"overview";
  const sincePosted=anTab==="videos"&&anVidView!=="compare";  // clips on both apps: totals since each went out, the range doesn't apply
  $("anContent").hidden=anTab==="grow"||sincePosted||anPlat==="instagram";
  document.querySelector(".an-range-wrap").hidden=sincePosted; $("anAsof").hidden=sincePosted;
  if(anTab==="overview"){ anIgAcctLoad(); anReadLoad(); }
  if(anTab==="videos" && typeof anVideosLoad==="function") anVideosLoad();
  if(anTab==="audience" && typeof anAudienceLoad==="function") anAudienceLoad();
  if(anTab==="grow" && typeof anGrowLoad==="function") anGrowLoad();
}
// The platform switch changes what's drawn, not what's loaded.
function anRepaint(){
  if(anData) renderAnalytics(anData);
  anTabLoad();
}

// fetch() with a time limit: a request YouTube never answers ends with a message instead of a spinner forever.
async function anFetch(url,ms){
  const c=new AbortController(), t=setTimeout(()=>c.abort(),ms||90000);
  try{ return await fetch(url,{signal:c.signal}); }
  catch(e){ if(e.name==="AbortError") throw new Error("timeout"); throw e; }
  finally{ clearTimeout(t); }
}
const AN_SLOW="YouTube took too long to answer. Try Refresh in a minute.";
// One retry for a dropped connection or a server hiccup; then a message that says which of the two it was.
async function anGet(url,again){
  let r;
  try{ r=await anFetch(url); }
  catch(e){
    if(e.message==="timeout") return {error:AN_SLOW};
    if(!again){ await new Promise(z=>setTimeout(z,1500)); return anGet(url,true); }
    return {error:"Couldn't reach Pit Crew. Check your internet connection, then press Refresh."};
  }
  let j=null; try{ j=await r.json(); }catch(e){}
  if(r.ok&&j) return j;
  if(!j&&!again&&r.status>=500){ await new Promise(z=>setTimeout(z,1500)); return anGet(url,true); }
  console.error("Analytics request failed:",url,r.status);
  return {error:(j&&j.error)||"Pit Crew hit a problem getting these numbers. Press Refresh in a minute."};
}
async function loadAnalytics(){
  anLoading=true;
  if(!$("anBody").children.length||$("anBody").querySelector(".an-skel")) $("anBody").innerHTML=anWait("Getting your numbers...","overview");
  else $("anBody").classList.add("loading");  // numbers already on screen: dim them under a stripe bar until the new ones come
  const q=anQuery();
  const j=await anGet("/api/analytics?"+q);
  anLoading=false; $("anBody").classList.remove("loading");
  if(q!==anQuery()) return;  // the creator changed the range meanwhile: that load will paint
  anData={days:anDays,q,...j};
  renderAnalytics(anData);
  anTabLoad();
}
// Instagram account numbers for the Overview's paired tiles and chart, for the page's range.
async function anIgAcctLoad(){
  const q=anIgQ(), st=(anData&&anData.instagram_state)||{};
  if(!st.signed_in || (anIgAcct&&anIgAcct.q===q)) return;
  anIgAcct={q,loading:true};
  const j=await anGet("/api/analytics/instagram?"+q);
  if(q!==anIgQ()) return;
  anIgAcct={...j,q};
  if(anData) renderAnalytics(anData);
}

// ---------- Overview
function renderAnalytics(j){
  const note=$("anNote"); note.hidden=true;
  const st=j.instagram_state||{}, igOn=!!(st.signed_in&&st.can_post), y=j.youtube, ig=anIgAcct&&!anIgAcct.loading&&!anIgAcct.error&&anIgAcct.connected?anIgAcct:null;
  if(!j.connected && !igOn){
    $("anAsof").textContent=""; $("anRead").innerHTML=""; $("anTry").innerHTML="";
    $("anBody").innerHTML='<div class="an-card an-empty"><span class="ms" aria-hidden="true">insights</span><h2>Connect YouTube or Instagram to see your analytics</h2>'+
      '<p>Views, likes, comments, shares and new followers for every clip, on both apps, side by side.</p>'+
      '<div class="an-connect"><button type="button" class="primary" id="anConnect"><span class="ms" aria-hidden="true">smart_display</span>Connect YouTube</button>'+
      '<button type="button" class="ghost" id="anIgConnect"><span class="ms" aria-hidden="true">photo_camera</span>Connect Instagram</button></div></div>';
    $("anConnect").onclick=()=>signIn(()=>loadAnalytics()); $("anIgConnect").onclick=()=>igSignIn(()=>{ anIgAcct=null; loadAnalytics(); });
    return;
  }
  if(j.error){ note.hidden=false; note.innerHTML='<span class="ms" aria-hidden="true">error</span><span></span>'; note.lastChild.textContent=j.error; }
  const t=(y&&y.totals)||{}, p=(y&&y.previous)||null, ok=!!(y&&y.full);
  $("anLede").textContent=[y&&y.channel&&y.channel.title?y.channel.title+" · "+full(y.channel.subscribers)+" subscribers":"",
    st.signed_in&&st.username?"@"+st.username:""].filter(Boolean).join(" · ")||"YouTube and Instagram, side by side.";
  // All time uses YouTube's live counts (what each video's page shows); a date range can only come from YouTube
  // Analytics, which is ~2 days behind and can count a comment or two differently (seen on a real channel: 1 vs 2)
  $("anAsof").textContent=!y||!y.range?"":anRangeText(y.range)+(anIgLifetime()?" · views, likes and comments are YouTube's live counts":" · from YouTube Analytics, about 2 days behind; a video's own page can show a comment or two more");
  if(y&&!y.full&&y.enable_url){  // the API is off in Google Cloud: reconnecting won't help, enabling it will
    note.hidden=false;
    note.innerHTML='<span class="ms" aria-hidden="true">lock_open</span><span>These are the live counts for the Shorts Pit Crew uploaded. To see views per day, watch time, retention and who watches, '+
      'turn on <b>YouTube Analytics API</b> in Google Cloud (one click: <b>Enable</b>), wait a few minutes, then press Refresh.</span>'+
      '<a class="ghost" id="anEnable" href="'+esc(y.enable_url)+'" target="_blank" rel="noopener">Turn it on<span class="ms" aria-hidden="true">open_in_new</span></a>';
  } else if(y&&!y.full&&(y.notes||[]).includes("unavailable")){
    note.hidden=false;
    note.innerHTML='<span class="ms" aria-hidden="true">info</span><span>YouTube Analytics didn\'t answer this time, so these are the live counts for the Shorts Pit Crew uploaded. Press Refresh in a few minutes for watch time, retention and trends.</span>';
  } else if(y&&!y.full){
    note.hidden=false;
    note.innerHTML='<span class="ms" aria-hidden="true">lock_open</span><span>These are the live counts for the Shorts Pit Crew uploaded. <b>Connect YouTube once more</b> to see watch time, retention, trends, how viewers find you and who they are.</span>'+
      '<button type="button" class="ghost" id="anRecon">Connect again</button>';
    $("anRecon").onclick=()=>signIn(()=>{ anData=null; loadAnalytics(); });
  }
  // Instagram's side: on All time each Reel's lifetime totals (and total followers); otherwise the account's numbers
  // for the same days, labelled whenever they can't match YouTube's range exactly
  const life=anIgLifetime(), lt=(j.instagram&&j.instagram.totals)||null, nReels=lt?lt.reels||0:0;
  const it=life?(lt||{}):(ig&&ig.totals)||{}, fol=(ig&&ig.follows)||{}, followers=((j.instagram||{}).account||{}).followers;
  const igReady=life?!!lt:!!ig;
  const showYt=anShowYt()&&!!y, showIg=anShowIg()&&igOn;
  const igText=life?(nReels>=30?"your latest 30 Reels, all time":"all your Reels, all time"):anIgRangeText(ig);
  const igLate=igReady&&(life?nReels>=30:!!(ig.note||(anStart&&!ig.since)))?'<small class="an-pnote">'+esc(igText)+'</small>':'';
  const d=k=>p&&p[k]!=null&&p[k]>0 ? deltaHTML((t[k]-p[k])/p[k]*100) : "";
  const B=[];
  if(showYt && showIg){
    const pair=(label,yv,iv,yd,inote)=>'<div class="an-card an-pair-tile"><div class="lab">'+esc(label)+'</div><div class="pp">'+
      '<div><span class="pl yt"><i></i>YouTube</span><b>'+esc(yv)+'</b>'+(yd||"")+'</div>'+
      '<div><span class="pl ig"><i></i>Instagram</span><b>'+(iv===anSkelNum?iv:esc(iv))+'</b>'+(inote?'<small class="an-pnote">'+esc(inote)+'</small>':igLate)+'</div></div></div>';
    const igv=k=>igReady&&it[k]!=null?compact(it[k]):(!life&&anIgAcct&&anIgAcct.loading?anSkelNum:"–");
    B.push('<div class="an-pairs4">'+
      pair("Views",compact(t.views),igv("views"),d("views"))+
      pair("Likes",compact(t.likes),igv("likes"),d("likes"))+
      pair("Comments and shares",compact((t.comments||0)+(t.shares||0)),igReady?compact((it.comments||0)+(it.shares||0)):igv("comments"),"")+
      (life?pair("Subscribers gained / followers",t.subs!=null?(t.subs>0?"+":"")+compact(t.subs):"–",followers!=null?compact(followers):"–",d("subs"),"followers in all")
           :pair("New subscribers / followers",t.subs!=null?(t.subs>0?"+":"")+compact(t.subs):"–",ig&&fol.FOLLOWER!=null?"+"+compact(fol.FOLLOWER):igv("x"),d("subs")))+'</div>'+
      (showIg&&igReady?'<p class="sub an-pairs-note">Instagram: '+esc(igText)+'. YouTube: '+esc(anRangeText((y&&y.range)||{days:anDays}).toLowerCase())+(life?". Instagram doesn\'t give follows from before the last 90 days, so the last tile shows your followers in all.":".")+'</p>':''));
  } else if(showYt){
    B.push('<div class="an-tiles">'+
      tile("visibility",({shorts:"Shorts views",videos:"Video views",all:"Views"})[anContent],compact(t.views),d("views"))+
      tile("schedule","Watch time",t.watch_hours!=null?compact(t.watch_hours)+" h":"–",d("watch_hours"))+
      tile("percent","Avg. viewed",t.avg_pct!=null&&ok?pct(t.avg_pct):"–",d("avg_pct"))+
      tile("timer","Avg. view",t.avg_secs!=null&&ok?secs(t.avg_secs):"–",d("avg_secs"))+
      tile("person_add","Subscribers",t.subs!=null?(t.subs>0?"+":"")+compact(t.subs):"–",d("subs"))+
      tile("favorite","Likes",compact(t.likes),d("likes"))+
      tile("chat_bubble","Comments",compact(t.comments),d("comments"))+
      tile("share","Shares",t.shares!=null?compact(t.shares):"–",d("shares"))+'</div>');
  } else if(showIg){
    const tl=(i,l,v)=>tile(i,l,v==null?"–":compact(v),"");
    B.push(igReady?'<div class="an-tiles ig">'+tl("visibility","Views",it.views)+tl("groups","Accounts reached",it.reach)+tl("favorite","Likes",it.likes)+
      tl("chat_bubble","Comments",it.comments)+tl("send","Shares",it.shares)+tl("bookmark","Saves",life?it.saved:it.saves)+
      (life?tl("person_add","Followers",followers):tile("person_add","New followers",fol.FOLLOWER!=null?"+"+compact(fol.FOLLOWER):"–",""))+
      (life?tl("movie","Reels counted",nReels):tl("link","Profile link taps",it.profile_links_taps))+'</div>'+
      '<p class="sub">Instagram, '+esc(igText)+'.'+(!life&&it.reach==null&&ig.days>30?' Accounts reached can\'t be added up over more than 30 days, so it\'s left out.':'')+'</p>':anWait("Getting your Instagram numbers...","igtiles"));
  } else if(anPlat==="instagram"){
    B.push(anMsg("photo_camera","Connect a professional Instagram account to see your Reels here.",'<button type="button" class="ghost" id="anIgConnect">Connect Instagram</button>'));
  } else if(anPlat==="youtube"){
    B.push(anMsg("smart_display","Connect YouTube to see your Shorts here.",'<button type="button" class="ghost" id="anConnect">Connect YouTube</button>'));
  }
  // one chart: YouTube views per day, and Instagram accounts reached per day when both cover the same days
  const daily=(y&&y.daily)||[], igd=(ig&&ig.reach_daily)||[], igBy={};
  igd.forEach(r=>igBy[r.day]=r.reach);
  const withIg=showIg&&igd.length>1&&!life&&!(ig&&ig.note), series=[];
  // All time starts at the channel's first day: skip the empty days before the first view (a week before it stays,
  // so the first rise is visible), like the Compare chart
  let d0=life?Math.max(0,daily.findIndex(r=>r.views>0)-7):0; if(d0<0||daily.length-d0<2) d0=0;
  const dd=daily.slice(d0);
  if(showYt&&dd.length>1) series.push({name:"YouTube views",color:AN_YT,values:dd.map(r=>r.views)});
  let xs=dd.map(r=>r.day);
  if(withIg){ if(!series.length) xs=igd.map(r=>r.day); series.push({name:"Instagram accounts reached",color:AN_IG,values:xs.map(day=>igBy[day]||0)}); }
  if(series.length) B.push(card("anDaily",series.length>1?"YouTube views and Instagram reach per day":series[0].name+" per day",
    (d0?"From a week before your first view. ":"")+(showYt&&dd.length>1?"YouTube is about 2 days behind"+(withIg?"; Instagram is up to date. ":". "):"")+(showIg&&!withIg&&igOn&&showYt?(life?"To see Instagram day by day too, pick dates in the last 90 days under Custom.":"Instagram keeps day-by-day numbers for 90 days."):""),
    '<div class="an-viz" id="anDailyViz"></div>',
    table(["Day"].concat(series.map(s=>s.name)),xs.map((day,i)=>[day].concat(series.map(s=>full(s.values[i])))),series.map((_,i)=>i+1))));
  // the clips on both apps
  B.push('<button type="button" class="an-card an-golink" id="anGoVideos"><b>Your clips on YouTube and Instagram</b><span>Likes, comments, shares and new followers, side by side for every clip</span><span class="go">Open Videos<span class="ms" aria-hidden="true">arrow_forward</span></span></button>');
  $("anBody").innerHTML=B.join("");
  wireCards();
  if($("anConnect")) $("anConnect").onclick=()=>signIn(()=>loadAnalytics());
  if($("anIgConnect")) $("anIgConnect").onclick=()=>igSignIn(()=>{ anIgAcct=null; loadAnalytics(); });
  $("anGoVideos").onclick=()=>{ anTabPick("videos"); anTab="videos"; anTabLoad(); };
  if($("anDailyViz")) lineChart($("anDailyViz"),{x:xs,fmtX:dayLabel,series,height:230});
  anReadPaint();
}

// ---------- Pit Crew's read (AI, from youtube/analytics_coach.py): ONE read per day for the whole page, whatever the
// range or platform (the AI is asked at most once a day per creator). The page picks the headline and tips for the
// platform it shows. While the AI writes (it can take a minute), the rule-based read shows, and the page asks again.
async function anReadLoad(){
  if(anRead&&(anRead.loading||anRead.headline!==undefined)){ anReadPaint(); return; }
  anRead={loading:true}; anReadPaint();
  const j=await anGet("/api/analytics/coach");
  anRead={...j}; anReadPaint();
  anReadPoll(0);
}
function anReadPoll(n){
  if(!anRead||!anRead.pending) return;
  if(n>=20){ anRead.pending=false; anReadPaint(); return; }
  setTimeout(async()=>{
    if(!anRead||$("s6").hidden) return;
    const j=await anGet("/api/analytics/coach");
    if(!j.error){ anRead={...j}; anReadPaint(); }
    anReadPoll(n+1);
  },6000);
}
const AN_PLAT_TAG={youtube:["YouTube","yt"],instagram:["Instagram","ig"],both:["Both apps","both"]};
function anReadPaint(){
  const r=anRead;
  if(!$("anRead")) return;
  if(r&&r.loading){
    $("anRead").innerHTML='<div class="an-read loading"><div class="eyebrow-ai"><span class="ms" aria-hidden="true">auto_awesome</span>Pit Crew\'s read</div><div class="sk-lines" aria-hidden="true"><span class="sk" style="width:92%"></span><span class="sk" style="width:64%"></span></div><p class="sub an-read-wait" role="status">Reading your numbers<span class="sk-dots" aria-hidden="true"><i></i><i></i><i></i></span></p></div>';
    $("anTry").innerHTML=""; return;
  }
  const head=!r||r.error||r.source==="none"?"":(anPlat==="youtube"?r.headline_youtube:anPlat==="instagram"?r.headline_instagram:r.headline)||"";
  if(!head){ $("anRead").innerHTML=""; $("anTry").innerHTML=""; return; }
  $("anRead").innerHTML='<div class="an-read"><div class="eyebrow-ai"><span class="ms" aria-hidden="true">auto_awesome</span>Pit Crew\'s read · today</div>'+
    '<p class="headline"></p>'+(r.pending?'<p class="sub an-read-wait" role="status">Pit Crew is writing a fuller read; it appears here in a moment<span class="sk-dots" aria-hidden="true"><i></i><i></i><i></i></span></p>':
      '<p class="sub an-read-note">Written once a day from all your Shorts and Reels, so it stays the same when you change the dates above.</p>')+'</div>';
  $("anRead").querySelector(".headline").textContent=head;
  const tips=(r.tips||[]).filter(t=>anPlat===""||t.platform==="both"||t.platform===anPlat).slice(0,3);
  $("anTry").innerHTML=tips.length?'<h2 class="an-h2">What to try next</h2><div class="an-tries">'+tips.map(t=>{ const g=AN_PLAT_TAG[t.platform]||AN_PLAT_TAG.both;
    return '<article class="an-card an-try"><span class="tag-plat '+g[1]+'">'+g[0]+'</span><h3></h3><p class="because"></p><p class="try"><b>Try:</b> <span></span></p></article>'; }).join("")+'</div>':"";
  $("anTry").querySelectorAll(".an-try").forEach((el,i)=>{ const t=tips[i]; el.querySelector("h3").textContent=t.title; el.querySelector(".because").textContent=t.because||""; el.querySelector(".try span").textContent=t.try; });
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
// "Last 28 days", "All time" or "Oct 1 – Oct 9, 2026" for a range from the API.
function anRangeText(r){
  if(r.custom){ const f=d=>new Date(d+"T00:00:00").toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}); return f(r.start)+" – "+f(r.end); }
  return r.days===365?"Last year":r.days?"Last "+r.days+" days":"All time";
}
function dayLabel(s){ const d=new Date(s+"T00:00:00"); return d.toLocaleDateString(undefined,{month:"short",day:"numeric"}); }

// ---------- line chart (one axis; series share it)
const tip=document.createElement("div"); tip.className="an-tip"; tip.hidden=true; document.body.appendChild(tip);
// Counts (views, likes...) get whole-number axis steps: 4 steps of at least 1, never 0.25 shown as "0".
function countMax(v){ const m=niceMax(v); return m<40 ? Math.max(1,Math.ceil(m/4))*4 : m; }
function niceMax(v){ if(v<=0) return 1; const p=Math.pow(10,Math.floor(Math.log10(v))), f=v/p; return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*p; }
function lineChart(el,o){
  const W=Math.max(240,el.clientWidth||600), H=o.height||220, bare=!!o.bare;
  const L=bare?2:46, R=bare?6:54, T=bare?6:12, Bm=bare?4:26, n=o.x.length;
  const top=Math.max(...o.series.flatMap(s=>s.values),0)*(o.headroom||1.08);
  const max=o.max || (o.series.every(s=>s.values.every(Number.isInteger)) && !o.fmtY ? countMax(top) : niceMax(top));
  const X=i=>L+(n<2?0:i*(W-L-R)/(n-1)), Y=v=>T+(H-T-Bm)*(1-v/max);
  const fy=o.fmtY||compact, fx=o.fmtX||(v=>v);
  let s='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" tabindex="0" aria-label="'+esc(o.series.map(x=>x.name).join(", "))+' chart">';
  if(!bare){
    s+='<g class="grid">'+[0,1,2,3,4].map(k=>'<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(max*k/4)+'" y2="'+Y(max*k/4)+'"/>').join("")+'</g>';
    s+='<g class="axis">'+[0,1,2,3,4].map(k=>'<text x="'+(L-8)+'" y="'+(Y(max*k/4)+4)+'" text-anchor="end">'+esc(fy(max*k/4))+'</text>').join("");
    const step=Math.max(1,Math.ceil(n/Math.max(2,Math.min(6,Math.floor((W-L-R)/80)))));  // labels at least ~80px apart
    const near=v=>o.x.reduce((b,x,i)=>Math.abs(x-v)<Math.abs(o.x[b]-v)?i:b,0);  // index of the x closest to v
    const ticks=o.xTicks ? [...new Set(o.xTicks.map(near))] : [...Array(n).keys()].filter(i=>i%step===0);
    ticks.forEach(i=>{ s+='<text x="'+X(i)+'" y="'+(H-6)+'" text-anchor="'+(i===0?"start":i===n-1&&o.xTicks?"end":"middle")+'">'+esc(fx(o.xTicks?o.xTicks[ticks.indexOf(i)]:o.x[i]))+'</text>'; });
    s+='</g>';
  }
  if(o.band){ const a=X(o.band.from), b=X(o.band.to);  // a highlighted stretch (e.g. where most viewers leave)
    s+='<rect x="'+a+'" y="'+T+'" width="'+Math.max(2,b-a)+'" height="'+(H-T-Bm)+'" fill="var(--c-down,#F87171)" fill-opacity=".12"/>'+
      '<text x="'+((a+b)/2)+'" y="'+(T+12)+'" text-anchor="middle" style="fill:var(--muted);font-size:11px;font-weight:600">'+esc(o.band.label)+'</text>'; }
  if(o.ref!=null && o.ref<=max){  // a dashed reference line with its meaning
    s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y(o.ref)+'" y2="'+Y(o.ref)+'" stroke="var(--muted)" stroke-dasharray="4 4" stroke-width="1"/>'+
      '<text x="'+(W-R)+'" y="'+(Y(o.ref)-6)+'" text-anchor="end" style="fill:var(--muted);font-size:11px">'+esc(o.refLabel||"")+'</text>'; }
  const ends=[];  // last-value labels, spread apart afterwards so close lines don't print on top of each other
  o.series.forEach(se=>{
    const pts=se.values.map((v,i)=>X(i).toFixed(1)+","+Y(v).toFixed(1)).join(" ");
    s+='<polygon points="'+X(0)+","+Y(0)+" "+pts+" "+X(n-1)+","+Y(0)+'" fill="'+se.color+'" fill-opacity=".1"/>';
    s+='<polyline points="'+pts+'" fill="none" stroke="'+se.color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    const lv=se.values[n-1];
    s+='<circle cx="'+X(n-1)+'" cy="'+Y(lv)+'" r="4" fill="'+se.color+'" stroke="var(--panel)" stroke-width="2"/>';
    if(!bare) ends.push({y:Y(lv)+4,t:fy(lv)});
  });
  ends.sort((a,b)=>a.y-b.y).forEach((e,i)=>{ if(i&&e.y-ends[i-1].y<12) e.y=ends[i-1].y+12; });
  const over=ends.length?Math.max(0,ends[ends.length-1].y-(H-Bm+4)):0;  // keep them above the x axis
  ends.forEach(e=>{ s+='<text x="'+(X(n-1)+8)+'" y="'+(e.y-over).toFixed(1)+'" style="fill:var(--muted);font-size:11px;font-weight:600">'+esc(e.t)+'</text>'; });
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
$("anDetail").addEventListener("close",()=>{ tip.hidden=true; anDOpen=null; });
// The window follows the page's range ("Last 28 days", a custom range...); "Whole life" shows it since it was posted.
let anDOpen=null;
// pair: the clip on both apps (analytics-videos.js), shown on top when the Short is also a Reel.
async function openShortAnalytics(id,channel,whole,pair){
  const allTime=!anStart&&!anEnd&&!anDays;
  whole=allTime||!!whole; anDOpen={id,channel};
  const s=((anData&&anData.youtube&&anData.youtube.shorts)||[]).find(x=>x.id===id)||{id,title:pair&&pair.title};
  const both=pair&&pair.instagram?h=>anPairWindow(pair,h):h=>h;
  $("anDBody").innerHTML=both(shortHead(s))+anSkel("detail","Getting this Short's numbers...");
  if(pair) anPairWindowWire(pair);
  if(!$("anDetail").open) $("anDetail").showModal();
  const q="?"+anQuery()+(whole?"&whole=1":"")+(channel?"&channel="+encodeURIComponent(channel):"");
  let j; try{ j=await (await anFetch("/api/analytics/short/"+encodeURIComponent(id)+q)).json(); }catch(e){ j={error:e.message==="timeout"?AN_SLOW:"Couldn't reach Pit Crew."}; }
  if(!anDOpen||anDOpen.id!==id) return;  // another video was opened meanwhile
  const m0={...s,...(j.short||{})};
  const span=allTime?"":'<div class="an-seg an-dwin" role="group" aria-label="Time range"><button type="button" data-w="0" aria-pressed="'+!whole+'">'+
    esc(anRangeText({custom:!!(anStart&&anEnd),start:anStart,end:anEnd,days:anDays}))+'</button><button type="button" data-w="1" aria-pressed="'+whole+'">Whole life</button></div>';
  const wire=()=>$("anDBody").querySelectorAll(".an-dwin button").forEach(b=>b.onclick=()=>{ if((b.dataset.w==="1")!==whole) openShortAnalytics(id,channel,b.dataset.w==="1",pair); });
  if(j.error){ $("anDBody").innerHTML=both(shortHead(m0))+span+'<p class="err"></p>'; $("anDBody").querySelector(".err").textContent=j.error; wire(); return; }
  if(j.before){ $("anDBody").innerHTML=both(shortHead(m0))+span+'<div class="an-card an-empty"><span class="ms" aria-hidden="true">event_busy</span><p>It was posted after this period, so there are no numbers for it here. Pick <b>Whole life</b> to see how it has done since.</p></div>'; wire(); return; }
  const life=!j.range||j.range.lifetime;
  const m=m0, t=j.totals||{}, B=[both(shortHead(m)),pair&&pair.instagram?'<h3 class="an-sub">On YouTube</h3>':'',span];
  const pick=(k,live)=>t[k]!=null?t[k]:(life?live:0);  // outside "whole life", never fall back to lifetime counts
  B.push('<div class="an-tiles">'+tile("visibility","Views",compact(pick("views",m.views)),"")+tile("percent","Avg. viewed",t.averageViewPercentage!=null?pct(t.averageViewPercentage):"–","")+
    tile("timer","Avg. view",t.averageViewDuration!=null?secs(t.averageViewDuration):"–","")+tile("favorite","Likes",compact(pick("likes",m.likes)),"")+
    tile("chat_bubble","Comments",compact(pick("comments",m.comments)),"")+tile("person_add","Subscribers",t.subscribersGained!=null?"+"+compact(t.subscribersGained):"–","")+'</div>');
  if(!j.full) B.push('<p class="sub">Connect YouTube once more to see this Short\'s retention curve and where its viewers came from.</p>');
  const fd=d=>new Date(d+"T00:00:00").toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"});
  B.push('<p class="sub an-d-note">'+(life?"Since it was posted. Views, likes and comments are live; the rest come from YouTube Analytics, about 2 days behind."
    :esc(fd(j.range.start)+" – "+fd(j.range.end))+". All numbers come from YouTube Analytics, about 2 days behind, so the last 2 days may still be filling in.")+'</p>');
  if(!life&&!(t.views>0)) B.push('<p class="sub">No views in this period yet. Pick <b>Whole life</b> to see everything since it was posted.</p>');
  const ret=j.retention||[], dd=j.daily||[], tr=j.traffic||[], len=m.secs||0;
  const at=p=>len?secs(len*p/100)+" ("+Math.round(p)+"%)":Math.round(p)+"%";  // a point in the Short: its time, and how far in
  const rs=retSummary(ret,len);
  if(rs) B.push(card("anRet","Where viewers stop watching","Of everyone who started this Short, the share still watching at each moment",
    '<div class="ret-stats">'+
      '<div><span>Still watching after 3 s</span><b>'+esc(rs.hook)+'</b><small>the hook</small></div>'+
      '<div><span>Still watching at the end</span><b>'+esc(rs.end)+'</b><small>'+esc(rs.endNote)+'</small></div>'+
      '<div><span>Biggest drop</span><b>'+esc(rs.dropAt)+'</b><small>'+esc(rs.dropNote)+'</small></div>'+
    '</div><p class="ret-say">'+esc(rs.say)+'</p><div class="an-viz" id="anRetViz"></div>'+
    '<p class="sub">Above the dashed line: people replayed that part (Shorts loop).</p>',
    table(["Point in the Short","Still watching"],ret.filter((r,i)=>i%5===0||i===ret.length-1).map(r=>[at(r.at),pct(r.watching)]),[1])));
  if(dd.length>1) B.push(card("anDDaily","Views per day","",'<div class="an-viz" id="anDDailyViz"></div>',table(["Day","Views"],dd.map(r=>[r.day,full(r.views)]),[1])));
  if(tr.length){ const tot=tr.reduce((a,r)=>a+r.views,0)||1;
    B.push(card("anDTraffic","How viewers found it","",barsHTML(tr.slice(0,6).map(r=>({nm:TRAFFIC[r.source]||r.source,v:r.views/tot*100,lab:pct(r.views/tot*100)}))),
      table(["Source","Views"],tr.map(r=>[TRAFFIC[r.source]||r.source,full(r.views)]),[1]))); }
  $("anDBody").innerHTML=B.join(""); wireCards(); wire(); if(pair) anPairWindowWire(pair);
  if($("anRetViz")) lineChart($("anRetViz"),{x:ret.map(r=>r.at),xTicks:[0,50,100],fmtX:v=>len?secs(len*v/100):Math.round(v)+"%",fmtY:v=>Math.round(v)+"%",
    series:[{name:"Still watching",color:"var(--c-yt)",values:ret.map(r=>r.watching)}],height:220,ref:100,
    max:Math.max(100,Math.ceil(Math.max(...ret.map(r=>r.watching))*1.05/25)*25),refLabel:"Everyone who started",
    band:rs?{from:rs.i0,to:rs.i1,label:"Most leave here"}:null});
  if($("anDDailyViz")) lineChart($("anDDailyViz"),{x:dd.map(r=>r.day),fmtX:dayLabel,series:[{name:"Views",color:"var(--c-yt)",values:dd.map(r=>r.views)}],height:180});
}
// The retention curve in plain words: the hook (3 s), the end, where most viewers leave, and how it compares
// with similar Shorts (YouTube's relativeRetentionPerformance: 0.5 is typical for Shorts of that length).
function retSummary(ret,len){
  if(!ret || ret.length<3) return null;
  const n=ret.length, v=ret.map(r=>r.watching), atTime=p=>len?secs(len*p/100):Math.round(p)+"%";
  const idxAt=p=>ret.reduce((b,r,i)=>Math.abs(r.at-p)<Math.abs(ret[b].at-p)?i:b,0);
  const show=x=>x>100?"All (rewatched)":Math.round(x)+"%";
  const hookI=len?idxAt(Math.min(100,300/len)):idxAt(10), hook=v[hookI], end=v[n-1];
  // Where people leave: compare points 10% of the Short apart, on values capped at 100% (a fall from 120% to 100%
  // is replays fading, not people leaving).
  const w=Math.max(1,Math.round(n/10)), c=v.map(x=>Math.min(100,x));
  let i0=0, best=-1;
  for(let i=0;i+w<n;i++){ const d=c[i]-c[i+w]; if(d>best){ best=d; i0=i; } }
  const i1=Math.min(n-1,i0+w);
  const rel=ret.map(r=>r.vs_similar).filter(x=>x!=null), relAvg=rel.length?rel.reduce((a,b)=>a+b,0)/rel.length:null;
  const vs=relAvg==null?"":relAvg>0.6?" Overall it holds viewers better than most Shorts of this length.":relAvg<0.4?" Overall it loses viewers faster than most Shorts of this length.":" Overall it's about typical for Shorts of this length.";
  const early=ret[i0].at<25;
  return {hook:show(hook), end:show(end), endNote:end>100?"people replayed it":"of everyone who started",
    dropAt:atTime(ret[i0].at)+"–"+atTime(ret[i1].at), dropNote:Math.round(best)+" of every 100 viewers leave here",
    say:(early?"Most viewers leave early, around "+atTime(ret[i0].at)+": a faster start or an earlier payoff should keep more of them."
              :"Viewers stay through the start; the biggest drop comes around "+atTime(ret[i0].at)+".")+vs, i0, i1};
}
function shortHead(s){
  return '<div class="an-d-head">'+(s.thumb?'<img src="'+esc(s.thumb)+'" alt="" referrerpolicy="no-referrer">':'')+'<div><h2 id="anDTitle">'+esc(s.title||"Your Short")+'</h2>'+
    '<div class="links"><a href="https://www.youtube.com/watch?v='+esc(s.id)+'" target="_blank" rel="noopener">Watch on YouTube</a>'+
    '<a href="'+esc(studioLink(s.id))+'" target="_blank" rel="noopener">Open in Studio</a></div></div></div>';
}
window.addEventListener("resize",()=>{ if(!$("s6").hidden && anData && anData.youtube){ clearTimeout(window._anRs); window._anRs=setTimeout(()=>renderAnalytics(anData),200); } });
