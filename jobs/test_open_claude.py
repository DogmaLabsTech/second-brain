"""Tests for jobs/bin/open-claude (start-claude's command): python3 -I jobs/test_open_claude.py. Nothing is opened."""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    path = os.path.join(HERE, "bin", "open-claude")
    loader = importlib.machinery.SourceFileLoader("open_claude", path)
    spec = importlib.util.spec_from_loader("open_claude", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class OpenClaude(unittest.TestCase):
    def setUp(self):
        self.oc = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, "example"))
        p = mock.patch.object(self.oc, "PROJECTS", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def test_a_project_opens_claude_in_its_folder_apart_from_the_runner(self):
        with mock.patch.object(self.oc.subprocess, "Popen") as popen:
            self.assertEqual(self.oc.main(["example"]), 0)
        argv, kw = popen.call_args
        self.assertIn(f"--dir={os.path.join(self.tmp.name, 'example')}", argv[0])
        self.assertEqual(argv[0][-1], "claude")
        self.assertTrue(kw["start_new_session"])

    def test_the_desk_is_agent_os(self):
        self.assertEqual(self.oc.folder("desk"), os.path.join(self.oc.HOME, "agent-os"))

    def test_unknown_or_odd_names_open_nothing(self):
        with mock.patch.object(self.oc.subprocess, "Popen") as popen:
            for bad in ([], ["nope"], ["../etc"], [".hidden"]):
                self.assertEqual(self.oc.main(bad), 2, bad)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
