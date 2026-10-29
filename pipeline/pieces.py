"""
The pieces of the vlog a Short keeps (AI Edit, pipeline/ai_edit.py): moment["pieces"] = [[start, end], ...] in the vlog's
seconds, in order, inside the moment's start..end. No "pieces" (every Short made before AI Edit, and every new one) means
one piece, start..end. Rendering joins the pieces (pipeline/render.py) and the captions follow (timeline()).

The same list is what the editor's timeline (Twick, editor-app/, gotcha 31) reads and writes: clips on the video track,
each a range of the vlog. Trim can reach past the moment; the moment's start..end then grows to fit (web/ai_edit.py).
"""

MIN_PIECE = 0.3  # seconds; anything shorter is dropped (a flash of picture isn't a piece)
JOIN = 0.05      # pieces closer than this are one piece


def normalize(ranges, start, end):
    """Ranges clipped to start..end, sorted, joined where they touch, too-short ones dropped: [(a, b), ...]."""
    out = []
    for r in sorted((float(a), float(b)) for a, b in ranges or []):
        a, b = max(start, r[0]), min(end, r[1])
        if b - a <= 0:
            continue
        if out and a - out[-1][1] <= JOIN:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a >= MIN_PIECE]


def kept(moment):
    """The pieces this Short keeps: [(a, b), ...] (one piece, start..end, when nothing was cut)."""
    s, e = float(moment["start"]), float(moment["end"])
    return normalize(moment.get("pieces") or [(s, e)], s, e) or [(s, e)]


def length(moment):
    """How long the Short is, in seconds (the pieces added up)."""
    if not moment.get("start") and not moment.get("end"):
        return 0.0
    return round(sum(b - a for a, b in kept(moment)), 2)


def subtract(ranges, cuts, start, end):
    """ranges minus cuts (both [(a, b)]), normalized."""
    out = list(ranges)
    for c0, c1 in cuts or []:
        nxt = []
        for a, b in out:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        out = nxt
    return normalize(out, start, end)


def to_short(pieces, t):
    """A vlog time (seconds) as a time in the Short, or None if it was cut."""
    at = 0.0
    for a, b in pieces:
        if a <= t <= b:
            return at + t - a
        at += b - a
    return None


def timeline(moment, words):
    """The Short's words on its own clock: [{"w", "s", "e"}] with times from 0, keeping only words in a kept piece (a
    word counts where its middle is). Other keys of a word are kept ("i": pipeline/render.py). For the captions."""
    pieces, out, at = kept(moment), [], 0.0
    for a, b in pieces:
        for w in words:
            mid = (w["s"] + w["e"]) / 2
            if a <= mid <= b:
                out.append({**w, "s": round(at + max(w["s"], a) - a, 3), "e": round(at + min(w["e"], b) - a, 3)})
        at += b - a
    return out


def said(transcript, moment):
    """What is said in the Short as it is now (cut words left out)."""
    pieces = kept(moment)
    return " ".join(w["w"] for w in transcript["words"] if any(a <= (w["s"] + w["e"]) / 2 <= b for a, b in pieces))
