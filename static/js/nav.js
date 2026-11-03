// Sidebar: + Create (asks: upload a vlog, or make Shorts; js/make-choice.js), Vlogs, Shorts & Reels, Drafts, Settings and the Account row. Scheduled and Analytics are wired in
// on-youtube.js and analytics.js.
function openCreate(){ clearInterval(poll); jobId=null; location.hash="new"; show(1); }
$("createBtn").onclick=()=>openCreateChoice();
$("vlNew").onclick=()=>openVlogUpload();
$("vlogsNav").onclick=()=>openVlogs();
$("clipsNav").onclick=()=>openClips();
$("draftsNav").onclick=()=>openDrafts();
// Back buttons on the pages under Drafts. Leaving the making page doesn't stop anything: it carries on, and shows on Drafts.
$("setupBack").onclick=()=>openDrafts("shorts");
$("makingBack").onclick=()=>openDrafts("shorts");
$("reviewBack").onclick=()=>openDrafts("shorts");
$("settingsNav").onclick=()=>openSettings();
