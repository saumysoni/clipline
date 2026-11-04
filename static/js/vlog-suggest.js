// AI suggestions on the video upload page (web/vlog_suggest.py): under the title, the description and the tags, a request in the
// creator's own words (optional) and options to pick from. Picking one fills the field, which saves as usual and can still be edited.
const VS_FIELDS=[["vuT","title","Make it funnier, or mention the place"],["vuD","description","Shorter, and mention the food market"],["vuTags","tags","More about budget travel"]];
VS_FIELDS.forEach(([id,field,eg])=>{
  const box=document.createElement("div"); box.className="vs"; box.dataset.field=field;
  box.innerHTML='<button type="button" class="linkbtn vs-open"><span class="ms" aria-hidden="true">auto_awesome</span>AI suggestions</button>'+
    '<div class="vs-panel" hidden><label class="vs-lab">What would you like? <small>optional</small><input type="text" class="vs-ask" maxlength="300" placeholder="'+esc(eg)+'"></label>'+
    '<button type="button" class="ghost sm vs-go">Suggest</button><div class="err vs-err" role="alert"></div><div class="vs-out"></div></div>';
  const target=$(id==="vuD"?"vuDCount":id==="vuTags"?"vuTagsCount":"vuIdeas"); target.after(box);
  const panel=box.querySelector(".vs-panel"), go=box.querySelector(".vs-go"), out=box.querySelector(".vs-out"), err=box.querySelector(".vs-err"), ask=box.querySelector(".vs-ask");
  box.querySelector(".vs-open").onclick=()=>{ panel.hidden=!panel.hidden; if(!panel.hidden) ask.focus(); };
  ask.addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); go.click(); } });
  go.onclick=async()=>{
    const job=vuId; err.textContent=""; go.disabled=true; go.textContent="Writing..."; out.innerHTML="";
    let r,j; try{ r=await fetch("/api/vlog/"+job+"/suggest",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({field,ask:ask.value.trim(),title:$("vuT").value,description:$("vuD").value,tags:vuTagList()})}); j=await r.json(); }
    catch(e){ r={ok:false}; j={error:"Couldn't reach Pit Crew. Check your internet connection, then try again."}; }
    go.disabled=false; go.textContent="Suggest"; if(job!==vuId) return;
    if(!r.ok){ err.textContent=j.error||"Couldn't write suggestions. Try again."; return; }
    out.innerHTML=j.items.map((t,i)=>'<div class="vs-opt"><span class="vs-t">'+esc(Array.isArray(t)?t.join(", "):t)+'</span><button type="button" class="ghost sm" data-i="'+i+'">Use this</button></div>').join("");
    out.querySelectorAll("button").forEach(b=>b.onclick=()=>{
      const t=j.items[+b.dataset.i]; $(id).value=Array.isArray(t)?t.join(", "):t; vuChanged();
      out.querySelectorAll(".vs-opt").forEach(o=>o.classList.remove("on")); b.closest(".vs-opt").classList.add("on");
    });
  };
});
