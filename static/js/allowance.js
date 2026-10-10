// Limits (web/allowance.py): the longest vlog Pit Crew takes, said under each "Drop your vlog here" and checked before
// the video is sent (no point sending 20 GB to hear it's too long), and this month's minutes in Settings.
let vlogLongest=0;  // minutes; 0 = no limit
async function loadLimits(){
  try{ const c=await (await fetch("/api/config")).json(); vlogLongest=c.longest||0; helpEmail=c.support||""; }catch(e){}
  paintHelp();
  const txt="English vlogs"+(vlogLongest?", up to "+limitLength(vlogLongest*60):"")+". Other languages are coming later.";
  document.querySelectorAll(".vlog-limits").forEach(el=>el.textContent=txt);
}
function limitLength(s){ const m=Math.round(s/60); if(m<1) return "less than a minute"; return m>=60 ? (m%60 ? Math.floor(m/60)+" h "+(m%60)+" min" : (m/60)+(m===60?" hour":" hours")) : m+(m===1?" minute":" minutes"); }
// The sentence to show if this file is longer than Pit Crew takes, else "" (also "" if the browser can't read its length:
// the server checks again).
function videoTooLong(file){
  if(!vlogLongest) return Promise.resolve("");
  return new Promise(res=>{
    try{
      const v=document.createElement("video"); v.preload="metadata";
      const done=t=>{ URL.revokeObjectURL(v.src); res(t); };
      v.onloadedmetadata=()=>done(isFinite(v.duration)&&v.duration>vlogLongest*60 ?
        "This vlog is "+limitLength(v.duration)+" long. Pit Crew takes vlogs up to "+limitLength(vlogLongest*60)+": trim it, or split it into parts and upload each one." : "");
      v.onerror=()=>done("");
      setTimeout(()=>done(""),5000);
      v.src=URL.createObjectURL(file);
    }catch(e){ res(""); }
  });
}
// Settings: "This month: 42 of 600 minutes of vlogs" (only when there's a monthly allowance).
async function paintUsage(){
  let a; try{ a=await (await fetch("/api/allowance")).json(); }catch(e){ return; }
  $("setUsage").innerHTML = a.monthly ? '<div class="set-row"><span class="ms" aria-hidden="true">timer</span><span class="set-t"><b>'+
    Math.round(a.used)+" of "+Math.round(a.monthly)+' minutes of vlogs this month</b><small>Starts again on '+esc(a.resets)+'</small></span></div>' : "";
}
