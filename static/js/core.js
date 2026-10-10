// Shared helpers and page state used by every other file: $(id), fmt(), esc(), show(step).
// All files in static/js share one global scope and load in the order listed in index.html.
const $ = id => document.getElementById(id);
const fmt = s => { s=Math.round(s); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0"); };
// "Open in Studio": through Google's sign-in, so a browser that isn't signed in to YouTube shows the
// sign-in page and then lands on this Short in Studio (a signed-in browser goes straight through).
const studioLink = id => "https://accounts.google.com/ServiceLogin?service=youtube&continue="+
  encodeURIComponent("https://studio.youtube.com/video/"+id+"/edit");
const esc = t => String(t).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let count = 5, jobId = null, poll = null, job = null;

// Screens: 1 Make Shorts from a new video, 2 Making, 3 Review/Post, 4 Posted, 5 Scheduled, 6 Analytics, 7 Vlogs, 8 Settings,
// 9 Shorts & Reels, 10 Upload a vlog to YouTube, 11 Drafts.
// The sidebar marks where the creator is (a vlog's own screens count as Vlogs).
const NAV_FOR = {1:"createBtn", 2:"vlogsNav", 3:"clipsNav", 4:"clipsNav", 5:"postedNav", 6:"analyticsNav", 7:"vlogsNav", 8:"settingsNav", 9:"clipsNav", 10:"vlogsNav", 11:"draftsNav"};
function show(n){
  [1,2,3,4,5,6,7,8,9,10,11].forEach(i=>$("s"+i).hidden = i!==n);
  if(n!==10 && typeof vuStop==="function") vuStop();  // the vlog upload page polls only while it shows
  document.querySelectorAll(".side .navlink,.side .create").forEach(b=>{ b.classList.remove("now"); b.removeAttribute("aria-current"); });
  const on=$(NAV_FOR[n]); if(on){ on.classList.add("now"); on.setAttribute("aria-current","page"); }
  if(typeof clDock==="function") clDock();  // the Shorts & Reels selection bar shows only on that page
  window.scrollTo(0,0);
}
show(1);
// Before sending a big video: still signed in? If the session ended, the server drops the upload part-way, which looks
// like a lost connection; this shows the sign-in screen instead. false = don't send (err says why if it isn't sign-in).
async function stillSignedIn(err){
  try{ const m=await (await fetch("/api/me")).json(); if(m.user) return true; showLogin(); return false; }
  catch(e){ err.textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; return false; }
}
