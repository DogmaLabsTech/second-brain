"""Tests for the agent-os jobs (remember-fix, start-job): rules, the job card, the argument checks, the detached
start in jobs/bin/agent-os-start and the routing in ask.ask(). The real agent-os is never run: a fake `agent-os`
and a fake `systemd-run` sit first on PATH in a temp folder and record their arguments.
Run: CRABBOX_LOCAL=1 python3 -I jobs/test_agent_jobs.py -v"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "ask"))
os.environ["BRAIN_STATE"] = tempfile.mkdtemp()
import jobs  # noqa: E402
import ask  # noqa: E402

START = os.path.join(HERE, "bin", "agent-os-start")
FOLDER_NAME = "20261016-1830-fix-the-thing"
TEXT = "fix the thing on my remember list tonight"
FAILED = "I couldn't start that job."
STARTED = "Started. It will wait for your go."

FAKE_AGENT_OS = '''#!%(py)s
import json, os, sys, time
argv = sys.argv[1:]
with open(os.environ["FAKE_CALLS"], "a") as f:
    f.write(json.dumps({"tool": "agent-os", "argv": argv}) + "\\n")
mode = os.environ.get("FAKE_HEAR_MODE", "ok")
if argv and argv[0] == "hear":
    if mode == "fail":
        sys.exit(1)
    name = os.environ.get("FAKE_FOLDER_NAME", "%(name)s")
    folder = os.path.join(os.environ["AGENT_OS_HOME"], name)
    os.makedirs(folder, exist_ok=True)
    if mode != "noask":
        with open(os.path.join(folder, "ask.md"), "w") as f:
            f.write("heard: " + argv[-1] + "\\nhow: " + argv[2] + "\\nwhen: 2026-10-16 18:30\\n")
    if mode != "noline":
        print("job: " + folder)
    sys.exit(0)
if argv and argv[0] == "run":
    time.sleep(30)
'''

FAKE_SYSTEMD_RUN = '''#!%(py)s
import json, os, subprocess, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_CALLS"], "a") as f:
    f.write(json.dumps({"tool": "systemd-run", "argv": argv}) + "\\n")
cmd = argv[argv.index("--") + 1:]
subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 start_new_session=True)
sys.exit(0)
'''


def load_start():
    loader = importlib.machinery.SourceFileLoader("agent_os_start", START)
    spec = importlib.util.spec_from_loader("agent_os_start", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def known_projects():
    """The real project list, plus the names these tests use if this machine doesn't have them."""
    return sorted(set(jobs.project_names()) | {"agent-os", "example-game", "example", "example-rpg"})


class Fakes(unittest.TestCase):
    """A temp folder with the fake agent-os and systemd-run first on PATH."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="agent-jobs-test-"))
        self.bin = os.path.join(self.tmp, "bin")
        self.home = os.path.join(self.tmp, "agent-os-home")
        os.makedirs(self.bin)
        os.makedirs(self.home)
        self.calls_file = os.path.join(self.tmp, "calls.jsonl")
        open(self.calls_file, "w").close()
        self.fake = os.path.join(self.bin, "agent-os")
        for path, body in ((self.fake, FAKE_AGENT_OS), (os.path.join(self.bin, "systemd-run"), FAKE_SYSTEMD_RUN)):
            with open(path, "w") as f:
                f.write(body % {"py": sys.executable, "name": FOLDER_NAME})
            os.chmod(path, 0o755)
        env = {"PATH": self.bin + os.pathsep + os.environ.get("PATH", ""), "AGENT_OS_BIN": self.fake,
               "AGENT_OS_HOME": self.home, "FAKE_CALLS": self.calls_file}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for k in ("AGENT_OS_DRY_RUN", "BRAIN_DETACH", "FAKE_HEAR_MODE", "FAKE_FOLDER_NAME"):
            os.environ.pop(k, None)

    def tearDown(self):
        subprocess.run(["pkill", "-f", self.tmp], capture_output=True)
        time.sleep(0.05)
        subprocess.run(["rm", "-rf", self.tmp], capture_output=True)

    def calls(self, tool=None):
        with open(self.calls_file) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        return [r for r in rows if tool is None or r["tool"] == tool]

    def wait_for(self, pred, seconds=3.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if pred():
                return True
            time.sleep(0.05)
        return pred()

    def run_job(self, job_id, text, how="typed"):
        obj = jobs.build(job_id, text, how=how)["job"]
        return self.run_obj(job_id, obj)

    def run_obj(self, job_id, obj):
        out = io.StringIO()
        t0 = time.monotonic()
        with contextlib.redirect_stdout(out):
            code = jobs.run(job_id, obj)
        return code, out.getvalue(), time.monotonic() - t0

    def message(self, printed):
        return json.loads(printed.strip().splitlines()[-1])["message"]


class Rules(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(jobs, "project_names", return_value=known_projects())
        p.start()
        self.addCleanup(p.stop)

    def test_remember_fix_phrases(self):
        for text in (TEXT, "Hey Claude, sort out the thing on my remembered list",
                     "do the thing on my remember list", "take care of the thing from my remember list"):
            self.assertEqual(jobs.match_rule(text), "remember-fix", text)

    def test_start_job_phrases(self):
        for text in ("start a job on agent-os: make the report shorter",
                     "start a job on example-game fix the map loading"):
            self.assertEqual(jobs.match_rule(text), "start-job", text)

    def test_not_agent_jobs(self):
        for text in ("what's on my remembered list?", "what's on my remember list",
                     "can you remember to fix the sink", "what should I fix on my remember list",
                     "fix the thing on my remember list and then start a job on example: the logs",
                     "fix the thing on my remember list tonight. Also open spotify",
                     "how do I fix the thing on my remember list"):
            self.assertNotIn(jobs.match_rule(text), jobs.AGENT_JOBS, text)

    def test_other_jobs_keep_their_phrases(self):
        self.assertEqual(jobs.match_rule("remember that the dentist is on friday"), "remember")
        for text in ("start a claude on example-game", "start working on example", "open the example-rpg PM"):
            self.assertEqual(jobs.match_rule(text), "start-claude", text)


class Build(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(jobs, "project_names", return_value=known_projects())
        p.start()
        self.addCleanup(p.stop)

    def test_remember_fix_card(self):
        out = jobs.build("remember-fix", "Hey Claude, " + TEXT + "?")
        self.assertEqual(out["kind"], "job")
        job = out["job"]
        self.assertEqual(job["id"], "remember-fix")
        self.assertTrue(job["needs_confirm"])
        self.assertEqual(job["label"], "Start a fix from your remember list")
        self.assertEqual(job["args"], {"text": TEXT, "how": "typed"})

    def test_how_voice(self):
        self.assertEqual(jobs.build("remember-fix", TEXT, how="voice")["job"]["args"]["how"], "voice")
        self.assertEqual(jobs.build("remember-fix", TEXT, how="bogus")["job"]["args"]["how"], "typed")

    def test_start_job_card(self):
        job = jobs.build("start-job", "start a job on agent-os: make the report shorter")["job"]
        self.assertEqual(job["label"], "Start a job on Agent Os")
        self.assertEqual(job["args"]["project"], "agent-os")
        self.assertTrue(job["needs_confirm"])
        job = jobs.build("start-job", "start a job on example-game fix the map loading")["job"]
        self.assertEqual(job["label"], "Start a job on Example Game")
        self.assertEqual(job["args"]["project"], "example-game")

    def test_start_job_without_a_task_is_an_answer(self):
        out = jobs.build("start-job", "start a job on agent-os")
        self.assertEqual((out["kind"], out["job"]), ("answer", None))

    def test_start_job_unknown_project_is_an_answer(self):
        out = jobs.build("start-job", "start a job on zzzqqq: do it")
        self.assertEqual((out["kind"], out["job"]), ("answer", None))


class Refuses(Fakes):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(jobs, "project_names", return_value=known_projects())
        p.start()
        self.addCleanup(p.stop)

    def refused(self, job_id, args):
        open(self.calls_file, "w").close()
        code, printed, _ = self.run_obj(job_id, {"args": args})
        self.assertNotEqual(code, 0, args)
        self.assertTrue(self.message(printed), args)
        self.assertEqual(self.calls(), [], args)

    def test_bad_text_never_reaches_agent_os(self):
        for text in ("two\nlines", "", "   ", "-rf everything", "x" * 600, None):
            with self.subTest(text=text):
                self.refused("remember-fix", {"text": text, "how": "typed"})

    def test_start_job_bad_project(self):
        for project in ("nonesuch", "desk", "", None):
            self.refused("start-job", {"project": project, "text": "do it", "how": "typed"})

    def test_check_normalises_how(self):
        got = jobs._check("remember-fix", {"text": "a  b", "how": "shout"})
        self.assertEqual(got, {"text": "a b", "how": "typed"})


class Starting(Fakes):
    def test_detached_start_with_systemd_run(self):
        code, printed, secs = self.run_job("remember-fix", TEXT)
        self.assertEqual(code, 0)
        self.assertLess(secs, 5)   # the fake run sleeps 30 s: the start is detached
        self.assertEqual(self.message(printed), STARTED)
        hear = self.calls("agent-os")[0]["argv"]
        self.assertEqual(hear, ["hear", "--how", "typed", "--", TEXT])
        folder = os.path.join(self.home, FOLDER_NAME)
        sd = self.calls("systemd-run")
        self.assertEqual(len(sd), 1)
        argv = sd[0]["argv"]
        self.assertEqual(argv[argv.index("--unit") + 1], "agent-os-" + FOLDER_NAME)
        self.assertEqual(argv[argv.index("--") + 1:], [self.fake, "run", "--job", folder])
        self.assertTrue(self.wait_for(lambda: any(c["argv"][:3] == ["run", "--job", folder]
                                                  for c in self.calls("agent-os"))))

    def test_text_is_one_literal_argument(self):
        text = "fix the thing on my remember list; rm -rf ~ $(whoami)"
        marker = os.path.join(self.tmp, "pwned")
        code, printed, _ = self.run_job("remember-fix", text)
        self.assertEqual(code, 0)
        hear = self.calls("agent-os")[0]["argv"]
        self.assertEqual(hear, ["hear", "--how", "typed", "--", jobs.clean_text(text)])
        self.assertEqual(len(hear), 5)
        quoted = "fix the thing on my remember list 'tonight' \"now\" `id`"
        os.environ["FAKE_FOLDER_NAME"] = "20261016-1831-quoted"
        self.run_job("remember-fix", quoted)
        hears = [c["argv"] for c in self.calls("agent-os") if c["argv"][0] == "hear"]
        self.assertEqual(hears[1], ["hear", "--how", "typed", "--", jobs.clean_text(quoted)])
        self.assertFalse(os.path.exists(marker))
        self.assertTrue(os.path.isdir(self.home))

    def test_how_voice(self):
        code, _, _ = self.run_job("remember-fix", TEXT, how="voice")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls("agent-os")[0]["argv"], ["hear", "--how", "voice", "--", TEXT])

    def test_start_job_runs_the_same_way(self):
        code, printed, _ = self.run_job("start-job", "start a job on agent-os: make the report shorter")
        self.assertEqual(code, 0)
        self.assertEqual(self.message(printed), STARTED)
        self.assertEqual(len(self.calls("systemd-run")), 1)

    def test_setsid_fallback(self):
        os.environ["BRAIN_DETACH"] = "setsid"
        code, printed, secs = self.run_job("remember-fix", TEXT)
        self.assertEqual(code, 0)
        self.assertLess(secs, 5)
        self.assertEqual(self.message(printed), STARTED)
        folder = os.path.join(self.home, FOLDER_NAME)
        self.assertTrue(self.wait_for(lambda: any(c["argv"][:1] == ["run"] for c in self.calls("agent-os"))))
        self.assertEqual(self.calls("systemd-run"), [])
        self.assertTrue(os.path.exists(os.path.join(folder, "run.log")))


class UnitName(unittest.TestCase):
    def test_unit_name(self):
        start = load_start()
        self.assertEqual(start.unit_name("/x/" + FOLDER_NAME), "agent-os-" + FOLDER_NAME)
        self.assertEqual(start.unit_name("/x/" + FOLDER_NAME + "/"), "agent-os-" + FOLDER_NAME)
        self.assertEqual(start.unit_name("../etc"), "agent-os-etc")   # only the basename is used, and it is safe
        for bad in ("Bad Name", "x;rm", "/jobs/..", "/jobs/.", "a.service", "", "20261016-1830-Fix", "/x/UPPER",
                    "/x/-dash-first", "/x/a@b"):
            with self.subTest(bad=bad):
                self.assertIsNone(start.unit_name(bad), bad)


class HearFailures(Fakes):
    def assert_nothing_started(self, code, printed):
        self.assertNotEqual(code, 0)
        self.assertEqual(self.message(printed), FAILED)
        self.assertEqual([c for c in self.calls("agent-os") if c["argv"][0] == "run"], [])
        self.assertEqual(self.calls("systemd-run"), [])

    def test_unsafe_folder_name(self):
        os.environ["FAKE_FOLDER_NAME"] = "20261016 Fix;x"
        code, printed, _ = self.run_job("remember-fix", TEXT)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "20261016 Fix;x", "ask.md")))
        self.assert_nothing_started(code, printed)

    def test_hear_exits_1(self):
        os.environ["FAKE_HEAR_MODE"] = "fail"
        self.assert_nothing_started(*self.run_job("remember-fix", TEXT)[:2])

    def test_hear_prints_no_job_line(self):
        os.environ["FAKE_HEAR_MODE"] = "noline"
        self.assert_nothing_started(*self.run_job("remember-fix", TEXT)[:2])

    def test_job_folder_without_ask_md(self):
        os.environ["FAKE_HEAR_MODE"] = "noask"
        self.assert_nothing_started(*self.run_job("remember-fix", TEXT)[:2])


class DryRun(Fakes):
    def argvs(self):
        self.wait_for(lambda: any(c["argv"][:1] == ["run"] for c in self.calls("agent-os")))
        return [c["argv"] for c in self.calls("agent-os")]

    def test_unset_adds_nothing(self):
        self.run_job("remember-fix", TEXT)
        self.assertTrue(self.argvs())
        for argv in self.argvs() + [c["argv"] for c in self.calls("systemd-run")]:
            self.assertNotIn("--dry-run", argv)

    def test_one_adds_it_to_hear_and_run(self):
        os.environ["AGENT_OS_DRY_RUN"] = "1"
        self.run_job("remember-fix", TEXT)
        argvs = self.argvs()
        self.assertEqual([a[0] for a in argvs], ["hear", "run"])
        for argv in argvs:
            self.assertIn("--dry-run", argv)

    def test_yes_is_not_one(self):
        os.environ["AGENT_OS_DRY_RUN"] = "yes"
        self.run_job("remember-fix", TEXT)
        for argv in self.argvs():
            self.assertNotIn("--dry-run", argv)


class NoOnTheCard(Fakes):
    def test_building_starts_nothing(self):
        with mock.patch.object(jobs, "project_names", return_value=known_projects()):
            jobs.build("remember-fix", TEXT)
            jobs.build("start-job", "start a job on agent-os: make the report shorter")
        self.assertEqual(self.calls(), [])
        self.assertEqual(os.listdir(self.home), [])


class Routing(unittest.TestCase):
    def run_ask(self, q, label, by="local_decider", how="typed"):
        saved = ask.decide, ask.search, ask.answer_question
        ask.decide = lambda *a, **k: {"label": label, "confidence": 0.95, "by": by}
        ask.search = lambda *a, **k: []
        ask.answer_question = lambda *a, **k: (ask.NOT_FOUND, "none")
        try:
            with mock.patch.object(jobs, "project_names", return_value=known_projects()):
                return ask.ask(q, how=how)
        finally:
            ask.decide, ask.search, ask.answer_question = saved

    def job_id(self, out):
        return (out.get("job") or {}).get("id")

    def test_remember_fix_wins_over_any_label(self):
        for label in ("question", "job:remember", "unsure", "chitchat"):
            out = self.run_ask(TEXT, label)
            self.assertEqual((out["kind"], self.job_id(out)), ("job", "remember-fix"), label)

    def test_start_job_wins_over_start_claude_label(self):
        out = self.run_ask("start a job on agent-os: make the report shorter", "job:start-claude")
        self.assertEqual(self.job_id(out), "start-job")

    def test_start_claude_unchanged(self):
        out = self.run_ask("start a claude on example-game", "job:start-claude")
        self.assertEqual(self.job_id(out), "start-claude")

    def test_remember_unchanged(self):
        out = self.run_ask("remember that the dentist is friday", "job:remember")
        self.assertEqual(self.job_id(out), "remember")

    def test_questions_stay_questions_even_if_local_decider_says_job(self):
        for q in ("what's on my remembered list?", "what should I fix on my remember list"):
            out = self.run_ask(q, "job:remember-fix")
            self.assertEqual((out["kind"], out["job"]), ("answer", None), q)

    def test_two_asks_say_again(self):
        out = self.run_ask("fix the thing on my remember list and then start a job on example: the logs",
                           "job:remember-fix")
        self.assertEqual(out["answer"], ask.SAY_AGAIN)
        self.assertIsNone(out["job"])

    def test_plain_question(self):
        out = self.run_ask("what port does rockceen run on", "question")
        self.assertEqual((out["kind"], out["job"]), ("answer", None))

    def test_voice_reaches_the_job(self):
        out = self.run_ask(TEXT, "job:remember-fix", how="voice")
        self.assertEqual(out["job"]["args"]["how"], "voice")
        self.assertEqual(self.run_ask(TEXT, "job:remember-fix")["job"]["args"]["how"], "typed")


if __name__ == "__main__":
    unittest.main()
