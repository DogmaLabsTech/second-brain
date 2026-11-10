"""brain log / rate / outcome say plainly when the input or the log is odd: python3 -I ask/test_asklog.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "jobs"))
import asklog  # noqa: E402


class Log(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = (asklog.ASKS, asklog.RATINGS)
        asklog.ASKS = os.path.join(self.tmp.name, "asks.jsonl")
        asklog.RATINGS = os.path.join(self.tmp.name, "ratings.jsonl")
        self.addCleanup(lambda: setattr(asklog, "ASKS", self.saved[0]) or setattr(asklog, "RATINGS", self.saved[1]))

    def put(self, path, *lines):
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def run_cmd(self, fn, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fn(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_one_cut_line_does_not_hide_the_rest_of_the_log(self):
        good = lambda i: json.dumps({"id": i, "at": "2026-11-01T10:00:00", "q": "question " + i})  # noqa: E731
        self.put(asklog.ASKS, good("a"), '{"id": "b", "q": "cut her', good("c"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows = asklog.read(asklog.ASKS)
        self.assertEqual([r["id"] for r in rows], ["a", "c"])
        self.assertIn("skipped 1 damaged line", err.getvalue())

    def test_a_row_that_is_not_an_object_is_left_out(self):
        self.put(asklog.ASKS, "[1, 2]", json.dumps({"id": "a", "at": "x", "q": "q"}))
        self.assertEqual([r["id"] for r in asklog.read(asklog.ASKS)], ["a"])

    def test_log_with_a_bad_number_says_how_to_use_it(self):
        code, _, err = self.run_cmd(asklog._cmd_log, "log", "abc")
        self.assertEqual(code, 2)
        self.assertIn("brain log", err)
        self.assertNotIn("Traceback", err)

    def test_log_prints_a_row_that_lacks_q_or_at(self):
        self.put(asklog.ASKS, json.dumps({"id": "a"}))
        code, out, _ = self.run_cmd(asklog._cmd_log, "log")
        self.assertEqual(code, 0)
        self.assertIn("ms", out)

    def test_rate_with_a_word_other_than_up_or_down_says_so(self):
        code, _, err = self.run_cmd(asklog._cmd_rate, "rate", "1", "sideways")
        self.assertEqual(code, 2)
        self.assertIn("say up or down", err)
        self.assertFalse(os.path.exists(asklog.RATINGS))

    def test_rate_last_ignores_rows_without_an_id(self):
        self.put(asklog.ASKS, json.dumps({"q": "no id"}), json.dumps({"id": "z9", "q": "q", "at": "x"}))
        code, out, _ = self.run_cmd(asklog._cmd_rate, "rate", "last", "up")
        self.assertEqual((code, out.strip()), (0, "noted up for z9"))


class NotesCollections(unittest.TestCase):
    def test_reading_the_added_collections_leaves_no_file_open_and_decodes_quoted_paths(self):
        import ask
        conf_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(conf_dir, "qmd"))
        odd = '/tmp/my "best" notes\\v2'
        with open(os.path.join(conf_dir, "qmd", "index.yml"), "w") as f:
            f.write("collections:\n  notes-odd:\n    path: %s\n" % json.dumps(odd))
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = conf_dir
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                found = ask._added_collections()
                import gc
                gc.collect()
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME")
            else:
                os.environ["XDG_CONFIG_HOME"] = old
        self.assertEqual(found, {"notes-odd": odd})
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])


if __name__ == "__main__":
    unittest.main()
