"""
In Chromium against the real server: Shorts & Reels and Videos show only the YouTube channel and Instagram account chosen in
the sidebar, switching shows a short Loading over the page and then the other account's clips, and every card links out
the same way ("Watch on YouTube" / "Watch on Instagram").
Run: python -m tests.browser.check_accounts  (needs pip install playwright + python -m playwright install chromium)
SHOTS=<folder> also saves screenshots.
"""
from tests import _env  # noqa: F401  (first: clean settings)

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

os.environ.update(INSTAGRAM_APP_ID="a", INSTAGRAM_APP_SECRET="b")

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import serve  # noqa: E402

from tests import fakes as F  # noqa: E402
from accounts import db  # noqa: E402
from settings import JOBS_DIR  # noqa: E402

PORT = int(os.getenv("PITCREW_TEST_PORT", "8794"))
B = f"http://127.0.0.1:{PORT}"
SHOTS = os.getenv("SHOTS")
CH1, CH2, IG1, IG2 = "UCchannelA00000000000001", "UCchannelB00000000000002", "1789", "2789"
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

u = F.new_user(email="two@example.com")
uid = u["id"]
F.connect_youtube(uid, CH2, "Second Channel", "@second")
F.connect_youtube(uid, CH1, "First Channel", "@first")  # connected last = the one chosen
F.connect_instagram(uid, IG2, "second.ig")
F.connect_instagram(uid, IG1, "first.ig")
now = time.time()
for acct in (CH1, CH2, IG1, IG2):
    db.set_channel_checked(uid, acct, now)  # read today: nothing is read again while the check runs

# Made outside Pit Crew: a Short and a long video on each channel, a Reel on each Instagram account
db.save_channel_videos(uid, CH1, [{"id": "shortA00001", "title": "Outside short A", "published": "2026-10-02T10:00:00Z", "seconds": 40, "privacy": "public", "short": True},
                                  {"id": "longA000001", "title": "Long video A", "published": "2026-10-01T10:00:00Z", "seconds": 900, "privacy": "public", "short": False}], now)
db.save_channel_videos(uid, CH2, [{"id": "shortB00001", "title": "Outside short B", "published": "2026-10-03T10:00:00Z", "seconds": 30, "privacy": "public", "short": True},
                                  {"id": "longB000001", "title": "Long video B", "published": "2026-10-01T09:00:00Z", "seconds": 800, "privacy": "public", "short": False}], now)
db.replace_instagram_reels(uid, IG1, [{"id": "9101", "title": "Outside reel A", "published": "2026-10-04T10:00:00+0000", "permalink": "https://www.instagram.com/reel/a/", "thumb": ""}])
db.replace_instagram_reels(uid, IG2, [{"id": "9202", "title": "Outside reel B", "published": "2026-10-05T10:00:00+0000", "permalink": "https://www.instagram.com/reel/b/", "thumb": ""}])

# Pit Crew's own: a vlog posted on each channel, and Shorts posted with each account
def job(jid, title, channel, shorts, uploads, ig_posts):
    d = JOBS_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    (d / "job.json").write_text(json.dumps({
        "id": jid, "owner": uid, "status": "ready", "kind": "vlog", "count": len(shorts), "name": title, "created": now - 3600,
        "duration": 600, "vlog": {"title": title, "youtube_url": "https://www.youtube.com/watch?v=" + jid[:10] + "x", "channel": channel},
        "vpost": {"state": "done", "privacy": "public", "video_id": jid[:10] + "x", "channel": channel},
        "shorts": shorts, "uploads": uploads, "ig_posts": ig_posts, "stages": []}))


sh = lambda i, t: {"idx": i, "title": t, "start": 0, "end": 30, "thumb": "", "video": f"short_{i}.mp4"}
job("aaaaaaaaa1", "Vlog on first", CH1, [sh(1, "Pit Crew A yt"), sh(2, "Pit Crew A both")],
    [{"idx": 1, "video_id": "pcA00000001", "channel": CH1, "when": None, "uploaded_at": "2026-10-10T10:00:00+00:00"},
     {"idx": 2, "video_id": "pcA00000002", "channel": CH1, "when": None, "uploaded_at": "2026-10-10T10:00:00+00:00"}],
    [{"idx": 2, "status": "done", "ig_id": IG2, "username": "second.ig", "permalink": "https://www.instagram.com/reel/pc2/", "posted_at": "2026-10-10T11:00:00+00:00"}])
job("bbbbbbbbb2", "Vlog on second", CH2, [sh(1, "Pit Crew B yt"), sh(2, "Pit Crew B ig")],
    [{"idx": 1, "video_id": "pcB00000001", "channel": CH2, "when": None, "uploaded_at": "2026-10-11T10:00:00+00:00"}],
    [{"idx": 2, "status": "done", "ig_id": IG1, "username": "first.ig", "permalink": "https://www.instagram.com/reel/pc3/", "posted_at": "2026-10-11T11:00:00+00:00"}])


def shot(pg, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=f"{SHOTS}/{name}.png")


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:300]))
    pg.on("console", lambda m: m.type == "error" and "i.ytimg.com" not in (m.location or {}).get("url", "") and "ERR_" not in m.text and errs.append(m.text[:300]))
    pg.goto(B + "/#signin")
    pg.evaluate("""e=>fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({email:e,password:'password-123'})})""", u["email"])
    grid = lambda: pg.inner_text("#clGrid")
    tab = lambda p: pg.inner_text({"": "#clNAll", "youtube": "#clNYt", "instagram": "#clNIg"}[p])

    print("1. Shorts & Reels: First Channel + first.ig")
    pg.goto(B + "/#clips"); pg.reload()
    pg.wait_for_function("document.getElementById('clGrid').textContent.includes('Outside short A')", timeout=10000)
    pg.wait_for_function("yt.signed_in && ig.signed_in", timeout=5000)
    g = grid()
    check(all(t in g for t in ("Pit Crew A yt", "Pit Crew A both", "Pit Crew B ig", "Outside short A", "Outside reel A")), "the chosen accounts' clips show")
    check(not any(t in g for t in ("Pit Crew B yt", "Outside short B", "Outside reel B")), "the other accounts' clips don't")
    check(tab("") == "5" and tab("youtube") == "3" and tab("instagram") == "2", f"tab counts follow: {tab('')}/{tab('youtube')}/{tab('instagram')}")
    both = pg.locator(".clip", has_text="Pit Crew A both")
    check(both.locator(".cl-see").count() == 1 and "Watch on YouTube" in both.inner_text(), "a clip shows only the chosen account's link (its Reel went to second.ig)")
    labels = pg.eval_on_selector_all("#clGrid .cl-see", "els=>els.map(e=>e.textContent.replace('open_in_new','').trim())")
    check(set(labels) == {"Watch on YouTube", "Watch on Instagram"} and len(labels) == 5, f"every card links the same way: {labels}")
    check(pg.locator("#clGrid .cl-x .cl-foot a.ghost").count() == 0, "no odd button on the outside cards")
    shot(pg, "1-first")

    print("2. Switch YouTube to Second Channel: Loading, then its clips")
    pg.evaluate(f"switchTo('yt','{CH2}')")
    pg.wait_for_selector("#s9 .af-busy .af-wait", state="visible", timeout=3000)
    check("Loading Shorts and Reels" in pg.inner_text("#s9 .af-wait"), "the Loading screen shows")
    check("Second Channel" in pg.inner_text("#s9 .af-wait"), "and names the account")
    shot(pg, "2-loading")
    t0 = time.time()
    pg.wait_for_selector("#s9 .af-busy", state="detached", timeout=5000)
    took = time.time() - t0
    check(0.5 < took + 0.2 < 3, f"for about a second ({took:.1f} s after it showed)")
    g = grid()
    check("Pit Crew B yt" in g and "Outside short B" in g, "the second channel's Shorts show")
    check("Pit Crew A yt" not in g and "Outside short A" not in g, "the first channel's are gone")
    check("Pit Crew B ig" in g and "Outside reel A" in g, "Instagram stays on first.ig")

    print("3. Switch Instagram to second.ig")
    pg.evaluate(f"switchTo('ig','{IG2}')")
    pg.wait_for_selector("#s9 .af-busy", state="attached", timeout=3000)
    pg.wait_for_selector("#s9 .af-busy", state="detached", timeout=5000)
    g = grid()
    check("Outside reel B" in g and "Pit Crew A both" in g, "second.ig's Reels show (Pit Crew A both is on it)")
    check("Outside reel A" not in g and "Pit Crew B ig" not in g, "first.ig's are gone")
    both = pg.locator(".clip", has_text="Pit Crew A both")
    check("Watch on Instagram" in both.inner_text() and "Watch on YouTube" not in both.inner_text(), "its card links only to the chosen one")

    print("4. Videos follows the YouTube channel")
    pg.evaluate("openVlogs()")
    pg.wait_for_function("document.getElementById('vlGrid').textContent.includes('Long video B')", timeout=10000)
    v = pg.inner_text("#vlGrid")
    check("Vlog on second" in v and "Long video B" in v, "the second channel's videos show")
    check("Vlog on first" not in v and "Long video A" not in v, "the first channel's don't")
    pg.evaluate(f"switchTo('yt','{CH1}')")
    pg.wait_for_selector("#s7 .af-busy .af-wait", state="visible", timeout=3000)
    check("Loading videos" in pg.inner_text("#s7 .af-wait"), "Loading shows on Videos too")
    pg.wait_for_selector("#s7 .af-busy", state="detached", timeout=5000)
    v = pg.inner_text("#vlGrid")
    check("Vlog on first" in v and "Long video A" in v and "Long video B" not in v, "then the first channel's")
    shot(pg, "4-videos")

    print("5. Phone and light")
    pg.set_viewport_size({"width": 390, "height": 844}); pg.emulate_media(color_scheme="light")
    pg.evaluate("openClips()")
    pg.wait_for_function("document.getElementById('clGrid').textContent.includes('Outside short A')", timeout=10000)
    pg.evaluate(f"switchTo('yt','{CH2}')")
    pg.wait_for_selector("#s9 .af-busy .af-wait", state="visible", timeout=3000)
    w = pg.evaluate("document.querySelector('#s9 .af-wait').getBoundingClientRect().width")
    sw = pg.evaluate("document.documentElement.scrollWidth")
    check(w <= 390, f"the Loading screen fits a phone ({w:.0f} px; page {sw} px wide)")
    shot(pg, "5-phone-light")
    pg.wait_for_selector("#s9 .af-busy", state="detached", timeout=5000)
    check(not errs, f"no page errors: {errs}")
    br.close()

print(f"\n{passes} ok, {len(fails)} failed")
if fails:
    raise SystemExit(1)
