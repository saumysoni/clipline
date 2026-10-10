// Vlogs | Shorts & Reels tabs on the Drafts and Scheduled pages. pageTabs(listId, onPick) wires the tab buttons
// (click, and arrow keys between them) and returns pick(tab), which shows that tab's panel without calling onPick.
// The tab the creator last clicked on each page is remembered on this device (pick.saved(), null before any click).
function pageTabs(listId, onPick){
  const tabs=[...$(listId).querySelectorAll("[role=tab]")], key="pc-tab-"+listId;
  function pick(tab){
    tabs.forEach(b=>{ const on=b.dataset.tab===tab; b.setAttribute("aria-selected",on); b.tabIndex=on?0:-1; $(b.getAttribute("aria-controls")).hidden=!on; });
  }
  tabs.forEach((b,i)=>{
    b.onclick=()=>{ pick(b.dataset.tab); try{ localStorage.setItem(key,b.dataset.tab); }catch(e){} onPick(b.dataset.tab); };
    b.onkeydown=e=>{
      const step=e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0; if(!step) return;
      const next=tabs[(i+step+tabs.length)%tabs.length]; next.focus(); next.click(); e.preventDefault();
    };
  });
  pick.saved=()=>{ let t=null; try{ t=localStorage.getItem(key); }catch(e){} return tabs.some(b=>b.dataset.tab===t)?t:null; };
  return pick;
}
// "3" next to a tab's name, or nothing while it's loading.
function tabCount(id,n){ $(id).textContent = n==null ? "" : String(n); }
// Deleting a vlog from these pages reuses the Vlogs page's delete, which reports problems on its own (hidden) page:
// move that message to the page showing.
function takeErr(from,to){ const m=$(from).textContent; $(from).textContent=""; if(m) $(to).textContent=m; }
// An empty tab: what's missing and what to do next.
function tabEmpty(icon,title,text,button){
  return '<div class="card vl-empty"><span class="ms" aria-hidden="true">'+icon+'</span><b>'+esc(title)+'</b><span>'+esc(text)+'</span>'+
    (button?'<button type="button" class="primary tab-empty-go"><span class="ms" aria-hidden="true">'+button[0]+'</span>'+esc(button[1])+'</button>':'')+'</div>';
}
