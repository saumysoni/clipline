// Must-have moments: the creator's own From/To times.
// ---- must-have moments (the server checks these again)
const parseTime=t=>{ t=String(t||"").trim(); if(!/^\d+(:\d{1,2}){0,2}(\.\d+)?$/.test(t)) return null; return t.split(":").reduce((a,p)=>a*60+parseFloat(p),0); };
let videoDuration=null;
function timesHTML(cls){
  return '<div class="times-row '+(cls||"")+'"><span>From</span><input type="text" class="t0" placeholder="2:10" inputmode="decimal" aria-label="Start time, minutes:seconds"><span>to</span><input type="text" class="t1" placeholder="2:45" inputmode="decimal" aria-label="End time, minutes:seconds"></div>';
}
function momentProblem(a,b,label){
  const s=parseTime(a), e=parseTime(b);
  if(s===null||e===null) return "Type both times for "+label+" like 2:10 (minutes:seconds).";
  if(e<=s) return "For "+label+", the To time has to be after the From time.";
  if(e-s<5) return "The "+label+" is too short. Make it at least 5 seconds.";
  if(e-s>180) return "The "+label+" is longer than 3 minutes, the most YouTube allows for a Short.";
  if(videoDuration && s>=videoDuration) return "The "+label+" starts after the video ends ("+fmt(videoDuration)+").";
  return "";
}
function mustRows(){
  return [...$("mustRows").children].map(r=>({start:r.querySelector(".t0").value.trim(),end:r.querySelector(".t1").value.trim(),row:r})).filter(r=>r.start||r.end);
}
function mustCountHint(){
  const k=mustRows().length;
  if(k>count){ count=Math.min(10,k); renderCount(); }
  $("mustHint").textContent = !k ? "" : k>=count ? "All "+count+" Shorts will be your must-have moments."
    : k+" of your "+count+" Shorts will be your must-have moments; Clipline picks the other "+(count-k)+".";
}
function checkMust(){
  let msg="";
  [...$("mustRows").children].forEach(r=>r.querySelectorAll("input").forEach(i=>i.classList.remove("bad")));
  mustRows().forEach((r,k)=>{
    const m=momentProblem(r.start,r.end,"must-have moment "+(k+1));
    if(m){ r.row.querySelectorAll("input").forEach(i=>i.classList.add("bad")); msg=msg||m; }
  });
  $("mustHint").classList.toggle("bad",!!msg);
  if(msg){ $("mustHint").textContent=msg; return false; }
  mustCountHint(); renderCount(); return true;
}
$("addMust").onclick=()=>{
  if($("mustRows").children.length>=10) return;
  $("mustRows").insertAdjacentHTML("beforeend",timesHTML("must"));
  const row=$("mustRows").lastElementChild;
  row.insertAdjacentHTML("beforeend",'<button type="button" class="x" aria-label="Remove this moment"><span class="ms" aria-hidden="true">close</span></button>');
  row.querySelector(".x").onclick=()=>{ row.remove(); checkMust(); renderCount(); };
  row.querySelectorAll("input").forEach(i=>i.addEventListener("input",()=>{ if($("mustHint").classList.contains("bad")) checkMust(); else mustCountHint(); }));
  row.querySelectorAll("input").forEach(i=>i.addEventListener("blur",checkMust));
  row.querySelector(".t0").focus();
};
