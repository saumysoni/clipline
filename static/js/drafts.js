// Drafts page (screen 11): two tabs. Vlogs = vlogs prepared here for YouTube that haven't been uploaded yet, and ones
// being prepared (rows from js/vlogs.js vlRow()). Shorts & Reels = clips on neither platform yet: the Shorts & Reels
// clip browser (js/clips.js) in "drafts" mode, grouped by vlog (each with Review & post, its review page), with its
// vlog filter, Select, Schedule and Delete; vlogs whose Shorts are being made, paused or stopped show there too
// (dfMaking), kept up to date by the progress card's checks (js/jobs-now.js dfFollow).
let dfVlogs=null, dfAll=[], dfTab="vlogs";
// Vlogs whose Shorts are being made, are paused, or stopped (not a vlog upload being prepared: that's the Vlogs tab).
const dfMaking=()=>dfAll.filter(v=>!v.prep && ["working","paused","error"].includes(v.status));
// A vlog upload being prepared for YouTube (or that stopped while it was).
const dfPrepping=v=>v.prep && ["working","error"].includes(v.status);
const dfPick=pageTabs("dfTabs",tab=>{ dfTab=tab; location.hash="drafts"+(tab==="shorts"?"/shorts":""); clDock(); qrClose(); });
// tab: "vlogs" or "shorts" (none = the tab last clicked, else the first one with something in it); vlog: show only
// that vlog's draft clips.
async function openDrafts(tab,vlog){
  clearInterval(poll); tab=tab||dfPick.saved();
  dfTab=tab||"vlogs"; location.hash="drafts"+(dfTab==="shorts"?"/shorts":""); show(11); dfPick(dfTab);
  await loadDraftVlogs();  // first: the clip browser draws the Shorts being made from it
  await clOpen("drafts",$("dfShorts"),vlog);
  if(!tab && dfVlogs && !dfVlogs.length && (clData.some(isDraftClip) || dfMaking().length)){ dfTab="shorts"; dfPick(dfTab); location.hash="drafts/shorts"; clDock(); }
  refreshJobsNow();  // checks again every few seconds while something is being made (dfFollow)
}
async function loadDraftVlogs(){
  try{ const r=await fetch("/api/vlogs"); if(!r.ok) throw 0; dfAll=(await r.json()).items||[]; }
  catch(e){ $("dfErr").textContent="Couldn't load your vlogs. Check your internet connection, then reload the page."; return; }
  paintDraftVlogs();
}
function paintDraftVlogs(){
  dfVlogs=dfAll.filter(v=>isDraftVlog(v) || dfPrepping(v));
  $("dfErr").textContent=""; tabCount("dfNVlogs",dfVlogs.length);
  const vl=$("dfVlogList");
  vl.innerHTML = dfVlogs.length ? dfVlogs.map(vlRow).join("")
    : tabEmpty("video_library","No vlog drafts","Vlogs you prepare for YouTube wait here until you upload them. Start one with Upload a vlog.",["add","Upload a vlog"]);
  vl.querySelectorAll(".vrow").forEach(el=>vlWire(el,dfVlogs.find(v=>v.id===el.dataset.id),loadDraftVlogs,"dfErr"));
  tabCount("dfNShorts",clData.filter(isDraftClip).length+dfMaking().length);
  const go=vl.querySelector(".tab-empty-go"); if(go) go.onclick=()=>openVlogUpload();
}
// The Shorts & Reels tab's number follows the clip browser (it changes after scheduling or deleting), and so do Quick
// review (js/quick-review.js) and the editor (js/editor.js).
clOnPaint=()=>{ if(clMode==="drafts") tabCount("dfNShorts",clData.filter(isDraftClip).length+dfMaking().length); qrSync(); edSync(); };
// The progress card checked the vlogs again (every few seconds while something is being made): follow it here.
// finished: something stopped being made (ready, paused or stopped), so its Shorts may be drafts now.
function dfFollow(items, finished){
  dfAll=items; paintDraftVlogs();
  if(clMode!=="drafts") return;
  if(finished) loadClips(); else paintClips();
}
