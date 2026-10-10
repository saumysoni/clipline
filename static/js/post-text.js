// A Short's text for posting, on its editor card (web/post_text.py): hashtags (shared by YouTube and Instagram), then a
// tab per platform: YouTube = the title (the description is written for you), Instagram = the caption (suggested until
// the creator writes their own, then saved as typed). Only connected platforms get a tab (none or both connected: both).
// Which platforms are connected is often not known yet when the cards are drawn, so ptApply() sets the tabs each time
// a card opens.
// The title input keeps its class "title": js/review-tiles.js saves it and shows it on the tile.
// "Generate ideas" under each asks the AI for three options (web/post_text.py, pipeline/post_suggest.py); picking one
// fills the field and saves it like typing.
function ptPlatforms(){
  const y=!!(yt&&yt.signed_in), i=!!(ig&&ig.signed_in);
  return y&&!i ? ["youtube"] : i&&!y ? ["instagram"] : ["youtube","instagram"];
}
const ptGen=kind=>'<div class="pt-gen"><button type="button" class="ghost sm pt-go" data-kind="'+kind+'"><span class="ms" aria-hidden="true">auto_awesome</span><span>Generate ideas</span></button>'+
  '<div class="pt-ideas" data-kind="'+kind+'" aria-live="polite"></div></div>';
const ptChip=t=>'<span class="pt-chip">#'+esc(t)+'<button type="button" class="pt-x" data-t="'+esc(t)+'" aria-label="Remove #'+esc(t)+'"><span class="ms" aria-hidden="true">close</span></button></span>';
function postTextHTML(s){
  const id="pt"+s.idx;
  const tab=(p,label,icon)=>'<button type="button" role="tab" id="'+id+p+'" aria-controls="'+id+p+'P" aria-selected="false" tabindex="-1" data-p="'+p+'">'+
    '<span class="ms '+(p==="youtube"?"yt":"ig")+'" aria-hidden="true">'+icon+'</span>'+label+'</button>';
  return '<div class="ptx">'+
    '<div class="tfield pt-tags"><label class="fld-lab" for="'+id+'tag">Hashtags<span class="pt-both"> · YouTube and Instagram</span></label>'+
      '<div class="pt-chips">'+(s.hashtags||[]).map(ptChip).join("")+
        '<input id="'+id+'tag" class="pt-tag-in" type="text" maxlength="50" placeholder="Add a hashtag" autocomplete="off" autocapitalize="off" spellcheck="false"></div>'+
      '<small class="pt-hint pt-extra"></small></div>'+
    '<div class="pt-tabs" role="tablist" aria-label="Where it\'s posted">'+tab("youtube","YouTube","smart_display")+tab("instagram","Instagram","photo_camera")+'</div>'+
    '<div class="pt-panel" role="tabpanel" id="'+id+'youtubeP" aria-labelledby="'+id+'youtube" data-p="youtube" hidden>'+
      '<div class="tfield"><label class="fld-lab" for="title'+s.idx+'">YouTube title</label><input class="title" id="title'+s.idx+'" type="text" value="'+esc(s.title)+'" maxlength="95"></div>'+
      ptGen("title")+
      '<small class="pt-hint">The description is written for you: the hook, a link to the full video and the hashtags.</small></div>'+
    '<div class="pt-panel" role="tabpanel" id="'+id+'instagramP" aria-labelledby="'+id+'instagram" data-p="instagram" hidden>'+
      '<div class="tfield"><label class="fld-lab" for="'+id+'cap">Instagram caption</label>'+
        '<textarea class="pt-cap" id="'+id+'cap" rows="5" maxlength="2200" placeholder="Getting the suggested caption..."></textarea>'+
        '<div class="pt-row"><small class="pt-state"></small><button type="button" class="linkbtn pt-reset" hidden>Use the suggested caption</button><small class="pt-count"></small></div>'+
        ptGen("caption")+
        '<small class="pt-hint">The hashtags are added at the end.</small>'+
        '<small class="pt-note" hidden></small></div></div>'+
    '<div class="err pt-err" role="alert"></div>'+
  '</div>';
}
// Shows the tab for each connected platform (one platform: no tab bar), on the tab last used on this device.
function ptApply(el){
  const box=el.querySelector(".ptx"); if(!box) return;
  const plats=ptPlatforms(), both=plats.length>1, cur=box.querySelector('[role=tab][aria-selected=true]');
  let saved=null; try{ saved=localStorage.getItem("pc-pt-tab"); }catch(e){}
  const on=cur&&plats.includes(cur.dataset.p) ? cur.dataset.p : plats.includes(saved) ? saved : plats[0];
  box.querySelector(".pt-tabs").hidden=!both; box.querySelector(".pt-both").hidden=!both;
  box.querySelector(".pt-extra").textContent = both ? "YouTube also gets #Shorts, Instagram #reels." : on==="youtube" ? "YouTube also gets #Shorts." : "Instagram also gets #reels.";
  box.querySelectorAll("[role=tab]").forEach(t=>{ const sel=t.dataset.p===on; t.setAttribute("aria-selected",sel); t.tabIndex=sel?0:-1; t.hidden=!plats.includes(t.dataset.p); });
  box.querySelectorAll(".pt-panel").forEach(p=>p.hidden=p.dataset.p!==on);
  if(on==="instagram" && box._ptLoad) box._ptLoad();
}
function wirePostText(el,s){
  const box=el.querySelector(".ptx"); if(!box||!s) return;
  const url="/api/clips/"+job.id+"/"+s.idx+"/post-text", err=box.querySelector(".pt-err");
  const cap=box.querySelector(".pt-cap"), state=box.querySelector(".pt-state"), reset=box.querySelector(".pt-reset");
  const count=box.querySelector(".pt-count"), note=box.querySelector(".pt-note"), tagIn=box.querySelector(".pt-tag-in");
  let suggested="", tags=[...(s.hashtags||[])], dirty=false;
  async function send(body){
    err.textContent="";
    try{
      const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}), j=await r.json();
      if(!r.ok){ err.textContent=j.error||"Couldn't save it. Try again."; return null; }
      return j;
    }catch(e){ err.textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; return null; }
  }
  function show(j){
    suggested=j.suggested||""; if(!dirty) cap.value=j.caption||suggested;
    reset.hidden=!j.caption; paintCount();
    note.hidden=!j.instagram;
    note.textContent = j.instagram==="posted" ? "Already on Instagram: changes here won't change the posted Reel."
      : j.instagram==="planned" ? "Planned for Instagram: it goes out with this caption." : "";
  }
  const paintCount=()=>{ count.textContent=cap.value.length.toLocaleString()+" / 2,200"; };
  async function load(){ if(dirty) return; try{ const r=await fetch(url); if(r.ok) show(await r.json()); }catch(e){} }
  box._ptLoad=load;  // the suggestion follows title and hook changes, so it's fetched whenever the Instagram tab shows
  // ---- tabs (one per platform; the last one used is remembered on this device)
  const tabs=[...box.querySelectorAll('[role=tab]')];
  tabs.forEach((b,i)=>{
    b.onclick=()=>{
      tabs.forEach(x=>{ const on=x===b; x.setAttribute("aria-selected",on); x.tabIndex=on?0:-1; });
      box.querySelectorAll(".pt-panel").forEach(p=>p.hidden=p.dataset.p!==b.dataset.p);
      try{ localStorage.setItem("pc-pt-tab",b.dataset.p); }catch(e){}
      if(b.dataset.p==="instagram") load();  // the suggestion follows title edits
    };
    b.onkeydown=e=>{ const st=e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0; if(!st) return;
      const n=tabs[(i+st+tabs.length)%tabs.length]; n.focus(); n.click(); e.preventDefault(); };
  });
  // ---- caption: saved a second after typing stops; the same text as the suggestion counts as "not edited"
  cap.addEventListener("input",()=>{
    dirty=true; paintCount(); state.textContent=""; clearTimeout(cap._save);
    cap._save=setTimeout(async()=>{
      state.textContent="Saving...";
      const j=await send({caption:cap.value});
      state.textContent=j?"Saved":""; dirty=false; if(j) show(j);
    },1000);
  });
  reset.onclick=async()=>{ clearTimeout(cap._save); dirty=false; cap.value=suggested; paintCount(); const j=await send({caption:""}); if(j){ show(j); state.textContent="Saved"; } };
  // ---- hashtags: type and press Enter, space or comma (or paste several); Backspace in the empty box removes the last
  function paintTags(){ box.querySelectorAll(".pt-chip").forEach(c=>c.remove()); tagIn.insertAdjacentHTML("beforebegin",tags.map(ptChip).join(""));
    box.querySelectorAll(".pt-x").forEach(x=>x.onclick=()=>{ tags=tags.filter(t=>t!==x.dataset.t); paintTags(); saveTags(); }); }
  async function saveTags(){
    const j=await send({hashtags:tags}); if(!j) return;
    tags=j.hashtags; s.hashtags=[...tags]; paintTags();
  }
  function addFrom(text){
    const add=String(text).split(/[\s,]+/).map(t=>t.replace(/^#+/,"").replace(/[^\p{L}\p{N}_]/gu,"")).filter(Boolean);
    const have=new Set(tags.map(t=>t.toLowerCase())), fresh=add.filter(t=>!have.has(t.toLowerCase())&&have.add(t.toLowerCase()));
    if(!fresh.length) return;
    if(tags.length+fresh.length>30){ err.textContent="Instagram allows 30 hashtags. Remove a few first."; return; }
    tags=tags.concat(fresh); paintTags(); saveTags();
  }
  tagIn.addEventListener("keydown",e=>{
    if(["Enter",","," "].includes(e.key)){ e.preventDefault(); addFrom(tagIn.value); tagIn.value=""; }
    else if(e.key==="Backspace" && !tagIn.value && tags.length){ tags.pop(); paintTags(); saveTags(); }
  });
  tagIn.addEventListener("paste",e=>{ const t=(e.clipboardData||window.clipboardData).getData("text"); if(/[\s,]/.test(t.trim())){ e.preventDefault(); addFrom(t); } });
  tagIn.addEventListener("blur",()=>{ if(tagIn.value.trim()){ addFrom(tagIn.value); tagIn.value=""; } });
  box.querySelector(".pt-chips").addEventListener("click",e=>{ if(e.target.classList.contains("pt-chips")) tagIn.focus(); });
  // ---- Generate ideas: three AI options under the title / caption; picking one fills the field (and saves it)
  box.querySelectorAll(".pt-go").forEach(go=>go.onclick=async()=>{
    const kind=go.dataset.kind, list=box.querySelector('.pt-ideas[data-kind="'+kind+'"]'), lab=go.lastChild;
    err.textContent=""; go.disabled=true; lab.textContent="Writing ideas...";
    let r,j; try{ r=await fetch("/api/clips/"+job.id+"/"+s.idx+"/suggest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind})}); j=await r.json(); }
    catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
    go.disabled=false; lab.textContent=r.ok?"More ideas":"Generate ideas";
    if(!r.ok){ err.textContent=j.error||"Couldn't write ideas right now. Try again in a moment."; return; }
    list.innerHTML=j.items.map(t=>'<button type="button" class="pt-idea">'+esc(t).replace(/\n/g,"<br>")+'</button>').join("");
    list.querySelectorAll(".pt-idea").forEach((b,i)=>b.onclick=()=>{
      const field=kind==="title" ? box.querySelector("input.title") : cap;
      field.value=j.items[i]; field.dispatchEvent(new Event("input",{bubbles:true})); field.focus();
      list.querySelectorAll(".pt-idea").forEach(x=>x.classList.toggle("used",x===b));
    });
  });
  paintTags();
  el.addEventListener("click",()=>{ if(!el.classList.contains("open")) ptApply(el); },true);  // opening the card
  ptApply(el);
}
