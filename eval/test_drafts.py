"""The check-up's drafts (eval/drafts.py): fake asks, ratings, misses and outcomes, made-up names, temp folders.
Run: python3 -I eval/test_drafts.py   (no network, no model, nothing real is read or written)"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="drafts-test-state-")
import drafts  # noqa: E402



def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


ORIGINAL_SCRUB = drafts.scrub   # the real one, before any test swaps it
NOW = time.mktime(time.strptime("2026-10-22T12:00:00", drafts.FORMAT))


def at(minutes_ago):
    return time.strftime(drafts.FORMAT, time.localtime(NOW - minutes_ago * 60))


DAY = 24 * 60


def ask(qid, q, ago=60, kind="answer", src="island", found=True, job=None, sources=(), answer="It is x."):
    return {"id": qid, "at": at(ago), "from": src, "q": q, "kind": kind, "answer": answer, "found": found,
            "job": job, "sources": list(sources)}


def fake_scrub(text):
    if "unsure" in text:
        raise drafts.Unsure("test")
    return re.sub(r"zorblax", "[NAME]", text, flags=re.I)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drafts-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state")
        self.lore = os.path.join(self.tmp, "agent-os", "lore")
        os.makedirs(self.state)
        os.makedirs(os.path.join(self.lore, "drafts"))
        with open(os.path.join(self.lore, "CONTEXT.md"), "w") as f:
            f.write("# lore\n\n| Story | Lesson |\n|---|---|\n| `old-story.md` | An old lesson. |\n")
        with open(os.path.join(self.lore, "old-story.md"), "w") as f:
            f.write("---\nstanding: insight\n---\n# Old\n")
        self.seen = os.path.join(self.tmp, "seen.jsonl")
        with open(self.seen, "w") as f:
            f.write(json.dumps({"id": "s01", "use": "howto", "q": "an old miss", "expect_paths": ["~/a.md"],
                                "expect_answer": "x", "stale_paths": []}) + "\n")
        self.note = os.path.join(self.tmp, "note.md")
        open(self.note, "w").close()
        for patch in (mock.patch.object(drafts.asklog, "STATE", self.state),
                      mock.patch.object(drafts.asklog, "ASKS", os.path.join(self.state, "asks.jsonl")),
                      mock.patch.object(drafts.asklog, "RATINGS", os.path.join(self.state, "ratings.jsonl")),
                      mock.patch.object(drafts.asklog, "OUTCOMES", os.path.join(self.state, "outcomes.jsonl")),
                      mock.patch.object(drafts, "seen_path", lambda: self.seen),
                      mock.patch.object(drafts, "scrub", fake_scrub),
                      mock.patch.dict(os.environ, {"BRAIN_DRAFTS": os.path.join(self.state, "drafts"),
                                                   "AGENT_OS_LORE": self.lore})):
            patch.start()
            self.addCleanup(patch.stop)

    def log(self, name, rows):
        with open(os.path.join(self.state, name + ".jsonl"), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    def week(self, asks=(), ratings=(), outcomes=(), misses=()):
        self.log("asks", asks)
        self.log("ratings", ratings)
        self.log("outcomes", outcomes)
        self.log("misses", misses)

    def run_drafts(self):
        return drafts.run(7, now=NOW, today="2026-10-22")

    def eval_rows(self):
        out = []
        for f in drafts._draft_files():
            out += drafts._read_jsonl(f)
        return out

    def drafted(self):
        """Only what sits in the two drafts folders (the test's own logs name the made-up name on purpose)."""
        return {p: b for p, b in self.tree().items()
                if p.startswith(("state/drafts/", os.path.join("agent-os", "lore", "drafts") + os.sep))}

    def tree(self):
        """Every file under the temp folder with its bytes, to see what changed."""
        out = {}
        for here, _, files in os.walk(self.tmp):
            for f in files:
                p = os.path.join(here, f)
                out[os.path.relpath(p, self.tmp)] = read(p, "rb")
        return out


class Signals(Case):
    def gather(self):
        return drafts.gather(drafts.asklog.read(drafts.asklog.ASKS), drafts.asklog.read(drafts.asklog.RATINGS),
                             drafts.asklog.read(drafts.asklog.OUTCOMES), drafts._read_jsonl(os.path.join(self.state, "misses.jsonl")),
                             7, NOW)

    def test_a_thumbs_down_counts_and_the_newest_vote_wins(self):
        self.week([ask("a1", "q one"), ask("a2", "q two")],
                  [{"id": "a1", "at": at(50), "verdict": "down", "why": "wrong note"},
                   {"id": "a2", "at": at(50), "verdict": "down"}, {"id": "a2", "at": at(40), "verdict": "up"}])
        got = self.gather()
        self.assertEqual(list(got), ["a1"])
        self.assertEqual(got["a1"]["why"], ["down"])

    def test_a_thumbs_down_on_a_cli_ask_counts_but_other_cli_asks_do_not(self):
        self.week([ask("a1", "rated", src="cli"), ask("a2", "asked 3 times", src="cli"),
                   ask("a3", "asked 3 times", src="cli", ago=30), ask("a4", "asked 3 times", src="cli", ago=20)],
                  [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.assertEqual(list(self.gather()), ["a1"])

    def test_only_misses_the_router_was_not_to_blame_for(self):
        self.week([ask("a1", "q one"), ask("a2", "q two"), ask("a3", "q three", src="cli")],
                  misses=[{"id": "a1", "at": at(5), "from": "island", "status": "not-router"},
                          {"id": "a2", "at": at(5), "from": "island", "status": "router"},
                          {"id": "a3", "at": at(5), "from": "cli", "status": "not-router"}])
        self.assertEqual(list(self.gather()), ["a1"])

    def test_repeated_three_times_or_twice_within_ten_minutes(self):
        self.week([ask("t1", "Where is the bar?", ago=3 * DAY), ask("t2", "where is the bar", ago=2 * DAY),
                   ask("t3", "WHERE IS THE BAR!", ago=1 * DAY),                      # three in a week: t1
                   ask("p1", "how do I reload", ago=100), ask("p2", "how do I reload", ago=95),   # 5 minutes apart: p1
                   ask("n1", "only twice", ago=3 * DAY), ask("n2", "only twice", ago=1 * DAY),    # far apart: no
                   ask("j1", "open the bar", kind="job", ago=100), ask("j2", "open the bar", kind="job", ago=99)])
        got = self.gather()
        self.assertEqual(sorted(got), ["p1", "t1"])
        self.assertEqual(got["t1"]["why"], ["repeat"])

    def test_declined_and_failed_jobs(self):
        self.week([ask("j1", "turn it on", kind="job", job="lamp"), ask("j2", "do the thing", kind="job", job="build"),
                   ask("j3", "fine", kind="job", job="lamp")],
                  outcomes=[{"id": "j1", "at": at(5), "what": "declined", "detail": ""},
                            {"id": "j2", "at": at(5), "what": "job-failed", "detail": "no such file"},
                            {"id": "j3", "at": at(5), "what": "job-ok"}])
        got = self.gather()
        self.assertEqual(sorted(got), ["j1", "j2"])
        self.assertEqual(drafts.cause(got["j1"]), "job:lamp:declined")
        self.assertEqual(drafts.cause(got["j2"]), "job:build:failed")

    def test_old_signals_are_left_out(self):
        self.week([ask("a1", "old one", ago=9 * DAY)], [{"id": "a1", "at": at(9 * DAY), "verdict": "down"}])
        self.assertEqual(self.gather(), {})

    def test_causes_of_answers(self):
        self.week([ask("a1", "x1", found=False), ask("a2", "x2"), ask("a3", "x3")],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}],
                  misses=[{"id": "a3", "at": at(5), "from": "island", "status": "not-router"}])
        got = self.gather()
        self.assertEqual([drafts.cause(got[i]) for i in ("a1", "a2", "a3")],
                         ["answer:not-found", "answer:down", "answer:miss"])


class EvalDrafts(Case):
    def test_a_draft_is_shaped_like_a_fair_test_line_with_no_note_yet(self):
        self.week([ask("a1", "where is the bar", sources=["/h/x/bar.md"])],
                  [{"id": "a1", "at": at(5), "verdict": "down"}])
        report = self.run_drafts()
        self.assertEqual(report["eval_new"], 1)
        (row,) = self.eval_rows()
        self.assertEqual({k: row[k] for k in ("id", "use", "q", "expect_paths", "expect_answer", "stale_paths", "source")},
                         {"id": "d-a1", "use": "howto", "q": "where is the bar", "expect_paths": [], "expect_answer": "",
                          "stale_paths": [], "source": "ask a1"})
        self.assertEqual(row["notes_used"], ["/h/x/bar.md"])
        self.assertIn("👎", row["from"])
        self.assertTrue(os.path.exists(os.path.join(self.state, "drafts", "eval-2026-10-22.jsonl")))

    def test_a_decided_question_is_guessed_as_decided(self):
        self.assertEqual(drafts.guess_use("What did we decide about the bar?"), "decided")
        self.assertEqual(drafts.guess_use("where is the bar"), "howto")

    def test_job_asks_are_counted_but_get_no_test_question(self):
        self.week([ask("j1", "turn it on", kind="job", job="lamp")], outcomes=[{"id": "j1", "at": at(5), "what": "declined"}])
        report = self.run_drafts()
        self.assertEqual(report["signals"], {"declined": 1})
        self.assertEqual(self.eval_rows(), [])

    def test_private_names_are_swapped_before_anything_is_written(self):
        self.week([ask("a1", "what did Zorblax say about the bar", sources=["/h/zorblax-notes.md"])],
                  [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.run_drafts()
        (row,) = self.eval_rows()
        self.assertEqual(row["q"], "what did [NAME] say about the bar")
        self.assertEqual(row["notes_used"], ["/h/[NAME]-notes.md"])
        self.assertTrue(self.drafted())
        for blob in self.drafted().values():
            self.assertNotIn(b"orblax", blob)

    def test_when_the_filter_is_not_sure_the_draft_is_skipped_and_counted(self):
        self.week([ask("a1", "unsure what this is"), ask("a2", "a fine question")],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}])
        report = self.run_drafts()
        # skipped: the test question that quotes it, and the story about the two 👎 that quoted it too
        self.assertEqual((report["eval_new"], report["skipped"], report["lore_new"]), (1, 2, []))
        self.assertEqual([r["id"] for r in self.eval_rows()], ["d-a2"])
        for blob in self.drafted().values():
            self.assertNotIn(b"unsure what", blob)

    def test_a_missing_filter_skips_everything(self):
        self.week([ask("a1", "a fine question")], [{"id": "a1", "at": at(5), "verdict": "down"}])

        def without_filter(text):
            with mock.patch.object(drafts, "_names", side_effect=ImportError("no decider")):
                return ORIGINAL_SCRUB(text)
        with mock.patch.object(drafts, "scrub", without_filter):
            report = self.run_drafts()
        self.assertEqual((report["eval_new"], report["skipped"]), (0, 1))
        self.assertEqual(self.eval_rows(), [])

    def test_running_again_adds_nothing(self):
        self.week([ask("a1", "q one"), ask("a2", "q two", found=False), ask("a3", "q two", found=False, ago=50)],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}])
        first = self.run_drafts()
        before = self.tree()
        again = self.run_drafts()
        self.assertEqual((first["eval_new"], again["eval_new"]), (2, 0))
        self.assertEqual(self.tree(), before)

    def test_the_same_question_in_a_new_ask_is_not_drafted_again(self):
        self.week([ask("a1", "q one")], [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.run_drafts()
        self.week([ask("a1", "q one"), ask("b9", "Q one?", ago=10)],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "b9", "at": at(5), "verdict": "down"}])
        self.assertEqual(self.run_drafts()["eval_new"], 0)

    def test_a_question_already_in_the_tuning_set_is_not_drafted(self):
        self.week([ask("a1", "An old miss!")], [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.assertEqual(self.run_drafts()["eval_new"], 0)

    def test_a_dropped_draft_is_never_drafted_again(self):
        self.week([ask("a1", "q one")], [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.run_drafts()
        drafts.drop("d-a1")
        self.assertEqual(self.eval_rows(), [])
        self.assertEqual(self.run_drafts()["eval_new"], 0)
        self.assertEqual(self.eval_rows(), [])


class LoreDrafts(Case):
    def test_the_same_cause_twice_makes_a_story(self):
        self.week([ask("j1", "turn it on", kind="job", job="lamp"), ask("j2", "turn on the lamp", kind="job", job="lamp")],
                  outcomes=[{"id": "j1", "at": at(5), "what": "declined"}, {"id": "j2", "at": at(4), "what": "declined"}])
        report = self.run_drafts()
        self.assertEqual(report["lore_new"], ["checkup-job-lamp-declined"])
        path = os.path.join(self.lore, "drafts", "checkup-job-lamp-declined.md")
        text = read(path)
        self.assertTrue(text.startswith("---\nstanding: observation\n"))
        self.assertIn("j1, j2", text)
        self.assertIn("not a lesson until <user> keeps it", text)

    def test_one_signal_alone_is_not_a_story_unless_it_fits_a_theme(self):
        self.week([ask("a1", "q one", found=False), ask("a2", "is the testbox busy right now", found=False)],
                  [{"id": "a2", "at": at(5), "verdict": "down"}])
        report = self.run_drafts()
        self.assertEqual(report["lore_new"], ["checkup-testbox-busy"])

    def test_a_story_is_scrubbed_and_a_name_never_lands_in_it(self):
        self.week([ask("a1", "what did Zorblax say about the testbox queue", found=False),
                   ask("a2", "what did Zorblax say about the other thing", found=False)],
                  [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.run_drafts()
        self.assertTrue(self.drafted())
        for blob in self.drafted().values():
            self.assertNotIn(b"orblax", blob)

    def test_an_unsure_filter_skips_the_story(self):
        self.week([ask("a1", "unsure one", found=False), ask("a2", "unsure two", found=False)],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}])
        report = self.run_drafts()
        self.assertEqual(report["lore_new"], [])
        self.assertGreaterEqual(report["skipped"], 1)
        self.assertEqual(os.listdir(os.path.join(self.lore, "drafts")), [])

    def test_no_drafts_folder_means_no_stories_and_no_new_folder(self):
        shutil.rmtree(os.path.join(self.lore, "drafts"))
        self.week([ask("j1", "x", kind="job", job="lamp"), ask("j2", "y", kind="job", job="lamp")],
                  outcomes=[{"id": "j1", "at": at(5), "what": "declined"}, {"id": "j2", "at": at(5), "what": "declined"}])
        self.assertEqual(self.run_drafts()["lore_new"], [])
        self.assertFalse(os.path.exists(os.path.join(self.lore, "drafts")))

    def test_a_story_that_is_already_there_or_was_dropped_is_not_made_again(self):
        self.week([ask("j1", "x", kind="job", job="lamp"), ask("j2", "y", kind="job", job="lamp")],
                  outcomes=[{"id": "j1", "at": at(5), "what": "declined"}, {"id": "j2", "at": at(5), "what": "declined"}])
        self.run_drafts()
        path = os.path.join(self.lore, "drafts", "checkup-job-lamp-declined.md")
        with open(path, "a") as f:
            f.write("<user> edited this.\n")
        self.assertEqual(self.run_drafts()["lore_new"], [])
        self.assertIn("<user> edited this.", read(path))
        drafts.drop("checkup-job-lamp-declined")
        self.assertEqual(self.run_drafts()["lore_new"], [])
        self.assertFalse(os.path.exists(path))


class Boundaries(Case):
    def test_the_check_up_writes_only_inside_the_two_drafts_folders(self):
        self.week([ask("a1", "is the testbox busy", found=False), ask("a2", "q two"),
                   ask("j1", "x", kind="job", job="lamp"), ask("j2", "y", kind="job", job="lamp")],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}],
                  [{"id": "j1", "at": at(5), "what": "declined"}, {"id": "j2", "at": at(5), "what": "declined"}])
        before = self.tree()
        self.run_drafts()
        after = self.tree()
        changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
        self.assertTrue(changed)
        for p in changed:
            self.assertTrue(p.startswith(("state/drafts/", os.path.join("agent-os", "lore", "drafts") + os.sep)), p)
        self.assertEqual(after["seen.jsonl"], before["seen.jsonl"])
        self.assertEqual(after[os.path.join("agent-os", "lore", "CONTEXT.md")], before[os.path.join("agent-os", "lore", "CONTEXT.md")])

    def test_a_write_outside_is_refused(self):
        for bad in (os.path.join(self.tmp, "elsewhere.txt"), os.path.join(self.state, "drafts", "..", "asks.jsonl"),
                    os.path.join(self.state, "drafts")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    drafts._write(os.path.join(self.state, "drafts"), bad, "x")
        os.makedirs(os.path.join(self.state, "drafts"))
        os.symlink(self.tmp, os.path.join(self.state, "drafts", "link"))
        with self.assertRaises(ValueError):
            drafts._write(os.path.join(self.state, "drafts"), os.path.join(self.state, "drafts", "link", "x.txt"), "x")


class RateOffers(Case):
    def test_unrated_answers_that_were_asked_again_at_most_three(self):
        asks = [ask("a%d" % i, "how do I reload the bar %d" % i, ago=300 - i * 30) for i in range(5)]
        again = [ask("r%d" % i, "how do I reload the bar %d" % i, ago=299 - i * 30) for i in range(5)]
        lonely = [ask("l1", "something else entirely", ago=20)]
        self.week(asks + again + lonely, [{"id": "a4", "at": at(1), "verdict": "up"}])
        offers = drafts.rate_offers(drafts.asklog.read(drafts.asklog.ASKS), drafts.asklog.read(drafts.asklog.RATINGS), 7, NOW)
        self.assertEqual(len(offers), 3)
        ids = {o["id"] for o in offers}
        self.assertNotIn("a4", ids)       # rated
        self.assertNotIn("l1", ids)       # never asked again
        self.assertTrue(all(o["id"].startswith(("a", "r")) for o in offers))

    def test_a_different_question_or_a_later_one_is_no_re_ask(self):
        self.week([ask("a1", "where is the bar", ago=100), ask("a2", "what time is it in tokyo", ago=99),
                   ask("b1", "where is the port", ago=300), ask("b2", "where is the port", ago=280)])
        offers = drafts.rate_offers(drafts.asklog.read(drafts.asklog.ASKS), [], 7, NOW)
        self.assertEqual(offers, [])

    def test_an_unsure_filter_gives_the_id_alone(self):
        self.week([ask("a1", "unsure how to reload", ago=100), ask("a2", "unsure how to reload", ago=99)])
        offers = drafts.rate_offers(drafts.asklog.read(drafts.asklog.ASKS), [], 7, NOW)
        self.assertEqual(offers, [{"id": "a1", "q": None}])

    def test_the_block_prints_one_press_lines(self):
        self.week([ask("a1", "how do I reload", ago=100), ask("a2", "how do I reload", ago=99)])
        text = "\n".join(drafts.lines(self.run_drafts()))
        self.assertIn("brain rate a1 up|down", text)
        self.assertIn('"how do I reload"', text)


class AutoRate(Case):
    """An answer asked again within 10 minutes is marked 👎 on its own (drafts.auto_rate)."""

    def ratings(self):
        return drafts.asklog.read(drafts.asklog.RATINGS)

    def test_the_first_answer_of_a_quick_re_ask_gets_a_thumbs_down(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99),
                   ask("l1", "something else entirely", ago=50)])
        marked = drafts.auto_rate(7, NOW)
        self.assertEqual([a["id"] for a in marked], ["a1"])
        self.assertEqual([(r["id"], r["verdict"], r["why"]) for r in self.ratings()], [("a1", "down", drafts.AUTO_WHY)])

    def test_running_again_marks_nothing_twice(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99)])
        drafts.auto_rate(7, NOW)
        self.assertEqual(drafts.auto_rate(7, NOW), [])
        self.assertEqual(len(self.ratings()), 1)

    def test_an_answer_owner_rated_is_never_touched(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99)],
                  ratings=[{"id": "a1", "at": at(90), "verdict": "up", "why": ""}])
        self.assertEqual(drafts.auto_rate(7, NOW), [])
        self.assertEqual([r["verdict"] for r in self.ratings()], ["up"])

    def test_his_later_up_beats_the_automatic_down_and_is_not_marked_again(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99)])
        drafts.auto_rate(7, NOW)
        drafts.asklog.rate("a1", "up")
        self.assertEqual(drafts.auto_rate(7, NOW), [])
        self.assertEqual({r["id"]: r["verdict"] for r in self.ratings()}["a1"], "up")
        self.assertEqual(drafts.rate_offers(drafts.asklog.read(drafts.asklog.ASKS), self.ratings(), 7, NOW), [])

    def test_the_automatic_down_still_shows_as_an_offer_to_undo(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99)])
        drafts.auto_rate(7, NOW)
        offers = drafts.rate_offers(drafts.asklog.read(drafts.asklog.ASKS), self.ratings(), 7, NOW)
        self.assertEqual([o["id"] for o in offers], ["a1"])

    def test_late_re_asks_jobs_and_the_checkups_own_asks_are_not_marked(self):
        self.week([ask("b1", "where is the port", ago=300), ask("b2", "where is the port", ago=280),
                   ask("j1", "pause the music", ago=100, kind="job"), ask("j2", "pause the music", ago=99, kind="job"),
                   ask("c1", "what is x", ago=100, src="checkup"), ask("c2", "what is x", ago=99, src="checkup")])
        self.assertEqual(drafts.auto_rate(7, NOW), [])
        self.assertEqual(self.ratings(), [])

    def test_the_automatic_down_is_a_signal_for_the_drafts(self):
        self.week([ask("a1", "how do I reload the bar", ago=100), ask("a2", "how do I reload the bar", ago=99)])
        drafts.auto_rate(7, NOW)
        report = self.run_drafts()
        self.assertEqual(report["signals"].get("down"), 1)


class KeepAndDrop(Case):
    def draft_one(self):
        self.week([ask("a1", "where is the bar", sources=["/h/x/bar.md"])], [{"id": "a1", "at": at(5), "verdict": "down"}])
        self.run_drafts()

    def test_keep_needs_the_note(self):
        self.draft_one()
        with self.assertRaises(ValueError):
            drafts.keep_eval("d-a1")
        with self.assertRaises(ValueError):
            drafts.keep_eval("d-a1", ["/no/such/note.md"])
        with self.assertRaises(KeyError):
            drafts.keep_eval("d-nope", [self.note])
        self.assertEqual(len(self.eval_rows()), 1)
        self.assertEqual(len(read(self.seen).splitlines()), 1)

    def test_keep_moves_it_to_the_tuning_set_and_never_to_the_fair_test(self):
        self.draft_one()
        new_id = drafts.keep_eval("d-a1", [self.note], answer="in the bar note")
        self.assertEqual(new_id, "s02")
        rows = [json.loads(l) for l in read(self.seen).splitlines()]
        self.assertEqual(rows[-1]["q"], "where is the bar")
        self.assertEqual(rows[-1]["expect_paths"], [self.note.replace(drafts.HOME, "~", 1)])
        self.assertEqual(rows[-1]["expect_answer"], "in the bar note")
        self.assertEqual(self.eval_rows(), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "heldout.jsonl")))
        self.assertEqual(self.run_drafts()["eval_new"], 0)   # and it is not drafted again

    def test_keep_takes_a_note_filled_in_by_hand(self):
        self.draft_one()
        (path,) = drafts._draft_files()
        rows = drafts._read_jsonl(path)
        rows[0]["expect_paths"] = [self.note]
        rows[0]["use"] = "decided"
        drafts._write(drafts.drafts_dir(), path, drafts._jsonl(rows))
        drafts.keep_eval("d-a1")
        self.assertEqual(json.loads(read(self.seen).splitlines()[-1])["use"], "decided")

    def test_keep_refuses_an_unknown_kind_of_question(self):
        self.draft_one()
        with self.assertRaises(ValueError):
            drafts.keep_eval("d-a1", [self.note], use="gossip")

    def story(self, slug="my-story"):
        with open(os.path.join(self.lore, "drafts", slug + ".md"), "w") as f:
            f.write("---\nstanding: observation\ndraft: waiting\nlesson-line: Say it once.\n---\n# A story\n\nText.\n")

    def test_keep_a_story_makes_it_an_insight_and_adds_its_line(self):
        self.story()
        drafts.keep_lore("my-story")
        text = read(os.path.join(self.lore, "my-story.md"))
        self.assertEqual(text, "---\nstanding: insight\n---\n# A story\n\nText.\n")
        ctx = read(os.path.join(self.lore, "CONTEXT.md"))
        self.assertIn("| `old-story.md` | An old lesson. |\n| `my-story.md` | Say it once. |\n", ctx)
        self.assertFalse(os.path.exists(os.path.join(self.lore, "drafts", "my-story.md")))
        with self.assertRaises(KeyError):
            drafts.drop("my-story")

    def test_keep_a_story_will_not_overwrite_a_lesson(self):
        self.story("old-story")
        with self.assertRaises(ValueError):
            drafts.keep_lore("old-story")
        self.assertIn("An old lesson", read(os.path.join(self.lore, "CONTEXT.md")))

    def test_drop_a_story(self):
        self.story()
        drafts.drop("my-story")
        self.assertEqual(drafts.lore_list(), [])
        self.assertFalse(os.path.exists(os.path.join(self.lore, "my-story.md")))

    def test_the_command_line(self):
        self.draft_one()
        self.story()

        def cli(*argv):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = drafts.main(list(argv))
            return code, out.getvalue(), err.getvalue()
        code, out, _ = cli()
        self.assertEqual(code, 0)
        self.assertIn("d-a1", out)
        self.assertIn("needs its note", out)
        self.assertIn("my-story  (lore story) Say it once.", out)
        self.assertEqual(cli("keep", "d-a1")[0], 1)
        self.assertIn("kept as s02", cli("keep", "d-a1", self.note, "--use", "decided")[1])
        self.assertIn("kept as lore/my-story.md", cli("keep", "my-story")[1])
        self.assertEqual(cli("drop", "nothing")[0], 1)
        self.assertIn("nothing waits", cli("list")[1])
        self.assertEqual(cli("keep")[0], 2)


class Block(Case):
    def test_a_quiet_week_says_nothing(self):
        self.week([ask("a1", "fine")])
        self.assertEqual(drafts.lines(self.run_drafts()), [])

    def test_the_block_in_plain_words(self):
        self.week([ask("a1", "where is the bar", found=False), ask("a2", "unsure thing")],
                  [{"id": "a1", "at": at(5), "verdict": "down"}, {"id": "a2", "at": at(5), "verdict": "down"}])
        block = drafts.lines(self.run_drafts())
        self.assertEqual(block[0], "Drafts for <user> (none of these is a lesson or a test question until he keeps it):")
        self.assertIn("  signals: 2 👎", block)
        self.assertIn("  new: 1 test questions, 0 lore stories; 1 skipped, the names filter was not sure", block)
        self.assertIn("  waiting: 1 test questions, 0 lore stories: `brain drafts`", block)


class RealNamesFilter(unittest.TestCase):
    """The real decider/names.py with a made-up list (skipped where the decider repo is not there)."""

    def test_made_up_names_are_swapped_and_a_broken_list_fails_closed(self):
        try:
            drafts._names()
        except ImportError:
            self.skipTest("decider repo not here")
        with tempfile.TemporaryDirectory() as d:
            private = os.path.join(d, "private.json")
            with open(private, "w") as f:
                json.dump({"words": ["zorblax"]}, f)
            env = {"DECIDER_PRIVATE_NAMES": private, "DECIDER_BUSINESS_DIR": os.path.join(d, "none")}
            with mock.patch.dict(os.environ, env):
                for text in ("Zorblax's notes", "zorblax-notes", "zorblax_notes", "ZorblaxNotes"):
                    with self.subTest(text=text):
                        self.assertNotIn("orblax", ORIGINAL_SCRUB(text).lower())
                self.assertEqual(ORIGINAL_SCRUB("nothing private"), "nothing private")
                with open(private, "w") as f:
                    f.write("{broken")
                with self.assertRaises(drafts.Unsure):
                    ORIGINAL_SCRUB("anything")


if __name__ == "__main__":
    unittest.main()
