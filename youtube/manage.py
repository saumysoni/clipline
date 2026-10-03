"""
Shorts already on YouTube: their live state, changing the time or title, deleting a replaced one.
"""



def video_states(youtube, ids):
    """Live state of uploaded videos: {id: {"privacy", "publish_at", "title"}}. Missing ids were deleted."""
    out = {}
    ids = [i for i in ids if i]
    for k in range(0, len(ids), 50):
        resp = youtube.videos().list(part="status,snippet", id=",".join(ids[k:k + 50])).execute()
        for it in resp.get("items", []):
            st = it.get("status", {})
            out[it["id"]] = {"privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt"),
                             "title": it.get("snippet", {}).get("title", "")}
    return out


def is_live(state):
    """True once people can see the video (public, or unlisted)."""
    return bool(state) and state.get("privacy") in ("public", "unlisted")


# status fields YouTube lets an app write back (anything else in the reply is read-only)
_STATUS_WRITABLE = ("privacyStatus", "publishAt", "embeddable", "license", "publicStatsViewable",
                    "selfDeclaredMadeForKids", "containsSyntheticMedia")


def reschedule(youtube, video_id, when):
    """Move a scheduled (private) Short to a new time. Raises RuntimeError in plain words."""
    items = youtube.videos().list(part="status", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError("This Short isn't on YouTube any more (was it deleted in YouTube Studio?).")
    st = items[0]["status"]
    if st.get("privacyStatus") != "private":
        raise RuntimeError("This Short is already public, so it can't be scheduled again. "
                           "Change it in YouTube Studio if you need to.")
    body = {k: st[k] for k in _STATUS_WRITABLE if k in st}
    body.update(privacyStatus="private", publishAt=when.isoformat(timespec="seconds"))
    youtube.videos().update(part="status", body={"id": video_id, "status": body}).execute()


def update_title(youtube, video_id, title):
    """Change only the title of an uploaded Short (description, tags and category are kept)."""
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError("This Short isn't on YouTube any more (was it deleted in YouTube Studio?).")
    sn = items[0]["snippet"]
    body = {"title": title[:100], "categoryId": sn.get("categoryId", "22"),
            "description": sn.get("description", ""), "tags": sn.get("tags", [])}
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": body}).execute()


def delete_video(youtube, video_id):
    youtube.videos().delete(id=video_id).execute()
