// Sending a vlog's video in pieces (web/video_upload.py), so a dropped connection doesn't start it over: each piece is
// retried, and the server says how much it has. Choosing the same file again (after closing the tab, or after the
// connection kept dropping) carries on where it stopped. Used by js/start.js and js/vlog-upload.js.
const UP_PIECE=8*1024*1024;  // web/video_upload.py PIECE_MB
const UP_SIGNIN="You were signed out. Sign in, then press the button again: the video carries on where it stopped.";
let upSending=0;  // videos this tab is sending: closing the tab asks first (they can carry on later)
window.addEventListener("beforeunload",e=>{ if(upSending){ e.preventDefault(); e.returnValue=""; } });
class UpStop extends Error{}
const upKey=f=>"clipline-upload:"+myEmail+":"+f.name+":"+f.size+":"+f.lastModified;
function upRemember(f,id){ try{ id?localStorage.setItem(upKey(f),id):localStorage.removeItem(upKey(f)); }catch(e){} }
function upRecall(f){ try{ return localStorage.getItem(upKey(f)); }catch(e){ return null; } }
async function upJSON(url,opts){ const r=await fetch(url,opts); let j={}; try{ j=await r.json(); }catch(e){} return [r,j]; }
// Sends the file; onProgress(pct), onNote(text, "" when all is well). Resolves to the upload id for /api/start or
// /api/vlog/start (which then calls upRemember(file,null)); rejects with a plain sentence.
async function sendVideo(file,onProgress,onNote){
  upSending++;
  try{
    let id=upRecall(file), received=0;
    if(id){ try{ const [r,j]=await upJSON("/api/upload/"+id); if(r.ok) received=j.received; else id=null; }catch(e){ id=null; } }
    if(!id){
      let r,j; try{ [r,j]=await upJSON("/api/upload/new",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:file.name,size:file.size})}); }
      catch(e){ throw new UpStop("Couldn't reach Pit Crew. Check your internet connection, then try again."); }
      if(r.status===401) throw new UpStop(UP_SIGNIN);
      if(!r.ok) throw new UpStop(j.error||"Couldn't start sending the video.");
      id=j.id; upRemember(file,id);
    }
    onProgress(received/file.size*100);
    let fails=0;
    while(received<file.size){
      try{
        const [r,j]=await upJSON("/api/upload/"+id+"?offset="+received,{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file.slice(received,received+UP_PIECE)});
        if(r.ok||r.status===409){ received=j.received; fails=0; onNote(""); onProgress(received/file.size*100); continue; }
        if(r.status===401) throw new UpStop(UP_SIGNIN);
        if(r.status===404){ upRemember(file,null); throw new UpStop("Pit Crew no longer has the part already sent. Press the button again to send the video again."); }
        if(r.status<500) throw new UpStop(j.error||"Couldn't send the video.");
        throw new Error("Pit Crew answered "+r.status);
      }catch(e){
        if(e instanceof UpStop) throw e;
        const pct=Math.floor(received/file.size*100);
        if(++fails>40) throw new UpStop("The connection kept dropping. Press the button again: the video carries on from "+pct+"%.");
        const wait=Math.min(30,2**Math.min(fails,5));
        onNote("Connection lost at "+pct+"%. Trying again in "+wait+" seconds…");
        await new Promise(res=>setTimeout(res,wait*1000));
        try{ const [r,j]=await upJSON("/api/upload/"+id); if(r.ok) received=j.received; }catch(x){}
      }
    }
    onNote("");
    return id;
  }finally{ upSending--; }
}
