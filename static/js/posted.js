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
      '<span class="acts">'+thumbLink(job.id,u)+relatedLink()+
      '<a href="https://studio.youtube.com/video/'+u.video_id+'/edit" target="_blank" rel="noopener">Open in Studio<span class="ms" aria-hidden="true">open_in_new</span></a></span></li>';
  }).join("");
  show(4);
}

// "Copy vlog title": for the Related video search in Studio (there's no way to set it from an app).
function relatedLink(){
  const t=job && job.vlog && job.vlog.title;
  return t ? '<button type="button" class="linkbtn cprel" data-t="'+esc(t)+'"><span class="ms" aria-hidden="true">content_copy</span>Copy vlog title</button>' : "";
}
document.addEventListener("click",async e=>{
  const b=e.target.closest(".cprel"); if(!b) return;
  try{ await navigator.clipboard.writeText(b.dataset.t); }
  catch(err){ const ta=document.createElement("textarea"); ta.value=b.dataset.t; document.body.appendChild(ta); ta.select(); try{ document.execCommand("copy"); }catch(x){} ta.remove(); }
  const lab=b.lastChild; const was=lab.textContent; lab.textContent="Copied"; setTimeout(()=>{ lab.textContent=was; },1500);
});
// "Download thumbnail" next to "Open in Studio": the image to upload in YouTube Studio.
function thumbLink(jid,u){
  if(!u.thumb) return "";
  const name=thumbFileName({title:u.title,idx:u.idx});
  return '<a href="/media/'+esc(jid)+'/'+esc(u.thumb)+'?dl='+encodeURIComponent(name)+'" download="'+esc(name)+'"><span class="ms" aria-hidden="true">download</span>Download thumbnail</a>';
}

// From the Posted page back to the Shorts, e.g. to upload ones that were left unticked. Posted ones stay marked.
let onReview=false;
$("backBtn").onclick=()=>{ onReview=true; $("upPanel").hidden=true; $("err3").textContent=""; renderResults(); show(3); showPost(false); markPosted(); };
$("newBtn").onclick=$("againBtn").onclick=()=>{ location.hash=""; location.reload(); };
