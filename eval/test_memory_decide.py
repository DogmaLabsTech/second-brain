"""The memory system asks the decider (ask/memory_decide.py; agent memory job 9, phase A): the start hook, the drafts'
"already known" and lesson gate, the flags' "newer note says the opposite". A fake `decide` stands in: the real the second decider and
the local decider are never called. Every choice falls back to today's word rule when the decider is not sure, off, or broken.
Run: CRABBOX_LOCAL=1 python3 -I eval/test_memory_decide.py   (no network, no model)"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ask"))
os.environ["BRAIN_STATE"] = tempfile.mkdtemp(prefix="mdecide-test-state-")
os.environ.pop("BRAIN_MEMORY_DECIDER", None)           # the default is ON: these tests prove it
import drafts  # noqa: E402
import memory_decide  # noqa: E402
import memory_drafts  # noqa: E402
import memory_flags  # noqa: E402
import memory_hook  # noqa: E402
import memory_keep  # noqa: E402
from test_memory_drafts import BODY, GIT_ENV, write_note  # noqa: E402


class Fake:
    """A stand-in for decider's `decide`: answers[task] = a choice, None (not sure) or an Exception; every call is kept."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def __call__(self, task, state, backend=None, timeout=None, caller=None, log=True):
        self.calls.append({"task": task, "state": state, "timeout": timeout, "caller": caller})
        got = self.answers.get(task)
        if isinstance(got, Exception):
            raise got
        if got is None:
            return {"task": task, "answers": {}, "backend": "second_decider", "sure": False, "ms": 1.0, "reason": "unsure"}
        return {"task": task, "answers": {memory_decide.TASKS[task]: {"choice": got, "confidence": 0.9}},
                "backend": "second_decider", "sure": True, "ms": 12.0}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mdecide-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state")
        for p in (mock.patch.dict(os.environ, {"BRAIN_HOOK_STATE": self.state, "BRAIN_MEMORY_STORE": os.path.join(self.tmp, "shared"),
                                               **GIT_ENV}),
                  mock.patch.object(memory_decide, "decide_fn", None)):
            p.start()
            self.addCleanup(p.stop)
        os.makedirs(os.path.join(self.tmp, "shared", "drafts"))
        os.environ.pop("BRAIN_MEMORY_DECIDER", None)

    def use(self, **answers):
        fake = Fake(**answers)
        memory_decide.decide_fn = fake
        return fake

    def log(self):
        try:
            with open(os.path.join(self.state, "memory-decider.jsonl")) as f:
                return [json.loads(line) for line in f]
        except OSError:
            return []


class Helper(Case):
    def test_on_by_default_and_the_switch_turns_it_off(self):
        fake = self.use(**{"memory-kind": "rule"})
        self.assertTrue(memory_decide.enabled())
        self.assertEqual(memory_decide.kind_of("Never print the key."), "rule")
        for off in ("off", "OFF", "0", "no", "false"):
            with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": off}):
                self.assertFalse(memory_decide.enabled())
                self.assertIsNone(memory_decide.kind_of("Never print the key."))
        self.assertEqual(len(fake.calls), 1)
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": "on"}):
            self.assertEqual(memory_decide.kind_of("x"), "rule")

    def test_each_helper_maps_its_task_and_names_itself_as_the_caller(self):
        fake = self.use(**{"memory-real-task": "yes", "memory-same-note": "same", "memory-conflict": "conflicts",
                           "memory-kind": "lesson", "memory-lesson-worth": "no"})
        self.assertIs(memory_decide.real_task("fix the bar"), True)
        self.assertIs(memory_decide.same_note("t", "b", "s"), True)
        self.assertEqual(memory_decide.relation("newer", "older"), "conflicts")
        self.assertEqual(memory_decide.kind_of("It broke because..."), "lesson")
        self.assertIs(memory_decide.lesson_worth("t", "b"), False)
        self.assertEqual([c["caller"] for c in fake.calls], [c["task"] for c in fake.calls])
        self.assertEqual(len(fake.calls), 5)
        self.assertIn("NEW LESSON:\nt\nb\n\nKEPT NOTE:\ns", fake.calls[1]["state"])
        self.assertIn("NEWER NOTE:\nnewer\n\nOLDER NOTE:\nolder", fake.calls[2]["state"])

    def test_not_sure_slow_or_broken_is_none_and_never_raises(self):
        for answer in (None, RuntimeError("boom")):
            self.use(**{"memory-kind": answer, "memory-real-task": answer})
            self.assertIsNone(memory_decide.kind_of("x"))
            self.assertIsNone(memory_decide.real_task("x"))
        self.assertIsNone(memory_decide.ask("memory-kind", "   "))
        self.assertIsNone(memory_decide.ask("memory-kind", None))

    def test_an_unexpected_option_is_none(self):
        self.use(**{"memory-kind": "maybe", "memory-conflict": "dunno"})
        self.assertIsNone(memory_decide.kind_of("x"))
        self.assertIsNone(memory_decide.relation("a", "b"))

    def test_the_log_has_the_answer_and_never_the_text(self):
        self.use(**{"memory-kind": "rule"})
        memory_decide.kind_of("A SECRET-LOOKING NOTE TEXT")
        rows = self.log()
        self.assertEqual((rows[0]["task"], rows[0]["choice"], rows[0]["sure"], rows[0]["backend"]), ("memory-kind", "rule", True, "second_decider"))
        self.assertNotIn("SECRET", json.dumps(rows))


class Hook(Case):
    def test_a_sure_answer_beats_the_word_list(self):
        self.use(**{"memory-real-task": "no"})
        self.assertEqual(memory_hook.real_task("please fix the bar now"), (None, "decider"))   # the rule says: a task
        self.use(**{"memory-real-task": "yes"})
        self.assertEqual(memory_hook.real_task("ok fine"), ("ok fine", "decider"))               # the rule says: filler

    def test_not_sure_off_or_broken_keeps_the_word_list(self):
        self.use(**{"memory-real-task": None})
        self.assertEqual(memory_hook.real_task("fix the bar now"), ("fix the bar now", "rule"))
        self.assertEqual(memory_hook.real_task("continue"), (None, "rule"))
        self.use(**{"memory-real-task": RuntimeError("down")})
        self.assertEqual(memory_hook.real_task("fix the bar now"), ("fix the bar now", "rule"))
        fake = self.use(**{"memory-real-task": "no"})
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": "off"}):
            self.assertEqual(memory_hook.real_task("fix the bar now"), ("fix the bar now", "rule"))
        self.assertEqual(fake.calls, [])

    def test_an_empty_prompt_is_not_sent_anywhere(self):
        fake = self.use(**{"memory-real-task": "yes"})
        self.assertEqual(memory_hook.real_task(""), (None, "rule"))
        self.assertEqual(memory_hook.real_task(None), (None, "rule"))
        self.assertEqual(fake.calls, [])

    def test_the_decider_gets_a_time_limit_that_leaves_the_search_its_second(self):
        fake = self.use(**{"memory-real-task": "yes"})
        memory_hook.real_task("fix the bar now", time.monotonic())
        self.assertLessEqual(fake.calls[-1]["timeout"], memory_hook.DECIDER_SECONDS)
        self.assertLessEqual(fake.calls[-1]["timeout"] + 1.0, memory_hook.TOTAL_SECONDS)
        fake = self.use(**{"memory-real-task": "yes"})            # 2 s of the 2.5 s already gone: no time to ask
        self.assertEqual(memory_hook.real_task("fix the bar now", time.monotonic() - 2.0), ("fix the bar now", "rule"))
        self.assertEqual(fake.calls, [])

    def test_the_prompt_sent_is_cut_to_1000_characters(self):
        fake = self.use(**{"memory-real-task": "yes"})
        task, how = memory_hook.real_task("word " * 600)
        self.assertEqual(len(fake.calls[0]["state"]), 1000)
        self.assertLessEqual(len(task), 1000)


class Gate(Case):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(os.environ, {"BRAIN_DRAFT_WRITER": "fixed"}),      # never the real Haiku
                  mock.patch.object(memory_keep, "guard_problem", lambda: None),
                  mock.patch.object(memory_drafts, "ask_haiku", mock.Mock(side_effect=AssertionError("Haiku called")))):
            p.start()
            self.addCleanup(p.stop)

    def add(self, job="job-1", title="test machine busy means wait in the queue", **kw):
        return memory_drafts.add("projects/second-brain/lessons", job, title, "job %s: check records" % job, kw.pop("body", BODY),
                                 store=os.path.join(self.tmp, "shared"), today="2026-10-28", search=None, hook_rows=[],
                                 **kw)

    def test_a_no_skips_the_draft_and_logs_it_and_uses_no_place_of_the_week(self):
        self.use(**{"memory-lesson-worth": "no"})
        with mock.patch.object(drafts, "scrub", lambda t: t):
            with self.assertRaises(memory_drafts.NotWorth) as why:
                self.add()
        self.assertIsInstance(why.exception, memory_drafts.DraftError)
        self.assertEqual(os.listdir(os.path.join(self.tmp, "shared", "drafts")), [])
        self.assertEqual(memory_drafts.log_rows(os.path.join(self.tmp, "shared")), [])
        self.assertIn("skipped", [r["event"] for r in self.log()])
        self.assertEqual([r for r in self.log() if r["event"] == "skipped"][0]["job"], "job-1")

    def test_a_yes_not_sure_off_and_broken_all_write_the_draft(self):
        for i, answer in enumerate(("yes", None, RuntimeError("x"))):
            self.use(**{"memory-lesson-worth": answer})
            with mock.patch.object(drafts, "scrub", lambda t: t):
                got = self.add(job="job-%d" % i, title="Title %d" % i)
            self.assertTrue(os.path.isfile(got["path"]))
        self.use(**{"memory-lesson-worth": "no"})
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": "off"}), mock.patch.object(drafts, "scrub", lambda t: t):
            self.assertTrue(os.path.isfile(self.add(job="job-9", title="Another one")["path"]))

    def test_text_the_names_filter_could_not_clean_is_never_asked_and_still_written(self):
        fake = self.use(**{"memory-lesson-worth": "no", "memory-same-note": "same"})
        with mock.patch.object(memory_keep, "guard_problem", lambda: "the list is broken"):
            got = self.add()
        self.assertTrue(os.path.isfile(got["path"]))
        self.assertEqual(fake.calls, [])

    def test_a_no_stops_before_haiku_is_asked(self):
        self.use(**{"memory-lesson-worth": "no"})
        with mock.patch.dict(os.environ, {"BRAIN_DRAFT_WRITER": "haiku"}), mock.patch.object(drafts, "scrub", lambda t: t):
            with self.assertRaises(memory_drafts.NotWorth):
                self.add()          # ask_haiku raises AssertionError if reached

    def test_the_gate_asks_after_the_names_filter_so_the_text_is_scrubbed(self):
        fake = self.use(**{"memory-lesson-worth": "yes"})
        with mock.patch.object(drafts, "scrub", lambda t: t.replace("Zorblax", "[NAME]")):
            self.add(title="Zorblax broke it", body="Zorblax pushed.")
        self.assertNotIn("Zorblax", fake.calls[0]["state"])


class Same(Case):
    def setUp(self):
        super().setUp()
        self.store = os.path.join(self.tmp, "shared")
        write_note(self.store, "projects/second-brain/lessons/queue.md", "Wait in the queue when the test machine is busy")

    def known(self, title="test machine busy means wait in the queue", body=BODY, search=None):
        return memory_drafts.already_known(self.store, "second-brain", title, body, search=search)

    def test_the_decider_says_same_even_where_the_words_differ(self):
        self.use(**{"memory-same-note": "same"})
        self.assertEqual(self.known(title="Queue up", body="Nothing else.")["rel"], "projects/second-brain/lessons/queue.md")

    def test_the_decider_says_new_even_where_the_words_overlap(self):
        self.use(**{"memory-same-note": "new"})
        self.assertIsNone(self.known())

    def test_not_sure_or_off_uses_the_word_rule(self):
        for ans in (None, RuntimeError("x")):
            self.use(**{"memory-same-note": ans})
            self.assertIsNotNone(self.known())
        self.use(**{"memory-same-note": "new"})
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": "off"}):
            self.assertIsNotNone(self.known())

    def test_only_the_top_three_candidates_go_to_the_decider_the_rest_use_the_rule(self):
        for i in range(5):
            write_note(self.store, "projects/second-brain/lessons/other-%d.md" % i, "Something about pins %d" % i)
        fake = self.use(**{"memory-same-note": "new"})
        rels = ["projects/second-brain/lessons/other-%d.md" % i for i in range(5)] + ["projects/second-brain/lessons/queue.md"]
        self.assertIsNotNone(self.known(search=lambda title: rels), "the queue note is 6th: the word rule still finds it")
        self.assertLessEqual(len(fake.calls), memory_drafts.SAME_ASKED)

    def test_without_search_the_likeliest_notes_are_asked_first(self):
        for i in range(5):
            write_note(self.store, "projects/second-brain/lessons/a-%d.md" % i, "Something about pins %d" % i)
        fake = self.use(**{"memory-same-note": "same"})
        got = self.known()
        self.assertEqual(got["rel"], "projects/second-brain/lessons/queue.md")
        self.assertEqual(len(fake.calls), 1)


class Conflict(Case):
    def note(self, summary, date):
        return {"summary": summary, "date": date, "rel": "p/%s.md" % date, "project": "p"}

    def test_the_decider_flags_only_a_conflict(self):
        old, new = self.note("Run the tests on the test machine", "2026-09-01"), self.note("Run the tests locally never on the test machine", "2026-10-01")
        for answer, flagged in (("conflicts", True), ("agrees", False), ("unrelated", False)):
            self.use(**{"memory-conflict": answer})
            self.assertIs(memory_flags.says_opposite(old, new), flagged, answer)

    def test_the_decider_overrides_the_word_rule_both_ways(self):
        old, new = self.note("Run the tests on the test machine", "2026-09-01"), self.note("Run the tests locally never on the test machine", "2026-10-01")
        self.assertTrue(memory_flags.opposite(old["summary"], new["summary"]))
        self.use(**{"memory-conflict": "agrees"})
        self.assertFalse(memory_flags.says_opposite(old, new))
        old, new = self.note("Keep drafts summary short", "2026-09-01"), self.note("Drafts summary need long form now", "2026-10-01")
        self.assertFalse(memory_flags.opposite(old["summary"], new["summary"]))
        self.use(**{"memory-conflict": "conflicts"})
        self.assertTrue(memory_flags.says_opposite(old, new))

    def test_not_sure_or_off_uses_the_word_rule(self):
        old, new = self.note("Run the tests on the test machine", "2026-09-01"), self.note("Run the tests locally never on the test machine", "2026-10-01")
        for ans in (None, RuntimeError("x")):
            self.use(**{"memory-conflict": ans})
            self.assertTrue(memory_flags.says_opposite(old, new))
        self.use(**{"memory-conflict": "agrees"})
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_DECIDER": "off"}):
            self.assertTrue(memory_flags.says_opposite(old, new))

    def test_a_pair_with_almost_no_shared_words_is_not_asked(self):
        fake = self.use(**{"memory-conflict": "conflicts"})
        self.assertFalse(memory_flags.says_opposite(self.note("Alpha beta gamma", "2026-09-01"), self.note("Delta epsilon never zeta", "2026-10-01")))
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()

