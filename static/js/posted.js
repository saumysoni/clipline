// Step 4: the posted / scheduled list, and going back to the Shorts.
function renderDone(){
  const ups=job.uploads||[], now=ups.length && ups.every(u=>!u.when);
  const n=ups.length===1 ? "1 Short " : ups.length+" Shorts ";
  $("doneTitle").textContent = n+(now ? "posted" : "scheduled");
  $("doneLede").textContent = now ? "They're on your channel now. You can change anything in YouTube Studio."
    : "Each Short goes public at its time. You can change anything in YouTube Studio before then.";
  $("cal").innerHTML = ups.map(u=>{
    const d=u.when?new Date(u.when):null;
    const day=d?d.toLocaleDateString(undefined,{weekday:"short"}):"Now";
    const sub=d?d.toLocaleDateString(undefined,{month:"short",day:"numeric"})+", "+d.toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"}):"Posting now";
    return '<li><div class="day">'+day+'<small>'+sub+'</small></div><div>'+esc(u.title)+(u.note?'<div class="from">'+esc(u.note)+'</div>':'')+'</div>'+
      '<a href="https://studio.youtube.com/video/'+u.video_id+'/edit" target="_blank" rel="noopener">Open in Studio<span class="ms" aria-hidden="true">open_in_new</span></a></li>';
  }).join("");
  show(4);
}

// From the Posted page back to the Shorts, e.g. to upload ones that were left unticked. Posted ones stay marked.
let onReview=false;
$("backBtn").onclick=()=>{ onReview=true; $("upPanel").hidden=true; $("err3").textContent=""; renderResults(); show(3); markPosted(); };
$("newBtn").onclick=$("againBtn").onclick=()=>{ location.hash=""; location.reload(); };
