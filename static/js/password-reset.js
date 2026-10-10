// Forgot password: ask for a reset link by email, and choose a new password from the link (/#reset=<token>).
// showAuthForm() switches between the sign-in, forgot and reset cards (account.js uses it too).
let resetToken="";
function showAuthForm(id){
  clearInterval(poll); $("app").hidden=true; $("auth").hidden=false;
  for(const f of ["authForm","forgotForm","resetForm"]) $(f).hidden = f!==id;
}
function backToSignIn(){
  if(location.hash.startsWith("#reset=")) history.replaceState(null,"",location.pathname);
  resetToken=""; showLogin();
}
async function authPost(url,body){
  try{ const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); return [r.ok, await r.json()]; }
  catch(x){ return [false,{error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}]; }
}
$("forgotBtn").onclick=()=>{
  showAuthForm("forgotForm"); $("forgotErr").textContent=$("forgotOk").textContent="";
  $("forgotEmail").value=$("authEmail").value; $("forgotGo").disabled=false;
  setTimeout(()=>$("forgotEmail").focus(),0);
};
$("forgotBack").onclick=$("resetBack").onclick=backToSignIn;
$("forgotForm").onsubmit=async e=>{
  e.preventDefault(); $("forgotErr").textContent=$("forgotOk").textContent="";
  $("forgotGo").disabled=true;
  const [ok,j]=await authPost("/api/auth/forgot",{email:$("forgotEmail").value});
  $("forgotGo").disabled=false;
  if(!ok){ $("forgotErr").textContent=j.error||"Couldn't send the link."; $("forgotEmail").focus(); return; }
  $("forgotOk").textContent=j.message; $("authEmail").value=$("forgotEmail").value;
};
function showReset(token){
  resetToken=token; showAuthForm("resetForm");
  $("resetErr").textContent=""; $("resetPass").value=""; $("resetGo").disabled=false;
  setTimeout(()=>$("resetPass").focus(),0);
}
$("resetForm").onsubmit=async e=>{
  e.preventDefault(); $("resetErr").textContent="";
  $("resetGo").disabled=true;
  const [ok,j]=await authPost("/api/auth/reset",{token:resetToken,password:$("resetPass").value});
  $("resetGo").disabled=false;
  if(!ok){ $("resetErr").textContent=j.error||"Couldn't save the new password."; if(!j.expired) $("resetPass").focus(); return; }
  $("resetPass").value=""; resetToken=""; history.replaceState(null,"",location.pathname); boot();
};
