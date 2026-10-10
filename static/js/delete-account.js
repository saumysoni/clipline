// Delete account (Settings; web/delete_account.py): type the email to confirm (Google accounts have no password).
$("setDelete").onclick=()=>{ $("setDelForm").hidden=false; $("setDelErr").textContent=""; $("setDelEmail").value=""; $("setDelEmail").focus(); };
$("setDelCancel").onclick=()=>{ $("setDelForm").hidden=true; };
$("setDelForm").onsubmit=async e=>{
  e.preventDefault(); $("setDelErr").textContent=""; $("setDelGo").disabled=true;
  let r,j; try{ r=await fetch("/api/account/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("setDelEmail").value})}); j=await r.json(); }
  catch(x){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
  $("setDelGo").disabled=false;
  if(!r.ok){ $("setDelErr").textContent=j.error||"Couldn't delete your account."; $("setDelEmail").focus(); return; }
  location.hash=""; location.reload();  // signed out: the sign-in screen
};
