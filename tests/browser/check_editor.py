"""
The editor in a real browser (Playwright + Chromium): the timeline (Twick, editor-app/), Trim, AI Edit and Captions together,
against Pit Crew's real server with the outside world faked (tests/fakes.py) and real FFmpeg renders. Every action a
person can take on the timeline, then what the server saved.

    pip install playwright && python -m playwright install chromium   (once)
    python -m tests.browser.check_editor                               (about 3 minutes; exits 1 on a failure)
    PITCREW_BROWSER=webkit python -m tests.browser.check_editor        (the same in Safari's engine: playwright install webkit)

Not part of `unittest discover` (it needs a browser).
"""
import os
import sys
import threading
import time
import urllib.request

os.environ["PITCREW_REAL_MEDIA"] = "1"
from tests import fakes as F  # noqa: E402  (first: clean settings, fakes, throwaway folders)

import glob  # noqa: E402
import json  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import serve  # noqa: E402

from settings import JOBS_DIR  # noqa: E402

PORT = int(os.getenv("PITCREW_TEST_PORT", "8791"))
B = f"http://127.0.0.1:{PORT}"
fails, passes = [], 0


def start_server():
    """Two vlogs with two Shorts each, for me@example.com; the server in the background."""
    app = F.app()
    c = F.client(F.new_user(email="me@example.com"))
    jobs = []
    for _ in range(2):
        jid, st = F.make_shorts(c, 120, 2)
        jobs.append({"id": jid, "shorts": [[s["idx"], s["start"], s["end"]] for s in st["shorts"]]})
    threading.Thread(target=lambda: serve(app, host="127.0.0.1", port=PORT, threads=8, _quiet=True), daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(B + "/healthz", timeout=2)
            break
        except OSError:
            time.sleep(0.1)
    return {"jobs_dir": str(JOBS_DIR), "jobs": jobs}


H = start_server()
A, BJ = H["jobs"][0]["id"], H["jobs"][1]["id"]


def check(cond, what):
    global passes
    if cond:
        passes += 1
        print("  ok  ", what)
    else:
        fails.append(what)
        print("  FAIL", what)


def near(a, b, tol=0.6):
    return abs(a - b) <= tol


with sync_playwright() as p:
    br = getattr(p, os.getenv("PITCREW_BROWSER", "chromium")).launch()  # PITCREW_BROWSER=webkit: Safari's engine
    pg = br.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errs, outside = [], set()
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:300]))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and errs.append(m.text[:300]))
    pg.on("request", lambda r: not r.url.startswith((B, "data:", "blob:")) and outside.add(r.url.split("?")[0]))
    pg.goto(B + "/")
    pg.evaluate("""fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({email:'me@example.com',password:'password-123'})})""")
    ev = pg.evaluate
    P = lambda: ev("edAE.pieces()")
    SV = lambda: ev("edAE.saved()")
    parts = lambda: pg.locator("#edTwick .twick-track-element")
    state = lambda: pg.inner_text("#edState")
    summ = lambda: pg.inner_text(".tr-sum").replace("\n", " ")
    server = lambda j, i: ev(f"fetch('/api/ai-edit/{j}/{i}').then(r=>r.json())")

    def open_short(j, i):
        pg.goto(B + f"/#edit/{j}/{i}")
        pg.wait_for_function("edAE.info() && window.PitTimeline && document.querySelectorAll('#edTwick .twick-track-element').length>0", timeout=20000)
        pg.wait_for_timeout(500)

    def tool(t):
        pg.click(f'#edRail button[data-t="{t}"]')
        pg.wait_for_timeout(300)

    def select(k):
        bb = parts().nth(k).bounding_box()
        pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        pg.wait_for_timeout(300)

    def drag_handle(k, side, dx, alt=False):
        """Drag part k's start or end (just inside its edge: no need to select it first) by dx px."""
        bb = parts().nth(k).bounding_box()
        x, y = (bb["x"] + 4 if side == "start" else bb["x"] + bb["width"] - 4), bb["y"] + bb["height"] / 2
        if alt:
            pg.keyboard.down("Alt")
        pg.mouse.move(x, y); pg.mouse.down()
        for n in range(1, 21):
            pg.mouse.move(x + dx * n / 20, y); pg.wait_for_timeout(12)
        pg.mouse.up(); pg.wait_for_timeout(700)
        if alt:
            pg.keyboard.up("Alt")

    def px_per_sec():
        bb = parts().first.bounding_box()
        return bb["width"] / (P()[0][1] - P()[0][0])

    def seek_video(t):
        ev(f"document.getElementById('edVideo').currentTime={t}")
        pg.wait_for_function(f"Math.abs(edTl.time()-({t}+(edAE.saved()[0][0]-edAE.pieces()[0][0])))<0.3 || true")
        pg.wait_for_timeout(3000)

    def wait_saved():
        pg.wait_for_function("document.getElementById('edState').textContent==='Saved'", timeout=90000)
        pg.wait_for_function("edAE.info() && !edAE.dirty()", timeout=30000)
        pg.wait_for_timeout(1500)

    def packed():
        bbs = [parts().nth(k).bounding_box() for k in range(parts().count())]
        return all(abs(bbs[k]["x"] - (bbs[k - 1]["x"] + bbs[k - 1]["width"])) < 4 for k in range(1, len(bbs)))

    # ---------------------------------------------------------------- 1. open
    print("1. Opening a draft")
    j0 = H["jobs"][0]["shorts"][1]  # [idx, start, end]
    open_short(A, 2)
    tool("trim")
    s0, e0 = j0[1], j0[2]
    check(P() == [[s0, e0]], f"pieces are the moment {P()}")
    check(parts().count() == 1, "one part on the timeline")
    check(state() == "Saved", "state Saved")
    check("0:31" in summ() and "0:47 to 1:18" in summ(), "Trim summary: " + summ())
    tw = pg.locator("#edTwick").bounding_box(); bb = parts().first.bounding_box()
    check(bb["x"] + bb["width"] <= tw["x"] + tw["width"] + 1 and bb["width"] > tw["width"] * 0.8, "the part fills the timeline at zoom 1")

    # ---------------------------------------------------------------- 2. drag the ends
    print("2. Dragging the ends")
    pps = px_per_sec()
    drag_handle(0, "end", -100)
    e1 = P()[0][1]
    check(near(e1, e0 - 100 / pps, 0.8), f"end trimmed by ~{100/pps:.1f}s: {e0} -> {e1}")
    check(state() == "1 change not saved", "state: " + state())
    check(parts().count() == 1 and packed(), "still one part, laid out")
    drag_handle(0, "start", 60)
    pps = px_per_sec()
    s1 = P()[0][0]
    check(s1 > s0 + 1 and P()[0][1] == e1, f"start trimmed: {s0} -> {s1}, end kept")
    check(parts().first.bounding_box()["x"] - pg.locator("#edTwick .twick-track").first.bounding_box()["x"] < 4, "the part starts at 0 again (no gap)")

    # ---------------------------------------------------------------- 3. nudge: reach past the moment
    print("3. Start / End buttons, reaching past the moment")
    pg.click('[data-end="0"][data-d="-5"]'); pg.wait_for_timeout(300)
    pg.click('[data-end="0"][data-d="-5"]'); pg.wait_for_timeout(300)
    check(near(P()[0][0], s1 - 10, 0.01), f"start 10 s earlier: {P()[0][0]}")
    check("past the original moment" in summ(), "summary says past the moment")
    pg.click('[data-end="1"][data-d="5"]'); pg.wait_for_timeout(300)
    check(near(P()[0][1], e1 + 5, 0.01), f"end 5 s later: {P()[0][1]}")
    check(near(ev("aeLen(edAE.pieces())"), (e1 + 5) - (s1 - 10), 0.01), "length adds up")
    tl_len = sum(parts().nth(k).bounding_box()["width"] for k in range(parts().count())) / px_per_sec()
    check(near(tl_len, ev("aeLen(edAE.pieces())"), 0.5), f"the timeline shows the new length ({tl_len:.1f}s)")

    # ---------------------------------------------------------------- 4. split and delete
    print("4. Split and delete")
    before = P()
    seek_video(5)  # the saved video's 0:05
    at = ev("edTl.time()")
    exp_at = (s0 + 5) - before[0][0]
    check(near(at, exp_at, 0.3), f"the playhead follows the player ({at:.2f} vs {exp_at:.2f})")
    pg.click("#edSplit"); pg.wait_for_timeout(600)
    check(parts().count() == 2, "split: two parts on the timeline")
    check(P() == before, "split alone doesn't change the Short")
    check(not pg.locator("#edDel").is_disabled(), "Delete part is on (second half chosen)")
    pg.keyboard.press("Delete"); pg.wait_for_timeout(700)
    cut_at = round(before[0][0] + at, 1)
    check(len(P()) == 1 and near(P()[0][1], cut_at, 0.15) and P()[0][0] == before[0][0], f"Delete key took the second half: {P()}")
    check(parts().count() == 1, "one part again")
    # split in the middle, delete the middle → two pieces with a gap
    whole = P()
    mid = (whole[0][1] - whole[0][0])
    ev(f"edTl.setTime({mid*0.3})"); pg.click("#edSplit"); pg.wait_for_timeout(500)
    ev(f"edTl.setTime({mid*0.6})"); pg.click("#edSplit"); pg.wait_for_timeout(500)
    check(parts().count() == 3, "two splits: three parts")
    select(1)
    pg.click("#edDel"); pg.wait_for_timeout(600)
    p2 = P()
    check(len(p2) == 2 and near(p2[0][1], whole[0][0] + mid * 0.3, 0.1) and near(p2[1][0], whole[0][0] + mid * 0.6, 0.1),
          f"the middle part is gone: {p2}")
    check(parts().count() == 2 and packed(), "two parts, end to end")
    check("2 parts" in summ(), "summary: " + summ())

    # ---------------------------------------------------------------- 5. moving a part leaves no gap / order
    print("5. Moving a part")
    bb = parts().nth(1).bounding_box()
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); pg.mouse.down()
    for n in range(1, 16):
        pg.mouse.move(bb["x"] + bb["width"] / 2 + 6 * n, bb["y"] + bb["height"] / 2); pg.wait_for_timeout(12)
    pg.mouse.up(); pg.wait_for_timeout(900)
    check(P() == p2, "moving a part doesn't change the Short")
    check(packed(), "the gap closes again")

    # ---------------------------------------------------------------- 6. right-click and file drops do nothing
    print("6. Twick's own menu is off")
    bb = parts().first.bounding_box()
    pg.mouse.click(bb["x"] + 20, bb["y"] + 10, button="right"); pg.wait_for_timeout(300)
    check(ev("[...document.querySelectorAll('body *')].filter(e=>e.offsetParent&&!e.children.length&&['Split','Delete'].includes(e.textContent.trim())).length") == 0,
          "no right-click menu")
    check(P() == p2, "nothing changed")

    # ---------------------------------------------------------------- 7. undo / redo
    print("7. Undo / Redo")
    n_undo = 0
    while not pg.locator("#edUndo").is_disabled() and n_undo < 20:
        pg.click("#edUndo"); n_undo += 1; pg.wait_for_timeout(200)
    check(P() == [[s0, e0]] and state() == "Saved" and parts().count() == 1, f"undo x{n_undo} back to the saved Short")
    for _ in range(n_undo):
        pg.click("#edRedo"); pg.wait_for_timeout(200)
    check(P() == p2 and parts().count() == 2, "redo all the way")

    # ---------------------------------------------------------------- 7b. smoother trimming
    print("7b. Trimming: any part's ends, stretching, snapping, the label, Esc")
    sep = pg.locator("#edTwick .twick-timeline-separator").first.bounding_box()  # a click on an empty spot: nothing chosen
    pg.mouse.click(sep["x"] + 200, sep["y"] + sep["height"] / 2); pg.wait_for_timeout(300)
    check(ev("edTlSel") == -1, "no part chosen")
    snaps = lambda side: ev(f"edTrimSnaps('{side}')")
    near_snap = lambda v, side: min(abs(v - c) for c in snaps(side)) < 0.002
    # a part that isn't chosen: grab its end and stretch it (Twick only let parts shrink: they touch)
    b0 = P()
    drag_handle(0, "end", 40)
    check(len(P()) == 2 and P()[0][1] > b0[0][1] + 0.5 and P()[0][1] <= b0[1][0] and P()[1] == b0[1],
          f"the first part stretched into the vlog without choosing it first: {b0[0]} -> {P()[0]}")
    check(packed() and parts().count() == 2, "the parts are laid out end to end again")
    # while dragging: an outline and a label; Esc cancels
    b1 = P()
    bb = parts().nth(1).bounding_box(); x, y = bb["x"] + bb["width"] - 4, bb["y"] + bb["height"] / 2
    pg.mouse.move(x, y); pg.mouse.down()
    for n in range(1, 11):
        pg.mouse.move(x - 4 * n, y); pg.wait_for_timeout(15)
    tip = pg.inner_text("#edTwick .pc-trim-tip") if pg.locator("#edTwick .pc-trim-tip").is_visible() else ""
    check(tip.startswith("Ends ") and "this part" in tip and "Short" in tip and pg.locator("#edTwick .pc-trim-lane").is_visible(),
          "dragging shows the new end and lengths: " + tip)
    pg.keyboard.press("Escape"); pg.mouse.up(); pg.wait_for_timeout(500)
    check(P() == b1 and not pg.locator("#edTwick .pc-trim-tip").is_visible(), "Esc cancels the drag")
    # it snaps to the gaps between words; Alt / Option drags freely
    pps = px_per_sec()
    e1, a1 = P()[1][1], P()[1][0]
    gap = max((c for c in snaps("end") if a1 + 1 < c < e1 - 0.3), default=None)  # a gap between words inside part 2
    check(gap is not None, "a gap between words to snap to")
    drag_handle(1, "end", round((gap - e1) * pps + 4))  # let go 4 px past it
    check(abs(P()[1][1] - round(gap, 3)) < 0.002, f"the end snapped to just after a word ({P()[1][1]} = {gap:.3f})")
    v = P()[1][1]
    want = round(v - 23 / pps, 3)
    drag_handle(1, "end", -23, alt=True)
    check(abs(P()[1][1] - want) < 0.08, f"with Alt it goes where it's dragged ({P()[1][1]} vs {want})")
    # the first part's start stretches back into the vlog
    s_before = P()[0][0]
    drag_handle(0, "start", -30)
    check(P()[0][0] < s_before - 0.3, f"the first part reaches back into the vlog: {s_before} -> {P()[0][0]}")
    # Start / End act on the chosen part, with fine steps
    tool("trim"); select(1)
    e_before = P()[1][1]
    check("Part 2 end" in pg.inner_text("#edTrim"), "the panel says which part it moves")
    pg.click('[data-end="1"][data-d="0.1"]'); pg.wait_for_timeout(300)
    check(abs(P()[1][1] - (e_before + 0.1)) < 0.002, f"+0.1 moves that part's end ({e_before} -> {P()[1][1]})")
    pg.click('[data-end="0"][data-d="-0.1"]'); pg.wait_for_timeout(300)
    check(P()[0][0] >= P()[0][0] and P()[1][0] < b1[1][0] + 0.01 and P()[1][0] >= P()[0][1], "−0.1 on its start stops at the part before")
    n_undo = 0
    while P() != p2 and n_undo < 20:
        pg.click("#edUndo"); n_undo += 1; pg.wait_for_timeout(200)
    check(P() == p2, f"Undo takes all of it back ({n_undo} steps)")

    # ---------------------------------------------------------------- 7c. the whole Short in view while dragging, and past the box's edge
    print("7c. The whole Short in view while dragging; past the box's edge")
    tool("trim")
    # while an end is dragged, the whole Short as it will be fits the box (every part), the dragged one lit
    last = parts().count() - 1
    bb = parts().nth(last).bounding_box(); sc = pg.locator("#edTwick .twick-timeline-scroll-container").bounding_box()
    x, y = bb["x"] + bb["width"] - 4, bb["y"] + bb["height"] / 2
    pg.mouse.move(x, y); pg.mouse.down()
    for n in range(1, 8):
        pg.mouse.move(x - 10 * n, y); pg.wait_for_timeout(15)
    lane = pg.locator("#edTwick .pc-trim-lane").bounding_box()
    blocks = ev("[...document.querySelectorAll('#edTwick .pc-trim-parts i')].map(i=>{const r=i.getBoundingClientRect();return [r.left,r.right,i.className]})")
    check(len(blocks) == parts().count() and "on" in blocks[-1][2], f"dragging: a lane with every part, the dragged one lit ({len(blocks)})")
    check(lane["x"] >= sc["x"] - 1 and lane["x"] + lane["width"] <= sc["x"] + sc["width"] + 1 and blocks[0][0] >= lane["x"] - 1 and blocks[-1][1] <= lane["x"] + lane["width"] + 1,
          "the whole Short fits the box while shrinking")
    pg.mouse.move(sc["x"] + sc["width"] + 40, y, steps=8); pg.wait_for_timeout(1500)
    blocks = ev("[...document.querySelectorAll('#edTwick .pc-trim-parts i')].map(i=>{const r=i.getBoundingClientRect();return [r.left,r.right]})")
    lane = pg.locator("#edTwick .pc-trim-lane").bounding_box()
    check(blocks[0][0] >= lane["x"] - 1 and blocks[-1][1] <= lane["x"] + lane["width"] + 1 and lane["x"] + lane["width"] <= sc["x"] + sc["width"] + 1,
          "and while growing past the box: still all in view")
    pg.keyboard.press("Escape"); pg.mouse.up(); pg.wait_for_timeout(400)
    check(P() == p2 and not pg.locator("#edTwick .pc-trim-lane").is_visible(), "Esc: nothing changed, the lane gone")
    # past the timeline's edge: held there, the last part keeps growing
    bb = parts().nth(last).bounding_box()
    x, y = bb["x"] + bb["width"] - 4, bb["y"] + bb["height"] / 2
    end0 = P()[-1][1]
    pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(sc["x"] + sc["width"] + 40, y, steps=8); pg.wait_for_timeout(1500)
    tip = pg.inner_text("#edTwick .pc-trim-tip")
    pg.mouse.up(); pg.wait_for_timeout(600)
    grew = P()[-1][1] - end0
    reach = (sc["x"] + sc["width"] + 40 - x) / px_per_sec()
    check(grew > reach + 1, f"held past the edge, the end keeps going ({grew:.1f} s; the pointer alone: {reach:.1f} s) · {tip}")
    n_undo = 0
    while P() != p2 and n_undo < 20:
        pg.click("#edUndo"); n_undo += 1; pg.wait_for_timeout(200)
    check(P() == p2, f"Undo takes all of it back ({n_undo} steps)")

    # ---------------------------------------------------------------- 8. AI Edit and the timeline are one list
    print("8. AI Edit <-> timeline")
    tool("ai")
    cut_words = pg.locator("#aeTr .ae-w.cut").count()
    check(cut_words > 0, f"words in the deleted middle show as cut ({cut_words})")
    kept = pg.locator("#aeTr .ae-w:not(.cut)")
    w = kept.nth(2); w.click(); pg.wait_for_timeout(500)
    check(len(P()) == 3, f"cutting a word in AI Edit splits the timeline: {len(P())} pieces")
    check(parts().count() == 3, "three parts on the timeline")
    pg.click("#edUndo"); pg.wait_for_timeout(400)
    check(P() == p2 and parts().count() == 2, "undo brings the word back")
    check("after your edits" in pg.inner_text("#aeSum"), "AI Edit's summary counts timeline edits")
    pg.click('[data-a="long"]') if not pg.locator('[data-a="long"]').is_disabled() else None
    pg.wait_for_timeout(400)
    tool("trim")

    # ---------------------------------------------------------------- 9. zoom, scrolling, ruler
    print("9. Zoom, scrolling along the timeline and the ruler")
    sc_left = lambda: ev("document.querySelector('#edTwick .twick-timeline-scroll-container').scrollLeft")
    w1 = parts().first.bounding_box()["width"]
    check(pg.locator("#edZoomOut").is_disabled() and pg.inner_text("#edZoomFit") == "Fit", "at Fit: zoom out is off")
    pg.click("#edZoomIn"); pg.wait_for_timeout(300); pg.click("#edZoomIn"); pg.wait_for_timeout(600)
    w4 = parts().first.bounding_box()["width"]
    check(near(w4 / w1, 1.6 * 1.6, 0.15), f"zoom in twice: {w1:.0f}px -> {w4:.0f}px")
    check(pg.inner_text("#edZoomFit") == "2.6×" and not pg.locator("#edZoomOut").is_disabled(), "the button says how far in: " + pg.inner_text("#edZoomFit"))
    box = pg.locator("#edTwick .twick-timeline-scroll-container").bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + 70)
    x0 = sc_left()
    room = ev("(s=>s.scrollWidth-s.clientWidth)(document.querySelector('#edTwick .twick-timeline-scroll-container'))")
    pg.mouse.wheel(0, 240 if room - x0 > 150 else -240); pg.wait_for_timeout(400)  # towards whichever end has room
    check(abs(sc_left() - x0) > 100, f"the wheel scrolls along the timeline ({x0:.0f} -> {sc_left():.0f} of {room:.0f})")
    sep = pg.locator("#edTwick .twick-timeline-separator").first.bounding_box()
    x1 = sc_left(); y = sep["y"] + sep["height"] / 2
    pg.mouse.move(box["x"] + 500, y); pg.mouse.down()
    for n in range(1, 16):
        pg.mouse.move(box["x"] + 500 + 12 * n, y); pg.wait_for_timeout(12)
    pg.mouse.up(); pg.wait_for_timeout(300)
    check(near(sc_left(), max(0, x1 - 180), 25), f"dragging an empty spot scrolls ({x1:.0f} -> {sc_left():.0f})")
    check(P() == ev("edAE.pieces()") and state().endswith("not saved"), "scrolling changes nothing")
    pg.keyboard.down("Control"); pg.mouse.move(box["x"] + 300, box["y"] + 70); pg.mouse.wheel(0, -120); pg.keyboard.up("Control"); pg.wait_for_timeout(500)
    check(parts().first.bounding_box()["width"] > w4 * 1.5, "Ctrl + scroll zooms in further")
    pg.click("#edZoomFit"); pg.wait_for_timeout(600)
    check(near(parts().first.bounding_box()["width"], w1, 3) and sc_left() == 0 and pg.inner_text("#edZoomFit") == "Fit", "Fit shows the whole Short again")
    ruler = pg.locator("#edTwick .twick-seek-track").first.bounding_box()
    t_click = 3.0
    pps = px_per_sec()
    pg.mouse.click(ruler["x"] + t_click * pps, ruler["y"] + ruler["height"] / 2); pg.wait_for_timeout(800)
    v = ev("document.getElementById('edVideo').currentTime")
    exp_v = (P()[0][0] + t_click) - SV()[0][0]
    if exp_v >= 0:
        check(near(v, exp_v, 0.4), f"a ruler click moves the player ({v:.2f} vs {exp_v:.2f})")
    else:
        check(pg.locator("#edTlNote").is_visible(), "a part the video doesn't have yet: 'Save to play the new parts'")

    # ---------------------------------------------------------------- 10. save and what the server keeps
    print("10. Save")
    want = P()
    # watch for blinking while it's saved and remade: a "Getting..." in a tool, or the timeline built again
    ev("""(()=>{ window.BLINK=[]; window.TL_ROOT=document.querySelector('#edTwick .pc-tl-root');
      ['edAI','edDBox','edCap'].forEach(id=>new MutationObserver(()=>{ const t=document.getElementById(id).textContent;
        if(/^Getting the/.test(t.trim())) BLINK.push(id); }).observe(document.getElementById(id),{childList:true,subtree:true})); })()""")
    pg.click("#edSave")
    wait_saved()
    pg.wait_for_timeout(1500)
    check(ev("BLINK") == [], f"saving and remaking don't blank the tools (no 'Getting...': {ev('BLINK')})")
    check(ev("TL_ROOT===document.querySelector('#edTwick .pc-tl-root')"), "the timeline isn't built again (it takes the new parts)")
    srv = server(A, 2)
    check(near(srv["start"], want[0][0], 0.01) and near(srv["end"], want[-1][1], 0.01), f"server moment {srv['start']}..{srv['end']} = {want[0][0]}..{want[-1][1]}")
    check(all(near(a, c, 0.01) and near(b, d, 0.01) for (a, b), (c, d) in zip(srv["pieces"], want)) and len(srv["pieces"]) == len(want),
          f"server pieces {srv['pieces']}")
    check(P() == SV() and parts().count() == len(want), "the timeline shows the saved Short")
    check("past the original moment" not in summ(), "the new reach is the moment now")
    dur = ev("document.getElementById('edVideo').duration")
    check(near(dur, sum(b - a for a, b in want), 0.3), f"the new video is {dur:.2f}s long")
    check(srv["words"][0]["s"] < s0, "the transcript covers the wider moment")

    # ---------------------------------------------------------------- 11. too short, discard
    print("11. Too short; Discard")
    drag_handle(0, "end", -int(parts().first.bounding_box()["width"] - 10))
    if len(P()) > 1:
        select(1); pg.click("#edDel"); pg.wait_for_timeout(500)
    short_len = ev("aeLen(edAE.pieces())")
    check(short_len < 5, f"trimmed under 5 s ({short_len:.2f})")
    check("At least" in summ(), "summary warns")
    pg.click("#edSave"); pg.wait_for_timeout(1200)
    check("less than" in pg.inner_text("#edDErr") or "less than" in pg.inner_text("body"), "Save refuses it")
    check(state().endswith("not saved"), "still unsaved: " + state())
    pg.click("#edCancel"); pg.wait_for_timeout(600)
    check(P() == SV() and state() == "Saved" and parts().count() == len(SV()), "Discard puts the saved Short back on the timeline")

    # ---------------------------------------------------------------- 12. clamps at the vlog's ends
    print("12. The vlog's ends")
    open_short(A, 1)
    tool("trim")
    pg.click('[data-end="0"][data-d="-5"]'); pg.wait_for_timeout(300)
    check(P()[0][0] == 0, f"start stops at 0:00 ({P()[0][0]})")
    check(pg.locator('[data-end="0"][data-d="-1"]').is_disabled(), "earlier is off at 0:00")
    pg.click("#edCancel"); pg.wait_for_timeout(400)
    check(state() == "Saved", "discarded")

    # ---------------------------------------------------------------- 12b. Save bar, one Undo for every tool
    print("12b. The Save bar and Undo / Redo across the tools")
    tool("ai")
    check(pg.locator('[data-a="cuts"]').count() == 0 and "Suggest cuts" not in pg.inner_text("#edAI"), "no AI suggested cuts")
    tool("details")
    check(not pg.locator("#edSaveRow").is_visible() and pg.locator("#edUndo").is_disabled(), "nothing changed: no Save bar, Undo off")
    title0 = pg.input_value("#edDBox input.title")
    pg.fill("#edDBox input.title", title0 + " again"); pg.wait_for_timeout(300)
    bar, panel = pg.locator("#edSaveRow").bounding_box(), pg.locator(".ed-panel").bounding_box()
    check(pg.locator("#edSaveRow").is_visible() and abs((bar["y"] + bar["height"]) - (panel["y"] + panel["height"])) < 3
          and bar["x"] >= panel["x"] - 1, "the Save bar sits at the bottom of the tool panel")
    check(pg.inner_text("#edSaveN") == "1 change not saved", "it says what's waiting: " + pg.inner_text("#edSaveN"))
    looks = pg.locator("#edDBox .looks button[aria-pressed=false]")
    if looks.count():
        looks.first.click(); pg.wait_for_timeout(300)
    tool("ai")
    w = pg.locator("#aeTr .ae-w:not(.cut)").nth(3); w.click(); pg.wait_for_timeout(400)
    cut_p = P()
    check(len(cut_p) == 2 and pg.inner_text("#edSaveN") == "3 changes not saved", f"three tools, three changes ({pg.inner_text('#edSaveN')})")
    pg.click("#edUndo"); pg.wait_for_timeout(400)
    check(P() == SV(), "Undo takes back the cut word")
    pg.click("#edUndo"); pg.wait_for_timeout(400)
    tool("details")
    check(pg.locator("#edDBox .looks button[aria-pressed=true]").count() == 0 or not looks.count() or
          ev("[...document.querySelectorAll('#edDBox .looks button')].findIndex(b=>b.getAttribute('aria-pressed')==='true')") == 0,
          "then the look")
    check(pg.input_value("#edDBox input.title") == title0 + " again", "the title is still changed")
    pg.locator("body").click(position={"x": 5, "y": 5}); pg.keyboard.press("Control+z"); pg.wait_for_timeout(400)
    check(pg.input_value("#edDBox input.title") == title0 and state() == "Saved" and not pg.locator("#edSaveRow").is_visible(),
          "Ctrl+Z takes back the title (one step for the typing): nothing left to save")
    pg.click("#edRedo"); pg.wait_for_timeout(300); pg.click("#edRedo"); pg.wait_for_timeout(300); pg.click("#edRedo"); pg.wait_for_timeout(400)
    check(pg.input_value("#edDBox input.title") == title0 + " again" and P() == cut_p and pg.locator("#edRedo").is_disabled(),
          "Redo puts all three back")
    check(ev("document.querySelector('#edMeta .ed-name').textContent") == title0 + " again", "the name in Details follows")
    pg.click("#edCancel"); pg.wait_for_timeout(800)
    check(state() == "Saved" and pg.locator("#edUndo").is_disabled() and pg.input_value("#edDBox input.title") == title0, "Discard: back to saved, nothing to undo")

    # ---------------------------------------------------------------- 12c. Captions
    print("12c. Captions")
    open_short(A, 1)
    tool("captions")
    pg.wait_for_function("document.querySelectorAll('#cpLines .cp-w').length>3", timeout=20000)
    pg.wait_for_function("(document.getElementById('cpImg')||{}).src && cpImg.src.startsWith('blob:')", timeout=20000)
    cap = lambda: ev("edCap.snap()")
    check(pg.locator(".cp-pre").count() == 7, "seven presets")
    check(pg.get_attribute('.cp-pre[data-p="bold"]', "aria-pressed") == "true", "Bold is on (the vlog's style)")
    check(ev("edCap.summary()") == "Bold" and pg.locator("#edCapTrack .ed-cap-c").count() > 3, "the captions' look: " + ev("edCap.summary()") + ", their lines on the timeline")
    nat = ev("cpImg.naturalWidth+'x'+cpImg.naturalHeight")
    check(nat == "540x960", "the preview is a 9:16 frame: " + nat)
    pg.click('.cp-pre[data-p="pop"]'); pg.wait_for_timeout(300)
    check(cap()["font"] == "bangers" and cap()["highlight"] == "grow" and state() == "1 change not saved", "Pop: Bangers, the word grows; 1 change")
    pg.wait_for_function("!cpVid.hidden && cpVid.src.startsWith('blob:') && !cpVid.paused", timeout=20000)
    check(True, "a preset that moves differently plays it")
    pg.click('.cp-seg [data-k="words"][data-v="1"]'); pg.wait_for_timeout(300)
    n_words = pg.locator("#cpLines .cp-w").count()
    check(pg.locator("#cpLines .cp-line").count() == n_words, f"one word a line: {n_words} lines")
    first = pg.locator("#cpLines .cp-w").nth(1); said = first.inner_text()
    first.click(); pg.wait_for_timeout(200)
    pg.fill(".cp-we input", "Kohima"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    check(pg.locator("#cpLines .cp-w").nth(1).inner_text() == "KOHIMA", "a word changed (in capitals, as Pop shows it)")
    check(pg.locator("#cpLines .cp-w.ed").count() == 1, "it's marked as changed")
    i_changed = ev("Object.keys(edCap.snap().edits)[0]")
    pg.click('.cp-we [data-a="pop"]'); pg.wait_for_timeout(200)
    pg.click('.cp-we [data-a="done"]'); pg.wait_for_timeout(200)
    pg.locator("#cpLines .cp-w").nth(3).click(); pg.wait_for_timeout(200)
    pg.click('.cp-we [data-a="hide"]'); pg.wait_for_timeout(200)
    check(pg.locator("#cpLines .cp-w.hid").count() == 1 and pg.locator("#cpLines .cp-w.pop").count() == 1, "one word left out, one made to pop")
    check("1 change not saved" == state(), "still one change (the captions): " + state())
    check("2 words changed" in ev("edCap.summary()"), "summary: " + ev("edCap.summary()"))
    pg.click("#edUndo"); pg.wait_for_timeout(300)
    check(pg.locator("#cpLines .cp-w.hid").count() == 0, "Undo brings the word back")
    pg.click("#edRedo"); pg.wait_for_timeout(300)
    check(pg.locator("#cpLines .cp-w.hid").count() == 1, "Redo leaves it out again")
    # a cut in AI Edit: the captions follow it
    tool("ai")
    pg.locator("#aeTr .ae-w:not(.cut)").nth(8).click(); pg.wait_for_timeout(400)
    tool("captions")
    check(pg.locator("#cpLines .cp-w").count() == n_words - 1, "a word cut in AI Edit leaves the captions too")
    check(state() == "2 changes not saved", "two tools, two changes: " + state())
    want_caps, want_p = cap(), P()
    pg.click("#edSave")
    wait_saved()
    pg.wait_for_function("edCap.snap() && !edCap.dirty()", timeout=30000)
    srv = ev(f"fetch('/api/captions/{A}/1').then(r=>r.json())")["captions"]
    check(srv["preset"] == "pop" and srv["words"] == 1 and srv["edits"] == want_caps["edits"] and srv["pop"] == [int(i_changed)],
          f"the server kept the captions: {srv['edits']} pop {srv['pop']}")
    check(len(server(A, 1)["pieces"]) == 2, "and the cut")
    st = ev(f"fetch('/api/status/{A}').then(r=>r.json())")
    vid = next(x["video"] for x in st["shorts"] if x["idx"] == 1)
    ass = open(os.path.join(H["jobs_dir"], A, vid.replace("short_", "captions_").replace(".mp4", ".ass")), encoding="utf-8").read()
    check("Style: Cap,Bangers," in ass and "KOHIMA" in ass, f"the new video's captions: Bangers, \"{said}\" became KOHIMA")
    check(state() == "Saved" and pg.locator("#edUndo").is_disabled(), "saved, nothing to undo")
    # captions alone: their own remake
    vid0 = vid
    pg.click('.cp-seg [data-k="highlight"][data-v="none"]'); pg.wait_for_timeout(200)
    pg.click('[data-pos="1200"]'); pg.wait_for_timeout(200)
    check(state() == "1 change not saved", "highlight off, moved up: " + state())
    pg.click("#edSave")
    wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={A!r}&&c.idx===1)||{{}}).video!=={vid0!r} && !edCap.dirty()", timeout=90000)
    st = ev(f"fetch('/api/status/{A}').then(r=>r.json())")
    vid = next(x["video"] for x in st["shorts"] if x["idx"] == 1)
    ass = open(os.path.join(H["jobs_dir"], A, vid.replace("short_", "captions_").replace(".mp4", ".ass")), encoding="utf-8").read()
    check(vid != vid0 and ",1200,1" in ass.split("Style: Cap,")[1].split("\n")[0], "captions alone remake the Short, higher up")
    # off, then Discard; a change, then Discard
    pg.click("#cpOn"); pg.wait_for_timeout(300)
    check(not pg.locator("#cpPrev").is_visible() and cap()["on"] is False, "Show captions off: no preview")
    ev("(i=>{i.value=60;i.dispatchEvent(new Event('change'))})(document.querySelector('.cp-range input[data-k=size]'))")  # a slider moved
    pg.wait_for_timeout(200)
    pg.click("#edCancel"); pg.wait_for_timeout(800)
    check(cap()["on"] is True and cap()["size"] == srv["size"] and state() == "Saved", "Discard puts the saved captions back")
    # the timeline's Captions row: a strip of the lines, each with room for its words, moving along with the player
    pg.click('.cp-seg [data-k="words"][data-v="3"]'); pg.wait_for_timeout(600)
    ev("document.getElementById('edVideo').currentTime=0"); pg.wait_for_timeout(600)
    blocks = pg.locator("#edCapTrack .ed-cap-c")
    n_lines = ev("edCap.track().length")
    check(blocks.count() == n_lines and n_lines > 5, f"a chip per caption line ({blocks.count()} / {n_lines})")
    full = ev("[...document.querySelectorAll('#edCapTrack .ed-cap-c span')].filter(s=>s.scrollWidth>s.clientWidth+1).length")
    check(full == 0, f"every chip shows its words in full ({full} cut)")
    check(ev("[...document.querySelectorAll('#edCapTrack .ed-cap-c')].every((b,k,a)=>!k||a[k-1].getBoundingClientRect().right<=b.getBoundingClientRect().left)"),
          "chips side by side, none on top of another")

    def follows():
        """the line being said is lit and in view"""
        now = pg.locator("#edCapTrack .ed-cap-c.now")
        if not now.count():
            return True  # between two lines
        tb, nb = pg.locator("#edCapTrack").bounding_box(), now.bounding_box()
        return nb["x"] >= tb["x"] - 1 and nb["x"] + nb["width"] <= tb["x"] + tb["width"] + 1
    check(follows(), "the line being said is lit and in view")
    blocks.nth(1).click(); pg.wait_for_timeout(400)
    check(pg.locator("#cpLine").is_visible() and "This line" in pg.inner_text("#cpLine"), "a click picks the line in Captions")
    blocks.nth(2).click(modifiers=["Shift"]); pg.wait_for_timeout(400)
    check("2 lines" in pg.inner_text("#cpLine") and pg.locator("#edCapTrack .ed-cap-c.on").count() == 2, "Shift-click picks one more")
    pg.select_option('#cpLine select[data-lk="font"]', "anton"); pg.wait_for_timeout(300)
    ev("(i=>{i.value=140;i.dispatchEvent(new Event('change'))})(document.querySelector('#cpLine input[data-lk=size]'))")
    pg.click('#cpLine [data-lpos="1200"]'); pg.wait_for_timeout(400)
    st_ = cap()["styles"]
    check(len({json.dumps(v, sort_keys=True) for v in st_.values()}) == 1 and list(st_.values())[0] == {"font": "anton", "size": 140}
          and state() == "1 change not saved", f"those two lines get their own look: {list(st_.values())[:1]}")
    check(pg.locator("#edCapTrack .ed-cap-c.own").count() == 2, "the timeline marks them")
    check("2 lines styled" in ev("edCap.summary()"), "summary: " + ev("edCap.summary()"))
    pg.click("#cpLDone"); pg.wait_for_timeout(300)
    check(not pg.locator("#cpLine").is_visible() and pg.locator("#edCapTrack .ed-cap-c.on").count() == 0, "Done: nothing picked")
    x0 = ev("edCapX")
    ev("(v=>{v.muted=true; return v.play()})(document.getElementById('edVideo'))"); pg.wait_for_timeout(2500)
    x1 = ev("edCapX"); ev("document.getElementById('edVideo').pause()"); pg.wait_for_timeout(300)
    check(x1 > x0 + 20 and follows(), f"playing moves the strip along ({x0:.0f} -> {x1:.0f} px), the line said lit")
    box = pg.locator("#edCapTrack").bounding_box()
    pg.wait_for_function("edVideo.paused && !edVideo.seeking", timeout=10000)  # (WebKit can stop a moment late)
    pg.wait_for_timeout(300)
    room = ev("(s=>s.scrollWidth-document.getElementById('edCapTrack').clientWidth)(document.querySelector('.ed-cap-strip'))")
    way = 300 if room - x1 > 150 else -300  # towards whichever end has room
    # (sent to the strip itself: a mouse move and a wheel in the same instant can reach what the pointer was over before)
    ev(f"document.querySelector('#edCapTrack .ed-cap-c').dispatchEvent(new WheelEvent('wheel',{{deltaY:{way},bubbles:true,cancelable:true}}))")
    pg.wait_for_timeout(300)
    pg.wait_for_timeout(1200)  # the timeline lining up the player after the pause mustn't undo it
    check(abs(ev("edCapX") - x1) > 100 and ev("edCapHand"), f"the wheel scrolls it by hand ({x1:.0f} -> {ev('edCapX'):.0f} px of {room:.0f}, by hand: {ev('edCapHand')})")
    ruler = pg.locator("#edTwick .twick-seek-track").first.bounding_box()
    pg.mouse.click(ruler["x"] + ruler["width"] * 0.3, ruler["y"] + ruler["height"] / 2); pg.wait_for_timeout(900)
    check(not ev("edCapHand") and follows(), "a seek on the timeline follows the player again")
    ev("document.getElementById('edVideo').currentTime=0"); pg.wait_for_timeout(600)
    vid0 = vid
    pg.click("#edSave")
    wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={A!r}&&c.idx===1)||{{}}).video!=={vid0!r} && !edCap.dirty()", timeout=90000)
    st = ev(f"fetch('/api/status/{A}').then(r=>r.json())")
    vid = next(x["video"] for x in st["shorts"] if x["idx"] == 1)
    ass = open(os.path.join(H["jobs_dir"], A, vid.replace("short_", "captions_").replace(".mp4", ".ass")), encoding="utf-8").read()
    own_rows = [ln for ln in ass.splitlines() if "\\fnAnton" in ln]
    check(own_rows and all("\\fs140" in ln for ln in own_rows) and len(own_rows) < len([ln for ln in ass.splitlines() if ln.startswith("Dialogue: 0,")]) / 2,
          f"saved: only those lines in Anton, bigger ({len(own_rows)} events)")
    check(pg.locator("#edCapTrack .ed-cap-c.own").count() == 2, "after saving the timeline still marks them")
    # "Lines come in" moves: it plays as a few seconds of video
    pg.click('.cp-seg [data-k="anim"][data-v="fade"]')
    pg.wait_for_function("(v=>v&&!v.hidden&&v.src.startsWith('blob:')&&v.readyState>=2&&!v.paused)(document.getElementById('cpVid'))", timeout=20000)
    check(near(ev("cpVid.duration"), 2.5, 0.3) and not pg.locator("#cpImg").is_visible(), f"changing how lines come in plays them moving ({ev('cpVid.duration'):.1f} s)")
    check(pg.locator('.cp-seg [data-k="anim"]').count() == 6, "six ways for lines to come in")
    for anim in ("punch", "slide", "words"):
        ev("cpVid.removeAttribute('src')")
        pg.click(f'.cp-seg [data-k="anim"][data-v="{anim}"]')
        pg.wait_for_function("(v=>v&&!v.hidden&&v.src.startsWith('blob:')&&v.readyState>=2&&!v.paused)(document.getElementById('cpVid'))", timeout=20000)
        check(cap()["anim"] == anim, f"{anim}: chosen, and it plays moving")
    pg.click('.cp-seg [data-k="words"][data-v="2"]'); pg.wait_for_timeout(200)
    pg.wait_for_function("cpImg.src.startsWith('blob:') && !cpImg.hidden && cpVid.hidden", timeout=20000)
    check(True, "other changes show a still frame again")
    pg.click("#cpPlay")
    pg.wait_for_function("!cpVid.hidden && cpVid.src.startsWith('blob:') && !cpVid.paused", timeout=20000)
    check(not ev("cpVid.loop") and "Pause" in pg.inner_text("#cpPlay"), "Play it plays the captions moving, with Pause")
    pg.click("#cpPlay"); pg.wait_for_timeout(300)
    check(ev("cpVid.paused") and "Play" in pg.inner_text("#cpPlay"), "Pause stops it")
    pg.click("#cpSlow"); pg.wait_for_timeout(300)
    check(ev("cpVid.playbackRate") == 0.5 and not ev("cpVid.paused") and pg.get_attribute("#cpSlow", "aria-pressed") == "true", "Slow plays it at half speed")
    pg.click("#cpSlow"); pg.wait_for_timeout(200)
    # (ended also shows for a moment after the first and second plays, before it starts again)
    pg.wait_for_function("cpVid.ended && document.getElementById('cpPlay').textContent.includes('Play again')", timeout=20000)
    check(ev("cpVid.paused"), "it plays three times, then stops (Play again)")
    pg.click("#edCancel"); pg.wait_for_timeout(800)
    check(state() == "Saved", "discarded")
    # the tools' edge: narrower, then above the player, then back
    grip = lambda: pg.locator("#edRailGrip").bounding_box()
    grid = pg.locator("#edGrid").bounding_box()
    stage_w = pg.locator(".ed-stage").bounding_box()["width"]

    def drag_grip(to_x):
        g = grip(); x, y = g["x"] + g["width"] / 2, g["y"] + g["height"] / 2
        pg.mouse.move(x, y); pg.mouse.down()
        for n in range(1, 16):
            pg.mouse.move(x + (to_x - x) * n / 15, y); pg.wait_for_timeout(15)
        pg.mouse.up(); pg.wait_for_timeout(700)
    drag_grip(grid["x"] + 170)
    rail_w = pg.locator("#edRail").bounding_box()["width"]
    check(near(rail_w, 168, 6) and pg.locator(".ed-stage").bounding_box()["width"] > stage_w + 40, f"drag: narrower tools ({rail_w:.0f} px), a wider player")
    drag_grip(grid["x"] + 40)
    rail, stage = pg.locator("#edRail").bounding_box(), pg.locator(".ed-stage").bounding_box()
    check(ev("edGrid.classList.contains('rail-top')") and rail["y"] + rail["height"] <= stage["y"] + 1 and stage["width"] > stage_w + 150,
          f"far left: the tools go above the player ({stage['width']:.0f} px wide)")
    check(ev("JSON.parse(localStorage.getItem('pc-ed-rail')).top") is True, "kept for next time")
    check(follows() and ev("document.getElementById('edCapTrack').getBoundingClientRect().width") > box["width"] + 100,
          "the caption strip takes the wider room")
    tool("details"); check(pg.locator("#edDetails").is_visible(), "the tools still work up there"); tool("captions")
    pg.click("#edRailDock"); pg.wait_for_timeout(700)
    check(not ev("edGrid.classList.contains('rail-top')") and pg.locator("#edRail").bounding_box()["x"] < pg.locator(".ed-stage").bounding_box()["x"],
          "Tools on the side brings them back")
    drag_grip(grid["x"] + 40); drag_grip(grid["x"] + 260)
    check(not ev("edGrid.classList.contains('rail-top')") and near(pg.locator("#edRail").bounding_box()["width"], 258, 6),
          "dragging back from the left edge too")
    ev("localStorage.removeItem('pc-ed-rail')"); ev("edRailW=220; edRailTop=false; edRailApply()"); pg.wait_for_timeout(400)
    tool("trim")

    # ---------------------------------------------------------------- 13. no video: read only
    print("13. The vlog's video is gone")
    for f in glob.glob(os.path.join(H["jobs_dir"], BJ, "source.*")):
        os.remove(f)
    open_short(BJ, 2)
    tool("trim")
    check("video was deleted" in pg.inner_text("#edTrim"), "Trim says why")
    tool("captions")
    pg.wait_for_function("document.querySelector('#edCap .cp-on')", timeout=20000)
    check("video was deleted" in pg.inner_text("#edCap") and pg.locator("#cpOn").is_disabled()
          and pg.locator(".cp-pre").first.is_disabled(), "Captions says why, and can't be changed")
    tool("trim")
    check(pg.locator('#edTrim [data-d]').first.is_disabled() and pg.locator("#edSplit").is_disabled(), "its buttons are off")
    b4 = P()
    try:
        drag_handle(0, "end", -80)
    except Exception:  # noqa: BLE001  (the handle may not show on a part that can't change)
        pass
    check(P() == b4 and state() == "Saved", "dragging an end doesn't change it")
    check(parts().count() == 1 and abs(parts().first.bounding_box()["width"] - pg.locator('#edTwick .twick-track').first.bounding_box()["width"]) < 60,
          "the part is put back")

    # ---------------------------------------------------------------- 14. leaving and coming back
    print("14. Leaving and coming back")
    open_short(A, 2)
    ev("(v=>{v.muted=true; return v.play()})(document.getElementById('edVideo'))"); pg.wait_for_timeout(800)
    check(not ev("document.getElementById('edVideo').paused"), "the Short plays")
    pg.click("#edBack"); pg.wait_for_timeout(1200)
    check(ev("document.getElementById('edVideo').paused"), "Back to Drafts stops it (it doesn't play on in the background)")
    open_short(A, 2)
    check(parts().count() == len(SV()), "the timeline is drawn again")
    pg.set_viewport_size({"width": 1180, "height": 820}); pg.wait_for_timeout(600)
    tool("trim")
    tw = pg.locator("#edTwick").bounding_box(); last = parts().nth(parts().count() - 1).bounding_box()
    check(last["x"] + last["width"] <= tw["x"] + tw["width"] + 1, "laptop size: the Short still fits")
    pg.emulate_media(color_scheme="light"); pg.wait_for_timeout(300)
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(500)

    print()
    other = sorted(u for u in outside if "fonts.googleapis.com" not in u and "fonts.gstatic.com" not in u)
    check(not other, f"no requests outside Pit Crew (besides its own Google Fonts): {other}")
    check(not errs, f"no errors in the page: {errs}")
    br.close()

print(f"\n{passes} passed, {len(fails)} failed")
for f in fails:
    print("FAILED:", f)
sys.exit(1 if fails else 0)
