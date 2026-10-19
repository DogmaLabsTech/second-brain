"""Tests for the desktop jobs (no desktop needed: apps, themes and files are faked):
python3 jobs/test_desktop_jobs.py"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop  # noqa: E402
import jobs  # noqa: E402

CATALOG = {
    "vesktop": {"name": "Discord", "words": ["discord", "", "vesktop", "vesktop"], "wmclass": "vesktop",
                "exe": "vesktop", "web": False},
    "Discord": {"name": "Discord", "words": ["discord", "", "omarchy-launch-webapp", "discord"], "wmclass": "",
                "exe": "omarchy-launch-webapp", "web": True},
    "spotify-launcher": {"name": "Spotify", "words": ["spotify", "", "spotify-launcher", "spotify-launcher", "music"],
                         "wmclass": "", "exe": "spotify-launcher", "web": False},
    "obsidian": {"name": "Obsidian", "words": ["obsidian", "", "obsidian", "obsidian"], "wmclass": "obsidian",
                 "exe": "obsidian", "web": False},
}


class Actions(unittest.TestCase):
    def test_actions_from_words(self):
        cases = {
            "take a screenshot": "screenshot", "screenshot part of the screen": "screenshot-area",
            "start recording the screen": "record-start", "stop recording": "record-stop",
            "turn on the night light": "nightlight-on", "night light off": "nightlight-off",
            "lock the screen": "lock", "shut down the computer": "shutdown", "restart the computer": "reboot",
            "log me out": "logout", "keep the screen awake": "stay-awake", "turn on do not disturb": "dnd",
            "mute my mic": "mic-mute", "turn the computer down": "volume-down", "show my keyboard shortcuts":
            "keybindings", "next wallpaper": "bg-next", "turn bluetooth off": "bluetooth-off",
        }
        for text, want in cases.items():
            self.assertEqual(desktop.find_action(text)[0], want, text)

    def test_reminder_parsing(self):
        self.assertEqual(desktop.parse_reminder("remind me in 10 minutes to check the oven"), (10, "Check the oven"))
        self.assertEqual(desktop.parse_reminder("remind me in an hour to call the vet")[0], 60)
        self.assertEqual(desktop.parse_reminder("set a timer for 5 minutes"), (5, "Reminder"))
        self.assertEqual(desktop.parse_reminder("remind me about the oven"), (None, None))

    def test_clock_reminders(self):
        import datetime as dt
        now = dt.datetime(2026, 10, 18, 12, 47).timestamp()     # a Sunday

        def at(text):
            when, msg = desktop.parse_clock(text, now)
            return (dt.datetime.fromtimestamp(when).strftime("%a %H:%M"), msg) if when else (None, msg)
        self.assertEqual(at("remind me at 2pm to go outside with Ollie"), ("Sun 14:00", "Go outside with Ollie"))
        self.assertEqual(at("remind me at 2 to go outside"), ("Sun 14:00", "Go outside"))
        self.assertEqual(at("remind me tomorrow at 8am to call the vet"), ("Mon 08:00", "Call the vet"))
        self.assertEqual(at("remind me at 9:30 to stretch"), ("Sun 21:30", "Stretch"))
        self.assertEqual(at("remind me at 11 am to stretch"), ("Mon 11:00", "Stretch"))     # gone by today
        self.assertEqual(at("remind me to take the bins out at 7 tonight"), ("Sun 19:00", "Take the bins out"))
        self.assertEqual(at("remind me at 7 on friday to pay rent")[0], "Fri 07:00")
        self.assertEqual(at("remind me at 3 on friday to pay rent")[0], "Fri 15:00")
        self.assertEqual(at("remind me at 10 in the morning to email")[0], "Mon 10:00")
        self.assertEqual(at("remind me at noon to eat")[0], "Mon 12:00")
        self.assertEqual(at("remind me at 14:30 to leave")[0], "Sun 14:30")
        self.assertEqual(at("remind me in 10 minutes to check the oven"), (None, None))
        self.assertEqual(at("remind me at 25 to x"), (None, None))
        action, value = desktop.find_action("remind me at 2pm to go outside with Ollie")
        self.assertEqual((action, value["message"]), ("reminder", "Go outside with Ollie"))

    def test_clock_reminder_job_card(self):
        """The whole way, as the island builds it: the card says when, the command sets the alarm."""
        import time
        j = jobs.build("desktop", "remind me tomorrow at 8am to test the alarm")["job"]
        self.assertEqual(j["label"], "Remind you tomorrow at 8 am: Test the alarm")
        self.assertIn("reminder", j["command"])
        soon = int(time.time()) + 7200
        self.assertTrue(desktop.action_label("reminder", {"at": soon, "message": "x"}, done=True).startswith(
            "I'll remind you at "))
        self.assertEqual(jobs.build("desktop", "remind me in 10 minutes to stretch")["job"]["label"],
                         "Remind you in 10 minutes: Stretch")

    def test_workspace_words(self):
        self.assertEqual(desktop.find_action("go to workspace three"), ("workspace", 3))
        self.assertEqual(desktop.find_action("switch to workspace 7"), ("workspace", 7))

    def test_named_theme_beats_next_theme(self):
        names = ["tokyo-night", "catppuccin", "catppuccin-latte", "vault"]
        with mock.patch.object(desktop, "themes", return_value=names):
            self.assertEqual(desktop.find_action("switch the theme to tokyo night"), ("theme-set", "tokyo-night"))
            self.assertEqual(desktop.find_action("change theme to catppuccin latte"), ("theme-set", "catppuccin-latte"))
            self.assertEqual(desktop.find_action("next theme"), ("theme-next", None))
            with self.assertRaises(ValueError):
                desktop.check_action("theme-set", "not-a-theme")

    def test_checks_refuse_bad_values(self):
        for action, value in [("rm-rf", None), ("reminder", {"minutes": 0}), ("reminder", {"minutes": 5000}),
                              ("workspace", 11), ("workspace", "3; reboot")]:
            with self.assertRaises(ValueError, msg=(action, value)):
                desktop.check_action(action, value)
        self.assertEqual(desktop.check_action("reminder", {"minutes": "5", "message": "  tea\n now "}),
                         ("reminder", {"minutes": 5, "message": "tea now"}))
        import time
        soon = int(time.time()) + 3600
        self.assertEqual(desktop.check_action("reminder", {"at": soon, "message": "Tea"}),
                         ("reminder", {"at": soon, "message": "Tea"}))
        for bad in (int(time.time()) - 60, int(time.time()) + 8 * 24 * 3600, "2pm"):
            with self.assertRaises(ValueError, msg=bad):
                desktop.check_action("reminder", {"at": bad, "message": "Tea"})

    def test_only_power_actions_ask_first(self):
        asks = {a for a, v in desktop.ACTIONS.items() if v[3]}
        self.assertEqual(asks, {"logout", "reboot", "shutdown"})

    def test_commands_fill_values(self):
        self.assertEqual(desktop.action_command("workspace", 3),
                         ["hyprctl", "dispatch", 'hl.dsp.focus({ workspace = "3" })'])
        self.assertEqual(desktop.action_command("reminder", {"at": 1792432800, "message": "Tea"}),
                         ["@alarm", "set", "1792432800", "Tea"])
        import time
        cmd = desktop.action_command("reminder", {"minutes": 5, "message": "Tea"})
        self.assertEqual((cmd[:2], cmd[3]), (["@alarm", "set"], "Tea"))
        self.assertAlmostEqual(int(cmd[2]), time.time() + 300, delta=5)


class Apps(unittest.TestCase):
    def test_find_app(self):
        with mock.patch.object(desktop, "open_classes", return_value=set()):
            self.assertEqual(desktop.find_app("open spotify", CATALOG)[0], "spotify-launcher")
            self.assertEqual(desktop.find_app("launch obsidian app", CATALOG)[0], "obsidian")
            # The real app beats its web copy.
            self.assertEqual(desktop.find_app("open discord", CATALOG)[0], "vesktop")
        self.assertEqual(desktop.find_app("open a terminal", CATALOG)[0], "@terminal")
        self.assertIsNone(desktop.find_app("open steam", CATALOG)[0])

    def test_spoken_requests(self):
        cat = dict(CATALOG, **{
            "google-chrome": {"name": "Google Chrome", "words": ["google chrome", "", "google-chrome-stable", "google-chrome"],
                              "wmclass": "", "exe": "google-chrome-stable", "web": False},
            "com.microsoft.VSCode": {"name": "Visual Studio Code", "words": ["visual studio code", "", "code", "vscode"],
                                     "wmclass": "", "exe": "code", "web": False}})
        with mock.patch.object(desktop, "open_classes", return_value=set()):
            self.assertEqual(desktop.find_app("Can you open up Chrome?", cat)[0], "google-chrome")
            self.assertEqual(desktop.find_app("Can you open up VS Code on my second monitor?", cat)[0],
                             "com.microsoft.VSCode")
            self.assertEqual(desktop.find_app("could you open discord for me", cat)[0], "vesktop")

    def test_open_window_wins_a_tie(self):
        cat = dict(CATALOG)
        cat["vesktop"] = dict(cat["vesktop"], web=True)
        with mock.patch.object(desktop, "open_classes", return_value={"vesktop"}):
            self.assertEqual(desktop.find_app("open discord", cat)[0], "vesktop")

    def test_unknown_app_is_refused(self):
        with self.assertRaises(ValueError):
            desktop.app_command("not-installed; reboot", CATALOG)
        cmd = desktop.app_command("vesktop", CATALOG)
        self.assertEqual(cmd[0], "omarchy-launch-or-focus")
        self.assertEqual(cmd[2], "uwsm-app -- vesktop.desktop")


class Files(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.home, "Downloads", "maps"))
        os.makedirs(os.path.join(self.home, ".ssh"))
        for p in ("Downloads/maps/kingdom-five-regions.png", "Downloads/kingdom-regional-map.docx", ".ssh/id_rsa",
                  "Downloads/run.sh", "Downloads/notes.txt"):
            open(os.path.join(self.home, p), "w").close()
        os.chmod(os.path.join(self.home, "Downloads/notes.txt"), 0o644)
        self.patch = mock.patch.multiple(desktop, HOME=self.home, FILE_ROOTS=[self.home])
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_allowed_paths(self):
        h = self.home
        self.assertTrue(desktop.allowed_path(os.path.join(h, "Downloads/notes.txt")))
        self.assertTrue(desktop.allowed_path(os.path.join(h, "Downloads")))
        self.assertIsNone(desktop.allowed_path(os.path.join(h, ".ssh/id_rsa")))      # hidden folder
        self.assertIsNone(desktop.allowed_path(os.path.join(h, "Downloads/run.sh")))  # a program
        self.assertIsNone(desktop.allowed_path("/etc/passwd"))                         # outside home
        self.assertIsNone(desktop.allowed_path(os.path.join(h, "nope.txt")))          # missing

    @unittest.skipUnless(os.path.exists("/usr/bin/fd"), "needs fd")
    def test_picture_word_picks_the_picture(self):
        self.assertTrue(desktop.find_file("open the kingdom map picture")[0].endswith("kingdom-five-regions.png"))
        self.assertTrue(desktop.find_file("open the kingdom map")[0].endswith("kingdom-regional-map.docx"))


class Routing(unittest.TestCase):
    def test_rules_pick_the_right_job(self):
        cases = {"next theme": "desktop", "take a screenshot": "desktop", "mute the tv": "tv",
                 "next song": "music", "stop recording": "desktop", "open spotify": "open-app",
                 "open my downloads folder": "open-file", "open my notes on the bar": "open-note",
                 "start a claude on example-game": "start-claude", "remember the wifi box is in the closet": "remember"}
        for text, want in cases.items():
            self.assertEqual(jobs.match_rule(text), want, text)

    def test_unknown_app_opens_no_loose_file_or_note(self):
        with mock.patch.object(desktop, "find_app", return_value=(None, None, 0)), \
                mock.patch.object(desktop, "find_file", return_value=(None, None, 0)) as ff:
            out = jobs.build("open-app", "open steam", search=lambda topic: [{"path": "x.md", "title": "x"}])
        self.assertIsNone(out["job"])
        self.assertEqual(ff.call_args.kwargs["min_score"], 1.0)

    def test_how_questions_are_not_jobs(self):
        self.assertTrue(jobs.is_how_question("how do i turn on the night light"))
        self.assertFalse(jobs.is_how_question("turn on the night light"))
        self.assertFalse(jobs.is_how_question("what are my reminders"))

    def test_power_job_asks_first(self):
        built = jobs.build("desktop", "shut down the computer")
        self.assertTrue(built["job"]["needs_confirm"])
        self.assertFalse(jobs.build("desktop", "lock the screen")["job"]["needs_confirm"])

    def test_run_refuses_a_changed_job(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = jobs.run("desktop", {"args": {"action": "format-disk"}})
        self.assertEqual(code, 2)
        self.assertIn("didn't do it", buf.getvalue())




class TeamScreen(unittest.TestCase):
    """"Show me the team" opens agent-os's Team screen app (<user>, 2026-10-19: the island answered it as a question)."""

    def test_words_pick_the_team_screen(self):
        for text in ("Show me the team.", "hey claude, show me the team", "open the team screen", "show me my team",
                     "can you bring up the team screen please"):
            self.assertEqual(jobs.match_rule(text), "team-screen", text)
        for text in ("show my keyboard shortcuts", "who is on the team for example-game", "open spotify",
                     "show me the team's report from last night"):
            self.assertNotEqual(jobs.match_rule(text), "team-screen", text)

    def test_the_job_opens_the_team_screen_app(self):
        job = jobs.load()["team-screen"]
        self.assertEqual(job["command"][1:], ["app", "agent-os-team"])
        self.assertFalse(job["needs_confirm"])
        built = jobs.build("team-screen", "show me the team")
        self.assertEqual(built["kind"], "job")
        self.assertEqual(built["answer"], "Opening the team screen.")

    def test_its_rule_beats_a_question_label(self):
        self.assertIn("team-screen", jobs.DESKTOP_JOBS)

    def test_an_open_terminal_is_not_the_team_screen(self):
        """It runs in kitty: the pattern matched the Desk's kitty window and focused it (<user>, 2026-10-19)."""
        import re
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "applications"))
            entries = {"agent-os-team": "Name=Team screen\nExec=kitty --class agent-os-team -e agent-os screen\n"
                                        "StartupWMClass=agent-os-team\n",
                       "kitty": "Name=kitty\nExec=kitty\n"}
            for app_id, body in entries.items():
                with open(os.path.join(tmp, "applications", app_id + ".desktop"), "w") as f:
                    f.write("[Desktop Entry]\nType=Application\n" + body)
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": tmp, "XDG_DATA_DIRS": ""}):
                team = desktop.app_command("agent-os-team")[1]
                term = desktop.app_command("kitty")[1]
        for cls, title in (("kitty", "Desk (talk to me)"), ("kitty", "Claude Code")):
            self.assertFalse(re.search(r"\b" + team + r"\b", cls, re.I) or re.search(r"\b" + team + r"\b", title, re.I))
        self.assertTrue(re.search(r"\b" + team + r"\b", "agent-os-team", re.I))
        self.assertTrue(re.search(r"\b" + term + r"\b", "kitty", re.I))

if __name__ == "__main__":
    unittest.main()
