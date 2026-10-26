// The ⋮ menu on clip and vlog cards (js/clips.js, js/vlogs.js): one shared list placed under its button with
// position:fixed, so a card's overflow:hidden can't clip it. items: {label, icon, run | href (+download), disabled
// (a reason, shown as its title), danger}. Closes on a click elsewhere, Escape, scrolling or resizing.
let cmFor=null;
const cmBox=document.createElement("div");
cmBox.className="card-menu"; cmBox.setAttribute("role","menu"); cmBox.hidden=true;
document.body.appendChild(cmBox);
function cardMenu(btn, items){
  if(cmFor===btn){ cmClose(); return; }
  cmClose();
  cmBox.innerHTML=items.map((it,i)=>{
    const inner='<span class="ms" aria-hidden="true">'+it.icon+'</span><span>'+esc(it.label)+'</span>';
    const cls=it.danger?' class="danger"':'';
    if(it.href && !it.disabled) return '<a role="menuitem"'+cls+' href="'+esc(it.href)+'"'+(it.download?' download':' target="_blank" rel="noopener"')+(it.title?' title="'+esc(it.title)+'"':'')+'>'+inner+'</a>';
    return '<button type="button" role="menuitem"'+cls+' data-i="'+i+'"'+(it.disabled?' disabled title="'+esc(it.disabled)+'"':it.title?' title="'+esc(it.title)+'"':'')+'>'+inner+'</button>';
  }).join("");
  cmBox.querySelectorAll("button[data-i]").forEach(b=>b.onclick=()=>{ cmClose(); items[+b.dataset.i].run(); });
  cmBox.querySelectorAll("a").forEach(a=>a.addEventListener("click",()=>setTimeout(cmClose)));
  cmBox.hidden=false; cmFor=btn; btn.setAttribute("aria-expanded","true");
  const r=btn.getBoundingClientRect(), w=cmBox.offsetWidth, h=cmBox.offsetHeight;
  cmBox.style.left=Math.max(8, Math.min(r.right-w, innerWidth-w-8))+"px";
  cmBox.style.top=(r.bottom+4+h > innerHeight-8 && r.top-4-h > 8 ? r.top-4-h : r.bottom+4)+"px";
  const first=cmBox.querySelector("a,button:not(:disabled)"); if(first) first.focus();
}
function cmClose(){
  if(!cmFor) return;
  cmBox.hidden=true; cmFor.setAttribute("aria-expanded","false"); cmFor=null;
}
document.addEventListener("click",e=>{ if(cmFor && !cmBox.contains(e.target) && !cmFor.contains(e.target)) cmClose(); });
document.addEventListener("keydown",e=>{ if(e.key==="Escape" && cmFor){ const b=cmFor; cmClose(); b.focus(); } });
addEventListener("scroll",cmClose,true); addEventListener("resize",cmClose);
// The ⋮ button itself.
const cmButton=label=>'<button type="button" class="iconbtn cm-more" aria-haspopup="menu" aria-expanded="false" aria-label="More for '+esc(label)+'"><span class="ms" aria-hidden="true">more_vert</span></button>';
