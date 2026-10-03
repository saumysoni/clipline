// Light / dark / match the computer.
// ---- light / dark / match the computer (remembered on this computer only)
function paintTheme(){
  let t="auto"; try{ t=localStorage.getItem("clipline-theme")||"auto"; }catch(e){}
  document.querySelectorAll("[data-theme-set]").forEach(b=>b.setAttribute("aria-pressed",b.dataset.themeSet===t));
}
document.querySelectorAll("[data-theme-set]").forEach(b=>b.onclick=()=>{
  const t=b.dataset.themeSet;
  if(t==="auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme",t);
  try{ localStorage.setItem("clipline-theme",t); }catch(e){}
  paintTheme();
});
paintTheme();
