// Scheduled page, Instagram part: every Reel Pit Crew posted or planned (web/instagram_posting.py), with
// Open on Instagram, Cancel (still waiting), Try again (failed) and Edit Short.
async function loadIgScheduled(){
  const list=$("igList");
  list.innerHTML='<li><span></span><span class="pv">Checking Instagram...</span></li>';
  let j; try{ j=await (await fetch("/api/instagram/posts")).json(); }catch(e){ j={items:[],error:"Couldn't reach Pit Crew."}; }
  const a=j.account||{};
  if(!j.items || !j.items.length){
    list.innerHTML='<li><span></span><span class="pv">'+(j.error ? esc(j.error)
      : !a.configured ? "Instagram posting isn't set up yet (README step 6)."
      : !a.signed_in ? 'Nothing on Instagram yet. <button type="button" class="linkbtn" id="igSchConnect">Connect Instagram</button>, then use the Instagram card on the Post page.'
      : "Nothing planned for Instagram yet. Use the Instagram card on the Post page after reviewing a vlog's Shorts.")+'</span></li>';
    if($("igSchConnect")) $("igSchConnect").onclick=()=>igSignIn(()=>loadIgScheduled());
    return;
  }
  const items=j.items.sort((x,y)=>(y.when||y.posted_at||"9").localeCompare(x.when||x.posted_at||"9"));
  const tag={waiting:'<span class="tag good">Scheduled</span>',posting:'<span class="tag good">Posting now</span>',done:'<span class="tag">Posted</span>',
    error:'<span class="tag bad">Failed</span>',check:'<span class="tag bad">Check Instagram</span>'};
  list.innerHTML=items.map((p,i)=>{
    const when=p.status==="done"?p.posted_at:p.when;
    const line=p.status==="waiting"?(p.when?whenText(p.when):"Going out in a moment"):p.status==="done"?(when?whenText(when):"Posted"):p.status==="posting"?(p.step||"Posting")+"...":p.error||"";
    return '<li data-i="'+i+'"><img src="/media/'+esc(p.job)+'/'+esc(p.thumb)+'" alt="">'+
      '<div><div class="pt">'+esc(p.title)+'</div><div class="pv">From '+esc(p.vlog)+((ig.accounts||[]).length>1&&p.username?' · @'+esc(p.username):'')+'</div>'+
      '<div class="pw">'+(tag[p.status]||"")+'<span>'+esc(line)+'</span></div>'+
      '<div class="pa">'+(p.permalink?'<a href="'+esc(p.permalink)+'" target="_blank" rel="noopener">Open on Instagram<span class="ms" aria-hidden="true">open_in_new</span></a>':'')+
        (["error","check"].includes(p.status)?'<button type="button" class="linkbtn rt"><span class="ms" aria-hidden="true">refresh</span>Try again</button>':'')+
        (["waiting","error","check"].includes(p.status)?'<button type="button" class="linkbtn cx"><span class="ms" aria-hidden="true">close</span>'+(p.status==="waiting"?"Cancel":"Remove")+'</button>':'')+
        '<button type="button" class="linkbtn ed"><span class="ms" aria-hidden="true">edit</span>Edit Short</button></div>'+
      '<div class="err" role="alert"></div></div></li>';
  }).join("");
  list.querySelectorAll("li[data-i]").forEach(li=>{
    const p=items[+li.dataset.i], err=li.querySelector(".err");
    const act=async what=>{
      err.textContent="";
      try{ const r=await fetch("/api/instagram/"+what+"/"+p.job+"/"+p.idx,{method:"POST"}); if(!r.ok){ err.textContent=(await r.json()).error||"Couldn't change it."; return; } }
      catch(e){ err.textContent="Couldn't reach Pit Crew."; return; }
      loadIgScheduled();
    };
    if(li.querySelector(".rt")) li.querySelector(".rt").onclick=()=>act("retry");
    if(li.querySelector(".cx")) li.querySelector(".cx").onclick=()=>{ if(p.status!=="waiting" || confirm("Cancel this Reel? It won't be posted to Instagram.")) act("cancel"); };
    li.querySelector(".ed").onclick=()=>openJob(p.job,p.idx);
  });
}
