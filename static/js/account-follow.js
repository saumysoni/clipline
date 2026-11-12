// Shorts & Reels and Videos show the YouTube channel and Instagram account chosen in the sidebar (onActive in js/core.js).
// Switching (or disconnecting) shows a short "Loading" over the page while it reloads: at least AF_MIN ms, so the change
// reads as a change and not as a blink. Called by switchedAccount() in js/account-switcher.js.
const AF_MIN=1000;
let afRun=0;
async function followAccount(){
  const on = !$("s9").hidden ? {page:$("s9"), load:loadClips, what:"Shorts and Reels"}
           : !$("s7").hidden ? {page:$("s7"), load:loadVlogs, what:"videos"} : null;
  if(!on) return;
  const box=on.page.querySelector(".work")||on.page, run=++afRun, t0=Date.now();
  let o=box.querySelector(".af-wait");
  if(!o){ o=document.createElement("div"); o.className="af-wait"; o.setAttribute("role","status"); box.appendChild(o); }
  const who=[yt.signed_in&&yt.channel&&yt.channel.title, ig.signed_in&&ig.username&&"@"+ig.username].filter(Boolean);
  o.innerHTML='<span class="af-spin" aria-hidden="true"></span><b>Loading '+esc(on.what)+'</b>'+
    (who.length?'<small>'+esc(who.join(" · "))+'</small>':'');
  box.classList.add("af-busy");
  try{ await on.load(); }catch(e){}
  await new Promise(r=>setTimeout(r, Math.max(0, AF_MIN-(Date.now()-t0))));
  if(run===afRun) box.classList.remove("af-busy");  // a second switch meanwhile keeps it up until that one is done
}
// The accounts' details arrive after the page may already be drawn (signing in, connecting one): draw it again for them.
function afRepaint(){
  if(!$("s9").hidden && clMode==="out") paintClips();
  else if(!$("s7").hidden && vlData) paintVlogs();
}
