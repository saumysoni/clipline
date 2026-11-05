"""
Drafts, the review page, the Vlogs page and the sidebar in a real browser (Playwright + Chromium), against Pit
Crew's real server with the outside world faked (tests/fakes.py) and real FFmpeg renders:

  - Shorts being made show on Drafts › Shorts & Reels under their vlog, with Pause / Resume and Stop; so does a vlog
    that stopped (Try again). Pause and Resume on the making page too.
  - Drafts groups the drafts by vlog, each with Review & post: the review page, which can always be reached again,
    with Drafts marked in the sidebar.
  - Vlogs shows only vlogs posted on YouTube; videos sent only for Shorts aren't there.
  - "View your channel" / "View your profile" under the YouTube and Instagram names.

    python -m tests.browser.check_drafts      (about 2 minutes; exits 1 on a failure)
"""
import os
import sys
import threading
import time
import urllib.request

os.environ["PITCREW_REAL_MEDIA"] = "1"
from tests import fakes as F  # noqa: E402  (first: clean settings, fakes, throwaway folders)

from playwright.sync_api import sync_playwright  # noqa: E402
from waitress import serve  # noqa: E402

from settings import JOBS_DIR  # noqa: E402

PORT = int(os.getenv("PITCREW_TEST_PORT", "8792"))
B = f"http://127.0.0.1:{PORT}"
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
user = F.new_user(email="me@example.com")
c = F.client(user)
ready, st = F.make_shorts(c, 120, 2)  # a video sent only to make Shorts: ready, two drafts
# a vlog posted on YouTube with Pit Crew (as web/vlog_upload.py leaves it), with no Shorts
posted, _ = F.make_shorts(c, 60, 1)
from web.store import JOBS, LOCK, update  # noqa: E402
with LOCK:
    JOBS[posted].update(kind="vlog", count=0, shorts=[], vdraft={"title": "My posted vlog", "description": "", "tags": []},
                        vpost={"state": "done", "privacy": "public", "video_id": "abcdefghijk", "pct": 100})
update(posted)
F.connect_youtube(user["id"], handle="@pitcrewtest")
F.connect_instagram(user["id"], username="pitcrew.test")
threading.Thread(target=lambda: serve(app, host="127.0.0.1", port=PORT, threads=8, _quiet=True), daemon=True).start()
for _ in range(100):
    try:
        urllib.request.urlopen(B + "/healthz", timeout=2)
        break
    except OSError:
        time.sleep(0.1)


def start_vlog(seconds=60, count=1):
    up = F.upload(c, F.test_video(seconds))
    return c.post("/api/start", data={"upload": up, "count": str(count)}).json["id"]


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    errs = []
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:300]))
    # (i.ytimg.com: the thumbnails of the made-up video ids in 6d. blob: reading the chosen file's length, js/allowance.js)
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and not (m.location or {}).get("url", "").startswith(("https://i.ytimg.com", "blob:")) and errs.append((m.text + " " + (m.location or {}).get("url", ""))[:300]))
    pg.on("dialog", lambda d: d.accept())  # Stop asks first
    pg.goto(B + "/")
    pg.evaluate("""fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
                   body:JSON.stringify({email:'me@example.com',password:'password-123'})})""")
    ev = pg.evaluate
    now_nav = lambda: ev("document.querySelector('.side .now') && document.querySelector('.side .now').id")

    def group(jid):
        return pg.locator(f'#clGrid .clg[data-k="{jid}"]')

    def drafts_shorts():  # opened afresh (from another page, as a person would)
        pg.goto(B + "/#settings"); pg.wait_for_timeout(300)
        pg.goto(B + "/#drafts/shorts")
        pg.wait_for_selector("#clGrid .clg, #clGrid .cl-empty", timeout=20000)
        pg.wait_for_timeout(500)

    # ---------------------------------------------------------------- 1. the sidebar
    print("1. Sidebar: View your channel / profile")
    pg.goto(B + "/#vlogs"); pg.wait_for_timeout(1500)
    check(pg.locator("#ytView").is_visible() and pg.get_attribute("#ytView", "href") == "https://www.youtube.com/%40pitcrewtest",
          "YouTube: " + str(pg.get_attribute("#ytView", "href")))
    check(pg.locator("#igView").is_visible() and pg.get_attribute("#igView", "href") == "https://www.instagram.com/pitcrew.test/",
          "Instagram: " + str(pg.get_attribute("#igView", "href")))
    yb, vb = pg.locator("#ytPill").bounding_box(), pg.locator("#ytView").bounding_box()
    check(vb["y"] > yb["y"] + yb["height"] - 2 and pg.get_attribute("#ytView", "target") == "_blank", "under the name, opens a new tab")

    # ---------------------------------------------------------------- 2. Vlogs: posted only
    print("2. Vlogs shows only posted vlogs")
    titles = pg.locator("#vlGrid .vr-title").all_inner_texts()
    check(titles == ["My posted vlog"], f"only the posted vlog: {titles}")

    # ---------------------------------------------------------------- 3. Drafts grouped, Review & post
    print("3. Drafts grouped by vlog; the review page can be reached again")
    drafts_shorts()
    g = group(ready)
    check(g.count() == 1 and "2 drafts" in g.inner_text(), "a group for the vlog with its 2 drafts")
    check(pg.locator(f'#clGrid .clip[data-k^="{ready}:"]').count() == 2, "its two cards follow")
    check(group(posted).count() == 0, "the posted vlog with no drafts has no group")
    g.locator(".clg-review").click()
    pg.wait_for_selector("#s3:not([hidden]) .short, #s3:not([hidden]) #reel > *", timeout=20000)
    check(ev("location.hash") == "#" + ready, "Review & post opens the review page (#" + ready + ")")
    check(now_nav() == "draftsNav", "the sidebar marks Drafts there (was: Shorts & Reels): " + str(now_nav()))
    pg.click("#vlogsNav"); pg.wait_for_timeout(800)
    pg.click("#draftsNav"); pg.wait_for_timeout(1200)
    if ev("location.hash") != "#drafts/shorts":
        pg.click("#dfTabShorts"); pg.wait_for_timeout(600)
    group(ready).locator(".clg-review").click()
    pg.wait_for_selector("#s3:not([hidden]) .short, #s3:not([hidden]) #reel > *", timeout=20000)
    check(ev("location.hash") == "#" + ready, "and again after leaving it")
    pg.go_back(); pg.wait_for_timeout(1200)
    check(ev("location.hash") == "#drafts/shorts" and not pg.locator("#s11").is_hidden(), "Back returns to Drafts")
    check(ev("document.getElementById('clVlog').options.length") >= 2, "the vlog filter still lists the vlog")
    ev(f"document.getElementById('clVlog').value='{ready}'; document.getElementById('clVlog').dispatchEvent(new Event('change'))")
    pg.wait_for_timeout(400)
    check(group(ready).count() == 1 and pg.locator("#clGrid .clg").count() == 1, "filtered to one vlog: its group and Review & post")

    # ---------------------------------------------------------------- 4. being made: on Drafts, Pause / Resume
    print("4. Shorts being made show on Drafts, with Pause / Resume and Stop")
    F.SLOW.transcribe = 6
    making = start_vlog(60, 1)
    drafts_shorts()
    pg.wait_for_selector(f'#clGrid .clg[data-k="{making}"] .clg-run', timeout=20000)
    g = group(making)
    check("Making your Shorts" in g.inner_text() and g.locator(".clg-pause").is_visible(), "its group shows the progress: " + g.inner_text().replace("\n", " | ")[:120])
    check(pg.locator("#jobsNow .jn").count() >= 1, "and the progress card too")
    F.wait(lambda: F.job_json(making).get("stage") == 1, what="transcribing")
    g.locator(".clg-pause").click()
    pg.wait_for_function(f"document.querySelector('#clGrid .clg[data-k=\"{making}\"] .clg-run.paused')", timeout=8000)  # at once, even mid-transcription
    F.SLOW.transcribe = 0
    g = group(making)
    check("Paused" in g.inner_text() and "Resume" in g.locator(".clg-pause").inner_text(), "then Paused, with Resume")
    check(F.job_json(making)["status"] == "paused", "the server agrees")
    check("Paused" in pg.inner_text("#jobsNow"), "the progress card says Paused (no 'Stopped' pop-up)")
    check(pg.locator(".toast").count() == 0, "no pop-up for a pause")
    g.locator(".clg-pause").click()
    pg.wait_for_function(f"!document.querySelector('#clGrid .clg[data-k=\"{making}\"] .clg-run')", timeout=60000)
    pg.wait_for_selector(f'#clGrid .clip[data-k="{making}:1"]', timeout=20000)
    check(group(making).locator(".clg-review").count() == 1, "Resume: it finishes, and its draft shows under it with Review & post")

    # ---------------------------------------------------------------- 5. the making page: Pause / Resume, Stop
    print("5. Pause / Resume and Stop on the making page")
    F.SLOW.transcribe = 6
    other = start_vlog(60, 1)
    pg.goto(B + "/#" + other)
    pg.wait_for_selector("#pauseBtn:not([hidden])", timeout=20000)
    check(now_nav() == "draftsNav", "the making page marks Drafts")
    F.wait(lambda: F.job_json(other).get("stage") == 1, what="transcribing")
    pg.click("#pauseBtn")
    pg.wait_for_function("document.getElementById('lightsTitle').textContent==='Paused'", timeout=8000)  # at once, mid-transcription
    check(F.SLOW.transcribe == 6 and F.job_json(other)["status"] == "paused", "Pause: paused at once, not when the step is done")
    F.SLOW.transcribe = 0
    check("Resume" in pg.inner_text("#pauseBtn"), "Paused, with Resume")
    pg.click("#pauseBtn")
    pg.wait_for_selector("#s3:not([hidden]) .short, #s3:not([hidden]) #reel > *", timeout=60000)
    check(F.job_json(other)["status"] == "ready", "Resume: on to the review page when it's done")
    F.SLOW.transcribe = 6
    third = start_vlog(60, 1)
    pg.goto(B + "/#" + third)
    pg.wait_for_selector("#stopBtn", state="visible", timeout=20000)
    pg.click("#stopBtn"); pg.wait_for_timeout(1500)
    F.SLOW.transcribe = 0
    F.wait(lambda: not (JOBS_DIR / third).exists(), timeout=20, what="stopped")
    check(ev("location.hash") == "#drafts/shorts", "Stop: removed, back to Drafts › Shorts & Reels (not Vlogs)")

    # ---------------------------------------------------------------- 6. stopped: Try again on Drafts
    print("6. A vlog that stopped shows on Drafts with Try again")
    F.SLOW.fail = "the video editor stopped"
    bad = start_vlog(60, 1)
    F.wait(lambda: F.job_json(bad).get("status") == "error", timeout=30, what="stopped")
    F.SLOW.fail = ""
    drafts_shorts()
    g = group(bad)
    check(g.count() == 1 and "Stopped" in g.inner_text() and g.locator(".clg-again").is_visible(), "Stopped, with Try again and its reason")
    g.locator(".clg-again").click()
    pg.wait_for_selector(f'#clGrid .clip[data-k="{bad}:1"]', timeout=60000)
    check(F.job_json(bad)["status"] == "ready", "Try again: made, now a draft")

    # ---------------------------------------------------------------- 6b. making Shorts: the form, then Drafts
    print("6b. The form, then Drafts filtered to that video with loading cards")
    pg.goto(B + "/#new"); pg.wait_for_timeout(600)
    check(pg.locator("#sched").count() == 0 and "When should they post" not in pg.inner_text("#s1") and pg.locator("#sumSched").count() == 0, "no question about when to post")
    check(pg.locator("#countPick button").count() == 10, "ten number buttons for how many Shorts")
    pg.click('#countPick button[data-n="3"]'); pg.wait_for_timeout(100)
    check(pg.get_attribute('#countPick button[data-n="3"]', "aria-checked") == "true" and "3" in pg.inner_text("#make"), "pressing 3 chooses 3")
    pg.locator("#file").set_input_files(F.test_video(60))
    F.SLOW.transcribe = 4.0
    pg.click("#make")
    pg.wait_for_function("location.hash.startsWith('#drafts/shorts/')", timeout=30000)
    made = ev("location.hash.split('/')[2]")
    pg.wait_for_selector("#clGrid .cl-sk", timeout=10000); pg.wait_for_timeout(400)
    check(now_nav() == "draftsNav" and ev("clVlog") == made and pg.input_value("#clVlog") == made, "Drafts, filtered to this video")
    check(pg.locator("#clGrid .cl-sk").count() == 3, f"a loading card per Short ({pg.locator('#clGrid .cl-sk').count()})")
    check(pg.locator(f'#clGrid .clg[data-k="{made}"] .clg-pause').is_visible(), "with Pause on its head")
    check(not errs, f"no errors so far: {errs}")
    pg.locator(f'#clGrid .clg[data-k="{made}"] .clg-see').click(); pg.wait_for_timeout(600)
    check(pg.locator("#makingBack").is_visible(), "the making page has a Back")
    pg.click("#makingBack"); pg.wait_for_timeout(600)
    check(now_nav() == "draftsNav", "Back goes to Drafts")
    F.SLOW.transcribe = 0.0
    pg.wait_for_selector(f'#clGrid .clip[data-k="{made}:1"]', timeout=60000); pg.wait_for_timeout(500)
    check(pg.locator("#clGrid .cl-sk").count() == 0, "when they're made, their drafts replace the loading cards")
    # a Short being added shows as a loading card too
    from web.store import update as _update
    _update(made, shorts=F.job_json(made)["shorts"] + [{"idx": 99, "pending": True, "retrying": True}])
    pg.goto(B + "/#settings"); pg.wait_for_timeout(200); pg.goto(B + f"/#drafts/shorts/{made}"); pg.wait_for_selector("#clGrid .cl-sk", timeout=10000)
    check(pg.locator("#clGrid .cl-sk").count() == 1, "a Short being added: a loading card on Drafts too")
    _update(made, shorts=[s for s in F.job_json(made)["shorts"] if s["idx"] != 99])

    # ---------------------------------------------------------------- 6c. a video being prepared for YouTube
    print("6c. A draft video's upload page: Drafts in the sidebar, Back, Pause, AI suggestions")
    up = F.upload(c, F.test_video(60))
    F.SLOW.transcribe = 3.0
    prep = c.post("/api/vlog/start", data={"upload": up}).json["id"]
    pg.goto(B + "/#settings"); pg.wait_for_timeout(200); pg.goto(B + f"/#vlog/{prep}")
    pg.wait_for_selector("#vuPauseBtn", state="visible", timeout=15000); pg.wait_for_timeout(300)
    check(now_nav() == "draftsNav" and "Back to Drafts" in pg.inner_text("#vuBack"), "the sidebar says Drafts, and so does Back")
    F.wait(lambda: F.job_json(prep).get("stage") == 1, what="transcribing")
    pg.click("#vuPauseBtn")
    pg.wait_for_function("document.getElementById('vuPauseBtn').textContent.includes('Resume')", timeout=20000)
    check(F.job_json(prep)["status"] == "paused" and "Paused" in pg.inner_text("#vuPauseNote"), "Pause while it's prepared")
    F.SLOW.transcribe = 0.0
    pg.click("#vuPauseBtn")
    pg.wait_for_selector("#vuT", state="visible", timeout=30000)
    check(F.job_json(prep)["status"] == "ready", "Resume, then it's ready to check")
    pg.locator('.vs[data-field="title"] .vs-open').click()
    pg.locator('.vs[data-field="title"] .vs-ask').fill("funnier")
    pg.locator('.vs[data-field="title"] .vs-go').click()
    pg.wait_for_selector('.vs[data-field="title"] .vs-opt', timeout=15000)
    chosen = pg.locator('.vs[data-field="title"] .vs-t').first.inner_text()
    pg.locator('.vs[data-field="title"] .vs-opt button').first.click(); pg.wait_for_timeout(1300)
    check(pg.input_value("#vuT") == chosen and F.job_json(prep)["vdraft"]["title"] == chosen, f"AI suggestions: Use this fills the title and saves it ({chosen})")
    check(pg.locator('.vs[data-field="description"] .vs-open').is_visible() and pg.locator('.vs[data-field="tags"] .vs-open').is_visible(), "the description and tags have them too")
    pg.click("#vuBack"); pg.wait_for_timeout(800)
    check(now_nav() == "draftsNav" and not pg.locator("#s11").is_hidden(), "Back goes to Drafts")

    # ---------------------------------------------------------------- 6d. the whole channel; gone from YouTube
    print("6d. The Videos page: the rest of the channel, and what's gone from YouTube")
    import web.channel_videos as CV
    import web.youtube_sync as YS
    CH = F.job_json(ready)["uploads"][0]["channel"] if F.job_json(ready).get("uploads") else None
    uid = F.job_json(ready)["owner"]
    channel = CH or (F.yt_account(uid)["channels"][0]["id"])
    F.VIDEOS["outsidelong"] = {"title": "A video from before", "channel": channel, "privacy": "public", "seconds": 900}
    F.VIDEOS["outsideshrt"] = {"title": "A Short from before #shorts", "channel": channel, "privacy": "public", "seconds": 40}
    F.VIDEOS["gonelater01"] = {"title": "Deleted soon", "channel": channel, "privacy": "public", "seconds": 900}
    CV.refresh_user(uid)
    F.VIDEOS.pop("gonelater01"); CV.refresh_user(uid)
    pg.goto(B + "/#settings"); pg.wait_for_timeout(200); pg.goto(B + "/#vlogs"); pg.wait_for_selector("#vlGrid .vr-outside", timeout=15000); pg.wait_for_timeout(300)
    t = pg.inner_text("#vlGrid")
    check("A video from before" in t and "Not posted with Pit Crew" in t, "a video posted elsewhere, with the reason")
    check(pg.get_attribute("#vlGrid .vr-outside a.ghost", "href") == "https://www.youtube.com/watch?v=outsidelong", "and its YouTube link")
    check("A Short from before" not in t, "Shorts aren't on this page")
    check("Removed or deleted from YouTube" in t and pg.locator("#vlGrid .vr-gone").count() == 1, "a grey card for one that's gone")
    pg.screenshot(path=os.path.join(os.getenv("PITCREW_SHOTS", "/tmp"), "videos-page.png"))
    pg.locator("#vlGrid .vl-x-clear").click(); pg.wait_for_timeout(400)
    check(pg.locator("#vlGrid .vr-gone").count() == 0, "Remove clears it")
    posted_job = next(j for j in (ready, made) if F.job_json(j).get("uploads")) if any(F.job_json(j).get("uploads") for j in (ready, made)) else None
    if not posted_job:
        posted_job = made
        c.post(f"/api/schedule/{made}", json={"shorts": [{"idx": 1, "title": "Going out", "keep": True}], "schedule": "now", "channel": channel})
        F.wait(lambda: F.job_json(made).get("upload_status") == "done", what="posted")
    gone_idx = F.job_json(posted_job)["uploads"][0]["idx"]
    F.VIDEOS.pop(F.job_json(posted_job)["uploads"][0]["video_id"]); YS.sync_deleted(uid, force=True)
    pg.goto(B + "/#settings"); pg.wait_for_timeout(200); pg.goto(B + "/#clips"); pg.wait_for_selector(f'#clGrid .clip.cl-gone[data-k="{posted_job}:{gone_idx}"]', timeout=15000); pg.wait_for_timeout(300)
    t = pg.inner_text("#clGrid")
    check("Removed or deleted from YouTube" in t, "Shorts & Reels: a grey card, not posted")
    check("A Short from before" in t and "Made outside Pit Crew" in t, "and a Short from outside Pit Crew, marked, with its link")
    pg.screenshot(path=os.path.join(os.getenv("PITCREW_SHOTS", "/tmp"), "shorts-page.png"))
    pg.locator(f'#clGrid .clip[data-k="{posted_job}:{gone_idx}"] .cl-back').click(); pg.wait_for_timeout(700)
    check(pg.locator(f'#clGrid .clip[data-k="{posted_job}:{gone_idx}"]').count() == 0, "Back to Drafts takes it off this page")
    drafts_shorts()
    check(pg.locator(f'#clGrid .clip[data-k="{posted_job}:{gone_idx}"]').count() == 1, "and it's a draft again")
    check("Vlog" not in pg.inner_text("#s11") and "Videos" in pg.inner_text(".side"), "the word on the pages is Videos")

    # ---------------------------------------------------------------- Create from video: every video in the list opens
    ev("openMake()")
    pg.wait_for_selector("#mkList .mk-vlog", timeout=10000)
    pg.locator("#mkList .mk-vlog").first.click()
    check(pg.locator("#mkOpts").is_visible() and pg.locator("#mkGo").is_visible(), "a video in Create from video can be clicked, and goes on to its options")
    ev("$('mkDialog').close()")
    urls = ev("clWatch({youtube:{state:'posted',video_id:'abc'},instagram:{state:'posted',permalink:'https://www.instagram.com/reel/x/'}}).map(w=>w.href)")
    check(urls == ["https://www.youtube.com/shorts/abc", "https://www.instagram.com/reel/x/"], f"a posted clip links to where it is: {urls}")
    check(ev("clWatch({youtube:{state:'scheduled',video_id:'abc'}}).length") == 0, "one not out yet doesn't")

    # ---------------------------------------------------------------- 7. light mode, phone width
    pg.emulate_media(color_scheme="light"); pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(os.getenv("PITCREW_SHOTS", "/tmp"), "drafts-light.png"))
    pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(500)
    # (no internet here, so the icon font doesn't load and icons show as their names: give them an icon's size)
    if not ev("document.fonts.check('20px \"Material Symbols Outlined\"')"):
        pg.add_style_tag(content=".ms{display:inline-block;width:1em;overflow:hidden;white-space:nowrap}"); pg.wait_for_timeout(300)
    # (the sidebar's top bar is checked on its own: with Help shown it's a little too wide on a phone, see CLAUDE.md)
    out = ev("(()=>{ const m=document.querySelector('.main'); return m.scrollWidth-m.clientWidth; })()")
    check(out <= 1, f"phone width: nothing on Drafts sticks out sideways ({out}px)")

    print()
    check(not errs, f"no errors in the page: {errs}")
    br.close()

print(f"\n{passes} passed, {len(fails)} failed")
for f in fails:
    print("FAILED:", f)
sys.exit(1 if fails else 0)
