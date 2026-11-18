# CLAUDE.md

Read before changing code. Dense on purpose: every line is a rule or a fact that cost a bug. Gotcha numbers are cited in
code comments: keep them stable, add new ones at the end.

**Names.** The product is **Pit Crew** (was Clipline): use it in everything people see; internal names keep `clipline`
(repo, `data/clipline.db`, `clipline-theme`, `clipline_ids`, postMessage `{clipline:...}`). People see **"Video", never
"Vlog"**; the code keeps `vlog` (`/api/vlogs`, `#vlogs`, `kind:"vlog"`, `vpost`, `web/vlog_*.py`), and so does this file.

## Top priorities (November 2026)

- **Saumya:** Analytics page easy to navigate; Instagram pipeline (posting + analytics); meaningful Undo / Redo.
- **Nesh:** the other advanced editing features (test and improve the existing ones); transcript / title / description
  from a YouTube URL without the YouTube API; production deploy.
- **Both:** app latency (gotcha 37).

## What Pit Crew is

A web app (live on GCP, `deploy/`) that turns one long vlog into vertical Shorts / Reels: transcribe (faster-whisper) →
pick moments (Gemini, or OpenAI with `AI_PROVIDER=openai`) → cut, reframe 9:16 around the face, burn word-by-word
captions (FFmpeg + libass) → thumbnail (Pillow) → review → post / schedule (YouTube Data API v3, Instagram API).
Users are **creators, not developers**: every error they can see is plain English and says what to do next.

**Cloud rules (every change):** no code paths for one kind of computer (no Apple-only / GPU-brand engines; portable
libraries that adapt); tune speed with settings (`WHISPER_DEVICE`, `WHISPER_BATCH_SIZE`, `WHISPER_THREADS`,
`X264_PRESET`...), never `if mac:`; `pipeline/` has no web or UI code (it's the future worker: pass everything in);
treat local files as temporary (`jobs/` → cloud storage, `JOBS` → a database). `start-mac.command` /
`start-windows.bat` are local conveniences. (An Apple-GPU MLX transcriber was set aside: `_backups/`.)

**The editor** (screen 12, `js/editor.js`): tools Details, AI Edit (gotcha 30), Captions (33), Reframe (34), Trim + the
timeline (31), Text & Overlays (text only) work; Audio, Thumbnail, Effects are marked Soon (`ED_TOOLS`). Only in a
draft's editor (Drafts › Edit), never on Shorts & Reels (those went out). Next: Effects & Enhancements (filters,
transitions, call to action, stickers, B-roll, images, music, speed, audio effects). Rules for new editor work:
- React lives only in `editor-app/` (Twick's timeline), built to `static/editor-app/` (`timeline.js`, `style.css`,
  `LICENSES.txt`) and **committed** (the server has no Node): `cd editor-app && npm ci --ignore-scripts && npm run
  build`, commit both. Every other page is plain JS, no build.
- The render stays on the server with FFmpeg (the browser only previews). New work: `pipeline/<feature>.py` +
  `web/<feature>.py`.
- Edits that need the vlog's video (Trim past the moment, B-roll, Try again) only work while it's kept (gotcha 21):
  say so on the tool. Hooks stay true (13); no YouTube data to free Gemini (29); each new prompt needs a branch in
  `tests/fakes.py` `FakeAI.kind()`. Music: royalty-free only. B-roll: only from the creator's own vlog.
- **Twick licence** ("Sustainable Use License", `static/editor-app/LICENSES.txt`): fine inside Pit Crew; a commercial
  licence is needed for "substantial revenue from the Software's functionality" (undefined): get it in writing from
  contact@kifferai.com before launch. Keep its notices, never its name / logo. Check MediaPipe's licence before use.
  New services or stored data go in the privacy policy (26).

## Run it

```bash
cp .env.example .env           # paste a Gemini key into GEMINI_API_KEY
bash start-mac.command         # or start-windows.bat: makes .venv, installs, runs app.py, opens localhost:8000
```
The start scripts reinstall when `requirements.txt` differs from `.venv/installed-requirements.txt` (so editing it ships
a dependency fix). Python 3.10+, FFmpeg / ffprobe on PATH. Manual: `.venv/bin/python app.py`. Server: `serve.py`
(Waitress) behind Caddy, `deploy/setup.sh` / `deploy/update.sh`, `LAUNCH.md`, `GCP-PRODUCTION.md` (gotcha 24).

## Where things live: one feature per file

So two people rarely touch the same file. A feature has up to three same-named files: work in `pipeline/` (or
`youtube/`, `instagram/`, `accounts/`), routes in `web/`, page in `static/js/` (+ `css/`, `sections/`).
Format: **feature**: work | routes | page — notes.

*Accounts and pages*
- **Accounts**, `gate()`: `accounts/db.py` | `web/accounts.py` | `js/account.js`, `sections/auth.html` — gotcha 16.
- **Forgot password**: `accounts/db.py` (`password_resets`), `accounts/mail.py` | `web/password_reset.py` | `js/password-reset.js`.
- **Confirm email** (`#verify=<token>`, 48 h; nothing works until confirmed: `gate()` → 403 `verify:true` except
  `UNCONFIRMED_OK`; Resend, Change email `POST /api/auth/email`; Google sign-ins count as confirmed): `accounts/db.py`
  | `web/verify_email.py` | `js/verify-email.js` (`showVerify`).
- **Delete account** (type the email; refused while something is made / posted; YouTube revoked): `db.delete_user` |
  `web/delete_account.py` | `js/delete-account.js`.
- **Private beta** (`INVITE_ONLY=1`, `INVITES_FILE`, read on every sign-up): `web/invites.py`.
- **Limits** (`MAX_VLOG_MINUTES`, `MONTHLY_VLOG_MINUTES` per UTC month; checked at `/api/upload/new`, at start
  `upload_problem()`, in the job `charge()` once via `job["charged"]`; 5 sign-ups / IP / hour): `db` (`usage`) |
  `web/allowance.py` | `js/allowance.js`.
- **Emails when away** (Shorts ready, stopped, posting failed; confirmed emails only, not while watching; links use `APP_URL`): `web/notices.py`.
- **Help** (`SUPPORT_EMAIL`: sidebar Help, "Get help" + the vlog id): `web/pages.py` (`/api/config`) | `js/help.js`.
- **Public pages** (`/welcome`, `/privacy`, `/terms`, `/data-deletion`, filled from settings): `web/legal.py` (`UPDATED`,
  `EXTRAS`) | `static/legal/`. Plain `/` always goes to `/welcome` (`boot()` in `js/account.js`), so every way into the
  app ends in a `#` (`/#vlogs`, `/#signin`, `/#signup`).
- **Meta callbacks** (`/api/instagram/deauthorize`, `/data-deletion`, `signed_request` with `INSTAGRAM_APP_SECRET`):
  `web/instagram_deletion.py`, `db` (`deletion_requests`).
- **Sidebar** (+ Create; Videos, Shorts & Reels, Drafts, Scheduled, Analytics; channels with View your channel /
  profile; Settings, Appearance; logo → `/welcome`; making + review pages mark Drafts via `NAV_FOR`):
  `sections/sidebar.html`, `js/nav.js`, `css/shell.css`. Under 1024 px it's the top bar: it must fit every width with
  Help shown (under 400 px tighter, buttons ≥ 32 px; pills hidden ≤ 640 px; logo hidden ≤ 360 px).
- **Progress card** (`#jobsNow`: vlog sent / made / paused, "Shorts ready"; its checks also refresh Videos and Drafts):
  `web/vlogs.py` | `js/jobs-now.js`, `css/jobs-now.css`. Under 1024 px it floats at the bottom: `--jn-space` (its
  height, from a ResizeObserver) pads `.main` and lifts `.dock`, `.cl-dock`, `.toast`.
- **Settings** | `js/settings.js`. **⋮ menus**: `js/card-menu.js` (`cardMenu`, `position:fixed`, before `vlogs.js`).
  **Tabs** (Drafts, Scheduled): `js/page-tabs.js` (`pageTabs()`). **Date / time picker** (every "when"; keeps a hidden
  `datetime-local`; choices `custom` / `now`, server still takes old `d18` / `d12` / `two`): `js/when-picker.js`.

*Vlogs and Shorts*
- **Sending the video** (resumable 8 MB pieces, `MAX_UPLOAD_GB`, room check with spare, unfinished gone after 24 h;
  start routes take `upload=<id>` via `take_upload()`): `web/video_upload.py` | `js/video-upload.js` (`sendVideo()`).
- **Setup / Making Shorts** (count 1-10 `#countPick`, style, must-have moments, file / links; lands on Drafts
  `#drafts/shorts/<id>` with loading cards): `youtube/links.py`, all of `pipeline/` | `web/make_shorts.py` (`start`,
  `safe()`), `web/times.py` | `js/setup-form.js`, `js/start.js`, `js/progress.js`, `sections/setup.html`, `making.html`.
- **Vlog queue** (`JOB_SLOTS`, `JOB_SLOTS_PER_CREATOR`; `enqueue_locked()`, `run_job()`; waiting = `working` + `queued`;
  restarted runs re-queued by `load_job()`, at most `MAX_RECOVERIES`): `web/job_queue.py`, `web/store.py` (`RECOVERED`).
  A waiting vlog's `msg` = its place + time ("Next in line · about 6 min"), shown by the making page, progress card
  and Drafts — gotcha 37(j).
- **Edit queue** (Saves that re-render a Short take turns server-wide): `web/edit_queue.py` — gotcha 37(i).
- **Pause / Resume** (making: at once, gotcha 36; status `"paused"`, fields `plan` / `made` / `pausing`,
  `transcript.partial.json`; vlog upload: sending = browser `upSetPaused`, preparing = `Run`, YouTube stage =
  `/upload-pause` etc., vpost `"paused"`, `job["vresume"]` never sent to the page): `web/pause.py`,
  `web/vlog_upload.py`, `youtube/vlog_upload.py` (`UploadPaused`) | `js/vlog-again.js` (`pauseVlog`, `resumeVlog`).
- **Stop / Try again a whole vlog**: `web/stop_and_retry.py` | `js/vlog-again.js`.
- **Upload a vlog to YouTube** (screen 10 `#vlog/new` / `#vlog/<id>`; AI title ideas, description with chapters, tags,
  16:9 thumbnail; then "Make Shorts from this vlog?"): `pipeline/vlog_meta.py`, `vlog_thumbnail.py`,
  `youtube/vlog_upload.py` | `web/vlog_upload.py` | `js/vlog-upload.js` — gotcha 23. AI suggestions:
  `pipeline/vlog_suggest.py` | `web/vlog_suggest.py` | `js/vlog-suggest.js`. What to make: `js/make-choice.js`.
- **Vlog info from a YouTube link** (API key, else the creator's connection, else oEmbed title):
  `youtube/vlog_info.py`, `pipeline/vlog_context.py` | `web/vlog_info.py` | `js/links.js`.
- **Game Mode v1** (gaming.md; GTA V gameplay streams: the setup form's "What's in this video?" = `job["game"]`, an
  ordinary Shorts run whose moments come from the screen and the sound): `pipeline/games/gta5.json`,
  `pipeline/game_signals.py`, `game_moments.py`, `game_check.py`, `game_frame.py` | `web/game_mode.py` (called from
  `web/make_shorts.py`) | `js/game-mode.js`, `sections/setup.html`, `css/setup.css` — gotcha 39.
- **The video from a link** (Google Drive, Dropbox, OneDrive / SharePoint, any https link to the file; never YouTube or
  its video servers): `pipeline/source_link.py` (`download_video`), `youtube/links.py` (`link_kind`) | both start
  routes, `web/video_upload.py` (`room_for_link`) | `js/links.js` (`linkKind`, `VIDEO_LINK_KINDS`) — gotcha 38.
- **Videos page** (home: vlogs posted with Pit Crew or going up, `isPostedVlog`; drafts / scheduled have their own
  pages; Shorts-only uploads aren't vlogs here; cards `vlRow`, `vlShortsActs`; picture = YouTube thumbnail, else
  `poster.jpg`, else a Short's; delete videos (their Shorts stay); stopped ones show `web/errors.py`'s reason):
  `pipeline/poster.py` | `web/vlogs.py` (`/api/vlogs`, `delete-video`, `delete-videos`) | `js/vlogs.js`.
- **Channel videos** (what's on the channel that Pit Crew didn't post; public / unlisted; Short = `#short(s)` or ≤ 3 min,
  the API has no flag and `youtube.com/shorts/<id>` is unofficial; read ≤ daily or Check now ≤ 6 h; `channel_videos`
  table): `youtube/channel_videos.py` | `web/channel_videos.py` | `vlOutside`, `clOutside`. Instagram's other Reels
  (each read replaces the list; picture links expire): `instagram/reels.py` | `web/instagram_reels.py`.
- **First connect** (once per account: `users.onboarded_at`, `db.channel_checked`; never holds anyone > 30 s; what's
  running is in memory): `web/first_import.py` | `js/first-import.js`.
- **One account at a time** (Shorts & Reels and Videos show the sidebar's chosen channel / IG account: `onActive(plat,
  id)` against `channel`, `ig_id`, `vpost.channel`, `account`; nothing recorded = shown; Drafts unfiltered):
  `js/account-follow.js` (`followAccount`), `clOnPlat`, `clVisible`, `vlBase`. **No YouTube connected (Nov 2026):**
  Videos shows only a Connect YouTube card, and Shorts & Reels shows it first with nothing of YouTube's (Instagram's
  Reels still show); nothing is drawn until the account state is in (`ytKnown`), so there's no flash
  (`ytNeedHTML`, `wireYtNeed` in `js/youtube-connect.js`; connecting from the card reloads the page, `ytNeedAsked`).
- **Removed / deleted cards** (gone from YouTube / Instagram: grey card, Back to Drafts / Remove; checked once a day,
  pages never ask): `web/removed.py`, `web/youtube_sync.py`, `web/youtube_upkeep.py` | `clGoneCard`, `vlGoneHTML`.
- **Drafts** (screen 11; Vlogs tab = `isDraftVlog` + `dfPrepping`; Shorts & Reels tab = the clip browser in "drafts"
  mode, grouped by vlog (`clGroupsHTML`, Review & post = `openJob`), plus vlogs being made / paused / stopped
  (`dfMaking`, kept fresh by `dfFollow`)): `web/vlogs.py`, `web/clips.py` | `js/drafts.js`, `js/clips.js`, `css/clips.css`.
- **Shorts & Reels** (clips that went out, `isOutClip`; one browser `#clBrowse` moved by `clOpen(mode, box, vlog)`;
  platform tabs `clPlatTabs()`; Select / schedule several; "Post it on Instagram too" `clPostOne()`; views via
  `/api/clips/views` ≤ once a minute): `web/clips.py`, `web/clip_views.py` | `js/clips.js`.
- **Quick review** (panel on Drafts; `shortDetails()` shared with the editor's Details; nothing saved until Save, changes
  in `qrPend`; never `sendMoment()` here): `js/short-details.js`, `js/quick-review.js`.
- **Review page** (`#<vlog id>`, from Drafts' Review & post; "Post this" starts unticked, `reviewPicked`):
  `web/job_status.py`, `web/pages.py` (`/media`) | `js/review.js`, `review-cards.js`, `review-tiles.js`.
- **Post page** (`#postView`, thumbnail as first frame): `pipeline/cover.py` | `web/posting.py` | `js/posting.js`.
- **Try again / Add a Short / must-have moments / Choose on the video**: `pipeline/try_again.py`, `manual_moment.py`,
  `preview.py` | `web/try_again.py`, `add_short.py`, `preview.py` | `js/review-cards.js`, `js/picker.js`.
- **Hooks**: `pipeline/hooks.py` | `web/hooks.py` | `js/hooks.js` — gotcha 13.
- **Thumbnails**: `pipeline/thumbnails/` (`make.py` → `design.py`: frames → plan → layout → `looks/<look>.py`;
  `simple.py`) — gotcha 12. Look switch: `web/thumbnail_look.py`. Text / Try again (`make_thumbnail(..., avoid=plan)`):
  `web/thumbnail_edit.py` (`/api/thumb`, `/thumb-text`, `/thumb-again`).
- **Hashtags, YouTube title, Instagram caption** (`caption_for()`: 30 hashtags / 2,200 chars; ideas via `HOOK_RULE` +
  said-numbers check): `instagram/publish.py`, `pipeline/post_suggest.py` | `web/post_text.py` | `js/post-text.js`.
- **Delete a clip that went out** (YouTube deleted by Pit Crew; **Instagram can't be deleted by Instagram-Login apps**:
  the creator deletes it, `/instagram-gone` reads it, error 100 = gone): `web/clip_remove.py` | `js/clip-remove.js`.

*Editor (screen 12, `#edit/<vlog>/<short>`)*
- **Shell**: `js/editor.js`, `sections/editor.html`, `css/editor.css`. Sidebar hidden (`body.ed-on`); resizable rail
  (`#edRailGrip`, `pc-ed-rail`) and panel (`#edPanelGrip`, `pc-ed-panel`); Save / Discard pinned at the panel's bottom
  (`#edSaveRow`, Cmd/Ctrl+S); Finish (`#edFin`); Export; phones get "needs a bigger screen". **Undo / Redo** = one
  history for every tool (`edRecord`, `edGo`; each tool's `snap()` / `restore()`; typing = one step per 1.5 s pause);
  with nothing unsaved, Undo reverts a whole save and saves it at once (`edSaves` / `edRedos`, this visit only). Seeks
  the page makes go through `vidSeek()` (`js/core.js`); others are the creator's (`edUserSeek`). Save ring:
  `pipeline/ffmpeg.py` `watching(on_time=)` | `web/remake_progress.py` | `edRing`.
- **Timeline and Trim**: `editor-app/` (`src/main.jsx`, `timeline.css`, `player-state.jsx`, `vite.config.js`),
  `js/trim-strip.js` (the Video row under every tool), `edTl*`, `edTrimPaint` (redraw on every pieces change),
  `edTrimShow` | `web/ai_edit.py` (`/apply` takes pieces anywhere in the vlog), `/api/preview/<job>`. Playhead handle
  `.ts-knob` (`startScrub`, `edHeadT`, `edHeadNow()`, `edHeadPlay`); under Trim the row is the saved Short ± 30 s
  (`TS_MARGIN`), click = move the player, drag = the yellow cut box; added-but-unsaved is green (`.ts-add`); the
  player's Play uses `trimView`'s preview when the saved video lacks the playhead's moment (`edPlayerWrong`). Read-only
  with the reason when the vlog's video is gone. Twick stays mounted hidden. Gotchas 30, 31.
- **AI Edit**: `pipeline/pieces.py`, `pipeline/ai_edit.py` | `web/ai_edit.py` | `js/ai-edit.js` (`aiEdit()`: one pieces
  list + one Undo for AI Edit and Trim; saved as the first remake via `shortDetails()` `o.extra`).
- **Captions**: `pipeline/captions.py` (`clean_captions`, `PRESETS`, `FONTS`, `build_ass`), `caption_preview.py`,
  `caption_fonts/` (OFL) | `web/captions.py` (`/preview`) | `js/captions.js` (`edCapTrack`, `edCapFollow`,
  `edCapEdit` double-click to type) — gotcha 33. Saved via `shortDetails()` `o.caps`.
- **Reframe**: `pipeline/smart_reframe.py` | `web/reframe.py` (`/follow`, `/auto`, `/track`), `web/reframe_look.py` |
  `js/reframe.js` — gotchas 34, 37(e). Saved with captions (`o.frame`: one remake makes both).
- **Text & Overlays** (text only; ≤ 6, `MAX`; `moment["overlays"]` in vlog seconds `a`/`b`, `clean_overlays()`; libass
  styles `Ovl` / `OvlBox`, layer 2, one event per kept piece, nothing added when none so the golden file holds; Try
  again drops them): `pipeline/overlays.py` | `web/overlays.py` | `js/overlays.js` (`edOv*`); saved via `o.ovl`.
- **Clean clips**: `pipeline/clean_clip.py` | `web/clean_clips.py` | `edTlOff` — gotcha 35.

*Posting and YouTube*
- **Connect YouTube**: `youtube/signin.py`, `connection.py`, `config.py` | `web/youtube_connect.py`,
  `web/google_redirect.py` | `js/youtube-connect.js` — gotchas 15, 20.
- **Upload / schedule**: `youtube/upload.py`, `schedule_times.py` | `web/posting.py` | `js/posting.js`.
- **Daily upload limit** (shared, gotcha 28): `db` (`youtube_uploads`) | `web/youtube_quota.py` | `js/youtube-today.js`.
- **Scheduled page** (`#scheduled`, old `#youtube`): `youtube/manage.py` | `web/on_youtube.py`,
  `web/instagram_posting.py` (`/api/instagram/posts`) | `js/on-youtube.js`, `js/scheduled-instagram.js`.
- **Posted list** (step 4): `js/posted.js`. **YouTube data rules** (gotcha 27): `youtube/connection.py` (`recheck`),
  `youtube/stored_data.py` | `web/youtube_upkeep.py`, `db` (`gone_channels`).
- **Connect Instagram**: `instagram/connection.py`, `config.py`, `http.py` | `web/instagram_connect.py` | `js/instagram-connect.js`.
- **Post to Instagram** (Pit Crew posts at the time): `instagram/publish.py` | `web/instagram_posting.py` (scheduler
  thread) | `js/instagram-posting.js` — gotcha 19.

*Analytics*
- **Page** (tabs Overview / Videos / Audience / Grow, `pageTabs("anTabs")`; `anPlat`; range All time (default) or
  Custom `?days=` / `?start=&end=` via `anRangeSet()`; `?content=` → `creatorContentType`): `youtube/analytics.py`,
  `analytics_coach.py` (`daily_facts`, `rules`, `read`), `instagram/insights.py` | `web/analytics.py`,
  `web/analytics_coach.py` | `js/analytics.js` (`anQuery()`, `openShortAnalytics`). Gotchas 17, 22-22e.
- **Videos tab** (YouTube vs Instagram per clip, ≤ 6 `AN_PAIR_MAX`; Compare any videos ≤ 8; first-week section):
  `youtube/analytics_more.py` (`clip_totals`), `instagram/insights.py` (`reel_numbers`), `account_insights.py`
  (`follows_after`) | `web/analytics_pairs.py`, `web/analytics_more.py`, `web/analytics_clips.py` |
  `js/analytics-videos.js`, `js/analytics-clips.js`.
- **Audience / Grow** (`donutHTML` ≤ 5 slices, `colsHTML` class `vbar`: theme.css owns `.bar`; lessons in
  localStorage `pc-an-lessons`): `analytics_more.py` (`audience`), `account_insights.py` | `js/analytics-audience.js`,
  `js/analytics-grow.js`.
- **Loading states** (`anSkel`, `anWait`, `anSkelNum`; one shared timer; no motion with reduced motion):
  `js/analytics-loading.js` (before `analytics.js`).

*Server*: `serve.py`; `deploy/` (`setup.sh`, `update.sh`, `test.sh`, `backup.sh`, `invite.sh`, `status.sh`,
`envtool.py`, `point-docs.sh`); `web/health.py` (`/healthz`); `REVIEWS.md` (platform review texts). Gotcha 24.

**Shared files** (change with care, say so in the PR):
- `app.py` loads `.env`, imports every `web/` file (registers routes). `settings.py`: `ROOT`, `JOBS_DIR` (env-movable).
- `web/server.py`: the Flask `app`, cookie settings. `web/store.py`: `JOBS` mirrored to `jobs/<id>/job.json`, `LOCK`,
  `update()`, `update_short()` (counts as an edit, gotcha 21), `load_job()`, `editable_job()`, `video_gone()`,
  `RETRY_LOCKS` (one remake at a time per vlog), `next_file_number()`.
- `pipeline/ai.py` `ai_json()` (gotcha 11). `web/errors.py` `plain_error()`: one plain sentence per failure; raw text to
  `job["error_detail"]` and the terminal, never the page. `web/youtube_sync.py` `sync_deleted()` (Shorts deleted in
  Studio become drafts; a vlog YouTube removed gets vpost `removed`). `web/priority.py` (gotcha 37a).
- `pipeline/ffmpeg.py` (`ffmpeg_exe()`, `run()`, `probe()`, `watching()`), `text.py`, `constants.py`.
  `pipeline/__init__.py`, `youtube/__init__.py`, `instagram/__init__.py` only re-export what `web/` uses.
- `static/index.html`: the skeleton (CSS / JS lists, `sections/*.html` includes, the icon list, gotcha 32).
  `static/js/core.js`: `$()`, `fmt()`, `esc()`, `setHTML()`, `show(n)` (screens 1 New vlog … 7 Videos, 8 Settings … 11
  Drafts, 12 editor), `NAV_FOR`, `shortLen()`, `studioLink()`, shared state. `static/css/tokens.css` (all colours,
  contrast-checked), `base.css`, `buttons.css`, `fields.css`, `cards.css`, `shell.css`; `theme.css` loads last (fonts
  Unbounded / Plus Jakarta Sans / JetBrains Mono). The logo (three rising slanted bars on a red tile; never a play
  button or a red P) is inline SVG in `sections/sidebar.html` and `auth.html` (own ids in each copy).

**Modularity rules**
- A new feature gets new files, plus **one line** each in `app.py` and `static/index.html` (the only shared edits).
- Inside `pipeline/` / `youtube/` import from the feature file (`from pipeline.hooks import hook_fields`), never the
  package `__init__` (circular imports). `web/` uses the facades (`pipeline.x`, `yt.x`, `ig.x`).
- `web/` route function names are unique: `gate()` checks `request.endpoint` against `PUBLIC` (function names).
- Page JS shares one global scope, loaded in `index.html` order (no modules): load-time code may only use earlier
  files; handlers may use any. `account.js` stays last (`boot()`).
- Runtime: `jobs/<id>/` (`source.*`, `transcript.json`, `captions_N.ass`, `short_N.mp4`, `look_N.mp4`, `thumb_N.jpg`,
  `thumbwork_N/`, `clip_<idx>.mp4`, `preview.mp4`, `poster.jpg`, `job.json`), `jobs/_transcripts/`, `jobs/_uploads/`,
  `data/` (database, cookie secret, token key). All git-ignored.

## Hard-won gotchas (don't undo these)

1. **Audio is decoded by FFmpeg** (`load_audio()` pipes 16 kHz mono float32 into `model.transcribe(array)`), not
   faster-whisper's PyAV decoder (PyAV ≥ 15 broke its `metadata_errors` argument).
2. **OpenCV < 5** (5 dropped `CascadeClassifier`). Face finding never fails a job: any error → `None` = centre crop.
3. **Not every FFmpeg has libass** (Homebrew, Anaconda): `ffmpeg_exe()` picks the first with the `subtitles` filter
   (`$FFMPEG_PATH`, PATH, Homebrew, then `imageio-ffmpeg`'s static binary). Never hard-code `"ffmpeg"` (ffprobe: PATH).
4. **Captions need a real font file**: `prepare_job_fonts()` copies `fonts/*` (else a system bold) into the job;
   `caption_font_name()` uses `CAPTION_FONT` only if present. No fontconfig + missing font = invisible captions.
5. **Gemini models retire and get busy**: `FALLBACK_MODELS` (newest Flash first; `GEMINI_MODEL` tried first);
   `gemini_error_kind()` = busy / limit / missing / bad_key / other; busy retried in rounds (`BUSY_WAITS`), missing /
   limited skip ahead. Check https://ai.google.dev/gemini-api/docs/models before renaming.
6. **`probe()`** uses `-show_streams -show_format`, rotation from `side_data_list` or old `tags.rotate`
   (`stream_side_data=` breaks FFmpeg 4.x). Remembered per (path, size, mtime) (37d).
7. **Sideways phone videos**: `probe()` swaps width / height for rotation 90 / 270.
8. **The subtitles filter runs with `cwd=job_dir` and relative paths** (`subtitles=captions_N.ass:fontsdir=fonts`):
   Windows drive letters break escaping. Same for `sendcmd` files.
9. **Transcription is batched** (`BatchedInferencePipeline`, ~2×; `WHISPER_BATCH_SIZE=0` = off). **English only for
   now**: batched mode guessed an English vlog as Welsh, so with `WHISPER_LANGUAGE=auto` `detect_language()` votes over
   8 clips; Hindi / Hinglish was tried and dropped. `drop_repeats()` keeps a phrase ≤ 2× in a row (Whisper loops over
   music) and cuts a letter repeated 4+ to two. `sentence_segments()` rebuilds sentences from word times (the AI needs
   them). Model loaded once per process (`whisper_model()`); GPU used when present.
10. **Never download videos from YouTube** (API policy, even the creator's own; risks posting access). Only public text
    is read (Data API with `YOUTUBE_API_KEY`, else oEmbed). Video comes from an upload or a Drive link.
11. **Every AI call goes through `ai_json()`** (Gemini `gemini_json()` / OpenAI `openai_json()`, shared `ask_models()`;
    images as `image_part(bytes)`). OpenAI JSON mode returns objects only: a list arrives as `{"items": [...]}`, callers
    accept both. OpenAI reasoning models reject `temperature` (retried without). Keep `OPENAI_FALLBACK_MODELS` current.
12. **Thumbnails**: one AI-chosen frame, look **Frame** (default) or **Duotone** (cut-out collages dropped: ugly cut-outs,
    180 MB model, 2 GB RAM).
    - Plan (`plan.py`): 12 frames (≤ 1920 px, 4 at a time) → AI returns `frame`, `focus` (box_2d `[ymin,xmin,ymax,xmax]`
      0-1000), `line1`, `line2`, `accent`; `clean_plan()` validates; fallback `plan_without_ai()`. **Always Gemini**
      (`THUMB_AI_PROVIDER`: trained on box_2d); a failing provider is skipped for `REST` (180 s).
    - Text: `tidy_lines()` drops words repeated from the headline; `text_spot()` above the face, else below (clear of the
      bottom 230 px), else the roomier side. Fonts bundled (OFL): Anton, DM Serif Display; Latin only.
    - Crop `layout.portrait()` 9:16 around `focus` (`ZOOM`, `FACE_AT`), sharpened when upscaled a lot.
    - Looks: `compose()` → `looks/<look>.py` (`LOOKS`, `THUMB_LOOK`); look saved in `plan.json`; switching redraws from
      `thumbwork_N/` (no AI, ~1 s). `upgrade_plan()` reads collage-era plans. `fresh_accent()` (under a lock) gives each
      Short of a vlog its own accent.
    - Speed / never stuck: started as soon as each Short is edited, `THUMB_WORKERS` (3) at once; timeouts everywhere
      (`ai.TIMEOUT` 180 s, thumbnails 60 s, overall `AI_DEADLINE` 120 s → `plan_without_ai()`); one silent Gemini
      request once froze a job. Output < 2 MB. `THUMB_STYLE=simple` or failure → `simple.py`.
    - **Shorts feed thumbnail can't be set by API** (thumbnails.set skips the Shorts feed and needs a verified channel):
      `pipeline/cover.py` puts it in as the first 0.2 s (6 frames) on upload and on Save (`/media/...?cover=1`), joined
      without re-encoding (re-encodes if the decode check finds a bad join; A/V within 0.3 ms); the job's Short stays
      clean; `cover_<short>_<thumb>.mp4` cached; `COVER_FRAME=0` = off.
    - Descriptions (`short_description()`): hook, "Watch the full video: <link>", "More from @handle", hashtags. Links in
      Shorts descriptions can't be tapped (@mentions can); Related video and feed thumbnail are manual Studio steps.
13. **Hooks must be true.** Fields `hooks` (curiosity / bold / story / custom), `hook`, `hook_style`, `hook_mode` ("text"
    / "none"). Every prompt carries `HOOK_RULE`; `hook_fields()` drops a hook with a number not said in the moment.
    Applying a hook can redraw the thumbnail text (`hook_to_lines()` → `retext_thumbnail()`, saved frames, no AI).
14. **No emoji in burned-in text** (fonts lack them: boxes): `without_emoji()` in `ass_escape()` and thumbnail drawers.
15. **YouTube OAuth redirect must match exactly** (`/api/youtube/callback`; local `http://localhost:8000`, never
    127.0.0.1; cloud `YOUTUBE_REDIRECT_URI`). Never `InstalledAppFlow.run_local_server()`. One `youtube` scope; a token
    without it = signed out. Replace uploads the new one first, then deletes the old; refused once public
    (`yt.is_live`). Upload records keep `video` (the file sent) to detect edits. The pending sign-in (state, PKCE,
    purpose) is in the session cookie.
16. **Accounts and ownership.** Every `/api` and `/media` route needs a user (`gate()`; open only `PUBLIC`), and any
    route with `job_id` checks `job["owner"]`, so new job routes are protected automatically. Background threads get the
    user id passed in. Google login asks `openid email profile` only; users matched by Google `sub`; an email that
    already has an account is refused (`EMAIL_EXISTS`), never joined. Reset link `APP_URL/#reset=<token>` (SHA-256
    stored, 1 h, same reply whether or not the account exists; using it verifies the email and bumps
    `session_version`). Build email links from `APP_URL`, never the Host header. Cross-Origin POSTs get 403. Login
    throttle uses `remote_addr` (behind a proxy: `TRUST_PROXY`, ProxyFix). **Tests set `DATABASE_PATH` and `JOBS_DIR`
    to temp paths before importing `app`** (`tests/_env.py`): a test once wrote to the real jobs.
17. **Analytics** needs `youtube` + optional `yt-analytics.readonly` (`ANALYTICS_SCOPE`); without it, live counts and
    `notes=["reconnect"]`. Filter `creatorContentType==shorts` (camelCase: `shorts`, `videoOnDemand`; UPPER_CASE → 400).
    Numbers lag ~2 days; cached 10 min per channel. `short_detail` = whole life with **live** views / likes / comments;
    first-week uses live counts until final (no false 0). Charts: one axis, token colours, text never in series
    colours, a Table button on each, whole-number steps (`countMax`).
18. **Open in Studio** goes through Google sign-in (`studioLink()`: `ServiceLogin?service=youtube&continue=...`).
19. **Instagram (Instagram Login, no Facebook Page).** Professional accounts only (`account_type` checked). 60-day token
    refreshed with < 10 days left. **Instagram downloads each Reel from Pit Crew**: container `video_url` = signed
    expiring link `/ig-video/<token>.mp4` (`public_video_url()`, in `PUBLIC`), poll until `FINISHED`, then
    `media_publish`. Never resumable upload to `rupload.facebook.com` (Facebook-Login apps only: "video_url is
    required"). So Pit Crew must be reachable over https when a Reel goes out (`PUBLIC_URL`, else the
    `INSTAGRAM_REDIRECT_URI` host, else `APP_URL`). `thumb_offset` = the cover frame. No scheduling for apps: a daemon
    thread posts due `job["ig_posts"]` (also ones missed while off); one left `posting` by a crash becomes `check`, never
    re-posted. 100 API posts / account / 24 h. **One process with threads** (scheduler, vlog queue, `jobs/_uploads`): no
    forking servers / `--preload` (threads don't survive a fork); proxies must accept ≥ 8 MB bodies.
20. **Several channels / IG accounts per creator** (`connections`: platform, `account_id`, token, profile, `active`).
    Active = where *new* posts go and what Analytics shows; Switch changes `active`; Disconnect makes the newest other
    active; sign-out leaves connections. **Never act on the active account for something planned or posted**: routes
    take the `channel` / `ig_id` the page showed; records keep `channel`, `ig_id` + `username`; pass them to
    `yt.get_service(channel=)` / `ig.post_reel(ig_id=)`. Caches keyed per account. Old one-per-user rows migrated
    (`user_version` 1, `_fill_channel`, `_stamp_account`). Add Instagram account sends `force_reauth=true`.
21. **Storage timers** (`web/retention.py`, every 15 min; 0 = forever; `RETENTION_OFF=1` in tests): vlog video
    `KEEP_ORIGINAL_HOURS` (72) after `last_edit_at`; draft `KEEP_DRAFT_DAYS` (30) after `edited_at`; posted Short's file
    `KEEP_POSTED_DAYS` (30) after it went out everywhere (`file_deleted_at`, Download → Studio); saved transcript
    `KEEP_TRANSCRIPT_DAYS` (30). **Route Short changes through `update_short()`** (it stamps both clocks). Warnings a day
    before (card + email). Nothing touched while made, remade, posted or a Reel waits. `remove_video()` is the only way
    a vlog's video goes (37h); then Try again / Add a Short are locked and drafts edit from clean clips (35). A stopped
    vlog keeps its video `KEEP_ORIGINAL_HOURS`, then it (or the whole vlog if it made nothing, `_empty_stop()`) goes.
22. **Compare clips by their first 7 days**, never lifetime. YouTube `first_week_views()` (`video==id`, final after 9
    days); Instagram gives running totals only, so `snapshot_reels()` saves daily (`reel_snapshots`, also every 6 h):
    first week = the snapshot 7-9 days after posting. `takeaways()` compares groups of 2+, needs 4+ finished clips per
    platform and a 20 % difference, and says what it's based on.
22b. **Reports YouTube refuses are left out, never an error** (`_try()`; `_with_engaged()`; a refused content filter is
    retried as a dimension `_report_by_type(kind)`; `video,creatorContentType` is refused). `subscribedStatus` 500s on
    some channels: `_subscribed()` → None, retried after `SUB_RETRY` (24 h). "All time" starts at `channel_start()`
    (never 2005: reports took 10-35 s). httplib2 isn't thread-safe: `_per_thread()` clients, 40 s timeout `_http()`.
    Apps can't read impressions / CTR, realtime, unique / returning viewers, "when viewers are on", swiped away: don't
    promise them. Instagram insights: ≤ 30 days per request, kept 90 days, demographics need 100+ followers,
    `impressions` retired (use `views`); `account_insights()` stitches ≤ 30-day pieces (`ig_window()`, notes "cut" /
    "old"); reach / accounts engaged over 30 days = None (page says so). Likes / comments: All time = live counts; a
    range = Analytics (counts differently, ~2 days behind; page says which). Compare (calendar) starts at the earliest
    ticked video's posting day. Charts: one colour per video `--s1..--s8`, fixed while ticked; donuts fold past 5;
    YouTube `--c-yt` (blue), Instagram `--c-ig` (orange) everywhere.
22c. **Instagram can't say which Reel brought a follower**: "new followers" = `follows_and_unfollows` in the 48 h after
    posting (`follows_after()`; `complete` false until then; None past 88 days). The page says so.
22d. **Pit Crew's read: ≤ 1 AI call per creator per day** (key: user, channel, Instagram on/off, date; never the range).
    It reads fixed facts (`daily_facts()`, every key names its span), answers headlines (both / YouTube / Instagram) +
    4-6 tagged tips (`_fill()`); `_honest()` drops tips with numbers not in the facts (±1; 0-10 allowed) and swaps a bad
    headline for `rules()`'s. Gemini then OpenAI, 25 s each. **The page never waits**: `read()` answers `rules()` with
    `pending:true`, the AI runs in a thread, the page re-asks every 6 s; failures retried after 10 min. Keep spans
    labelled (a 7-day read once called a lifetime number "this week's").
22e. **Shorts posted straight away have `"when": None`**; `uploaded_at` since Oct 2026; older records get dates from
    `fill_dates()` (YouTube's published date).
23. **A vlog upload is a job with `kind:"vlog"`**: `VLOG_STAGES` while prepared, then `status:"ready"` + `job["vdraft"]`
    (what the creator edits), once sent `job["vpost"]` (uploading → done / error / waiting / paused / removed) and
    `job["vlog"]` (id, URL, channel; Shorts link to it). No `count` until Shorts are asked for: `/api/vlogs` calls it
    `prep` (opens screen 10). `/shorts` turns it into a Shorts job on the same video + transcript (only while the video
    is kept and before any Shorts). vpost left "uploading" by a restart → error; retention never deletes mid-upload.
24. **The server** (Ubuntu 24.04, systemd): one process, `serve.py` (Waitress, `WEB_THREADS`) behind Caddy (https,
    `/static` served directly with `no-cache`, security headers, no access log). Runs as `pitcrew` with
    `ProtectSystem=strict`: **code is read-only; everything written lives under `/srv/pitcrew`** (`DATABASE_PATH`,
    `JOBS_DIR`, `HF_HOME`, `HOME`). A setting whose laptop default is wrong for a server goes in setup.sh's first-run
    `--force` list (`JOB_SLOTS=2` once stayed on a 2-core server). `update.sh` runs from a temp copy, refuses if server
    code was edited, compiles before restarting, runs the fast tests, and on failure moves the **branch** back
    (`checkout -B`). Never pipe long output into `grep -q` under `pipefail` (SIGPIPE fails the check). Oracle images also
    block 80/443 in iptables.
25. **Caption fonts by full name**: `caption_font_name()` returns `CAPTION_FONT` if it matches a family *or full name*,
    else the full name of the job's font ("Montserrat ExtraBold"); asking libass for a family with many weights gave
    Regular. setup.sh copies Montserrat ExtraBold into `fonts/`.
26. **The privacy policy is a promise about the code** (`static/legal/privacy.html`; retention times read from
    retention's settings, AI providers from `.env`). Collect something new, send to a new service, keep longer, or
    change a scope → update it and `UPDATED` in `web/legal.py` **in the same PR**.
27. **YouTube stored-data rules (Developer Policies III.E.4, III.D.2), `web/youtube_upkeep.py` daily**: channels
    re-checked every `CHECK_DAYS` (7; rule 30): token refreshed (invalid_grant drops it), profile re-read (`yt.recheck()`,
    `profile.checked_at`), posted videos checked (`sync_deleted(force=True)`). A channel in records but disconnected →
    `gone_channels`, forgotten `GONE_DAYS` (5) later (upload records → drafts, vlog links, cached numbers); reconnecting
    first keeps all. Link details (`job["vlog"]`, `fetched_at`) re-read after `LINK_DAYS` (30) or deleted when YouTube
    can't find the video. Cached numbers ≤ 30 days (`youtube/stored_data.py`). **Anything new kept from a YouTube API
    answer needs a refresh-or-delete path here** (+ the policy). Open question for the audit: a deleted outside video's
    title kept on a grey card (`GONE_DAYS` in `web/channel_videos.py`).
28. **YouTube's upload limit is per Cloud project; Pit Crew is one** (`YOUTUBE_DAILY_UPLOADS` 100, reset midnight
    Pacific; a scheduled Short counts the day it's sent). Never add projects to get more (against the terms; the audit
    raises it). Every upload: `youtube_quota.take()` first, `give_back()` if it didn't reach YouTube; YouTube's
    `quotaExceeded` marks the day used (`youtube_says_used_up`). Over the limit nothing fails: Shorts → `job["yt_waiting"]`,
    a vlog → vpost `waiting`; the `youtube-waiting` thread sends them after reset, oldest first. Only Replace says "press
    again after midnight". `YOUTUBE_OPEN_SHARE` (60), `YOUTUBE_RESERVE` (5).
29. **Nothing from YouTube's API goes to free Gemini** (it may train on it; Google's Limited Use rule):
    `youtube_data_ok()` is true only for OpenAI or `GEMINI_PAID=1`. Until then YouTube-read titles / descriptions stay
    out of prompts (`vlog_context_block()`, thumbnail plan) and the Analytics read uses `rules()`. What the creator typed
    is fine. Every new prompt with YouTube data checks `youtube_data_ok()`.
30. **A Short can keep several pieces** (`s["pieces"]` = `[[a, b], ...]` in vlog seconds inside `start`..`end`; none =
    one piece). `/apply` takes pieces anywhere in the vlog and sets `start` / `end` to the first / last piece (one piece =
    just new `start` / `end`). **Not `keep`: that's the "Post this" tick.** Only `pipeline/pieces.py` reads pieces:
    `kept()`, `length()` (the Short's length everywhere: `pipeline.short_length`, `shortLen()`; never `end - start`),
    `timeline()` (words on the Short's clock), `said()` (what's still said: hooks, titles, captions ideas). `render_short`
    joins them in one FFmpeg run (`trim` / `atrim` + `concat`, 20 ms fades; `-ss` before `-i`). After a cut,
    `honest_hooks()` drops hooks with numbers no longer said (`edit_note`). Try again drops pieces; hook / look keep
    them. AI Edit's AI reads only the Short's words (60 s timeout, one short busy wait).
31. **Twick's timeline (`editor-app/src/main.jsx`) only works with all of these**: track type `"element"`; every clip has
    `trackId`, `frame`, a non-empty `src` (no video = empty `data:` URL, else its validator undoes trims) and
    `mediaDuration`; new clip ids per layout. Twick's own split isn't used (reloads video details, can lose the clip):
    Split / Delete are worked out on the pieces; a split alone isn't a change (`aeNorm`). Its right-click menu and file
    drops are caught. Changes are reported after Twick's update (`setTimeout`) and the page re-lays it from `aiEdit()`'s
    pieces. Privacy: `@twick/live-player` replaced by `src/player-state.jsx`, PostHog off
    (`window.__TWICK_ANALYTICS_DISABLED__`, `analytics.enabled:false`), its Google Fonts / cdnfonts `@import`s dropped,
    every rule scoped to `.pc-tl` (`vite.config.js`); its inline-white ruler is overridden in `src/timeline.css`.
    `npm` needs `--ignore-scripts`. Navigation and **trimming are ours** (`mount()`: box-select off, wheel scrolls,
    Ctrl/Cmd+wheel zooms, `trimStart` / `trimMove` / `trimEnd` within `EDGE` px of any part's end, clamped to
    neighbours and the vlog, ≥ `MIN_PART` 0.5 s, snapped to `opts.snaps()`, committed via `impl.commit()`; a press on a
    join takes the right-hand part). Run `tests/browser/check_editor.py` after any change here.
32. **The icon font only has icons listed in `static/index.html`** (`icon_names=` on the Material Symbols link, A-Z or
    Google refuses). An unlisted icon shows its name. `tests/test_page_scripts.py` fails on an unlisted one.
33. **Captions = the Short's `captions` settings.** None = the job style's preset, which writes **exactly** the old .ass
    (`tests/captions_golden.json`, byte for byte: change the default look only on purpose). `clean_captions()` checks
    every key. Word changes (`edits`, "" = left out), `pop`, `br` and per-line `styles` (`LINE_KEYS`; a line takes its
    first word's) key on the word's **index in transcript.json `words`** (`"i"`), never its time, so cuts never move
    them. Every remake reads them; Try again keeps the look, drops word changes (`style_only`). The editor's Save sends
    them before a cut / hook remake without their own remake (that one makes them); if that's refused they get their
    own. Fonts bundled (OFL) and copied to `fonts/` (4); libass gets the full name (25); one-weight display fonts asked
    without Bold (`BOLD`). Preview = one frame of the vlog framed like the Short with the same .ass (`caption_frame()`,
    ≤ 2 at once, `PREVIEWS`) or 2.5 s silent video (`caption_clip()`). Pop / Punch scale **every word** (a line-wide tag
    is undone by each word's `\fscx`); Pop / Word by word hide later words with `\1a\3a\4a` (`POP_STEP`) so the line
    never shifts; Slide up = `\move` to the line's own place. Effects < 0.2 s aren't visible at 30 fps. **Swear words are starred** (`censor`, on by default: `SWEARS`, "Fuck" →
    "F***"; the sound is untouched; a word the creator typed in the editor shows as typed).
34. **Reframe = the Short's `reframe` settings** (`pipeline/smart_reframe.py`). None = `crop_filter(meta, cx)` **exactly**
    (`tests/test_reframe.py`); a vertical vlog is padded as before. Times are vlog seconds, positions fractions; the render
    walks the Short's clock every 1/30 s, maps back through pieces (`to_vlog`), asks `framing_at`. **A moving frame is
    `sendcmd`** (`reframe_<uuid>.cmd`, relative path, deleted after the run) setting `crop@rfa` x / y (+ zoom: `scale@rfz`
    w / h, `crop@rf` x / y). **Never change a crop's size by command** (FFmpeg stops after one frame): zoom = fixed crop of
    the widest frame → scale → crop. Verified on FFmpeg 7.1 and 8.1 (`tests/system/system_reframe.py`). In the captions
    preview `setpts` comes **before** the framing. Fit / Split use labelled pads (`split[rfa][rfb];...`), valid in `-vf`
    and spliced into joined pieces. Remakes keep it; Try again keeps the layout, drops moves (`reframe_style_only`).
    Fill with Fit shots overlays Fit on the Short's clock (`fit_ranges`); punch-ins multiply zoom (`punch_at`). Thumbnails
    still use `cx`. Auto layout (`auto_shots`, `scene_changes`), Track (`track_moves`, 320 px template match every
    0.2 s), Follow (`follow_moves`, a face every 0.5 s, a move after 7 % for 1 s) never fail a request (no face = `[]`).
35. **After a vlog's video is deleted, drafts are remade from clean clips** (`web/clean_clips.py`). `remove_video()` calls
    `make_clips()` first: each draft gets `clip_<idx>.mp4` (kept parts ± `PAD` 30 s, H.264 CRF 20, 1080 short side;
    `s["clip"]` = {file, from, to, scale}); a failure never stops the deletion. **Times stay vlog seconds**: `source()` =
    {path, offset (clip `from`), scale, reach, clip}; the pipeline reads at (vlog time − offset) (`render_short(offset=)`,
    `caption_frame`, `follow_moves`; page: `edTlOff`, Trim preview, Reframe). **`cx` is in vlog pixels**:
    `clean_clips.render()` scales it into the clip and back. Pieces clamp to `reach`. Posted / planned Shorts get none;
    Try again / Add a Short still need the vlog. `tests/system/system_clean_clips.py`. In the privacy policy.
36. **Pause and Stop don't wait** (`web/pause.py` `Run`): the run's thread only waits on helpers (`run.doing(fn)`) and
    checks every 0.1 s. FFmpeg is killed within 0.2 s (`pipeline.ffmpeg.watching(check=)`; pipeline just calls `run()`),
    transcription stops at its next batch (resumed from `transcript.partial.json` behind a per-file lock), an AI answer
    is dropped. After the run is left, `Run.check()` raises in helpers too, so **a helper never writes over a paused
    job**: new run steps go through `step()` / `run.doing()`. A progress callback raising is `_Halted` (not a batched
    engine failure). YouTube's stage pauses after the 16 MB piece in flight. **Every FFmpeg gets
    `stdin=subprocess.DEVNULL`** (or `-nostdin`): under `timeout` (update.sh) FFmpeg reading the terminal got stopped and
    tests hung (`test_ffmpeg_never_gets_the_terminal`).
37. **Speed on a small server (e2-standard-4 = 2 physical cores).** Pages answer in ms even while a vlog is made; lag is
    heavy work competing, not file count (105 page files load in ~0.1 s over HTTP/2). Measured on a 2-core box with a
    4K vlog (`tests/test_speed.py`, `tests/system/system_speed.py`, `tests/test_clean_clips.py` SlowDeletion,
    `tests/test_edit_queue.py`):
    a. **Background work runs at nice 10** (`web/priority.py` `lower()` / `background(fn)`): making Shorts
       (`job_queue._run`), the scrubbing copy, posters, copies, video deletion. On Linux nice is per thread and inherited
       by threads / programs started after (the speech model's workers, FFmpeg). New long background threads call
       `lower()` first; threads the creator waits on (a remake after Save) don't.
    b. **Face finding reads keyframes only** when there's one every ≤ 2.5 s (`reframe.key_frames`: `-skip_frame nokey`,
       `-vsync passthrough`, grey PGMs on a pipe), else one pass, a picture a second (`_every_second`; a seek per
       second decoded up to a GOP each): 6× on 1080p, 14× on 4K HEVC.
    c. **`-t` goes before `-i` when filters drop frames** (`select`): after `-i` it counts output time, so
       `scene_changes` read to the end of the vlog.
    d. `probe()` cached per (path, size, mtime) (~50 ms per editor click).
    e. **Reframe's buttons read a small copy** (`web/reframe_look.py`): `look_<n>.mp4` beside `short_<n>.mp4` (640 wide;
       `look_<n>.json` = its vlog seconds), a second output of the render (`render.look_output`: +5 %, the Short
       bit-identical; on failure rendered the plain way; none from a clean clip). Read with `offset` = its start; pieces
       outside it use the source. Older Shorts get one when Reframe opens (background, never waited for; not while the
       video is being deleted). Same answers; 4K: Follow 22 → 1.4 s, Auto 17 → 0.6 s, Track 16 → 0.2 s. Deleted with
       the video (`look_*`) and the Short (`_short_files`); in the privacy policy. The editor's player / Trim / Text keep
       the vlog itself (a small copy would be blurry there).
    f. **Captions preview keeps the framed picture** of its last 12 moments (`caption_preview._BASES`; not for a
       moving frame: its cmd file changes): another change at the same moment only draws captions (4K 1.3 → 0.1 s).
    g. Transcription tuning on the server: `sudo bash deploy/test.sh ab whisper --video /srv/pitcrew/jobs/<id>/source.mp4`.
    h. **Deleting a video happens behind the button** (`vlogs.delete_soon`): clips take ~1 min each on 4K, so the
       request sets `deleting_video`, waits ≤ `SETTLE_WAIT` (5 s; small vlogs and tests finish within it) and the rest
       runs at nice 10, one vlog after another. `store.video_gone(job)` (deleted or being deleted) is the check for
       anything needing the whole vlog (page's `video_deleted`, Try again, new thumbnail frames, Make Shorts again,
       resume, vlog posting). `clean_clips.source()` alone looks at `video_deleted_at`, so editing continues from the
       vlog meanwhile, but `/api/preview` hands a player only the clip (else `building`), and the file is removed only
       after remakes started meanwhile finish (`_remakes_done`). A deletion cut short by a restart is finished by the
       retention sweep.
    i. **Saves that re-render a Short take turns server-wide** (`web/edit_queue.py` `turn(job_id, idx)` around the
       render in captions / reframe / text, Trim, hooks, Try again / Add a Short): `EDIT_SLOTS`, default half the cores
       (2 on the server, ≤ 4); the rest show `WAITING_MSG`. Thumbnail redraws don't wait. 5 saves at once on 2 cores:
       all done at 73 s before; now 30, 30, 58, 59, 73 s, memory 2.4 → 1.4 GB, pages faster. A slot is always given
       back (failed render, deleted vlog).
    j. **A waiting vlog says its place and when it starts** (`job_queue._paint_locked`): "Next in line · about 6 min",
       "3rd in line · ...", "Starts after your other video". The time is learned on this server (`SPEED`, seconds per
       minute of video for "shorts" / "prep", averaged from runs that finished without a pause, kept in
       `JOBS_DIR/_queue_speed.json`) and covers what's left of the running vlogs (by `pct`) plus those ahead, over
       `SLOTS`. Nothing learned yet (or a length unknown) = only the place, never a made-up time. Video lengths are
       probed outside the lock (`_lengths`); the dispatcher repaints every 5 s. Keep the text short: the sidebar card
       cuts it on a laptop.
38. **A video link is fetched by the server, so it's guarded** (`pipeline/source_link.py`): https only, and every name
    must resolve to public addresses only (never this server, the local network or 169.254.169.254, the cloud's
    metadata service), checked on every redirect and on the very address connected to (`_SafeHTTPS`). YouTube and
    `googlevideo.com` links are refused (gotcha 10). Downloads stream in 1 MB pieces with `check()` (Pause / Stop),
    `MAX_UPLOAD_GB` and the free room (`room_for_link`); Drive goes through gdown, checked only after it finishes. The
    half file is `.download.part`, never `source.*.part`: the pages find a vlog's video with `glob("source.*")`. A
    sign-in or "request access" page (HTML) is refused with the sharing message.
39. **Game Mode is an ordinary Shorts run** (`job["game"] = "gta5"`, never a new `kind`: many places branch on
    `kind`). Only the moment picking differs (`web/game_mode.py` `game_moments`, from `make_shorts`): signals read in
    `CHUNK`-second pieces through `run.doing()` (Pause / Stop, gotcha 36), from keyframes when they're <= 2.6 s apart,
    else one picture a second, saved in `game_signals.json` (Resume doesn't read it again); scored per stream (a flat
    or always-on signal is left out, never counted as zero, so a silent stream scores on pictures); the AI sees a few
    middle-third pictures of the best ~15 (`pipeline/game_check.py`, `ai_json()`, `HOOK_RULE` + `hook_fields()`), and
    a failed AI = the detector's order with plain labels. Game moments don't go through `clean_moments` (it drops
    moments where nobody speaks) and the run sets no `little_speech`. Each Short gets `cx` (passed to `render_short`:
    the vlog face finder would lock on the facecam) and ordinary Reframe settings: Split (game on top, facecam below,
    the bottom view capped at `ZOOM_MAX` 2.5) or Fill that changes through the Short (`auto_frame`: a new
    frame at each scene change, follows the person in a shot, two people too far apart = that shot Fit, nobody = the
    motion; a frame per part on the motion if the video can't be read). Montages are Shorts with
    several pieces, kept to one stretch (`montage.max_span`, 5 min): a montage's clean clip, thumbnail frames and Trim
    strip reach from its first part to its last (gotcha 35). First real stream (GTA Online, Nov 17): the minimap
    region must stop above the health / armour bars (their blue read as police); WASTED is white there, so a death =
    a grey picture that isn't the pause map (`edges` ≥ `map_edges`) or black (`bright`); wanted stars count only near
    the police (city lights); gold = fire as often as MISSION PASSED (named so for the AI); a montage never repeats
    another Short's moment. The wanted corner and centre regions are still estimates. Game Fill Shorts use `wide` (Reframe setting: a square view
    across the middle over a blurred copy, `game_frame.WIDE`; none = 9:16 as before), and single moments grow to whole
    sentences (`with_context`: the setup ≤ 8 s before, the sentence's end ≤ 4 s after, never into a neighbour). The
    minimap is laid over a game Short only while it's really in its corner (`game_signals` "map", `hud["on"]`)
    (`moment["hud"]`, `pipeline/game_hud.py` `with_hud()` around the reframe chain in `render_short`; bottom-left
    under the captions, or top-left in a wide view; none = the render exactly as before). Graphics an editor laid
    over the video's corners (a scoreboard) are found by `game_signals.find_overlays` (outlines shared by pictures of
    different scenes, kept only if fully on or off: a camera the video cuts back to isn't one) and laid whole, smaller
    (`EXTRA_W`), on their side of the view's top row while on screen (`hud["extras"]`). Try again on a game Short still
    picks from the transcript (stage 2 of gaming.md). The detector's details are on the Short as `s["game"]`. What the AI check cost (pictures, provider, model, tokens) is `job["game_ai"]`
    (`ai_json(usage=)`); a game Short the creator deletes or replaces with Try again goes into `job["game_log"]`
    (`web/game_feedback.py`, `game_verdicts()`: posted / draft / deleted / tried_again), to tune `gta5.json` later.

## Conventions

- Dependency-light, one concern per file, no frontend framework (except `editor-app/`). The only database is SQLite in
  `accounts/db.py`; jobs are `job.json` files.
- Creator-facing errors: `raise RuntimeError("What happened. What to do.")`, shown as-is; technical detail via
  `print()` / `traceback.print_exc()`. Long steps call `progress(pct, "Short message")`.
- **Nothing blinks on polls or saves**: draw with `setHTML(el, html)` (only when changed), reload a showing tool quietly
  (`load(true)`; "Getting..." only the first time), keep the Twick timeline for the same Short (`edTlFor`), swap a
  remade video under the last frame (`edSwapVideo`, `#edFreeze`). `check_editor` fails on a blink.
- Settings live in `.env` (`os.getenv(NAME, default)`), each documented in `.env.example` and the README.
- **Never commit secrets** (`.env`, `client_secret.json`, `token.json`, `data/`). Tokens are encrypted (`TOKEN_KEY`, else
  `data/token_key`; `accounts/token_box.py`: never store a token without `seal()`); `data/secret_key` signs cookies.
  No media in git (`jobs/`, `_test/`, font files ignored).
- After Python changes: `python -m compileall -q app.py settings.py pipeline youtube accounts web` and start the app once.

## Testing without burning API quota

**Test the code and the UI.** After the suites, look at every touched screen in a real browser (Playwright screenshots):
light and dark; 1440, 1180, 900 and 390 px; and with a vlog being made (the progress card). Nothing cut off, covered or
sideways-scrolling, no page errors, every icon shows (32). Offline sandbox: load fonts locally (npm `material-symbols`,
`@fontsource/*`) or icons show as names. Report UI problems found, even old ones; fix them only after Saumya or Nesh
says yes.

| Suite | Run | Covers | Time |
|---|---|---|---|
| Fast | `python -m unittest discover -s tests -t .` | every feature through the real routes; creator journeys (`test_flows.py`) | ~90 s |
| System | `python -m unittest discover -s tests/system -t . -p "system_*.py"` | the real FFmpeg pipeline and the real server over HTTP | ~5 min |
| Browser | `python -m tests.browser.check_editor` (also `check_drafts`, `check_text`, `check_accounts`, `check_first_import`; need `pip install playwright` + `python -m playwright install chromium`) | Chromium against the real server and FFmpeg | ~3-5 min each |
| A/B | `python -m tests.ab.compare [encoder captions looks slots whisper]` | options side by side (speed, size, SSIM, contrast, slots, speech settings + click time) | ~2 min |
| Stress | `python -m tests.stress.stress [--users 25 --seconds 60 --vlogs 1]`; live: `... live --url https://<domain> --email <test account>` (read-only, stops itself) | many users at once: p50 / p95, errors, memory, threads | 1-5 min |

Server: `sudo bash /opt/pitcrew/app/deploy/test.sh [fast|system|ab|stress|live|all]` (as `pitcrew`, low priority,
throwaway folders). `update.sh` runs the fast suite before every restart.

- **`tests/_env.py` comes first in every test file**: no `.env`, every `.env.example` setting removed, database / jobs /
  invites in a temp folder, `RETENTION_OFF=1`. New settings go in `.env.example` (then they're cleared automatically).
- **`tests/fakes.py` is the outside world**: real `ai_json()` against a fake Gemini client that answers by prompt
  (`AI.fail(code, msg)`); in-memory YouTube channel + strict Analytics fake (22b); in-memory Instagram
  (`instagram.http.call`); email to `OUTBOX`; users confirmed unless `new_user(verified=False)`. `fast()` swaps
  transcription, editing, thumbnails for stand-ins (`SLOW.render` / `SLOW.transcribe` slow them); the system suite keeps
  the real ones (`PITCREW_REAL_MEDIA=1`). A new prompt needs a `FakeAI.kind()` branch; a new outside call needs a fake.
- `test_page_scripts.py` runs `node --check` on every page script and checks looked-up ids exist.
- Add a test with every fix.
- Handy: `ffmpeg -ss 300 -i long.mp4 -t 90 -c copy test90.mp4`; frames via `ffmpeg -ss 1.2 -i jobs/<id>/short_1.mp4
  -frames:v 1 f.jpg`. `X264_PRESET` veryfast (CRF 18) = 2.5× faster than medium, SSIM 0.994; `ultrafast` and
  `WHISPER_MODEL=base` for quick testing.

## Working together (two people)

- **Exactly three branches**: `saumya`, `nesh`, `main`; never create or delete others. `main` always runs. Push your
  branch, open a PR into `main`, let the other look. **Never merge into `main` locally or push to it**: only PRs merged
  on GitHub by Saumya or Nesh.
- **No AI attribution in git**: never `Co-Authored-By: Claude ...`, `Claude-Session: ...`, "Generated with Claude Code"
  or similar in commits or PRs (history was cleaned, Oct 2026). Commits are authored by Saumya or Nesh.
- Before starting: `git checkout <yours> && git fetch origin && git merge origin/main && git push`.
- Mention `requirements.txt` changes in the PR. Each person keeps their own `.env`, `client_secret.json`, `data/`.
- Different features = different files; a shared-file change stays small and is mentioned in the PR.

## Known limits

- Transcription on CPU (`small`): ~9 min per 40-min vlog on an M-series Mac before batching (~half now); much slower on
  the 2-core server (move to a hosted Whisper, e.g. Groq, is an option on hold).
- Low-resolution sources give soft Shorts. New YouTube API projects upload **private** until Google's audit passes.
  Custom Shorts thumbnails only work on channels YouTube enabled.
- A vlog prepared for YouTube that had Shorts made before uploading can't be uploaded from Pit Crew (opens its Shorts'
  review page); it shows on neither Videos nor Drafts' Vlogs tab.
- UI ideas waiting for a yes: open on Drafts when nothing is posted; "← Drafts" + the vlog name on the review page; vlog thumbnails on Drafts' group heads; hide the "coming"
  timeline rows.
