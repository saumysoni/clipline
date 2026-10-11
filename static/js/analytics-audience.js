// Analytics, Audience tab: who watches and how they find you. YouTube (youtube/analytics_more.audience() plus the
// Overview's countries, ages and genders): the typical viewer in one sentence, pie charts (donuts) for splits with
// a few parts (how they found you, device, men/women, where they watched, subscribers vs not when YouTube gives
// it), a view-to-fan funnel, and column charts with the number on every column for lists (age, countries, cities,
// searches). Instagram (instagram/account_insights.py): who the Reels reached and who the followers are.
// Pie charts never have more than 5 slices (the rest is "Other"); every chart has a Table button.
let anAud=null, anAudIg=null;
function anAudForget(){ anAud=null; anAudIg=null; }
function anAudienceLoad(){
  const q=anQuery(), st=(anData&&anData.instagram_state)||{};
  if(anShowYt()&&anData&&anData.connected&&(!anAud||anAud.q!==q)) anAudYtLoad(q); else anAudYtPaint();
  if(anShowIg()&&st.signed_in&&(!anAudIg||anAudIg.days!==anIgDaysFor())) anAudIgLoad(); else anAudIgPaint();
}
async function anAudYtLoad(q){
  $("anAudBox").innerHTML=anWait("Getting who watches...","audience");
  const j=await anGet("/api/analytics/audience?"+q);
  if(q!==anQuery()) return;
  anAud={q,...j}; anAudYtPaint();
}
async function anAudIgLoad(){
  const d=anIgDaysFor();
  $("anIgBox").innerHTML=anWait("Getting your Instagram audience...","igaudience");
  const j=await anGet("/api/analytics/instagram?days="+d);
  anAudIg={...j,days:d}; anAudIgPaint();
}
// Column chart: one column per row with its number on top (rows: {label, v, lab, sub, color}).
function colsHTML(rows,o){
  o=o||{};
  const max=Math.max(...rows.map(r=>r.v||0),1e-9);
  return '<div class="an-vcols" role="img" aria-label="'+esc((o.label||"")+": "+rows.map(r=>r.label+" "+(r.lab||full(r.v))).join(", "))+'">'+rows.map(r=>
    '<div class="vc" title="'+esc(r.label+": "+(r.title||r.lab||full(r.v)))+'"><div class="vbar"><b>'+esc(r.lab||full(r.v))+'</b>'+
    (r.stack?r.stack.map(s=>'<i style="height:'+(s.v/max*84).toFixed(1)+'%;background:'+s.color+'"></i>').join(""):'<i style="height:'+Math.max(1.5,(r.v||0)/max*84).toFixed(1)+'%;background:'+(r.color||AN_S(0))+'"></i>')+
    '</div><span class="nm">'+esc(r.label)+'</span>'+(r.sub?'<small>'+esc(r.sub)+'</small>':'')+'</div>').join("")+'</div>';
}
function anAudYtPaint(){
  const box=$("anAudBox");
  if(!anShowYt()){ box.innerHTML=""; return; }
  if(!anData||!anData.connected){ box.innerHTML=anMsg("smart_display","Connect YouTube to see who watches your videos.",'<button type="button" class="ghost" id="anAudYtC">Connect YouTube</button>');
    $("anAudYtC").onclick=()=>signIn(()=>loadAnalytics()); return; }
  const j=anAud; if(!j||j.q!==anQuery()) return;
  if(j.error){ box.innerHTML=anMsg("error",j.error); return; }
  const y=(anData&&anData.youtube)||{}, t=y.totals||{}, W=anWord(), B=['<div class="an-plat"><i style="background:var(--c-yt)"></i><h2>YouTube viewers</h2><span>'+esc(anRangeText(y.range||{days:anDays}))+'</span></div>'];
  // the typical viewer, in one sentence
  const tops=a=>a&&a.length?a[0]:null, sum=a=>a.reduce((s,r)=>s+(r.views||0),0);
  const g=tops([...(y.genders||[])].sort((a,b)=>b.pct-a.pct)), ages=[...(y.ages||[])], cv=y.countries||[], dev=j.devices||[], tr=y.traffic||[];
  let ageTop=ages.length?[...ages].sort((a,b)=>b.pct-a.pct).slice(0,2).map(a=>a.group).sort():[];
  if(ageTop.length===2 && (ageTop[0].split("–")[1]||"")!==String(+(ageTop[1].split("–")[0])-1)) ageTop=ageTop.slice(0,1);  // only neighbours make a range
  const ctry=tops(cv), devTop=tops(dev), trTop=tops(tr);
  const bits=[], chips=[];
  if(g){ bits.push(g.gender==="male"?"a man":g.gender==="female"?"a woman":"someone"); chips.push([pct(g.pct),GENDER[g.gender]||g.gender]); }
  if(ageTop.length){ const lo=ageTop[0].split("–")[0], hi=(ageTop[ageTop.length-1].split("–")[1]||"+"); bits.push("aged "+lo+(hi==="+"||hi===""?"+":" to "+hi));
    chips.push([pct(ages.filter(a=>ageTop.includes(a.group)).reduce((s,a)=>s+a.pct,0)),"aged "+ageTop.join(" and ")]); }
  if(ctry&&t.views){ bits.push("in "+(["US","GB","AE","NL","PH","CZ"].includes(ctry.code)?"the ":"")+regionName(ctry.code)); chips.push([pct(ctry.views/t.views*100),"in "+regionName(ctry.code)]); }
  if(devTop){ const dt=sum(dev)||1; bits.push(({MOBILE:"watching on a phone",DESKTOP:"watching on a computer",TABLET:"watching on a tablet",TV:"watching on a TV"})[devTop.key]||""); chips.push([pct(devTop.views/dt*100),"on a "+(devTop.label||"").toLowerCase()]); }
  if(trTop){ const tt=sum(tr)||1; bits.push(trTop.source==="SHORTS"?"who found you in the Shorts feed":trTop.source==="YT_SEARCH"?"who found you by searching":"who found you through "+(TRAFFIC[trTop.source]||"YouTube").toLowerCase()); chips.push([pct(trTop.views/tt*100),"from "+(TRAFFIC[trTop.source]||trTop.source).toLowerCase()]); }
  if(bits.length>=2) B.push('<div class="an-card an-persona"><span class="ms" aria-hidden="true">person</span><div><div class="eyebrow-ai">Your typical viewer</div><p class="headline"></p></div>'+
    '<div class="chips">'+chips.map(c=>'<span><b>'+esc(c[0])+'</b> '+esc(c[1])+'</span>').join("")+'</div></div>');
  // pie charts: splits with a few parts
  const shareRows=(rows,key,lab)=>{ const tot=rows.reduce((a,r)=>a+(r[key]||0),0)||1; return rows.map(r=>({nm:lab?lab(r):r.label,v:r[key]||0,lab:full(r[key])+" "+(key==="shares"?"shares":"views"),pct:(r[key]||0)/tot*100})); };
  const dn=(id,title,sub,rows,note)=>rows.length&&rows.some(r=>r.v>0)?card(id,title,sub,donutHTML(rows)+(note?'<p class="sub dn-note">'+esc(note)+'</p>':''),table(["","Count","Share"],rows.map(r=>[r.nm,full(r.v),pct(r.pct)]),[1,2])):"";
  const trRows=shareRows(tr.map(r=>({label:TRAFFIC[r.source]||r.source,views:r.views,source:r.source})),"views");
  const srch=tr.find(r=>r.source==="YT_SEARCH"), srchPct=srch&&sum(tr)?srch.views/sum(tr)*100:0;
  const d1=[dn("anAuTr","How they found you","Where your "+W[1]+"' views came from",trRows,srchPct?"Search is the slice to grow: it keeps sending viewers long after the feed stops ("+pct(srchPct)+" now).":""),
    dn("anAuDev","What they watch on","",shareRows(dev,"views"),""),
    (y.genders||[]).length?dn("anAuGen","Men and women","Signed-in viewers only",y.genders.map(x=>({nm:GENDER[x.gender]||x.gender,v:x.pct,pct:x.pct,lab:pct(x.pct)})),""):"",
    dn("anAuPlay","Where they watched","",shareRows(j.playback||[],"views"),"")];
  if(j.subscribed&&j.subscribed.length) d1.push(dn("anAuSub","Subscribers vs everyone else","Views from people already subscribed",shareRows(j.subscribed,"views"),""));
  B.push('<div class="an-grid4">'+d1.filter(Boolean).join("")+'</div>');
  if(!(j.subscribed&&j.subscribed.length)) B.push('<div class="an-card an-waiting"><span class="ms" aria-hidden="true">hourglass_empty</span><div><b>Subscribers vs everyone else</b>'+
    '<p class="sub">How many of your views come from people already subscribed. YouTube hasn\'t given this for your channel yet; Pit Crew asks again once a day and shows it here as soon as it does. '+
    (t.subs!=null?'(Not the same as new subscribers: '+(t.subs>0?"+":"")+full(t.subs)+' in this period.)':'')+'</p></div></div>');
  // from a view to a fan
  if(t.views){ const steps=[["Watched",t.views],["Kept watching",t.engaged],["Liked",t.likes],["Subscribed",t.subs!=null?Math.max(0,t.subs):null]].filter(s=>s[1]!=null);
    B.push(card("anAuFunnel","From a view to a fan","Each step is a smaller group of the same viewers",
      '<div class="an-funnel">'+steps.map(([nm,v],i)=>'<span class="nm">'+esc(nm)+(i===1?'<small>engaged views</small>':'')+'</span><span class="tr"><i style="width:'+Math.max(0.6,v/t.views*100).toFixed(1)+'%"></i></span><span class="v"><b>'+full(v)+'</b>'+(i?'<small>'+pct(v/t.views*100)+'</small>':'')+'</span>').join("")+'</div>',
      table(["Step","Viewers","Share of views"],steps.map(([nm,v])=>[nm,full(v),pct(v/t.views*100)]),[1,2]))); }
  // lists: columns with their numbers
  const lists=[];
  const ag=y.age_gender||[];
  if(ages.length){
    const by={}; ag.forEach(r=>{ (by[r.group]=by[r.group]||{})[r.gender]=r.pct; });
    lists.push(card("anAuAge","Age","Signed-in viewers; each column split into men (blue) and women (orange)",
      colsHTML(ages.map(a=>({label:a.group,v:a.pct,lab:pct(a.pct),title:"men "+pct((by[a.group]||{}).male||0)+", women "+pct((by[a.group]||{}).female||0),
        stack:ag.length?[{v:(by[a.group]||{}).female||0,color:AN_S(1)},{v:(by[a.group]||{}).male||0,color:AN_S(0)}]:null})),{label:"Age"}),
      table(["Age","Viewers","Men","Women"],ages.map(a=>[a.group,pct(a.pct),pct((by[a.group]||{}).male||0),pct((by[a.group]||{}).female||0)]),[1,2,3])));
  }
  if(cv.length){ const known=cv.reduce((s,r)=>s+r.views,0), rows=cv.slice(0,6).map(r=>({label:regionName(r.code),v:r.views,sub:t.views?pct(r.views/t.views*100):""}));
    if(t.views&&t.views-known>0) rows.push({label:"Not known",v:t.views-known,sub:pct((t.views-known)/t.views*100),color:"var(--faint)"});
    lists.push(card("anAuCountry","Countries","Views and share",colsHTML(rows,{label:"Countries"}),table(["Country","Views","Share"],rows.map(r=>[r.label,full(r.v),r.sub]),[1,2]))); }
  if((j.cities||[]).length) lists.push(card("anAuCity","Cities","YouTube names a city only once enough people watch from it",colsHTML(j.cities.slice(0,8).map(r=>({label:r.label,v:r.views,color:AN_S(2)})),{label:"Cities"}),table(["City","Views"],j.cities.map(r=>[r.label,full(r.views)]),[1])));
  if((j.os||[]).length) lists.push(card("anAuOs","Phones and computers","Operating systems",colsHTML(j.os.slice(0,6).map(r=>({label:r.label,v:r.views,color:AN_S(3)})),{label:"Operating systems"}),table(["System","Views"],j.os.map(r=>[r.label,full(r.views)]),[1])));
  if(lists.length) B.push('<div class="an-grid2">'+lists.join("")+'</div>');
  if((j.search||[]).length) B.push(card("anAuSearch","What they typed to find you",full(srch?srch.views:0)+" views came from YouTube search",
    colsHTML(j.search.slice(0,8).map(r=>({label:r.label,v:r.views,color:AN_S(4)})),{label:"Searches"}),table(["Search","Views"],j.search.map(r=>[r.label,full(r.views)]),[1])));
  if((j.sharing||[]).length) B.push(card("anAuShare","Where they share","Shares by app",colsHTML(j.sharing.slice(0,6).map(r=>({label:({WHATSAPP:"WhatsApp",COPY_PASTE:"Copied the link",TEXT_MESSAGE:"Text message"})[r.key]||String(r.label).replace(/_/g," ").toLowerCase().replace(/^\w/,c=>c.toUpperCase()),v:r.shares,color:AN_S(5)})),{label:"Shares"}),
    table(["App","Shares"],j.sharing.map(r=>[r.label,full(r.shares)]),[1])));
  box.innerHTML=B.join("");
  const ph=box.querySelector(".an-persona .headline");
  if(ph){ const s=bits.filter(Boolean); ph.textContent=s[0][0].toUpperCase()+s[0].slice(1)+" "+s.slice(1).join(", ")+"."; }
  wireCards(); wireDonuts(box);
}
function anAudIgPaint(){
  const box=$("anIgBox"), st=(anData&&anData.instagram_state)||{};
  if(!anShowIg()){ box.innerHTML=""; return; }
  if(!st.signed_in){ box.innerHTML=anPlat==="instagram"||!anData||!anData.connected?anMsg("photo_camera","Connect a professional Instagram account to see who your Reels reach.",'<button type="button" class="ghost" id="anAudIgC">Connect Instagram</button>'):"";
    if($("anAudIgC")) $("anAudIgC").onclick=()=>igSignIn(()=>{ anAudIg=null; anIgAcct=null; loadAnalytics(); }); return; }
  const j=anAudIg; if(!j) return;
  if(j.error){ box.innerHTML=anMsg("error",j.error); return; }
  if(!j.connected){ box.innerHTML=""; return; }
  const B=['<div class="an-plat"><i style="background:var(--c-ig)"></i><h2>Instagram audience</h2><span>Last '+j.days+' days · Instagram describes your followers, YouTube describes your viewers</span></div>'];
  const FT={FOLLOWER:"Your followers",NON_FOLLOWER:"People who don't follow you",UNKNOWN:"Unknown"};
  const rb=Object.entries(j.reach_by||{}).map(([k,v])=>({nm:FT[k]||k,v})), tot=rb.reduce((a,r)=>a+r.v,0)||1;
  rb.forEach(r=>{ r.pct=r.v/tot*100; r.lab=full(r.v)+" accounts"; });
  const F=j.followers||{}, rowsOf=(o,lab)=>Object.entries(o||{}).map(([k,v])=>({label:lab?lab(k):k,v})).sort((a,b)=>b.v-a.v);
  const g1=[];
  if(rb.some(r=>r.v>0)) g1.push(card("anIgRb","Who your Reels reached","Accounts reached in the last "+j.days+" days",donutHTML(rb),table(["","Accounts","Share"],rb.map(r=>[r.nm,full(r.v),pct(r.pct)]),[1,2])));
  const gen=rowsOf(F.gender,k=>({F:"Women",M:"Men",U:"Other"})[k]||k);
  if(gen.length){ const gt=gen.reduce((a,r)=>a+r.v,0)||1; g1.push(card("anIgGen","Followers: men and women","",donutHTML(gen.map(r=>({nm:r.label,v:r.v,pct:r.v/gt*100}))),table(["","Followers"],gen.map(r=>[r.label,full(r.v)]),[1]))); }
  const colsOf=(id,title,o,lab,color)=>{ const rows=rowsOf(o,lab); if(!rows.length) return ""; const tt=rows.reduce((a,r)=>a+r.v,0)||1;
    return card(id,title,"",colsHTML(rows.slice(0,6).map(r=>({label:r.label,v:r.v,lab:pct(r.v/tt*100),color})),{label:title}),table(["","Followers"],rows.map(r=>[r.label,full(r.v)]),[1])); };
  const g2=[colsOf("anIgCountry","Followers by country",F.country,c=>regionName(c),"var(--c-ig)"),colsOf("anIgAge","Followers by age",F.age,null,"var(--c-ig)"),colsOf("anIgCity","Followers by city",F.city,c=>c.split(",")[0],"var(--c-ig)")].filter(Boolean);
  if(g1.length) B.push('<div class="an-grid4">'+g1.join("")+'</div>');
  B.push(g2.length?'<div class="an-grid2">'+g2.join("")+'</div>':anMsg("groups","Instagram shares who your followers are (country, city, age, gender) once the account has at least 100 followers."));
  box.innerHTML=B.join(""); wireCards(); wireDonuts(box);
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
  return '<div class="donut" data-rows="'+esc(JSON.stringify(rows.map(r=>({nm:r.nm,lab:r.lab||pct(r.share),share:r.share,col:r.col}))))+'">'+
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

