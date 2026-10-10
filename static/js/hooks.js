// Hook controls on each card: choose, write or rewrite the hook.
// ---- hook controls
const HOOK_NAMES={curiosity:"Curiosity",bold:"Bold",story:"Story",custom:"Your own"};
function hookOptions(s){
  const opts=Object.entries(s.hooks||{}).filter(([,t])=>t);
  if(s.hook && !opts.some(([,t])=>t===s.hook)) opts.push(["custom",s.hook]);  // older Shorts: just the one hook
  return opts;
}
function hookOptsHTML(s,chosen){
  return hookOptions(s).map(([k,t])=>'<li><label><input type="radio" name="hk'+s.idx+'" value="'+esc(k)+'" data-text="'+esc(t)+'"'+(chosen===k?' checked':'')+'><span><small>'+esc(HOOK_NAMES[k]||k)+'</small>'+esc(t)+'</span></label></li>').join("")+
    '<li><label><input type="radio" name="hk'+s.idx+'" value="none"'+(chosen==="none"?' checked':'')+'><span><small>No text hook</small>Let the original audio open the Short</span></label></li>';
}
function hookHTML(s){
  const none=s.hook_mode==="none"||!s.hook;
  return '<div class="hookbox"><div class="hk-head"><span class="small-lab"><span class="ms fill" aria-hidden="true">bolt</span>Hook</span><button type="button" class="linkbtn hk-change">Change</button></div>'+
    '<div class="hk-now'+(none?' none':'')+'">'+(none?'No text hook (original audio)':esc(s.hook))+'</div>'+
    '<div class="hk-edit" hidden>'+
      '<ul class="hk-opts" role="radiogroup" aria-label="Hook for Short '+s.idx+'">'+hookOptsHTML(s,none?"none":(s.hook_style||"custom"))+'</ul>'+
      '<input type="text" class="hk-text" maxlength="60" aria-label="Hook text, edit to write your own" value="'+esc(none?"":s.hook)+'"'+(none?' disabled':'')+'>'+
      '<div class="hk-emoji" hidden>Emoji can\'t be shown in the video or thumbnail, so they\'re left out there. They stay in the title and description.</div>'+
      '<label class="hk-thumb"><input type="checkbox" class="hk-usethumb" checked> Also put it on the thumbnail</label>'+
      '<div class="redo-row"><input type="text" class="hk-note" maxlength="300" placeholder="Optional: funnier, mention the snow..." aria-label="What the new hooks should be like"><button type="button" class="ghost hk-rewrite"><span class="ms" aria-hidden="true">auto_awesome</span>Rewrite</button></div>'+
      '<div class="redo-row"><button type="button" class="primary hk-apply">Apply</button><button type="button" class="ghost hk-cancel">Cancel</button></div>'+
      '<div class="err hk-err" role="alert"></div>'+
    '</div></div>';
}
function wireHook(el,s){
  const box=el.querySelector(".hookbox"), edit=box.querySelector(".hk-edit"), text=box.querySelector(".hk-text"), err=box.querySelector(".hk-err");
  const usethumb=box.querySelector(".hk-usethumb"), emoji=box.querySelector(".hk-emoji");
  const paintText=()=>{
    emoji.hidden=!/[\u{1F000}-\u{1FFFF}\u2600-\u27BF]/u.test(text.value);
    usethumb.disabled=text.disabled; usethumb.parentElement.style.opacity=text.disabled?.5:1;
  };
  const wireOpts=()=>box.querySelectorAll(".hk-opts input").forEach(r=>r.onchange=()=>{
    text.disabled = r.value==="none"; text.value = r.value==="none" ? "" : r.dataset.text; paintText();
  });
  paintText();
  wireOpts();
  // Typing your own text makes it "Your own" hook.
  text.addEventListener("input",()=>{
    const r=box.querySelector(".hk-opts input:checked");
    if(r && r.value!=="none" && text.value.trim()!==r.dataset.text){ r.checked=false; }
    paintText();
  });
  box.querySelector(".hk-change").onclick=()=>{ edit.hidden=!edit.hidden; err.textContent=""; };
  box.querySelector(".hk-cancel").onclick=()=>{ edit.hidden=true; err.textContent=""; };
  box.querySelector(".hk-rewrite").onclick=async()=>{
    const b=box.querySelector(".hk-rewrite"); err.textContent=""; b.disabled=true; b.textContent="Writing...";
    try{
      const r=await fetch("/api/hooks/"+jobId+"/"+s.idx,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({note:box.querySelector(".hk-note").value.trim()})});
      const j=await r.json().catch(()=>({}));
      if(!r.ok){ err.textContent=j.error||"Couldn't write new hooks. Please try again."; return; }
      s.hooks=j.hooks;
      box.querySelector(".hk-opts").innerHTML=hookOptsHTML({...s,hook:null},j.pick); wireOpts();
      text.disabled=false; text.value=j.hooks[j.pick]||""; paintText();
    }catch(e){ err.textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; }
    finally{ b.disabled=false; b.innerHTML='<span class="ms" aria-hidden="true">auto_awesome</span>Rewrite'; }
  };
  box.querySelector(".hk-apply").onclick=async()=>{
    err.textContent="";
    const r=box.querySelector(".hk-opts input:checked"), none=r&&r.value==="none", t=text.value.trim();
    if(!none && !t){ err.textContent="Type a hook, or choose No text hook."; return; }
    const style = none ? "none" : (r && r.dataset.text===t ? r.value : "custom");
    if(await sendMoment("/api/hook/"+jobId+"/"+s.idx,{mode:none?"none":"text",text:t,style,thumb:usethumb.checked},err)){ edit.hidden=true; el.querySelector("video").pause(); }
  };
}
