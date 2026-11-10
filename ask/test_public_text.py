"""What this copy prints to a user says "you", never the <user> placeholder: python3 -I ask/test_public_text.py"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


class PublicText(unittest.TestCase):
    def run_brain(self, *argv):
        home = tempfile.mkdtemp()
        env = dict(os.environ, HOME=home, BRAIN_STATE=os.path.join(home, "state"))
        return subprocess.run([os.path.join(ROOT, "bin", "brain"), *argv], capture_output=True, text=True, env=env, timeout=60)

    def test_the_help_says_you(self):
        out = self.run_brain()
        self.assertNotIn("<user>", out.stdout + out.stderr)

    def test_the_memory_hook_text_says_your(self):
        import memory_hook
        self.assertNotIn("<user>", memory_hook.header("demo", 3))
        self.assertIn("from your memory store", memory_hook.header("demo", 3))

    def test_the_alarm_help_says_you(self):
        text = open(os.path.join(ROOT, "jobs", "bin", "alarm")).read().split('"""')[1]
        self.assertNotIn("<user>", text)


class Runner(unittest.TestCase):
    def test_the_test_runner_covers_the_deck_app_test(self):
        text = open(os.path.join(ROOT, "bin", "test")).read()
        self.assertIn("deck/app/test/rules.test.js", text)
        self.assertIn("fail=1", text.split("deck app")[1])   # a failure there fails the run


if __name__ == "__main__":
    unittest.main()
