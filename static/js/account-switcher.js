// Channel switcher: the menu that opens from the YouTube / Instagram buttons (sidebar and Post page).
// Lists every connected channel or account; clicking one makes it the active one (no new sign-in),
// "Add" connects another, "Disconnect" removes the active one. New posts go to the active one;
// posts already made or planned stay on their own channel (the server keeps track).
let swMenu=null;
function closeSwitcher(){
  if(!swMenu) return;
  swMenu.remove(); swMenu=null;
  document.removeEventListener("pointerdown",swOutside,true); document.removeEventListener("keydown",swKey,true);
}
function swOutside(e){ if(swMenu && !swMenu.contains(e.target) && !(swMenu.anchor && swMenu.anchor.contains(e.target))) closeSwitcher(); }
function swKey(e){ if(e.key==="Escape"){ const a=swMenu&&swMenu.anchor; closeSwitcher(); if(a) a.focus(); } }
function swItems(kind){
  if(kind==="yt") return (yt.channels||[]).map(c=>({id:c.id,name:c.title||"Your channel",sub:c.handle||"",pic:c.thumb,active:c.active,ok:true}));
  return (ig.accounts||[]).map(a=>({id:a.ig_id,name:"@"+(a.username||""),sub:a.can_post?(a.name||""):"Personal account: can't post",pic:a.picture,active:a.active,ok:a.can_post}));
}
function openSwitcher(kind,anchor){
  if(swMenu && swMenu.anchor===anchor){ closeSwitcher(); return; }
  closeSwitcher();
  const items=swItems(kind), isYt=kind==="yt", active=items.find(i=>i.active);
  const icon=isYt?"smart_display":"photo_camera";
  const m=document.createElement("div");
  m.className="switcher"; m.setAttribute("role","menu"); m.anchor=anchor;
  if(!(isYt?yt:ig).configured){  // nothing to connect to yet: say what's missing instead of doing nothing
    m.setAttribute("role","dialog");
    m.innerHTML='<div class="sw-head">'+(isYt?"YouTube channels":"Instagram accounts")+'</div>'+
      '<p class="sw-setup"><span class="ms" aria-hidden="true">info</span><span>'+(isYt
        ? "YouTube posting isn't set up yet: Pit Crew needs the Google client file in the app's folder (README step 5). Add it, then click here again."
        : "Instagram posting isn't set up yet: Pit Crew needs a Meta app. Put its <b>INSTAGRAM_APP_ID</b> and <b>INSTAGRAM_APP_SECRET</b> in the .env file (README step 6), then restart Pit Crew.")+'</span></p>';
    placeSwitcher(m,anchor); isYt?loadAccount():loadIg(); return;
  }
  m.innerHTML='<div class="sw-head">'+(isYt?"YouTube channels":"Instagram accounts")+'</div>'+
    items.map(i=>'<button type="button" role="menuitemradio" aria-checked="'+i.active+'" class="sw-item'+(i.active?' on':'')+'" data-id="'+esc(i.id)+'">'+
      (i.pic?'<img src="'+esc(i.pic)+'" alt="" referrerpolicy="no-referrer">':'<span class="ms sw-pic" aria-hidden="true">'+icon+'</span>')+
      '<span class="sw-t"><b>'+esc(i.name)+'</b>'+(i.sub?'<small'+(i.ok?'':' class="warn"')+'>'+esc(i.sub)+'</small>':'')+'</span>'+
      (i.active?'<span class="ms sw-check" aria-hidden="true">check</span>':'')+'</button>').join("")+
    '<div class="sw-sep"></div>'+
    '<button type="button" role="menuitem" class="sw-act" id="swAdd"><span class="ms" aria-hidden="true">add</span>'+(isYt?"Add channel":"Add account")+'</button>'+
    (active?'<button type="button" role="menuitem" class="sw-act sw-out" id="swOut"><span class="ms" aria-hidden="true">logout</span>Disconnect '+esc(active.name)+'</button>':'')+
    '<p class="sw-note">New '+(isYt?"Shorts":"Reels")+' go to the ticked one. Ones already posted or scheduled stay where they are.</p>';
  placeSwitcher(m,anchor);
  m.querySelectorAll(".sw-item").forEach(b=>b.onclick=()=>{ closeSwitcher(); if(!b.classList.contains("on")) switchTo(kind,b.dataset.id); });
  $("swAdd").onclick=()=>{ closeSwitcher(); if(isYt) signIn(); else igSignIn(null,true); };
  if($("swOut")) $("swOut").onclick=()=>{ closeSwitcher(); if(isYt) signOut(active.id); else igSignOut(active.id); };
  const first=m.querySelector(".sw-item.on")||m.querySelector("button"); if(first) first.focus();
}
// Show the menu next to its button, kept inside the window; closes on a click outside or Escape.
function placeSwitcher(m,anchor){
  document.body.appendChild(m); swMenu=m;
  const r=anchor.getBoundingClientRect(), w=m.offsetWidth, h=m.offsetHeight;
  let left=Math.min(Math.max(8,r.left), innerWidth-w-8), top=r.bottom+6;
  if(top+h>innerHeight-8) top=Math.max(8, r.top-h-6);
  m.style.left=left+"px"; m.style.top=top+"px";
  document.addEventListener("pointerdown",swOutside,true); document.addEventListener("keydown",swKey,true);
}
async function switchTo(kind,id){
  const isYt=kind==="yt";
  let r,a;
  try{ r=await fetch(isYt?"/api/youtube/switch":"/api/instagram/switch",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(isYt?{channel:id}:{ig_id:id})}); a=await r.json(); }
  catch(e){ r={ok:false}; a={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  if(!r.ok){ if(isYt) ytError(a.error||"Couldn't switch channel."); else if($("igErr")) $("igErr").textContent=a.error||"Couldn't switch account."; isYt?loadAccount():loadIg(); return; }
  if(isYt){ yt=a; paintAccount(); } else { ig=a; paintIg(); }
  switchedAccount();
}
// The pages that show one channel's numbers follow the switch.
function switchedAccount(){
  if(location.hash==="#analytics" && typeof loadAnalytics==="function") loadAnalytics();
  else if(location.hash==="#youtube" && typeof openPosted==="function") openPosted();
}
