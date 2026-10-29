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
    def parts():
        """Twick's parts. Under Trim the strip takes the Video row (7d): the sections on Twick's own trimming show it."""
        if ev("edTrimOn"):
            ev("edTrimShow(false)"); pg.wait_for_timeout(300)
        return pg.locator("#edTwick .twick-track-element")
    state = lambda: pg.inner_text("#edState")
    summ = lambda: pg.inner_text(".tr-sum").replace("\n", " ")
    server = lambda j, i: ev(f"fetch('/api/ai-edit/{j}/{i}').then(r=>r.json())")

    def open_short(j, i):
        pg.goto(B + f"/#edit/{j}/{i}")
        pg.wait_for_function("edAE.info() && window.PitTimeline && document.querySelectorAll('#edTwick .twick-track-element').length>0", timeout=20000)
        pg.wait_for_timeout(500)

    def tool(t, strip=False):
        """strip: Trim as a creator sees it (its strip in the Video row, 7d); else Twick's timeline shows under Trim's
        panel too, for the sections on Twick's own trimming (still there under every other tool)."""
        pg.click(f'#edRail button[data-t="{t}"]')
        pg.wait_for_timeout(300)
        if t == "trim" and not strip:
            ev("edTrimShow(false)"); pg.wait_for_timeout(300)
        if strip and not ev("edTrimOn"):
            ev("edTrimShow(true)"); pg.wait_for_timeout(300)

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
    check("0:31" in summ() and "0:00.0 to 0:30.8" in summ(), "Trim summary, on the Short's clock: " + summ())
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
    print("3. Reaching past the moment")
    ev(f"edAE.setPieces([[{s1 - 10}, {e1}]])"); pg.wait_for_timeout(300)
    check(near(P()[0][0], s1 - 10, 0.01), f"start 10 s earlier: {P()[0][0]}")
    ev(f"edAE.setPieces([[{s1 - 10}, {e1 + 5}]])"); pg.wait_for_timeout(300)
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
    ev("edTl.split()"); pg.wait_for_timeout(600)
    check(parts().count() == 2, "split: two parts on the timeline")
    check(P() == before, "split alone doesn't change the Short")
    pg.keyboard.press("Delete"); pg.wait_for_timeout(700)
    cut_at = round(before[0][0] + at, 1)
    check(len(P()) == 1 and near(P()[0][1], cut_at, 0.15) and P()[0][0] == before[0][0], f"Delete key took the second half: {P()}")
    check(parts().count() == 1, "one part again")
    # split in the middle, delete the middle → two pieces with a gap
    whole = P()
    mid = (whole[0][1] - whole[0][0])
    ev(f"edTl.setTime({mid*0.3})"); ev("edTl.split()"); pg.wait_for_timeout(500)
    ev(f"edTl.setTime({mid*0.6})"); ev("edTl.split()"); pg.wait_for_timeout(500)
    check(parts().count() == 3, "two splits: three parts")
    select(1)
    ev("edTl.remove()"); pg.wait_for_timeout(600)
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

    # ---------------------------------------------------------------- 7d. trimming on the video row
    print("7d. Trimming on the video row: a yellow box made with two clicks, shaped, then cut out")
    tool("trim", strip=True)
    film = lambda: pg.locator("#edTrimStrip .ts-film").bounding_box()
    win0, f0, o0 = ev("edTS.win()"), film(), ev("edOrigin()")
    X = lambda t: f0["x"] + (t - win0["a"]) / (win0["b"] - win0["a"]) * f0["width"]
    Y = f0["y"] + f0["height"] / 2
    px = 2 * (win0["b"] - win0["a"]) / f0["width"]  # 2 px in seconds (WebKit's pointer lands on whole pixels)

    def click(t, alt=True):
        if alt:
            pg.keyboard.down("Alt")
        pg.mouse.click(X(t), Y)
        if alt:
            pg.keyboard.up("Alt")
        pg.wait_for_timeout(250)
    check(pg.locator("#edTrimStrip .ts.trim").is_visible() and not pg.locator("#edTwick").is_visible(), "the video row, ready to trim")
    zero = ev("[...document.querySelectorAll('#edTrimStrip .ts-ticks span')].find(s=>s.textContent==='0:00')?.getBoundingClientRect().left")
    check(zero is not None and abs(zero + 12 - X(o0)) < 16, "its times are the Short's: 0:00 where the saved Short starts")
    ln = ev("aeLen(edAE.saved())")
    check(win0["b"] - win0["a"] >= ln + 50 or win0["a"] == 0, f"zoomed out: the Short and at least 30 s either side ({win0})")
    check(pg.locator("#edTrimStrip .ts-dim").count() >= 3, "before, between and after the parts: dimmed")
    pg.wait_for_function("""(()=>{const c=document.querySelector('#edTrimStrip .ts-pics'); if(!c||!c.width) return false;
        const d=c.getContext('2d').getImageData(c.width/2|0,c.height/2|0,1,1).data; return d[0]+d[1]+d[2]>60;})()""", timeout=20000)
    check(True, "the vlog's pictures are drawn")
    pg.mouse.move(X(o0 + 3), Y); pg.wait_for_timeout(700)
    lab = pg.inner_text("#edTrimView").split()[0]
    check(pg.locator("#edTrimView").is_visible() and near(int(lab.split(":")[0]) * 60 + float(lab.split(":")[1]), 3, px + 0.05),
          f"pointing at the row shows that moment big ({lab})")
    a2 = p2[1][0]
    click(a2 + 1)
    check(near(ev("edTS.first()"), a2 + 1, px) and "Now click where the part to cut out ends" in pg.inner_text("#edTrim"), "first click: the start")
    click(a2 + 3)
    sel = ev("edTS.sel()")
    check(sel and near(sel["a"], a2 + 1, px) and near(sel["b"], a2 + 3, px) and ev("edTS.win()") == win0,
          f"second click: the end; yellow, the scale unchanged ({sel})")
    check(not pg.locator("#trCut").is_disabled() and pg.locator("#trKeep").count() == 0 and P() == p2,
          "Cut it out (no Keep it); nothing changed yet")
    # made once: more clicks don't start another; its ends stretch and narrow it, dragging inside moves it
    sel0 = ev("edTS.sel()")
    click(a2 + 8); click(a2 + 10)
    check(ev("edTS.sel()") == sel0 and ev("edTS.first()") is None, "clicks elsewhere don't make another box")
    sb = sel0["b"]
    pg.mouse.move(X(sb), Y); pg.mouse.down(); pg.mouse.move(X(sb) + 25, Y, steps=6); pg.mouse.up(); pg.wait_for_timeout(300)
    check(ev("edTS.sel()")["b"] > sb + 0.5 and near(ev("edTS.sel()")["a"], sel0["a"], 0.01), f"its end stretches it ({sb} -> {ev('edTS.sel()')['b']})")
    sa = ev("edTS.sel()")["a"]
    pg.mouse.move(X(sa), Y); pg.mouse.down(); pg.mouse.move(X(sa) + 12, Y, steps=6); pg.mouse.up(); pg.wait_for_timeout(300)
    check(ev("edTS.sel()")["a"] > sa + 0.3, f"its start narrows it ({sa} -> {ev('edTS.sel()')['a']})")
    s1 = ev("edTS.sel()"); mid = (s1["a"] + s1["b"]) / 2
    pg.keyboard.down("Alt"); pg.mouse.move(X(mid), Y); pg.mouse.down(); pg.mouse.move(X(mid) - 20, Y, steps=6); pg.mouse.up(); pg.keyboard.up("Alt")
    pg.wait_for_timeout(300)
    s2 = ev("edTS.sel()")
    check(s2["a"] < s1["a"] - 0.5 and near(s2["b"] - s2["a"], s1["b"] - s1["a"], 0.01), f"dragging inside moves it, the same length ({s1} -> {s2})")
    ev(f"edTS.setSel({{a:{a2 + 1}, b:{a2 + 3}}})")
    pg.keyboard.press("Delete"); pg.wait_for_timeout(600)
    p3 = P()
    check(len(p3) == 3 and near(p3[1][1], a2 + 1, 0.01) and near(p3[2][0], a2 + 3, 0.01) and ev("edTS.sel()") is None,
          f"Delete cuts it out: {p3}")
    check(ev("edTV.playing()") and pg.locator("#edTrimView").is_visible() and "Without" in pg.inner_text("#edTrimView"),
          "then the Short plays without it, big")
    pg.click("#trPlay"); pg.wait_for_timeout(200)
    if ev("edTV.playing()"):
        pg.click("#trPlay"); pg.wait_for_timeout(200)
    cut = ev("[...document.querySelectorAll('#edTrimStrip .ts-cut')].map(d=>{const r=d.getBoundingClientRect();return [r.left,r.right]})")
    check(any(abs(c[0] - X(a2 + 1)) < 4 and abs(c[1] - X(a2 + 3)) < 4 for c in cut) and ev("getComputedStyle(document.querySelector('#edTrimStrip .ts-cut')).backdropFilter||getComputedStyle(document.querySelector('#edTrimStrip .ts-cut')).webkitBackdropFilter").startswith("blur"),
          f"the cut part looks cut: blurred and striped, apart from the vlog around it ({len(cut)} cut)")
    # the Short's own end, dragged out into the vlog after it: that part is added
    e_was = P()[-1][1]
    pg.mouse.move(X(e_was), Y); pg.mouse.down()
    for i in range(1, 11):
        pg.mouse.move(X(e_was) + 6 * i, Y); pg.wait_for_timeout(15)
    tip_ = pg.inner_text("#edTrimStrip .ts-tip")
    pg.mouse.up(); pg.wait_for_timeout(400)
    check(P()[-1][1] > e_was + 2 and "Ends" in tip_, f"the Short's end drags out into the vlog ({e_was} -> {P()[-1][1]}; {tip_})")
    pg.click("#edUndo"); pg.wait_for_timeout(300)
    check(near(P()[-1][1], e_was, 0.01), "Undo takes it back")
    check(state() != "Saved", "a change waiting to be saved")
    click(a2 + 6); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check(ev("edTS.first()") is None, "Esc clears a start")
    # a part already left out (dimmed): nothing to cut
    e_last = P()[-1][1]
    click(e_last + 2); click(e_last + 6)
    check(pg.locator("#trCut").is_disabled() and "already left out" in pg.inner_text("#edTrim"), "a dimmed part: nothing to cut")
    pg.click("#trClear"); pg.wait_for_timeout(200)
    pg.click("#trPlay"); pg.wait_for_timeout(1200)
    check(ev("edTV.playing()"), "Play the Short as it'll be")
    pg.click("#trPlay"); pg.wait_for_timeout(200)
    pg.click("#trMore"); pg.wait_for_timeout(300)
    w2 = ev("edTS.win()")
    check(w2["a"] < win0["a"] or w2["b"] > win0["b"], f"Show more of the vlog ({win0} -> {w2})")
    n_undo = 0
    while P() != p2 and n_undo < 20:
        pg.click("#edUndo"); n_undo += 1; pg.wait_for_timeout(200)
    check(P() == p2, f"Undo takes all of it back ({n_undo} steps)")
    tool("details")
    check(pg.locator("#edTrimStrip .ts").is_visible() and pg.locator("#edTrimStrip .ts.trim").count() == 0 and not pg.locator("#edTrimView").is_visible(),
          "other tools: the whole clip, nothing yellow, no big preview")
    fb = film(); pg.mouse.click(fb["x"] + fb["width"] / 2, fb["y"] + 20); pg.wait_for_timeout(300)
    check(ev("edTS.first()") is None, "a click there just moves the player")
    pg.mouse.click(X(win0["b"] - 3), Y); pg.wait_for_timeout(700)
    check(pg.locator("#edTrimView").is_visible() and "not in the Short" in pg.inner_text("#edTrimView"),
          "a click on the vlog around the Short shows that moment big")
    ev("(v=>{v.muted=true; return v.play()})(document.getElementById('edVideo'))"); pg.wait_for_timeout(500)
    check(not pg.locator("#edTrimView").is_visible(), "playing the Short puts the player back")
    ev("document.getElementById('edVideo').pause()")
    tw = pg.locator("#edTwick"); lb = parts().nth(parts().count() - 1).bounding_box(); tw = tw.bounding_box()
    check(lb["x"] + lb["width"] <= tw["x"] + tw["width"] + 1 and packed(), "Twick's view under it is still laid out and fitted")

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
    dur = ev("document.getElementById('edVideo').duration")
    check(near(dur, sum(b - a for a, b in want), 0.3), f"the new video is {dur:.2f}s long")
    check(srv["words"][0]["s"] < s0, "the transcript covers the wider moment")

    # ---------------------------------------------------------------- 11. too short, discard
    print("11. Too short; Discard")
    drag_handle(0, "end", -int(parts().first.bounding_box()["width"] - 10))
    if len(P()) > 1:
        select(1); ev("edTl.remove()"); pg.wait_for_timeout(500)
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
    tool("trim", strip=True)
    check(ev("edTS.win()")["a"] == 0, f"near the vlog's start: the row starts at the vlog's 0:00 ({ev('edTS.win()')})")
    ev("edTS.setSel({a:-5, b:2})")
    check(ev("edTS.sel()")["a"] == 0, "a stretch can't start before the vlog")
    pg.click("#trClear"); pg.wait_for_timeout(300)
    check(ev("edTS.sel()") is None and state() == "Saved", "Clear: nothing chosen, nothing changed")

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
    kb = pg.locator("#edTrimStrip .ts-keep").first.bounding_box()  # a click in a kept part on the Video row
    pg.mouse.click(kb["x"] + kb["width"] * 0.4, kb["y"] + kb["height"] / 2); pg.wait_for_timeout(900)
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

    # ---------------------------------------------------------------- 12d. Reframe
    print("12d. Reframe")
    RJ, RI = ev("[edC.job, edC.idx]")
    rsrv = lambda: ev(f"fetch('/api/reframe/{RJ}/{RI}').then(r=>r.json())")
    rf = lambda: (ev("edRf.snap()") or {}).get("r")
    box = lambda: pg.locator("#edRfStage .rf-box").first.bounding_box()
    ev("(v=>{v.muted=true; return v.play()})(document.getElementById('edVideo'))"); pg.wait_for_timeout(500)
    tool("reframe")
    pg.wait_for_function("document.querySelector('#edRfStage .rf-box')", timeout=20000)
    check(pg.locator("#edRfStage").is_visible() and ev("document.getElementById('edVideo').paused"),
          "Reframe takes the player's place (the player pauses)")
    pg.wait_for_function("""(()=>{const c=document.querySelector('#edRfStage .rf-res'); if(!c||!c.width) return false;
        const d=c.getContext('2d').getImageData(c.width/2|0,c.height/2|0,1,1).data; return d[0]+d[1]+d[2]>60;})()""", timeout=20000)
    check(rf() is None and state() == "Saved", "the Short as it'll look, drawn live; nothing changed yet")
    face, zm = rsrv()["face"], rsrv()["zoom_max"]  # the test vlog is small: the zoom stops sooner (web/reframe.py _zoom_max)
    b0 = box(); x, y = b0["x"] + b0["width"] / 2, b0["y"] + b0["height"] / 2
    pg.mouse.move(x, y); pg.mouse.down()
    for i in range(1, 13):
        pg.mouse.move(x - 100 * i / 12, y); pg.wait_for_timeout(15)
    live = box()["x"]
    pg.mouse.up(); pg.wait_for_timeout(400)
    r1 = rf()
    check(live < b0["x"] - 40 and r1 and r1["moves"][0]["x"] < face - 0.03 and state() == "1 change not saved",
          f"dragging the frame moves it (x {face} -> {r1 and r1['moves'][0]['x']})")
    ev("(i=>{i.value=9;i.dispatchEvent(new Event('input'));i.dispatchEvent(new Event('change'))})(document.getElementById('rfZoom'))"); pg.wait_for_timeout(400)
    check(rf()["moves"][0]["z"] == zm and near(box()["width"], b0["width"] / zm, 3), f"zoom: as far as this vlog allows ({zm}×), a smaller frame")
    pg.click("#edUndo"); pg.wait_for_timeout(300)
    check(rf()["moves"][0]["z"] == 1, "Undo takes the zoom back")
    pg.click("#edRedo"); pg.wait_for_timeout(300)
    check(rf()["moves"][0]["z"] == zm, "Redo puts it back")
    pg.click("#rfFollow")
    pg.wait_for_function("document.querySelector('#edRf .rf-note').textContent.length>0", timeout=30000)
    check("No face" in pg.inner_text("#edRf .rf-note") and rf()["moves"][0]["z"] == zm, "Follow the speaker: no face in this test video, says so, changes nothing")
    # moves over time: the frame somewhere else later in the Short
    pg.click("#rfOver"); pg.wait_for_timeout(300)
    ev("document.getElementById('edVideo').currentTime=6"); pg.wait_for_timeout(800)
    b1 = box(); x, y = b1["x"] + b1["width"] / 2, b1["y"] + b1["height"] / 2
    pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x + 160, y, steps=10); pg.mouse.up(); pg.wait_for_timeout(400)
    r2 = rf()
    check(len(r2["moves"]) == 2 and r2["moves"][1]["x"] > r2["moves"][0]["x"] and pg.locator("#edRf .rf-move").count() == 2,
          f"moves over time: a second move later on ({[(m['t'], m['x']) for m in r2['moves']]})")
    pg.click('[data-moves="cut"]'); pg.wait_for_timeout(200)
    check(rf()["cut"] is True, "moves can cut instead of gliding")
    pg.click("#rfExact")
    pg.wait_for_function("!document.querySelector('#edRfStage .rf-exact').hidden", timeout=30000)
    check(True, "Check with captions shows the server's frame")
    vid0 = ev(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video")
    pg.click("#edSave")
    wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video!=={vid0!r} && !edRf.dirty()", timeout=120000)
    sv = rsrv()["reframe"]
    check(sv and len(sv["moves"]) == 2 and sv["cut"] is True and sv["moves"][0]["z"] == zm, f"saved: the moves, the cut, the zoom ({sv})")
    check(ev("!edRf.dirty() && document.getElementById('edUndo').disabled"), "saved, nothing to undo")
    # captions and framing changed together: both saved, one remake
    seen_js = f"window.SEEN=new Set(); window.SEENT=setInterval(()=>{{const c=clData.find(c=>c.job==={RJ!r}&&c.idx==={RI}); if(c) SEEN.add(c.video);}},100)"
    ev(seen_js)
    pg.click('[data-layout="fit"]'); pg.wait_for_timeout(300)
    tool("captions"); pg.click('.cp-pre[data-p="clean"]'); pg.wait_for_timeout(300); tool("reframe")
    check(state() == "2 changes not saved", "captions and framing: " + state())
    vid1 = ev(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video")
    pg.click("#edSave"); wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video!=={vid1!r} && !edRf.dirty() && !edCap.dirty()", timeout=120000)
    pg.wait_for_timeout(4000)
    seen = ev("(clearInterval(SEENT), [...SEEN])")
    cs = ev(f"fetch('/api/captions/{RJ}/{RI}').then(r=>r.json())")["captions"]
    check(rsrv()["reframe"]["layout"] == "fit" and cs["preset"] == "clean" and len(seen) == 2,
          f"both saved, one remake ({len(seen) - 1} new videos)")
    # framing and a cut word: the cut's remake makes the framing too
    pg.click('[data-layout="fill"]'); pg.wait_for_timeout(300)
    tool("ai"); n_p = len(P()); pg.locator("#aeTr .ae-w:not(.cut)").nth(3).click(); pg.wait_for_timeout(400); tool("reframe")
    vid2 = ev(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video")
    pg.click("#edSave"); wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video!=={vid2!r} && !edRf.dirty()", timeout=120000)
    check(rsrv()["reframe"] is None and len(server(RJ, RI)["pieces"]) == n_p + 1,
          "framing (back to Pit Crew's) with a cut: both made in the cut's remake")
    # smart framing: auto layout per shot, a shot flipped, punch-ins, tracking; then saved
    pg.click("#rfAuto")
    pg.wait_for_function("document.querySelector('#edRf .rf-note').textContent.length>0", timeout=60000)
    r3 = rf() or {}
    check(r3.get("shots") and pg.locator("#edRf .rf-shot").count() == len(r3["shots"]) and "shown whole" in pg.inner_text("#edRf .rf-note"),
          f"Auto layout per shot: {len(r3.get('shots') or [])} shots listed ({pg.inner_text('#edRf .rf-note')})")
    first_fit = r3["shots"][0]["fit"]
    check(ev("document.querySelector('#edRfStage .rf-src').classList.contains('fit')") == first_fit, "the picture shows the shot's layout")
    pg.click(f'#edRf [data-shot="0"][data-fit="{0 if first_fit else 1}"]'); pg.wait_for_timeout(300)
    r4 = rf()
    check(r4 and (r4.get("shots") or [{}])[0].get("fit", False) != first_fit or (first_fit and not r4.get("shots")),
          "a shot flipped by hand")
    pg.click('#edRf [data-punch="punchy"]'); pg.wait_for_timeout(300)
    r5 = rf()
    check(r5 and r5.get("punch") and r5["punch"]["amount"] == 0.16 and len(r5["punch"]["at"]) >= 2, f"Zoom on emphasis: Punchy, {len((r5 or {}).get('punch', {}).get('at', []))} punch-ins")
    pg.click("#rfTrack"); pg.wait_for_timeout(200)
    check(ev("document.querySelector('#edRfStage .rf-src').classList.contains('tracking')"), "Track something: waiting for a click in the picture")
    sb_ = pg.locator("#edRfStage .rf-src").bounding_box()
    pg.mouse.click(sb_["x"] + sb_["width"] * 0.3, sb_["y"] + sb_["height"] * 0.4)
    pg.wait_for_function("!document.querySelector('#edRfStage .rf-src').classList.contains('tracking') && document.querySelector('#rfTrack') && !document.querySelector('#rfTrack').disabled", timeout=60000)
    tnote = pg.inner_text("#edRf .rf-note")
    check("Following it for" in tnote or "couldn't follow" in tnote, "tracking answers: " + tnote)
    vid_s = ev(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video")
    pg.click("#edSave"); wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={RJ!r}&&c.idx==={RI})||{{}}).video!=={vid_s!r} && !edRf.dirty()", timeout=120000)
    srv_r = rsrv()["reframe"] or {}
    st = ev(f"fetch('/api/status/{RJ}').then(r=>r.json())")
    me_r = next(x for x in st["shorts"] if x["idx"] == RI)
    check(not me_r.get("retry_error") and srv_r.get("punch", {}).get("amount") == 0.16, f"saved and remade with them ({me_r.get('retry_error')})")
    sv = rsrv()["reframe"]
    pg.click('[data-layout="split"]'); pg.wait_for_timeout(400)
    check(pg.locator("#edRfStage .rf-box").count() == 2 and rf()["layout"] == "split", "Split: two frames, one per view")
    pg.click("#edCancel"); pg.wait_for_timeout(800)
    check(rf() == sv and state() == "Saved", "Discard puts the saved framing back")
    tool("details")
    check(not pg.locator("#edRfStage").is_visible() and pg.locator("#edVideo").is_visible(), "other tools: the player is back")

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
    tool("trim", strip=True)
    fb = pg.locator("#edTrimStrip .ts-film").bounding_box()
    pg.mouse.click(fb["x"] + fb["width"] * 0.4, fb["y"] + 20); pg.mouse.click(fb["x"] + fb["width"] * 0.5, fb["y"] + 20); pg.wait_for_timeout(300)
    check(ev("edTS.sel()") is None and ev("edTS.first()") is None and pg.locator("#edTrimStrip .ts.ro").count() == 1,
          "clicks on the video row don't choose anything to cut")
    tool("trim")
    b4 = P()
    try:
        drag_handle(0, "end", -80)
    except Exception:  # noqa: BLE001  (the handle may not show on a part that can't change)
        pass
    check(P() == b4 and state() == "Saved", "dragging an end doesn't change it")
    check(parts().count() == 1 and abs(parts().first.bounding_box()["width"] - pg.locator('#edTwick .twick-track').first.bounding_box()["width"]) < 60,
          "the part is put back")
    tool("reframe")
    pg.wait_for_function("document.querySelector('#edRf .ae-warn, #edRf .ae-help')", timeout=20000)
    check("video was deleted" in pg.inner_text("#edRf") and pg.locator("#edRf [data-layout]").first.is_disabled(),
          "Reframe says why, and can't be changed")

    # ---------------------------------------------------------------- 13b. the vlog deleted, the Shorts' clean clips kept
    print("13b. The vlog's video deleted by the creator: its drafts keep a clean clip")
    r = ev(f"fetch('/api/vlogs/{A}/delete-video',{{method:'POST'}}).then(r=>r.status)")
    check(r == 200 and not glob.glob(os.path.join(H["jobs_dir"], A, "source.*")), "the vlog's video is deleted")
    open_short(A, 1)
    ai = ev("edAE.info()")
    check(ai["can_apply"] and ai["clip"] and ai["reach"][1] - ai["reach"][0] < 200, f"the Short can still be edited, from its clip ({ai['reach']})")
    tool("trim", strip=True)
    w = ev("edTS.win()")
    check(w["a"] >= ai["reach"][0] - 0.01 and w["b"] <= ai["reach"][1] + 0.01 and ev("edTlOff") == ai["reach"][0],
          f"the video row shows the clip, at its place in the vlog ({w})")
    pg.wait_for_function("""(()=>{const c=document.querySelector('#edTrimStrip .ts-pics'); if(!c||!c.width) return false;
        const d=c.getContext('2d').getImageData(c.width/2|0,c.height/2|0,1,1).data; return d[0]+d[1]+d[2]>60;})()""", timeout=20000)
    check(True, "with its pictures")
    tool("reframe")
    pg.wait_for_function("document.querySelector('#edRf [data-layout]')", timeout=20000)
    check(not pg.locator('#edRf [data-layout="fit"]').is_disabled(), "Reframe works")
    vid_a = ev(f"(clData.find(c=>c.job==={A!r}&&c.idx===1)||{{}}).video")
    pg.click('#edRf [data-layout="fit"]'); pg.wait_for_timeout(300)
    pg.click("#edSave"); wait_saved()
    pg.wait_for_function(f"(clData.find(c=>c.job==={A!r}&&c.idx===1)||{{}}).video!=={vid_a!r} && !edRf.dirty()", timeout=120000)
    st = ev(f"fetch('/api/status/{A}').then(r=>r.json())")
    me = next(x for x in st["shorts"] if x["idx"] == 1)
    check(not me.get("retry_error") and (me.get("reframe") or {}).get("layout") == "fit", f"remade from its clip ({me.get('retry_error')})")
    tool("details")

    # ---------------------------------------------------------------- 14. leaving and coming back
    print("14. Leaving and coming back")
    open_short(A, 2)
    tool("details")  # (13 ended in Reframe, whose picture covers the player)
    ev("(v=>{v.muted=true; return v.play()})(document.getElementById('edVideo'))"); pg.wait_for_timeout(800)
    check(not ev("document.getElementById('edVideo').paused") and ev("document.getElementById('edVideo').currentTime") < 3,
          "the Short plays, from its start (not where the last Short was)")
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
