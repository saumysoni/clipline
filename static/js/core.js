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

// Screens: 1 New vlog, 2 Making, 3 Review/Post, 4 Posted, 5 Scheduled, 6 Analytics, 7 Vlogs, 8 Settings.
// The sidebar marks where the creator is (a vlog's own screens count as Vlogs).
const NAV_FOR = {1:"createBtn", 2:"vlogsNav", 3:"vlogsNav", 4:"vlogsNav", 5:"postedNav", 6:"analyticsNav", 7:"vlogsNav", 8:"settingsNav"};
function show(n){
  [1,2,3,4,5,6,7,8].forEach(i=>$("s"+i).hidden = i!==n);
  document.querySelectorAll(".side .navlink,.side .create").forEach(b=>{ b.classList.remove("now"); b.removeAttribute("aria-current"); });
  const on=$(NAV_FOR[n]); if(on){ on.classList.add("now"); on.setAttribute("aria-current","page"); }
  window.scrollTo(0,0);
}
show(1);
