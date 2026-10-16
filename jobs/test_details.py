"""Tests for details pulled out by the local writer (details.py, jobs.build_with_details), with a fake writer:
no Ollama, no installed apps needed. python3 jobs/test_details.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BRAIN_DETAILS"] = "1"
import details  # noqa: E402
import jobs  # noqa: E402


class Ground(unittest.TestCase):
    def test_only_what_was_said(self):
        f = details.ground("open-app", {"app": "Spotify", "screen": "bottom"}, "get spotify going")
        self.assertEqual(f, {"app": "Spotify", "screen": ""})                       # no screen was said
        f = details.ground("send-file", {"device": "laptop", "name": "<user>", "kind": "video"}, "throw my newest screen grab on the lap top")
        self.assertEqual((f["name"], f["kind"]), ("", ""))                          # made-up name and kind
        f = details.ground("open-file", {"name": "tavern light", "kind": "folder"}, "the example-rpg folder")
        self.assertEqual(f["name"], "tavern light")                                 # close spelling counts

    def test_projects_and_actions(self):
        f = details.ground("start-claude", {"project": "example-classifier"}, "start a claude on the moon base project")
        self.assertEqual(f["project"], "none")
        f = details.ground("start-claude", {"project": "example-flights"}, "get a helper going on the flight thing")
        self.assertEqual(f["project"], "example-flights")
        f = details.ground("desktop", {"action": "volume-up", "number": 80, "words": "", "screen": ""}, "turn my brightness up")
        self.assertEqual(f["action"], "none")                                       # brightness is not volume
        f = details.ground("desktop", {"action": "reminder", "number": 0, "words": "x", "screen": ""}, "remind me to x")
        self.assertEqual(f["action"], "none")                                       # no time said

    def test_as_text(self):
        self.assertEqual(details.as_text("open-app", {"app": "spotify", "screen": "left"}), "open spotify on my left screen")
        self.assertEqual(details.as_text("send-file", {"device": "laptop", "name": "newest", "kind": "screenshot"}),
                         "send the latest screenshot to the laptop")
        self.assertEqual(details.as_text("send-file", {"device": "", "name": "map", "kind": ""}), None)
        self.assertEqual(details.as_text("tv", {"action": "none"}), None)


class WithDetails(unittest.TestCase):
    def test_rules_first(self):
        def never(*a):
            raise AssertionError("the writer must not be asked when the word rules found it")
        r = jobs.build_with_details("tv", "turn the tv down", fill=never)
        self.assertEqual((r["details"], r["job"]["args"]), ("rules", {"action": "down"}))

    def test_writer_fills_what_rules_missed(self):
        r = jobs.build_with_details("tv", "the telly is way too loud", fill=lambda *a: {"action": "down"})
        self.assertEqual((r["details"], r["job"]["args"]), ("local", {"action": "down"}))
        r = jobs.build_with_details("music", "get rid of this song", fill=lambda *a: {"action": "Next"})
        self.assertEqual((r["details"], r["job"]["args"]), ("local", {"action": "Next"}))

    def test_nothing_useful_keeps_the_rules_answer(self):
        r = jobs.build_with_details("tv", "the telly is weird", fill=lambda *a: {"action": "none"})
        self.assertEqual((r["kind"], r["details"]), ("answer", "none"))
        r = jobs.build_with_details("tv", "the telly is weird", fill=lambda *a: None)   # not loaded or too slow
        self.assertEqual(r["kind"], "answer")

    def test_switched_off(self):
        os.environ["BRAIN_DETAILS"] = "0"
        try:
            r = jobs.build_with_details("tv", "the telly is way too loud", fill=lambda *a: {"action": "down"})
            self.assertEqual((r["kind"], r["details"]), ("answer", "rules"))
        finally:
            os.environ["BRAIN_DETAILS"] = "1"


if __name__ == "__main__":
    unittest.main()
