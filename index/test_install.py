"""install.sh --json lists each missing item on its own: python3 -I index/test_install.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class InstallJson(unittest.TestCase):
    def tools(self, *names):
        """A bin folder with links to only these tools, so the others look missing."""
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        for n in names:
            real = sys.executable if n == "python3" else shutil.which(n)
            if real:
                os.symlink(real, os.path.join(d, n))
        return d

    def run_json(self, bin_dir):
        env = {"PATH": bin_dir, "HOME": tempfile.mkdtemp()}
        out = subprocess.run([shutil.which("bash"), os.path.join(ROOT, "install.sh"), "--json"], env=env,
                             capture_output=True, text=True, timeout=120)
        return out.returncode, json.loads(out.stdout)

    def test_each_missing_and_optional_item_is_its_own_list_entry(self):
        bin_dir = self.tools("python3", "timeout", "readlink", "dirname", "cat", "env")   # no git, no qmd, no ollama, no claude
        code, got = self.run_json(bin_dir)
        self.assertEqual(code, 1)
        self.assertFalse(got["ok"])
        self.assertIn("git", got["missing"])
        self.assertIn("qmd", got["missing"])
        self.assertTrue(all(" " not in m or m.startswith(("python", "node")) for m in got["missing"]), got["missing"])
        for item in ("ollama", "claude"):
            self.assertIn(item, got["optional_missing"])      # not one string "numpy ollama claude"
        self.assertNotIn("numpy ollama claude", got["optional_missing"])

    def test_a_name_with_a_space_stays_whole(self):
        # "node 22.12+" is one name: it must not be split at its space
        code, got = self.run_json(self.tools("python3", "timeout", "readlink", "dirname", "cat", "env"))
        self.assertIn("node 22.12+", got["optional_missing"])


if __name__ == "__main__":
    unittest.main()
