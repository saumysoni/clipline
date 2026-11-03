// Step 1 form: how many Shorts, and the plan summary.
// ---- form
function renderCount(){
  const must=typeof mustRows==="function" ? mustRows().length : 0;
  const box=$("countPick");
  if(!box.children.length){  // 1 to 10: one press, no steppers
    box.innerHTML=Array.from({length:10},(_,i)=>'<button type="button" role="radio" data-n="'+(i+1)+'">'+(i+1)+'</button>').join("");
    box.querySelectorAll("button").forEach(b=>b.onclick=()=>{
      const n=+b.dataset.n, least=mustRows().length;
      if(n<least){ $("countHint").textContent="You chose "+least+" must-have moments, so at least "+least+" Shorts. Remove a moment to make fewer."; return; }
      count=n; renderCount(); if(!$("mustHint").classList.contains("bad")) mustCountHint();
    });
    // arrow keys move along the row, like any radio group
    box.addEventListener("keydown",e=>{
      const d={ArrowRight:1,ArrowUp:1,ArrowLeft:-1,ArrowDown:-1}[e.key]; if(!d) return;
      e.preventDefault(); const n=Math.max(1,Math.min(10,count+d)); box.querySelector('[data-n="'+n+'"]').click(); box.querySelector('[data-n="'+count+'"]').focus();
    });
  }
  box.querySelectorAll("button").forEach(b=>{ const n=+b.dataset.n, on=n===count;
    b.setAttribute("aria-checked",on); b.tabIndex=on?0:-1; b.classList.toggle("least",n<must); });
  $("countTag").textContent=count+(count===1?" Short":" Shorts");
  $("countHint").textContent=must?must+" of them "+(must===1?"is":"are")+" your must-have moment"+(must===1?"":"s")+". Pit Crew picks the rest.":"";
  $("make").innerHTML = '<span class="ms" aria-hidden="true">auto_awesome</span>'+(count===1 ? "Make my Short" : "Make my "+count+" Shorts")+'<span class="ms" aria-hidden="true">arrow_forward</span>';
  paintPlan();
}
// The "Your plan" summary next to the form.
function paintPlan(){
  if(!$("sumCount")) return;
  const f=$("file").files[0], link=$("link").value.trim();
  const linkOk = link && linkKind(link)==="drive_file";
  $("sumVlog").textContent = f ? f.name : linkOk ? "Google Drive link" : link ? "Check the link" : "Not added yet";
  $("sumVlog").classList.toggle("todo",!f&&!linkOk);
  $("sumCount").textContent = count;
  const k=typeof mustRows==="function" ? mustRows().length : 0;
  $("sumMust").textContent = k ? k+" of "+count : "None";
  $("mustTag").textContent = k ? k+" / "+count+" chosen" : "Optional";
  const st=document.querySelector("input[name=style]:checked");
  $("sumStyle").textContent = st ? st.closest("label").querySelector("small").textContent : "";
}
renderCount();
