"""
In Chromium against the real server: Connect your accounts for a new account, the wait while what's on an account comes in, where
it lands, Reels on Shorts & Reels, and never interrupting someone in the middle of something.
Run: python -m tests.browser.check_first_import  (needs pip install playwright + python -m playwright install chromium)
SHOTS=<folder> also saves screenshots.
"""
from tests import _env  # noqa: F401  (first: clean settings)

import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

os.environ.update(INSTAGRAM_APP_ID="a", INSTAGRAM_APP_SECRET="b")

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import serve  # noqa: E402

from tests import fakes as F  # noqa: E402
import web.channel_videos as CV  # noqa: E402

PORT = int(os.getenv("PITCREW_TEST_PORT", "8793"))
B = f"http://127.0.0.1:{PORT}"
SHOTS = os.getenv("SHOTS")
CH = "UCchannel000000000000001"
fails, passes = [], 0


def check(cond, what):
    global passes
    if cond:
        passes += 1
        print("  ok  ", what)
    else:
        fails.append(what)
        print("  FAIL", what)


app = F.app()
F.install()
threading.Thread(target=lambda: serve(app, host="127.0.0.1", port=PORT, threads=8, _quiet=True), daemon=True).start()
for _ in range(100):
    try:
        urllib.request.urlopen(B + "/healthz", timeout=2)
        break
    except OSError:
        time.sleep(0.1)

for vid, title, sec in (("longvideo01", "Road trip", 900), ("longvideo02", "City walk", 800), ("shortvid001", "Quick #shorts", 40)):
    F.VIDEOS[vid] = {"title": title, "channel": CH, "privacy": "public", "seconds": sec}
F.REELS["9001"] = {"caption": "Sunset drive\nmore", "ig_id": "1789", "thumb": "", "posted": datetime(2026, 10, 1, tzinfo=timezone.utc)}

# A read that takes a moment, so the wait can be seen (and held open by a test)
real_read, HOLD = CV.refresh_channel, threading.Event()
HOLD.set()


def slow_read(*a, **k):
    HOLD.wait(60)
    return real_read(*a, **k)


CV.refresh_channel = slow_read


def shot(pg, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=f"{SHOTS}/{name}.png")


def sign_in(pg, email):
    pg.goto(B + "/#signin")
    pg.evaluate("""e=>fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({email:e,password:'password-123'})})""", email)


# The sign-in windows are Google's and Meta's: the connection is made here, then the page finds out as it does from the window.
# ytAsked / igAsked stand for the sign-in having been started by a click.
CONNECTED_YT = "ytAsked=true; fetch('/api/youtube/me').then(r=>r.json()).then(a=>signedIn(a))"
CONNECTED_IG = "igAsked=true; fetch('/api/instagram/me').then(r=>r.json()).then(a=>igSignedIn(a))"

with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:300]))
    pg.on("console", lambda m: m.type == "error" and "i.ytimg.com" not in (m.location or {}).get("url", "") and "ERR_TUNNEL" not in m.text and errs.append(m.text[:300]))
    on = lambda: pg.locator("#onb").is_visible()
    title = lambda: pg.inner_text("#onbTitle")

    print("1. A new account: Connect your accounts, then Skip")
    a = F.new_user(email="skip@example.com", onboarded=False)
    sign_in(pg, a["email"])
    pg.goto(B + "/#vlogs"); pg.reload(); pg.wait_for_selector("#onb:not([hidden])", timeout=10000)
    pg.wait_for_function("document.querySelectorAll('.onb-link').length===2", timeout=5000)
    check(title() == "Connect your accounts", "the screen shows")
    check(pg.locator(".onb-link").count() == 2, "YouTube and Instagram both offered")
    check(pg.evaluate("document.getElementById('app').inert"), "the app behind it can't be used")
    shot(pg, "1-welcome-dark")
    pg.click("#onbGo")
    check(not on() and not pg.evaluate("document.getElementById('app').inert"), "Skip for now gets in")
    pg.reload(); pg.wait_for_timeout(1000)
    check(not on(), "not shown again")

    print("2. Connecting YouTube: the wait, then Instagram is offered, then both land")
    b = F.new_user(email="join@example.com", onboarded=False)
    sign_in(pg, b["email"])
    pg.goto(B + "/#vlogs"); pg.reload(); pg.wait_for_selector("#onb:not([hidden])", timeout=10000)
    HOLD.clear()
    F.connect_youtube(b["id"])
    pg.evaluate(CONNECTED_YT)
    pg.wait_for_selector(".onb-step.run", timeout=5000)
    check(title() == "Getting your dashboard ready", "the wait says so")
    check("Connected to" in pg.inner_text("#onbSteps") and "Finding your videos and Shorts" in pg.inner_text("#onbSteps"), "real steps")
    check(pg.locator("#onbFoot").is_hidden(), "nothing to press while it reads")
    shot(pg, "2-wait-dark")
    HOLD.set()
    pg.wait_for_function("document.getElementById('onbTitle').textContent==='Your dashboard is ready'", timeout=15000)
    check("Found 2 videos and 1 Short" in pg.inner_text("#onbSteps"), "says what it found: " + pg.inner_text("#onbSteps").replace("\n", " / "))
    check("Connect Instagram too" in pg.inner_text("#onbLinks"), "the other app is offered")
    shot(pg, "3-found-dark")
    F.connect_instagram(b["id"])
    pg.evaluate(CONNECTED_IG)
    pg.wait_for_function("document.getElementById('onbSteps').textContent.includes('Found 1 Reel')", timeout=15000)
    check(True, "Instagram's Reels counted on the same screen")
    pg.wait_for_function("document.getElementById('onb').hidden", timeout=15000)
    pg.wait_for_selector("#vlGrid", timeout=5000)
    check(pg.locator("#s7").is_visible(), "lands on Videos, where the long ones are")
    pg.wait_for_function("document.getElementById('vlGrid').textContent.includes('Road trip')", timeout=10000)
    check("Sunset drive" not in pg.inner_text("#vlGrid"), "Reels aren't on Videos")
    pg.reload(); pg.wait_for_timeout(1200)
    check(not on(), "only once: not shown after a reload")

    print("3. Reels on Shorts & Reels")
    pg.goto(B + "/#clips"); pg.wait_for_selector("#clGrid .cl-x", timeout=10000)
    grid = pg.inner_text("#clGrid")
    check("Sunset drive" in grid and "Watch on Instagram" in grid and "Quick #shorts" in grid, "both apps' cards")
    check(pg.locator("#clGrid .cl-x .cl-x-nopic").count() == 1, "a Reel without a picture has a stand-in")
    check((pg.inner_text("#clNAll"), pg.inner_text("#clNYt"), pg.inner_text("#clNIg")) == ("2", "1", "1"), "counts per app")
    pg.click('#clPlatTabs button[data-p="instagram"]')
    grid = pg.inner_text("#clGrid")
    check("Sunset drive" in grid and "Quick #shorts" not in grid, "the Instagram tab shows only Reels")
    shot(pg, "4-reels-dark")

    print("4. A failed read: says so, doesn't trap anyone")
    c = F.new_user(email="fail@example.com")
    sign_in(pg, c["email"])
    pg.goto(B + "/#settings"); pg.reload(); pg.wait_for_selector("#s8:not([hidden])", timeout=8000)
    F.connect_youtube(c["id"], channel="UCchannelfail0000000000001", title="Broken")
    import youtube as yt
    real = yt.channel_videos
    yt.channel_videos = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("quota"))
    pg.evaluate("ig.configured=false; " + CONNECTED_YT)
    pg.wait_for_function("document.getElementById('onbSteps').textContent.includes(\"Couldn't read\")", timeout=15000)
    yt.channel_videos = real
    pg.wait_for_selector("#onbGo", state="visible", timeout=5000)  # (after the screen's shortest time)
    check("Your dashboard is open" == title(), "says it plainly, not as ready")
    check(pg.locator("#onbGo").is_visible(), "a button to carry on")
    shot(pg, "4b-failed-dark")
    pg.click("#onbGo")
    check(not on(), "carries on")

    print("5. In the middle of something: no interruption")
    d = F.new_user(email="busy@example.com")
    sign_in(pg, d["email"])
    pg.goto(B + "/#new"); pg.reload(); pg.wait_for_selector("#s1:not([hidden])", timeout=8000)
    F.connect_youtube(d["id"], channel="UCchannelbusy0000000000001")
    pg.evaluate(CONNECTED_YT); pg.wait_for_timeout(1500)
    check(not on() and pg.locator("#s1").is_visible(), "the screen stays on what they were doing")
    pg.goto(B + "/#vlogs"); pg.reload(); pg.wait_for_timeout(1200)
    check(not on(), "and doesn't pop up later")

    print("5b. Connecting from a dialog, reported twice: still no interruption")
    d2 = F.new_user(email="dialog@example.com")
    sign_in(pg, d2["email"])
    pg.goto(B + "/#drafts/shorts"); pg.reload(); pg.wait_for_selector("#s11:not([hidden])", timeout=8000)
    pg.evaluate("document.getElementById('clSched').showModal()")
    F.connect_youtube(d2["id"], channel="UCchanneldialog00000000001")
    pg.evaluate("ytThen=()=>{}; " + CONNECTED_YT)  # what the dialog's signIn(()=>{}) leaves waiting
    pg.wait_for_timeout(300)
    pg.evaluate("fetch('/api/youtube/me').then(r=>r.json()).then(a=>signedIn(a))")  # the window's message and the 2 s check both report it
    pg.wait_for_timeout(1500)
    check(not on() and pg.evaluate("document.getElementById('clSched').open"), "the dialog stays, with the creator's picks")
    pg.evaluate("document.getElementById('clSched').close()")
    d3 = F.new_user(email="dialog2@example.com")
    sign_in(pg, d3["email"])
    pg.goto(B + "/#drafts/shorts"); pg.reload(); pg.wait_for_selector("#s11:not([hidden])", timeout=8000)
    pg.evaluate("document.getElementById('clSched').showModal()")
    F.connect_youtube(d3["id"], channel="UCchanneldialog00000000002")
    pg.evaluate(CONNECTED_YT)  # from a dialog without a callback (the account switcher)
    pg.wait_for_timeout(1500)
    check(not on(), "any open dialog holds it back")
    pg.evaluate("document.getElementById('clSched').close()")

    d4 = F.new_user(email="twice@example.com")
    sign_in(pg, d4["email"])
    pg.goto(B + "/#analytics"); pg.reload(); pg.wait_for_selector("#s6:not([hidden])", timeout=8000)
    F.connect_youtube(d4["id"], channel="UCchanneltwice000000000001")
    pg.evaluate("ytThen=()=>{}; " + CONNECTED_YT + "; fetch('/api/youtube/me').then(r=>r.json()).then(a=>signedIn(a))")  # no dialog: only the one-answer rule holds it back
    pg.wait_for_timeout(1500)
    check(not on(), "a second report of one sign-in opens nothing")

    print("5c. Real pictures, and one that has expired")
    g = F.new_user(email="pics@example.com")
    F.REELS.clear()
    F.REELS["7001"] = {"caption": "Has a picture", "ig_id": "1789", "thumb": "https://scontent.cdninstagram.com/ok.jpg", "posted": datetime(2026, 10, 2, tzinfo=timezone.utc)}
    F.REELS["7002"] = {"caption": "Picture expired", "ig_id": "1789", "thumb": "https://scontent.cdninstagram.com/dead.jpg", "posted": datetime(2026, 10, 1, tzinfo=timezone.utc)}
    pixel = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082")
    pg.route("**/ok.jpg", lambda r: r.fulfill(status=200, content_type="image/png", body=pixel))
    pg.route("**/dead.jpg", lambda r: r.fulfill(status=403, body=b""))
    F.connect_instagram(g["id"])
    import web.instagram_reels as IR
    IR.refresh_user(g["id"])
    sign_in(pg, g["email"])
    pg.goto(B + "/#clips"); pg.reload(); pg.wait_for_selector("#clGrid .cl-x", timeout=8000)
    pg.wait_for_function("document.querySelectorAll('#clGrid .cl-x .cl-x-nopic').length===1", timeout=5000)
    check(pg.evaluate("[...document.querySelectorAll('#clGrid .cl-x img')].filter(i=>i.naturalWidth>0).length") == 1, "the good one shows")
    check(True, "the expired one has a stand-in, not a broken picture")
    errs[:] = [x for x in errs if "403" not in x]

    print("5d. A personal Instagram account that can't be read says what to do")
    h = F.new_user(email="personal@example.com")
    sign_in(pg, h["email"])
    pg.goto(B + "/#settings"); pg.reload(); pg.wait_for_selector("#s8:not([hidden])", timeout=8000)
    F.connect_instagram(h["id"], account_type="PERSONAL")
    import instagram as ig_mod
    real_ar = ig_mod.account_reels
    ig_mod.account_reels = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("no"))
    pg.evaluate(CONNECTED_IG)
    pg.wait_for_function("document.getElementById('onbSteps').textContent.includes('Switch to professional')", timeout=15000)
    ig_mod.account_reels = real_ar
    check(True, "points at the switch")
    pg.wait_for_selector("#onbGo", state="visible", timeout=5000)
    pg.click("#onbGo")

    print("6. Takes too long: sent on, never trapped")
    e = F.new_user(email="late@example.com")
    sign_in(pg, e["email"])
    pg.goto(B + "/#vlogs"); pg.reload(); pg.wait_for_selector("#s7:not([hidden])", timeout=8000)
    HOLD.clear()
    F.connect_youtube(e["id"], channel="UCchannellate0000000000001")
    pg.evaluate("window.__t=Date.now; " + CONNECTED_YT)
    pg.wait_for_selector(".onb-step.run", timeout=5000)
    pg.evaluate("onbFrom=Date.now()-ONB_MAX-1")
    pg.wait_for_function("document.getElementById('onbTitle').textContent==='Still bringing them in'", timeout=5000)
    check(pg.locator("#onbGo").is_visible(), "can go on straight away")
    shot(pg, "5-late-dark")
    pg.wait_for_function("document.getElementById('onb').hidden", timeout=8000)
    check(True, "goes on by itself")
    HOLD.set()

    print("7. Phone and light theme")
    f = F.new_user(email="phone@example.com", onboarded=False)
    ph = br.new_page(viewport={"width": 390, "height": 760}, color_scheme="light")
    pg = ph
    sign_in(pg, f["email"])
    pg.goto(B + "/#vlogs"); pg.reload(); pg.wait_for_selector("#onb:not([hidden])", timeout=10000)
    pg.wait_for_function("document.querySelectorAll('.onb-link').length===2", timeout=5000)
    sizes = pg.evaluate("({page:document.documentElement.scrollWidth,onb:document.getElementById('onb').scrollWidth,"
                        "card:document.querySelector('.onb-card').getBoundingClientRect().right,app:document.querySelector('.side').scrollWidth})")
    print("   ", sizes, pg.evaluate("""[...document.querySelectorAll('#onb, #onb *')].filter(e=>e.getBoundingClientRect().right>390)
        .map(e=>e.tagName+'.'+e.className+' '+Math.round(e.getBoundingClientRect().right))"""))
    check(sizes["onb"] <= 390 and sizes["card"] <= 390, "the screen fits 390 px")
    pg.evaluate("window.scrollTo(50,0)")
    check(pg.evaluate("window.scrollX") == 0, "and the page behind can't slide sideways")
    shot(pg, "6-welcome-phone-light")
    br.close()

check(not errs, f"no page errors: {errs[:5]}")
print(f"\n{passes} ok, {len(fails)} failed")
os._exit(1 if fails else 0)
