"""Tests for the agent-os jobs (remember-fix, start-job): rules, the job card, the argument checks, the detached
`boss prepare` call in jobs/bin/agent-os-start and the routing in ask.ask(). The real agent-os is never run: a fake
`agent-os` and a fake `systemd-run` (a tripwire: nothing is started detached any more) sit first on PATH in a temp
folder and record their arguments.
Run: CRABBOX_LOCAL=1 python3 -I jobs/test_agent_jobs.py -v"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
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
BOSS = os.path.join(HERE, "bin", "agent-os-boss")
FOLDER_NAME = "20261016-1830-fix-the-thing"
TEXT = "fix the thing on my remember list tonight"
FAILED = "I couldn't start that job."
PREPARED = "Prepared the fix from your remember list. It waits for your go."
WHICH_ONE = ("More than one thing on your remember list fits. Pick which one in the office, then it waits for your "
             "go.")

FAKE_AGENT_OS = '''#!%(py)s
import json, os, sys, time
argv = sys.argv[1:]
with open(os.environ["FAKE_CALLS"], "a") as f:
    f.write(json.dumps({"tool": "agent-os", "argv": argv}) + "\\n")
if argv[:2] == ["boss", "prepare"] and "--remember" in argv:
    mode = os.environ.get("FAKE_REMEMBER_MODE", "ok")
    if mode == "slow":
        time.sleep(30)
    if mode == "fail":
        print("agent-os: no repo for that item; the desk asks", file=sys.stderr)
        sys.exit(2)
    if mode != "noline":
        print("job: /fake/jobs/%(name)s")
    if mode == "which":
        print("1. fix the bar clock")
        print("2. fix the bar wifi icon")
        print("WAITING: which one? 2 items on the remember list fit")
        sys.exit(3)
    if mode == "odd":
        sys.exit(4)
    print("worker job: /fake/jobs/%(name)s-worker")
    sys.exit(0)
if argv[:2] == ["boss", "prepare"]:
    boss_mode = os.environ.get("FAKE_BOSS_MODE", "ok")
    if boss_mode == "fail":
        print("agent-os: no repo called " + argv[argv.index("--repo") + 1], file=sys.stderr)
        sys.exit(5)
    if boss_mode == "slow":
        time.sleep(30)
    print("boss job: /fake/boss")
    sys.exit(0)
sys.exit(9)
'''

# A tripwire: nothing may be started detached any more. It only records that it was called.
FAKE_SYSTEMD_RUN = '''#!%(py)s
import json, os, sys
with open(os.environ["FAKE_CALLS"], "a") as f:
    f.write(json.dumps({"tool": "systemd-run", "argv": sys.argv[1:]}) + "\\n")
sys.exit(0)
'''


def load_start(path=START, name="agent_os_start"):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
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
        for k in ("AGENT_OS_DRY_RUN", "BRAIN_DETACH", "FAKE_REMEMBER_MODE", "FAKE_BOSS_MODE"):
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


TEAM_CARDS = [
    ("start a claude on example: tidy the logs", "example", "tidy the logs"),
    ("Hey Claude, start a claude on example-rpg to fix the map loading", "example-rpg", "fix the map loading"),
    ("start a claude on example-game and tidy the saves, please", "example-game", "tidy the saves"),
    ("start a claude on example: fix the example-board links", "example", "fix the example-board links"),
    ("start a claude on example, tidy the logs", "example", "tidy the logs"),
    ("start a claude on example - tidy the logs", "example", "tidy the logs"),
    ("start a claude on example \u2014 tidy the logs", "example", "tidy the logs"),
    ("start a claude on example \u2013 tidy the logs", "example", "tidy the logs"),
    ("start a claude on example-game, fix the saves, please", "example-game", "fix the saves"),
    # "to check in" is a task on purpose: "to" is how people say it, and the card shows the task before Yes.
    ("start a claude on example to check in", "example", "check in"),
    # one word is enough after a colon (and after a joining word), not after a comma or dash
    ("start a claude on example: cleanup", "example", "cleanup"),
    ("start a claude on example, to check in", "example", "check in"),
    ("start a claude on example-rpg, fix the login page", "example-rpg", "fix the login page"),
    ("start a claude for example-rpg - fix logins too", "example-rpg", "fix logins"),
]
# Spoken with a pause the engine writes a full stop between the words (<user>'s real try, 2026-10-19).
TEAM_CARDS += [
    ("Start a claude on Example. Tidy the logs.", "example", "Tidy the logs"),
    ("Start an agent on Example. Tidy the logs.", "example", "Tidy the logs"),
    ("start a claude on example-rpg! fix the login page", "example-rpg", "fix the login page"),
    ("Start a claude on Example. Look at the example-board links.", "example", "Look at the example-board links"),
    ("Start an agent on example-rpg. Take care of the map loading.", "example-rpg", "Take care of the map loading"),
]
# The speech engine often hears "Claude" as one of these (<user>'s real tries, 2026-10-19); "agent" is what the decider took.
MISHEARD_CLAUDE = ["Start a clot on Example. Tidy the logs.", "start a cloud on example: tidy the logs",
                   "Start an agent on Example. Tidy the logs.", "get a clod on example-rpg, fix the login page"]
SENTENCE_NO_TASK = ["Start a claude on example. What time is it?", "start a claude on example. Open spotify.",
                    "start a claude on example. Remember the dentist.", "start a claude on example. That's all.",
                    "start a claude on example. Sounds good.", "start a claude on example. No rush.",
                    "start a claude on example. See you later.", "start a claude on example. The usual.",
"Start a claude on Example. I need the logs.", "start a claude on example. Thanks.",
                    "start a claude on example. Okay.", "Start a claude on Example. Quick one.",
                    "start a claude on example-rpg. example-rpg."]
TEAM_PHRASES = [t for t, _, _ in TEAM_CARDS if " agent " not in t]
NO_TASK = ["start a claude on example-game", "open the example-rpg PM", "start working on example",
           "get a claude going for example-board", "start a claude on example like now", "start a claude on example, thanks",
           "start a claude on example, then", "start a claude on example so I can watch it",
           "start a claude on example that's all", "start a claude on example and example-rpg",
           "start a claude on example, example-rpg",
           "start a claude on example: example-rpg", "start a claude on example: 's all", "start a claude on example's logs",
           # after a comma or dash: chat, filler and one word are not a task (round 3)
           "start a claude on example, ok", "start a claude on example, right", "start a claude on example, cool",
           "start a claude on example, you know", "start a claude on example \u2014 okay",
           "start a claude for example-rpg - quick", "start a claude on example, I'll tell it what to do",
           "start a claude on example, so I can watch", "start a claude on example, example-rpg too",
           "start a claude on example, yeah sure", "start a claude on example - we will see", "start a claude on example, tidy",
           "start a claude on example: so I can watch", "start a claude on example: okay"]


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
                     "how do I fix the thing on my remember list",
                     # review F1, F3: questions about the list and runs that name no project
                     "do you have anything on my remember list", "do I need to sort out my taxes from my remember list",
                     "does anything on my remember list need fixing", "start a run on tuesday",
                     "start a build for the weekend", "start a run for me"):
            self.assertNotIn(jobs.match_rule(text), jobs.AGENT_JOBS, text)

    def test_agent_jobs_still_fit(self):
        self.assertEqual(jobs.match_rule("can you fix the thing on my remember list"), "remember-fix")
        # review F2: start-job's task is free text, so two sentences in it are still one job
        self.assertEqual(jobs.match_rule("start a job on example: fix the bug. Then add tests"), "start-job")

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
        self.assertIn("wait for your go", out["answer"])   # remember-fix keeps its go-wait lines

    def test_how_voice(self):
        self.assertEqual(jobs.build("remember-fix", TEXT, how="voice")["job"]["args"]["how"], "voice")
        self.assertEqual(jobs.build("remember-fix", TEXT, how="bogus")["job"]["args"]["how"], "typed")

    def test_start_job_card(self):
        out = jobs.build("start-job", "start a job on agent-os: make the report shorter")
        self.assertNotIn("saved for later", out["answer"])
        self.assertIn("your go", out["answer"])
        job = out["job"]
        self.assertEqual(job["args"]["text"], "make the report shorter")   # the task, as start-claude hands it
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

    # ---- start-claude with a task: a team job ----

    def test_team_phrases_are_start_claude(self):
        for text in TEAM_PHRASES:
            self.assertEqual(jobs.match_rule(text), "start-claude", text)

    def test_misheard_claude_still_starts_a_team(self):
        for text in MISHEARD_CLAUDE:
            with self.subTest(text=text):
                self.assertEqual(jobs.match_rule(text), "start-claude", text)
                job = jobs.build("start-claude", text, how="voice")["job"]
                self.assertTrue(job["label"].startswith("Start a team on"), job["label"])
        for text in ("open the cloud app", "start a clot of paint"):   # not ours
            self.assertNotEqual(jobs.match_rule(text), "start-claude", text)
        out = jobs.build("start-claude", "start a cloud on aws", how="voice")     # no such project: asks, starts nothing
        self.assertIsNone(out.get("job"))
        self.assertIn("Which project", out["answer"])

    def test_a_spoken_pause_between_project_and_task(self):
        """"Start an agent on Example. Tidy the logs." is a task after a pause; chat after a pause is not."""
        for text in SENTENCE_NO_TASK:
            with self.subTest(text=text):
                out = jobs.build("start-claude", text, how="voice")
                self.assertIsNone(out["job"], text)                       # no team card, and no PM chat either
                self.assertIn("What should the team do on", out["answer"])

    def test_team_card(self):
        for text, project, task in TEAM_CARDS:
            with self.subTest(text=text):
                out = jobs.build("start-claude", text, how="voice")
                job = out["job"]
                self.assertEqual(job["label"], "Start a team on " + jobs.pretty(project))
                self.assertTrue(job["needs_confirm"])
                self.assertTrue(job["speak"])
                self.assertEqual(job["args"], {"project": project, "name": jobs.pretty(project), "text": task,
                                               "how": "voice"})
                self.assertIn("agent-os-boss --repo " + project + " --how voice -- " + task, job["command"])
                self.assertIn("Nothing starts until you say go", out["answer"])

    def test_no_task_asks_for_the_task_and_never_opens_a_project_pm(self):
        for text in NO_TASK:
            with self.subTest(text=text):
                out = jobs.build("start-claude", text)
                self.assertIsNone(out["job"], text)
                self.assertIn("What should the team do on", out["answer"], text)
                self.assertIn("start a claude on", out["answer"], text)

    def test_the_question_names_the_project(self):
        out = jobs.build("start-claude", "start a claude on example-game")
        self.assertIn("Example Game", out["answer"])

    def test_two_projects_are_never_a_team_job(self):
        # find_project picks the desk here (as it always did): the old whole-desk card, and no team card
        out = jobs.build("start-claude", "start a claude on example and the desk")
        self.assertNotIn("text", out["job"]["args"])
        self.assertFalse(out["job"]["label"].startswith("Start a team"))

    def test_team_card_shows_the_task(self):
        out = jobs.build("start-claude", "start a claude on example to check in")
        self.assertIn("check in", out["answer"])

    def test_whole_desk_stays_the_desk_pm(self):
        for text in ("start a claude on the desk", "start a claude on the whole desk: tidy the notes"):
            job = jobs.build("start-claude", text)["job"]
            self.assertEqual((job["label"], job["args"]["project"]), ("Start the whole-desk PM", "desk"), text)
            self.assertNotIn("text", job["args"])

    def test_desk_with_a_task_says_the_task_is_not_used(self):
        for text in ("start a claude on the desk: tidy the board", "start a claude on the whole desk to tidy the board",
                     "start a claude on the desk, tidy the board"):
            out = jobs.build("start-claude", text)
            self.assertEqual(out["job"]["label"], "Start the whole-desk PM", text)
            self.assertNotIn("text", out["job"]["args"])
            self.assertIn("The whole desk has no team job", out["answer"], text)
            self.assertIn("your task was not used", out["answer"], text)
        plain = jobs.build("start-claude", "start a claude on the desk")["answer"]
        self.assertNotIn("not used", plain)

    def test_dash_task_is_an_answer(self):
        out = jobs.build("start-claude", "start a claude on example: -rf everything")
        self.assertEqual((out["kind"], out["job"]), ("answer", None))

    def test_start_job_still_wins(self):
        for text in ("start a job on example: tidy the logs", "kick off a job for example: tidy the logs"):
            self.assertEqual(jobs.match_rule(text), "start-job", text)


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

    def test_team_job_bad_input_never_reaches_agent_os(self):
        bad = ({"project": "example", "text": "two\nlines"}, {"project": "example", "text": "   "},
               {"project": "example", "text": "x" * 501}, {"project": "example", "text": "-rf everything"},
               {"project": "nonesuch", "text": "do it"}, {"project": "desk", "text": "do it"},
               {"project": "", "text": "do it"})
        for args in bad:
            with self.subTest(args=args):
                self.refused("start-claude", dict(args, how="typed"))

    def test_team_check_normalises_how(self):
        got = jobs._check("start-claude", {"project": "example", "text": "a  b", "how": "shout"})
        self.assertEqual(got, {"project": "example", "name": "Example", "text": "a b", "how": "typed"})

    def test_check_normalises_how(self):
        got = jobs._check("remember-fix", {"text": "a  b", "how": "shout"})
        self.assertEqual(got, {"text": "a b", "how": "typed"})


class Starting(Fakes):
    """Yes on the remember-fix card: exactly `agent-os boss prepare --remember --how <how> -- "<words>"`, nothing else.
    Yes on the start-job card: exactly `agent-os boss prepare --repo <project> --how <how> -- "<task>"`."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(jobs, "project_names", return_value=known_projects())
        p.start()
        self.addCleanup(p.stop)

    def test_remember_fix_prepares_a_team_job(self):
        code, printed, _ = self.run_job("remember-fix", TEXT, how="voice")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(printed.strip().splitlines()[-1]), {"message": PREPARED, "speak": True})
        self.assertEqual(self.calls(), [{"tool": "agent-os",
                                         "argv": ["boss", "prepare", "--remember", "--how", "voice", "--", TEXT]}])

    def test_which_one_waits_for_the_pick_in_the_office(self):
        os.environ["FAKE_REMEMBER_MODE"] = "which"
        code, printed, _ = self.run_job("remember-fix", TEXT)
        self.assertEqual(code, 0)   # not a failure: the job is there and waits for <user>'s pick
        self.assertEqual(self.message(printed), WHICH_ONE)
        self.assertEqual(len(self.calls()), 1)

    def test_text_is_one_literal_argument(self):
        text = "fix the thing on my remember list; rm -rf ~ $(touch " + os.path.join(self.tmp, "pwned") + ")"
        code, _, _ = self.run_job("remember-fix", text)
        self.assertEqual(code, 0)
        argv = self.calls("agent-os")[0]["argv"]
        self.assertEqual(argv, ["boss", "prepare", "--remember", "--how", "typed", "--", jobs.clean_text(text)])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "pwned")))

    def test_start_job_prepares_a_team_job_on_the_project(self):
        code, printed, _ = self.run_job("start-job", "start a job on agent-os: make the report shorter", how="voice")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), [{"tool": "agent-os", "argv": ["boss", "prepare", "--repo", "agent-os", "--how",
                                                                     "voice", "--", "make the report shorter"]}])
        self.assertEqual(self.message(printed), "Prepared the Agent Os team job. It waits for your go.")
        self.assertNotIn("saved for later", printed)

    def test_never_hear_run_start_or_detach(self):
        os.environ["AGENT_OS_DRY_RUN"] = "1"   # the old test switch does nothing now
        self.run_job("remember-fix", TEXT)
        self.run_job("start-job", "start a job on example: tidy the logs")
        self.assertEqual(len(self.calls("agent-os")), 2)
        for call in self.calls("agent-os"):
            self.assertEqual(call["argv"][:2], ["boss", "prepare"])
            self.assertNotIn("--dry-run", call["argv"])
        self.assertEqual(self.calls("systemd-run"), [])
        self.assertEqual(os.listdir(self.home), [])

    def test_answers_on_the_cards_match(self):
        self.assertEqual(jobs.load()["remember-fix"]["message"], PREPARED)
        self.assertNotIn("saved for later", json.dumps(jobs.load()["start-job"]))


class TeamJob(Fakes):
    """Yes on the team card: exactly `agent-os boss prepare --repo <project> -- "<words>"`, nothing else."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(jobs, "project_names", return_value=known_projects())
        p.start()
        self.addCleanup(p.stop)

    def run_boss(self, *argv):
        out = subprocess.run([sys.executable, "-I", BOSS, *argv], capture_output=True, text=True, timeout=60,
                             stdin=subprocess.DEVNULL)
        return out.returncode, out.stdout

    def test_yes_runs_exactly_boss_prepare(self):
        code, printed, _ = self.run_job("start-claude", "start a claude on example: tidy the logs", how="voice")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), [{"tool": "agent-os",
                                         "argv": ["boss", "prepare", "--repo", "example", "--how", "voice", "--", "tidy the logs"]}])
        self.assertEqual(json.loads(printed.strip().splitlines()[-1]),
                         {"message": "Prepared the Example team job. It waits for your go.", "speak": True})

    def test_never_starts_anything(self):
        self.run_job("start-claude", "start a claude on example: tidy the logs")
        for call in self.calls():
            self.assertNotIn(call["argv"][0], ("hear", "run", "do", "hire"))
            self.assertNotEqual(call["argv"][:2], ["boss", "start"])
        self.assertEqual(self.calls("systemd-run"), [])

    def test_no_card_starts_nothing(self):
        # No is the island not calling `brain job run` at all; building the card must not call agent-os.
        jobs.build("start-claude", "start a claude on example: tidy the logs")
        self.assertEqual(self.calls(), [])

    def test_text_is_one_literal_argument(self):
        marker = os.path.join(self.tmp, "pwned")
        code, _, _ = self.run_job("start-claude", "start a claude on example: tidy $(touch " + marker + ") 'logs'; rm -rf ~")
        self.assertEqual(code, 0)
        argv = self.calls("agent-os")[0]["argv"]
        self.assertEqual(argv[:7], ["boss", "prepare", "--repo", "example", "--how", "typed", "--"])
        self.assertEqual(len(argv), 8)
        self.assertFalse(os.path.exists(marker))

    def test_failing_agent_os_is_spoken(self):
        os.environ["FAKE_BOSS_MODE"] = "fail"
        code, printed, _ = self.run_job("start-claude", "start a claude on example: tidy the logs")
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(printed.strip().splitlines()[-1]),
                         {"message": "I couldn't prepare that job.", "speak": True})

    def test_slow_agent_os_gives_up(self):
        os.environ["FAKE_BOSS_MODE"] = "slow"
        boss = load_start(BOSS, "agent_os_boss")
        out = io.StringIO()
        with mock.patch.object(boss, "PREPARE_SECONDS", 1), contextlib.redirect_stdout(out):
            code = boss.main(["--repo", "example", "--how", "voice", "--", "tidy the logs"])
        self.assertEqual((code, self.message(out.getvalue())), (1, "I couldn't prepare that job."))

    def test_script_refuses_bad_input_before_agent_os(self):
        for argv in ([], ["--repo", "example"], ["--repo", "example", "--how", "voice", "--", ""], ["--repo", "example", "--how", "voice", "--", "   "],
                     ["--repo", "example", "--how", "voice", "--", "two\nlines"], ["--repo", "example", "--how", "voice", "--", "x" * 501],
                     ["--repo", "example", "--how", "voice", "--", "-rf everything"], ["--repo", "example", "--how", "voice", "--", " -x"],
                     ["--repo", "nonesuch", "--how", "voice", "--", "do it"], ["--repo", "desk", "--how", "voice", "--", "do it"],
                     ["--repo", "../etc", "--how", "voice", "--", "do it"], ["--repo", "example", "--how", "voice", "--", "a", "b"],
                     ["--repo", "example", "tidy the logs"],
                     ["--repo", "example", "--", "no how given"], ["--repo", "example", "--how", "shouted", "--", "x"],
                     ["--repo", "example", "--how", "voice", "tidy the logs"]):
            with self.subTest(argv=argv):
                code, printed = self.run_boss(*argv)
                self.assertNotEqual(code, 0)
                self.assertEqual(self.message(printed), "I couldn't prepare that job.")
                self.assertEqual(self.calls(), [])

    def test_script_accepts_500_characters(self):
        code, printed = self.run_boss("--repo", "example", "--how", "voice", "--", "x" * 500)
        self.assertEqual(code, 0, printed)
        self.assertEqual(self.calls("agent-os")[0]["argv"][-1], "x" * 500)

    def test_pm_chat_card_still_runs_pm(self):
        with mock.patch.object(jobs.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            with contextlib.redirect_stdout(io.StringIO()):
                jobs.run("start-claude", jobs.build("start-claude", "start a claude on the desk")["job"])
        argv = run.call_args[0][0]
        self.assertTrue(argv[0].endswith("project-manager/bin/pm"), argv)
        self.assertEqual(argv[1:], ["open", "--desk", "--launch"])
        self.assertEqual(self.calls(), [])


class JobArgument(Fakes):
    def test_bad_arguments_are_refused_before_agent_os(self):
        start = load_start()
        for argv in (["--job", "other", "--how", "typed", "--", TEXT], ["--how", "shout", "--", TEXT],
                     ["--how", "typed", TEXT], ["--how", "typed", "--", ""], ["--how", "typed", "--", "a\nb"],
                     ["--how", "typed", "--", "-x"], ["--how", "typed", "--", "x" * 501],
                     ["--job", "start-job", "--how", "typed", "--", "do it"],
                     ["--job", "start-job", "--repo", "desk", "--how", "typed", "--", "do it"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = start.main(argv)
                self.assertNotEqual(code, 0)
                self.assertIn(self.message(out.getvalue()), (FAILED, "I couldn't prepare that job."))
        self.assertEqual(self.calls(), [])


class RememberFailures(Fakes):
    def failed(self, mode):
        os.environ["FAKE_REMEMBER_MODE"] = mode
        code, printed, _ = self.run_job("remember-fix", TEXT)
        self.assertNotEqual(code, 0, mode)
        self.assertEqual(self.message(printed), FAILED, mode)
        self.assertEqual(self.calls("systemd-run"), [])

    def test_agent_os_refuses(self):
        self.failed("fail")

    def test_no_job_line(self):
        self.failed("noline")

    def test_an_exit_it_does_not_know(self):
        self.failed("odd")

    def test_slow_agent_os_gives_up(self):
        os.environ["FAKE_REMEMBER_MODE"] = "slow"
        start = load_start()
        out = io.StringIO()
        with mock.patch.object(start, "PREPARE_SECONDS", 1), contextlib.redirect_stdout(out):
            code = start.main(["--how", "voice", "--", TEXT])
        self.assertEqual((code, self.message(out.getvalue())), (1, FAILED))


class NoOldCalls(unittest.TestCase):
    def test_no_hear_or_run_left_in_the_code(self):
        """No `agent-os hear` or `agent-os run` anywhere in the repo's code (tests and history notes aside)."""
        import re
        bad = re.compile(r"agent-os (hear|run)\b|\[exe, \"(hear|run)\"|\"(hear|run)\", \"--")
        found = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "history")]
            for f in files:
                path = os.path.join(root, f)
                if f.startswith("test_") or not (f.endswith((".py", ".json", ".sh", ".qml")) or
                                                 os.path.dirname(path).endswith(os.path.join("jobs", "bin"))):
                    continue
                with open(path, errors="replace") as fh:
                    if bad.search(fh.read()):
                        found.append(os.path.relpath(path, REPO))
        self.assertEqual(found, [])


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

    def test_start_claude_with_a_task_is_a_team_card(self):
        out = self.run_ask("start a claude on example: tidy the logs", "job:start-claude")
        self.assertEqual(self.job_id(out), "start-claude")
        self.assertEqual(out["job"]["label"], "Start a team on Example")
        self.assertEqual(out["job"]["args"]["text"], "tidy the logs")

    def test_start_claude_with_no_task_asks_for_one(self):
        out = self.run_ask("start a claude on example-game", "job:start-claude")
        self.assertIsNone(self.job_id(out))                       # no PM chat is opened any more
        self.assertIn("What should the team do on Example Game", out["answer"])
        desk = self.run_ask("start a claude on the desk", "job:start-claude")
        self.assertEqual(self.job_id(desk), "start-claude")       # the whole-desk PM still opens

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
