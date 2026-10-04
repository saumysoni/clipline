// Connect Instagram: the sign-in window and the account line on the Post page (web/instagram_connect.py).
let ig={configured:false,signed_in:false}, igWatch=null, igThen=null;
async function loadIg(){
  try{ const r=await fetch("/api/instagram/me"); if(r.ok) ig=await r.json(); }catch(e){}
  paintIg();
}
const IG_SWITCH='In the Instagram app: <b>Profile › ☰ › Settings › Account type and tools › Switch to professional account</b> '+
  '(Creator or Business, free; you keep your followers and posts). Then click <b>Connect again</b>.';
function paintIg(){
  const box=$("igAcct"); if(!box) return;
  const pic=ig.picture ? '<img src="'+esc(ig.picture)+'" alt="" referrerpolicy="no-referrer">' : '<span class="ms" aria-hidden="true">photo_camera</span>';
  box.innerHTML = !ig.configured
    ? '<span class="ms" aria-hidden="true">info</span><span>Instagram posting isn\'t set up yet: Clipline needs a Meta app (README step 6). You can still Save each Short and post it yourself.</span>'
    : !ig.signed_in
    ? '<span class="ms" aria-hidden="true">photo_camera</span><span>Instagram isn\'t connected yet.</span><button type="button" class="linkbtn" id="igIn">Connect Instagram</button>'
    : pic+'<span>Posting to <b>@'+esc(ig.username||"")+'</b>'+(ig.offline?' (offline right now)':'')+'</span>'+
      '<button type="button" class="linkbtn" id="igIn">Switch</button><button type="button" class="linkbtn" id="igOut">Disconnect</button>'+
      (ig.signed_in && !ig.can_post ? '<div class="ig-warn"><span class="ms" aria-hidden="true">warning</span><span>This is a <b>personal</b> account, and Instagram only lets apps post to professional ones. '+IG_SWITCH+'</span></div>' : '');
  if($("igIn")) $("igIn").onclick=()=>igSignIn();
  if($("igOut")) $("igOut").onclick=igSignOut;
  if(typeof igDock==="function") igDock();
}
function igSignIn(then){
  igThen=then||null;
  if(!ig.configured){ loadIg(); return; }
  const url="/api/instagram/signin", w=520, h=700, x=Math.max(0,(screen.width-w)/2), y=Math.max(0,(screen.height-h)/2);
  const win=window.open(url+"?popup=1","clipline-instagram","popup,width="+w+",height="+h+",left="+x+",top="+y);
  if(!win){ location.href=url; return; }
  clearInterval(igWatch); const until=Date.now()+5*60000, was=ig.username;
  igWatch=setInterval(async()=>{
    if(Date.now()>until){ clearInterval(igWatch); return; }
    try{ const a=await (await fetch("/api/instagram/me")).json(); if(a.signed_in && (a.username!==was || !ig.signed_in)) igSignedIn(a); }catch(e){}
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
async function igSignOut(){
  try{ await fetch("/api/instagram/signout",{method:"POST"}); }catch(e){}
  ig={configured:ig.configured,signed_in:false}; paintIg();
}
loadIg();
