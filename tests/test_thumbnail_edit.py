"""A draft's thumbnail from Quick review and the editor (web/thumbnail_edit.py): new text, Try again."""
from tests import fakes as F

import unittest

from settings import JOBS_DIR


class ThumbnailEdit(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.u = F.new_user()
        self.c = F.client(self.u)
        self.jid, self.st = F.make_shorts(self.c, 150, 3)

    def short(self, idx=1):
        return next(s for s in F.job_json(self.jid)["shorts"] if s["idx"] == idx)

    def done(self, idx=1):
        return F.wait(lambda: not self.short(idx).get("retrying") and self.short(idx), what="the thumbnail")

    def test_new_text(self):
        before = self.short()["thumb"]
        info = self.c.get(f"/api/thumb/{self.jid}/1").json
        self.assertTrue(info["can_text"] and info["can_again"])
        r = self.c.post(f"/api/thumb-text/{self.jid}/1", json={"line1": "I ate", "line2": "  DOG  meat "})
        self.assertEqual(r.status_code, 200, r.json)
        s = self.done()
        self.assertNotEqual(s["thumb"], before)
        self.assertEqual((s["thumb_line1"], s["thumb_line2"]), ("I ate", "DOG meat"))
        self.assertEqual(self.c.post(f"/api/thumb-text/{self.jid}/1", json={"line1": "x", "line2": ""}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/thumb-text/{self.jid}/1", json={"line2": "y" * 31}).status_code, 400)

    def test_try_again(self):
        before = self.short(2)["thumb"]
        F.THUMB_AVOIDED.clear()
        self.assertEqual(self.c.post(f"/api/thumb-again/{self.jid}/2").status_code, 200)
        s = self.done(2)
        self.assertNotEqual(s["thumb"], before)
        self.assertEqual(len(F.THUMB_AVOIDED), 1)

    def test_try_again_needs_the_video(self):
        for f in (JOBS_DIR / self.jid).glob("source.*"):
            f.unlink()
        r = self.c.post(f"/api/thumb-again/{self.jid}/1")
        self.assertEqual(r.status_code, 400)
        self.assertIn("deleted", r.json["error"])
        self.assertFalse(self.c.get(f"/api/thumb/{self.jid}/1").json["can_again"])

    def test_someone_else_cant(self):
        other = F.client(F.new_user())
        self.assertIn(other.post(f"/api/thumb-again/{self.jid}/1").status_code, (403, 404))


if __name__ == "__main__":
    unittest.main()
