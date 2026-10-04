// Connect YouTube: the sign-in window and the account line.
// ---- YouTube sign-in: the creator signs in once, then every post goes to that channel
let yt = {configured:false, signed_in:false, channel:null}, ytWin = null;
async function loadAccount(){
  try{ const r=await fetch("/api/youtube/me"); yt=await r.json(); }catch(e){}
  paintAccount();
}
function paintAccount(){
  const name = yt.channel ? yt.channel.title : "your channel";
  $("ytDot").classList.toggle("on", yt.signed_in);
  $("ytText").textContent = yt.signed_in ? name : "Connect YouTube";
  $("ytPill").title = !yt.configured ? "YouTube posting isn't set up yet (README step 5)"
    : yt.signed_in ? "Posting to "+name : "Connect your YouTube channel to post your Shorts";
  $("acct").hidden = false;
  $("acct").innerHTML = !yt.configured
    ? '<span class="ms" aria-hidden="true">info</span><span>YouTube posting isn\'t set up yet: the Google client file is missing from the Clipline folder (README step 5). Drop it in and click <b>Connect YouTube</b>; no restart needed. You can still Save each Short.</span>'
    : yt.signed_in
    ? (yt.channel&&yt.channel.thumb ? '<img src="'+esc(yt.channel.thumb)+'" alt="" referrerpolicy="no-referrer">' : '<span class="ms" aria-hidden="true">smart_display</span>')+
      '<span>Posting to <b>'+esc(name)+'</b>'+(yt.offline?' (offline right now)':'')+'</span>'+
      '<button type="button" class="linkbtn" id="ytSwitch">Switch channel</button><button type="button" class="linkbtn" id="ytOut">Disconnect</button>'
    : '<span class="ms" aria-hidden="true">smart_display</span><span>YouTube isn\'t connected yet. <b>Upload to YouTube</b> asks you to connect first; then press it again to upload.</span><button type="button" class="linkbtn" id="ytIn3">Connect now</button>';
  if($("ytSwitch")){ $("ytSwitch").onclick=()=>signIn(); $("ytOut").onclick=signOut; }
  $("yt1").innerHTML = yt.signed_in
    ? '<span class="who">'+(yt.channel&&yt.channel.thumb ? '<img src="'+esc(yt.channel.thumb)+'" alt="" referrerpolicy="no-referrer">' : '<span class="ms" aria-hidden="true">smart_display</span>')+
        '<span>Posting to <b>'+esc(name)+'</b></span></span>'+
      '<span class="acts"><button type="button" class="linkbtn" id="ytSwitch1">Switch channel</button><button type="button" class="linkbtn" id="ytOut1">Disconnect</button></span>'
    : '<button type="button" class="ghost" id="ytIn1"><span class="ms" aria-hidden="true">smart_display</span>Connect YouTube</button>'+
      '<span>Optional now. If you skip it, Clipline asks when you upload.</span>'+(yt.configured ? '' : '<span class="err" id="ytSetup1"></span>');
  if($("ytIn1")) $("ytIn1").onclick=()=>signIn();
  if($("ytIn3")) $("ytIn3").onclick=()=>signIn();
  if($("ytSwitch1")){ $("ytSwitch1").onclick=()=>signIn(); $("ytOut1").onclick=signOut; }
  if(typeof dock==="function" && jobId) dock();
}
// Opens Google's sign-in in a small window. Must run straight from a click, or the browser blocks it.
function ytError(msg){ if(!$("s1").hidden) $("err1").textContent=msg; else if(!$("reviewView").hidden) $("err3r").textContent=msg; else $("err3").textContent=msg; }
// What to do once the sign-in lands (e.g. the upload the creator asked for before signing in).
let ytThen=null;
function signedIn(a){
  clearInterval(ytWatch); yt=a; paintAccount(); ytError("");
  const f=ytThen; ytThen=null; if(f && yt.signed_in) f();
}
function signIn(then){
  ytThen = then || null;
  if(!yt.configured){
    const msg="YouTube posting isn't set up yet: Clipline needs the Google client file (README step 5). "+
      "Download it from Google Cloud and put it in the Clipline folder as it is (no need to rename it), then click Connect YouTube again.";
    // Check again first: the file may have been added since the page loaded (then one more click signs in).
    loadAccount().then(()=>{
      const m = yt.configured ? "Found the Google client file. Click Connect YouTube again." : msg;
      if(!$("s1").hidden && $("ytSetup1")) $("ytSetup1").textContent=m; else if(!$("s1").hidden) $("err1").textContent=m; else ytError(m);
    });
    return;
  }
  const url="/api/youtube/signin?next="+encodeURIComponent(jobId||"");
  const w=520, h=640, x=Math.max(0,(screen.width-w)/2), y=Math.max(0,(screen.height-h)/2);
  ytWin=window.open(url+"&popup=1","clipline-youtube","popup,width="+w+",height="+h+",left="+x+",top="+y);
  if(!ytWin){ location.href=url; return; }  // popups blocked: sign in in this tab, then come back
  // Google's pages can cut the link to the window, so ask Clipline itself until the sign-in lands.
  clearInterval(ytWatch); const until=Date.now()+5*60000;
  ytWatch=setInterval(async()=>{
    if(Date.now()>until){ clearInterval(ytWatch); return; }
    try{ const r=await fetch("/api/youtube/me"); const a=await r.json();
      if(a.signed_in) signedIn(a); }catch(e){}
  },2000);
}
let ytWatch=null;
window.addEventListener("message",e=>{
  if(e.origin!==location.origin || !e.data || e.data.clipline!=="youtube") return;
  if(!e.data.ok){ ytThen=null; ytError(e.data.msg); }
  else fetch("/api/youtube/me").then(r=>r.json()).then(a=>{ if(a.signed_in) signedIn(a); }).catch(()=>{});
});
async function signOut(){
  try{ await fetch("/api/youtube/signout",{method:"POST"}); }catch(e){}
  yt.signed_in=false; yt.channel=null; paintAccount();
}
$("ytPill").onclick=()=>{ if(!yt.signed_in) signIn(); };
