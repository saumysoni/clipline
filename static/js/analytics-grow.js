// Analytics, Grow tab: when to post next, and what the creator's own numbers are teaching them.
// - When to post: the evenings (7–11 pm) of the countries most YouTube viewers watch from, and the hours the
//   Instagram followers are online (Instagram gives them hour by hour; YouTube doesn't), shown on the creator's own
//   clock, plus 3 suggested times for the next 3 clips, 2 days apart, so Pit Crew can later tell which works best.
// - Lessons: plain-English lessons, each built from one of the creator's numbers and shown only when the numbers
//   are there. "Got it" is remembered on this device.
const AN_ZONES={US:[["US East Coast","America/New_York"],["US West Coast","America/Los_Angeles"]],IN:[["India","Asia/Kolkata"]],GB:[["UK","Europe/London"]],
  CA:[["Canada (east)","America/Toronto"]],AU:[["Australia (east)","Australia/Sydney"]],DE:[["Germany","Europe/Berlin"]],FR:[["France","Europe/Paris"]],
  AE:[["UAE","Asia/Dubai"]],PK:[["Pakistan","Asia/Karachi"]],BD:[["Bangladesh","Asia/Dhaka"]],NP:[["Nepal","Asia/Kathmandu"]],ID:[["Indonesia","Asia/Jakarta"]],
  PH:[["Philippines","Asia/Manila"]],SG:[["Singapore","Asia/Singapore"]],MY:[["Malaysia","Asia/Kuala_Lumpur"]],BR:[["Brazil","America/Sao_Paulo"]],
  MX:[["Mexico","America/Mexico_City"]],NG:[["Nigeria","Africa/Lagos"]],ZA:[["South Africa","Africa/Johannesburg"]],NZ:[["New Zealand","Pacific/Auckland"]],
  IE:[["Ireland","Europe/Dublin"]],NL:[["Netherlands","Europe/Amsterdam"]],ES:[["Spain","Europe/Madrid"]],IT:[["Italy","Europe/Rome"]],JP:[["Japan","Asia/Tokyo"]],
  KR:[["South Korea","Asia/Seoul"]],SA:[["Saudi Arabia","Asia/Riyadh"]],LK:[["Sri Lanka","Asia/Colombo"]],KE:[["Kenya","Africa/Nairobi"]],TR:[["Turkey","Europe/Istanbul"]]};
// Minutes to add to a time in `zone` to get the creator's own clock (today, so summer time is right).
function anZoneShift(zone){
  try{
    const now=new Date(), part=(tz)=>{ const p=new Intl.DateTimeFormat("en-US",{timeZone:tz,hour12:false,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).formatToParts(now);
      const g=t=>+p.find(x=>x.type===t).value; return Date.UTC(g("year"),g("month")-1,g("day"),g("hour")%24,g("minute")); };
    return Math.round((part(Intl.DateTimeFormat().resolvedOptions().timeZone)-part(zone))/6e4);
  }catch(e){ return null; }
}
const anClock=m=>{ m=((m%1440)+1440)%1440; const d=new Date(); d.setHours(Math.floor(m/60),m%60,0,0); return d.toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"}); };
let anLessonsDone={}; try{ anLessonsDone=JSON.parse(localStorage.getItem("pc-an-lessons")||"{}"); }catch(e){}

function anGrowLoad(){
  const st=(anData&&anData.instagram_state)||{};
  if(st.signed_in&&anShowIg()&&!anIgAcct) anIgAcctLoad().then(anGrowPaint);
  if(!anPairs) anGet("/api/analytics/pairs").then(j=>{ anPairs=anPairs||j; anGrowPaint(); });
  anGrowPaint();
}
function anGrowPaint(){
  const box=$("anGrowBox");
  if(!anData){ box.innerHTML=anWait("Getting your numbers...","grow"); return; }
  const y=(anData.youtube&&anData.youtube.full!==false)?anData.youtube:null, ig=anIgAcct&&!anIgAcct.loading&&anIgAcct.connected?anIgAcct:null;
  const B=[];
  // ----- when to post
  // Most people watch in their evening (7–11 pm where they live). For the countries most YouTube views come from, Pit
  // Crew works out when that evening is on the creator's own clock, then suggests 3 posting times, 2 days apart, so
  // the creator can compare the 3 clips' first weeks. One slot per country first (a big country with two time zones,
  // like the US, gets its second zone only if there's room), and the share of views is said once per country.
  const zones=[], t=(y&&y.totals)||{}, myTz=(()=>{ try{ return Intl.DateTimeFormat().resolvedOptions().timeZone; }catch(e){ return ""; } })();
  if(y&&anShowYt()) (y.countries||[]).slice(0,3).forEach(c=>(AN_ZONES[c.code]||[]).forEach(([nm,tz],k)=>zones.push({nm,tz,k,code:c.code,share:t.views?c.views/t.views*100:null})));
  zones.forEach(z=>{ z.shift=anZoneShift(z.tz); });
  const online=ig&&anShowIg()?ig.online||{}:{}, off=-new Date().getTimezoneOffset(), byHour=Array(24).fill(0);
  Object.entries(online).forEach(([h,n])=>{ byHour[((Math.round(+h+off/60))%24+24)%24]+=n; });
  const igPeak=Object.keys(online).length?byHour.indexOf(Math.max(...byHour)):null;
  const ok=zones.filter(z=>z.shift!=null), firsts=ok.filter(z=>z.k===0), extras=ok.filter(z=>z.k>0);
  const who=z=>(/Coast|\(/.test(z.nm)?"on the ":"in ")+z.nm.replace(/^(.*) \((.*)\)$/,"$1, $2");
  const slots=[...firsts,...extras].map(z=>({at:20*60+z.shift,plat:"yt",
    why:"8 PM for your viewers "+who(z),
    note:z.share!=null?(z.k===0?pct(z.share)+" of your YouTube views come from "+regionName(z.code):"also "+regionName(z.code)+", another time zone"):"",
    mine:z.tz===myTz}));
  if(igPeak!=null) slots.splice(Math.min(1,slots.length),0,{at:igPeak*60,plat:"ig",why:"When most of your Instagram followers are online",note:"Instagram tells Pit Crew this hour by hour"});
  const plan=slots.slice(0,3).map((s,i)=>{ const d=new Date(); d.setDate(d.getDate()+1+2*i); d.setHours(0,0,0,0); d.setMinutes(((s.at%1440)+1440)%1440);
    return {...s,day:d.toLocaleDateString(undefined,{weekday:"short",month:"short",day:"numeric"}),time:anClock(s.at)}; });
  if(plan.length){
    B.push('<section class="an-read an-when"><div class="eyebrow-ai"><span class="ms" aria-hidden="true">schedule</span>When to post your next '+plan.length+' clip'+(plan.length>1?'s':'')+'</div>'+
      '<p class="headline">Most people watch in their evening. Your viewers live in different places, so post each clip at one of these times and see which does best.</p>'+
      '<ol class="an-slots">'+plan.map((p,i)=>'<li class="an-slot '+p.plat+'"><span class="n">Clip '+(i+1)+'</span><b>'+esc(p.day)+'</b><b class="t">'+esc(p.time)+' <small>your time</small></b>'+
        '<span>'+esc(p.why)+(p.mine?' (that’s your own evening too)':'')+'</span>'+(p.note?'<small>'+esc(p.note)+'</small>':'')+'</li>').join("")+'</ol>'+
      '<p class="sub">2 days apart, so each clip gets its own first days of views. A week after the third one, compare their first weeks on the Videos tab ("Each clip\'s first week"). Posting at these times from the calendar comes next.</p></section>');
  }
  const g=[];
  if(ok.length) g.push(card("anGrowZones","When it's evening for your viewers","Each bar is 7 to 11 PM where those viewers live, moved onto your clock"+(myTz?" ("+myTz.replace(/_/g," ")+")":"")+". The line is now.",
    '<div class="an-zones">'+ok.map(z=>{ const a=((19*60+z.shift)%1440+1440)%1440, w=240;
      const seg=(s,l)=>'<i style="left:'+(s/1440*100).toFixed(2)+'%;width:'+(l/1440*100).toFixed(2)+'%"></i>';
      return '<span class="nm">'+esc(z.nm)+(z.share!=null&&z.k===0?'<small>'+pct(z.share)+' of views</small>':'')+'</span><span class="tr">'+(a+w>1440?seg(a,1440-a)+seg(0,a+w-1440):seg(a,w))+'</span><span class="v">'+esc(anClock(a)+" – "+anClock(a+w))+'</span>'; }).join("")+
    '<span></span><span class="ticks"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>12 AM</span></span><span></span></div>',
    table(["Viewers in","Share of views","Their 7–11 PM, your time"],ok.map(z=>{ const a=19*60+z.shift; return [z.nm,z.k===0&&z.share!=null?pct(z.share):"",anClock(a)+" – "+anClock(a+240)]; }),[])));
  if(igPeak!=null) g.push(card("anGrowIg","Instagram followers online, by hour","How many of your followers are on Instagram at each hour, on your clock",hoursHTML(byHour),
    table(["Hour (your time)","Followers online"],byHour.map((n,i)=>[anClock(i*60),full(n)]),[1])));
  if(g.length) B.push('<div class="an-grid2">'+g.join("")+'</div>');
  // ----- lessons
  const L=[], tr=(y&&y.traffic)||[], trT=tr.reduce((a,r)=>a+r.views,0), find=k=>(tr.find(r=>r.source===k)||{}).views||0;
  if(y&&t.views){
    if(t.avg_pct) L.push({id:"watch",plat:"youtube",title:"How much of each video people watch",big:pct(t.avg_pct),note:"of each "+anWord()[0]+" is watched, on average",
      what:t.avg_pct>100?"Above 100% means people watch more than once: your "+anWord()[1]+" loop well.":"Most people leave in the first seconds if what the hook promises isn't on screen yet. Open a "+anWord()[0]+" in the window on the Videos tab to see exactly where they leave.",
      try:"show the thing you talk about (the place, the dish) while you say the hook."});
    if(trT) L.push({id:"search",plat:"youtube",title:"Feed views burst, search views last",big:pct(find("YT_SEARCH")/trT*100),note:"of YouTube views came from search ("+pct(find("SHORTS")/trT*100)+" from the Shorts feed)",
      what:"The feed shows a "+anWord()[0]+" for a day or two, then moves on. Search keeps sending people for months, but only to topics people type in.",try:"use the exact name people search for in your title and first line."});
    const daily=(y.daily||[]).map(d=>d.views), dsum=daily.reduce((a,b)=>a+b,0);
    if(daily.length>=7&&dsum){ const top2=[...daily].sort((a,b)=>b-a).slice(0,2).reduce((a,b)=>a+b,0);
      if(top2/dsum>=0.5) L.push({id:"burst",plat:"both",title:"A clip gets about 2 days",big:pct(top2/dsum*100),note:"of these views came on just 2 days",
        what:"Most views arrive right after a clip goes out. Clips posted together share those days instead of each getting their own.",try:"post one clip every 2 days."}); }
    if(t.engaged!=null) L.push({id:"engaged",plat:"youtube",title:"Engaged views: who really watched",big:pct(t.engaged/t.views*100),note:"of views were engaged ("+full(t.engaged)+" of "+full(t.views)+")",
      what:"An engaged view is someone who didn't swipe away in the first seconds. It rises when the opening lands.",try:"judge a new clip by engaged views, not views alone."});
    if(t.subs!=null) L.push({id:"subs",plat:"youtube",title:"Turning viewers into subscribers",big:(t.subs>0?"+":"")+full(t.subs),note:"new subscribers from "+full(t.views)+" views",
      what:t.subs<=0?"People watched, but nothing told them there's more. A clip from a vlog has a built-in reason: the full story.":"Each new subscriber will see your next videos first.",
      try:"end with where the full story is: “The whole trip is on my channel.”"});
  }
  const it=(ig&&ig.totals)||{};
  if(ig&&anShowIg()){
    const rb=ig.reach_by||{}, rbt=Object.values(rb).reduce((a,b)=>a+b,0);
    if(it.shares!=null) L.push({id:"shares",plat:"instagram",title:"Shares carry a Reel to new people",big:full(it.shares),note:"shares, "+anIgRangeText(ig)+(rbt?"; "+pct((rb.NON_FOLLOWER||0)/rbt*100)+" of the accounts you reached don't follow you":""),
      what:"Each share puts a Reel in front of someone who doesn't follow you yet.",try:"end with a question people want to answer, or send to a friend."});
  }
  const both=((anPairs&&anPairs.clips)||[]).filter(c=>c.youtube&&c.instagram&&c.youtube.views&&c.instagram.views);
  if(both.length&&anPlat===""){ const c=both.reduce((a,b)=>Math.abs(Math.log(b.instagram.views/b.youtube.views))>Math.abs(Math.log(a.instagram.views/a.youtube.views))?b:a);
    const r=c.instagram.views/c.youtube.views;
    if(r>=2||r<=0.5) L.push({id:"apps",plat:"both",title:"The same clip, two different audiences",big:(Math.round((r>=1?r:1/r)*10)/10)+"×",note:"more views for “"+c.title+"” on "+(r>=1?"Instagram":"YouTube"),
      what:"What works on one app doesn't always work on the other. The Videos tab shows each clip on both, side by side.",try:"after each clip, check where it landed best."}); }
  const Ls=L.filter(l=>anPlat===""||l.plat==="both"||l.plat===anPlat);
  if(Ls.length){
    const done=Ls.filter(l=>anLessonsDone[l.id]).length;
    B.push('<div class="an-head an-lessons-head"><h2 class="an-h2">What your numbers are teaching you</h2><span class="an-progress"><b>'+done+' of '+Ls.length+'</b> understood<i><i style="width:'+(done/Ls.length*100).toFixed(0)+'%"></i></i></span></div>'+
      '<div class="an-lessons">'+Ls.map(l=>{ const g=AN_PLAT_TAG[l.plat]||AN_PLAT_TAG.both, ok=!!anLessonsDone[l.id];
        return '<article class="an-card an-lesson"><span class="tag-plat '+g[1]+'">'+g[0]+'</span><h3>'+esc(l.title)+'</h3><div class="big"><b>'+esc(l.big)+'</b><span>'+esc(l.note)+'</span></div>'+
          '<p>'+esc(l.what)+'</p><p class="try"><b>Try:</b> '+esc(l.try)+'</p><button type="button" class="ghost sm an-got" data-id="'+l.id+'" aria-pressed="'+ok+'">'+(ok?'<span class="ms" aria-hidden="true">check</span>Understood':'Got it')+'</button></article>'; }).join("")+'</div>');
  }
  if(!B.length) B.push(anMsg("trending_up","Once your clips have a few days of views, this tab shows when to post and what your numbers are teaching you."));
  box.innerHTML=B.join(""); wireCards(); anNowLine();
  box.querySelectorAll(".an-got").forEach(b=>b.onclick=()=>{ const id=b.dataset.id; if(anLessonsDone[id]) delete anLessonsDone[id]; else anLessonsDone[id]=1;
    try{ localStorage.setItem("pc-an-lessons",JSON.stringify(anLessonsDone)); }catch(e){} anGrowPaint(); });
}

// A thin line at "now" across the evenings chart, so "your clock" is obvious.
function anNowLine(){
  const tr=document.querySelector("#anGrowZones .an-zones"); if(!tr) return;
  const d=new Date(), m=d.getHours()*60+d.getMinutes();
  tr.querySelectorAll(".tr").forEach(el=>{ const n=document.createElement("b"); n.className="now"; n.style.left=(m/1440*100).toFixed(2)+"%"; n.setAttribute("aria-hidden","true"); el.appendChild(n); });
}
