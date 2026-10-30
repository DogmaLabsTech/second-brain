"""Tests for media/media.py (the media store). Run: python3 -I media/test_media.py. Made-up files in a temp folder."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import media  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = media.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = os.path.realpath(self.tmp.name)
        self.old = (media.STORE, media.caller)
        media.STORE = os.path.join(self.t, "store")
        os.makedirs(media.STORE)
        media.caller = lambda: ("", "")
        self.src = os.path.join(self.t, "src")
        os.makedirs(self.src)
        # no search server in tests: find() falls back to the direct sidecar read only
        sys.modules["ask"] = type(sys)("ask")
        sys.modules["ask"].search = lambda q, limit=5: []

    def tearDown(self):
        media.STORE, media.caller = self.old[0], self.old[1]
        sys.modules.pop("ask", None)
        self.tmp.cleanup()

    def shot(self, name="Shot 1.PNG", data=b"png"):
        p = os.path.join(self.src, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def add(self, **kw):
        kw.setdefault("why", "the bar with the clock open")
        kw.setdefault("project", "omarchy-setup")
        kw.setdefault("commit", "abc1234")
        kw.setdefault("date", "2026-10-30")
        return media.add(self.shot(), **kw)

    def test_add_moves_file_and_writes_sidecar(self):
        dest = self.add(name="Bar clock")
        self.assertEqual(dest, os.path.join(media.STORE, "omarchy-setup", "2026-10-30-bar-clock.png"))
        self.assertFalse(os.path.exists(os.path.join(self.src, "Shot 1.PNG")))
        meta, body = media.read_sidecar(dest + ".md")
        self.assertEqual((meta["project"], meta["date"], meta["commit"], meta["kind"]), ("omarchy-setup", "2026-10-30", "abc1234", "image"))
        self.assertEqual(meta["public"], "false")
        self.assertIn("the bar with the clock open", body)

    def test_why_is_required(self):
        with self.assertRaises(media.MediaError):
            media.add(self.shot(), why="  ")
        self.assertTrue(os.path.exists(os.path.join(self.src, "Shot 1.PNG")))   # nothing moved
        code, _, err = run("add", self.shot("b.png"))
        self.assertEqual(code, 2)
        self.assertIn("say why", err)

    def test_same_name_twice_and_date_prefix_not_doubled(self):
        a = self.add(name="2026-10-30-bar")
        b = self.add(name="bar")
        self.assertTrue(a.endswith("2026-10-30-bar.png"))
        self.assertTrue(b.endswith("2026-10-30-bar-2.png"))

    def test_sources_kept_beside_and_before_link(self):
        clip = self.shot("raw.mp4")
        first = self.add(name="before")
        dest = media.add(self.shot("g.gif"), why="the fix as a GIF", project="omarchy-setup", name="fixed",
                         sources=[clip], before=os.path.basename(first), commit="", date="2026-10-30")
        meta, _ = media.read_sidecar(dest + ".md")
        self.assertEqual(meta["sources"], ["omarchy-setup/2026-10-30-fixed-source.mp4"])
        self.assertTrue(os.path.exists(os.path.join(media.STORE, meta["sources"][0])))
        self.assertEqual(meta["before"], "omarchy-setup/2026-10-30-before.png")
        self.assertNotIn("commit", meta)

    def test_already_in_store_and_missing_file(self):
        dest = self.add()
        with self.assertRaises(media.MediaError):
            media.add(dest, why="x")
        with self.assertRaises(media.MediaError):
            media.add(os.path.join(self.src, "nope.png"), why="x")

    def test_add_then_find(self):
        dest = self.add(why='The "island" shows 3 timers: "quoted" text, with: colons')
        code, out, _ = run("find", "island", "timers")
        self.assertEqual(code, 0)
        self.assertIn(dest, out)
        self.assertEqual(run("find", "unrelated", "words")[0], 1)

    def test_private_by_default_and_only_public_marks_public(self):
        dest = self.add()
        other = media.add(self.shot("o.png"), why="other", project="omarchy-setup", commit="", date="2026-10-30")
        self.assertEqual(media.public_items(), [])
        code, out, _ = run("public", os.path.basename(dest))
        self.assertEqual(code, 0)
        self.assertEqual(media.public_items(), [dest])
        self.assertNotIn(other, media.public_items())
        self.assertEqual(run("public", "--list")[1].strip(), dest)
        run("public", os.path.basename(dest), "--off")
        self.assertEqual(media.public_items(), [])

    def test_agent_cannot_mark_public(self):
        dest = self.add()
        media.caller = lambda: ("claude", "builder")
        code, _, err = run("public", os.path.basename(dest))
        self.assertEqual(code, 2)
        self.assertIn("only <user>", err)
        self.assertEqual(media.public_items(), [])

    def test_damaged_public_line_is_private(self):
        dest = self.add()
        with open(dest + ".md") as f:
            text = f.read().replace("public: false", "public: True ")
        with open(dest + ".md", "w") as f:
            f.write(text)
        self.assertEqual(media.public_items(), [])

    def test_id_must_be_unique(self):
        a = self.add(name="x")
        media.add(self.shot("y.png"), why="y", project="other", name="x", commit="", date="2026-10-30")
        with self.assertRaises(media.MediaError):
            media.resolve("2026-10-30-x.png")
        self.assertEqual(media.resolve("omarchy-setup/2026-10-30-x.png"), os.path.relpath(a, media.STORE))

    def test_project_from_folder(self):
        home = media.HOME
        self.assertEqual(media.project_of(os.path.join(home, "projects", "Projects", "second-brain", "day")), "second-brain")
        self.assertEqual(media.project_of(os.path.join(home, ".agent-os", "worktrees", "second-brain", "w1")), "second-brain")
        self.assertEqual(media.project_of(self.t), "")


class Stray(unittest.TestCase):
    def test_untracked_media_in_repo_is_stray_tracked_is_not(self):
        with tempfile.TemporaryDirectory() as t:
            t = os.path.realpath(t)
            git = lambda *a: subprocess.run(["git", "-C", t, *a], check=True, capture_output=True)  # noqa: E731
            git("init", "-q")
            for n in ("logo.png", "stray.png", "clip.webm", "notes.txt"):
                with open(os.path.join(t, n), "wb") as f:
                    f.write(b"x")
            os.makedirs(os.path.join(t, "node_modules"))
            with open(os.path.join(t, "node_modules", "dep.png"), "wb") as f:
                f.write(b"x")
            git("add", "logo.png")
            found = media.stray([t])
            self.assertEqual(found, [os.path.join(t, "clip.webm"), os.path.join(t, "stray.png")])
            code, out, err = run("stray", t, "--list")
            self.assertEqual(code, 1)
            self.assertIn("stray.png", out)
            self.assertIn("media add", err)
            code, out, err = run("stray", t)
            self.assertEqual(code, 1)
            self.assertNotIn("stray.png", out)
            self.assertIn("(other)", out)
            self.assertIn("2  total", out)
            self.assertEqual(media.stray(path=os.path.join(t, "logo.png")), [])
            self.assertEqual(media.stray(path=os.path.join(t, "stray.png")), [os.path.join(t, "stray.png")])
            self.assertEqual(media.stray([t], days=1)[0], os.path.join(t, "clip.webm"))
            os.utime(os.path.join(t, "clip.webm"), (1, 1))
            self.assertNotIn(os.path.join(t, "clip.webm"), media.stray([t], days=1))

    def test_worktrees_skipped_unless_asked_and_counted_per_project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = os.path.join(os.path.realpath(tmp.name), "home")
        wt = os.path.join(home, ".agent-os", "worktrees", "repo-a", "w1")
        proj = os.path.join(home, "projects", "Projects", "repo-b")
        for d in (wt, proj):
            os.makedirs(d)
            for n in ("a.png", "b.png"):
                with open(os.path.join(d, n), "wb") as f:
                    f.write(b"x")
        with mock.patch.object(media, "HOME", home), mock.patch.object(media, "STRAY_ROOTS", [os.path.join(home, "projects", "Projects")]):
            self.assertEqual(media.stray(), [os.path.join(proj, "a.png"), os.path.join(proj, "b.png")])
            self.assertEqual(len(media.stray(worktrees=True)), 4)
            code, out, _ = run("stray")
            self.assertIn("2  repo-b", out)
            self.assertNotIn("repo-a", out)
            self.assertIn("2  total", out)
            code, out, _ = run("stray", "--worktrees")
            self.assertIn("2  repo-a", out)
            self.assertIn("4  total", out)

    def test_clean_folder_exits_0(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(run("stray", t)[0], 0)


class StrayWatch(unittest.TestCase):
    def setUp(self):
        import stray_watch
        self.w = stray_watch
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = os.path.realpath(self.tmp.name)
        self.proj = os.path.join(t, "home", "projects", "Projects", "repo-b")
        os.makedirs(self.proj)
        self.told = []
        for target, value in ((media, ("HOME", os.path.join(t, "home"))), (media, ("STRAY_ROOTS", [os.path.dirname(self.proj)])),
                              (self.w, ("STATE", os.path.join(t, "state", "counts.json")))):
            p = mock.patch.object(target, value[0], value[1])
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.w, "tell", lambda text: self.told.append(text) or True)
        p.start()
        self.addCleanup(p.stop)

    def stray(self, *names):
        for n in names:
            with open(os.path.join(self.proj, n), "wb") as f:
                f.write(b"x")

    def test_new_strays_tell_once_unchanged_stays_quiet(self):
        self.assertEqual(self.w.main([]), 0)
        self.assertEqual(self.told, [])  # nothing stray: quiet
        self.stray("a.png", "b.gif")
        self.w.main([])
        self.assertEqual(len(self.told), 1)
        self.assertIn("repo-b +2 (2)", self.told[0])
        self.w.main([])
        self.assertEqual(len(self.told), 1)  # same two files: quiet
        self.stray("c.png")
        self.w.main([])
        self.assertEqual(len(self.told), 2)
        self.assertIn("repo-b +1 (3)", self.told[1])

    def test_fewer_strays_quiet_and_remembered(self):
        self.stray("a.png", "b.png")
        self.w.main([])
        os.remove(os.path.join(self.proj, "b.png"))
        self.w.main([])
        self.assertEqual(len(self.told), 1)  # 2 -> 1: quiet, but 1 is remembered
        self.stray("b.png")
        self.w.main([])
        self.assertEqual(len(self.told), 2)  # 1 -> 2 is new again

    def test_failed_tell_keeps_old_counts_and_dry_run_changes_nothing(self):
        self.stray("a.png")
        self.assertEqual(self.w.main(["--dry-run"]), 0)
        self.assertEqual((self.told, os.path.exists(self.w.STATE)), ([], False))
        with mock.patch.object(self.w, "tell", lambda text: False):
            self.assertEqual(self.w.main([]), 1)
        self.assertFalse(os.path.exists(self.w.STATE))  # not saved: tomorrow tells again
        self.w.main([])
        self.assertEqual(len(self.told), 1)


if __name__ == "__main__":
    unittest.main()
