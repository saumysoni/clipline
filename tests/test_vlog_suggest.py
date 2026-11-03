"""AI suggestions for a video's title, description and tags, with a request in the creator's words (web/vlog_suggest.py)."""
from tests import _env  # noqa: F401  (first: clean settings)

import unittest

from tests import fakes as F


class Suggest(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()
        self.c = F.client(F.new_user())
        up = F.upload(self.c, F.test_video(60))
        self.jid = self.c.post("/api/vlog/start", data={"upload": up}).json["id"]
        F.wait(lambda: self.c.get(f"/api/status/{self.jid}").json["status"] == "ready", timeout=30, what="ready")

    def ask(self, **body):
        return self.c.post(f"/api/vlog/{self.jid}/suggest", json=body)

    def test_titles_drop_hashtags_and_numbers_not_said(self):
        r = self.ask(field="title", ask="make it funny", title="Old title")
        self.assertEqual(r.json["items"], ["We got lost", "A new way up the hills"])

    def test_description_keeps_the_chapter_lines_and_drops_invented_ones(self):
        r = self.ask(field="description", description="Old words.\n0:00 Intro\n1:30 The hills\n2:00 Home")
        self.assertEqual(r.json["items"], ["We got lost in the hills.\n\n0:00 Intro\n1:30 The hills\n2:00 Home"])

    def test_tags_are_lists_cleaned_like_the_field(self):
        items = self.ask(field="tags", tags=["old"]).json["items"]
        self.assertEqual(items[0], ["hills", "road trip", "market"])
        self.assertEqual(len(items), 2)

    def test_nothing_saved_until_picked(self):
        before = F.job_json(self.jid)["vdraft"]["title"]
        self.ask(field="title", title="Typed but not saved")
        self.assertEqual(F.job_json(self.jid)["vdraft"]["title"], before)

    def test_bad_field_ai_trouble_and_someone_elses_video(self):
        self.assertEqual(self.ask(field="thumbnail").status_code, 400)
        F.AI.fail(400, "API key not valid")
        r = self.ask(field="title")
        self.assertIn(r.status_code, (400, 503))
        self.assertNotIn("API key", r.json["error"])
        other = F.client(F.new_user())
        self.assertIn(other.post(f"/api/vlog/{self.jid}/suggest", json={"field": "title"}).status_code, (403, 404))


if __name__ == "__main__":
    unittest.main()
