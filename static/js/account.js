// Pit Crew account: sign-in screen, and boot() which starts the app (runs last).
// ---- Pit Crew account: the app shows only to a signed-in user; any "sign in first" reply brings the sign-in back
let signup=false, booted=false, myEmail="";
function paintAuth(){
  $("authTitle").textContent = signup ? "Create your account" : "Sign in";
  $("authLede").textContent = signup ? "Free to start. Your vlogs and Shorts stay in your own account." : "Turn one vlog into a week of Shorts.";
  $("nameRow").hidden=!signup; $("authGo").textContent = signup ? "Create account" : "Sign in";
  $("authPass").autocomplete = signup ? "new-password" : "current-password";
  $("authPass").placeholder = signup ? "At least 8 characters" : "";
  $("authSwitchText").textContent = signup ? "Already have an account?" : "New to Pit Crew?";
  $("authSwitch").textContent = signup ? "Sign in" : "Create an account";
  $("forgotBtn").hidden=signup;
  $("authErr").textContent="";
}
function showLogin(){
  showAuthForm("authForm"); paintAuth();
  setTimeout(()=>$("authEmail").focus(),0);
}
$("authSwitch").onclick=()=>{ signup=!signup; paintAuth(); $("authEmail").focus(); };
$("authForm").onsubmit=async e=>{
  e.preventDefault(); $("authErr").textContent="";
  const body={email:$("authEmail").value,password:$("authPass").value,name:$("authName").value};
  $("authGo").disabled=true;
  let r,j; try{ r=await fetch(signup?"/api/auth/signup":"/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); j=await r.json(); }
  catch(x){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("authGo").disabled=false;
  if(!r.ok){ $("authErr").textContent=j.error||"Couldn't sign in."; if(j.field==="password") $("authPass").focus(); else $("authEmail").focus(); return; }
  $("authPass").value=""; boot();
};
$("logoutBtn").onclick=async()=>{ try{ await fetch("/api/auth/logout",{method:"POST"}); }catch(x){} location.hash=""; location.reload(); };
// Any reply that says "sign in first" (the session ended) shows the sign-in screen.
const rawFetch=window.fetch.bind(window);
window.fetch=async(...a)=>{ const r=await rawFetch(...a); if(r.status===401) showLogin(); return r; };
async function boot(){
  let m; try{ m=await (await rawFetch("/api/me")).json(); }catch(x){ m={user:null,google:false}; }
  $("googleBtn").hidden=$("authOr").hidden=!m.google;
  if(location.hash.startsWith("#reset=")){ showReset(location.hash.slice(7)); return; }  // link from a reset email
  if(m.auth_error){  // Google sign-in didn't work (e.g. the email already has a password account): say so in red
    signup=false; showLogin();
    if(m.auth_error.email) $("authEmail").value=m.auth_error.email;
    $("authErr").textContent=m.auth_error.error; return;
  }
  if(!m.user){ showLogin(); return; }
  myEmail=m.user.email; $("meEmail").textContent=myEmail; $("accountNav").title=myEmail;
  $("auth").hidden=true; $("app").hidden=false;
  loadAccount(); loadIg(); refreshJobsNow();
  if(booted){ if(jobId) startPolling(jobId); return; }  // signed in again mid-session: pick the job back up
  booted=true;
  openRoute(location.hash.slice(1));
}
// The screen for an address (#vlogs, #new, #youtube, #analytics, #settings, or a vlog's id). The Vlogs page is home.
function openRoute(h){
  if(h==="youtube") openPosted();
  else if(h==="analytics") openAnalytics();
  else if(h==="settings") openSettings();
  else if(h==="new") openCreate();
  else if(/^[0-9a-f]{10}$/.test(h)) startPolling(h);
  else openVlogs();
}
// The browser's Back and Forward buttons change the address: show that screen. Addresses Pit Crew sets itself
// match the screen already showing, so they're left alone.
window.addEventListener("hashchange",()=>{
  if(!booted || $("app").hidden) return;
  const h=location.hash.slice(1);
  if(h.startsWith("reset=")) return;
  const at = !$("s7").hidden?"vlogs" : !$("s5").hidden?"youtube" : !$("s6").hidden?"analytics" : !$("s8").hidden?"settings" : !$("s1").hidden?"new" : jobId;
  if(h===at || (!h && at==="vlogs")) return;
  openRoute(h);
});
boot();
