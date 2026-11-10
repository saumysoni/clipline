"""
Text & Overlays in a real browser (Playwright + Chromium), against Pit Crew's real server with the outside world faked
(tests/fakes.py) and real FFmpeg renders: add text, type it, drag it on the picture, style it, change when it shows, the
Overlays row, Undo / Redo, Discard, Save (then what the server saved and burned in), Exact frame, and the panel's look at
several widths in both themes (screenshots in SHOTS).

    python -m tests.browser.check_text        (about a minute; exits 1 on a failure)

Not part of `unittest discover` (it needs a browser).
"""
import os
import sys
import threading
import time
import urllib.request

os.environ["PITCREW_REAL_MEDIA"] = "1"
from tests import fakes as F  # noqa: E402  (first: clean settings, fakes, throwaway folders)

import tempfile  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import serve  # noqa: E402

from settings import JOBS_DIR  # noqa: E402

PORT = int(os.getenv("PITCREW_TEST_PORT", "8793"))
B = f"http://127.0.0.1:{PORT}"
SHOTS = os.getenv("PITCREW_SHOTS") or tempfile.mkdtemp(prefix="pc-text-")
fails, passes = [], 0


def start_server():
    app = F.app()
    c = F.client(F.new_user(email="me@example.com"))
    jid, st = F.make_shorts(c, 120, 2)
    threading.Thread(target=lambda: serve(app, host="127.0.0.1", port=PORT, threads=8, _quiet=True), daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(B + "/healthz", timeout=2)
            break
        except OSError:
            time.sleep(0.1)
    return jid, st["shorts"][0]["idx"]


def check(cond, what):
    global passes
    if cond:
        passes += 1
        print("  ok  ", what)
    else:
        fails.append(what)
        print("  FAIL", what)


JID, IDX = start_server()

with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:300]))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and errs.append(m.text[:300]))
    pg.goto(B + "/")
    pg.evaluate("""fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({email:'me@example.com',password:'password-123'})})""")
    ev = pg.evaluate
    pg.goto(B + f"/#edit/{JID}/{IDX}")
    pg.wait_for_function("edAE.info() && edOv.snap()!==null && edTlSrc", timeout=30000)
    pg.wait_for_timeout(500)

    print("The tool and its stage")
    pg.click('#edRail button[data-t="text"]')
    pg.wait_for_timeout(600)
    check(pg.is_visible("#edOvWrap") and pg.is_visible("#edOvStage"), "Text & Overlays opens, its picture over the player")
    check(pg.locator("#edOvTrack .ed-ov-add").count() == 1, "the Overlays row offers Add text")
    pg.wait_for_function("document.querySelector('#edOvStage canvas') && document.querySelector('#edOvStage canvas').width>0", timeout=15000)

    print("Add, type, style")
    pg.click("#ovAdd")
    pg.wait_for_timeout(500)
    check(len(ev("edOv.snap()")) == 1, "Add text adds one")
    check(pg.inner_text("#edState").startswith("1 change"), "the save state counts it")
    pg.fill("#ovWords", "DAY 3 IN GOA")
    pg.wait_for_timeout(300)
    check(ev("edOv.snap()[0].text") == "DAY 3 IN GOA", "typing changes the words")
    pg.wait_for_selector("#edOvStage .ov-box.on", timeout=5000)
    check(pg.locator("#edOvStage .ov-box").count() == 1, "the text has a box on the picture")
    check("DAY 3 IN GOA" in pg.inner_text("#edOvTrack"), "the Overlays row shows it")
    pg.click('.ov-style[data-style="boxed"]')
    pg.click('#edOv .cp-seg [data-k="size"][data-v="l"]')
    pg.select_option('#edOv select[data-k="font"]', "anton")
    o = ev("edOv.snap()[0]")
    check((o["style"], o["size"], o["font"]) == ("boxed", "l", "anton"), "style, size and font")

    print("Top / Lower clear of the hook and the captions")
    pg.click('#edOv .cp-seg [data-k="y"]:has-text("Lower")')
    pg.wait_for_timeout(200)
    o = ev("edOv.snap()[0]")
    cap = ev("edCap.snap()")
    bottom_px = o["y"] * 1920 + 136 * 0.55  # (size L, one line)
    check(bottom_px < 1920 - cap["bottom"] - cap["size"], f"Lower ends above the captions ({bottom_px:.0f} px)")
    pg.click('#edOv .cp-seg [data-k="y"]:has-text("Top")')
    pg.wait_for_timeout(200)
    o = ev("edOv.snap()[0]")
    check(o["y"] * 1920 - 136 * 0.55 >= 390, "Top starts under a two-line hook")

    print("Drag it on the picture")
    box = pg.locator("#edOvStage .ov-box").first.bounding_box()
    cv = pg.locator("#edOvStage canvas").bounding_box()
    y0 = o["y"]
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pg.mouse.down()
    for n in range(1, 11):
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2 + cv["height"] * 0.2 * n / 10)
        pg.wait_for_timeout(15)
    pg.mouse.up()
    pg.wait_for_timeout(400)
    o = ev("edOv.snap()[0]")
    check(abs(o["y"] - (y0 + 0.2)) < 0.03 and o["x"] == 0.5, f"dragged down a fifth, kept in the middle ({y0} -> {o['y']})")

    print("When it shows")
    a, b = o["a"], o["b"]
    pg.click('#edOv [data-t="b"][data-d="0.5"]')
    pg.wait_for_timeout(200)
    check(abs(ev("edOv.snap()[0].b") - (b + 0.5)) < 0.01, "End +0.5 s")
    pg.click('#edOv [data-t="b"][data-d="-0.5"]')
    for _ in range(6):
        pg.click('#edOv [data-t="b"][data-d="-0.5"]')
    check(abs(ev("edOv.snap()[0].b") - (a + 0.5)) < 0.01 and "third of a second" in pg.inner_text("#ovErr"),
          "never shorter than a third of a second")

    print("Undo / Redo / Discard")
    n = ev("edOv.snap()[0].b")
    pg.click("#edUndo")
    pg.wait_for_timeout(200)
    check(abs(ev("edOv.snap()[0].b") - n - 0.5) < 0.01, "Undo puts the end back")
    pg.click("#edRedo")
    pg.wait_for_timeout(200)
    check(abs(ev("edOv.snap()[0].b") - n) < 0.01, "Redo")
    hist = ev("edHist.length")
    pg.click("#ovWords")
    pg.keyboard.press("End")
    pg.keyboard.type("!!!")
    pg.wait_for_timeout(200)
    check(ev("edHist.length") == hist + 1, "typing is one Undo step")
    pg.click('#edOv [data-t="b"][data-d="0.5"]')
    pg.click('#edOv [data-t="b"][data-d="0.5"]')
    pg.click('#edOv [data-t="b"][data-d="0.5"]')  # a little over 1.5 s on screen

    print("Screenshots")
    for w, h in ((1440, 900), (1180, 800), (900, 1000)):
        for scheme in ("dark", "light"):
            pg.set_viewport_size({"width": w, "height": h})
            pg.emulate_media(color_scheme=scheme)
            ev(f"document.documentElement.dataset.theme='{scheme}'")
            pg.wait_for_timeout(500)
            pg.screenshot(path=f"{SHOTS}/text-{w}-{scheme}.png", full_page=w <= 900)
            check(ev("document.documentElement.scrollWidth<=innerWidth+1"), f"nothing sticks out sideways at {w} px ({scheme})")
    pg.set_viewport_size({"width": 1440, "height": 900})

    print("Exact frame")
    pg.click("#ovExactBtn")
    pg.wait_for_selector("#ovExact img", timeout=30000)
    check(True, "the server draws the exact frame")
    pg.wait_for_timeout(800)
    ev("document.getElementById('ovExact').scrollIntoView({block:'end'})")
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{SHOTS}/text-exact.png")

    print("Save")
    pg.click("#edSave")
    pg.wait_for_function("document.getElementById('edState').textContent==='Saved'", timeout=120000)
    pg.wait_for_timeout(1500)
    saved = ev(f"fetch('/api/overlays/{JID}/{IDX}').then(r=>r.json())")["overlays"]
    check(len(saved) == 1 and saved[0]["text"] == "DAY 3 IN GOA!!!" and saved[0]["style"] == "boxed", "the server saved it")
    me = next(s for s in F.job_json(JID)["shorts"] if s["idx"] == IDX)
    ass = (JOBS_DIR / JID / me["video"].replace("short_", "captions_").replace(".mp4", ".ass")).read_text()
    check("DAY 3 IN GOA!!!" in ass and ",OvlBox," in ass, "and burned it into the remade Short")
    check(not ev("edD.dirty()") and not ev("edOv.dirty()"), "nothing left to save")

    print("Undo the save")
    pg.click("#edUndo")
    pg.wait_for_function("document.getElementById('edState').textContent==='Saved'", timeout=120000)
    pg.wait_for_timeout(1500)
    check(ev(f"fetch('/api/overlays/{JID}/{IDX}').then(r=>r.json())")["overlays"] == [], "Undo after a save takes the text off the Short")
    pg.click("#edRedo")
    pg.wait_for_function("document.getElementById('edState').textContent==='Saved'", timeout=120000)
    pg.wait_for_timeout(1500)
    check(len(ev(f"fetch('/api/overlays/{JID}/{IDX}').then(r=>r.json())")["overlays"]) == 1, "Redo puts it back")

    print("Delete it, then Discard")
    pg.click('#edOv .ov-pick')
    pg.click('#edOv .ov-list .ov-del')
    pg.wait_for_timeout(200)
    check(ev("edOv.snap().length") == 0 and ev("edOv.dirty()"), "deleted, not saved yet")
    pg.click("#edCancel")
    pg.wait_for_timeout(1500)
    check(ev("edOv.snap().length") == 1, "Discard brings it back")

    check(not errs, "no page errors" + ("" if not errs else ": " + " | ".join(errs[:5])))
    br.close()

print(f"\n{passes} passed, {len(fails)} failed. Screenshots in {SHOTS}")
sys.exit(1 if fails else 0)
