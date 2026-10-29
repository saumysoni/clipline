// The editor's timeline (js/editor.js mounts it with window.PitTimeline.mount): Twick's timeline showing the Short's
// pieces (pipeline/pieces.py) as clips on one video track, laid end to end, each a stretch of the vlog. Dragging a
// clip's ends trims it; Split and Delete are worked out here on the pieces. Every change goes to the page as pieces
// (vlog seconds, in the vlog's order), which keeps them (js/ai-edit.js: Undo / Redo, Save) and lays them out again
// with setPieces. Twick's own split isn't used (it reloads the video's details for each half, and loses the clip if
// that fails), nor its right-click menu, dropping files or drawing a box to select clips (dragging the empty part of the
// timeline scrolls it instead).
// Getting around (mount): zoom in / out / fit (the page's buttons; Ctrl or Cmd + wheel, or a trackpad pinch, zooms
// around the pointer), the wheel scrolls sideways, dragging an empty spot scrolls, and the view follows the playhead.
// Trimming is ours too (mount): either end of any part is a grab zone (EDGE px, no need to select it first); a part can
// grow into the vlog before or after it, up to the next part's own stretch (Twick only lets a part shrink, as the parts
// touch); while dragging, the whole Short as it will be is drawn over the video track, fitted to the box (all of it
// stays in view as a part shrinks or grows), with a label giving the new edge and lengths; the edge snaps to the gaps
// between words (Alt / Option: no snapping), the player shows that moment when it can, and Esc cancels. Held past the
// box's ends, the end keeps going, faster the further out.
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { TimelineProvider, useTimelineContext } from "@twick/timeline";
import { LivePlayerProvider, useLivePlayerContext } from "@twick/live-player";
import { TimelineManager } from "@twick/video-editor";
import "@twick/video-editor/dist/video-editor.css";
import "./timeline.css";

window.__TWICK_ANALYTICS_DISABLED__ = true;  // Twick's PostHog analytics stay off (privacy policy)

const TRACK = "t-pitcrew-video";
const NO_VIDEO = "data:video/mp4;base64,";  // no pictures (Twick won't trim a clip with no source at all)
const r3 = (x) => +x.toFixed(3);
const total = (pieces) => pieces.reduce((n, [a, b]) => n + b - a, 0);

// pieces [[a, b], ...] (vlog seconds) -> Twick's project: one track, clips end to end. An "element" track: Twick only
// takes a clip dragged on its own track for one of those. A clip's start in the vlog is props.time.
// Each layout gets new clip ids, so Twick draws its clips afresh (a clip keeps its own dragged size while its id stays).
let layout = 0;
function project(pieces, src, duration) {
  let at = 0;
  layout += 1;
  const elements = pieces.map(([a, b], k) => {
    const el = { id: "e-piece" + layout + "-" + k, trackId: TRACK, type: "video", s: r3(at), e: r3(at + b - a),
                 name: "Part " + (k + 1), frame: { x: 0, y: 0, size: [720, 1280] },
                 props: { src: src || NO_VIDEO, time: a, playbackRate: 1, volume: 1 },
                 // the vlog's length, given (Twick would otherwise read it from the video, and without one it won't trim)
                 mediaDuration: duration || Math.max(b, 1) };
    at += b - a;
    return el;
  });
  return { tracks: [{ id: TRACK, name: "Video", type: "element", elements }], version: 1 };
}

// Twick's project -> the clips, in order on the timeline: [{s, e, a, b, id}] (s..e on the Short's clock, a..b in the
// vlog). Every track counts: a clip dragged onto a new one is still a clip.
function clipsOf(data) {
  const out = [];
  for (const track of (data && data.tracks) || []) {
    for (const el of track.getElements()) {
      const s = el.getStart(), e = el.getEnd(), a = el.getStartAt ? el.getStartAt() : (el.getProps().time || 0);
      out.push({ s, e, a, b: a + (e - s), id: el.getId() });
    }
  }
  return out.sort((x, y) => x.s - y.s);
}
const piecesOf = (data) => clipsOf(data).map(c => [r3(c.a), r3(c.b)]);
// Pieces as the page keeps them (js/ai-edit.js aeNorm): in order, touching ones joined. A split that nothing has been
// done to yet is the same Short, so it isn't a change.
const tidy = (pieces) => {
  const out = [];
  for (const [a, b] of [...pieces].sort((x, y) => x[0] - y[0])) {
    if (out.length && a - out[out.length - 1][1] <= 0.05) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
    else out.push([a, b]);
  }
  return JSON.stringify(out.map(([a, b]) => [r3(a), r3(b)]));
};
const packed = (clips) => clips.every((c, k) => Math.abs(c.s - (k ? clips[k - 1].e : 0)) < 0.01);

function Bridge({ api, opts }) {
  const { editor, changeLog, selectedItem, setSelectedItem } = useTimelineContext();
  const player = useLivePlayerContext();
  const last = useRef(tidy(opts.pieces));
  const sel = useRef(null), now = useRef(0), seen = useRef(false);  // now: the playhead (set by the page, or a click on the ruler)
  sel.current = selectedItem;
  // (after Twick has finished its own update, so the page can lay the timeline out again straight away)
  const report = (p) => { last.current = tidy(p); setTimeout(() => opts.onChange && opts.onChange(p)); };
  const selected = () => {
    const el = sel.current;
    return el && el.getStart ? clipsOf(editor.getTimelineData()).findIndex(c => c.id === el.getId()) : -1;
  };
  useEffect(() => {  // what the page can ask of the timeline
    // Lay these pieces out end to end; pick = the index of the clip to keep selected (or none)
    api.setPieces = (pieces, pick) => {
      last.current = tidy(pieces);
      editor.loadProject(project(pieces, opts.src, opts.duration));
      api.setLength && api.setLength(total(pieces));
      const els = editor.getTimelineData().tracks[0].getElements();
      setSelectedItem(pick != null && pick >= 0 && els[pick] ? els[pick] : null);
    };
    api.setTime = (t) => { now.current = Math.max(0, t); player.setCurrentTime(now.current); };
    api.time = () => now.current;
    api.deselect = () => setSelectedItem(null);
    api.pieces = () => clipsOf(editor.getTimelineData()).map(c => [r3(c.a), r3(c.b)]);
    api.commit = (p) => report(p);  // a trim worked out by mount(): hand it to the page like any other change
    api.select = (k) => { const els = editor.getTimelineData().tracks[0].getElements(); setSelectedItem(els[k] || null); };
    api.selected = selected;
    api.count = () => clipsOf(editor.getTimelineData()).length;  // parts on the timeline (a split shows two)
    // Split the clip under t (the Short's clock; the playhead if not given) in two, on the timeline only (the Short is the same until one half is
    // trimmed or deleted); the second half is selected. Answers whether it did.
    api.split = (t) => {
      if (t == null) t = now.current;
      const clips = clipsOf(editor.getTimelineData());
      const k = clips.findIndex(c => t > c.s + 0.3 && t < c.e - 0.3);
      if (k < 0) return false;
      const c = clips[k], at = r3(c.a + (t - c.s));
      const p = clips.map(x => [r3(x.a), r3(x.b)]);
      p.splice(k, 1, [r3(c.a), at], [at, r3(c.b)]);
      const keep = last.current;
      api.setPieces(p, k + 1);
      last.current = keep;
      return true;
    };
    // Delete the selected clip (never the only one); answers whether it did
    api.remove = () => {
      const k = selected(), clips = clipsOf(editor.getTimelineData());
      if (k < 0 || clips.length < 2) return false;
      report(clips.filter((_, i) => i !== k).map(x => [r3(x.a), r3(x.b)]));
      return true;
    };
  });
  useEffect(() => {  // something changed on the timeline (a trim, a move): hand back the pieces
    const data = editor.getTimelineData();
    if (!data) return;
    const clips = clipsOf(data), p = clips.map(c => [r3(c.a), r3(c.b)]);
    if (!p.length) { if (seen.current) api.setPieces(JSON.parse(last.current)); return; }  // never left empty
    seen.current = true;
    if (tidy(p) !== last.current) report(p);
    else if (!packed(clips)) setTimeout(() => api.setPieces(p, selected()));  // moved into a gap: close it again
  }, [changeLog]);
  const drawn = useRef(false);  // (not the first run: nobody has clicked the ruler yet)
  useEffect(() => {
    if (drawn.current) { now.current = player.seekTime; opts.onSeek && opts.onSeek(player.seekTime); }
    drawn.current = true;
  }, [player.seekTime]);
  useEffect(() => { opts.onSelect && opts.onSelect(selected()); }, [selectedItem]);
  return null;
}

// Zoom 1 = the whole Short fits the box (Twick draws 100 px a second at its zoom 1); the page's buttons multiply it.
const HEADER = 40, ROOM = 28;  // Twick's track header column; the scroll bar and a little air at the end
const MAX_PPS = 400;  // zoomed in all the way: 400 px a second (a word or two across a part)
function App({ api, opts }) {
  const [box, setBox] = useState(opts.el.clientWidth || 800), [times, setTimes] = useState(opts.nav.times), [len, setLen] = useState(opts.length || 30);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setBox(e.contentRect.width));
    ro.observe(opts.el); opts.nav.set = setTimes; api.setLength = setLen;
    return () => ro.disconnect();
  }, []);
  const fit = Math.max(0.02, (box - HEADER - ROOM) / (Math.max(len, 1) * 100));
  const zoom = fit * times;
  opts.nav.pps = zoom * 100; opts.nav.fitPps = fit * 100;  // for getting around (mount)
  return (
    <LivePlayerProvider>
      <TimelineProvider contextId={"pitcrew-" + opts.key} initialData={project(opts.pieces, opts.src, opts.duration)}
                        analytics={{ enabled: false }} maxHistorySize={1}>
        <Bridge api={api} opts={opts} />
        <TimelineManager trackZoom={zoom}
                         timelineTickConfigs={[{ durationThreshold: 20, majorInterval: 2, minorTicks: 4 },
                                               { durationThreshold: 60, majorInterval: 5, minorTicks: 5 },
                                               { durationThreshold: 200, majorInterval: 10, minorTicks: 5 }]}
                         elementColors={{ video: "#E8002D", audio: "#3D8B8B", image: "#D4956C", text: "#A78EC8",
                                          caption: "#9B8ACE", fragment: "#1A1A1A" }} />
      </TimelineProvider>
    </LivePlayerProvider>
  );
}

// opts: {key, src (a playable copy of the vlog, for the clips' pictures; "" for none), duration (the vlog's), pieces, onChange(pieces),
// onSeek(t: the Short's clock), onSelect(index of the selected clip, or -1), onZoom(times: 1 = the whole Short fits),
// canEdit() (trimming is on), snaps(side: "start" | "end") (vlog seconds an edge can snap to: the gaps between words),
// onScrub(t: vlog seconds, while an edge is dragged)}
// px of each end that drags it; px to snap within; the shortest a part can be dragged to (s: safely over the 0.3 s under
// which the page drops a part, js/ai-edit.js AE_MIN_PIECE, so a part never vanishes by being dragged short)
const EDGE = 12, SNAP = 8, MIN_PART = 0.5;
const clock = (t) => { const m = Math.floor(t / 60), s = t - m * 60; return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1); };
function mount(el, opts) {
  // The page's handle. The timeline fills in `impl` once it's drawn; until then the calls do nothing.
  const impl = {}, api = {}, nav = { times: 1, pps: 0, fitPps: 0, set: null };
  for (const [name, none] of [["setPieces"], ["time", 0], ["selected", -1], ["count", 0], ["split", false], ["remove", false],
    ["pieces", []], ["select"], ["deselect"]])  // pieces / select / deselect: for Trim's strip (js/trim-strip.js)
    api[name] = (...args) => (impl[name] ? impl[name](...args) : none);
  el.classList.add("pc-tl");  // Twick's styles only apply inside (vite.config.js)
  const box = () => el.querySelector(".twick-timeline-scroll-container");
  // ---- zoom: times 1 = the whole Short fits; around a point (px from the timeline's left edge), else the playhead
  // (if it's in view), else the left edge
  const maxTimes = () => Math.max(1, nav.fitPps ? MAX_PPS / nav.fitPps : 8);
  function zoomTo(t, anchorX) {
    t = Math.min(maxTimes(), Math.max(1, t));
    if (Math.abs(t - nav.times) < 0.001) return;
    const sc = box(), old = nav.pps || 1;
    let ax = anchorX;
    if (ax == null && sc) {
      const ph = HEADER + api.time() * old - sc.scrollLeft;
      ax = ph >= HEADER && ph <= sc.clientWidth ? ph : HEADER;
    }
    const at = sc ? (sc.scrollLeft + (ax || HEADER) - HEADER) / old : 0;  // the second under the anchor stays there
    nav.times = t;
    if (nav.set) nav.set(t);
    opts.onZoom && opts.onZoom(t, maxTimes());
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const s2 = box(); if (s2) s2.scrollLeft = Math.max(0, at * nav.pps + HEADER - (ax || HEADER));
    }));
  }
  api.zoomIn = () => zoomTo(nav.times * 1.6);
  api.zoomOut = () => zoomTo(nav.times / 1.6);
  api.fit = () => { zoomTo(1); const sc = box(); if (sc) sc.scrollLeft = 0; };
  api.zoom = () => ({ times: nav.times, max: maxTimes() });
  // ---- the playhead: set by the page as the player moves; the view follows it when it leaves the screen
  api.setTime = (t) => {
    if (!impl.setTime) return;
    impl.setTime(t);
    const sc = box(); if (!sc || !nav.pps) return;
    const x = HEADER + Math.max(0, t) * nav.pps, left = sc.scrollLeft + HEADER, right = sc.scrollLeft + sc.clientWidth - 12;
    if (x < left || x > right) sc.scrollLeft = Math.max(0, x - HEADER - (sc.clientWidth - HEADER) * 0.2);
  };
  // ---- the wheel scrolls sideways; Ctrl / Cmd + wheel (a trackpad pinch) zooms around the pointer
  const wheel = (e) => {
    const sc = box(); if (!sc) return;
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      zoomTo(nav.times * Math.exp(-Math.max(-60, Math.min(60, e.deltaY)) * 0.01), e.clientX - sc.getBoundingClientRect().left);
    } else if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && sc.scrollWidth > sc.clientWidth + 1) {
      e.preventDefault();
      sc.scrollLeft += e.deltaY;
    }
  };
  // ---- trimming: drag either end of any part (see the top). While dragging, a lane over the video track shows the whole
  // Short as it will be (every part, laid end to end, fitted to the box), so all of it stays in view whether the part
  // shrinks or grows; the part being dragged is lit, and a label (tip) over its moving edge gives the times. The lane
  // has its own seconds (the ruler above is dimmed: it's the old scale) and marks where the Short ended before. Pointer
  // to seconds keeps the scale the drag started at (trim.pps), so the edge doesn't run away as the lane re-fits.
  let trim = null, swallow = false;
  const lane = document.createElement("div"), tip = document.createElement("div");
  const laneParts = document.createElement("div"), laneTicks = document.createElement("div"), laneWas = document.createElement("b");
  lane.className = "pc-trim-lane"; tip.className = "pc-trim-tip"; lane.hidden = tip.hidden = true;
  laneParts.className = "pc-trim-parts"; laneTicks.className = "pc-trim-ticks"; laneWas.className = "pc-trim-was";
  lane.append(laneParts, laneTicks, laneWas);
  const parts = () => [...el.querySelectorAll(".twick-track-element")].sort((p, q) => p.getBoundingClientRect().left - q.getBoundingClientRect().left);
  // Where the lane goes (px in el): where Twick lays the Short out when it fits, at the video track's height
  const laneBox = (r) => {
    const sc = box(), er = el.getBoundingClientRect(), sr = sc ? sc.getBoundingClientRect() : er;
    return { left: sr.left - er.left + HEADER, width: Math.max(40, (sc ? sc.clientWidth : er.width) - HEADER - ROOM),
             top: r.top - er.top, height: r.height, cl: sr.left + HEADER };
  };
  const trimStart = (e) => {
    const clipEl = e.target.closest && e.target.closest(".twick-track-element");
    if (e.button !== 0 || !clipEl || !impl.pieces || !nav.pps || (opts.canEdit && !opts.canEdit())) return false;
    const r = clipEl.getBoundingClientRect(), zone = Math.min(EDGE, r.width / 4);
    const side = e.clientX - r.left <= zone ? "start" : r.right - e.clientX <= zone ? "end" : null;
    const k = parts().indexOf(clipEl), p = impl.pieces();
    if (!side || k < 0 || !p[k]) return false;
    e.preventDefault(); e.stopPropagation();
    trim = { k, side, x0: e.clientX, p, r, pps: nav.pps, box: laneBox(r), id: e.pointerId, val: null, extra: 0,
             at: { clientX: e.clientX, altKey: e.altKey }, t: 0 };
    laneParts.replaceChildren(...p.map((_, n) => { const d = document.createElement("i"); if (n === k) d.className = "on " + side; return d; }));
    el.setPointerCapture(e.pointerId); inner.classList.add("pc-trimming");
    trimMove(trim.at);
    trim.raf = requestAnimationFrame(edgeRun);
    return true;
  };
  // Past the lane's ends: while the pointer is held beyond them (right for an end, left for a start), `extra` seconds
  // keep being added (1 to 8 a second, by how far out), so a part can grow as far as it can.
  const edgeRun = (ts) => {
    if (!trim) return;
    const dtf = trim.t ? Math.min(0.05, (ts - trim.t) / 1000) : 0, B = trim.box;
    trim.t = ts;
    if (dtf) {
      const x = trim.at.clientX, start = trim.side === "start";
      const out = start ? B.cl + 2 - x : x - (B.cl + B.width - 2);
      if (out > 0) { trim.extra += (start ? -1 : 1) * Math.min(8, 1 + out / 12) * dtf; trimMove(trim.at); }
    }
    trim.raf = requestAnimationFrame(edgeRun);
  };
  const trimMove = (e) => {
    trim.at = { clientX: e.clientX, altKey: e.altKey };
    const [a, b] = trim.p[trim.k], prev = trim.p[trim.k - 1], next = trim.p[trim.k + 1];
    const dt = (e.clientX - trim.x0) / trim.pps + trim.extra, start = trim.side === "start";
    const lo = start ? Math.max(0, prev ? prev[1] : 0) : a + MIN_PART;
    const hi = start ? b - MIN_PART : Math.min(opts.duration || Infinity, next ? next[0] : Infinity);
    const raw = (start ? a : b) + dt;
    let v = Math.min(hi, Math.max(lo, raw)), snapped = false;
    trim.extra -= raw - v;  // at a limit: going back starts at once, not after undoing what piled up past it
    if (!e.altKey && opts.snaps) {  // the nearest gap between words, if it's close on screen
      let best = null;
      for (const c of opts.snaps(trim.side) || []) if (c >= lo && c <= hi && (best == null || Math.abs(c - v) < Math.abs(best - v))) best = c;
      if (best != null && Math.abs(best - v) * trim.pps <= SNAP) { v = best; snapped = true; }
    }
    trim.val = v;
    // the lane: the whole Short as it will be, fitted to the box
    const p = trim.p.map(x => [...x]); p[trim.k][start ? 0 : 1] = v;
    const all = p.reduce((n, [x, y]) => n + y - x, 0), B = trim.box, k2 = B.width / Math.max(0.1, all);
    let at = 0, edge = 0;
    p.forEach(([x, y], n) => {
      const d = laneParts.children[n], w = (y - x) * k2;
      Object.assign(d.style, { left: at * k2 + "px", width: Math.max(1, w - 2) + "px" });
      if (n === trim.k) edge = (start ? at : at + (y - x)) * k2;
      at += y - x;
    });
    Object.assign(lane.style, { left: B.left + "px", width: B.width + "px", top: B.top + "px", height: B.height + "px" });
    lane.classList.toggle("snapped", snapped);
    // its seconds (a tick every 1, 2, 5, 10... s, at least 44 px apart) and where the Short ended before
    const step = [1, 2, 5, 10, 15, 30, 60, 120].find(x => x * k2 >= 44) || 300;
    let ticks = "";
    for (let t = 0; t <= all + 1e-6; t += step)
      ticks += `<i style="left:${(t * k2).toFixed(1)}px"${t * k2 > B.width - 30 ? "" : ` data-t="${clock(t).replace(/\.\d$/, "")}"`}></i>`;
    laneTicks.innerHTML = ticks;
    const was = trim.p.reduce((n, [x, y]) => n + y - x, 0);
    laneWas.hidden = Math.abs(was - all) < 0.05;
    laneWas.style.left = (was * k2).toFixed(1) + "px";
    laneWas.textContent = "was " + clock(was).replace(/\.\d$/, "");
    const len = start ? b - v : v - a;
    tip.textContent = (start ? "Starts " : "Ends ") + clock(v) + " in the vlog · this part " + len.toFixed(1) + " s · Short " +
      clock(all).replace(/\.\d$/, "") + (snapped ? " · at a word" : "");
    lane.hidden = tip.hidden = false;
    const er = el.getBoundingClientRect(), ex = B.left + edge;
    tip.style.left = Math.max(4, Math.min(er.width - tip.offsetWidth - 4, ex - tip.offsetWidth / 2)) + "px";
    tip.style.top = Math.max(0, B.top - tip.offsetHeight - 6) + "px";
    if (opts.onScrub) opts.onScrub(v);
  };
  const trimEnd = (e, cancel) => {
    const t = trim; trim = null; swallow = true; setTimeout(() => { swallow = false; });
    cancelAnimationFrame(t.raf);
    try { el.releasePointerCapture(t.id); } catch (_) { /* already released */ }
    inner.classList.remove("pc-trimming"); lane.hidden = tip.hidden = true;
    if (cancel || t.val == null) return;
    const p = t.p.map(x => [...x]), at = t.side === "start" ? 0 : 1;
    if (Math.abs(p[t.k][at] - t.val) < 0.005) return;
    p[t.k][at] = r3(t.val);
    if (impl.select) impl.select(t.k);
    impl.commit(p);
  };
  const keys = (e) => { if (trim && e.key === "Escape") { e.preventDefault(); trimEnd(e, true); } };
  // ---- dragging an empty spot (not a part, its ends or the ruler) scrolls; a click there unselects the part
  let pan = null, panned = false;
  const down = (e) => {
    const sc = box();
    if (e.button !== 0 || !sc || !sc.contains(e.target)) return;
    if (trimStart(e)) return;
    if (e.target.closest(".twick-track-element, .twick-seek-track, .twick-seek-track-empty-space, [class*='handle']")) return;
    e.preventDefault(); e.stopPropagation();  // (no box to select clips)
    pan = { x: e.clientX, left: sc.scrollLeft, id: e.pointerId, moved: false };
    el.setPointerCapture(e.pointerId); el.classList.add("pc-panning");
  };
  const move = (e) => {
    if (trim && e.pointerId === trim.id) { e.preventDefault(); e.stopPropagation(); trimMove(e); return; }
    if (!pan || e.pointerId !== pan.id) return;
    const dx = e.clientX - pan.x;
    if (Math.abs(dx) > 3) pan.moved = true;
    if (pan.moved) box().scrollLeft = pan.left - dx;
  };
  const up = (e) => {
    if (trim && e.pointerId === trim.id) { e.preventDefault(); e.stopPropagation(); trimEnd(e, e.type === "pointercancel"); return; }
    if (!pan || e.pointerId !== pan.id) return;
    if (!pan.moved && impl.deselect) impl.deselect();
    panned = pan.moved; pan = null; el.classList.remove("pc-panning");
    setTimeout(() => { panned = false; });
  };
  const click = (e) => { if (panned || swallow) { e.preventDefault(); e.stopPropagation(); } };
  // (Twick listens for mouse events too: during a trim they're ours)
  const mouse = (e) => { if (trim || swallow) { e.preventDefault(); e.stopPropagation(); } };
  // Twick's right-click menu and dropping files on the timeline are turned off: caught before they reach it
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
  const on = [["contextmenu", stop], ["dragover", stop], ["drop", stop], ["pointerdown", down], ["pointermove", move],
              ["pointerup", up], ["pointercancel", up], ["click", click], ["mousedown", mouse], ["mouseup", mouse], ["mousemove", mouse]];
  on.forEach(([t, f]) => el.addEventListener(t, f, true));
  el.addEventListener("wheel", wheel, { passive: false });
  const inner = document.createElement("div");
  inner.className = "pc-tl-root";
  el.replaceChildren(inner, lane, tip);
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  document.addEventListener("keydown", keys, true);
  // read-only (the vlog's video is gone): no grips on the parts' ends
  api.setEditable = (on) => inner.classList.toggle("pc-ro", !on);
  opts = { ...opts, el, nav, length: total(opts.pieces || []) };
  const root = createRoot(inner);
  root.render(<App api={impl} opts={opts} />);
  api.destroy = () => {
    root.unmount();
    on.forEach(([t, f]) => el.removeEventListener(t, f, true));
    el.removeEventListener("wheel", wheel);
    document.removeEventListener("keydown", keys, true);
    el.classList.remove("pc-panning"); el.replaceChildren();
  };
  return api;
}

window.PitTimeline = { mount, project, piecesOf };
