// Shared helpers and page state used by every other file: $(id), fmt(), esc(), show(step).
// All files in static/js share one global scope and load in the order listed in index.html.
const $ = id => document.getElementById(id);
const fmt = s => { s=Math.round(s); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0"); };
const esc = t => String(t).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let count = 5, jobId = null, poll = null, job = null;

function show(n){
  [1,2,3,4,5].forEach(i=>$("s"+i).hidden = i!==n);
  $("postedNav").classList.toggle("now", n===5);
  document.querySelectorAll("#steps li").forEach(li=>{
    const k=+li.dataset.step, ic=li.querySelector(".st-ic");
    li.classList.toggle("done",n<5&&k<n); li.classList.toggle("now",k===n);
    if(k===n) li.setAttribute("aria-current","step"); else li.removeAttribute("aria-current");
    ic.innerHTML = n<5&&k<n ? '<span class="ms" aria-hidden="true">check</span>' : String(k);
  });
  window.scrollTo(0,0);
}
show(1);
