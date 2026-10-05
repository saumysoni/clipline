// Settings: the account (change password, sign out), every connected YouTube channel and Instagram account
// (use / disconnect / add), and appearance (theme.js handles its buttons).
function openSettings(){ clearInterval(poll); location.hash="settings"; show(8); $("setPassOk").textContent=""; paintSettings(); loadAccount(); loadIg(); }
function setRows(list, kind){
  const isYt=kind==="yt", conf=(isYt?yt:ig).configured;
  if(!conf) return '<p class="set-note"><span class="ms" aria-hidden="true">info</span>'+(isYt
    ? "YouTube posting isn't set up yet: Pit Crew needs the Google client file in the app's folder (README step 5)."
    : "Instagram posting isn't set up yet: Pit Crew needs a Meta app. Put its INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET in the .env file (README step 6), then restart Pit Crew.")+'</p>';
  const rows=list.map(i=>'<div class="set-row" data-id="'+esc(i.id)+'">'+
    (i.pic?'<img src="'+esc(i.pic)+'" alt="" referrerpolicy="no-referrer">':'<span class="ms" aria-hidden="true">'+(isYt?"smart_display":"photo_camera")+'</span>')+
    '<span class="set-t"><b>'+esc(i.name)+'</b><small'+(i.ok?'':' class="warn"')+'>'+(i.active?"New "+(isYt?"Shorts":"Reels")+" go here":esc(i.sub||""))+'</small></span>'+
    '<span class="set-acts">'+(i.active?'<span class="tag good">In use</span>':'<button type="button" class="linkbtn s-use">Use this one</button>')+
    '<button type="button" class="linkbtn s-out">Disconnect</button></span></div>').join("");
  return (rows||'<p class="set-note">'+(isYt?"No YouTube channel connected yet.":"No Instagram account connected yet.")+'</p>')+
    '<button type="button" class="ghost s-add"><span class="ms" aria-hidden="true">add</span>'+(isYt?"Add channel":"Add account")+'</button>';
}
function paintSettings(){
  if($("s8").hidden) return;
  $("setEmail").textContent=myEmail;
  for(const kind of ["yt","ig"]){
    const box=$(kind==="yt"?"setYt":"setIg"), isYt=kind==="yt";
    box.innerHTML=setRows(swItems(kind), kind);
    box.querySelectorAll(".set-row").forEach(r=>{
      const id=r.dataset.id;
      if(r.querySelector(".s-use")) r.querySelector(".s-use").onclick=()=>switchTo(kind,id);
      r.querySelector(".s-out").onclick=()=>isYt?signOut(id):igSignOut(id);
    });
    const add=box.querySelector(".s-add"); if(add) add.onclick=()=>isYt?signIn():igSignIn(null,(ig.accounts||[]).length>0);
  }
}
// Change password: the same email link as Forgot password (proves it's really them).
$("setPass").onclick=async()=>{
  $("setPass").disabled=true;
  let j; try{ j=await (await fetch("/api/auth/forgot",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:myEmail})})).json(); }
  catch(e){ j={error:"Couldn't reach Pit Crew. Is the app window still open?"}; }
  $("setPass").disabled=false;
  $("setPassOk").textContent = j.error ? "" : "We've emailed you a link to choose a new password. It works for 1 hour.";
  if(j.error) $("setPassOk").textContent=j.error;
};
