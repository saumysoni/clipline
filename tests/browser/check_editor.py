"""
The editor in a real browser (Playwright + Chromium): the timeline (Twick, editor-app/), Trim and AI Edit together,
against Pit Crew's real server with the outside world faked (tests/fakes.py) and real FFmpeg renders. Every action a
person can take on the timeline, then what the server saved.

    pip install playwright && python -m playwright install chromium   (once)
    python -m tests.browser.check_editor                               (about 3 minutes; exits 1 on a failure)

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
    br = p.chromium.launch()
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

    def drag_handle(k, side, dx):
        select(k)
        h = pg.locator(f"#edTwick .twick-track-element-handle-{side}").bounding_box()
        x, y = h["x"] + 1, h["y"] + h["height"] / 2
        pg.mouse.move(x, y); pg.mouse.down()
        for n in range(1, 21):
            pg.mouse.move(x + dx * n / 20, y); pg.wait_for_timeout(12)
        pg.mouse.up(); pg.wait_for_timeout(700)

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

    # ---------------------------------------------------------------- 9. zoom, ruler
    print("9. Zoom and the ruler")
    w1 = parts().first.bounding_box()["width"]
    ev("const z=document.getElementById('edZoom'); z.value=4; z.dispatchEvent(new Event('input'))"); pg.wait_for_timeout(500)
    w4 = parts().first.bounding_box()["width"]
    check(near(w4 / w1, 4, 0.2), f"zoom 4x: {w1:.0f}px -> {w4:.0f}px")
    ev("const z=document.getElementById('edZoom'); z.value=1; z.dispatchEvent(new Event('input'))"); pg.wait_for_timeout(500)
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
    pg.click("#edSave")
    wait_saved()
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

    # ---------------------------------------------------------------- 13. no video: read only
    print("13. The vlog's video is gone")
    for f in glob.glob(os.path.join(H["jobs_dir"], BJ, "source.*")):
        os.remove(f)
    open_short(BJ, 2)
    tool("trim")
    check("video was deleted" in pg.inner_text("#edTrim"), "Trim says why")
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
    pg.click("#edBack"); pg.wait_for_timeout(1200)
    open_short(A, 2)
    check(parts().count() == len(SV()), "the timeline is drawn again")
    pg.set_viewport_size({"width": 1180, "height": 820}); pg.wait_for_timeout(600)
    tool("trim")
    tw = pg.locator("#edTwick").bounding_box(); last = parts().nth(parts().count() - 1).bounding_box()
    check(last["x"] + last["width"] <= tw["x"] + tw["width"] + 1, "laptop size: the Short still fits")
    pg.emulate_media(color_scheme="light"); pg.wait_for_timeout(300)
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(500)

    print()
    other = sorted(u for u in outside if "fonts.googleapis.com" not in u)
    check(not other, f"no requests outside Pit Crew (besides its own Google Fonts): {other}")
    check(not errs, f"no errors in the page: {errs}")
    br.close()

print(f"\n{passes} passed, {len(fails)} failed")
for f in fails:
    print("FAILED:", f)
sys.exit(1 if fails else 0)
