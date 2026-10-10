// Drafts page (screen 11): two tabs. Vlogs = vlogs prepared here for YouTube that haven't been uploaded yet
// (rows from js/vlogs.js vlRow()). Shorts & Reels = clips on neither platform yet: the Shorts & Reels clip browser
// (js/clips.js) in "drafts" mode, with its vlog filter, Select, Schedule and Delete.
let dfVlogs=null, dfTab="vlogs";
const dfPick=pageTabs("dfTabs",tab=>{ dfTab=tab; location.hash="drafts"+(tab==="shorts"?"/shorts":""); clDock(); });
// tab: "vlogs" or "shorts" (none = the tab last clicked, else the first one with something in it); vlog: show only
// that vlog's draft clips.
async function openDrafts(tab,vlog){
  clearInterval(poll); tab=tab||dfPick.saved();
  dfTab=tab||"vlogs"; location.hash="drafts"+(dfTab==="shorts"?"/shorts":""); show(11); dfPick(dfTab);
  await Promise.all([loadDraftVlogs(), clOpen("drafts",$("dfShorts"),vlog)]);
  if(!tab && dfVlogs && !dfVlogs.length && clData.some(isDraftClip)){ dfTab="shorts"; dfPick(dfTab); location.hash="drafts/shorts"; clDock(); }
}
async function loadDraftVlogs(){
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; dfVlogs=((await r.json()).items||[]).filter(isDraftVlog); }
  catch(e){ $("dfErr").textContent="Couldn't load your vlogs. Check your internet connection, then reload the page."; return; }
  $("dfErr").textContent=""; tabCount("dfNVlogs",dfVlogs.length);
  const vl=$("dfVlogList");
  vl.innerHTML = dfVlogs.length ? dfVlogs.map(vlRow).join("")
    : tabEmpty("video_library","No vlog drafts","Vlogs you prepare for YouTube wait here until you upload them. Start one with Upload a vlog.",["add","Upload a vlog"]);
  vl.querySelectorAll(".vrow").forEach(el=>vlWire(el,dfVlogs.find(v=>v.id===el.dataset.id),loadDraftVlogs,"dfErr"));
  const go=vl.querySelector(".tab-empty-go"); if(go) go.onclick=()=>openVlogUpload();
}
// The Shorts & Reels tab's number follows the clip browser (it changes after scheduling or deleting).
clOnPaint=()=>{ if(clMode==="drafts") tabCount("dfNShorts",clData.filter(isDraftClip).length); };
