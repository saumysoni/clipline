// Thumbnail on each Short's card: switch between Frame and Duotone, and download it. A switch is
// redrawn on the server from the frames saved when the thumbnail was made (no AI, about a second).
const LOOK_NAMES={frame:"Frame",duotone:"Duotone"};
let showThumbFor=null;  // after a redraw, the new card opens on its thumbnail
function lookHTML(s){
  if(!s.thumb) return "";
  return '<div class="looks" role="group" aria-label="Thumbnail look"><span class="small-lab">Look</span>'+
    Object.entries(LOOK_NAMES).map(([k,n])=>'<button type="button" data-look="'+k+'" aria-pressed="'+(s.thumb_look===k)+'">'+n+'</button>').join("")+
    '<a class="dl" href="/media/'+job.id+'/'+esc(s.thumb)+'?dl='+encodeURIComponent(thumbFileName(s))+'" download="'+esc(thumbFileName(s))+'" title="Download the thumbnail" aria-label="Download the thumbnail"><span class="ms" aria-hidden="true">download</span></a></div>';
}
function thumbFileName(s){
  const t=String(s.title||"Short "+s.idx).replace(/[\\/:*?"<>|]+/g,"").trim().slice(0,60)||"Short "+s.idx;
  return t+" - thumbnail.jpg";
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
