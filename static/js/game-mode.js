// Game Mode (web/game_mode.py): the setup form's "What's in this video?" choice. A gameplay stream (GTA V for now) has its
// moments found from the screen and the sound; start.js sends gameChoice() as "game".
function gameChoice(){ const r=document.querySelector("input[name=kind]:checked"); return r ? r.value : ""; }
function paintGameChoice(){
  const g=gameChoice();
  $("gmHint").hidden=!g;
  $("sumKind").textContent = g ? "GTA V gameplay" : "Vlog or talk";
}
document.querySelectorAll("input[name=kind]").forEach(r=>r.addEventListener("change",paintGameChoice));
// After a job starts: the next video is a vlog unless the creator chooses again (a GTA choice must never stick unseen).
function resetGameChoice(){ const v=document.querySelector('input[name=kind][value=""]'); if(v){ v.checked=true; paintGameChoice(); } }
