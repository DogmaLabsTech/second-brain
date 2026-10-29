"""Tests for index/brain-backup.sh: a temp brain and a temp target, never the real ones."""
import os
import subprocess
import tarfile
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "brain-backup.sh"


class BrainBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = self.tmp / "brain"
        (self.store / "projects" / "second-brain" / "lessons").mkdir(parents=True)
        (self.store / "projects" / "second-brain" / "lessons" / "one.md").write_text("a lesson\n")
        (self.store / "drafts").mkdir()
        (self.store / "drafts" / "unsaved.md").write_text("not committed\n")
        subprocess.run(["git", "init", "-q", str(self.store)], check=True, timeout=30)
        self.dest = self.tmp / "hdd" / "brain"

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)], check=True, timeout=30)

    def run_backup(self, mount="/", store=None):
        env = dict(os.environ, BRAIN_DIR=str(store or self.store), BRAIN_BACKUP_MOUNT=mount,
                   BRAIN_BACKUP_DIR=str(self.dest))
        return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)

    def copies(self):
        return sorted(p.name for p in self.dest.glob("brain-*.tar.gz"))

    def test_a_copy_holds_notes_drafts_and_git(self):
        r = self.run_backup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.copies(), [f"brain-{date.today():%F}.tar.gz"])
        with tarfile.open(self.dest / self.copies()[0]) as t:
            names = t.getnames()
        self.assertIn("brain/projects/second-brain/lessons/one.md", names)
        self.assertIn("brain/drafts/unsaved.md", names)
        self.assertIn("brain/.git/HEAD", names)
        self.assertTrue((self.dest / "last-copy.txt").is_file())
        self.assertEqual(list(self.dest.glob("*.tmp")), [])

    def test_a_copy_holds_every_section_private_included(self):
        for section in ("private/finance", "chats", "days", "rules"):
            (self.store / section).mkdir(parents=True)
            (self.store / section / "note.md").write_text("x\n")
        self.assertEqual(self.run_backup().returncode, 0)
        with tarfile.open(self.dest / self.copies()[0]) as t:
            names = t.getnames()
        for section in ("private/finance", "chats", "days", "rules"):
            self.assertIn(f"brain/{section}/note.md", names)

    def test_no_copy_when_the_drive_is_not_mounted(self):
        not_mounted = self.tmp / "empty-mount"
        not_mounted.mkdir()
        r = self.run_backup(mount=str(not_mounted))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not mounted", r.stderr)
        self.assertFalse(self.dest.exists())

    def test_no_copy_when_the_brain_is_missing(self):
        r = self.run_backup(store=self.tmp / "nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not there", r.stderr)
        self.assertFalse(self.dest.exists())

    def test_keeps_the_14_newest_and_nothing_else_is_touched(self):
        self.dest.mkdir(parents=True)
        for day in range(1, 15):
            (self.dest / f"brain-2020-01-{day:02d}.tar.gz").write_text("old")
        (self.dest / "notes.txt").write_text("not a copy")
        r = self.run_backup()
        self.assertEqual(r.returncode, 0, r.stderr)
        copies = self.copies()
        self.assertEqual(len(copies), 14)
        self.assertNotIn("brain-2020-01-01.tar.gz", copies)
        self.assertIn(f"brain-{date.today():%F}.tar.gz", copies)
        self.assertTrue((self.dest / "notes.txt").is_file())

    def test_a_second_run_the_same_day_replaces_that_days_copy(self):
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(len(self.copies()), 1)

    def test_a_failed_copy_leaves_nothing_behind(self):
        self.assertEqual(self.run_backup().returncode, 0)
        good = (self.dest / self.copies()[0]).read_bytes()
        bad = self.store / "drafts" / "unreadable.md"
        bad.write_text("x")
        bad.chmod(0)
        r = self.run_backup()
        bad.chmod(0o600)
        self.assertEqual(r.returncode, 1)
        self.assertIn("tar failed", r.stderr)
        self.assertEqual(list(self.dest.glob("*.tmp")), [])
        self.assertEqual((self.dest / self.copies()[0]).read_bytes(), good)

    def test_copies_are_for_owner_only(self):
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual((self.dest / self.copies()[0]).stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
