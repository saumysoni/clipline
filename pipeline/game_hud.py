"""
Game Mode's HUD overlay (gaming.md "HUD overlays"): the minimap sits outside a 9:16 crop of a 16:9 game, so it's cut from
the same frame and laid over the Short. It's part of the one render (pipeline/render.py), so it's always in sync.

moment["hud"] = {"minimap": [x0, y0, x1, y1], "spot", "on", "extras": [{"box", "on"}]} (fractions of the game picture;
the minimap from pipeline/games/<game>.json, extras = fixed corner graphics found in the stream, like an edited
video's scoreboard: game_signals.find_overlays), set by web/game_mode.py. Fractions of iw / ih, so it also works on a Short's clean clip (a
scaled copy, gotcha 35). "on": [[a, b], ...] vlog seconds when the minimap is really in its corner (game_signals "map");
shown only then (an edited video cuts to facecams and real-life shots). No "on" = all the time.

Where (moment["hud"]["spot"]):
  "low"  bottom-left, below the captions (their bottom margin is 560 px of 1920) and above where YouTube / Instagram put
         the title and channel name, clear of the hook banner at the top (a full-height Fill frame)
  "high" top-left, inside a wide view's top corner (smart_reframe "wide": the view starts at (1920 - 1080 / wide) / 2),
         under the hook banner and far from the captions
Extras go in the same row, on their own side of the picture (a scoreboard from the top-right: top-right), stacked
when two share a side, EXTRA_W wide: smaller than in the video, whole, and never cut by the 9:16 crop.
"""
HUD_W = 330  # px on the 1080 x 1920 Short
HUD_X, HUD_Y = 40, 1390
HIGH_W, HIGH_Y = 280, 470
EDGE = 30      # px from the Short's side
EXTRA_W = 240  # an extra's width on the Short
GAP = 16       # between two stacked on one side
BORDER = 4


def _box(region):
    try:
        x0, y0, x1, y1 = (float(v) for v in region)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    return x0, y0, x1, y1


def _ranges(v):
    out = []
    for r in (v if isinstance(v, list) else [])[:200]:
        try:
            a, b = float(r[0]), float(r[1])
        except (TypeError, ValueError, IndexError):
            continue
        if b > a:
            out.append([round(a, 2), round(b, 2)])
    return out


def clean_hud(raw):
    """The HUD settings to keep (None = none)."""
    if not isinstance(raw, dict):
        return None
    out = {"spot": "high" if raw.get("spot") == "high" else "low", "extras": []}
    box = _box(raw.get("minimap"))
    if box:
        out["minimap"] = [round(v, 4) for v in box]
        if "on" in raw:
            out["on"] = _ranges(raw.get("on"))
    for x in (raw.get("extras") if isinstance(raw.get("extras"), list) else [])[:4]:
        b = _box(x.get("box")) if isinstance(x, dict) else None
        if b:
            out["extras"].append({"box": [round(v, 4) for v in b], "on": _ranges(x.get("on"))})
    return out if box or out["extras"] else None


def on_short_clock(on, pieces):
    """The vlog-second ranges `on` as (start, end) on the Short's clock, through its pieces."""
    out, done = [], 0.0
    for a, b in pieces:
        for c, d in on:
            lo, hi = max(a, c), min(b, d)
            if hi > lo + 1e-3:
                out.append((done + lo - a, done + hi - a))
        done += b - a
    return out


def _items(hud, aspect):
    """[(box, on or None, width, x expression, y)] in the order they're laid."""
    high = hud["spot"] == "high"
    y_of = {"left": HIGH_Y if high else HUD_Y, "right": HIGH_Y if high else HUD_Y}
    out = []

    def place(box, on, w, side):
        x0, y0, x1, y1 = box
        h = w * (y1 - y0) / ((x1 - x0) * aspect)
        x = f"{EDGE if high else HUD_X}" if side == "left" else f"W-w-{EDGE}"
        out.append((box, on, w, x, round(y_of[side])))
        y_of[side] += h + GAP
    if "minimap" in hud:
        place(hud["minimap"], hud.get("on"), HIGH_W if high else HUD_W, "left")
    for x in hud["extras"]:
        place(x["box"], x["on"], EXTRA_W, "left" if (x["box"][0] + x["box"][2]) / 2 < 0.5 else "right")
    return out


def with_hud(frame, hud, pieces=None, aspect=16 / 9):
    """The render's picture chain (`frame`: input -> 1080 x 1920, may use labelled pads) with the minimap and the extras
    laid over it, each while it's on screen (`pieces`: the Short's, vlog seconds; aspect: the video's width / height).
    Nothing to lay = `frame` unchanged."""
    hud = clean_hud(hud)
    if not hud:
        return frame
    laid = []
    for box, on, w, x, y in _items(hud, aspect):
        when = ""
        if on is not None:
            spans = on_short_clock(on, pieces or [])
            if not spans:
                continue
            when = ":enable='" + "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans) + "'"
        laid.append((box, w, f"{x}:{y}{when}"))
    if not laid:
        return frame
    k = len(laid)
    chain = [f"split={k + 1}[hudm]" + "".join(f"[huds{i}]" for i in range(k)), f"[hudm]{frame}[hudf0]"]
    for i, (box, w, at) in enumerate(laid):
        x0, y0, x1, y1 = box
        chain.append(f"[huds{i}]crop=iw*{x1 - x0:.4f}:ih*{y1 - y0:.4f}:iw*{x0:.4f}:ih*{y0:.4f},scale={w}:-2,"
                     f"drawbox=c=black@0.7:t={BORDER}[hudi{i}]")
        last = i == k - 1
        chain.append(f"[hudf{i}][hudi{i}]overlay={at}" + (",setsar=1" if last else f"[hudf{i + 1}]"))
    return ";".join(chain)
