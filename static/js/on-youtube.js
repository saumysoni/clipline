// Scheduled page, YouTube part: every uploaded Short (change time, edit, unmark). Instagram: scheduled-instagram.js.
// ---- On YouTube: every uploaded Short, with Change time / Edit Short / Open in Studio
function stateTag(u){
  const st=u.state;
  if(st && st.privacy==="missing") return '<span class="tag bad">Not found on YouTube</span>';
  if(st && st.privacy==="other_channel") return '<span class="tag">On another channel</span>';
  if(st && st.privacy==="private" && st.publish_at && new Date(st.publish_at)>new Date()) return '<span class="tag good">Scheduled</span>';
  if(st && st.privacy==="private") return '<span class="tag">Private</span>';
  if(st && st.privacy) return '<span class="tag good">'+(st.privacy==="public"?"Public":"Unlisted")+'</span>';
  return u.when && new Date(u.when)>new Date() ? '<span class="tag good">Scheduled</span>' : '<span class="tag">Posted</span>';
}
function localInput(d){ const p=x=>String(x).padStart(2,"0"); return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+"T"+p(d.getHours())+":"+p(d.getMinutes()); }
async function openPosted(){
  clearInterval(poll); location.hash="youtube"; show(5);
  if(typeof loadIgScheduled==="function") loadIgScheduled();
  $("plist").innerHTML='<li><span></span><span class="pv">Checking YouTube...</span></li>'; $("ptNote").hidden=true;
  let j; try{ j=await (await fetch("/api/posted")).json(); }catch(e){ j={items:[],note:"Couldn't reach Clipline. Is the app window still open?"}; }
  const notes=[];
  if(j.note) notes.push(j.note);
  else if(!j.signed_in && j.items.length) notes.push("Connect YouTube to see each Short's live status and change it.");
  if(j.items.some(u=>u.state&&u.state.privacy==="private"&&!u.state.publish_at)) notes.push("Private Shorts: YouTube keeps uploads private until your Google project passes YouTube's API audit (README step 5). Set them public in YouTube Studio.");
  $("ptNote").hidden=!notes.length; $("ptNote").innerHTML='<span class="ms" aria-hidden="true">info</span><span>'+notes.map(esc).join("<br>")+'</span>';
  if(!j.items.length){ $("plist").innerHTML='<li><span></span><span class="pv">Nothing uploaded yet. Shorts you upload to YouTube from Clipline show up here.</span></li>'; return; }
  j.items.sort((a,b)=>{ const ta=a.state&&a.state.publish_at||a.when||"", tb=b.state&&b.state.publish_at||b.when||""; return tb.localeCompare(ta); });
  $("plist").innerHTML=j.items.map((u,i)=>{
    const st=u.state||{}, gone=st.privacy==="missing", other=st.privacy==="other_channel";
    const when=st.publish_at && st.privacy==="private" ? st.publish_at : u.when;
    const canMove=!gone && !other && (!st.privacy || st.privacy==="private");
    return '<li data-i="'+i+'"><img src="/media/'+esc(u.job)+'/'+esc(u.thumb)+'" alt="">'+
      '<div><div class="pt">'+esc(u.title)+'</div><div class="pv">From '+esc(u.vlog)+'</div>'+
      '<div class="pw">'+stateTag(u)+'<span>'+(gone?"Deleted in YouTube Studio, or uploaded to a different channel?":other?"Connect that channel to change it.":esc(whenText(st.privacy&&st.privacy!=="private"?null:when)))+'</span>'+
        (u.changed?'<span class="tag cap">Edited, not updated on YouTube</span>':'')+'</div>'+
      '<div class="pa">'+(canMove?'<button type="button" class="linkbtn mv"><span class="ms" aria-hidden="true">schedule</span>Change time</button>':'')+
        '<button type="button" class="linkbtn ed"><span class="ms" aria-hidden="true">edit</span>Edit Short</button>'+
        (gone?'<button type="button" class="linkbtn um">Unmark it so I can upload it again</button>':'')+
        (gone||other?'':thumbLink(u.job,u)+'<a href="'+esc(studioLink(u.video_id))+'" target="_blank" rel="noopener">Open in Studio<span class="ms" aria-hidden="true">open_in_new</span></a>')+'</div>'+
      '<div class="pform" hidden><input type="datetime-local" aria-label="New date and time"><button type="button" class="primary sv">Save time</button><button type="button" class="ghost cn">Cancel</button></div>'+
      '<div class="err" role="alert"></div></div></li>';
  }).join("");
  $("plist").querySelectorAll("li[data-i]").forEach(li=>{
    const u=j.items[+li.dataset.i], form=li.querySelector(".pform"), inp=form.querySelector("input"), err=li.querySelector(".err");
    const mv=li.querySelector(".mv");
    if(mv) mv.onclick=()=>{
      if(!j.signed_in){ signIn(); return; }
      const cur=(u.state&&u.state.publish_at)||u.when; const d=cur?new Date(cur):new Date(Date.now()+86400000);
      inp.min=localInput(new Date(Date.now()+16*60000)); inp.value=localInput(d<new Date()?new Date(Date.now()+3600000):d);
      form.hidden=false; inp.focus();
    };
    form.querySelector(".cn").onclick=()=>{ form.hidden=true; err.textContent=""; };
    form.querySelector(".sv").onclick=async()=>{
      err.textContent=""; let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
      const b=form.querySelector(".sv"); b.disabled=true; b.textContent="Saving...";
      let r,k; try{ r=await fetch("/api/reschedule/"+u.job+"/"+u.idx,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:inp.value,tz})}); k=await r.json(); }
      catch(e){ r={ok:false}; k={error:"Couldn't reach Clipline. Is the app window still open?"}; }
      b.disabled=false; b.textContent="Save time";
      if(!r.ok){ err.textContent=k.error||"Couldn't change the time."; return; }
      openPosted();
    };
    li.querySelector(".ed").onclick=()=>openJob(u.job,u.idx);
    const um=li.querySelector(".um");
    if(um) um.onclick=async()=>{
      if(!confirm("Unmark \""+u.title+"\"?\n\nOnly do this if it's really gone from YouTube. Clipline will then let you upload it again.")) return;
      const r=await fetch("/api/unmark/"+u.job+"/"+u.idx,{method:"POST"}); if(!r.ok){ err.textContent=(await r.json()).error||"Couldn't unmark it."; return; }
      openPosted();
    };
  });
}
let focusIdx=null;
function openJob(id,idx){ onReview=true; focusIdx=idx; $("reel").innerHTML=""; startPolling(id); }
$("postedBtn").onclick=$("postedBtn4").onclick=$("postedNav").onclick=openPosted;
$("ptNew").onclick=()=>{ location.hash=""; location.reload(); };
