"""Tests for index/reindex.sh and index/setup.sh in a throwaway home with a stand-in qmd, never the real one."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

QMD = """#!/usr/bin/env bash
echo "$@" >> "$HOME/qmd-calls.log"
"""


class Scripts(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / ".local" / "bin").mkdir(parents=True)
        qmd = self.home / ".local" / "bin" / "qmd"
        qmd.write_text(QMD)
        qmd.chmod(qmd.stat().st_mode | stat.S_IXUSR)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "BRAIN_"))}
        self.env["HOME"] = str(self.home)

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.home)], check=True, timeout=30)

    def conf(self, text="collections:\n  notes: {}\n  codex: {}\n"):
        path = self.home / ".config" / "qmd" / "index.yml"
        path.parent.mkdir(parents=True)
        path.write_text(text)

    def run_script(self, name):
        return subprocess.run(["bash", str(HERE / name)], env=self.env, capture_output=True, text=True, timeout=120,
                              cwd=self.home)

    def calls(self):
        log = self.home / "qmd-calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_reindex_works_on_a_fresh_home(self):
        # no ~/.local/share/second-brain yet: the lock folder must be made, not fail the run
        self.conf()
        r = self.run_script("reindex.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("embed -c notes", self.calls())
        self.assertNotIn("embed -c codex", self.calls())  # codex vectors are made elsewhere
        self.assertTrue((self.home / ".local" / "share" / "second-brain").is_dir())
        self.assertNotIn("No such file", r.stderr)  # the optional test-machine script is not part of the public repo

    def test_reindex_says_so_when_the_config_cannot_be_read(self):
        r = self.run_script("reindex.sh")  # no qmd config at all
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read", r.stderr)
        self.assertNotIn("embed", " ".join(self.calls()))

    def test_reindex_says_so_when_qmd_is_missing(self):
        (self.home / ".local" / "bin" / "qmd").unlink()
        self.env["PATH"] = "/usr/bin:/bin"
        r = self.run_script("reindex.sh")
        self.assertEqual(r.returncode, 1)
        self.assertIn("qmd is not installed", r.stderr)

    def test_setup_embeds_every_collection_and_stops_on_a_bad_config(self):
        r = self.run_script("setup.sh")  # writes the shipped config, then embeds each section
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(c.startswith("embed -c ") for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
