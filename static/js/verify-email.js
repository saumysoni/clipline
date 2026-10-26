// Confirm your email (web/verify_email.py): the link from the welcome email (#verify=<token>). Pit Crew can't be used
// before it's confirmed: showVerify() is the only screen (Resend, Change email, Sign out), and it carries on by itself
// once the link is opened, here or on another device.
let verifyNote="";  // what the link did, shown once boot() knows whether the creator is signed in
async function confirmEmail(token){
  history.replaceState(null,"",location.pathname);  // the token is used once: don't leave it in the address bar
  let r,j; try{ r=await fetch("/api/auth/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token})}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then open the link again."}; }
  verifyNote = r.ok ? "Email confirmed. Pit Crew will email you when your Shorts are ready." : (j.error||"Couldn't confirm your email.");
  return r.ok;
}
// Signed in: the bar (not confirmed yet, or what the link just did).
function paintVerifyBar(user){
  const bar=$("verifyBar"), ok=verifyNote.startsWith("Email confirmed");
  if(verifyNote){
    bar.className="verify-bar"+(ok?" ok":""); bar.hidden=false;
    bar.innerHTML='<span class="ms" aria-hidden="true">'+(ok?"check_circle":"error")+'</span><span class="vb-t">'+esc(verifyNote)+'</span>'+
      (ok?'<button type="button" class="linkbtn" id="vbClose">OK</button>':'<button type="button" class="linkbtn" id="vbSend">Resend</button>');
    verifyNote="";
  }else if(!user.verified){
    bar.className="verify-bar"; bar.hidden=false;
    bar.innerHTML='<span class="ms" aria-hidden="true">mark_email_unread</span><span class="vb-t">Confirm <b>'+esc(user.email)+
      '</b> so Pit Crew can email you when your Shorts are ready.</span><button type="button" class="linkbtn" id="vbSend">Send link</button>';
  }else{ bar.hidden=true; return; }
  if($("vbClose")) $("vbClose").onclick=()=>{ bar.hidden=true; };
  if($("vbSend")) $("vbSend").onclick=async()=>{
    $("vbSend").disabled=true;
    let j; try{ j=await (await fetch("/api/auth/verify/resend",{method:"POST"})).json(); }
    catch(e){ j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
    bar.querySelector(".vb-t").textContent=j.error||j.message; $("vbSend").disabled=false;
  };
}

let vfTimer=null;
function showVerify(user){
  showAuthForm("verifyForm");
  $("vfEmail").textContent=user.email; $("vfNewEmail").value=user.email;
  $("vfPassRow").hidden=!user.has_password;
  if(verifyNote){ $(verifyNote.startsWith("Email confirmed")?"vfOk":"vfErr").textContent=verifyNote; verifyNote=""; }
  clearInterval(vfTimer);
  vfTimer=setInterval(async()=>{  // opened the link on another device? carry on
    if($("verifyForm").hidden){ clearInterval(vfTimer); return; }
    try{ const m=await (await rawFetch("/api/me")).json(); if(!m.user || m.user.verified){ clearInterval(vfTimer); boot(); } }catch(e){}
  },5000);
}
$("vfResend").onclick=async()=>{
  $("vfErr").textContent=$("vfOk").textContent=""; $("vfResend").disabled=true;
  let r,j; try{ r=await fetch("/api/auth/verify/resend",{method:"POST"}); j=await r.json(); }
  catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  $("vfResend").disabled=false; $(r.ok?"vfOk":"vfErr").textContent=j.error||j.message;
};
$("vfChangeBtn").onclick=()=>{ $("vfChange").hidden=false; $("vfNewEmail").focus(); };
$("verifyForm").onsubmit=async e=>{
  e.preventDefault(); $("vfErr").textContent=$("vfOk").textContent="";
  let r,j; try{ r=await fetch("/api/auth/email",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({email:$("vfNewEmail").value,password:$("vfPass").value})}); j=await r.json(); }
  catch(x){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  if(!r.ok){ $("vfErr").textContent=j.error; return; }
  $("vfEmail").textContent=j.email; $("vfChange").hidden=true; $("vfPass").value=""; $("vfOk").textContent=j.message;
};
$("vfOut").onclick=async()=>{ try{ await fetch("/api/auth/logout",{method:"POST"}); }catch(x){} location.hash=""; location.reload(); };
