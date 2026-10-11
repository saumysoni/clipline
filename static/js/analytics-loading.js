// Analytics loading states: a skeleton shaped like what's coming (tiles, charts, donuts, rows) with a shimmer, a
// racing-stripe progress bar, and a status line that steps through what Pit Crew is doing. After 18 s it says plainly
// that YouTube is slow, so a long wait never looks frozen. Motion stops for people who turned it off (reduced motion).
// anSkel(kind, title) returns the HTML; one shared timer moves every skeleton on the page and stops when none is left.

const AN_SKEL_STEPS={
  overview:["Asking YouTube for your views","Adding up your Shorts","Getting Instagram's numbers","Drawing your charts"],
  pairs:["Finding the clips Pit Crew posted","Getting each clip's YouTube numbers","Getting each Reel's Instagram numbers","Lining them up side by side"],
  audience:["Asking YouTube who watches","Sorting by country, age and device","Drawing the charts"],
  igaudience:["Asking Instagram about your followers","Drawing the charts"],
  igtiles:["Asking Instagram for your account's numbers"],
  grow:["Reading when your viewers are around","Working out your best times to post"],
  compare:["Getting every video's numbers","Adding them up"],
  detail:["Getting this clip's numbers","Checking its whole life on YouTube","Drawing the charts"],
  chart:["Getting each day's numbers","Drawing the lines"],
  cards:["Getting your numbers"]
};
let anSkelTimer=null;
const AN_SKEL_SLOW="This is taking longer than usual (YouTube can be slow). Still working on it; the other tabs work meanwhile.";

function anSkel(kind,title){
  kind=AN_SKEL_STEPS[kind]?kind:"cards";
  if(!anSkelTimer) anSkelTimer=setInterval(anSkelTick,400);  // stops by itself once no skeleton is left
  const steps=AN_SKEL_STEPS[kind];
  return '<div class="an-skel sk-'+kind+'" role="status" aria-live="polite" aria-busy="true" data-kind="'+kind+'" data-t0="'+Date.now()+'">'+
    '<div class="sk-head"><div class="sk-race" aria-hidden="true"><i></i></div>'+
    '<p class="sk-msg"><b>'+esc(title||"Getting your numbers...")+'</b><span class="sk-step">'+esc(steps[0])+'</span><span class="sk-dots" aria-hidden="true"><i></i><i></i><i></i></span></p></div>'+
    '<div class="sk-body" aria-hidden="true">'+anSkelShape(kind)+'</div></div>';
}

function anSkelShape(kind){
  const L=(w,h)=>'<span class="sk" style="width:'+w+';height:'+(h||"12px")+'"></span>';
  const card=inner=>'<div class="sk-card">'+inner+'</div>';
  const tiles=n=>'<div class="sk-tiles">'+Array.from({length:n},()=>card(L("45%")+L("60%","26px")+L("30%","10px"))).join("")+'</div>';
  const line='<div class="sk-card sk-chart">'+L("38%","14px")+L("55%","10px")+
    '<svg viewBox="0 0 400 120" preserveAspectRatio="none"><path class="sk-grid" d="M0 30H400M0 60H400M0 90H400"/>'+
    '<path class="sk-line" d="M0 95 L40 82 L80 88 L120 60 L160 70 L200 42 L240 55 L280 30 L320 48 L360 26 L400 34"/></svg></div>';
  const cols=(n,hs)=>'<div class="sk-cols">'+Array.from({length:n},(_,i)=>'<span style="--h:'+hs[i%hs.length]+'%;--d:'+(i*90)+'ms"></span>').join("")+'</div>';
  const colCard=hs=>card(L("40%","14px")+cols(10,hs)+L("70%","10px"));
  const rows=n=>card(Array.from({length:n},()=>'<div class="sk-row"><span class="sk sk-thumb"></span><div>'+L("70%")+L("45%","10px")+'</div>'+L("48px","16px")+'</div>').join(""));
  const donut=()=>card(L("50%","14px")+'<div class="sk-donut"><span class="sk-ring"></span><div>'+L("80%")+L("65%")+L("50%")+'</div></div>');
  switch(kind){
    case "overview": return tiles(4)+line+'<div class="sk-tiles three">'+card(L("30%","10px")+L("70%","14px")+L("90%"))+card(L("30%","10px")+L("60%","14px")+L("85%"))+card(L("30%","10px")+L("65%","14px")+L("80%"))+'</div>';
    case "pairs": return '<div class="sk-grid2">'+colCard([30,80,25,60,20,45,15,35,10,20])+colCard([20,70,20,55,15,50,15,40,8,12])+colCard([12,90,10,65,10,50,8,40,6,10])+colCard([30,40,30,60,30,75,20,95,15,10])+'</div>'+rows(4);
    case "audience": return card('<div class="sk-persona"><span class="sk sk-avatar"></span><div>'+L("30%","10px")+L("85%","18px")+L("60%","18px")+'</div></div>')+'<div class="sk-grid2">'+donut()+donut()+donut()+donut()+'</div>';
    case "igaudience": return '<div class="sk-grid2">'+donut()+colCard([60,40,30,20,15,12,10,8,6,5])+'</div>';
    case "igtiles": return tiles(4);
    case "grow": return card(L("30%","10px")+L("70%","18px")+'<div class="sk-tiles three">'+card(L("50%","16px")+L("80%"))+card(L("50%","16px")+L("75%"))+card(L("50%","16px")+L("85%"))+'</div>')+card(L("40%","14px")+cols(24,[10,8,6,5,5,8,15,30,45,60,70,80,75,70,65,60,62,70,80,90,85,60,35,20]));
    case "compare": return line+rows(5);
    case "detail": return '<div class="sk-tiles">'+card(L("40%")+L("60%","24px"))+card(L("40%")+L("60%","24px"))+card(L("40%")+L("60%","24px"))+'</div>'+line+'<div class="sk-grid2">'+colCard([20,80])+colCard([30,65])+'</div>';
    case "chart": return line;
    default: return tiles(3)+rows(3);
  }
}

// One timer for every skeleton on the page: next step every 2.6 s (stays on the last), the slow note after 18 s.
function anSkelTick(){
  const all=document.querySelectorAll(".an-skel[data-t0]");
  if(!all.length){ clearInterval(anSkelTimer); anSkelTimer=null; return; }
  all.forEach(el=>{
    const s=(Date.now()-(+el.dataset.t0))/1000, steps=AN_SKEL_STEPS[el.dataset.kind]||AN_SKEL_STEPS.cards;
    const step=s>=18?AN_SKEL_SLOW:steps[Math.min(steps.length-1,Math.floor(s/2.6))];
    const sp=el.querySelector(".sk-step");
    if(sp&&sp.textContent!==step){ sp.textContent=step; sp.classList.remove("in"); void sp.offsetWidth; sp.classList.add("in"); el.classList.toggle("slow",s>=18); }
  });
}
// A small inline placeholder for one number that's still coming (Instagram tiles while the account loads).
const anSkelNum='<span class="sk sk-num" role="img" aria-label="loading"></span>';
