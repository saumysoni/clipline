"""Every AI call goes through ai_json(): busy models are retried in rounds, retired ones skipped, limits and bad keys
end in one plain sentence, and answers wrapped in extra words still parse (pipeline/ai.py)."""
from tests import fakes as F

import os
import unittest

from pipeline import ai


PROMPT = "You write on-screen hooks for a YouTube Short."


class Retries(unittest.TestCase):
    def setUp(self):
        F.install()
        F.reset()

    def models(self):
        return [m for _, m in F.AI.calls]

    def test_first_model_answers(self):
        self.assertIn("hooks", ai.ai_json(PROMPT))
        self.assertEqual(self.models(), [ai.FALLBACK_MODELS[0]])

    def test_gemini_model_from_env_first(self):
        os.environ["GEMINI_MODEL"] = "gemini-test-model"
        try:
            ai.ai_json(PROMPT)
        finally:
            os.environ.pop("GEMINI_MODEL")
        self.assertEqual(self.models(), ["gemini-test-model"])

    def test_busy_moves_on_then_rounds(self):
        F.AI.fail(503, "UNAVAILABLE: overloaded")
        ai.ai_json(PROMPT)
        self.assertEqual(self.models(), ai.FALLBACK_MODELS[:2])  # the next model answered
        F.reset()
        F.AI.fail(503, "overloaded", times=len(ai.FALLBACK_MODELS))  # a whole round busy: the next round works
        ai.ai_json(PROMPT)
        self.assertEqual(len(self.models()), len(ai.FALLBACK_MODELS) + 1)

    def test_busy_every_round_says_so(self):
        F.AI.fail(503, "overloaded", times=100)
        with self.assertRaises(RuntimeError) as e:
            ai.ai_json(PROMPT, busy_hint="Try again in a few minutes.")
        self.assertIn("overloaded right now", str(e.exception))
        self.assertIn("Try again in a few minutes.", str(e.exception))
        self.assertEqual(len(self.models()), len(ai.FALLBACK_MODELS) * (1 + len(ai.BUSY_WAITS)))

    def test_retired_models_are_skipped_not_retried(self):
        F.AI.fail(404, "models/x is not found", times=2)
        ai.ai_json(PROMPT)
        self.assertEqual(self.models(), ai.FALLBACK_MODELS[:3])

    def test_limit_and_bad_key(self):
        F.AI.fail(429, "RESOURCE_EXHAUSTED", times=10)
        with self.assertRaises(RuntimeError) as e:
            ai.ai_json(PROMPT)
        self.assertIn("limit", str(e.exception))
        F.reset()
        F.AI.fail(403, "API key not valid")
        with self.assertRaises(RuntimeError) as e:
            ai.ai_json(PROMPT)
        self.assertNotIn("403", str(e.exception))
        self.assertEqual(len(self.models()), 1)  # a refused key stops at once

    def test_no_key_and_unknown_provider(self):
        key = os.environ["GEMINI_API_KEY"]
        os.environ["GEMINI_API_KEY"] = ""
        try:
            with self.assertRaises(RuntimeError) as e:
                ai.ai_json(PROMPT)
            self.assertIn("isn't available", str(e.exception))
        finally:
            os.environ["GEMINI_API_KEY"] = key
        with self.assertRaises(RuntimeError):
            ai.ai_json(PROMPT, provider="claude-9")

    def test_answer_formats(self):
        self.assertEqual(ai.parse_ai_json('```json\n{"a": 1}\n```', "G"), {"a": 1})
        self.assertEqual(ai.parse_ai_json('Sure! Here it is: [1, 2] Hope that helps', "G"), [1, 2])
        with self.assertRaises(RuntimeError):
            ai.parse_ai_json("no json here", "G")

    def test_images_go_with_the_prompt(self):
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, "JPEG")
        got = ai.ai_json(["thumbnail for a YouTube Short", ai.image_part(buf.getvalue())])
        self.assertEqual(got["frame"], 1)


class YouTubeDataAndFreeGemini(unittest.TestCase):
    """A vlog's details read from YouTube go to the AI only where Google's Limited Use rule allows it."""

    def tearDown(self):
        os.environ.pop("GEMINI_PAID", None)
        os.environ.pop("AI_PROVIDER", None)

    def test_context_left_out_on_free_gemini(self):
        from pipeline.vlog_context import vlog_context_block
        from_youtube = {"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "title": "From YouTube", "description": "d"}
        typed = {"title": "Typed by the creator", "description": "mine"}
        self.assertEqual(vlog_context_block(from_youtube), "")
        self.assertIn("Typed by the creator", vlog_context_block(typed))  # the creator's own words are fine
        os.environ["GEMINI_PAID"] = "1"
        self.assertIn("From YouTube", vlog_context_block(from_youtube))
        os.environ.pop("GEMINI_PAID")
        os.environ["AI_PROVIDER"] = "openai"
        self.assertIn("From YouTube", vlog_context_block(from_youtube))  # OpenAI's API doesn't train on it

    def test_moment_prompt_on_free_gemini(self):
        F.install()
        F.reset()
        from pipeline.moments import pick_moments
        seen = []
        real = F.AI.answer
        F.AI.answer = lambda model, contents: (seen.append(contents), real(model, contents))[1]
        try:
            pick_moments(F.transcript_for(150), 1, context={"youtube_url": "https://youtu.be/dQw4w9WgXcQ",
                                                             "title": "Secret YouTube title"})
        finally:
            F.AI.answer = real
        self.assertNotIn("Secret YouTube title", seen[0])


if __name__ == "__main__":
    unittest.main()
