"""Tests for the servers-by-voice job (a temporary hosting list and a pretend hostctl; nothing real is switched):
python3 jobs/test_servers.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jobs  # noqa: E402
import servers  # noqa: E402

SITES = """# name unit lport tport category label
example-game   example-game-preview  4181  18443  Games  Example Game
bt      bt-preview            4179  7443   Prototypes  example-horror prototype
"""
SERVICES = """vox      voxtype         -  -  Voice  Voxtype dictation
ollama   ollama          -  -  AI     Ollama
example-board  example-board         4190  16443  Always-on  Pit Wall board
tthome   example-game-home  4182  19443  Always-on  Example Game home (tablet)
llcnamer llc-namer       4198  28443  Always-on  LLC Namer (for Tino)
"""
FAKE_HOSTCTL = """#!/bin/sh
# pretend hostctl: state is one file per site in $FAKE_STATE
case "$1" in
  list) printf '%s\\t%s\\thttps://x:1\\tLLC Namer (for Tino)\\tAlways-on\\n' "$2" "$( [ -f "$FAKE_STATE/$2" ] && echo UP || echo down )" ;;
  on)  touch "$FAKE_STATE/$2" ;;
  off) rm -f "$FAKE_STATE/$2" ;;
esac
"""


class Servers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = os.path.join(self.tmp.name, "hosting")
        os.makedirs(d)
        for name, text in (("sites.conf", SITES), ("services.conf", SERVICES)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        self.old = os.environ.get("HOSTCTL_CONF_DIR")
        os.environ["HOSTCTL_CONF_DIR"] = d
        self.addCleanup(lambda: os.environ.pop("HOSTCTL_CONF_DIR") if self.old is None
                        else os.environ.__setitem__("HOSTCTL_CONF_DIR", self.old))

    def test_only_entries_with_a_link(self):
        self.assertEqual([e["id"] for e in servers.entries()], ["example-game", "bt", "example-board", "tthome", "llcnamer"])

    def test_names_and_actions(self):
        cases = {"turn on the llc namer": ("on", "llcnamer"), "turn the llc namer off": ("off", "llcnamer"),
                 "stop the pit wall board": ("off", "example-board"), "switch on example-board": ("on", "example-board"),
                 "start the namer": ("on", "llcnamer"), "shut down example-horror": ("off", "bt"),
                 "turn on example-game": ("on", "example-game"), "turn on example-game home": ("on", "tthome"),
                 "take the llc namer down": ("off", "llcnamer")}
        for text, (action, site) in cases.items():
            self.assertEqual(servers.action_of(text), action, text)
            self.assertEqual(servers.find_server(text)["id"], site, text)
            self.assertEqual(jobs.match_rule(text), "servers", text)

    def test_things_that_are_not_server_asks(self):
        for text in ["start a claude on example-game", "start a job on example-game: fix the logs", "open spotify",
                     "turn off the tv", "stop the music", "next theme", "turn on the night light", "turn on voxtype",
                     "turn on ollama", "turn on the llc namer and off the pit wall board", "example-game",
                     "remind me to turn off the llc namer", "turn on the printer",
                     "Start a clot on Example. Tidy the logs.", "start a cloud on example: tidy the logs"]:
            self.assertNotEqual(jobs.match_rule(text), "servers", text)

    def test_ambiguous_half_name_is_not_guessed(self):
        self.assertIsNone(servers.find_server("turn on tamers"))

    def test_build_on_just_happens_off_asks_first(self):
        on = jobs.build("servers", "turn on the llc namer")["job"]
        off = jobs.build("servers", "turn off the llc namer")["job"]
        self.assertEqual((on["needs_confirm"], off["needs_confirm"]), (False, True))
        self.assertEqual(on["args"], {"site": "llcnamer", "action": "on"})
        self.assertEqual(off["label"], "Turn off LLC Namer (for Tino)")

    def test_build_without_a_server_asks(self):
        r = jobs.build("servers", "turn it on")
        self.assertEqual(r["kind"], "answer")
        self.assertIsNone(r["job"])

    def test_route_beats_a_decider_that_says_open_app(self):
        self.assertEqual(jobs.route_label("servers", "job:open-app", "start the namer"), "job:servers")
        self.assertEqual(jobs.route_label(None, "job:open-app", "open spotify"), "job:open-app")

    def test_run_checks_the_arguments(self):
        for bad in ({"site": "vox", "action": "off"}, {"site": "llcnamer", "action": "toggle"},
                    {"site": "../x", "action": "on"}, {}):
            with self.assertRaises(ValueError):
                jobs._check("servers", bad)
        self.assertEqual(jobs._check("servers", {"site": "example-board", "action": "off", "x": 1}),
                         {"site": "example-board", "action": "off"})

    def run_script(self, *args):
        home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(home, ".local", "bin"), exist_ok=True)
        state = os.path.join(self.tmp.name, "state")
        os.makedirs(state, exist_ok=True)
        fake = os.path.join(home, ".local", "bin", "hostctl")
        with open(fake, "w") as f:
            f.write(FAKE_HOSTCTL)
        os.chmod(fake, 0o755)
        r = subprocess.run([os.path.join(HERE, "bin", "servers"), *args], capture_output=True, text=True,
                           env={**os.environ, "HOME": home, "FAKE_STATE": state}, timeout=30)
        return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])["message"], os.path.exists(
            os.path.join(state, "llcnamer"))

    def test_script_turns_on_then_off(self):
        self.assertEqual(self.run_script("on", "llcnamer"), (0, "Turned LLC Namer (for Tino) on.", True))
        self.assertEqual(self.run_script("off", "llcnamer")[:2], (0, "Turned LLC Namer (for Tino) off."))

    def test_script_refuses_bad_asks(self):
        self.assertEqual(self.run_script("restart", "llcnamer")[0], 2)
        self.assertEqual(self.run_script("on", "")[0], 2)


if __name__ == "__main__":
    unittest.main()
