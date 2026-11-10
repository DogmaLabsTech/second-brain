"""Small tests for the check-up pieces (no network, no models): python3 ask/test_ask_units.py
(not `-m unittest ask/…`: that imports the ask/ folder as `ask` instead of ask.py)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp()
import ask  # noqa: E402
import asklog  # noqa: E402
from expand import expanded_document  # noqa: E402


class Expand(unittest.TestCase):
    def test_question_is_searched_as_said(self):
        lines = expanded_document("how do I reload the bar after editing").splitlines()
        self.assertEqual(lines[0], "vec: how do I reload the bar after editing")
        self.assertTrue(lines[1].startswith("vec: how do I reload the bar after editing "))   # <user>'s words -> notes' words
        self.assertLessEqual(len(lines), 2)

    def test_no_word_search_line_by_default(self):
        self.assertFalse(any(l.startswith("lex: ") for l in expanded_document("where is the zebra").splitlines()))

    def test_word_search_line_comes_back_with_the_switch(self):
        import expand
        old = expand.USE_LEX
        try:
            expand.USE_LEX = True
            lines = expanded_document("how do I reload the bar after editing").splitlines()
            self.assertTrue(lines[0].startswith("lex: "))
            self.assertEqual(lines[1], "vec: how do I reload the bar after editing")
            self.assertLessEqual(len(lines), 3)
        finally:
            expand.USE_LEX = old


class SearchCli(unittest.TestCase):
    HITS = [{"path": "/x/a.md", "snippet": "first", "score": 1.4432}, {"path": "/x/b.md", "snippet": "second"}]

    def test_lines_have_no_score_by_default(self):
        import search_cli
        self.assertTrue(all("\t" not in line and " — " in line for line in search_cli.lines(self.HITS)))

    def test_lines_start_with_the_score_when_asked(self):
        import search_cli
        out = search_cli.lines(self.HITS, scores=True)
        self.assertEqual(out[0].split("\t")[0], "1.443")
        self.assertEqual(out[1].split("\t")[0], "0.000")        # no score: 0, never a crash
        self.assertTrue(out[0].endswith("a.md — first"))


@unittest.skipUnless(os.path.exists(os.path.expanduser("~/.config/qmd/index.yml")), "needs your search index config")
class Collections(unittest.TestCase):
    def test_every_indexed_collection_has_a_folder(self):
        """A collection missing here comes back as a qmd:// link, not a note (agent-os and codex, 2026-10-18)."""
        import yaml
        with open(os.path.join(os.path.dirname(HERE), "index", "index.yml")) as f:
            cols = yaml.safe_load(f)["collections"]
        for name, c in cols.items():
            self.assertEqual(ask.COLLECTIONS.get(name), c["path"], name)

    def test_the_notes_live_in_the_brain(self):
        """One brain (2026-10-28): the agent store and the private notes are sections of ~/brain."""
        self.assertEqual(ask.COLLECTIONS["private"], os.path.join(ask.HOME, "brain", "private"))
        self.assertEqual(ask.COLLECTIONS["memory"], os.path.join(ask.HOME, "brain", "agents"))


class LocalOnly(unittest.TestCase):
    """A memory note marked local-only (eval/memory_keep.py) never reaches Haiku; the local writer answers."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(ask.COLLECTIONS, {"memory": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)
        self.sent = []
        for name in ("haiku_write", "local_write"):
            p = mock.patch.object(ask, name, lambda prompt, *a, who=name, **k: self.sent.append(who) or ("ok", 1, 2))
            p.start()
            self.addCleanup(p.stop)

    def hit(self, name, text):
        path = os.path.join(self.tmp.name, name)
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
        return {"path": path, "title": name, "snippet": "s", "line": 1}

    def test_marked_note_goes_to_the_local_writer_only(self):
        hits = [self.hit("a.md", "---\nproject: x\nlocal-only: true\n---\nzorbel lesson\n")]
        self.assertTrue(ask.local_only(hits[0]))
        self.assertTrue(ask.write("q", hits, "auto")[1].startswith("local:"))
        self.assertEqual(self.sent, ["local_write"])
        with self.assertRaises(RuntimeError):
            ask.write("q", hits, "haiku")
        self.assertEqual(self.sent, ["local_write"])

    def test_every_spelling_the_viewer_marks_is_also_blocked_for_the_online_writer(self):
        long_summary = "summary: " + "x" * 5000 + "\n"
        cases = {
            "true": ("---\nlocal-only: true\n---\nbody\n", True),
            "capital": ("---\nlocal-only: True\n---\nbody\n", True),
            "quoted": ("---\nlocal-only: \"true\"\n---\nbody\n", True),
            "after a long line": ("---\n" + long_summary + "local-only: true\n---\nbody\n", True),
            "windows line ends": ("---\r\nlocal-only: true\r\n---\r\nbody\r\n", True),
            "said twice, last wins in the viewer": ("---\nlocal-only: false\nlocal-only: true\n---\nbody\n", True),
            "front matter never closes": ("---\nproject: x\nbody\n", True),
            "false": ("---\nlocal-only: false\n---\nbody\n", False),
            "no key": ("---\nproject: x\n---\nbody\n", False),
        }
        for i, (label, (text, want)) in enumerate(cases.items()):
            with self.subTest(label):
                self.assertEqual(ask.local_only(self.hit("spelling-%d.md" % i, text)), want)

    def test_unreadable_memory_note_counts_as_local_only(self):
        self.assertTrue(ask.local_only(self.hit("gone.md", None)))

    def test_unmarked_and_other_notes_are_not(self):
        self.assertFalse(ask.local_only(self.hit("b.md", "---\nproject: x\npinned: false\n---\nlocal-only: true\n")))
        self.assertFalse(ask.local_only({"path": "/elsewhere/c.md"}))
        ask.write("q", [self.hit("b.md", "---\npinned: false\n---\nbody\n")], "haiku")
        self.assertEqual(self.sent, ["haiku_write"])

    def test_every_private_note_is_local_only_marked_or_not(self):
        with mock.patch.dict(ask.COLLECTIONS, {"private": self.tmp.name + "-private"}):
            hit = {"path": os.path.join(self.tmp.name + "-private", "finance", "bill.md"), "title": "bill",
                   "snippet": "s", "line": 1}
            self.assertTrue(ask.local_only(hit))
            self.assertTrue(ask.write("q", [hit], "auto")[1].startswith("local:"))
            self.assertFalse(ask.local_only({"path": os.path.join(self.tmp.name + "-ish", "a.md")}))
        self.assertEqual(self.sent, ["local_write"])


class OnlineAgents(unittest.TestCase):
    """`brain ask` / `brain search` leave the private section out unless this copy's Deck or Obsidian ran them, with no
    online agent anywhere above (one brain, 2026-10-29; Deck or Obsidian only, 2026-11-10)."""
    def fake_qmd(self, files):
        body = json.dumps({"results": [{"file": f, "title": f, "snippet": "s", "line": 1, "score": 1} for f in files]})
        return mock.patch.object(ask.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body.encode()))

    def test_private_hits_dropped_only_when_hidden(self):
        files = ["qmd://private/finance/bank.md", "qmd://computer/system/top-bar.md"]
        with self.fake_qmd(files), mock.patch.object(ask, "NEWER_DAYS", 0):
            with mock.patch.object(ask, "HIDE_PRIVATE", True):
                self.assertEqual([h["file"] for h in ask.search("bank")], files[1:])
            with mock.patch.object(ask, "HIDE_PRIVATE", False):
                self.assertEqual([h["file"] for h in ask.search("bank")], files)

    def test_hidden_unless_searchlog_says_this_caller_may_read_them(self):
        import searchlog
        with mock.patch.object(searchlog, "private_ok", lambda: True):
            self.assertFalse(ask.private_hidden())
        with mock.patch.object(searchlog, "private_ok", lambda: False):
            self.assertTrue(ask.private_hidden())
        with mock.patch.object(searchlog, "private_ok", side_effect=OSError("no /proc")):
            self.assertTrue(ask.private_hidden())   # can't tell: keep them out

    def test_brain_search_sets_it_from_the_same_check(self):
        import search_cli
        import searchlog
        with mock.patch.object(searchlog, "private_ok", lambda: False), \
                mock.patch.object(search_cli.ask, "HIDE_PRIVATE", False), \
                mock.patch.object(search_cli, "search", return_value=[]), \
                mock.patch.object(search_cli.sys, "argv", ["search_cli.py", "bank"]), \
                contextlib.redirect_stdout(io.StringIO()):
            search_cli.main()
            self.assertTrue(search_cli.ask.HIDE_PRIVATE)


class FirstSentence(unittest.TestCase):
    def setUp(self):
        self.got = []
        ask.EMIT[:] = [self.got.append]

    def tearDown(self):
        ask.EMIT[:] = []

    def test_waits_for_winner_and_question(self):
        f = ask.First()
        f.feed(text="Your Top bar note says restart the shell. Then")
        self.assertEqual(self.got, [])
        f.feed(winner=True)
        self.assertEqual(self.got, [])
        f.feed(question=True)
        self.assertEqual(self.got, [{"event": "first", "text": "Your Top bar note says restart the shell."}])
        f.feed(text="Your Top bar note says restart the shell. Then more. And more.")
        self.assertEqual(len(self.got), 1)

    def test_no_early_sentence_before_it_ends(self):
        f = ask.First()
        f.feed(text="Your Top bar note says restart", winner=True, question=True)
        self.assertEqual(self.got, [])


class Record(unittest.TestCase):
    def test_log_and_rate(self):
        qid = asklog.new_id()
        asklog.log_ask(qid, "q?", {"kind": "answer", "answer": "a.", "writer": "haiku",
                                   "sources": [{"path": "~/x.md"}], "ms": 5, "steps": {}}, "test")
        asklog.rate(qid, "down", "wrong note")
        self.assertEqual(asklog.read(asklog.ASKS)[-1]["id"], qid)
        self.assertEqual(asklog.read(asklog.RATINGS)[-1], {**asklog.read(asklog.RATINGS)[-1], "id": qid, "verdict": "down"})
        self.assertEqual(oct(os.stat(asklog.STATE).st_mode & 0o777), "0o700")
        with self.assertRaises(ValueError):
            asklog.rate(qid, "meh")


class NewerFirst(unittest.TestCase):
    def test_new_note_wins_a_close_call_only(self):
        d = tempfile.mkdtemp()
        old, new = os.path.join(d, "old.md"), os.path.join(d, "new.md")
        for p in (old, new):
            open(p, "w").close()
        os.utime(old, (time.time() - 200 * 86400,) * 2)
        close = ask.newer_first([{"path": old, "score": 0.5}, {"path": new, "score": 0.45}])
        self.assertEqual(close[0]["path"], new)
        clear = ask.newer_first([{"path": old, "score": 1.0}, {"path": new, "score": 0.33}])
        self.assertEqual(clear[0]["path"], old)


class SayAgain(unittest.TestCase):
    """Router upgrade 2: a decider's own "unsure", or the local decider under its sure-bar, gets "Sorry, say that again?"."""

    def run_ask(self, q, intent):
        saved = ask.decide, ask.search, ask.answer_question
        ask.decide = lambda *a, **k: intent
        ask.search = lambda *a, **k: []
        ask.answer_question = lambda *a, **k: (ask.NOT_FOUND, "none")
        try:
            return ask.ask(q)
        finally:
            ask.decide, ask.search, ask.answer_question = saved

    def test_unsure_from_local_decider_or_below_bar(self):
        for intent in ({"label": "unsure", "confidence": 0.97, "by": "local_decider"},
                       {"label": "unsure", "confidence": 0.9, "by": "fallback", "reason": "below-bar"}):
            out = self.run_ask("I've seen this so like", intent)
            self.assertEqual((out["answer"], out.get("again")), (ask.SAY_AGAIN, True))

    def test_timeout_or_rule_keeps_the_old_way(self):
        out = self.run_ask("what port does rockceen run on", {"label": "unsure", "confidence": 0.0, "by": "timeout"})
        self.assertEqual(out["answer"], ask.NOT_FOUND)
        out = self.run_ask("what port does rockceen run on", {"label": "unsure", "confidence": 0.3, "by": "fallback"})
        self.assertEqual(out["answer"], ask.NOT_FOUND)
        out = self.run_ask("remember that the dentist is on friday", {"label": "unsure", "confidence": 0.9, "by": "local_decider"})
        self.assertEqual(out["kind"], "job")   # a word rule fits: the rule still wins


if __name__ == "__main__":
    unittest.main()
