// Sidebar: + Create (a new vlog), Vlogs, Settings and the Account row. Scheduled and Analytics are wired in
// on-youtube.js and analytics.js.
function openCreate(){ clearInterval(poll); jobId=null; location.hash="new"; show(1); }
$("createBtn").onclick=openCreate;
$("vlNew").onclick=openCreate;
$("vlogsNav").onclick=()=>openVlogs();
$("settingsNav").onclick=$("accountNav").onclick=()=>openSettings();
