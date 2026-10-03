// Step 1 form: how many Shorts, and the plan summary.
// ---- form
function renderCount(){
  $("num").textContent = count; $("minus").disabled = count<=1; $("plus").disabled = count>=10;
  const mine=typeof mustRows==="function" ? Math.min(count,mustRows().length) : 0;
  $("frames").innerHTML = Array.from({length:count},(_,i)=>'<span class="'+(i<mine?"mine":"")+'">'+(i+1)+'</span>').join("");
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
  $("sumSched").textContent = {d18:"One a day, 6 PM",d12:"One a day, 12 PM",two:"Two a day",now:"All at once",custom:"Your own times"}[$("sched").value]||"";
}
$("minus").onclick=()=>{count=Math.max(1,mustRows().length,count-1);renderCount();if(!$("mustHint").classList.contains("bad")) mustCountHint();};
$("plus").onclick=()=>{count=Math.min(10,count+1);renderCount();if(!$("mustHint").classList.contains("bad")) mustCountHint();};
renderCount();
