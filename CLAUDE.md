# CLAUDE.md

**The product is called Pit Crew** (renamed from Clipline in Oct 2026). Use "Pit Crew" in everything people see. Internal names keep `clipline` on purpose (repo, folder, `data/clipline.db`, `clipline-theme` storage key, `clipline_ids`, postMessage `{clipline: ...}`): renaming them would break existing setups for nothing.

Guidance for Claude (and humans) working on this repo. Read this before changing code.

## What Pit Crew is

A local web app that turns one long vlog into finished vertical YouTube Shorts:
transcribe (faster-whisper) → pick moments (Gemini, or OpenAI with `AI_PROVIDER=openai`) → cut,
reframe to 9:16 around the face, burn in word-by-word captions (FFmpeg + libass) → thumbnail (Pillow)
→ review in the browser → upload and schedule (YouTube Data API v3).

Today it runs on your own computer (the prototype); it is going to the cloud (below). The people using it are
**creators, not developers**:
every error they can see must be plain English and say what to do next.

## Direction: this is going to the cloud

Decided October 2026: Pit Crew will become a hosted web app. Creators upload from any device and our
servers do the work. The local version is the prototype. **Every change must work the same on a
Linux cloud server as on a laptop:**

- **No code paths for one kind of computer** (no Apple-only, Windows-only or GPU-brand-only engines).
  Use portable libraries that adapt by themselves. For example, faster-whisper uses an NVIDIA GPU
  when present and the processor otherwise.
- **Tune speed with environment settings** (`WHISPER_DEVICE`, `WHISPER_BATCH_SIZE`, `WHISPER_THREADS`,
  `X264_PRESET`, ...), not with `if mac:` branches. A cloud server sets them once.
- **Keep `pipeline/` free of web or UI concerns.** It will become the worker that processes queued
  jobs. Pass everything it needs as arguments or settings.
- **Treat local files as temporary.** The `jobs/` folder will become cloud storage, and in-memory `JOBS`
  will become a database. Don't build features that assume one long-running process on one disk.
- `start-mac.command` / `start-windows.bat` are local-development conveniences only.
- An Apple-GPU (MLX) transcription experiment was set aside for this reason (kept outside git, in
  `_backups/apple-gpu-transcription/`).

## Run it

```bash
cp .env.example .env              # then paste a Gemini key into GEMINI_API_KEY
bash start-mac.command            # Mac (Windows: start-windows.bat)
# → creates .venv, installs requirements.txt, runs app.py, opens http://localhost:8000
```

The start scripts reinstall packages whenever `requirements.txt` differs from
`.venv/installed-requirements.txt`, so **changing requirements.txt is how you ship a dependency fix** to
someone else's machine. Needs Python 3.10+ and FFmpeg/ffprobe on PATH.

Manual run: `.venv/bin/python app.py`. There is no build step. Tests: `python -m unittest discover -s tests -t .`
(a few seconds; see "Testing" below).

**On a server** (the live site): `python serve.py` (Waitress) behind Caddy, set up by `deploy/setup.sh`, updated with
`deploy/update.sh`. **LAUNCH.md** is the step-by-step launch; gotcha 24 has the rules.

## Where things live: one feature per file

The code is split so two people can work on different features without touching the same file.
**A feature usually has up to three files with the same name**: the work in `pipeline/` (or
`youtube/`), the web routes in `web/`, and the page in `static/js/` (+ `static/css/`, `static/sections/`).

| Feature | Work | Web routes | Page |
|---|---|---|---|
| Accounts (email + Google sign-in), `gate()` | `accounts/db.py` | `web/accounts.py` | `js/account.js`, `sections/auth.html`, `css/auth.css` |
| Forgot password (reset link by email) | `accounts/db.py` (`password_resets`), `accounts/mail.py` | `web/password_reset.py` | `js/password-reset.js`, `sections/auth.html` |
| Confirm your email (link on sign-up, `#verify=<token>`, 48 h; **nothing works until it's confirmed**: `gate()` answers 403 `verify: true` except `UNCONFIRMED_OK`; the confirm screen `#verifyForm` checks every 5 s, Resend, Change email for a typo (`POST /api/auth/email`, `change_email()`), Sign out; Google sign-ins are confirmed) | `accounts/db.py` (`email_verifications`, `change_email`) | `web/verify_email.py`, `web/accounts.py` (`UNCONFIRMED_OK`) | `js/verify-email.js` (`showVerify`), `sections/auth.html`, `css/auth.css`, `css/verify-email.css` |
| Delete account (Settings: type the email; every vlog, saved transcript, connection (YouTube revoked) and the account; refused while something is being made or posted) | `accounts/db.py` (`delete_user`) | `web/delete_account.py` | `js/delete-account.js`, `sections/settings.html` |
| Emails when away (Shorts ready, vlog ready to upload, stopped, posting failed; not while the creator watches the page, only to confirmed emails; links use `APP_URL`) | | `web/notices.py` | |
| Stop / Try again a whole vlog (Stop while it's made: removed, or back to ready if it was prepared for YouTube; Try again after it stopped: same video and transcript) | | `web/stop_and_retry.py` | `js/vlog-again.js` (used by `js/progress.js`, `js/vlog-upload.js`) |
| Sidebar (+ Create; Workspace: Vlogs, Shorts & Reels, Drafts, Scheduled, Analytics; Channels; Account / Settings / Appearance) | | | `sections/sidebar.html`, `js/nav.js`, `css/shell.css` |
| Drafts page (screen 11, `#drafts` / `#drafts/shorts`; tabs Vlogs = `isDraftVlog` (vlog uploads not on YouTube yet), Shorts & Reels = the Shorts & Reels clip browser in "drafts" mode (`isDraftClip`: on neither platform), with vlog filter, Select, Schedule, Delete) | | `web/vlogs.py`, `web/clips.py` (same APIs) | `js/drafts.js`, `sections/drafts.html` |
| Vlogs / Shorts & Reels tabs (Drafts and Scheduled; `pageTabs()`, last tab clicked remembered) | | | `js/page-tabs.js`, `css/page-tabs.css` |
| Vlogs page (home: every vlog except drafts and scheduled ones (`isDraftVlog` / `isScheduledVlog`, they have their own pages) as a row like YouTube's search results; each row's Shorts as buttons "5 drafts" / "1 scheduled" / "2 posted" to Drafts / Scheduled / Shorts & Reels (`vlShortsActs`, `vlOpen`, `vlWire` also used by Drafts and Scheduled); landscape picture = the vlog's YouTube thumbnail, else `poster.jpg`, else a Short's thumbnail on a blur; find by title; tick or Select all to delete several videos, their Shorts stay; a vlog that stopped before making any Shorts is removed completely; stopped vlogs show `web/errors.py`'s plain reason) | `pipeline/poster.py` | `web/vlogs.py` (`/api/vlogs`, `delete-video`, `delete-videos`) | `js/vlogs.js`, `sections/vlogs.html`, `css/vlogs.css` |
| Upload a vlog to YouTube (+ Create → Upload a vlog, or New vlog on the Vlogs page; screen 10, `#vlog/new` / `#vlog/<id>`): transcribe, AI title ideas + description with chapters + tags + a 16:9 thumbnail (Frame / Duotone), the creator edits (saved as typed), uploads public / scheduled / unlisted / private, then is offered "Make Shorts & Reels from this vlog?" | `pipeline/vlog_meta.py`, `pipeline/vlog_thumbnail.py`, `youtube/vlog_upload.py` | `web/vlog_upload.py` (`/api/vlog/start`, `/<id>/draft`, `/look`, `/upload`, `/shorts`) | `js/vlog-upload.js`, `sections/vlog-upload.html`, `css/vlog-upload.css` |
| What to make (+ Create asks: upload a vlog, or make Shorts; Make Shorts asks: from a vlog uploaded here, while its video is kept, or a new video file = screen 1) | | `web/vlog_upload.py` (`/shorts`) | `js/make-choice.js`, `sections/make-dialogs.html`, `css/vlog-upload.css` |
| Shorts & Reels page (clips that went out or are going out now, `isOutClip`; drafts and scheduled ones are on their own pages, and a clip that's out on one platform and planned on the other shows only the platform it's out on, `clOnPlat`. `#clBrowse` (bar + grid + Select / dock / schedule dialog) is one clip browser that `clOpen(mode, box, vlog)` moves into Shorts & Reels ("out") or Drafts ("drafts"); platform tabs All / YouTube Shorts / Instagram Reels with counts (`clPlatTabs()`, Shorts & Reels only); vlog filter and sort; Select all; Analytics / Download / Edit; schedule several at once on one plan of times; a clip on one platform but not the other has "Instagram · Post it there too" / "YouTube · Post it there too" on its card (`clPostOne()`: the same dialog, only that platform ticked); titles saved as typed) | | `web/clips.py` | `js/clips.js`, `sections/clips.html`, `css/clips.css` |
| Progress card (vlog being sent / made, "Shorts ready" pop-up) | | `web/vlogs.py` | `js/jobs-now.js`, `css/jobs-now.css` |
| Settings page (account: change password, sign out; connected channels; appearance) | | | `js/settings.js`, `sections/settings.html`, `css/settings.css` |
| Connect YouTube | `youtube/signin.py`, `youtube/connection.py`, `youtube/config.py` | `web/youtube_connect.py`, `web/google_redirect.py` | `js/youtube-connect.js` |
| Setup form (count, style, must-have moments, file, links) | `youtube/links.py` | `web/make_shorts.py` (`start`), `web/times.py` | `js/setup-form.js`, `js/must-have.js`, `js/video-file.js`, `js/links.js`, `js/start.js`, `sections/setup.html`, `css/setup.css` |
| Vlog title/description from a YouTube link (API key, else the creator's YouTube connection, else title only) | `youtube/vlog_info.py`, `pipeline/vlog_context.py` | `web/vlog_info.py` | `js/links.js` |
| Making Shorts (the whole run) | all of `pipeline/` | `web/make_shorts.py` | `js/progress.js`, `sections/making.html`, `css/making.css` |
| Vlog queue (`JOB_SLOTS` at once, `JOB_SLOTS_PER_CREATOR` per creator; every vlog run goes through `enqueue_locked()` and `run_job()` builds it from the job; waiting = `working` + `queued`; vlogs under way at a restart are queued again by `load_job()` (`_restarted`, at most `MAX_RECOVERIES`)) | | `web/job_queue.py`, `web/store.py` (`RECOVERED`) | `js/progress.js` (waiting title) |
| Limits (`MAX_VLOG_MINUTES`, `MONTHLY_VLOG_MINUTES` per account per UTC month; checked at `/api/upload/new`, at start from the sent file (`upload_problem()`: also "not a video"), and in the job after probe (`charge()`, once per vlog: `job["charged"]`); sign-ups 5 per IP per hour) | `accounts/db.py` (`usage`) | `web/allowance.py`, `web/accounts.py` | `js/allowance.js` (hint under the drop zones, length check before sending, Settings usage) |
| Help (`SUPPORT_EMAIL`: sidebar Help, "Get help" + reference = the vlog's id on a stopped vlog and in emails) | | `web/pages.py` (`/api/config`), `web/notices.py` | `js/help.js` |
| Sending the video in pieces (resumable: 8 MB pieces, retries, same file = carry on; `MAX_UPLOAD_GB`, room check, unfinished ones gone after 24 h; start routes take `upload=<id>` via `take_upload()`) | | `web/video_upload.py` | `js/video-upload.js` (`sendVideo()`, used by `js/start.js`, `js/vlog-upload.js`) |
| Transcription (+ saved transcripts) | `pipeline/transcribe.py`, `pipeline/transcript_cache.py` | | |
| Finding moments | `pipeline/moments.py` | | |
| Editing a Short (reframe, captions, render) | `pipeline/reframe.py`, `pipeline/captions.py`, `pipeline/render.py`, `pipeline/fonts.py` | | |
| Thumbnails | `pipeline/thumbnails/` (`make.py` → `design.py`: `frames` → `plan` → `layout` → `looks/<look>.py`; `simple.py`) | | |
| Review cards (YouTube-sized tiles; click opens the full card as a panel; "Post this" starts unticked, ticked cards are outlined, ticks kept in `reviewPicked`) | | `web/job_status.py`, `web/pages.py` (`/media`) | `js/review.js`, `js/review-cards.js`, `js/review-tiles.js`, `sections/review.html`, `css/review.css`, `css/review-tiles.css` |
| Hooks | `pipeline/hooks.py` | `web/hooks.py` | `js/hooks.js`, `css/hooks.css` |
| Thumbnail look (Frame / Duotone switch) and download | `pipeline/thumbnails/looks/` (one file per look), `make.py` (`relook_thumbnail`) | `web/thumbnail_look.py` | `js/thumbnail-look.js`, `css/thumbnail-look.css` |
| Post page (after review: list, when, where, upload; thumbnail as first frame) | `pipeline/cover.py` | `web/posting.py` | `sections/review.html` (`#postView`), `js/posting.js` (`showPost()`), `css/posting.css` |
| Try again (stays clickable when the vlog's video is deleted: the click explains it and says to upload again) | `pipeline/try_again.py` | `web/try_again.py` | `js/review-cards.js` |
| Add a Short / must-have moments | `pipeline/manual_moment.py` | `web/add_short.py` | `js/review-cards.js` |
| Choose on the video | `pipeline/preview.py` | `web/preview.py` | `js/picker.js`, `sections/picker.html`, `css/picker.css` |
| Upload / schedule | `youtube/upload.py`, `youtube/schedule_times.py` | `web/posting.py` | `js/posting.js`, `css/posting.css` |
| YouTube's daily upload limit, shared (open until 60 %, then fair shares, 5 kept for Replace; over it a Short or vlog waits in Pit Crew and goes up after midnight Pacific by itself; gotcha 28) | `accounts/db.py` (`youtube_uploads`) | `web/youtube_quota.py` (`take`, `defer`, `send_waiting`, `/api/youtube/today`), `web/posting.py`, `web/vlog_upload.py` (`send_waiting_vlog`) | `js/youtube-today.js`, `js/posting.js`, `js/posted.js`, `js/clips.js`, `js/vlog-upload.js` |
| Date and time picker (every "when": Post page YouTube + Instagram, Schedule dialog, vlog upload, Change time on Scheduled; a calendar + times every 15 minutes, opening in the page below its button; the hidden `datetime-local` input keeps its value, so callers didn't change; inputs added later are picked up). The choices are "On a day and time I choose" (`custom`) or "Right away" (`now`): the 12 PM / 6 PM presets were removed from the pages in Oct 2026 (the server still accepts `d18` / `d12` / `two` from old jobs) | | | `js/when-picker.js` (right after `theme.js`), `css/when-picker.css` |
| Posted list (step 4) | | | `js/posted.js`, `sections/posted.html`, `css/posted.css` |
| Scheduled page (sidebar "Scheduled", `#scheduled` / `#scheduled/shorts`, old `#youtube` = Shorts tab; tabs Vlogs = vlogs set to go public later, Shorts & Reels = YouTube + Instagram lists of what hasn't gone out, plus ones that need a look) | `youtube/manage.py` | `web/on_youtube.py`, `web/instagram_posting.py` (`/api/instagram/posts`) | `js/on-youtube.js`, `js/scheduled-instagram.js`, `js/nav.js` (Make Shorts link), `sections/on-youtube.html`, `sections/sidebar.html`, `css/on-youtube.css` |
| Analytics first-week section on the Videos tab (each Pit Crew clip's first-week views per platform, What's working, top clips; All / YouTube / Instagram switch; vlog filter) | `youtube/analytics.py` (`first_week_views`), `instagram/insights.py` (`snapshot_reels`), `accounts/db.py` (`reel_snapshots`) | `web/analytics_clips.py` | `js/analytics-clips.js` |
| Analytics page (4 tabs, `pageTabs("anTabs")`; filters Both / YouTube / Instagram (`anPlat`); range **All time (default)** or **Custom ▾** (a menu: 7 / 28 / 90 days, a year, or two dates: `anRangeSet()`, `?days=` / `?start=&end=`), hidden on Videos › "clips on both apps" (totals since posted); Shorts / Long videos / All = `?content=` -> `CONTENT` (`creatorContentType`), `period()`). **Overview**: Pit Crew's read (one per day, see 22d), paired YouTube/Instagram tiles (Instagram for the same window: `anIgQ()`; All time = each Reel's lifetime totals + total followers), one daily chart (All time starts a week before the first view; Instagram reach on it when the window is in Instagram's 90 days) | `youtube/analytics.py`, `youtube/analytics_coach.py` (`daily_facts`, `rules`, `read`), `instagram/insights.py` | `web/analytics.py`, `web/analytics_coach.py` (`/api/analytics/coach`, one read per day) | `js/analytics.js` (state, filters, `anQuery()`, Overview, clip window `openShortAnalytics`), `sections/analytics.html`, `css/analytics.css`, `css/analytics-pro.css` |
| Analytics **Videos** tab: each Pit Crew clip on YouTube vs Instagram (4 grouped column charts: likes, comments, shares, new subscribers vs new followers; Totals / Per 1,000 views; top 6 by views / newest 6 / one vlog / choose, at most 6 (`AN_PAIR_MAX`)), all clips list, clip window with both apps; "Compare any videos" (top 3 ticked, up to 8, calendar or days-since-posting, per day or running total); first-week section | `youtube/analytics_more.py` (`clip_totals`), `instagram/insights.py` (`reel_numbers`), `instagram/account_insights.py` (`follows_after`) | `web/analytics_pairs.py` (`/api/analytics/pairs`), `web/analytics_more.py` (`/videos`, `/compare`, `/vlogs`) | `js/analytics-videos.js`, `js/analytics-clips.js` |
| Analytics **Audience** tab (typical viewer, donuts for parts of a whole (`donutHTML`, ≤5 slices), columns with numbers for lists (`colsHTML`, class `vbar`: theme.css owns `.bar`), funnel, subscribers vs not when YouTube gives it; Instagram reach, followers by country/age/city) and **Grow** tab (when to post: 3 slots from viewers' evenings + Instagram online hours, on the creator's clock; lessons with "Got it", saved in localStorage `pc-an-lessons`) | `youtube/analytics_more.py` (`audience`), `instagram/account_insights.py` | `web/analytics_more.py` (`/audience`, `/instagram`) | `js/analytics-audience.js`, `js/analytics-grow.js` |
| Analytics loading states (`anSkel(kind, title)` / `anWait(title, kind)`: a skeleton shaped like what's coming (overview, pairs, audience, igaudience, igtiles, grow, compare, detail, chart), shimmer, racing-stripe bar, a status line that steps through what's happening and says "taking longer than usual" after 18 s; one shared timer that stops when no skeleton is left; `anSkelNum` for one number still coming; reloading over numbers already shown dims them under a stripe bar instead; no motion with reduced motion) | | | `js/analytics-loading.js` (before `analytics.js`), `css/analytics-loading.css` |
| Running on a server (`serve.py`: Waitress, one process; `deploy/setup.sh` Ubuntu 24.04 setup: packages, `pitcrew` user, code in `/opt/pitcrew/app`, data in `/srv/pitcrew`, `.env`, systemd service, Caddy https, nightly backups, firewall; `update.sh` safe updates with rollback, runs `tests/` first; `test.sh` every test suite on the server, safely; `backup.sh`, `invite.sh`, `status.sh`; `envtool.py` fills `.env` without overwriting; `point-docs.sh` turns `docs/` into redirects to the site) | | `web/health.py` (`/healthz`) | `deploy/`, `LAUNCH.md`, `REVIEWS.md` (Google/YouTube/Meta review texts) |
| YouTube's data rules (daily: re-check connected channels, every posted video, a vlog's link details after 30 days; forget a disconnected channel's data after 5 days; numbers in memory ≤ 30 days; gotcha 27) | `youtube/connection.py` (`recheck`), `youtube/stored_data.py` | `web/youtube_upkeep.py`, `accounts/db.py` (`gone_channels`) | |
| Private beta invites (`INVITE_ONLY=1`: only emails in `INVITES_FILE` (default `data/invites.txt`) can make an account, by email or Google; existing accounts unaffected; read on every sign-up, no restart) | | `web/invites.py` (used by `web/accounts.py`) | |
| Public pages (homepage `/welcome`, `/privacy`, `/terms`, `/data-deletion`; filled from settings: `SUPPORT_EMAIL`, `OPERATOR_NAME`, `GEMINI_PAID`, AI keys, retention times; linked from the sign-in screen and Settings) | | `web/legal.py` | `static/legal/` (`page.html` shell, one HTML per page, `legal.css`; the homepage also `home.css` + `home.js` (animated demo, step tabs, caption styles, example chart; `EXTRAS` in `web/legal.py` loads them there only; "Get started" = `/#signup`)) |
| Meta's callbacks (removed in Instagram → `/api/instagram/deauthorize`: connection dropped; data deletion asked through Meta → `/api/instagram/data-deletion`: connection, Reel records and saved numbers deleted, answers a code that `/data-deletion?code=` shows; both need a `signed_request` signed with `INSTAGRAM_APP_SECRET`) | | `web/instagram_deletion.py`, `accounts/db.py` (`deletion_requests`) | `static/legal/data-deletion.html` |
| Connect Instagram | `instagram/connection.py`, `instagram/config.py`, `instagram/http.py` | `web/instagram_connect.py`, `web/google_redirect.py` | `js/instagram-connect.js` |
| Hashtags, YouTube title, Instagram caption on each Short's editor card (hook first, then hashtags shared by both platforms, then a tab per connected platform; the caption is suggested from the title + full video (not the hook: it's on screen already, and repeated the title) until edited, then `ig_caption` is saved as typed; `caption_for()` keeps Instagram's 30 hashtags / 2,200 characters; "Generate ideas" under the title and the caption gives three AI options, `HOOK_RULE` + said-numbers check, works without the video) | `instagram/publish.py` (`suggested_caption`, `caption_for`), `pipeline/post_suggest.py` | `web/post_text.py` (`/post-text`, `/suggest`) | `js/post-text.js`, `css/post-text.css` |
| Post to Instagram (own schedule, Pit Crew posts at the time) | `instagram/publish.py` | `web/instagram_posting.py` (scheduler thread) | `js/instagram-posting.js`, `sections/review.html` (Instagram card), `css/posting.css` |

**Shared files** (used by many features; change with care and tell the other person):

| File | What it is |
|---|---|
| `app.py` | Starts the server: loads `.env`, imports every `web/` file (that's what registers its routes), runs Flask. |
| `settings.py` | `ROOT` and `JOBS_DIR` (set `JOBS_DIR` in the environment to move the jobs folder, e.g. in tests or the cloud). |
| `web/server.py` | The one Flask `app` every `web/` file adds routes to; cookie/session settings. |
| `web/store.py` | Job state: `JOBS` (in memory) mirrored to `jobs/<id>/job.json`, `LOCK`, `update()`, `update_short()`, `load_job()`, `editable_job()`. |
| `pipeline/ai.py` | `ai_json()`: every AI call (Gemini or OpenAI), with retries and model fallbacks. |
| `web/youtube_sync.py` | `sync_deleted()`: Shorts deleted in YouTube Studio (e.g. a cancelled scheduled one) are forgotten when Shorts & Reels or Scheduled opens (once a minute per creator; only records with a connected `channel`; any YouTube error changes nothing), so they're drafts again. A vlog Pit Crew uploaded that YouTube no longer has (deleted, or removed by YouTube for spam or copyright, sometimes minutes after uploading) gets `vpost` state `removed` (checked in the background when Vlogs opens, `sync_soon()`): its dead link is dropped, the page links to Studio for the reason and offers Upload again. |
| `web/errors.py` | `plain_error()`: one plain sentence for a failed vlog (AI busy, AI limit, video editor stopped...). The raw text goes to `job["error_detail"]` and the terminal, never to the page. |
| `pipeline/ffmpeg.py`, `pipeline/text.py`, `pipeline/constants.py` | FFmpeg (`ffmpeg_exe()`, `run()`, `probe()`), small text helpers, shared numbers. |
| `pipeline/__init__.py`, `youtube/__init__.py`, `instagram/__init__.py` | Only re-export what `web/` uses, so web code can write `pipeline.render_short(...)` / `yt.upload_short(...)` / `ig.post_reel(...)`. |
| `static/index.html` | The page skeleton: lists the CSS and JS files and includes each `sections/*.html` (the `/` route fills them in). |
| `static/js/core.js` | `$()`, `fmt()`, `esc()`, `show(n)` (screens 1 New vlog … 7 Vlogs, 8 Settings; `NAV_FOR` marks the sidebar item) and the shared page state (`job`, `jobId`, `poll`, `count`). |
| `static/css/tokens.css`, `base.css`, `buttons.css`, `fields.css`, `cards.css`, `shell.css` | The look shared by every screen. |
| `static/css/theme.css` | The Pit Crew look on top of everything (loads after every screen's CSS): carbon glass panels, YouTube-red buttons and glow, the checkered eyebrow, the sidebar rail, stage lights on Making, hazard-stripe progress bars, the pit-lane sign-in backdrop. Colours only from `tokens.css` (contrast-checked). Fonts: Unbounded (headings, wordmark), Plus Jakarta Sans (text), JetBrains Mono (numbers, labels). The logo (three rising slanted bars on a red tile: growth and speed. Never a play button or a red P: those copy YouTube's and Pinterest's logos) is inline SVG in `sections/sidebar.html` and `sections/auth.html` (give each copy its own ids). |

**Rules for keeping it modular**

- **A new feature gets new files.** Add the work to a new `pipeline/<feature>.py` (or `youtube/`), its routes to a new
  `web/<feature>.py`, its page code to a new `static/js/<feature>.js` (and CSS/section if needed). Then add **one line**
  each to `app.py` (import the web file) and `static/index.html` (the `<script>`/`<link>`/include). Those one-line
  additions are the only shared edits, and git merges them easily.
- Inside `pipeline/` and `youtube/`, import from the feature file directly (`from pipeline.hooks import hook_fields`),
  never from the package `__init__` (that causes circular imports). `web/` uses the facades (`pipeline.x`, `yt.x`).
- `web/` route functions must have unique names: `gate()` in `web/accounts.py` checks `request.endpoint` against
  `PUBLIC`, which lists function names.
- **The page's JS files share one global scope** and load in the order listed in `index.html` (no modules, no build).
  Code that runs while the page loads may only use things defined in the same or an earlier file; anything called
  later (click handlers, polling) can use any file. `account.js` must stay last: it calls `boot()`.
- Where it lives at runtime: `jobs/<id>/` holds each run (`source.*`, `transcript.json`, `captions_N.ass`,
  `short_N.mp4`, `thumb_N.jpg`, `thumbwork_N/`, `preview.mp4`, `job.json`); `jobs/_transcripts/` the transcript
  cache; `data/` the accounts database and cookie secret. All git-ignored.

## Hard-won gotchas (don't undo these)

1. **Audio is decoded with FFmpeg, not faster-whisper's own decoder.** `load_audio()` pipes 16 kHz mono
   float32 from FFmpeg into `model.transcribe(numpy_array)`. faster-whisper's decoder uses PyAV, and
   PyAV ≥ 15 removed the `metadata_errors` argument it passes ("open() got an unexpected keyword
   argument 'metadata_errors'").
2. **OpenCV is pinned below 5** (`opencv-python-headless>=4.8,<5`). OpenCV 5 dropped
   `cv2.CascadeClassifier`, which the face finder uses. `face_center_x()` also catches any failure and
   returns `None`, which means "crop from the centre", so face finding must never fail a job.
3. **Not every FFmpeg can burn captions.** Some builds (recent Homebrew, Anaconda) ship without libass,
   so the `subtitles` filter doesn't exist and FFmpeg says `No option name near 'captions_1.ass...'`.
   `ffmpeg_exe()` uses the first FFmpeg that lists `subtitles` in `-filters`: `$FFMPEG_PATH`, PATH,
   Homebrew paths, then the complete static binary from the `imageio-ffmpeg` package. Always call
   `ffmpeg_exe()` and never hard-code `"ffmpeg"`. (`ffprobe` still comes from PATH.)
4. **Captions need a real font file.** `prepare_job_fonts()` copies `fonts/*.ttf|otf` into the job folder;
   if there are none it copies a system bold font (Arial Bold on Mac). `caption_font_name()` uses
   `CAPTION_FONT` only if that family is actually present, otherwise the family that is. Static FFmpeg
   builds may have no fontconfig, so a missing font can mean invisible captions.
5. **Gemini models are retired often, and they get busy.** `FALLBACK_MODELS` lists current Flash models,
   newest first; `.env` `GEMINI_MODEL` is tried first. `gemini_error_kind()` sorts errors into
   busy / limit / missing / bad_key / other. Busy (5xx) models are retried in rounds (waits in
   `BUSY_WAITS`), while missing and limited models move on to the next one. As of October 2026, the 2.5
   models are restricted to accounts that already used them. Check
   https://ai.google.dev/gemini-api/docs/models before changing names.
6. **ffprobe call is version-agnostic.** `probe()` uses `-show_streams -show_format` and reads rotation
   from `side_data_list` *or* the old `tags.rotate`; `stream_side_data=` in `-show_entries` breaks on
   FFmpeg 4.x.
7. **Sideways phone videos:** `probe()` swaps width/height when rotation is 90/270.
8. The subtitles filter runs with `cwd=job_dir` and relative paths (`subtitles=captions_N.ass:fontsdir=fonts`)
   to avoid Windows drive-letter escaping problems. Keep it that way.

9. **Transcription is batched, and the language is detected across the whole video.** `transcribe()` uses
   faster-whisper's `BatchedInferencePipeline` (about 2× faster; `WHISPER_BATCH_SIZE=0` turns it off and
   falls back to one-at-a-time). Batched mode guesses the language from too little audio: an English
   vlog with car noise came out as **Welsh**. So `detect_language()` votes over 8 clips spread across
   the video and passes the winner in, but only with `WHISPER_LANGUAGE=auto`: **Pit Crew is English-only for
   now** and transcribes as English by default (a Hinglish vlog was guessed as English and came out as
   invented text; Hindi support was tried with large-v3-turbo + Roman transliteration and dropped).
   `drop_repeats()` keeps any phrase at most twice in a row (Whisper gets stuck over music or noise:
   "It's snowing everywhere" 40 times), and a letter repeated 4+ times is cut to two.
   Batched output comes in ~30-second chunks, so `sentence_segments()` rebuilds sentence-sized lines
   from word timings. Gemini needs those to choose good start points. The model is loaded once per
   process (`whisper_model()`), and the GPU is used automatically when present.

10. **Never download videos from YouTube.** YouTube's API policies forbid apps from downloading or storing
    YouTube audiovisual content, even the creator's own, and breaking that risks the API access posting
    depends on. `fetch_video_info()` reads only public text (Data API with `YOUTUBE_API_KEY`, else oEmbed =
    title only). The video always comes from an upload or a Drive link.
11. **AI calls go through `ai_json()`**, which uses Gemini (`gemini_json()`) or OpenAI (`openai_json()`) depending
    on `AI_PROVIDER`. Both share `ask_models()` (retries busy models, skips retired ones) and parse JSON. Use
    it for any new AI feature instead of calling a client directly, and pass images as `image_part(bytes)`.
    OpenAI's JSON mode only returns objects, so a requested list arrives as `{"items": [...]}`; callers must
    accept a dict wrapping the list (as `pick_moments()` does). OpenAI's reasoning models reject
    `temperature`, so `openai_json()` retries without it. `OPENAI_FALLBACK_MODELS` needs the same care as
    `FALLBACK_MODELS` (check https://platform.openai.com/docs/models).
12. **Thumbnails:** one frame of the Short, chosen by the AI, in one of two looks: **Frame** (default,
    colour-graded) or **Duotone** (two-colour poster in the Short's accent). Cut-out collages were dropped in
    October 2026 after a side-by-side test of 8 styles on real Shorts: uneven cut-outs made some thumbnails
    look bad, and they cost a 180 MB model, 2 GB of memory and seconds per thumbnail.
    - **Plan** (`plan.py`): 12 frames (up to 1920 px wide, grabbed 4 at a time) go to the AI, which returns
      `frame`, `focus` (box_2d `[ymin, xmin, ymax, xmax]`, 0-1000, around what must stay in view, usually the
      face), `line1`, `line2` and `accent`. `clean_plan()` validates everything; a missing frame falls back to
      `plan_without_ai()` (biggest sharp face from the face finder, else the sharpest frame).
      **Thumbnails use Gemini whatever `AI_PROVIDER` says** (`THUMB_AI_PROVIDER`): Gemini is trained on box_2d.
      A provider that fails is skipped by every thumbnail for `REST` (180 s) so the others go straight to the
      next one (Gemini was overloaded for minutes in a real run), then no AI.
    - **Text:** `tidy_lines()` drops words from line1 that the headline already has ("Rice Older? / Older
      Than Me" -> "Rice / Older Than Me"), and the prompt asks for that too. `text_spot()` puts the text above
      the face if it fits, else below it (clear of the bottom 230 px where YouTube draws the title), else on
      the roomier side, smaller. Fonts are bundled in `pipeline/thumbnails/fonts/` (OFL): Anton for the
      headline, DM Serif Display for the small line; Latin only, other scripts use the system bold font.
    - **Crop** (`layout.portrait()`): 9:16 around `focus`, a little tighter than the frame height (`ZOOM`) so
      the face can sit at `FACE_AT`; sharpened when blown up a lot (low-resolution vlogs).
    - **Looks:** `compose()` hands the plan to `looks/<look>.py` (`LOOKS`, `THUMB_LOOK`). The look is saved
      in `plan.json`; a creator switches it on the card (`/api/look/...`, redrawn from `thumbwork_N/`, no AI,
      about a second) and can download the thumbnail there. `upgrade_plan()` reads collage-era plans
      (`face_frame`/`face_box`/`items`), which are redrawn as Frame.
    - **Colours:** `fresh_accent()` gives each Short of a vlog a different accent (it reads the other
      `thumbwork_*/plan.json`), chosen under a lock because thumbnails are made side by side.
    - **Speed:** `make_shorts` starts each thumbnail as soon as its Short is edited, `THUMB_WORKERS` (3) at
      once; nearly all of a thumbnail's time is the AI call. Drawing takes ~0.15 s.
    - **Never wait forever on the AI:** every request has a timeout (`ai.TIMEOUT`, 180 s; thumbnails 60 s, no
      busy waits), and thumbnail planning has an overall `AI_DEADLINE` (120 s) after which `plan_without_ai()` is
      used. Without these, one Gemini request that never answered left a job stuck on "Thumbnail 2 of 6".
    Output stays under YouTube's 2 MB thumbnail limit. `THUMB_STYLE=simple` (or a failure) uses `simple.py`.
    - **Shorts feed thumbnail:** the API can't set it (thumbnails.set only covers search, home and
      subscriptions, and needs a phone-verified channel: youtube.com/verify). So `pipeline/cover.py` puts the
      thumbnail in as the first 0.2 s (6 frames) when uploading (`web/posting.upload_file()`) and for the
      Save button (`/media/...?cover=1`); the creator picks that frame in the YouTube app (any channel), or
      uses Download thumbnail + Open in Studio (Partner Program). The cover clip is encoded with the Short's
      own settings and joined without re-encoding (~1 s); if the decode check finds a bad join, it re-encodes.
      Measured: audio and video stay within 0.3 ms. The Short in the job stays clean (Review plays it
      without the flash; upload records keep its name), and `cover_<short>_<thumb>.mp4` is cached.
      `COVER_FRAME=0` turns it off.
    - **Links on Shorts:** each description (`web/posting.short_description()`) has the hook, "Watch the full
      video: <vlog link>", "More from @handle" (the vlog's channel, else the uploading channel) and hashtags.
      Links in Shorts descriptions can't be tapped (YouTube, since Aug 2023); @mentions can. The tappable
      "Related video" and the Shorts-feed thumbnail can't be set through the API, so the Posted page lists
      them as manual Studio steps.

13. **Hooks must be true.** Each Short has `hooks` (curiosity / bold / story, plus "custom" if the creator typed
    one), the chosen `hook`, `hook_style` and `hook_mode` ("text" or "none" = no banner, the original audio opens
    it). Every prompt carries `HOOK_RULE` (no invented facts), and `hook_fields()` drops any hook with a number
    that isn't said in the moment ("I lost $2,000" from a clip that never says it). Keep both when changing prompts.
    Applying a hook can also redraw the thumbnail text (`hook_to_lines()` → `retext_thumbnail()`), which reuses
    the thumbnail's saved `thumbwork_N/` frames and `plan.json` (no AI, no new frames).
14. **No emoji in burned-in text.** The caption and thumbnail fonts have no emoji, so they'd show as empty boxes;
    `without_emoji()` strips them in `ass_escape()` and the thumbnail drawers. Titles/descriptions keep them.
15. **YouTube sign-in redirects to `/api/youtube/callback` and must match the OAuth client exactly.** Locally that's
    `http://localhost:8000/...` (not `127.0.0.1`); in the cloud set `YOUTUBE_REDIRECT_URI`. Never go back to
    `InstalledAppFlow.run_local_server()`: it opens a browser on the server and can't work in the cloud. Scopes are
    the single `youtube` scope (upload, channel name, reschedule, title update, delete for Replace); a saved token
    missing it counts as signed out. Replacing an edited Short uploads the new one first, then deletes the old one,
    and is refused once the Short is public (`yt.is_live`). Upload records store `video`, the file that went up, so
    an edit is detected by comparing it with the Short's current `video`.
    The waiting sign-in (state + PKCE verifier + purpose) lives in the user's session cookie, so a callback only
    finishes a sign-in the same browser started.
16. **Accounts and ownership.** Every `/api` and `/media` route needs a signed-in user (`gate()` in `web/accounts.py`;
    only names in `PUBLIC` are open), and any route with a `job_id` checks `job["owner"]` there, so a new job route
    is protected automatically. Background threads have no request, so pass the user id in (as `do_upload` does).
    Google sign-in ("login") asks only `openid email profile` (no cap, no warning); Connect YouTube is separate.
    Users are matched by Google `sub`. Google sign-in with an email that already has an account (not linked to that
    Google account) is refused with "Email already exists" (`EMAIL_EXISTS`), shown in red on the sign-in screen
    (`login_problem_page()` puts it in the session; `/api/me` hands it to the page once). Accounts are never joined
    by email. **Forgot password** (`web/password_reset.py`, `accounts/mail.py`): a one-time link `APP_URL/#reset=<token>`
    (only its SHA-256 is stored in `password_resets`, 1 hour), emailed over SMTP in a background thread (no SMTP
    settings = the link is printed in the terminal); the reply is the same whether or not the account exists. Using
    it sets the password, marks the email verified and bumps `session_version` (ends every old session, which
    also stops pre-account hijacking: someone signing up with another person's email first). In the cloud set
    `APP_URL`: never build email links from the request's Host. POSTs from another Origin get 403.
    Tests must set the `DATABASE_PATH` and `JOBS_DIR` environment settings to temporary paths before importing `app`:
    a test once wrote to the real jobs.
    The login throttle keys on `request.remote_addr`; behind a cloud proxy, use the real client IP (ProxyFix).
17. **Analytics needs a second Google scope.** `youtube` is required; `yt-analytics.readonly` (`ANALYTICS_SCOPE`) is
    asked on connect but optional. Without it (or without "YouTube Analytics API" enabled in Google Cloud),
    `youtube/analytics.py` falls back to live counts of Pit Crew's Shorts and adds `notes=["reconnect"]`, and the page
    shows "Connect again". Shorts are filtered with `creatorContentType==shorts` (camelCase: `shorts`, `videoOnDemand`; the UPPER_CASE names in Google's docs get HTTP 400, checked on a real channel); numbers lag ~2 days. Results are
    cached 10 minutes per channel. One Short's window (`short_detail`) is its whole life on its own channel (`?channel=`),
    with YouTube's **live** views/likes/comments (what Studio shows; Analytics lags ~2 days). First-week views use the live
    count until the week + delay is over, so new clips never show a false 0. Count axes use whole-number steps (`countMax`). Charts: one axis, colours from `css/analytics.css` tokens (validated), text never in
    series colours, a Table button on every chart.
18. **Open in Studio goes through Google sign-in** (`studioLink()` in `js/core.js`:
    `accounts.google.com/ServiceLogin?service=youtube&continue=<studio link>`), so a signed-out creator lands on the
    Short after signing in instead of on Studio's home page.
19. **Instagram (Instagram API with Instagram Login, no Facebook Page).** Only professional accounts (Business or
    Creator) can be posted to; `account_type` is checked on connect and the page shows the switch steps.
    The 60-day token is refreshed when fewer than 10 days are left (`instagram/connection.load`). **Instagram downloads
    each Reel from Pit Crew**: the container gets a `video_url`, a signed link that expires (`public_video_url()` ->
    `/ig-video/<token>.mp4`, public in `PUBLIC`, one file of one job), then it's polled until `FINISHED`, then
    `media_publish`. Never go back to *resumable upload* (bytes to `rupload.facebook.com`): it only works for apps on
    Facebook Login for Business; with Instagram Login, Instagram answers "The parameter video_url is required" (a real
    Reel failed this way in Oct 2026). So Pit Crew must be reachable over https when a Reel goes out: `PUBLIC_URL`, else
    the `INSTAGRAM_REDIRECT_URI` host (locally the tunnel, which must then be running), else `APP_URL`. `thumb_offset` points at the cover frame
    (`pipeline/cover.py`). Instagram has **no scheduling for apps**: `web/instagram_posting.py` keeps
    `job["ig_posts"]` and a daemon thread posts due Reels (also ones that came due while Pit Crew was off). A Reel left
    in `posting` by a crash becomes `check`, never re-posted on its own. 100 API posts per account per 24 h.
    In the cloud the scheduler (like the vlog queue, `web/job_queue.py`, and unfinished uploads in `jobs/_uploads`) must run in exactly one process with threads (no gunicorn `--preload`/forking: threads started at import don't survive a fork, and vlogs would wait forever; any proxy in front must accept request bodies of at least 8 MB, the upload pieces) (or move to a job queue). The redirect address is
    `INSTAGRAM_REDIRECT_URI` (Meta may refuse plain `http://localhost`; use an https tunnel then).
20. **Several channels and Instagram accounts per creator.** `connections` in `accounts/db.py` (platform youtube /
    instagram, `account_id` = YouTube channel id / Instagram user id, token, profile, `active`). One per platform is
    active: it's where *new* posts go, and Analytics shows it. Connecting adds a connection (or updates the same
    one) and makes it active; Switch just changes `active` (no new sign-in); Disconnect drops one and the newest other
    becomes active. Pit Crew sign-out leaves connections alone (planned Reels must still go out).
    **Never act on the active account for something already planned or posted.** Upload/schedule routes take the
    `channel` / `ig_id` the page showed (another tab may have switched); upload records keep `channel` and each
    `ig_posts` entry keeps `ig_id` + `username`; reschedule, Replace, the Scheduled page's live state and the
    Instagram scheduler use those. Pass `channel=` / `ig_id=` to `yt.get_service()` / `ig.post_reel()`.
    Analytics and Instagram insights caches are keyed per channel/account. Rows moved from the old one-per-user
    tables (`PRAGMA user_version` 0 → 1; the old tables stay, unused) get their YouTube channel id on first
    `yt.account()` (`_fill_channel`); Reels planned before this get the first-connected account (`_stamp_account`).
    "Add account" for Instagram sends `force_reauth=true`, so Instagram asks who to log in as.
21. **Storage is deleted on a timer (`web/retention.py`, checked every 15 minutes).** A vlog's video: `KEEP_ORIGINAL_HOURS`
    (72) after `job["last_edit_at"]`; a draft (on neither platform, nor planned): `KEEP_DRAFT_DAYS` (30) after the Short's
    `edited_at`; a posted Short's video file: `KEEP_POSTED_DAYS` (30) after it went out everywhere it was planned (then
    `file_deleted_at`, Download points at Studio); a saved transcript (`jobs/_transcripts`): `KEEP_TRANSCRIPT_DAYS` (30) after it was made
    (`sweep_transcripts()`). 0 = keep forever. Every `update_short()` counts as an edit (stamps
    both clocks), so route Short changes through it. Warnings a day before: on the card (`video_expires` / `expires` in
    the APIs) and by email (`mail.notify`, printed when SMTP isn't set). Nothing is touched while a vlog is being made,
    remade or posted, or while a Reel is still waiting. `remove_video()` (`web/vlogs.py`) is shared with the 🗑 button;
    after it, the editor locks Try again / hooks / Add a Short (`job.video_deleted_at`). A vlog that stopped keeps its video
    `KEEP_ORIGINAL_HOURS` after it stopped (`last_edit_at`, for Try again), then it's deleted (`_sweep_stopped`), or the whole vlog
    if it made nothing to keep (never one prepared for YouTube: `_empty_stop()` in `web/vlogs.py`). `RETENTION_OFF=1` stops the
    timer (tests). In the cloud this becomes a scheduled job.
22b. **Analytics reports YouTube refuses are left out, never an error.** Every extra report goes through `_try()`;
    `engagedViews` is added with `_with_engaged()` (falls back without it); a `creatorContentType==X` filter that a report
    refuses (HTTP 400) is retried with creatorContentType as a dimension (`_report_by_type(kind)`; YouTube refuses
    `video,creatorContentType`, so video lists rely on the filter). Real-channel facts (_test/an_diag*.py, Oct 2026):
    `subscribedStatus` answers HTTP 500 for every metric on some channels, so `_subscribed()` returns None and asks that channel again only after `SUB_RETRY` (24 h); the Audience tab shows the card only when it comes back; "All time" starts at the channel's creation day
    (`channel_start()`), never 2005 (thousands of empty days made reports take 10-35 s). Google's client
    (httplib2) is not thread-safe: thread pools use `_per_thread()` clients, and every client has a 40 s timeout
    (`_http()`). Apps can't read
    impressions/CTR, realtime, unique or returning viewers, "when your viewers are on YouTube" or Shorts viewed vs swiped
    away: don't promise them. Instagram account insights: at most 30 days per request,
    kept 90 days, demographics need 100+ followers, `impressions` is retired (use `views`). `account_insights(days | start, end)`
    asks any window in the last 90 days in pieces of up to 30 days (`ig_window()`; older dates: `note` "cut" / "old") and adds
    up the counts; reach and accounts engaged count each account once per piece, so over 30 days they're None (the page says
    so and shows views by followers/non-followers instead). **Likes/comments: All time = YouTube's live counts; a date range
    can only come from Analytics**, which can count a comment differently (real channel: live 2, Analytics 1) and is ~2 days
    behind; the page says which. Compare (calendar) starts on the earliest ticked video's posting day, not the range start
    (zero-view days are rows too). Column charts say what a bar counts (`colsHTML(rows, {unit})`). Charts: one colour per video,
    fixed order `--s1..--s8`, kept while ticked (colour follows the video, not its rank); donuts fold past 5 slices into Other.
    YouTube is `--c-yt` (blue) and Instagram `--c-ig` (orange) everywhere both appear.
22e. **Upload records of Shorts posted straight away have `"when": None`** (`when` is the scheduled time); `uploaded_at` is
    saved since Oct 2026, and for older records `fill_dates()` (web/analytics_clips.py, used by both Videos sections) uses YouTube's published date, so dates, "Newest" and the
    follows window work.
22c. **Instagram can't say which Reel brought a follower.** "New followers" for a Reel is the account's
    `follows_and_unfollows` (breakdown `follow_type`) in the 48 h after it went out (`follows_after()`; `complete` false
    until those 48 h are over; None for Reels older than 88 days, past Instagram's 90-day insight window). The page says so.
22d. **Pit Crew's read: one per creator per day, and it only quotes real numbers.** The AI is asked at most once a day per
    creator (cache key: user, YouTube channel, Instagram on/off, date), whatever range or platform the page shows: it reads
    fixed numbers (`daily_facts()`: Shorts all time, Shorts last 28 days, Instagram's last 30 days, each clip since posted;
    every key names its time span) and answers a headline for both apps, one for YouTube only, one for Instagram only, and
    4-6 tagged tips (`_fill()`: at least 2 per app); the page picks by platform. Never key it on the range again (that asked
    the AI on every range change). `_honest()` drops any tip whose text has a number not in the facts (±1, titles included;
    counts 0-10 allowed) and swaps a bad headline for `rules()`'s. Gemini first then OpenAI, 25 s per model, no busy waits.
    **The page never waits for the AI**: `read()` answers `rules()` at once with `pending: true` and asks the AI in a
    background thread (one per key); the page asks again every 6 s (a real read took 35-70 s). A failed AI read is retried
    after 10 min. A 7-day read once called a clip "this week's winner" from its lifetime views: keep the spans labelled.
22. **Compare clips by their first 7 days, never by lifetime totals** (older clips have had longer). YouTube:
    `first_week_views()` asks each Short's own channel (`video==id`, first 7 days; final after 9 days because of the
    ~2-day delay; cached). Instagram only gives running totals, so `snapshot_reels()` saves each Pit Crew Reel's numbers
    once a day (`reel_snapshots`, also every 6 h in the background): first week = the saved day 7–9 days after posting,
    else "still counting" (< 7 days) or "not enough history" (saving began later). "What's working" (`takeaways()`) only
    compares groups of 2+ clips, needs 4+ finished clips per platform and a 20% difference, and says what it's based on.

23. **A vlog upload is a job with `kind: "vlog"`** (`web/vlog_upload.py`): `VLOG_STAGES` while it's prepared, then
    `status: "ready"` with `job["vdraft"]` (what the creator edits) and, once sent, `job["vpost"]` (uploading → done /
    error) and `job["vlog"]` (video id, URL, channel), so its Shorts link back to it. It has no `count` until Shorts are
    asked for; `/api/vlogs` calls that `prep`. The page decides from that: `prep` opens the upload page (screen 10),
    anything else the usual progress / Shorts & Reels (`progress.js` `tick()` hands a `prep` job to `openVlogUpload`).
    `/shorts` turns it into an ordinary Shorts job on the same video and transcript (no second upload, no second
    transcription), only while the video is kept (`KEEP_ORIGINAL_HOURS`, 72) and before it has any Shorts. A
    `vpost` left "uploading" by a restart becomes an error (`load_job`), and retention never deletes a video mid-upload.

24. **The server (deploy/, tested on a fresh Ubuntu 24.04 with systemd, Oct 2026).** One process: `serve.py` (Waitress,
    threads) behind Caddy (https, `/static` served directly with `Cache-Control: no-cache`, security headers, no access log).
    The service runs as `pitcrew` with `ProtectSystem=strict`: **the code folder is read-only; anything Pit Crew writes must
    live under `/srv/pitcrew`** (`DATABASE_PATH`, `JOBS_DIR`, `HF_HOME` for the speech model, `HOME`). A new setting whose
    laptop default in `.env.example` is wrong for a server goes in setup.sh's first-run `--force` list (a non-empty example
    value is otherwise kept: `JOB_SLOTS=2` once stayed on a 2-core server). `update.sh` runs from a temp copy of itself,
    refuses if code on the server was edited, compiles before restarting (a syntax error never takes the site down),
    and on any later failure moves the **branch** back too (`checkout -B`: a rollback that only moved HEAD once left
    `main` on the broken commit, and the next update "rolled back" to it). In deploy scripts never pipe a long output
    into `grep -q` under `set -o pipefail` (grep exits early, the writer gets SIGPIPE, the check fails: it stopped setup
    at "FFmpeg can't add captions"). Oracle's Ubuntu images block 80/443 in iptables as well as in the cloud firewall.
25. **Caption fonts by full name.** `caption_font_name()` returns `CAPTION_FONT` when it matches a font's family *or full
    name*, else the full name ("Montserrat ExtraBold") of the font in the job's fonts folder. On Linux with all Montserrat
    weights installed (`fonts-montserrat`), asking libass for the family "Montserrat" gave Regular; the full name gives the
    exact file. setup.sh copies Montserrat ExtraBold into `fonts/`.
26. **The privacy policy is a promise about the code.** `static/legal/privacy.html` says what is collected, who gets it and
    how long it's kept; retention times come from web/retention.py's settings (so they can't drift), AI providers from
    the keys in `.env`. When you collect something new, send data to a new service, store something longer, or change a
    permission (scope), update the policy and `UPDATED` in `web/legal.py` in the same pull request.
27. **YouTube's stored-data rules (Developer Policies III.E.4, III.D.2) are kept by `web/youtube_upkeep.py`, once a day.**
    Connected channels are re-checked every `CHECK_DAYS` (7; the rule is 30): sign-in refreshed (a removal in Google's
    settings shows up as invalid_grant and drops the connection), name/handle/picture re-read (`yt.recheck()`, stamps
    `profile.checked_at`), and every posted video checked (`sync_deleted(force=True)`). A channel still in records but no
    longer connected goes into `gone_channels` (accounts/db.py) and is forgotten `GONE_DAYS` (5) later: its upload records
    (the Shorts are drafts again), a vlog's `video_id`/link/channel, its numbers in memory; reconnecting before then keeps
    everything, and a vlog being made or posted is left for the next day (the channel stays listed). The rules allow 7
    days after a disconnect, 30 after a Google-settings removal; the privacy and data-deletion pages promise 7 and 14.
    A vlog's details read from its YouTube link (`job["vlog"]`, `fetched_at`) are read again after `LINK_DAYS` (30), or
    deleted when YouTube says it can't find the video (other errors: retried up to a week, then deleted); the title stays.
    Numbers in memory (`youtube/stored_data.py`): expired cache entries dropped, first-week views at most 30 days old.
    **Anything new you keep from a YouTube API answer needs a refresh-or-delete path here** (and a line in the policy).
28. **YouTube's upload limit is per Google Cloud project, and Pit Crew is one project** (`YOUTUBE_DAILY_UPLOADS`, 100
    uploads a day, reset at midnight Pacific; a scheduled Short counts the day it's sent, not the day it goes public).
    Never add more projects to get more: it's against YouTube's API terms; the audit raises the number. Every upload goes
    through `youtube_quota.take()` first (Shorts, vlogs, Replace) and `give_back()` if it didn't reach YouTube; YouTube's
    own `quotaExceeded` marks the day used up (`youtube_says_used_up`). Nothing over the limit fails: Shorts go into
    `job["yt_waiting"]` with their chosen times, a vlog into vpost state `waiting`; the `youtube-waiting` thread sends
    them after the reset, oldest first (a time that passed meanwhile = public at once). Only Replace says "press again after
    midnight". Settings: `YOUTUBE_OPEN_SHARE` (60), `YOUTUBE_RESERVE` (5).
29. **Free Gemini may train on what it's sent, so nothing from YouTube's API goes to it** (Google's Limited Use rule).
    `pipeline/ai.py` `youtube_data_ok()` is true only for OpenAI or `GEMINI_PAID=1`. Until then a vlog's title and
    description read from its YouTube link stay out of the prompts (`vlog_context_block()`, the thumbnail plan) and
    Pit Crew's read on Analytics is written by the rules (`analytics_coach._providers()`). What the creator typed is fine.
    Any new prompt with YouTube data must check `youtube_data_ok()`.

## Conventions

- Keep it **dependency-light and single-file-per-concern**. No frontend framework. The only database is
  `accounts/db.py` (SQLite from the standard library, accounts and YouTube connections); jobs are still `job.json`
  files. Both are local files for now; in the cloud they need lasting storage (a database server and file storage).
- User-facing errors: raise `RuntimeError("plain sentence about what happened. What to do.")`. They are
  shown in the UI as-is. Log technical detail with `print()` / `traceback.print_exc()` in the terminal.
- Progress: long steps call `progress(pct, "Short message")`; the UI shows the message.
- Settings belong in `.env` (document every new one in `.env.example` and the README), read with
  `os.getenv(NAME, default)`.
- Never commit secrets: `.env`, `client_secret.json`, `token.json` and `data/` are git-ignored. `data/clipline.db`
  holds every user's YouTube connection (can post to real channels; the tokens are encrypted with `TOKEN_KEY`, else
  `data/token_key`: `accounts/token_box.py`, never store a token without `seal()`) and `data/secret_key` signs sign-in cookies.
  The login and sign-up limits key on `request.remote_addr`: in the cloud set `TRUST_PROXY` (`web/server.py`, ProxyFix).
- Don't commit media. `jobs/`, `_test/` and font files are ignored (fonts have their own licences).
- After changing Python files, at minimum run: `python -m compileall -q app.py settings.py pipeline youtube accounts web`
  and start the app once (an import error in any `web/` file stops it from starting).

## Testing without burning API quota

**Automated tests** (standard-library `unittest`, no internet, no keys, no quota; the same on a laptop and the server):

| Suite | Run | What | Time |
|---|---|---|---|
| Fast (unit + combined flows) | `python -m unittest discover -s tests -t .` | every feature through the real routes: accounts, email links, deleting an account, uploads in pieces, the queue, Stop / Try again, restarts, limits, YouTube and Instagram posting, editing, vlog upload, analytics (a strict fake of YouTube Analytics), retention, pages, security, YouTube's data rules, Meta's callbacks; whole creator journeys (`test_flows.py`) | ~45 s |
| System | `python -m unittest discover -s tests/system -t . -p "system_*.py"` | the real FFmpeg pipeline (vertical Shorts with sound, captions burned in with the highlight, hook banner, designed thumbnails, look switch, cover frame, preview, vlog thumbnail) and the real server process over HTTP (20 MB upload, request limits, killed mid-vlog and started again) | ~2 min |
| A/B | `python -m tests.ab.compare [encoder captions looks slots whisper]` | our options side by side: speed, size, quality (SSIM), thumbnail text contrast, JOB_SLOTS 1 vs 2, speech settings where the model exists | ~2 min |
| Stress | `python -m tests.stress.stress [--users 25 --seconds 60 --vlogs 1]` | a copy of Pit Crew under many people at once: p50/p95 per request, errors, every vlog finished, memory, threads | 1-4 min |
| Live check | `python -m tests.stress.stress live --url https://<domain> --email <test account>` | gentle and read-only on the real site; stops itself on errors or slow answers | ≤ 5 min |

On the server: `sudo bash /opt/pitcrew/app/deploy/test.sh [fast|system|ab|stress|live|all]` (as the `pitcrew` user, low
priority, throwaway folders). `deploy/update.sh` runs the fast suite before every restart: a failing test keeps the
old version running.

How they stay safe and repeatable:
- **`tests/_env.py` comes first in every test file.** It switches off `load_dotenv` and removes every setting `.env.example`
  lists, so the server's keys, AI provider, limits and storage times can't change a result or reach a real service, then
  points the database, jobs folder and invite list at a temporary folder (removed at exit) and sets `RETENTION_OFF=1`.
  A new setting goes in `.env.example`, and is then cleared for tests automatically.
- **`tests/fakes.py` is the outside world:** the real `ai_json()` runs against a fake `google.genai.Client` that answers by
  prompt (`AI.fail(code, msg)` makes it fail like Gemini); the youtube facade functions and `youtube.analytics._services`
  are an in-memory channel and a strict Analytics fake (gotcha 22b rules); `instagram.http.call` is an in-memory account;
  email goes to `OUTBOX`. Fake users are confirmed unless `new_user(verified=False)`. `fast()` swaps transcription, editing and thumbnails for quick stand-ins; the system suite keeps
  the real ones (`PITCREW_REAL_MEDIA=1`) and fakes only the AI and the speech model. Test videos are generated with FFmpeg
  and cached per user in the temp folder.
- A new prompt needs a branch in `FakeAI.kind()`; a new outside call needs a fake here, or tests will reach the internet.
- `test_page_scripts.py` runs `node --check` on every page script (Python tests can't see a JavaScript syntax error,
  which stops the whole page) and checks the ids they look up exist.
- Add a test with every fix: the suites found the Instagram "Same as YouTube" refusal and the upload clean-up race.

Manual checks that work well:

- **Short clip:** `ffmpeg -ss 300 -i long.mp4 -t 90 -c copy test90.mp4` and upload that in the UI.
- **Skip Gemini:** monkeypatch `google.genai.Client` with a fake whose `models.generate_content()`
  returns `types.SimpleNamespace(text='[{"start": 17.5, "end": 45.8, "hook": "...", "title": "...",
  "thumb_line1": "...", "thumb_line2": "...", "why": "...", "hashtags": ["a","b","c"]}]')`, then call
  `pipeline.pick_moments(transcript, n)` or drive the whole app with `app.app.test_client()`.
- **Encoder speed:** `X264_PRESET` defaults to `veryfast` (CRF 18): measured 2.5x faster than `medium` with a
  slightly smaller file and SSIM 0.994 against it (no visible difference). `ultrafast` and `WHISPER_MODEL=base`
  speed up testing further.
- **Look at the output:** grab frames with `ffmpeg -ss 1.2 -i jobs/<id>/short_1.mp4 -frames:v 1 f.jpg`
  and check that the captions, yellow word highlight, hook banner and face crop are all present.

Still worth automated tests: retention (`sweep_job()` with fake times), the vlog queue, `ai_json()` retries with a fake
client, the API routes through `app.app.test_client()`.

## Working together (two people)

- **Branches: exactly three, no new ones.** Saumya always works on `saumya`, Nesh always on `nesh`. `main`
  should always run. Push your branch, open a pull request into `main`, and let the other person look before
  merging. Never merge into `main` locally or push to it directly: changes reach `main` only through a pull
  request that Saumya or Nesh merges on GitHub. Never create other branches, and never delete these three.
- **No AI attribution in git.** Commits and pull requests are authored by Saumya or Nesh only: never add
  `Co-Authored-By: Claude ...`, `Claude-Session: ...`, "Generated with Claude Code" or similar lines to
  commit messages or PR descriptions. (This repo's history was cleaned of them in October 2026.)
- Before you start, bring your branch level with `main` (after the other person's PRs are merged):
  `git checkout saumya` (or `nesh`), `git fetch origin`, `git merge origin/main`, `git push`.
- If you change `requirements.txt`, say so in the PR. The other person's start script will reinstall
  automatically on the next launch.
- Each person keeps their own `.env` (Gemini/OpenAI keys), `client_secret.json` and `data/` (accounts and YouTube
  connections). Never share these through git.
- Work on different features = different files (see "Where things live"). If you both need a shared file, keep the
  change small and say so in the PR.

## Ideas / known limits

- Transcription speed: before batching, `WHISPER_MODEL=small` on CPU took about 9 min for a 40-min vlog on an
  M-series Mac; batching roughly halves that. A GPU cloud server is much faster still.
- Low-resolution sources (e.g. 640×360 YouTube downloads) give soft Shorts; use original exports.
- New YouTube API projects can only upload as **private** until Google's audit is passed (see README).
- Custom thumbnails for Shorts only work on channels YouTube has enabled them for.
