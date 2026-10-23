// Date and time picker for every "when" field (Post page, Schedule dialog, vlog upload, Change time on Scheduled).
// Each <input type="datetime-local"> becomes a button showing the chosen time ("Wed, Oct 22 · 6:00 PM") that opens a
// calendar and a list of times right below it (in the page, so dialogs never clip it). The input stays in the page,
// hidden, with its "YYYY-MM-DDTHH:MM" value: code that reads or sets .value, sets .min / .disabled, calls .focus()
// or marks it .bad keeps working. Inputs added later (Change time) are picked up by themselves.
const WP_STEP=15;  // minutes between the times offered
const wpPad=x=>String(x).padStart(2,"0");
const wpLocal=d=>d.getFullYear()+"-"+wpPad(d.getMonth()+1)+"-"+wpPad(d.getDate())+"T"+wpPad(d.getHours())+":"+wpPad(d.getMinutes());
function wpParse(v){ const m=/^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(v||""); return m?new Date(+m[1],m[2]-1,+m[3],+m[4],+m[5]):null; }
const wpDay=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
const wpSame=(a,b)=>!!a && !!b && a.getFullYear()===b.getFullYear() && a.getMonth()===b.getMonth() && a.getDate()===b.getDate();
const wpTime=d=>d.toLocaleTimeString(undefined,{hour:"numeric",minute:"2-digit"});
const wpLabel=d=>d.toLocaleDateString(undefined,{weekday:"short",month:"short",day:"numeric"})+" · "+wpTime(d);
const WP_VALUE=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value");
const WP_DISABLED=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"disabled");
const WP_OPEN=new Set();

function whenPicker(inp){
  if(inp._wp) return;
  inp._wp=true;
  const name=inp.getAttribute("aria-label")||"Date and time";
  const wrap=document.createElement("div"); wrap.className="wp";
  const btn=document.createElement("button"); btn.type="button"; btn.className="wp-btn"; btn.setAttribute("aria-expanded","false");
  const panel=document.createElement("div"); panel.className="wp-panel"; panel.hidden=true; panel.setAttribute("role","group"); panel.setAttribute("aria-label",name);
  inp.before(wrap); wrap.append(btn,panel,inp); inp.type="hidden";
  let view=null;  // first day of the month the calendar shows

  const min=()=>wpParse(inp.min) || new Date(Date.now()+16*60000);  // the server wants at least 15 minutes ahead
  const sel=()=>wpParse(WP_VALUE.get.call(inp));
  function set(d){
    WP_VALUE.set.call(inp,wpLocal(d)); paintBtn();
    inp.dispatchEvent(new Event("input",{bubbles:true})); inp.dispatchEvent(new Event("change",{bubbles:true}));
  }
  function paintBtn(){
    const d=sel();
    btn.innerHTML='<span class="ms" aria-hidden="true">calendar_month</span><b>'+(d?wpLabel(d):"Pick a date and time")+'</b><span class="ms wp-chev" aria-hidden="true">expand_more</span>';
    btn.setAttribute("aria-label",name+": "+(d?wpLabel(d):"not chosen")+". Change");
  }
  // The times offered on a day: every WP_STEP minutes from the earliest allowed, plus the chosen one if it's off the grid.
  function slots(day){
    const lo=min(), out=[];
    for(let m=0;m<1440;m+=WP_STEP){ const t=new Date(day.getFullYear(),day.getMonth(),day.getDate(),0,m); if(t>=lo) out.push(t); }
    const s=sel(); if(s && wpSame(s,day) && s>=lo && !out.some(t=>+t===+s)){ out.push(s); out.sort((a,b)=>a-b); }
    return out;
  }
  function pickDay(day){
    const s=sel(), want=new Date(day.getFullYear(),day.getMonth(),day.getDate(),s?s.getHours():18,s?s.getMinutes():0);
    const ok=slots(day); if(!ok.length) return;
    set(want>=ok[0] ? want : ok[0]); render(true);
    const b=panel.querySelector('.wp-day[data-d="'+day.getDate()+'"]'); if(b) b.focus();
  }
  function render(keepScroll){
    const lo=min(), s=sel(), today=new Date(), y=view.getFullYear(), mo=view.getMonth();
    const first=new Date(y,mo,1).getDay(), days=new Date(y,mo+1,0).getDate(), loDay=wpDay(lo);
    const wd=[...Array(7)].map((_,i)=>'<span class="wp-wd">'+new Date(2026,1,1+i).toLocaleDateString(undefined,{weekday:"narrow"})+'</span>').join("");  // Feb 1 2026 is a Sunday
    let cells="";
    for(let i=0;i<first;i++) cells+="<span></span>";
    for(let d=1;d<=days;d++){
      const day=new Date(y,mo,d), cls=(wpSame(day,today)?" today":"")+(wpSame(day,s)?" on":"");
      cells+='<button type="button" class="wp-day'+cls+'" data-d="'+d+'"'+(day<loDay?" disabled":"")+' aria-label="'+
        day.toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"})+'"'+(wpSame(day,s)?' aria-pressed="true"':"")+'>'+d+'</button>';
    }
    const day=s||lo, times=slots(wpDay(day));
    const oldTop=keepScroll && panel.querySelector(".wp-times") ? panel.querySelector(".wp-times").scrollTop : null;
    let tz=""; try{ tz=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
    panel.innerHTML='<div class="wp-cal"><div class="wp-head">'+
        '<button type="button" class="wp-nav" data-go="-1" aria-label="Previous month"'+(new Date(y,mo,1)<=new Date(lo.getFullYear(),lo.getMonth(),1)?" disabled":"")+'><span class="ms" aria-hidden="true">chevron_left</span></button>'+
        '<b aria-live="polite">'+view.toLocaleDateString(undefined,{month:"long",year:"numeric"})+'</b>'+
        '<button type="button" class="wp-nav" data-go="1" aria-label="Next month"><span class="ms" aria-hidden="true">chevron_right</span></button></div>'+
        '<div class="wp-grid">'+wd+cells+'</div></div>'+
      '<div class="wp-times" role="listbox" aria-label="Time on '+day.toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"})+'">'+
        (times.length?times.map(t=>'<button type="button" class="wp-time'+(s&&+t===+s?" on":"")+'" role="option" aria-selected="'+(s&&+t===+s)+'" data-t="'+(+t)+'">'+wpTime(t)+'</button>').join("")
          :'<p class="wp-none">No times left on this day. Pick another day.</p>')+'</div>'+
      '<div class="wp-foot"><span>'+(s?wpLabel(s):"Pick a day, then a time")+(tz?' <small>· your time ('+esc(tz.replace(/_/g," "))+')</small>':"")+'</span>'+
        '<button type="button" class="ghost sm wp-done">Done</button></div>';
    const list=panel.querySelector(".wp-times"), on=list.querySelector(".wp-time.on");
    const near=on || [...list.querySelectorAll(".wp-time")].find(b=>new Date(+b.dataset.t).getHours()>=9);  // nothing chosen: from 9 AM
    if(oldTop!==null) list.scrollTop=oldTop;
    else if(near) list.scrollTop=near.offsetTop-list.offsetTop-(on?list.clientHeight/2-on.offsetHeight/2:0);
  }
  function open(){
    if(btn.disabled) return;
    WP_OPEN.forEach(c=>c!==close && c());
    const d=sel()||min(); view=new Date(d.getFullYear(),d.getMonth(),1);
    panel.hidden=false; render(false); btn.setAttribute("aria-expanded","true"); WP_OPEN.add(close);  // shown first: the time list measures itself to scroll
    (panel.querySelector(".wp-day.on")||panel.querySelector(".wp-day:not(:disabled)")||btn).focus({preventScroll:true});
    // keep the whole panel in view (Post page, dialogs) without jumping the page when it already fits
    const r=panel.getBoundingClientRect(); if(r.bottom>innerHeight) panel.scrollIntoView({block:"nearest",behavior:"smooth"});
  }
  function close(){ if(panel.hidden) return; panel.hidden=true; btn.setAttribute("aria-expanded","false"); WP_OPEN.delete(close); }

  btn.onclick=()=>panel.hidden?open():close();
  panel.addEventListener("click",e=>{
    const b=e.target.closest("button"); if(!b || b.disabled) return;
    if(b.dataset.go){ view=new Date(view.getFullYear(),view.getMonth()+ +b.dataset.go,1); render(false);
      panel.querySelector('.wp-nav[data-go="'+b.dataset.go+'"]')?.focus(); return; }
    if(b.dataset.d){ pickDay(new Date(view.getFullYear(),view.getMonth(),+b.dataset.d)); return; }
    if(b.dataset.t){ set(new Date(+b.dataset.t)); close(); btn.focus(); return; }
    if(b.classList.contains("wp-done")){ close(); btn.focus(); }
  });
  panel.addEventListener("keydown",e=>{
    if(e.key==="Escape"){ e.preventDefault(); e.stopPropagation(); close(); btn.focus(); return; }  // not the dialog's Escape
    const b=e.target.closest(".wp-day"); if(!b) return;
    const step={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[e.key]; if(!step) return;
    const next=panel.querySelector('.wp-day[data-d="'+(+b.dataset.d+step)+'"]:not(:disabled)');
    if(next){ e.preventDefault(); next.focus(); }
  });
  Object.defineProperty(inp,"value",{configurable:true,get(){ return WP_VALUE.get.call(inp); },
    set(v){ WP_VALUE.set.call(inp,v); paintBtn(); if(!panel.hidden) render(true); }});
  Object.defineProperty(inp,"disabled",{configurable:true,get(){ return WP_DISABLED.get.call(inp); },
    set(v){ WP_DISABLED.set.call(inp,v); btn.disabled=!!v; if(v) close(); }});
  inp.focus=()=>{ btn.focus(); open(); };
  new MutationObserver(()=>btn.classList.toggle("bad",inp.classList.contains("bad"))).observe(inp,{attributes:true,attributeFilter:["class"]});
  btn.disabled=WP_DISABLED.get.call(inp);
  paintBtn();
}
document.addEventListener("pointerdown",e=>{ document.querySelectorAll(".wp").forEach(w=>{
  if(!w.contains(e.target) && !w.querySelector(".wp-panel").hidden) w.querySelector(".wp-btn").click(); }); });
document.querySelectorAll('input[type="datetime-local"]').forEach(whenPicker);
new MutationObserver(ms=>{ for(const m of ms) for(const n of m.addedNodes) if(n.nodeType===1){
  if(n.matches('input[type="datetime-local"]')) whenPicker(n);
  n.querySelectorAll('input[type="datetime-local"]').forEach(whenPicker);
} }).observe(document.body,{childList:true,subtree:true});
