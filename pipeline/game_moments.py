"""
Game Mode, step 2: one score per second from the signals (pipeline/game_signals.py), the best moments, and montages.

Scoring: each signal is normalised **within this stream** (robust: its median and spread), so a loud streamer, a quiet
one or a stream with no game sound are compared with themselves. A signal that barely moves in this stream (no game
sound, a silent streamer, no police) is left out of the score instead of pulling it down: the score is the weighted
average of the signals that are alive here. Events (WASTED, MISSION PASSED, more wanted stars) lend their weight to the
seconds before and after them (game config "events").

Moments: peaks at least clips.peak_gap apart, grown while the score stays above half the peak, clips.pre / clips.post
of build-up and follow-through, merged when closer than clips.merge_gap, between clips.min and clips.max long.

Montages: the best moments of one stretch of play (a chase or a mission: moments closer than montage.group_gap, the
whole stretch at most montage.max_span) stitched in order, each part at most montage.segment_max, montage.target long.
The span is capped on purpose: a montage's clean clip, thumbnail frames and the editor's Trim strip all reach from its
first part to its last (CLAUDE.md gotcha 35); "best of the whole session" waits for one clean clip per part.

Each moment: {"start", "end", "pieces": [[a, b], ...], "score", "why": [signal names], "segments": [{start, end,
score, why}]} in stream seconds. No web code here.
"""

ALWAYS_ON = 0.5  # an event signal on in more than this share of the stream is ignored
WEAK = 0.25      # a moment scoring under this share of the best one isn't a highlight
SIGNALS = ("loud", "loud_jump", "motion", "cuts", "chase", "stars_up", "wasted", "passed", "keywords")
NAMES = {"loud": "loud", "loud_jump": "sudden noise", "motion": "fast action", "cuts": "quick cuts",
         "chase": "police chase", "stars_up": "wanted level up", "wasted": "wasted",
         "passed": "fire or gold flash",
         "keywords": "big reaction"}


def _median(v):
    s = sorted(v)
    return s[len(s) // 2] if s else 0.0


def normalise(v):
    """0-1 per second: how far above this stream's usual level, in robust spreads (MAD), capped at 3. None = flat
    (the signal doesn't move here: left out of the score)."""
    if not v:
        return None
    med = _median(v)
    mad = _median([abs(x - med) for x in v]) * 1.4826
    top = max(v)
    if top - med < 1e-6:
        return None
    spread = max(mad, (top - med) / 6.0, 1e-6)  # (mostly flat with a few peaks: MAD is ~0, so use the peaks' height)
    return [min(1.0, max(0.0, (x - med) / spread / 3.0)) for x in v]


def _smooth(v, r=1):
    return [sum(v[max(0, k - r):k + r + 1]) / len(v[max(0, k - r):k + r + 1]) for k in range(len(v))]


def _spread_events(flags, before, after):
    """An event at second k lights k-before .. k+after (the action that led to it and what follows)."""
    out = [0.0] * len(flags)
    for k, f in enumerate(flags):
        if f:
            for j in range(max(0, k - before), min(len(flags), k + after + 1)):
                out[j] = max(out[j], f)
    return out


NEAR_CHASE = 10


def raw_signals(ps, game):
    """The scored signals, per second, from game_signals.per_second()."""
    n = len(ps["motion"])
    th, ev = game["thresholds"], game["events"]
    loud = ps["loud"]
    known = [x for x in loud if x is not None]
    floor = min(known) if known else -70.0
    loud = [x if x is not None else floor for x in loud]
    base = [_median(loud[max(0, k - 30):k]) if k else loud[0] for k in range(n)]
    stars = _smooth(ps["stars"], 1)
    # the wanted corner's white also catches city lights and sky: a rise only counts with the police near (+-NEAR_CHASE s)
    police = ps["police"]
    chased = [any(p > 0 for p in police[max(0, k - NEAR_CHASE):k + NEAR_CHASE + 1]) for k in range(n)]
    stars_up = [1.0 if k >= 5 and stars[k] - stars[k - 5] > 0.02 and chased[k] else 0.0 for k in range(n)]
    # a grey picture that isn't the pause map (thin lines everywhere) or a black loading screen: the death screen (GTA
    # Online's WASTED is white, story mode's red: the colour isn't needed). Streams saved before Nov 17 lack edges.
    edges, bright = ps.get("edges") or [0.0] * n, ps.get("bright") or [1.0] * n
    wasted = [1.0 if g and e < th.get("map_edges", 0.17) and b > th.get("dark", 0.2) else 0.0
              for g, e, b in zip(ps["grey"], edges, bright)]
    passed = [1.0 if g >= th["word"] and not gr else 0.0 for g, gr in zip(ps["gold"], ps["grey"])]
    return {
        "loud": loud if known else [0.0] * n,
        "loud_jump": [max(0.0, x - b) for x, b in zip(loud, base)] if known else [0.0] * n,
        "motion": _smooth(ps["motion"], 1),
        "cuts": _smooth(ps["cuts"], 2),
        "chase": [min(1.0, p / th["police"]) for p in ps["police"]],
        "stars_up": _spread_events(stars_up, *ev["stars_up"]),
        "wasted": _spread_events(wasted, *ev["wasted"]),
        "passed": _spread_events(passed, *ev["passed"]),
        "keywords": _smooth(ps["keywords"], 2),
    }


def score(ps, game):
    """(score per second 0-1, {signal: 0-1 per second or None when flat})."""
    raw = raw_signals(ps, game)
    norm = {}
    for k, v in raw.items():
        if k in ("wasted", "passed", "stars_up", "chase"):  # already 0-1 and meaningful as they are
            # on in most of the stream = says nothing about any moment (a HUD overlay in that corner, another game mode)
            norm[k] = v if any(x > 0 for x in v) and sum(v) / len(v) < ALWAYS_ON else None
        else:
            norm[k] = normalise(v)
    w = game["weights"]
    alive = {k: v for k, v in norm.items() if v is not None and w.get(k, 0) > 0}
    n = len(ps["motion"])
    if not alive:
        return [0.0] * n, norm
    total = sum(w[k] for k in alive)
    s = [sum(w[k] * alive[k][t] for k in alive) / total for t in range(n)]
    return _smooth(s, 1), norm


def _why(norm, a, b, weights=None, top=2):
    """The signals that made a..b stand out, the ones that count most first."""
    found = []
    for k, v in norm.items():
        if v is None:
            continue
        part = v[int(a):int(b) + 1]
        if part and max(part) >= 0.5:
            found.append((max(part) * (weights or {}).get(k, 1.0), k))
    return [k for _, k in sorted(found, reverse=True)[:top]]


def candidates(s, norm, game, duration):
    """The best moments, highest score first (up to clips.candidates), each as described at the top."""
    c = game["clips"]
    n = len(s)
    order = sorted(range(n), key=lambda k: -s[k])
    peaks = []
    for k in order:
        if s[k] <= 0 or len(peaks) >= c["candidates"] * 3:
            break
        if all(abs(k - p) >= c["peak_gap"] for p in peaks):
            peaks.append(k)
    spans = []
    usual = _median(s)
    for p in peaks:
        half = usual + (s[p] - usual) / 2  # grown while it stays well above this stream's usual level
        a, b = p, p
        while a > 0 and s[a - 1] >= half and p - a < c["max"]:
            a -= 1
        while b < n - 1 and s[b + 1] >= half and b - p < c["max"]:
            b += 1
        a, b = max(0.0, a - c["pre"]), min(float(duration), b + 1 + c["post"])
        if b - a < c["min"]:  # too short: grow around the peak
            grow = (c["min"] - (b - a)) / 2
            a, b = max(0.0, a - grow), min(float(duration), b + grow)
        if b - a > c["max"]:  # too long: keep the part around the peak
            a = max(a, min(p - c["max"] * 0.6, b - c["max"]))
            b = a + c["max"]
        spans.append([a, b, s[p]])
    spans.sort()
    merged = []
    for a, b, sc in spans:
        if merged and a - merged[-1][1] < c["merge_gap"] and b - merged[-1][0] <= c["max"]:
            merged[-1] = [merged[-1][0], max(b, merged[-1][1]), max(sc, merged[-1][2])]
        elif merged and a < merged[-1][1]:  # overlapping but too long together: keep the better one
            if sc > merged[-1][2]:
                merged[-1] = [a, b, sc]
        else:
            merged.append([a, b, sc])
    out = [{"start": round(a, 2), "end": round(b, 2), "pieces": [[round(a, 2), round(b, 2)]], "score": round(sc, 4),
            "why": _why(norm, a, b, game["weights"])} for a, b, sc in merged if b - a >= c["min"] * 0.5]
    for m in out:
        m["segments"] = [{"start": m["start"], "end": m["end"], "score": m["score"], "why": m["why"]}]
    out.sort(key=lambda m: -m["score"])
    best = out[0]["score"] if out else 0
    return [m for m in out if m["score"] >= best * WEAK][:c["candidates"]]


def montages(moments, s, norm, game):
    """Montages (best parts of one stretch of play), best first. Each is a moment with several pieces."""
    mc = game["montage"]
    lo, hi = mc["target"]
    groups, cur = [], []
    for m in sorted(moments, key=lambda m: m["start"]):
        if cur and (m["start"] - cur[-1]["end"] > mc["group_gap"] or m["end"] - cur[0]["start"] > mc["max_span"]):
            groups.append(cur)
            cur = []
        cur.append(m)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        if len(g) < mc["min_segments"]:
            continue
        parts = []
        for m in g:  # each moment's best stretch, at most segment_max long, around its peak
            a, b = m["start"], m["end"]
            if b - a > mc["segment_max"]:
                best = max(range(int(a), max(int(a) + 1, int(b - mc["segment_max"]) + 1)),
                           key=lambda t: sum(s[int(t):int(t + mc["segment_max"])]))
                a, b = float(best), float(best) + mc["segment_max"]
            parts.append({"start": round(a, 2), "end": round(b, 2), "score": m["score"], "why": m["why"]})
        while sum(p["end"] - p["start"] for p in parts) > hi and len(parts) > mc["min_segments"]:
            parts.remove(min(parts, key=lambda p: p["score"]))  # over the target: drop the weakest
        total = sum(p["end"] - p["start"] for p in parts)
        if total < lo * 0.5:
            continue
        parts.sort(key=lambda p: p["start"])
        pieces = [[p["start"], p["end"]] for p in parts]
        out.append({"start": pieces[0][0], "end": pieces[-1][1], "pieces": pieces, "montage": True,
                    "score": round(sum(p["score"] for p in parts) / len(parts), 4),
                    "why": sorted({w for p in parts for w in p["why"]}, key=lambda w: list(NAMES).index(w))[:3],
                    "segments": parts})
    out.sort(key=lambda m: -m["score"])
    return out


def with_context(m, segments, game, duration, lo=0.0, hi=None):
    """A single moment grown to whole sentences: it starts where what's being said starts (the setup, up to
    clips.context_before s earlier, sentence by sentence while they follow on) and ends where the sentence going on at
    its end ends (up to clips.context_after s later), within clips.max and never past lo..hi (its neighbours: growing
    into them would make it a repeat). segments: transcript.json "segments"."""
    c = game["clips"]
    hi = float(duration) if hi is None else hi
    a, b = m["start"], m["end"]
    first = a
    while True:  # back to the start of the sentence going on, then of ones running into it
        prev = [g for g in segments if g["s"] < a and g["e"] >= a - 1.0 and first - g["s"] <= c.get("context_before", 8)]
        if not prev:
            break
        a = min(g["s"] for g in prev)
    nxt = [g for g in segments if g["s"] < b < g["e"] and g["e"] - b <= c.get("context_after", 4)]
    if nxt:
        b = max(g["e"] for g in nxt)
    a, b = max(0.0, lo, min(a, m["start"])), min(float(duration), hi, max(b, m["end"]))
    if b - a > c["max"]:
        a = b - c["max"]
    a, b = round(a, 2), round(b, 2)
    return {**m, "start": a, "end": b, "pieces": [[a, b]],
            "segments": [{**g, "start": a, "end": b} for g in m.get("segments") or []]}


def all_with_context(found, segments, game, duration):
    """with_context() for every single moment, each kept clear of the others."""
    spans = sorted((m["start"], m["end"]) for m in found)
    out = []
    for m in found:
        lo = max([b for a, b in spans if b <= m["start"]], default=0.0)
        hi = min([a for a, b in spans if a >= m["end"]], default=float(duration))
        out.append(with_context(m, segments, game, duration, lo, hi))
    return out


def plan(ps, game, count):
    """What to make for `count` Shorts: (moments best first, montages best first, the score per second). The caller
    (and the AI check) chooses among them; plan() never asks the AI."""
    s, norm = score(ps, game)
    found = candidates(s, norm, game, ps["duration"])
    return found, montages(found, s, norm, game), s


def label(m):
    """A plain label from the signals, for when the AI check isn't there: "Police chase · sudden noise"."""
    why = [NAMES.get(w, w) for w in m.get("why") or []]
    text = " · ".join(why) if why else "big moment"
    if m.get("montage"):
        return ("Best of the chase" if "chase" in (m.get("why") or []) else "Best bits") + ": " + text
    return text[:1].upper() + text[1:]
