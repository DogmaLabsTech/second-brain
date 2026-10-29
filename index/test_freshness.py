"""Index freshness (index/freshness.py, `brain status`, the check-up warnings) and the test machine status line that
index/codex-testbox.sh leaves. Everything runs on made-up folders, a made-up index and fake ssh/rsync: it never
touches the real index, the test machine or the network, and never re-indexes.

Run: python3 -I index/test_freshness.py
"""
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
os.environ["BRAIN_MEMORY_DECIDER"] = "off"   # tests never ask the decider (the second decider); test_memory_decide.py tests it with a fake
sys.path.insert(0, os.path.join(ROOT, "eval"))
sys.path.insert(0, os.path.join(ROOT, "ask"))
import freshness  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def hours_ago(h):
    return NOW - datetime.timedelta(hours=h)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def touch(path, when):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("# note\n")
    os.utime(path, (when.timestamp(), when.timestamp()))


def make_index(path, docs, vectors=()):
    """docs: (collection, path, modified datetime, hash); vectors: hashes that have vectors."""
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, collection TEXT, path TEXT, hash TEXT, "
               "modified_at TEXT, active INTEGER DEFAULT 1)")
    db.execute("CREATE TABLE content_vectors (hash TEXT, seq INTEGER, embedded_at TEXT)")
    for c, p, t, h in docs:
        db.execute("INSERT INTO documents (collection, path, hash, modified_at) VALUES (?,?,?,?)", (c, p, h, iso(t)))
    for h in vectors:
        db.execute("INSERT INTO content_vectors VALUES (?,0,?)", (h, iso(NOW)))
    db.commit()
    db.close()


class Folders(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.dir = self._d.name
        self.addCleanup(self._d.cleanup)

    def conf(self, name="notes", **extra):
        return {name: dict({"path": os.path.join(self.dir, name), "pattern": "**/*.md"}, **extra)}

    def run_assess(self, collections, docs, vectors=(), testbox=None):
        make_index(os.path.join(self.dir, "i.sqlite"), docs, vectors)
        state = freshness.index_state(os.path.join(self.dir, "i.sqlite"))
        return freshness.assess(collections, state, testbox, NOW)


class Behind(Folders):
    def test_in_step_is_quiet(self):
        touch(os.path.join(self.dir, "notes", "a.md"), hours_ago(1))
        r = self.run_assess(self.conf(), [("notes", "a.md", hours_ago(1), "h1")], ["h1"])
        self.assertEqual(r["warnings"], [])
        self.assertFalse(r["collections"][0]["behind"])

    def test_more_than_24_hours_behind_warns(self):
        touch(os.path.join(self.dir, "notes", "old.md"), hours_ago(80))
        touch(os.path.join(self.dir, "notes", "new.md"), hours_ago(1))
        r = self.run_assess(self.conf(), [("notes", "old.md", hours_ago(80), "h1")], ["h1"])
        self.assertTrue(r["collections"][0]["behind"])
        self.assertEqual(r["collections"][0]["behind_hours"], 79.0)
        self.assertEqual(len(r["warnings"]), 1)
        self.assertIn("notes: the index is behind by 79 h", r["warnings"][0])

    def test_23_hours_is_still_fine_and_25_is_not(self):
        touch(os.path.join(self.dir, "notes", "new.md"), hours_ago(1))
        for lag, behind in ((23, False), (25, True)):
            with self.subTest(lag=lag):
                r = self.run_assess(self.conf(), [("notes", "x.md", hours_ago(1 + lag), "h1")], ["h1"])
                self.assertEqual(r["collections"][0]["behind"], behind)
                self.assertEqual(bool(r["warnings"]), behind)

    def test_nothing_indexed_but_notes_on_disk_warns(self):
        touch(os.path.join(self.dir, "notes", "a.md"), hours_ago(1))
        r = self.run_assess(self.conf(), [])
        self.assertIn("all of it", r["warnings"][0])

    def test_an_empty_folder_is_not_behind(self):
        os.makedirs(os.path.join(self.dir, "notes"))
        self.assertEqual(self.run_assess(self.conf(), [])["warnings"], [])

    def test_a_missing_folder_is_said(self):
        r = self.run_assess(self.conf(), [("notes", "a.md", hours_ago(1), "h1")], ["h1"])
        self.assertIn("is not there", r["warnings"][0])

    def test_notes_without_vectors_warn_only_when_old(self):
        touch(os.path.join(self.dir, "notes", "a.md"), hours_ago(1))
        r = self.run_assess(self.conf(), [("notes", "a.md", hours_ago(1), "h1")])  # new, no vectors yet: normal
        self.assertEqual(r["warnings"], [])
        self.assertEqual(r["collections"][0]["no_vector"], 1)
        r = self.run_assess(self.conf(), [("notes", "a.md", hours_ago(30), "h1"), ("notes", "b.md", hours_ago(1), "h2")])
        self.assertIn("1 note(s) older than 24 h still have no", r["warnings"][0])

    def test_removed_notes_in_the_index_are_ignored(self):
        touch(os.path.join(self.dir, "notes", "a.md"), hours_ago(1))
        make_index(os.path.join(self.dir, "i.sqlite"), [("notes", "a.md", hours_ago(1), "h1"), ("notes", "g.md", hours_ago(90), "h2")], ["h1"])
        db = sqlite3.connect(os.path.join(self.dir, "i.sqlite"))
        db.execute("UPDATE documents SET active = 0 WHERE path = 'g.md'")
        db.commit()
        db.close()
        state = freshness.index_state(os.path.join(self.dir, "i.sqlite"))
        self.assertEqual(state["collections"]["notes"]["notes"], 1)
        self.assertEqual(state["collections"]["notes"]["no_vector"], [])


class WhichFiles(Folders):
    def names(self, **conf):
        c = self.conf(**conf)["notes"]
        return sorted(r for r, _ in freshness.source_files(c))

    def test_the_pattern_list_ignore_hidden_and_skipped_folders(self):
        root = os.path.join(self.dir, "notes")
        for rel in ("top.md", "a/one.md", "a/docs/two.md", "a/docs/deep/three.md", "a/other/four.md", "a/x.txt",
                    ".hid/five.md", "a/.six.md", "node_modules/m/seven.md", "skip/eight.md"):
            touch(os.path.join(root, rel), hours_ago(1))
        self.assertEqual(self.names(pattern="*/*.md,*/docs/**/*.md", ignore=["skip/**"]),
                         ["a/docs/deep/three.md", "a/docs/two.md", "a/one.md"])
        self.assertEqual(self.names(pattern="**/*.md", ignore=["skip/**"]),
                         ["a/docs/deep/three.md", "a/docs/two.md", "a/one.md", "a/other/four.md", "top.md"])

    def test_a_file_pattern_with_a_comma_list(self):
        root = os.path.join(self.dir, "notes")
        for rel in ("memories/USER.md", "memories/USER.md.bak", "SOUL.md", "auth.md"):
            touch(os.path.join(root, rel), hours_ago(1))
        self.assertEqual(self.names(pattern="memories/*.md,SOUL.md"), ["SOUL.md", "memories/USER.md"])


class RogLine(Folders):
    def testbox(self, result, detail="", at=1, ok_at=None):
        return {"at": hours_ago(at), "result": result, "detail": detail, "ok_at": hours_ago(ok_at) if ok_at else None}

    def verdict(self, testbox):
        return freshness.assess({}, {"collections": {}}, testbox, NOW)

    def test_no_record_is_not_a_warning(self):
        r = self.verdict(None)
        self.assertEqual((r["testbox"]["state"], r["warnings"]), ("unknown", []))

    def test_ok_is_quiet(self):
        r = self.verdict(self.testbox("ok", ok_at=1))
        self.assertEqual((r["testbox"]["state"], r["warnings"]), ("ok", []))

    def test_a_failed_embed_warns_and_says_why_and_the_last_good_run(self):
        r = self.verdict(self.testbox("failed", "stopped at: embedding on the test machine (exit 1)", at=2, ok_at=50))
        self.assertEqual(r["testbox"]["state"], "failed")
        self.assertIn("failed (stopped at: embedding on the test machine (exit 1))", r["warnings"][0])
        self.assertIn("last good run 2d ago", r["warnings"][0])

    def test_rog_off_for_a_while_is_fine_but_not_for_days(self):
        self.assertEqual(self.verdict(self.testbox("unreachable", at=1, ok_at=5))["warnings"], [])
        r = self.verdict(self.testbox("unreachable", at=1, ok_at=30))
        self.assertIn("not been reachable", r["warnings"][0])
        self.assertIn("not been reachable", self.verdict(self.testbox("unreachable"))["warnings"][0])

    def test_status_file_reading(self):
        p = os.path.join(self.dir, "s")
        self.assertIsNone(freshness.rog_status(p))
        for bad in ("", "{", "[1]"):
            with open(p, "w") as f:
                f.write(bad)
            self.assertIsNone(freshness.rog_status(p))
        with open(p, "w") as f:
            f.write('{"at":"2026-10-22T10:00:00Z","result":"failed","detail":"x","ok_at":""}\n')
        got = freshness.rog_status(p)
        self.assertEqual((got["result"], got["detail"], got["ok_at"]), ("failed", "x", None))
        self.assertEqual(got["at"], hours_ago(2))


class Retire(Folders):
    def test_hermes_is_named_for_retirement_and_nothing_is_removed(self):
        touch(os.path.join(self.dir, "hermes", "SOUL.md"), hours_ago(500))
        conf = self.conf("hermes")
        r = self.run_assess(conf, [("hermes", "SOUL.md", hours_ago(500), "h1")], ["h1"])
        self.assertEqual([n for n, _ in r["retire"]], ["hermes"])
        self.assertIn("qmd collection remove hermes", r["retire"][0][1])
        self.assertEqual(r["warnings"], [])  # dead, but not a fault
        self.assertTrue(os.path.exists(os.path.join(self.dir, "hermes", "SOUL.md")))
        self.assertEqual(freshness.index_state(os.path.join(self.dir, "i.sqlite"))["collections"]["hermes"]["notes"], 1)


class Commands(Folders):
    """`brain status` and the check-up, on a made-up index (paths moved by environment variables)."""

    def setUp(self):
        super().setUp()
        touch(os.path.join(self.dir, "notes", "a.md"), datetime.datetime.now(UTC) - datetime.timedelta(days=4))
        touch(os.path.join(self.dir, "notes", "b.md"), datetime.datetime.now(UTC) - datetime.timedelta(hours=1))
        now = datetime.datetime.now(UTC)
        make_index(os.path.join(self.dir, "i.sqlite"), [("notes", "a.md", now - datetime.timedelta(days=4), "h1")], ["h1"])
        with open(os.path.join(self.dir, "index.yml"), "w") as f:
            f.write(f"collections:\n  notes:\n    path: {self.dir}/notes\n    pattern: '**/*.md'\n"
                    f"  hermes:\n    path: {self.dir}/nothere\n    pattern: '*.md'\n")
        os.makedirs(os.path.join(self.dir, "state"))
        with open(os.path.join(self.dir, "state", "codex-testbox.status"), "w") as f:
            f.write('{"at":"2026-10-22T10:00:00Z","result":"failed","detail":"stopped at: copying the notes","ok_at":""}\n')
        self.env = dict(os.environ, BRAIN_LIVE_INDEX=os.path.join(self.dir, "i.sqlite"),
                        BRAIN_QMD_CONFIG=os.path.join(self.dir, "index.yml"), BRAIN_STATE_DIR=os.path.join(self.dir, "state"))

    def test_brain_status_says_it_in_plain_words(self):
        out = subprocess.run([os.path.join(ROOT, "bin", "brain"), "status"], env=self.env, capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("notes", out.stdout)
        self.assertRegex(out.stdout, r"\[BEHIND 9[45]h")  # 4 days minus 1 hour, give or take rounding
        self.assertIn("FOLDER MISSING", out.stdout)
        self.assertIn("RETIRE", out.stdout)
        self.assertIn("Codex vectors on the test machine: FAILED", out.stdout)
        self.assertIn("To retire (not deleted):", out.stdout)

    def test_brain_status_json(self):
        out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "freshness.py"), "--json"], env=self.env,
                             capture_output=True, text=True, timeout=60)
        data = json.loads(out.stdout)
        self.assertEqual({r["name"] for r in data["collections"]}, {"notes", "hermes"})
        self.assertEqual(data["testbox"]["state"], "failed")
        self.assertEqual(len(data["warnings"]), 3)  # notes behind, hermes folder missing, the test machine embed

    def test_the_checkup_prints_the_warnings_first(self):
        import checkup
        for k, v in self.env.items():
            if k.startswith("BRAIN_"):
                os.environ[k] = v
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in self.env if k.startswith("BRAIN_")])
        lines = checkup.freshness_lines()
        self.assertEqual(sum(l.startswith("!! ") for l in lines), 3)
        self.assertTrue(any("to retire (not deleted): hermes" in l for l in lines))
        self.assertEqual(checkup.freshness_lines({"warnings": [], "retire": []}), [])

    def test_a_missing_index_file_is_a_warning_not_a_crash(self):
        env = dict(self.env, BRAIN_LIVE_INDEX=os.path.join(self.dir, "none.sqlite"))
        out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "freshness.py")], env=env, capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("is not there", out.stdout)


class CodexRogScript(Folders):
    """index/codex-testbox.sh with fake ssh, rsync and node first on the path: it must leave the right status line."""

    def setUp(self):
        super().setUp()
        self.fake = os.path.join(self.dir, "fake")
        os.makedirs(self.fake)
        self.state = os.path.join(self.dir, "state")
        self.notes = os.path.join(self.dir, "codexnotes")
        os.makedirs(self.notes)
        self.status = os.path.join(self.state, "codex-testbox.status")
        self.env = dict(os.environ, PATH=self.fake + os.pathsep + os.environ["PATH"], BRAIN_STATE_DIR=self.state,
                        BRAIN_CODEX_NOTES=self.notes, BRAIN_ROG_HOST="nobody@invalid.invalid",
                        BRAIN_LIVE_INDEX=os.path.join(self.dir, "live.sqlite"), BRAIN_NODE=os.path.join(self.fake, "node"))

    def fake_cmd(self, name, body):
        p = os.path.join(self.fake, name)
        with open(p, "w") as f:
            f.write("#!/usr/bin/env bash\n" + body + "\n")
        os.chmod(p, 0o755)

    def run_script(self):
        return subprocess.run(["bash", os.path.join(HERE, "codex-testbox.sh")], env=self.env, capture_output=True,
                              text=True, timeout=60)

    def read(self):
        with open(self.status) as f:
            return json.loads(f.read())

    def test_rog_off_is_recorded_as_unreachable_and_is_not_an_error(self):
        self.fake_cmd("ssh", "exit 255")
        out = self.run_script()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.read()["result"], "unreachable")

    def test_a_failed_copy_is_recorded_as_failed_with_the_step(self):
        self.fake_cmd("ssh", "exit 0")
        self.fake_cmd("rsync", "exit 23")
        out = self.run_script()
        self.assertNotEqual(out.returncode, 0)
        got = self.read()
        self.assertEqual(got["result"], "failed")
        self.assertIn("copying the notes to the test machine (exit 23)", got["detail"])

    def test_a_good_run_is_ok_and_a_later_failure_keeps_the_last_good_time(self):
        self.fake_cmd("ssh", "exit 0")
        self.fake_cmd("rsync", "exit 0")
        self.fake_cmd("node", "exit 0")
        self.assertEqual(self.run_script().returncode, 0)
        good = self.read()
        self.assertEqual((good["result"], good["ok_at"]), ("ok", good["at"]))
        self.fake_cmd("node", "exit 3")
        self.assertNotEqual(self.run_script().returncode, 0)
        bad = self.read()
        self.assertEqual(bad["result"], "failed")
        self.assertIn("merging the vectors (exit 3)", bad["detail"])
        self.assertEqual(bad["ok_at"], good["ok_at"])
        # and the check-up side reads it as a failed embed
        self.assertEqual(freshness.rog_status(self.status)["result"], "failed")

    def test_no_codex_notes_yet_leaves_no_status(self):
        self.env["BRAIN_CODEX_NOTES"] = os.path.join(self.dir, "missing")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertFalse(os.path.exists(self.status))


if __name__ == "__main__":
    unittest.main()
