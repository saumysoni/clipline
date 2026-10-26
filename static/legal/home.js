// The homepage's animations (static/legal/welcome.html, styles in home.css). Everything here is decoration: without it
// the page shows each part in its finished state. Respects "reduce motion", pauses off screen and in background tabs.
(function(){
  "use strict";
  var $ = function(id){ return document.getElementById(id); };
  var calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var watch = function(el, cb, threshold){  // cb(true/false) as el comes into / leaves view
    if(!el) return;
    if(!("IntersectionObserver" in window)){ cb(true); return; }
    new IntersectionObserver(function(es){ es.forEach(function(e){ cb(e.isIntersecting); }); }, {threshold: threshold || 0.2}).observe(el);
  };

  // ---- captions: each word lights up in turn
  function cycleWords(cap){
    var words = cap.querySelectorAll("span"), i = -1;
    return function(){
      if(words[i]) words[i].classList.remove("on");
      i = (i + 1) % (words.length + 2);  // a short rest after the last word
      if(words[i]) words[i].classList.add("on");
    };
  }

  // ---- the hero: a vlog becomes three Shorts, planned for the week
  var stage = $("hmStage"), pause = $("hmPause");
  if(stage){
    var STEPS = [[1, 0], [2, 2900], [3, 4700], [4, 7700], [0, 11800]];  // [step, ms from the start of the loop]
    var phoneCaps = [].map.call(stage.querySelectorAll(".hm-cap"), cycleWords);
    var timers = [], wordTimer = 0, paused = false, onScreen = true, running = false;
    var show = function(n){
      for(var k = 1; k <= 4; k++) stage.classList.toggle("p" + k, k <= n);
      stage.setAttribute("data-st", n);
    };
    var stop = function(){ timers.forEach(clearTimeout); timers = []; clearInterval(wordTimer); wordTimer = 0; running = false; };
    var loop = function(){
      stop(); running = true; show(0);
      STEPS.forEach(function(s){
        timers.push(setTimeout(function(){
          show(s[0]);
          if(s[0] === 3) wordTimer = setInterval(function(){ phoneCaps.forEach(function(f){ f(); }); }, 340);
          if(s[0] === 0){ clearInterval(wordTimer); timers.push(setTimeout(loop, 500)); }
        }, s[1] + 60));
      });
    };
    var update = function(){
      var go = !paused && onScreen && !document.hidden;
      stage.classList.toggle("paused", !go);
      if(go && !running) loop();
      else if(!go && running){ stop(); show(4); }  // stopped: the finished picture
    };
    stage.classList.add("js");
    if(calm){ show(4); if(pause) pause.hidden = true; }
    else {
      watch(stage, function(v){ onScreen = v; update(); }, 0.15);
      document.addEventListener("visibilitychange", update);
      if(pause) pause.onclick = function(){
        paused = !paused;
        pause.setAttribute("aria-pressed", paused);
        pause.textContent = paused ? "Play animation" : "Pause animation";
        update();
      };
      update();
    }
  }

  // ---- how it works: tabs that move on by themselves until someone picks one
  var tablist = document.querySelector(".hm-tabs");
  if(tablist){
    var tabs = [].slice.call(tablist.querySelectorAll('[role="tab"]')), TAB_MS = 6000, auto = !calm, tabTimer = 0, tabsSeen = false;
    var select = function(t, focus){
      tabs.forEach(function(x){
        var on = x === t;
        x.setAttribute("aria-selected", on); x.tabIndex = on ? 0 : -1;
        $(x.getAttribute("aria-controls")).hidden = !on;
      });
      if(focus) t.focus();
      if(auto && tabsSeen){  // restart the progress line on the new tab
        tablist.classList.remove("auto"); void tablist.offsetWidth; tablist.classList.add("auto");
      }
    };
    var next = function(){ var i = tabs.findIndex(function(t){ return t.getAttribute("aria-selected") === "true"; }); select(tabs[(i + 1) % tabs.length]); };
    var stopAuto = function(){ auto = false; clearInterval(tabTimer); tablist.classList.remove("auto"); };
    tablist.style.setProperty("--tab-ms", TAB_MS + "ms");
    tabs.forEach(function(t, i){
      t.onclick = function(){ stopAuto(); select(t); };
      t.onkeydown = function(e){
        var j = {ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1}[e.key];
        if(j === undefined) return;
        e.preventDefault(); stopAuto(); select(tabs[(j + tabs.length) % tabs.length], true);
      };
    });
    watch(tablist.parentNode, function(v){
      clearInterval(tabTimer);
      if(!auto) return;
      tabsSeen = v;
      if(v){ tablist.classList.add("auto"); tabTimer = setInterval(next, TAB_MS); }
      else tablist.classList.remove("auto");
    }, 0.4);
  }

  // ---- caption styles
  var demo = $("hmDemoCap"), group = document.querySelector(".hm-styles");
  if(demo && group){
    var radios = [].slice.call(group.querySelectorAll('[role="radio"]'));
    var pick = function(r, focus){
      radios.forEach(function(x){ var on = x === r; x.setAttribute("aria-checked", on); x.tabIndex = on ? 0 : -1; });
      demo.className = "hm-cap demo " + r.getAttribute("data-style");
      if(focus) r.focus();
    };
    radios.forEach(function(r, i){
      r.onclick = function(){ pick(r); };
      r.onkeydown = function(e){
        var j = {ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1}[e.key];
        if(j === undefined) return;
        e.preventDefault(); pick(radios[(j + radios.length) % radios.length], true);
      };
    });
    if(calm) demo.querySelector("span").classList.add("on");
    else {
      var demoWords = cycleWords(demo), demoTimer = 0;
      watch(demo.closest(".hm-two"), function(v){ clearInterval(demoTimer); if(v) demoTimer = setInterval(demoWords, 420); });
    }
  }

  // ---- the example chart grows when it comes into view; hovering a bar shows its (example) number
  var chart = $("hmChart");
  if(chart){
    [].forEach.call(chart.querySelectorAll(".g"), function(g){
      var clip = g.querySelector("small").textContent;
      [].forEach.call(g.querySelectorAll("i"), function(b){
        var n = Math.round(parseFloat(b.style.getPropertyValue("--v")) * 120) * 100;
        b.setAttribute("data-n", n.toLocaleString("en-US") + " views");
        b.title = clip + ", " + (b.classList.contains("yt") ? "YouTube" : "Instagram") + ": " + n.toLocaleString("en-US") + " views (example)";
      });
    });
    if(!calm){ chart.classList.add("js"); watch(chart, function(v){ if(v) chart.classList.add("in"); }, 0.35); }
  }

  // ---- sections slide in as you scroll to them
  if(!calm && "IntersectionObserver" in window){
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add("in"); io.unobserve(e.target); } });
    }, {threshold: 0.12, rootMargin: "0px 0px -40px 0px"});
    [].forEach.call(document.querySelectorAll(".hm-sec"), function(s){
      if(s.getBoundingClientRect().top < innerHeight) return;  // already on screen: no jump
      s.classList.add("rv"); io.observe(s);
    });
  }
})();
