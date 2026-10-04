// Step 3: a Short's card.
// ---- review
function cardHTML(s){
  if(s.pending) return '<article class="short pending" data-idx="'+s.idx+'" data-video="">'+
    '<div class="phone"><div class="busy" aria-live="polite"><span class="spin" aria-hidden="true"></span><span class="bmsg"></span></div></div>'+
    '<div class="meta"><span class="tc"><span class="ms" aria-hidden="true">movie</span>New Short</span></div></article>';
  const v="/media/"+job.id+"/"+s.video, t="/media/"+job.id+"/"+s.thumb;
  return '<article class="short" data-idx="'+s.idx+'" data-video="'+esc(s.video+"|"+s.thumb)+'">'+
    '<div class="phone"><video src="'+v+'" poster="'+t+'" controls playsinline preload="metadata"></video><img src="'+t+'" alt="Thumbnail for '+esc(s.title)+'">'+
      '<div class="busy" aria-live="polite"><span class="spin" aria-hidden="true"></span><span class="bmsg"></span></div></div>'+
    '<div class="toggle" role="group" aria-label="Preview"><button type="button" aria-pressed="true" data-v="v"><span class="ms" aria-hidden="true">play_circle</span>Short</button><button type="button" aria-pressed="false" data-v="t"><span class="ms" aria-hidden="true">image</span>Thumbnail</button></div>'+
    lookHTML(s)+
    '<div class="meta"><span class="tc"><span class="ms" aria-hidden="true">schedule</span>'+fmt(s.start)+'–'+fmt(s.end)+' · '+Math.round(s.end-s.start)+'s</span>'+(s.manual?'<span class="tag cap">Your pick</span>':'')+'</div>'+
    '<div><label class="fld-lab" for="title'+s.idx+'">YouTube title</label><input class="title" id="title'+s.idx+'" type="text" value="'+esc(s.title)+'" maxlength="95"></div>'+
    hookHTML(s)+
    '<div class="why">'+esc(s.why)+'</div>'+
    '<div class="row"><label class="keep"><input type="checkbox"'+(s.keep===false?'':' checked')+'> Post this</label>'+
      '<span class="links"><button type="button" class="linkbtn retry"><span class="ms" aria-hidden="true">refresh</span>Try again</button><a href="'+v+'" download title="Download the Short (video)"><span class="ms" aria-hidden="true">download</span>Save</a></span></div>'+
    '<div class="redo" hidden>'+
      '<textarea rows="3" maxlength="500" aria-label="What would you like instead for Short '+s.idx+'?" placeholder="Optional: what would you like instead? For example: the part where we reach the top, or around 3:20"></textarea>'+
      '<div class="pick-row"><button type="button" class="ghost pick"><span class="ms" aria-hidden="true">movie</span>Choose on the video</button></div><span class="small-lab">Or type the exact times</span>'+timesHTML()+
      '<div class="redo-row"><button type="button" class="primary go">Find another moment</button><button type="button" class="ghost cancel">Cancel</button></div>'+
    '</div>'+
    '<div class="err rerr" role="alert"></div>'+
  '</article>';
}
