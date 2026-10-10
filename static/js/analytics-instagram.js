// Analytics, Instagram part: the account's recent Reels (views, reach, likes, comments, shares, saves,
// watch time) from instagram/insights.py, in Instagram orange. Uses the helpers in analytics.js.
function igAnalyticsHTML(j){
  const st=j.instagram_state||{}, d=j.instagram;
  const head='<div class="an-plat"><i style="background:var(--c-ig)"></i><h2>Instagram</h2>'+(d&&d.account?'<span>@'+esc(d.account.username||"")+
    (d.account.followers!=null?' · '+full(d.account.followers)+' followers':'')+'</span>':'')+'</div>';
  if(!st.configured) return head+'<div class="an-card an-mini"><span class="ms" aria-hidden="true">photo_camera</span><p>Instagram isn\'t available right now. Check back later to see your Reels next to your Shorts.</p></div>';
  if(!st.signed_in) return head+'<div class="an-card an-mini"><span class="ms" aria-hidden="true">photo_camera</span><p>Connect Instagram to see views, reach, saves and shares for your Reels here.</p>'+
    '<button type="button" class="ghost" id="anIgConnect">Connect Instagram</button></div>';
  if(!st.can_post && !d) return head+'<div class="an-card an-mini"><span class="ms" aria-hidden="true">warning</span><p>Instagram only shares Reel numbers for professional accounts. '+IG_SWITCH+'</p>'+
    '<button type="button" class="ghost" id="anIgConnect">Connect again</button></div>';
  if(j.instagram_error) return head+'<div class="an-card an-mini"><span class="ms" aria-hidden="true">error</span><p>'+esc(j.instagram_error)+'</p></div>';
  if(!d) return "";
  const t=d.totals||{}, reels=d.reels||[];
  if(!reels.length) return head+'<div class="an-card an-mini"><span class="ms" aria-hidden="true">movie</span><p>No Reels on @'+esc(d.account.username||"")+' yet. Post one from the Post page and its numbers show up here.</p></div>';
  const inter=(t.likes||0)+(t.comments||0)+(t.shares||0)+(t.saved||0), eng=t.reach?inter/t.reach*100:0;
  const B=[head];
  B.push('<div class="an-tiles ig">'+
    tile("visibility","Views",compact(t.views),"")+tile("groups","Accounts reached",compact(t.reach),"")+
    tile("favorite","Likes",compact(t.likes),"")+tile("chat_bubble","Comments",compact(t.comments),"")+
    tile("send","Shares",compact(t.shares),"")+tile("bookmark","Saves",compact(t.saved),"")+
    tile("bolt","Engagement",t.reach?pct(eng):"–","")+tile("movie","Reels",full(t.reels),"")+'</div>');
  const ins=igInsights(reels);
  if(ins.length) B.push('<div class="an-insights">'+ins.map(i=>'<div class="an-ins ig"><span class="ms" aria-hidden="true">'+i[0]+'</span><span>'+esc(i[1])+'</span></div>').join("")+'</div>');
  const max=Math.max(...reels.map(r=>r.views||0),1);
  B.push(card("anIgTop","Top Reels","Lifetime numbers of your last "+reels.length+" Reels. Click one to open it on Instagram",
    '<div class="tops">'+reels.slice(0,12).map((r,i)=>'<a class="top-row ig" href="'+esc(r.permalink||"#")+'" target="_blank" rel="noopener">'+
      '<span class="rk">'+(i+1)+'</span>'+(r.thumb?'<img src="'+esc(r.thumb)+'" alt="" referrerpolicy="no-referrer" loading="lazy">':'<span class="noimg"></span>')+
      '<span class="tt"><b>'+esc(r.caption||"Reel")+(r.clipline?'<span class="tag clip">Pit Crew</span>':'')+'</b><small>'+
      (r.when?new Date(r.when).toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}):"")+(r.avg_watch_s?" · "+r.avg_watch_s+" s avg. watch":"")+'</small></span>'+
      '<span class="tr"><i style="width:'+((r.views||0)/max*100).toFixed(1)+'%"></i></span>'+
      '<span class="vv"><b>'+compact(r.views)+'</b><small>'+compact(r.likes)+' likes · '+compact(r.saved||0)+' saves</small></span></a>').join("")+'</div>',
    table(["Reel","Views","Reach","Likes","Comments","Shares","Saves","Avg. watch"],reels.map(r=>[r.caption||"Reel",full(r.views),full(r.reach),full(r.likes),full(r.comments),full(r.shares),full(r.saved),r.avg_watch_s?r.avg_watch_s+" s":"–"]),[1,2,3,4,5,6,7])));
  const mix=[["Likes",t.likes],["Comments",t.comments],["Shares",t.shares],["Saves",t.saved]].filter(x=>x[1]>0);
  if(mix.length) B.push('<div class="an-grid2">'+card("anIgMix","What people do with your Reels","Every interaction across these Reels",
    barsHTML(mix.map(([nm,v])=>({nm,v,lab:compact(v)}))),table(["Action","Count"],mix.map(([nm,v])=>[nm,full(v)]),[1]))+
'</div>');
  if(d.partial) B.push('<p class="sub">Some Reels\' numbers didn\'t load (Instagram only gives numbers for Reels posted while the account was professional).</p>');
  return B.join("");
}
function igInsights(reels){
  const out=[], withV=reels.filter(r=>r.views>0);
  if(!withV.length) return out;
  const best=withV.reduce((a,r)=>r.views>a.views?r:a);
  out.push(["emoji_events","Best Reel: “"+(best.caption||"Reel").slice(0,60)+"” with "+compact(best.views)+" views."]);
  const saves=withV.filter(r=>r.saved>0).sort((a,b)=>b.saved/b.views-a.saved/a.views)[0];
  if(saves) out.push(["bookmark","Most saved for its views: “"+(saves.caption||"Reel").slice(0,50)+"”. Saves tell Instagram a Reel is worth showing to more people."]);
  const cl=withV.filter(r=>r.clipline), other=withV.filter(r=>!r.clipline);
  if(cl.length && other.length){
    const a=cl.reduce((s,r)=>s+r.views,0)/cl.length, b=other.reduce((s,r)=>s+r.views,0)/other.length;
    out.push(["auto_awesome","Pit Crew's Reels average "+compact(a)+" views, your others "+compact(b)+"."]);
  }
  return out;
}
function igAnalyticsWire(){
  if($("anIgConnect")) $("anIgConnect").onclick=()=>igSignIn(()=>loadAnalytics());
}
