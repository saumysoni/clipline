// A draft Short's details, editable: hook (js/hooks.js), thumbnail (look, its text, Try again: web/thumbnail_edit.py),
// hashtags, YouTube title and Instagram caption (js/post-text.js), through the same routes as the vlog's editor card. Used by Quick review (js/quick-review.js) and
// the editor's Details tool (js/editor.js), each with its own copy (pre keeps their ids apart).
// Nothing is saved while editing: changes wait in pend until save(); cancel() draws everything again from what's saved.
// snap() / restore(p): the changes waiting, as a copy, and putting such a copy back (the editor's Undo / Redo).
// Saving a hook or a thumbnail change remakes the Short, one at a time: hook, then the thumbnail (Try again or its text),
// then the look. The page calls remadeDone() when it sees a remake has finished, and the next one starts.
// o: {box, err, pre, onChange() (pend changed), onLoad() (drawn from what's saved), onTitle(v) (title typed),
//     onRemaking() (a remake started), onGone()
//     (the Short isn't there any more), onLook() (a look was picked: show the thumbnail),
//     extra (the editor's AI Edit, js/ai-edit.js: {dirty(), count(), step() -> [url, body] | {error}, sent(), reset()}:
//     its change is saved with the rest, as the first remake),
//     caps (the editor's Captions, js/captions.js: {dirty(), count(), canEdit(), step(remake) -> [url, body], sent(remake),
//     reset()}: a remake of its own, unless a cut or a new hook remakes the Short anyway, then saved just before that)}
function shortDetails(o){
  let c=null, s=null, pend={}, queue=[], gen=0, tinfo={}, st=null;  // st: the Short's vlog as last loaded
  const changed=()=>o.onChange&&o.onChange();
  const post=async(url,body)=>{
    let r,j={}; try{ r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); j=await r.json().catch(()=>({})); }
    catch(e){ o.err.textContent="Couldn't reach Pit Crew. Check your internet connection, then try again."; return false; }
    if(!r.ok){ o.err.textContent=j.error||"Couldn't save it. Try again."; return false; }
    return true;
  };
  // Draws the fields from what's saved (also Cancel).
  // quiet: drawn already (after a save or a remake): what's shown stays until the new data is in (no "Getting...")
  async function load(quiet){
    const my=++gen, cl=c; pend={}; changed(); o.err.textContent="";
    if(!quiet || !s) o.box.innerHTML='<p class="qr-wait">Getting the hook and text...</p>';
    let j; try{
      const [r,ti]=await Promise.all([fetch("/api/status/"+cl.job), fetch("/api/thumb/"+cl.job+"/"+cl.idx)]);
      if(!r.ok) throw 0; j=await r.json(); tinfo=ti.ok?await ti.json():{};
    }
    catch(e){ if(my===gen) o.box.innerHTML='<p class="qr-wait">Couldn\'t load the hook and text. Check your internet connection, then try again.</p>'; return; }
    if(my!==gen) return;  // another Short was opened meanwhile
    s=(j.shorts||[]).find(x=>x.idx===cl.idx);
    if(!s){ if(o.onGone) o.onGone(); return; }
    st=j;
    if(s.retry_error) o.err.textContent="The last change didn't work: "+s.retry_error;
    draw();
    if(o.onLoad) o.onLoad();
  }
  // The fields: what's saved, with the changes waiting in pend shown on top (after load(), pend is empty).
  function draw(){
    const cl=c, j=st, gone=!!j.video_deleted_at, box=o.box, held=pend.text||{};
    const sv={...s, hashtags:held.hashtags||s.hashtags};  // hashtags waiting to be saved show as chips
    box.innerHTML='<div class="qr-sec">'+hookHTML(sv,o.pre)+'</div>'+
      (s.thumb?'<div class="qr-sec sd-thumb">'+lookHTML(s,cl.job)+
        '<div class="sd-tt"><label class="small-lab" for="'+o.pre+'tl2">Thumbnail text</label>'+
          '<input type="text" class="sd-l1" maxlength="30" placeholder="Small line (optional)" aria-label="Thumbnail: small line above the headline" value="'+esc(tinfo.line1||"")+'">'+
          '<input type="text" class="sd-l2" id="'+o.pre+'tl2" maxlength="30" placeholder="Headline" value="'+esc(tinfo.line2||"")+'">'+
          '<div class="sd-again-row"><button type="button" class="ghost sm sd-again" aria-pressed="false"><span class="ms" aria-hidden="true">refresh</span><span>Try again</span></button>'+
          '<small>A new frame and text, picked by AI.</small></div></div>'+
        '<small class="sd-hint" hidden></small></div>':'')+
      '<div class="qr-sec">'+postTextHTML(sv,o.pre)+'</div>';
    // hook: Apply keeps it (shown here) until Save
    const showHook=body=>{ const now=box.querySelector(".hk-now"), none=body.mode==="none";
      now.classList.toggle("none",none); now.textContent=none?"No text hook (original audio)":body.text; };
    wireHook(box,sv,{jid:cl.job, pre:o.pre, apply:body=>{
      const was={mode:s.hook_mode==="none"||!s.hook?"none":"text", text:s.hook||""};
      if(body.mode===was.mode && (body.mode==="none" || body.text===was.text)) delete pend.hook; else pend.hook=body;
      showHook(body); changed(); return true;
    }});
    if(pend.hook) showHook(pend.hook);
    // the vlog's video is deleted: the hook can't be put back into the video (titles and looks still work)
    box.querySelectorAll(".hk-change,.hk-apply,.hk-rewrite").forEach(b=>{ b.disabled=gone||!!cl.remaking; if(gone) b.title="Needs the vlog's video, which was deleted"; });
    // hashtags and caption: held, saved together
    wirePostText(box,sv,cl.job,body=>{ pend.text={...(pend.text||{}),...body}; changed(); }, "caption" in held ? {caption:held.caption} : null);
    // thumbnail: look, text and Try again are chosen here and made on Save
    const hint=()=>{ const h=box.querySelector(".sd-hint"); if(!h) return;
      h.textContent = pend.tagain ? "A new thumbnail is made when you save." : "The thumbnail is redrawn when you save.";
      h.hidden=!(pend.tagain||pend.ttext||pend.look); };
    if(pend.look) box.querySelectorAll(".looks button").forEach(x=>x.setAttribute("aria-pressed",x.dataset.look===pend.look));
    box.querySelectorAll(".looks button").forEach(b=>{ b.disabled=!!cl.remaking; b.onclick=()=>{
      box.querySelectorAll(".looks button").forEach(x=>x.setAttribute("aria-pressed",x===b));
      if(b.dataset.look===(s.thumb_look||"frame")) delete pend.look; else pend.look=b.dataset.look;
      hint(); if(o.onLook) o.onLook(); changed();
    }; });
    const l1=box.querySelector(".sd-l1"), l2=box.querySelector(".sd-l2"), again=box.querySelector(".sd-again");
    if(l1){
      const typed=()=>{
        const a=l1.value.trim(), b=l2.value.trim();
        if(a===(tinfo.line1||"").trim() && b===(tinfo.line2||"").trim()) delete pend.ttext; else pend.ttext={line1:a,line2:b};
        hint(); changed();
      };
      l1.addEventListener("input",typed); l2.addEventListener("input",typed);
      if(!tinfo.can_text){ l1.disabled=l2.disabled=true; l2.title="The vlog's video was deleted, so this thumbnail can't be redrawn"; }
      // Try again: on or off; while it's on, the text is the AI's (the fields wait)
      again.onclick=()=>{
        const on=!pend.tagain; if(on) pend.tagain=true; else delete pend.tagain;
        again.setAttribute("aria-pressed",on); again.lastChild.textContent=on?"New thumbnail on save":"Try again";
        l1.disabled=l2.disabled=on||!tinfo.can_text; hint(); if(o.onLook&&on) o.onLook(); changed();
      };
      if(!tinfo.can_again){ again.disabled=true; again.title="Needs the vlog's video, which was deleted"; }
      if(pend.ttext){ l1.value=pend.ttext.line1; l2.value=pend.ttext.line2; }
      if(pend.tagain){ again.setAttribute("aria-pressed",true); again.lastChild.textContent="New thumbnail on save"; l1.disabled=l2.disabled=true; }
    }
    hint();
    // the YouTube title
    const title=box.querySelector("input.title");
    if(title && "title" in pend) title.value=pend.title;
    if(title) title.addEventListener("input",()=>{ setPend(title.value); if(o.onTitle) o.onTitle(title.value); });
    if(cl.remaking) box.querySelectorAll("button,input,textarea").forEach(b=>b.disabled=true);
  }
  function setPend(v){ v=v.trim(); if(v===s.title) delete pend.title; else pend.title=v; changed(); }
  // Title typed somewhere else on the page (the editor's header): the same change.
  function setTitle(v){
    if(!s) return;
    const t=o.box.querySelector("input.title"); if(t) t.value=v;
    setPend(v);
  }
  // Save: title and text at once, then the remakes one at a time (hook, thumbnail, look; remadeDone() starts the next).
  async function save(){
    if(!c||!s||!api.dirty()) return;
    const p=pend, cl=c, base="/api/clips/"+cl.job+"/"+cl.idx;
    if("title" in p && !p.title){ o.err.textContent="Type a YouTube title."; return; }
    if(p.ttext && !p.tagain && !p.ttext.line2){ o.err.textContent="Type the headline for the thumbnail."; return; }
    const ex=o.extra&&o.extra.dirty()?o.extra.step():null;
    if(ex&&ex.error){ o.err.textContent=ex.error; return; }
    const cap=o.caps&&o.caps.dirty()?o.caps:null;
    if(cap&&!cap.canEdit()){ o.err.textContent="The captions can't be changed now. Wait for the Short to finish, or discard the caption changes."; return; }
    o.err.textContent="";
    if("title" in p){ if(!await post(base+"/title",{title:p.title})) return changed(); delete p.title; }
    if(p.text){ if(!await post(base+"/post-text",p.text)) return changed(); delete p.text; }
    const steps=ex?[ex]:[];  // the cut first: a new hook is then burned into the cut Short
    if(p.hook) steps.push(["/api/hook/"+cl.job+"/"+cl.idx,p.hook]);
    // Captions: a cut or a new hook remakes the Short anyway, so they're saved just before it and that remake makes them
    // (if it's then refused, they get a remake of their own, so the video never lags behind them); else their own remake.
    let capFirst=false;
    if(cap && steps.length){ if(!await post(...cap.step(false))) return changed(); cap.sent(false); }
    else if(cap){ steps.push(cap.step(true)); capFirst=true; }
    if(p.tagain) steps.push(["/api/thumb-again/"+cl.job+"/"+cl.idx,{}]);
    else if(p.ttext) steps.push(["/api/thumb-text/"+cl.job+"/"+cl.idx,p.ttext]);
    if(p.look) steps.push(["/api/look/"+cl.job+"/"+cl.idx,{look:p.look}]);
    const remade=steps.length>0;
    if(remade){
      if(!await post(...steps[0])){
        if(cap && !capFirst){ const msg=o.err.textContent; if(await post(...cap.step(true))){ cap.sent(true); if(o.onRemaking) o.onRemaking(); loadClips(); } o.err.textContent=msg; }
        return changed();
      }
      if(ex) o.extra.sent();
      if(capFirst) cap.sent(true);
      ["hook","tagain","ttext","look"].forEach(k=>delete p[k]);
      queue=steps.slice(1);  // one remake at a time: the rest go after (remadeDone)
    }
    changed();
    if(remade){ o.box.querySelectorAll("button,input,textarea").forEach(b=>b.disabled=true); if(o.onRemaking) o.onRemaking(); }
    else load(true);
    clToast("Changes saved", remade?"The Short is being remade with them.":"");
    loadClips();
  }
  // A remake finished: the next saved change, else the fields again.
  async function remadeDone(){
    if(!queue.length){ load(true); return; }
    const next=queue.shift();
    if(await post(...next)){ if(o.onRemaking) o.onRemaking(); loadClips(); }
    else{ const msg=o.err.textContent; queue=[]; await load(true); o.err.textContent="Some of your changes were saved, but not all: "+msg+" Make the rest again and save."; }
  }
  const api={
    open(clip){ c=clip; queue=[]; return load(); },
    clear(){ c=s=null; pend={}; queue=[]; gen++; changed(); },
    follow(clip){ c=clip; },  // the clip list was loaded again
    dirty:()=>Object.keys(pend).length>0 || !!(o.extra&&o.extra.dirty()) || !!(o.caps&&o.caps.dirty()),
    count:()=>Object.keys(pend).length+(o.extra?o.extra.count():0)+(o.caps?o.caps.count():0),
    has:k=>k in pend,
    // The editor's Undo / Redo: the changes waiting, and putting a copy of them back (the fields are drawn again).
    snap:()=>JSON.parse(JSON.stringify(pend)),
    restore(p){
      if(!s||!st) return;
      pend=JSON.parse(JSON.stringify(p||{})); draw();
      if(o.onTitle) o.onTitle("title" in pend ? pend.title : s.title);
      changed();
    },
    cancel:()=>{ if(o.extra) o.extra.reset(); if(o.caps) o.caps.reset(); return c&&load(true); }, save, setTitle, remadeDone,
  };
  return api;
}
// Short / Thumbnail switch over a player: shows the video, or the thumbnail image instead.
function sdView(group,video,img,v){
  group.querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.v===v));
  img.hidden=v!=="t"; video.hidden=v==="t"; if(v==="t") video.pause();
}
// Unsaved details anywhere on the page: the browser asks before the tab is closed or reloaded.
const sdOpen=[];
addEventListener("beforeunload",e=>{ if(sdOpen.some(d=>d.dirty())){ e.preventDefault(); e.returnValue=""; } });
