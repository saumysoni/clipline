// Thumbnail look on each Short's card: Scene / Burst / Bold. Redrawn on the server from the frames
// saved when the thumbnail was made (no AI), so switching takes a few seconds.
const LOOK_NAMES={scene:"Scene",burst:"Burst",bold:"Bold"};
let showThumbFor=null;  // after a redraw, the new card opens on its thumbnail
function lookHTML(s){
  if(!s.thumb) return "";
  return '<div class="looks" role="group" aria-label="Thumbnail look"><span class="small-lab">Look</span>'+
    Object.entries(LOOK_NAMES).map(([k,n])=>'<button type="button" data-look="'+k+'" aria-pressed="'+(s.thumb_look===k)+'">'+n+'</button>').join("")+'</div>';
}
function wireLook(el,s){
  const box=el.querySelector(".looks"); if(!box||!s) return;
  if(showThumbFor===s.idx){ showThumbFor=null; const t=el.querySelector('.toggle button[data-v="t"]'); if(t) t.click(); }
  box.querySelectorAll("button").forEach(b=>b.onclick=async()=>{
    if(b.getAttribute("aria-pressed")==="true") return;
    const err=el.querySelector(".rerr"); err.textContent="";
    const t=el.querySelector('.toggle button[data-v="t"]'); if(t) t.click();
    showThumbFor=s.idx;
    if(!await sendMoment("/api/look/"+jobId+"/"+s.idx,{look:b.dataset.look},err)) showThumbFor=null;
  });
}
