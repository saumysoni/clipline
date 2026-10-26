// YouTube's daily upload limit (web/youtube_quota.py): a line on the post page when it matters. Shorts over the limit
// aren't refused: they wait in Pit Crew and go up after midnight Pacific, at the times the creator chose.
async function ytToday(){
  let note=$("ytToday");
  if(!note){ note=document.createElement("p"); note.id="ytToday"; note.className="yt-today"; note.hidden=true; $("err3").before(note); }
  let j; try{ const r=await fetch("/api/youtube/today"); if(!r.ok) return; j=await r.json(); }catch(e){ return; }
  const reset=new Date(j.resets_at), hrs=Math.max(1,Math.round((reset-new Date())/36e5));
  const when="after midnight Pacific time (in about "+hrs+" hour"+(hrs===1?"":"s")+")";
  let t="";
  if(j.left_today===0 || j.day_left===0) t="Today's YouTube uploads for Pit Crew are used up. Shorts you post now wait and go up by themselves "+when+", at the times you choose.";
  else if(j.left_today!=null) t="Today Pit Crew can upload "+j.left_today+" more of your Shorts to YouTube (the daily uploads are shared by everyone). Any more wait and go up "+when+", at the times you choose.";
  if(j.waiting) t=(t?t+" ":"")+j.waiting+(j.waiting===1?" of your Shorts is":" of your Shorts are")+" already waiting.";
  note.textContent=t; note.hidden=!t;
}
