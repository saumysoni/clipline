// The first time an account is connected: a screen that waits while what's already on it comes in (web/first_import.py), and
// before that, for a new account, Connect your accounts. Connecting in the middle of something (posting a Short, uploading)
// doesn't stop the creator: it comes in behind what they're doing.
let onbData={imports:[]}, onbMode="", onbT=null, onbFrom=0, onbLate=false;
const ONB_MIN=1800, ONB_MAX=30000, ONB_AFTER_LATE=4000;
const onbPlural=(n,w)=>n.toLocaleString()+" "+w+(n===1?"":"s");
async function onbAsk(url,post){
  try{ const r=await fetch(url,post?{method:"POST"}:undefined);
    if(r.status===401||r.status===403){ onbHide(); return null; }
    return r.ok?await r.json():null; }
  catch(e){ return null; }
}
// In the middle of something: making or posting, uploading, editing, a dialog or Quick review open.
const onbBusy=()=>[1,2,3,4,10,12].some(n=>!$("s"+n).hidden) || !!document.querySelector("dialog[open]") || document.body.classList.contains("qr-open");
async function onbBoot(){
  const j=await onbAsk("/api/import/status"); if(!j) return;
  if(j.welcome){ await Promise.all([loadAccount(),loadIg()]); onbData=j; onbOpen("welcome"); }
  else if(j.imports.length && !onbBusy()){ await Promise.all([loadAccount(),loadIg()]); onbData=j; onbFollow(); }
}
// An account was just connected from anywhere on the page.
async function onbConnected(){
  const j=await onbAsk("/api/import/begin",true); if(!j) return;
  const open=!$("onb").hidden;
  if(!j.imports.length){ if(open) onbPaint(); return; }  // already read before: nothing to wait for
  if(open||!onbBusy()){ onbData=j; onbFollow(); }
  else onbAsk("/api/import/seen",true);
}
async function onbQuiet(){ await onbAsk("/api/import/begin",true); onbAsk("/api/import/seen",true); }
function onbOpen(mode){
  onbMode=mode; $("onb").hidden=false; $("app").inert=true; document.documentElement.classList.add("onb-on"); onbPaint();
  setTimeout(()=>$("onbTitle").focus(),0);
}
function onbHide(){ clearTimeout(onbT); $("onb").hidden=true; $("app").inert=false; document.documentElement.classList.remove("onb-on"); }
function onbFollow(){
  clearTimeout(onbT); onbFrom=Date.now(); onbLate=false;
  if($("onb").hidden) onbOpen("import"); else { onbMode="import"; onbPaint(); }
  onbTick();
}
async function onbTick(){
  const j=await onbAsk("/api/import/status");
  if($("onb").hidden) return;
  if(j) onbData=j;
  const running=onbData.imports.some(x=>x.state==="running"), took=Date.now()-onbFrom;
  if(running && took>=ONB_MAX){  // never held here: it carries on while they work
    onbLate=true; onbMode="done"; onbPaint(); onbT=setTimeout(onbFinish,ONB_AFTER_LATE); return; }
  if(running || took<ONB_MIN){ onbPaint(); onbT=setTimeout(onbTick,Math.min(800,Math.max(100,running?800:ONB_MIN-took))); return; }
  onbMode="done";
  if(onbOffer() || onbData.imports.some(x=>x.state==="error")) onbPaint();  // something for them to read or choose
  else { onbPaint(); onbT=setTimeout(onbFinish,1200); }
}
// The other app, when it can be connected and isn't.
const onbOffer=()=>!onbLate && (yt.configured&&!yt.signed_in ? "youtube" : ig.configured&&!ig.signed_in ? "instagram" : "");
function onbStep(state,text){
  const icon={ok:"check_circle",run:"progress_activity",bad:"warning"}[state];
  return '<li class="onb-step '+state+'"><span class="ms" aria-hidden="true">'+icon+'</span><span>'+esc(text)+'</span></li>';
}
function onbFound(x){
  if(x.platform==="instagram") return x.reels ? "Found "+onbPlural(x.reels,"Reel") : "No Reels on this account yet";
  const parts=[]; if(x.videos) parts.push(onbPlural(x.videos,"video")); if(x.shorts) parts.push(onbPlural(x.shorts,"Short"));
  return parts.length ? "Found "+parts.join(" and ") : "No videos on this channel yet";
}
function onbLink(platform,more){
  const isYt=platform==="youtube", name=isYt?"YouTube":"Instagram";
  return '<button type="button" class="ghost onb-link" data-p="'+platform+'"><span class="ms" aria-hidden="true">'+(isYt?"smart_display":"photo_camera")+'</span>'+
    '<span class="onb-link-t"><b>Connect '+name+(more?" too":"")+'</b><small>'+(isYt?"Brings in your videos and Shorts":"Brings in your Reels")+'</small></span></button>';
}
function onbPaint(){
  const rows=onbData.imports, welcome=onbMode==="welcome", done=onbMode==="done", bad=rows.some(x=>x.state==="error"), offer=done?onbOffer():"";
  $("onbTitle").textContent = welcome ? "Connect your accounts" : onbLate ? "Still bringing them in" : done ? (bad?"Your dashboard is open":"Your dashboard is ready") : "Getting your dashboard ready";
  $("onbLede").textContent = welcome ? "Pit Crew brings in what you've already posted, and posts your new Shorts and Reels for you. You can do this later in Settings."
    : onbLate ? "There's a lot here. It keeps coming in while you work, so you can carry on."
    : done ? (bad?"":offer?"Connect "+(offer==="youtube"?"YouTube":"Instagram")+" too, or go straight in.":"Everything you've posted is here now.")
    : "This only happens the first time you connect an account.";
  const steps=rows.map(x=>onbStep("ok","Connected to "+x.name)+(
    x.state==="running" ? onbStep("run",x.platform==="instagram"?"Finding your Reels":"Finding your videos and Shorts")
    : x.state==="error" ? onbStep("bad",x.personal
      ? "Instagram only shares Reels with apps for professional accounts. In the Instagram app, go to Settings › Account type and tools › Switch to professional account (free), then connect again."
      : "Couldn't read "+x.name+" just now. Pit Crew tries again by itself, so they'll appear soon.")
    : onbStep("ok",onbFound(x)))).join("");
  $("onbSteps").hidden=welcome;
  setHTML($("onbSteps"), welcome?"":steps+(done&&!onbLate ? onbStep("ok","Dashboard ready") : onbLate ? "" : onbStep("run","Getting your dashboard ready")));
  const links=welcome ? [yt.configured&&!yt.signed_in&&"youtube", ig.configured&&!ig.signed_in&&"instagram"].filter(Boolean) : offer?[offer]:[];
  $("onbLinks").hidden=!links.length;
  setHTML($("onbLinks"), links.map(p=>onbLink(p,!welcome)).join(""));
  $("onbLinks").querySelectorAll(".onb-link").forEach(b=>b.onclick=()=>{ $("onbErr").textContent=""; if(b.dataset.p==="youtube") signIn(); else igSignIn(); });
  const stay=welcome||(done&&!onbLate&&(offer||bad));
  $("onbFoot").hidden=!(stay||onbLate);
  $("onbGo").className=welcome?"ghost":"primary";
  $("onbGo").textContent=welcome?"Skip for now":"Go to my dashboard";
}
$("onbGo").onclick=()=>onbFinish();
async function onbFinish(){
  const found=onbData.imports.filter(x=>x.state==="done"), sum=k=>found.reduce((n,x)=>n+(x[k]||0),0);
  const videos=sum("videos"), clips=sum("shorts")+sum("reels"), wasWelcome=onbMode==="welcome";
  onbHide(); onbAsk("/api/import/seen",true);
  onbData={imports:[]}; onbMode=""; onbLate=false;
  if(wasWelcome) return;
  openRoute(videos?"vlogs":clips?"clips":location.hash.slice(1));  // where it all shows up (or the same page, fresh)
}
