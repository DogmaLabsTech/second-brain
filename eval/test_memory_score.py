"""The agent memory score (eval/memory_score.py) and its two question sets: python3 -I eval/test_memory_score.py
The scorer runs on a fake `find`; the set files are checked for shape, for no overlap and (when this computer has
them) against the real store and the run specs they quote. No network, no model."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import memory_score as ms  # noqa: E402

STORE = "/store"
# The PM build runs went to the Archive with the project manager (one brain, 2026-10-28).
RUNS = os.path.expanduser("~/Archive/2026-10-29-project-manager/runs")


def note(rel, pinned=False):
    return {"path": f"{STORE}/{rel}", "pinned": pinned}


def fake_find(table):
    """find(repo, task) answering the notes listed for the task text (and the BRAIN_MEMORY_EXACT it saw)."""
    seen = []

    def find(repo, task):
        seen.append((task, os.environ.get("BRAIN_MEMORY_EXACT")))
        return {"notes": table.get(task, [])}
    find.seen = seen
    return find


def rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Scoring(unittest.TestCase):
    def test_rank_of_the_first_wanted_note(self):
        self.assertEqual(ms.rank_of(["a", "b", "c"], {"c", "b"}), 2)
        self.assertIsNone(ms.rank_of(["a"], {"z"}))
        self.assertIsNone(ms.rank_of([], {"z"}))

    def test_pinned_notes_count_in_all_but_not_in_unpinned(self):
        find = fake_find({"t": [note("p1.md", True), note("p2.md", True), note("x.md"), note("want.md")]})
        r = ms.score_row({"repo": "r", "task": "t", "want": ["want.md"]}, find, STORE)
        self.assertEqual((r["all"], r["unpinned"]), (4, 2))
        self.assertEqual((r["listed"], r["unpinned_listed"]), (4, 2))

    def test_a_pinned_wanted_note_has_no_unpinned_rank(self):
        find = fake_find({"t": [note("want.md", True), note("x.md")]})
        r = ms.score_row({"repo": "r", "task": "t", "want": ["want.md"]}, find, STORE)
        self.assertEqual((r["all"], r["unpinned"]), (1, None))

    def test_any_wanted_note_counts_and_the_first_one_sets_the_rank(self):
        find = fake_find({"t": [note("a.md"), note("w2.md"), note("w1.md")]})
        r = ms.score_row({"repo": "r", "task": "t", "want": ["w1.md", "w2.md"]}, find, STORE)
        self.assertEqual(r["all"], 2)

    def test_strict_counts_only_the_project_note(self):
        find = fake_find({"t": [note("all-projects/lessons/broad.md"), note("x.md"), note("y.md"),
                                note("projects/r/lessons/own.md")]})
        r = ms.score_row({"repo": "r", "task": "t",
                          "want": ["all-projects/lessons/broad.md", "projects/r/lessons/own.md"]}, find, STORE)
        self.assertEqual((r["all"], r["strict"]), (1, 4))
        r = ms.score_row({"repo": "r", "task": "t", "want": ["all-projects/lessons/broad.md"]}, find, STORE)
        self.assertEqual(r["strict"], 1)   # no project note wanted: the all-projects one counts

    def test_summary_top3_and_mean_rank(self):
        res = [{"all": 1, "strict": 1, "unpinned": 1, "listed": 5, "unpinned_listed": 5},
               {"all": 3, "strict": 3, "unpinned": 2, "listed": 5, "unpinned_listed": 4},
               {"all": 4, "strict": 4, "unpinned": 3, "listed": 5, "unpinned_listed": 4}]
        s = ms.summarize(res)
        self.assertEqual((s["rows"], s["top3_all"], s["top3_unpinned"], s["missed"]), (3, 2, 3, 0))
        self.assertAlmostEqual(s["mean_rank_all"], round((1 + 3 + 4) / 3, 2))
        self.assertAlmostEqual(s["mean_rank_unpinned"], 2.0)

    def test_a_note_the_push_does_not_list_counts_one_past_the_last(self):
        res = [{"all": 1, "strict": 1, "unpinned": 1, "listed": 4, "unpinned_listed": 3},
               {"all": None, "strict": None, "unpinned": None, "listed": 4, "unpinned_listed": 3}]
        s = ms.summarize(res)
        self.assertEqual((s["missed"], s["top3_all"], s["top3_unpinned"]), (1, 1, 1))
        self.assertEqual(s["mean_rank_all"], 3.0)        # (1 + 5) / 2
        self.assertEqual(s["mean_rank_unpinned"], 2.5)   # (1 + 4) / 2

    def test_no_rows_is_not_a_crash(self):
        self.assertEqual(ms.summarize([])["mean_rank_all"], 0.0)

    def test_the_rule_switch_is_set_per_run_and_put_back(self):
        find = fake_find({"t": [note("want.md")]})
        rows_ = [{"repo": "r", "task": "t", "want": ["want.md"]}]
        with mock.patch.dict(os.environ, {"BRAIN_MEMORY_EXACT": "1"}):
            ms.run_set(rows_, find, STORE, False)
            self.assertEqual(os.environ["BRAIN_MEMORY_EXACT"], "1")
        with mock.patch.dict(os.environ):
            os.environ.pop("BRAIN_MEMORY_EXACT", None)
            ms.run_set(rows_, find, STORE, True)
            self.assertNotIn("BRAIN_MEMORY_EXACT", os.environ)
        self.assertEqual([v for _, v in find.seen], ["0", "1"])


class LogAndCommand(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="memscore-test-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.log = os.path.join(self.dir, "memory-scores.tsv")
        self.sets = {}
        for name, n in (("tuning", 3), ("heldout", 2)):
            path = os.path.join(self.dir, name + ".jsonl")
            with open(path, "w") as f:
                for i in range(n):
                    f.write(json.dumps({"id": f"{name}-{i}", "repo": "r", "task": f"{name} task {i}",
                                        "want": [f"{name}-{i}.md"], "source": "test"}) + "\n")
            self.sets[name] = (path, False)

    def run_main(self, argv, find):
        out = io.StringIO()
        with mock.patch.object(ms, "LOG", self.log), mock.patch.object(ms, "set_files", return_value=self.sets), \
                mock.patch.object(ms.memory, "store_path", return_value=STORE), contextlib.redirect_stdout(out):
            code = ms.main(argv, find=find)
        return code, out.getvalue()

    def good_find(self):
        # the wanted note is first for "...task N", except tuning task 2, where it is 4th
        def find(repo, task):
            name, _, i = task.split(" ")
            notes = [note(f"{name}-{i}.md")]
            if task == "tuning task 2":
                notes = [note("x1.md"), note("x2.md"), note("x3.md")] + notes
            return {"notes": notes}
        return find

    def test_prints_one_line_per_set_and_rule(self):
        code, out = self.run_main([], self.good_find())
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.startswith(("tuning", "heldout"))]
        self.assertEqual(len(lines), 4)
        self.assertIn("rule on", lines[0])
        self.assertIn("top 3: 2/3 (all)", lines[0])
        self.assertIn("top 3: 2/2 (all)", lines[2])
        self.assertFalse(os.path.exists(self.log), "no --log, no log row")

    def test_log_adds_rows_newest_last_with_one_header(self):
        self.run_main(["--rule", "on", "--log", "first"], self.good_find())
        self.run_main(["--rule", "off", "--set", "heldout", "--log", "second"], self.good_find())
        with open(self.log) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], ms.HEADER)
        self.assertEqual(len(lines), 1 + 2 + 1)
        cols = lines[1].split("\t")
        self.assertEqual((cols[1], cols[2], cols[3], cols[4], cols[-1]), ("tuning", "on", "3", "2/3", "first"))
        self.assertEqual(len(cols), len(ms.HEADER.split("\t")))
        self.assertEqual(lines[-1].split("\t")[1:3], ["heldout", "off"])
        self.assertEqual(lines[-1].split("\t")[-1], "second")

    def test_floor_leaves_the_task_out(self):
        asked = []

        def find(repo, task):
            asked.append(task)
            return {"notes": []}
        code, out = self.run_main(["--set", "heldout", "--rule", "on", "--floor"], find)
        self.assertEqual(code, 0)
        self.assertEqual(asked, ["heldout task 0", "heldout task 1", None, None])
        self.assertIn("rule none", out)

    def test_the_example_file_is_flagged(self):
        self.sets["heldout"] = (self.sets["heldout"][0], True)
        _, out = self.run_main(["--set", "heldout", "--rule", "on"], self.good_find())
        self.assertIn("NOTE: the real held-out set is not on this computer", out)


KEYS = {"id", "repo", "task", "want", "source"}


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def shingles(text, n=6):
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


@unittest.skipUnless(os.path.exists(os.path.join(HERE, "memory-tuning.jsonl")), "needs your own question set (not shipped)")
class SetFiles(unittest.TestCase):
    """The sets as they sit in this folder. The real held-out file is git-ignored; the example file is always here."""

    @classmethod
    def setUpClass(cls):
        cls.tuning = rows(os.path.join(HERE, "memory-tuning.jsonl"))
        cls.example = rows(os.path.join(HERE, "memory-heldout.example.jsonl"))
        path, is_example = ms.set_files()["heldout"]
        cls.heldout = rows(path)
        cls.real_heldout = not is_example

    def test_tuning_shape(self):
        self.assertGreaterEqual(len(self.tuning), 30)
        self.check_shape(self.tuning)

    def test_heldout_shape(self):
        self.assertGreaterEqual(len(self.heldout), 10)
        self.assertGreaterEqual(len(self.example), 10)
        self.check_shape(self.heldout)
        self.check_shape(self.example)

    def check_shape(self, rs):
        self.assertEqual(len({r["id"] for r in rs}), len(rs), "ids are unique")
        self.assertEqual(len({(r["repo"], r["task"]) for r in rs}), len(rs), "no question twice")
        for r in rs:
            self.assertEqual(set(r), KEYS, r["id"])
            self.assertTrue(r["task"].strip() and r["source"].strip(), r["id"])
            self.assertTrue(re.fullmatch(r"[A-Za-z0-9][\w.-]*", r["repo"]), r["id"])
            self.assertTrue(r["want"] and all(w.endswith(".md") and not w.startswith("/") and ".." not in w
                                              for w in r["want"]), r["id"])
            self.assertEqual(len(set(r["want"])), len(r["want"]), r["id"])
            scope = ("projects/" + r["repo"] + "/", "all-projects/")
            self.assertTrue(all(w.startswith(scope) for w in r["want"]), f"{r['id']}: wanted note outside the scope")

    def test_the_example_rows_are_real_heldout_rows(self):
        if not self.real_heldout:
            self.skipTest("the real held-out set is not on this computer")
        by_id = {r["id"]: r for r in self.heldout}
        for r in self.example:
            self.assertEqual(r, by_id[r["id"]])

    def test_no_question_in_both_sets_and_no_near_copy(self):
        for held in (self.heldout, self.example):
            ids = {r["id"] for r in self.tuning} & {r["id"] for r in held}
            self.assertFalse(ids)
            tasks = {r["task"].strip() for r in self.tuning} & {r["task"].strip() for r in held}
            self.assertFalse(tasks)
            for t in self.tuning:
                ts = shingles(t["task"])
                for h in held:
                    self.assertFalse(ts & shingles(h["task"]), f"{t['id']} copies a run's words ({h['id']})")
                    both = set(words(t["task"])) | set(words(h["task"]))
                    same = set(words(t["task"])) & set(words(h["task"]))
                    self.assertLess(len(same) / len(both), 0.5, f"{t['id']} is near {h['id']}")

    def test_heldout_rows_are_quoted_from_the_run_specs(self):
        def squash(s):
            return " ".join(s.split())
        checked = 0
        for r in self.heldout:
            m = re.match(r"project-manager/runs/([^/]+)/spec\.md", r["source"])
            self.assertTrue(m, f"{r['id']}: source names a run spec")
            spec = os.path.join(RUNS, m.group(1), "spec.md")
            if not os.path.exists(spec):
                continue
            with open(spec, encoding="utf-8") as f:
                text = squash(f.read())
            for line in r["task"].splitlines():
                if line.strip():
                    self.assertIn(squash(line), text, f"{r['id']}: a line is not in the spec")
            checked += 1
        if not checked:
            self.skipTest("the run specs are not on this computer")

    def test_wanted_notes_exist_in_the_store(self):
        store = ms.memory.store_path()
        if not os.path.isdir(os.path.join(store, "projects")):
            self.skipTest("the memory store is not on this computer")
        for r in self.tuning + self.heldout:
            for w in r["want"]:
                self.assertTrue(os.path.isfile(os.path.join(store, w)), f"{r['id']}: {w}")

    def test_the_score_log_header_matches_the_code(self):
        with open(os.path.join(HERE, "memory-scores.tsv")) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], ms.HEADER)
        self.assertTrue(all(len(l.split("\t")) == len(ms.HEADER.split("\t")) for l in lines[1:]))


if __name__ == "__main__":
    unittest.main()
