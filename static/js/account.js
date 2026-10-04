// Clipline account: sign-in screen, and boot() which starts the app (runs last).
// ---- Clipline account: the app shows only to a signed-in user; any "sign in first" reply brings the sign-in back
let signup=false, booted=false;
function paintAuth(){
  $("authTitle").textContent = signup ? "Create your account" : "Sign in";
  $("authLede").textContent = signup ? "Free to start. Your vlogs and Shorts stay in your own account." : "Turn one vlog into a week of Shorts.";
  $("nameRow").hidden=!signup; $("authGo").textContent = signup ? "Create account" : "Sign in";
  $("authPass").autocomplete = signup ? "new-password" : "current-password";
  $("authPass").placeholder = signup ? "At least 8 characters" : "";
  $("authSwitchText").textContent = signup ? "Already have an account?" : "New to Clipline?";
  $("authSwitch").textContent = signup ? "Sign in" : "Create an account";
  $("authErr").textContent="";
}
function showLogin(){
  clearInterval(poll); $("app").hidden=true; $("auth").hidden=false; paintAuth();
  setTimeout(()=>$("authEmail").focus(),0);
}
$("authSwitch").onclick=()=>{ signup=!signup; paintAuth(); $("authEmail").focus(); };
$("authForm").onsubmit=async e=>{
  e.preventDefault(); $("authErr").textContent="";
  const body={email:$("authEmail").value,password:$("authPass").value,name:$("authName").value};
  $("authGo").disabled=true;
  let r,j; try{ r=await fetch(signup?"/api/auth/signup":"/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); j=await r.json(); }
  catch(x){ r={ok:false}; j={error:"Couldn't reach Clipline. Is the app window still open?"}; }
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
  if(!m.user){ showLogin(); return; }
  $("meEmail").textContent=m.user.email; $("meEmail").title=m.user.email;
  $("auth").hidden=true; $("app").hidden=false;
  loadAccount();
  if(booted){ if(jobId) startPolling(jobId); return; }  // signed in again mid-session: pick the job back up
  booted=true;
  if(location.hash==="#youtube") openPosted();
  else if(location.hash==="#analytics") openAnalytics();
  else if(location.hash.length>1) startPolling(location.hash.slice(1));
}
boot();
