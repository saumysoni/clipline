// Review cards as YouTube-sized tiles (like a channel's Shorts tab): thumbnail, title and "Post this".
// Clicking a tile opens the whole card (player, look, title, hook, Try again...) as a panel over the page.
// The card element itself is what opens, so everything that reads the cards keeps working.
let openIdx=null;
function tileCapHTML(s){
  return '<div class="tile-cap"><div class="tile-title">'+esc(s.title)+'</div>'+
    '<div class="tile-meta">'+Math.round(s.end-s.start)+'s'+(s.manual?' · your pick':'')+'</div></div>'+
    '<button type="button" class="tile-x" aria-label="Close"><span class="ms" aria-hidden="true">close</span></button>';
}
function openTile(el){
  if(!el || el.classList.contains("open")) return;
  closeTile();
  const ph=document.createElement("div"); ph.className="tile-place"; ph.style.height=el.offsetHeight+"px";
  el.before(ph); el.classList.add("open"); openIdx=el.dataset.idx||"add";
  $("tileShade").hidden=false; document.body.classList.add("tile-open");
  el.setAttribute("role","dialog"); el.setAttribute("aria-modal","true");
  const x=el.querySelector(".tile-x"); if(x) x.focus({preventScroll:true});
}
function closeTile(){
  const el=document.querySelector(".short.open"); openIdx=null;
  $("tileShade").hidden=true; document.body.classList.remove("tile-open");
  document.querySelectorAll(".tile-place").forEach(p=>p.remove());
  if(!el) return;
  el.classList.remove("open"); el.removeAttribute("role"); el.removeAttribute("aria-modal");
  el.querySelectorAll("video").forEach(v=>v.pause());
}
function wireTile(el){
  if(el.classList.contains("pending")) return;
  const phone=el.querySelector(".phone"), cap=el.querySelector(".tile-cap"), x=el.querySelector(".tile-x");
  const open=e=>{ if(!el.classList.contains("open")){ e.preventDefault(); openTile(el); } };
  if(phone) phone.addEventListener("click",open,true);  // first click opens; inside the panel the player works
  if(cap) cap.onclick=open;
  if(x) x.onclick=e=>{ e.stopPropagation(); closeTile(); };
  const title=el.querySelector("input.title"), tt=el.querySelector(".tile-title");
  if(title && tt) title.addEventListener("input",()=>{ tt.textContent=title.value; });
  // Saved as it's edited (a second after typing stops), so the new title is used wherever the Short is posted from.
  if(title) title.addEventListener("input",()=>{ clearTimeout(title._save); title._save=setTimeout(()=>{
    const s=job.shorts.find(x=>x.idx===+el.dataset.idx), v=title.value.trim();
    if(!s || !v || v===s.title) return;
    s.title=v; fetch("/api/clips/"+job.id+"/"+s.idx+"/title",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:v})}).catch(()=>{});
  },1000); });
  if(openIdx===el.dataset.idx) openTile(el);  // redrawn while open (a new thumbnail, a remade Short)
}
$("tileShade").onclick=closeTile;
document.addEventListener("keydown",e=>{ if(e.key==="Escape" && openIdx!==null && !$("picker").open) closeTile(); });
