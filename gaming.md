# Pit Crew Game Mode: build spec (v1, GTA only)

Build the basic Game Mode for Pit Crew (people see "Pit Crew"; the code may say clipline, CLAUDE.md "Names"): a user uploads a recorded GTA stream, and the system finds highlight moments and renders vertical Shorts/Reels, including montages stitched from different timestamps. Test on GTA 5 footage now; GTA 6 support is a config swap later.

## Status (Nov 16, 2026)

**Stage 1 built** (not committed): signals, scoring, montages, the AI check with its fallback, facecam Split / a crop
that follows the action, the run, the setup form's "What's in this video?" choice, tests (`tests/test_game_mode.py`),
CLAUDE.md gotcha 39. Since Nov 17: token logging per job (`job["game_ai"]`) and the accept / reject log
(`job["game_log"]`, `web/game_feedback.py`). Tested only on generated videos: **the GTA V screen positions and colours in
`pipeline/games/gta5.json` are estimates until checked on real streams.**

**Stage 2 next:** picture-in-picture, HUD overlays (minimap / health / weapon inside the vertical clip), a facecam box
of its own in the editor (drag / resize; Split's zoom stops at 2.5 today), Try again that picks from the gameplay
(today it uses the transcript), one clean clip per montage part (then "best of the session" montages), money cost from the tokens (prices per
model), measuring times
on a real 1-3 hour stream, then 6 hours (Whisper only on the candidate windows).

## Constraints

- **GTA only.** No other games in v1. Valorant and multiplayer games come later (separate reference code).
- **No GPU.** Everything runs on CPU. No object tracking or segmentation models.
- **Desktop only.** Game Mode lives in Advanced Editing; mobile shows an "open on laptop" notice.
- **LLM provider: OpenAI for now.** Every model call goes through the existing `ai_json()` (`pipeline/ai.py`, gotcha 11): it already switches providers, retries and takes images. Anthropic later = a third provider there, not a new interface. Each new prompt needs a branch in `tests/fakes.py` `FakeAI.kind()`.
- **Recorded VODs only.** No live clipping.
- **Never send the whole video to the LLM.** Cheap CPU signals scan everything; the LLM sees only a few frames from top candidates.

## Pipeline

1. **Upload**: the existing resumable upload in pieces (`web/video_upload.py`) or a video link (`pipeline/source_link.py`). Keep the original for rendering.
2. **Job**: the existing vlog queue (`web/job_queue.py`, `kind: "game"`), run at the background priority (gotcha 37), with Pause / Stop (gotcha 36). Report progress per stage with `step()`.
3. **Proxy**: FFmpeg makes a low-res proxy (~480p) plus extracted audio for analysis.
4. **Audio analysis (CPU)**: per-second scores for loud events (sirens, gunfire, explosions, crashes) via a small pretrained audio tagger plus loudness spikes; streamer excitement (mic loudness/pitch, laughter, shouting) and keywords from a transcript.
5. **Video analysis (CPU)**:
   - Motion intensity and scene-cut detection (frame difference / FFmpeg scene score).
   - OCR or template matching on fixed HUD regions, 2 frames/sec: wanted stars rising, "Wasted" / "Mission passed" style screens.
   - Minimap check: flashing red/blue police dots = chase signal.
6. **Score**: combine signals into one score per second with weights from the game config. Signals that are weak in a given video (e.g. no game audio, silent streamer) must not sink the score; normalize per video.
7. **Pick candidates**: find peaks, merge peaks close together, pad with build-up (about 3s before, 2s after).
8. **LLM check (only paid step)**: for the top ~15 candidates, send a few frames each, cropped to the **middle vertical third** at ~480p. The model confirms, ranks, and returns a one-line label (e.g. "police chase ends in crash"). Track token cost per job.
9. **Review**: moments saved in `job.json` like every Short (Drafts, Quick review, the editor); user accepts, rejects, trims, reorders. Log accept/reject in `job.json` to tune weights later.
10. **Render**: FFmpeg cuts from the **original** file (not the proxy) into 9:16, applies layout and HUD overlays, then hands off to Pit Crew's existing captions / hashtags / publish flow.

## Clip data model

A clip is an ordered list of segments: `{start, end, label, score}`. A normal clip is one segment; a montage is many. Same render path for both. In Pit Crew this is a Short's `pieces` (`[[start, end], ...]`, gotcha 30); each segment's label and score sit beside it (e.g. `game_segments`).

## Montage reels

- Stitch top moments from different timestamps into one reel, in order.
- Segments less than ~4s apart merge into one.
- Group by chase/mission using wanted-level changes, mission screens, or long gaps: "best of this chase" or "best of the session".
- Target 30–60s; drop the lowest-scored segments if over.
- FFmpeg concat with hard cuts and a short audio crossfade at each join.

## Layouts (user picks per clip)

| Layout | Shows | Rule |
| --- | --- | --- |
| Split | Game on top half, facecam on bottom half | Only if a facecam is found |
| Gameplay only | Game cropped to 9:16 | Crop follows on-screen motion, not locked to centre |
| Picture-in-picture | Full vertical gameplay, facecam in a corner | Only if a facecam is found |

Facecam box is auto-detected and user-adjustable (drag/resize). No facecam means only Gameplay only.

## HUD overlays

The minimap, health bar, and weapon sit outside the vertical crop. Cut them from fixed regions **of the same frame** and overlay them as small elements inside the vertical clip (FFmpeg crop + overlay). They stay synced to the timestamp automatically.

## Game config (keep it adaptable)

All game-specific values live in one config file per game, e.g. `pipeline/games/gta5.json` and later `gta6.json` (JSON, not YAML: no new dependency):

- HUD regions (minimap, health, weapon, wanted stars) as relative coordinates
- Templates/text for "Wasted", "Mission passed", etc.
- Signal weights and padding values

Switching from GTA 5 to GTA 6 should only mean adding a new config, not changing code.

## Stream length

**v1: up to 3 hours**, the same as every video today (`MAX_VLOG_MINUTES`). The page says "upload up to 3 hours: trim
longer streams into parts". Keep `MAX_UPLOAD_GB` (30) as the hard file limit.

What a stream costs on the current server (2 physical cores, 16 GB, ~84 GB free disk; rough, measure on a real GTA
stream with `deploy/test.sh ab whisper` before promising times):

| Stream | File (1080p, ~6 Mbps) | Full transcription | Game signals on the 480p proxy |
| --- | --- | --- | --- |
| 1 hour | ~2.7 GB | ~15–25 min | a few min |
| 3 hours | ~8 GB | ~45–75 min | ~5–10 min |
| 6 hours | ~16 GB | ~1.5–2.5 h | ~10–20 min |

- Transcription is the slow part, not the game signals. With `JOB_SLOTS=2`, a long stream also delays the next creator.
- Disk: videos are kept 72 h (`KEEP_ORIGINAL_HOURS`); ten 3-hour streams in three days fill the free disk. Watch it.
- **Then 6 hours**: Game Mode stops transcribing the whole stream. The cheap signals scan everything first, then Whisper
  hears only the top ~20 candidate windows (±30 s each: ~20 min of audio instead of 6 h) for keywords and the clips'
  captions. A 6-hour stream then takes ~20–30 min.
- Decide monthly minutes for gamers (`MONTHLY_VLOG_MINUTES`): one 3-hour stream is 180 minutes of a month's allowance.
- Ordinary vlogs stay at 3 hours with a full transcript.

## Fitting it into Pit Crew (review, Nov 2026)

**Reuse what exists:**
- A clip's segments = a Short's `pieces` (gotcha 30); `render_short` already joins far-apart parts with a 20 ms sound
  fade. A montage is a Short with many pieces: no new data model, one render path.
- Layouts: Reframe already has Fill / Fit / **Split** (two stacked views, `pipeline/smart_reframe.py`, gotcha 34). Game
  on top + facecam below = Split with the bottom view on the facecam box. Picture-in-picture = one new layout.
- Signals already computed elsewhere: transcript (faster-whisper), scene changes (`smart_reframe.scene_changes`),
  keyframe reading (`reframe.key_frames`, gotcha 37), template matching (OpenCV, already a dependency, < 5).
- Captions, hooks, hashtags, thumbnails, Drafts, the editor and posting carry over as they are.

**Choices that keep it light on a 2-core server:**
- Audio: start with FFmpeg loudness (`ebur128` / `astats`) + transcript keywords. Add a pretrained tagger only if tests
  show it's needed, and then an ONNX build (YAMNet, small, CPU) after a licence check: not TensorFlow / PyTorch
  (hundreds of MB, ~1 GB memory a run).
- HUD reading: OpenCV template matching on the fixed regions ("Wasted", "Mission passed", wanted stars), not Tesseract
  OCR (a system install).
- Where it lives: a **"Gaming video" choice under + Create / Setup** (finding highlights happens while Shorts are made);
  layout, facecam box and HUD placement are editor tools (desktop only, like the editor).

**Things the plan must handle:**
- Clean clips for montages: when a video is deleted, a draft keeps its first part to its last ±30 s (gotcha 35). A
  montage with parts 2 hours apart would keep a 2-hour clip: make one small clip per part instead.
- Captions and the hook banner placed so they don't cover the facecam (Split / picture-in-picture).
- HUD overlays inside the render's filter chain with a moving crop (`sendcmd`, gotcha 34): needs a system test like
  `tests/system/system_reframe.py`.
- Privacy policy: frames of the creator's video go to OpenAI for the check (gotcha 26).
- Rights: read Rockstar's current video policy before marketing GTA clipping; clipping another streamer's VOD needs
  their permission, as with vlogs.

**Where the code would go:**

| Step | File |
| --- | --- |
| Game rules (HUD regions, templates, weights, padding) | `pipeline/games/gta5.json` |
| Signals per second: loudness, keywords, motion / scene cuts, HUD templates, minimap red/blue | `pipeline/game_signals.py` |
| Score, peaks, merge, padding, montage grouping → moments with `pieces` | `pipeline/game_moments.py` |
| AI check of ~15 candidates (middle-third frames) | `pipeline/game_check.py` through `ai_json()` |
| The run | `web/game_mode.py` (`kind: "game"`), routes there |
| Facecam detection, Split / picture-in-picture, HUD overlays | `pipeline/smart_reframe.py` (new layout) + `pipeline/game_hud.py` |
| Page | `static/js/game-mode.js` (+ CSS / section), one line each in `app.py` and `static/index.html` |
| Accept / reject log | `job.json` |

## Testing

- Nesh will provide GTA 5 stream videos (and GTA 6 later).
- Include quiet videos (low game audio, streamer barely talking) to check visual signals carry the score.
- For each test video, compare detected moments against a quick hand-picked list of the real highlights.
- Log LLM tokens and cost per video. Target: a few cents per 40-minute video.

## Future (not v1)

- Object spotlight: user picks a cop car or NPC, clip zooms/dims/follows it. Needs a GPU tracker (e.g. SAM 2 on serverless GPU).
- Music library via royalty-free provider APIs, auto-ducking game audio, beat-synced montage cuts.
- Valorant using the friend's reference code, then other multiplayer games.
- Twitch chat as a signal; live clipping. (Not import by YouTube / Twitch link: YouTube forbids downloading its videos, gotcha 10, and Twitch's terms are similar. Streamers upload the file or share a Drive / Dropbox / OneDrive link.)
