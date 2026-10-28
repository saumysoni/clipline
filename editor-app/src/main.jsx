// The editor's timeline (js/editor.js mounts it with window.PitTimeline.mount): Twick's timeline showing the Short's
// pieces (pipeline/pieces.py) as clips on one video track, laid end to end, each a stretch of the vlog. Dragging a
// clip's ends trims it; Split and Delete are worked out here on the pieces. Every change goes to the page as pieces
// (vlog seconds, in the vlog's order), which keeps them (js/ai-edit.js: Undo / Redo, Save) and lays them out again
// with setPieces. Twick's own split isn't used (it reloads the video's details for each half, and loses the clip if
// that fails), nor its right-click menu, dropping files or drawing a box to select clips (dragging the empty part of the
// timeline scrolls it instead).
// Getting around (mount): zoom in / out / fit (the page's buttons; Ctrl or Cmd + wheel, or a trackpad pinch, zooms
// around the pointer), the wheel scrolls sideways, dragging an empty spot scrolls, and the view follows the playhead.
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
// onSeek(t: the Short's clock), onSelect(index of the selected clip, or -1), onZoom(times: 1 = the whole Short fits)}
function mount(el, opts) {
  // The page's handle. The timeline fills in `impl` once it's drawn; until then the calls do nothing.
  const impl = {}, api = {}, nav = { times: 1, pps: 0, fitPps: 0, set: null };
  for (const [name, none] of [["setPieces"], ["time", 0], ["selected", -1], ["count", 0], ["split", false], ["remove", false]])
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
  // ---- dragging an empty spot (not a part, its ends or the ruler) scrolls; a click there unselects the part
  let pan = null, panned = false;
  const down = (e) => {
    const sc = box();
    if (e.button !== 0 || !sc || !sc.contains(e.target)) return;
    if (e.target.closest(".twick-track-element, .twick-seek-track, .twick-seek-track-empty-space, [class*='handle']")) return;
    e.preventDefault(); e.stopPropagation();  // (no box to select clips)
    pan = { x: e.clientX, left: sc.scrollLeft, id: e.pointerId, moved: false };
    el.setPointerCapture(e.pointerId); el.classList.add("pc-panning");
  };
  const move = (e) => {
    if (!pan || e.pointerId !== pan.id) return;
    const dx = e.clientX - pan.x;
    if (Math.abs(dx) > 3) pan.moved = true;
    if (pan.moved) box().scrollLeft = pan.left - dx;
  };
  const up = (e) => {
    if (!pan || e.pointerId !== pan.id) return;
    if (!pan.moved && impl.deselect) impl.deselect();
    panned = pan.moved; pan = null; el.classList.remove("pc-panning");
    setTimeout(() => { panned = false; });
  };
  const click = (e) => { if (panned) { e.preventDefault(); e.stopPropagation(); } };
  // Twick's right-click menu and dropping files on the timeline are turned off: caught before they reach it
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
  const on = [["contextmenu", stop], ["dragover", stop], ["drop", stop], ["pointerdown", down], ["pointermove", move],
              ["pointerup", up], ["pointercancel", up], ["click", click]];
  on.forEach(([t, f]) => el.addEventListener(t, f, true));
  el.addEventListener("wheel", wheel, { passive: false });
  const inner = document.createElement("div");
  inner.className = "pc-tl-root";
  el.replaceChildren(inner);
  opts = { ...opts, el, nav, length: total(opts.pieces || []) };
  const root = createRoot(inner);
  root.render(<App api={impl} opts={opts} />);
  api.destroy = () => {
    root.unmount();
    on.forEach(([t, f]) => el.removeEventListener(t, f, true));
    el.removeEventListener("wheel", wheel);
    el.classList.remove("pc-panning"); el.replaceChildren();
  };
  return api;
}

window.PitTimeline = { mount, project, piecesOf };
