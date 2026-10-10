// Help (SUPPORT_EMAIL, from /api/config): a Help link in the sidebar, and "Get help" with a reference (the vlog's id) on a
// vlog that stopped, so "if it keeps happening, tell us" leads somewhere and we can find what went wrong
// (job["error_detail"]). Nothing shows when SUPPORT_EMAIL isn't set.
let helpEmail="";
function helpHref(ref){ return "mailto:"+helpEmail+"?subject="+encodeURIComponent("Pit Crew help"+(ref?" (reference "+ref+")":"")); }
// The bit after a stopped vlog's error (progress.js, vlog-upload.js).
function helpLine(ref){
  return helpEmail ? ' <a class="linkbtn" href="'+esc(helpHref(ref))+'">Get help</a> <small class="help-ref">Reference '+esc(ref)+'</small>' : "";
}
function paintHelp(){
  let a=$("helpNav");
  if(!helpEmail){ if(a) a.remove(); return; }
  if(!a){
    $("settingsNav").insertAdjacentHTML("afterend",'<a class="navlink sm" id="helpNav" href="#" style="text-decoration:none;color:inherit"><span class="st-ic"><span class="ms" aria-hidden="true">help</span></span><span><b>Help</b></span></a>');
    a=$("helpNav");
  }
  a.href=helpHref("");
}
