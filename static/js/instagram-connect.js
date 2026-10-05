// Connect Instagram: the sign-in window and the account line on the Post page (web/instagram_connect.py).
let ig={configured:false,signed_in:false,accounts:[]}, igWatch=null, igThen=null;
async function loadIg(){
  try{ const r=await fetch("/api/instagram/me"); if(r.ok) ig=await r.json(); }catch(e){}
  paintIg();
}
const IG_SWITCH='In the Instagram app: <b>Profile › ☰ › Settings › Account type and tools › Switch to professional account</b> '+
  '(Creator or Business, free; you keep your followers and posts). Then click <b>Connect again</b>.';
function paintPill(){
  $("igDot").classList.toggle("on", !!ig.signed_in && !!ig.can_post);
  $("igText").textContent = ig.signed_in ? "@"+(ig.username||"") : "Connect Instagram";
  const more=(ig.accounts||[]).length-1; $("igMore").textContent = ig.signed_in && more>0 ? "+"+more : "";
  $("igPill").classList.toggle("has", !!ig.signed_in);
  $("igPill").title = !ig.configured ? "Instagram posting isn't set up yet (README step 6)"
    : !ig.signed_in ? "Connect Instagram to post Reels" : !ig.can_post ? "Personal account: switch to professional to post" : "Posting Reels to @"+ig.username;
}
$("igPill").onclick=()=>{ if(ig.configured && !(ig.accounts||[]).length) igSignIn(); else openSwitcher("ig",$("igPill")); };
function paintIg(){
  paintPill();
  const box=$("igAcct"); if(!box) return;
  const pic=ig.picture ? '<img src="'+esc(ig.picture)+'" alt="" referrerpolicy="no-referrer">' : '<span class="ms" aria-hidden="true">photo_camera</span>';
  box.innerHTML = !ig.configured
    ? '<span class="ms" aria-hidden="true">info</span><span>Instagram posting isn\'t set up yet: Pit Crew needs a Meta app (README step 6). You can still Save each Short and post it yourself.</span>'
    : !ig.signed_in
    ? '<span class="ms" aria-hidden="true">photo_camera</span><span>Instagram isn\'t connected yet.</span><button type="button" class="linkbtn" id="igIn">Connect Instagram</button>'
    : pic+'<span>Posting to <b>@'+esc(ig.username||"")+'</b>'+(ig.offline?' (offline right now)':'')+'</span>'+
      '<button type="button" class="linkbtn" id="igSw">'+((ig.accounts||[]).length>1?"Change account":"Switch")+'</button><button type="button" class="linkbtn" id="igOut">Disconnect</button>'+
      (ig.signed_in && !ig.can_post ? '<div class="ig-warn"><span class="ms" aria-hidden="true">warning</span><span>This is a <b>personal</b> account, and Instagram only lets apps post to professional ones. '+IG_SWITCH+'</span></div>' : '');
  if($("igIn")) $("igIn").onclick=()=>igSignIn();
  if($("igSw")) $("igSw").onclick=()=>openSwitcher("ig",$("igSw"));
  if($("igOut")) $("igOut").onclick=()=>igSignOut();
  if(typeof igDock==="function") igDock();
  if(typeof paintSettings==="function") paintSettings();
}
// add: connecting another account, so Instagram asks who to log in as (not the account the browser is in).
function igSignIn(then,add){
  igThen=then||null;
  if(!ig.configured){ loadIg(); return; }
  const url="/api/instagram/signin"+(add?"?add=1":""), w=520, h=700, x=Math.max(0,(screen.width-w)/2), y=Math.max(0,(screen.height-h)/2);
  const win=window.open(url+(add?"&":"?")+"popup=1","clipline-instagram","popup,width="+w+",height="+h+",left="+x+",top="+y);
  if(!win){ location.href=url; return; }
  const key=a=>(a.signed_in?a.ig_id:"")+"|"+(a.accounts||[]).map(x=>x.ig_id).join(",");
  clearInterval(igWatch); const until=Date.now()+5*60000, was=key(ig);
  igWatch=setInterval(async()=>{
    if(Date.now()>until){ clearInterval(igWatch); return; }
    try{ const a=await (await fetch("/api/instagram/me")).json(); if(a.signed_in && key(a)!==was) igSignedIn(a); }catch(e){}
  },2000);
}
function igSignedIn(a){
  clearInterval(igWatch); ig=a; paintIg();
  const f=igThen; igThen=null; if(f && ig.signed_in) f();
}
window.addEventListener("message",e=>{
  if(e.origin!==location.origin || !e.data || e.data.clipline!=="instagram") return;
  if(!e.data.ok){ igThen=null; if($("igErr")) $("igErr").textContent=e.data.msg; return; }
  fetch("/api/instagram/me").then(r=>r.json()).then(a=>{ if(a.signed_in) igSignedIn(a); }).catch(()=>{});
});
// Disconnect one account (none given: the active one); another connected account becomes active.
async function igSignOut(igId){
  try{ const r=await fetch("/api/instagram/signout",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ig_id:igId||null})});
    ig = r.ok ? await r.json() : {configured:ig.configured,signed_in:false,accounts:[]}; }
  catch(e){ ig={configured:ig.configured,signed_in:false,accounts:[]}; }
  paintIg(); switchedAccount();
}

