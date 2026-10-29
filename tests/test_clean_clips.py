"""Clean clips (pipeline/clean_clip.py, web/clean_clips.py): deleting a vlog's video first keeps each draft's moment and
30 s either side; after that Captions, Reframe, the hook and AI Edit / Trim (inside that reach) remake the Short from
its clip, at the right offset and face position; posted Shorts get none; Try again still needs the vlog; the clip goes
with its Short."""
from tests import fakes as F

import unittest

from settings import JOBS_DIR


class CleanClips(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())
        self.jid, st = F.make_shorts(self.c, 150, 2)
        self.s, self.t = st["shorts"][0], st["shorts"][1]
        self.dir = JOBS_DIR / self.jid

    def short(self, idx=None):
        idx = self.s["idx"] if idx is None else idx
        return F.wait(lambda: (x := next(y for y in F.job_json(self.jid)["shorts"] if y["idx"] == idx))
                      and not x.get("retrying") and x, what="remade")

    def gone(self):
        self.assertEqual(self.c.post(f"/api/vlogs/{self.jid}/delete-video").status_code, 200)
        self.assertEqual(list(self.dir.glob("source.*")), [])

    def test_drafts_get_a_clip_posted_ones_dont(self):
        from web.store import LOCK, JOBS, load_job
        with LOCK:
            job = load_job(self.jid)
            job["uploads"] = [{"idx": self.t["idx"], "video_id": "x", "channel": "c"}]
            JOBS[self.jid] = job
        self.gone()
        me, other = self.short(), self.short(self.t["idx"])
        clip = me["clip"]
        self.assertTrue((self.dir / clip["file"]).is_file())
        self.assertEqual((clip["from"], clip["to"]), (max(0, round(me["start"] - 30, 3)), min(150, round(me["end"] + 30, 3))))
        self.assertNotIn("clip", other)

    def test_editing_carries_on_from_the_clip(self):
        idx = self.s["idx"]
        self.gone()
        clip = self.short()["clip"]
        # every tool says it can still change it; AI Edit / Trim reach only as far as the clip
        info = self.c.get(f"/api/ai-edit/{self.jid}/{idx}").json
        self.assertTrue(info["can_apply"] and info["clip"])
        self.assertEqual(info["reach"], [clip["from"], clip["to"]])
        self.assertTrue(self.c.get(f"/api/captions/{self.jid}/{idx}").json["can_apply"])
        self.assertTrue(self.c.get(f"/api/reframe/{self.jid}/{idx}").json["can_apply"])
        # the page's pictures come from the clip, with its offset
        p = self.c.post(f"/api/preview/{self.jid}", json={"idx": idx}).json
        self.assertEqual((p["status"], p["url"], p["offset"]), ("clip", f"/media/{self.jid}/{clip['file']}", clip["from"]))
        self.assertEqual(self.c.get(p["url"]).status_code, 200)
        # a cut, reaching past the clip: kept inside it, rendered from it at its offset
        s, e = self.s["start"], self.s["end"]
        r = self.c.post(f"/api/ai-edit/{self.jid}/{idx}/apply", json={"pieces": [[s - 100, s + 5], [s + 8, e + 100]]})
        self.assertEqual(r.status_code, 200, r.json)
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertEqual((me["start"], me["end"]), (clip["from"], clip["to"]))
        self.assertEqual((F.RENDERED[-1]["src"], F.RENDERED[-1]["offset"]), (clip["file"], clip["from"]))
        # captions, the hook and the framing remake it too
        self.assertEqual(self.c.post(f"/api/captions/{self.jid}/{idx}", json={"captions": {"preset": "pop"}, "remake": True}).status_code, 200)
        self.assertFalse(self.short().get("retry_error"))
        self.c.post(f"/api/hook/{self.jid}/{idx}", json={"mode": "text", "text": "Wait for it"})
        me = self.short()
        self.assertFalse(me.get("retry_error"), me.get("retry_error"))
        self.assertEqual(me["hook"], "Wait for it")
        r = self.c.post(f"/api/reframe/{self.jid}/{idx}", json={"reframe": {"layout": "fit"}, "remake": True})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.short()["reframe"]["layout"], "fit")
        self.assertEqual(F.RENDERED[-1]["src"], clip["file"])

    def test_face_position_is_scaled_into_the_clip_and_back(self):
        from web.store import update_short
        idx = self.s["idx"]
        self.gone()
        clip = self.short()["clip"]
        update_short(self.jid, idx, cx=1000, clip={**clip, "scale": 0.5})  # (a 4K vlog: its clip is half as wide)
        self.c.post(f"/api/hook/{self.jid}/{idx}", json={"mode": "text", "text": "Big news"})
        me = self.short()
        self.assertEqual(F.RENDERED[-1]["cx"], 500)  # in the clip's pixels
        self.assertEqual(me["cx"], 1000)             # kept in the vlog's

    def test_what_still_needs_the_vlog(self):
        idx = self.s["idx"]
        self.gone()
        r = self.c.post(f"/api/retry/{self.jid}/{idx}", json={})
        me = self.short()
        self.assertTrue(r.status_code != 200 or me.get("retry_error"), "Try again needs another moment of the vlog")
        # no clip (an older Short): as before, nothing can be remade
        from web.store import update_short
        (self.dir / me["clip"]["file"]).unlink()
        update_short(self.jid, idx, clip=None)
        self.assertFalse(self.c.get(f"/api/ai-edit/{self.jid}/{idx}").json["can_apply"])
        self.assertFalse(self.c.get(f"/api/captions/{self.jid}/{idx}").json["can_apply"])

    def test_the_clip_goes_with_its_short(self):
        from web.retention import _short_files
        self.gone()
        me = self.short()
        self.assertIn(self.dir / me["clip"]["file"], _short_files(self.dir, me))


if __name__ == "__main__":
    unittest.main()
