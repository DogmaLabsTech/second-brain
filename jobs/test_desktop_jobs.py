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

    def test_only_power_actions_ask_first(self):
        asks = {a for a, v in desktop.ACTIONS.items() if v[3]}
        self.assertEqual(asks, {"logout", "reboot", "shutdown"})

    def test_commands_fill_values(self):
        self.assertEqual(desktop.action_command("workspace", 3),
                         ["hyprctl", "dispatch", 'hl.dsp.focus({ workspace = "3" })'])
        self.assertEqual(desktop.action_command("reminder", {"minutes": 5, "message": "Tea"}),
                         ["omarchy", "reminder", "5", "Tea"])


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


if __name__ == "__main__":
    unittest.main()
