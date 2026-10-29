"""Tests for "send files to a device" and "move a window to a screen" (no desktop, no network):
a fake hyprctl, scp, tailscale and send-to-laptop are put on PATH, and HOME is a temp folder.
python3 jobs/test_send_move.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop  # noqa: E402
import jobs  # noqa: E402
import sendfiles  # noqa: E402

BIN = os.path.join(HERE, "bin")


def touch(path, size=10, age=0, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    t = time.time() - age
    os.utime(path, (t, t))
    if mode is not None:
        os.chmod(path, mode)
    return path


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/usr/bin/env python3\n" + body)
    os.chmod(path, 0o755)


MONITORS2 = [
    {"id": 0, "name": "HDMI-A-1", "description": "LG Electronics LG HDR WFHD 0x0007651F", "x": 0, "y": 0,
     "width": 2560, "height": 1080, "focused": False, "disabled": False},
    {"id": 1, "name": "DP-3", "description": "Shenzhen KTC Technology Group H27T27 00000000000", "x": 2560, "y": 0,
     "width": 2560, "height": 1440, "focused": True, "disabled": False},
]
MONITORS3 = MONITORS2 + [{"id": 2, "name": "DP-4", "description": "Dell U2720Q", "x": 5120, "y": 0,
                          "width": 1920, "height": 1080, "focused": False, "disabled": False}]


def client(addr, cls, mon, ws=1, focus=1, title="", **kw):
    return dict({"address": addr, "class": cls, "title": title or cls, "monitor": mon, "workspace": {"id": ws},
                 "mapped": True, "hidden": False, "focusHistoryID": focus}, **kw)


# A fake hyprctl: state in $FAKE_HYPR (json). Dispatches are logged; `stick` makes the window stay put.
FAKE_HYPRCTL = r'''
import json, os, re, sys
st_path = os.environ["FAKE_HYPR"]
st = json.load(open(st_path))
a = sys.argv[1:]
if a[:1] == ["monitors"]:
    print(json.dumps(st["monitors"]))
elif a[:1] == ["clients"]:
    print(json.dumps(st["clients"]))
elif a[:1] == ["activewindow"]:
    print(json.dumps(st.get("active") or {}))
elif a[:1] == ["dispatch"]:
    st.setdefault("log", []).append(a[1])
    m = re.fullmatch(r'hl\.dsp\.window\.move\(\{ monitor = "([^"]+)", window = "address:(0x[0-9a-f]+)" \}\)', a[1])
    if m and not st.get("stick"):
        mon = next((x for x in st["monitors"] if x["name"] == m.group(1)), None)
        for c in st["clients"]:
            if c["address"] == m.group(2) and mon:
                c["monitor"] = mon["id"]
    print("ok")
json.dump(st, open(st_path, "w"))
'''
# launches "fooapp": adds a window to the focused monitor and makes it the active one
FAKE_LAUNCH = r'''
import json, os
st_path = os.environ["FAKE_HYPR"]
st = json.load(open(st_path))
if not any(c["class"].lower() == "fooapp" for c in st["clients"]):
    mon = next(m for m in st["monitors"] if m.get("focused"))
    for c in st["clients"]:
        c["focusHistoryID"] += 1
    st["clients"].append({"address": "0xbeef", "class": "fooapp", "title": "Foo", "monitor": mon["id"],
                          "workspace": {"id": 1}, "mapped": True, "hidden": False, "focusHistoryID": 0})
    st["active"] = st["clients"][-1]
else:
    c = next(c for c in st["clients"] if c["class"].lower() == "fooapp")
    st["active"] = c
st.setdefault("launched", []).append(1)
json.dump(st, open(st_path, "w"))
'''


class Env(unittest.TestCase):
    """A temp HOME, a fake bin folder on PATH and an applications folder with one app."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.fakebin = os.path.join(self.tmp, "bin")
        self.apps = os.path.join(self.tmp, "share", "applications")
        for d in (self.home, self.fakebin, self.apps):
            os.makedirs(d)
        with open(os.path.join(self.apps, "fooapp.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Foo App\nExec=fooapp\nStartupWMClass=fooapp\n")
        self.state = os.path.join(self.tmp, "hypr.json")
        script(os.path.join(self.fakebin, "hyprctl"), FAKE_HYPRCTL)
        script(os.path.join(self.fakebin, "omarchy-launch-or-focus"), FAKE_LAUNCH)
        self.env = dict(os.environ, HOME=self.home, PATH=self.fakebin + os.pathsep + os.environ["PATH"],
                        FAKE_HYPR=self.state, XDG_DATA_HOME=os.path.join(self.tmp, "share"),
                        XDG_DATA_DIRS=os.path.join(self.tmp, "share"))
        self.patches = [mock.patch.multiple(desktop, HOME=self.home, FILE_ROOTS=[self.home]),
                        mock.patch.multiple(jobs, HOME=self.home, PROJECTS=os.path.join(self.home, "projects", "Projects"),
                                            PM_PROJECTS=os.path.join(self.home, "pm"))]
        # In this process too, apps come from the temp applications folder, never this computer's.
        self.patches.append(mock.patch.dict(os.environ, XDG_DATA_HOME=os.path.join(self.tmp, "share"),
                                            XDG_DATA_DIRS=os.path.join(self.tmp, "share")))
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def h(self, *p):
        return os.path.join(self.home, *p)

    def hypr(self, monitors=MONITORS2, clients=(), active=None, **kw):
        with open(self.state, "w") as f:
            json.dump(dict({"monitors": monitors, "clients": list(clients), "active": active}, **kw), f)

    def hypr_state(self):
        with open(self.state) as f:
            return json.load(f)

    def run_bin(self, name, *args, env=None):
        out = subprocess.run([os.path.join(BIN, name), *args], capture_output=True, text=True, timeout=60,
                             env=env or self.env)
        last = [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]
        return out.returncode, (last[-1]["message"] if last else ""), out.stdout


# ---------- routing ----------

class Routing(unittest.TestCase):
    def test_rules(self):
        cases = {
            "can you send the latest example-game files to the laptop": "send-file",
            "send the screenshot to my phone": "send-file",
            "put the kingdom map on my iphone": "send-file",
            "send the lap top the latest example-game file": "send-file",
            "share the latest video with the laptop": "send-file",
            "move this window to my laptop screen": "desktop",
            "move this window to my other screen": "desktop",
            "move chrome to the left monitor": "desktop",
            "move spotify to the right screen": "desktop",
            "open vs code on my second monitor": "open-app",
            "can you open vs code and move it to the left screen": "open-app",
            "take a screenshot": "desktop", "mute the tv": "tv", "open my downloads folder": "open-file",
        }
        for text, want in cases.items():
            self.assertEqual(jobs.match_rule(text), want, text)
        self.assertIsNone(jobs.match_rule("send mom a text"))

    def test_other_jobs_that_mention_a_device_are_not_sends(self):
        # These worked before the send job and must keep working (the skeptic's regression list).
        cases = {
            "remind me in 10 minutes to put the charger on the laptop": "desktop",
            "remember to send the invoice to my phone": "remember",
            "can you put the volume up on the laptop": "desktop",
            "put the night light on for the laptop": "desktop",
            "take a screenshot and send it to my phone": "desktop",
        }
        for text, want in cases.items():
            self.assertEqual(jobs.match_rule(text), want, text)
            self.assertFalse(sendfiles.is_send_request(text), text)
        self.assertEqual(jobs.build("desktop", "remind me in 10 minutes to put the charger on the laptop")["job"]["label"],
                         "Remind you in 10 minutes: Put the charger on the laptop")
        self.assertEqual(jobs.build("desktop", "can you put the volume up on the laptop")["job"]["label"],
                         "Turn the computer up")
        self.assertEqual(jobs.build("desktop", "take a screenshot and send it to my phone")["job"]["label"],
                         "Take a screenshot")
        self.assertTrue(sendfiles.is_send_request("please send my last screenshot to the testbox"))
        self.assertTrue(sendfiles.is_send_request("hey claude can you send the lap top the latest example-game file"))

    def test_how_question_is_a_question(self):
        self.assertTrue(jobs.is_how_question("how do I send a file to the laptop"))

    def test_decider_label_is_corrected_by_rule(self):
        r = jobs.route_label
        self.assertEqual(r("send-file", "job:open-file", "send it to the laptop"), "job:send-file")
        self.assertEqual(r("send-file", "job:desktop", "send it to the laptop"), "job:send-file")
        # a desktop label the desktop job can do stays, and a send label gives way to another job's rule
        self.assertEqual(r("send-file", "job:desktop", "put the volume up on the laptop"), "job:desktop")
        self.assertEqual(r("desktop", "job:send-file", "remind me in 10 minutes to put the charger on the laptop"),
                         "job:desktop")
        self.assertEqual(r("remember", "job:send-file", "remember to send the invoice to my phone"), "job:remember")
        self.assertEqual(r("desktop", "job:open-app", "move chrome to my other screen"), "job:desktop")
        self.assertEqual(r("open-app", "job:open-app", "open vs code on my second monitor"), "job:open-app")
        self.assertEqual(r("desktop", "job:open-app", "open the theme picker"), "job:open-app")

    def test_device_words_and_speech_slips(self):
        d = sendfiles.device_from
        self.assertEqual(d("send it to the lap top"), "laptop")
        self.assertEqual(d("send it to the lab top"), "laptop")
        self.assertEqual(d("put it on my i phone"), "phone")
        self.assertEqual(d("copy it to the testbox handheld"), "testbox")
        self.assertEqual(d("send it to the rogue"), "testbox")
        self.assertEqual(d("send the laptop the file"), "laptop")
        self.assertIsNone(d("send mom a text"))

    def test_monitor_words(self):
        m = desktop.monitor_spec
        self.assertEqual(m("move this window to my other screen"), "other")
        self.assertEqual(m("open vs code on my second monitor"), "other")
        self.assertEqual(m("move it to the left monitor"), "left")
        self.assertEqual(m("move it to the right display"), "right")
        self.assertEqual(m("move chrome to monitor 2"), "other")
        self.assertEqual(m("move it to the TV screen"), "name:tv")
        self.assertEqual(m("open it on my main screen"), "main")
        self.assertIsNone(m("open spotify"))
        self.assertIsNone(m("open it on my screen"))


# ---------- sending: what gets picked ----------

class Picking(Env):
    def setUp(self):
        super().setUp()
        self.projects = self.h("projects", "Projects")
        os.makedirs(os.path.join(self.projects, "example-game", "docs"))
        os.makedirs(os.path.join(self.projects, "example-rpg"))
        touch(self.h("Documents", "example-game-Arena-how-to-play.txt"), age=100)
        touch(self.h("Downloads", "example-game", "build-notes.md"), age=200)
        touch(self.h("Downloads", "example-game", "old-notes.md"), age=3 * 86400)
        touch(os.path.join(self.projects, "example-game", "README.md"), age=5 * 86400)
        touch(os.path.join(self.projects, "example-game", "docs", "design.md"), age=9 * 86400)
        touch(os.path.join(self.projects, "example-game", "node_modules", "x", "readme.md"), age=1)
        touch(os.path.join(self.projects, "example-game", ".git", "notes.md"), age=1)
        touch(self.h("Media", "Pictures", "Screenshots", "screenshot-1.png"), age=500)
        touch(self.h("Media", "Pictures", "Screenshots", "screenshot-2.png"), age=50)
        touch(self.h("Downloads", "invoice.pdf"), age=800)
        touch(self.h("Downloads", "example-rpg", "kingdom-map.png"), age=60)

    def plan(self, text):
        return sendfiles.plan(text, find_project=jobs.find_project, projects_root=self.projects,
                              project_dirs=[os.path.join(self.projects, p) for p in jobs.project_names()])

    def test_latest_project_files(self):
        got = self.plan("can you send the latest example-game files to the laptop")
        self.assertEqual(got["device"], "laptop")
        self.assertEqual(got["name"], "Example Game")
        names = [os.path.basename(p) for p in got["paths"]]
        # the newest, plus those within an hour of it; nothing from node_modules or .git
        self.assertEqual(names, ["example-game-Arena-how-to-play.txt", "build-notes.md"])
        self.assertTrue(got["label"].startswith("Send 2 Example Game files to the laptop"))
        for n in names:
            self.assertIn(n, got["answer"])

    def test_singular_is_one_file(self):
        got = self.plan("send the latest example-game file to the testbox")
        self.assertEqual([os.path.basename(p) for p in got["paths"]], ["example-game-Arena-how-to-play.txt"])
        self.assertEqual(got["device"], "testbox")

    def test_plural_is_capped_at_five(self):
        for i in range(8):
            touch(self.h("Downloads", "example-game", f"shot-{i}.png"), age=10 + i)
        got = self.plan("send the latest example-game files to the laptop")
        self.assertEqual(len(got["paths"]), 5)

    def test_latest_screenshot(self):
        got = self.plan("send my last screenshot to the testbox")
        self.assertEqual([os.path.basename(p) for p in got["paths"]], ["screenshot-2.png"])
        got = self.plan("send the screenshot to my phone")
        self.assertEqual([os.path.basename(p) for p in got["paths"]], ["screenshot-2.png"])

    def test_nothing_found_is_an_answer(self):
        shutil.rmtree(self.h("Downloads", "example-game"))
        os.remove(self.h("Documents", "example-game-Arena-how-to-play.txt"))
        shutil.rmtree(os.path.join(self.projects, "example-game"))
        os.makedirs(os.path.join(self.projects, "example-game"))
        got = self.plan("send the latest example-game files to the laptop")
        self.assertNotIn("paths", got)
        self.assertIn("couldn't find any Example Game files", got["answer"])

    def test_missing_device_asks(self):
        self.assertIn("Which one", self.plan("send the latest example-game files")["answer"])

    def test_config_sources_are_searched(self):
        extra = os.path.join(self.tmp, "extra")
        touch(os.path.join(extra, "tt-balance.csv"), age=1)
        cfg = os.path.join(self.tmp, "sources.json")
        with open(cfg, "w") as f:
            json.dump({"example-game": [extra]}, f)
        # outside home: allowed_path refuses it, so it is dropped, not sent
        with mock.patch.object(sendfiles, "SOURCES", cfg):
            files = sendfiles.project_files("example-game", os.path.join(self.projects, "example-game"))
        self.assertNotIn(os.path.join(extra, "tt-balance.csv"), files)
        inside = os.path.join(self.home, "extra")
        shutil.copytree(extra, inside)
        with open(cfg, "w") as f:
            json.dump({"example-game": [inside]}, f)
        with mock.patch.object(sendfiles, "SOURCES", cfg):
            files = sendfiles.project_files("example-game", os.path.join(self.projects, "example-game"))
        self.assertIn(os.path.join(inside, "tt-balance.csv"), files)

    @unittest.skipUnless(shutil.which("fd"), "needs fd")
    def test_words_that_name_no_file_get_a_question_not_a_card(self):
        # Files whose names hold the words said, the way the skeptic's real home had them.
        for rel in ("Applications/vesktop/locales/it.pak", "go/pkg/mod/oauth2/spotify/x.go",
                    "Downloads/images/to-mom.jpg", "notes/note.md", "cfg/music.json", "src/timer.rs",
                    "tools/oncall.py", "cfg/tv.json", "code/windows-ssh-keys.ts", "code/src/env.rs"):
            touch(self.h(*rel.split("/")))
        with open(os.path.join(self.apps, "spotify.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Spotify\nExec=spotify\n")
        for text in ("send it to the laptop", "put spotify on the laptop", "send a text to mom on my phone",
                     "can you send me a note on my phone", "move the music to my phone", "get the time on my phone",
                     "transfer the call to my phone", "send the tv to the laptop", "send my ssh key to the laptop",
                     "send the .env to the laptop"):
            got = self.plan(text)
            self.assertNotIn("paths", got, f"{text} -> {got.get('paths')}")
        self.assertIn("key or a password", self.plan("send my ssh key to the laptop")["answer"])
        self.assertIn("Spotify is an app", self.plan("put spotify on the laptop")["answer"])
        self.assertIn("Which file", self.plan("send it to the laptop")["answer"])
        self.assertIn("only send files", self.plan("send a text to mom on my phone")["answer"])
        # a code file is still sent when its whole name is said
        got = self.plan("send timer.rs to the laptop")
        self.assertEqual([os.path.basename(p) for p in got["paths"]], ["timer.rs"])

    @unittest.skipUnless(shutil.which("fd"), "needs fd")
    def test_name_search(self):
        got = self.plan("send the kingdom map to my phone")
        self.assertEqual([os.path.basename(p) for p in got["paths"]], ["kingdom-map.png"])


# ---------- sending: the safety check ----------

class Safety(Env):
    def test_refused_paths(self):
        touch(self.h(".ssh", "id_rsa"))
        touch(self.h("Downloads", "run.sh"), mode=0o755)
        touch(self.h("Downloads", "tool"), mode=0o755)
        touch(self.h("Downloads", "my-secret-plan.txt"))
        touch(self.h("Downloads", "bank-token.txt"))
        touch(self.h("Downloads", "cert.pem"))
        touch(self.h("Downloads", ".env"))
        os.symlink("/etc/passwd", self.h("Downloads", "link.txt"))
        for p in (self.h(".ssh", "id_rsa"), self.h("Downloads", "run.sh"), self.h("Downloads", "tool"),
                  self.h("Downloads", "my-secret-plan.txt"), self.h("Downloads", "bank-token.txt"),
                  self.h("Downloads", "cert.pem"), self.h("Downloads", ".env"), "/etc/passwd",
                  self.h("Downloads", "link.txt"), self.h("Downloads", "missing.txt")):
            with self.assertRaises(ValueError, msg=p):
                sendfiles.check_send("laptop", [p])

    def test_bad_device_and_shapes(self):
        touch(self.h("Downloads", "a.txt"))
        for dev, paths in [("fridge", [self.h("Downloads", "a.txt")]), ("laptop", []), ("laptop", "a.txt"),
                           ("laptop", [5]), ("laptop", [self.h("Downloads", "a.txt")] * 0)]:
            with self.assertRaises(ValueError):
                sendfiles.check_send(dev, paths)

    def test_caps(self):
        files = [touch(self.h("Downloads", f"f{i}.txt")) for i in range(12)]
        self.assertEqual(len(sendfiles.check_send("laptop", files[:10])[1]), 10)
        with self.assertRaises(ValueError):
            sendfiles.check_send("laptop", files[:11])   # more than 10
        with self.assertRaises(ValueError):
            sendfiles.check_send("testbox", files[:6])       # more than 5
        big = touch(self.h("Downloads", "big.mp4"), size=1)
        with mock.patch.object(os.path, "getsize", return_value=480 * 1024 * 1024):
            with self.assertRaises(ValueError) as cm:
                sendfiles.check_send("laptop", [big])
        self.assertIn("480 MB", str(cm.exception))
        self.assertIn("300 MB", str(cm.exception))
        with mock.patch.object(os.path, "getsize", return_value=150 * 1024 * 1024):
            sendfiles.check_send("laptop", [big])
            with self.assertRaises(ValueError):
                sendfiles.check_send("phone", [big])

    def test_folders(self):
        touch(self.h("Downloads", "pack", "a.txt"))
        touch(self.h("Downloads", "pack", "sub", "b.md"))
        dev, real, info = sendfiles.check_send("laptop", [self.h("Downloads", "pack")])
        self.assertEqual((info["count"], info["dirs"]), (2, 1))
        touch(self.h("Downloads", "hidden-pack", ".git", "config"))
        with self.assertRaises(ValueError):
            sendfiles.check_send("laptop", [self.h("Downloads", "hidden-pack")])
        touch(self.h("Downloads", "with-secret", "id_rsa"))
        with self.assertRaises(ValueError):
            sendfiles.check_send("laptop", [self.h("Downloads", "with-secret")])
        for i in range(201):
            touch(self.h("Downloads", "many", f"{i}.txt"), size=1)
        with self.assertRaises(ValueError):
            sendfiles.check_send("laptop", [self.h("Downloads", "many")])

    def test_links_inside_a_folder_are_refused(self):
        touch(self.h(".ssh", "id_ed25519"))
        touch(self.h("Documents", "trip", "plan.txt"))
        os.symlink("../../.ssh", self.h("Documents", "trip", "stuff"))
        with self.assertRaises(ValueError) as cm:
            sendfiles.check_send("laptop", [self.h("Documents", "trip")])
        self.assertIn("links", str(cm.exception))
        os.remove(self.h("Documents", "trip", "stuff"))
        os.symlink(self.h(".ssh", "id_ed25519"), self.h("Documents", "trip", "notes.txt"))
        with self.assertRaises(ValueError):
            sendfiles.check_send("laptop", [self.h("Documents", "trip")])
        with self.assertRaises(ValueError):
            jobs._check("send-file", {"device": "laptop", "paths": [self.h("Documents", "trip")]})
        os.remove(self.h("Documents", "trip", "notes.txt"))
        self.assertEqual(sendfiles.check_send("laptop", [self.h("Documents", "trip")])[2]["count"], 1)

    def test_changed_job_object_is_refused_by_run(self):
        touch(self.h("Downloads", "a.txt"))
        for args in ({"device": "fridge", "paths": [self.h("Downloads", "a.txt")]},
                     {"device": "laptop", "paths": ["../../etc/passwd"]},
                     {"device": "laptop", "paths": [self.h("Downloads", "a.txt")] * 0},
                     {"device": "laptop", "paths": [self.h("Downloads", f"{i}.txt") for i in range(50)]},
                     {"device": "laptop", "paths": ["/etc/passwd"]}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = jobs.run("send-file", {"args": args})
            self.assertEqual(code, 2, args)
            self.assertIn("didn't do it", buf.getvalue())

    def test_card_asks_first_and_names_everything(self):
        projects = self.h("projects", "Projects")
        os.makedirs(os.path.join(projects, "example-game"))
        touch(self.h("Documents", "example-game-Arena-how-to-play.txt"), age=100)
        touch(self.h("Documents", "example-game-arena-map.png"), age=120)
        built = jobs.build("send-file", "can you send the latest example-game files to the laptop")
        self.assertEqual(built["kind"], "job")
        job = built["job"]
        self.assertTrue(job["needs_confirm"])
        self.assertIn("laptop", job["label"])
        for n in ("example-game-Arena-how-to-play.txt", "example-game-arena-map.png"):
            self.assertIn(n, built["answer"])
        # what the island sends back is accepted by the check
        got = jobs._check("send-file", job["args"])
        self.assertEqual(got["device"], "laptop")
        self.assertEqual(len(got["paths"]), 2)


# ---------- sending: bin/send ----------

class SendScript(Env):
    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.tmp, "calls.log")
        fake = os.path.join(self.tmp, "fake-send-to-laptop")
        script(fake, f'import sys, json\nopen({self.log!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")\n')
        self.env["BRAIN_SEND_BIN"] = fake
        for tool in ("scp", "tailscale"):
            script(os.path.join(self.fakebin, tool),
                   'import sys, json, os\nlog = os.environ["CALLS"]\n'
                   'if sys.argv[1:2] == ["status"]:\n'
                   '    print(json.dumps({"Peer": {"a": {"DNSName": "host.example.ts.net.", "Online": os.environ.get("TESTBOX_ON", "1") == "1"},'
                   ' "b": {"DNSName": "host.example.ts.net.", "Online": True}}}))\n'
                   'else:\n'
                   '    open(log, "a").write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")\n')
        self.env["CALLS"] = self.log
        os.makedirs(self.h(".local", "state", "bar-status"))
        self.status(mounted=True, age=30)

    def status(self, mounted, age):
        with open(self.h(".local", "state", "bar-status", "laptop.json"), "w") as f:
            json.dump({"mounted": mounted, "at": time.time() - age}, f)

    def calls(self):
        try:
            with open(self.log) as f:
                return [json.loads(l) for l in f]
        except OSError:
            return []

    def test_one_file_goes_straight_through(self):
        f = touch(self.h("Downloads", "map.png"))
        code, msg, _ = self.run_bin("send", "laptop", json.dumps([f]), "Files")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), [[os.path.realpath(f)]])
        self.assertIn("Sent map.png to the laptop", msg)
        self.assertIn("From desktop", msg)

    def test_several_files_make_one_folder(self):
        fs = [touch(self.h("Downloads", n)) for n in ("a.txt", "b.txt", "c.md")]
        code, msg, _ = self.run_bin("send", "laptop", json.dumps(fs), "Example Game")
        self.assertEqual(code, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        folder = calls[0][0]
        self.assertTrue(os.path.basename(folder).startswith("Example Game - "))
        self.assertEqual(sorted(os.listdir(folder)), ["a.txt", "b.txt", "c.md"])
        self.assertIn("3 files", msg)
        # a second run the same minute gets its own folder
        self.run_bin("send", "laptop", json.dumps(fs), "Example Game")
        self.assertNotEqual(self.calls()[1][0], folder)

    def test_stale_laptop_status_says_so(self):
        f = touch(self.h("Downloads", "map.png"))
        self.status(mounted=True, age=600)
        code, msg, _ = self.run_bin("send", "laptop", json.dumps([f]), "Files")
        self.assertEqual(code, 0)
        self.assertIn("off or asleep", msg)
        self.assertEqual(len(self.calls()), 1)   # still lined up
        self.status(mounted=False, age=10)
        self.assertIn("off or asleep", self.run_bin("send", "laptop", json.dumps([f]), "Files")[1])

    def test_old_stage_folders_are_deleted(self):
        stage = self.h(".local", "state", "send-to-laptop", "files")
        old = os.path.join(stage, "Example Game - 2026-09-01")
        new = os.path.join(stage, "Example Game - 2026-10-14")
        other = os.path.join(stage, "photo-copy")
        for d in (old, new, other):
            touch(os.path.join(d, "x.txt"))
        t = time.time() - 20 * 86400
        os.utime(old, (t, t))
        os.utime(other, (t, t))
        f = touch(self.h("Downloads", "map.png"))
        self.run_bin("send", "laptop", json.dumps([f]), "Files")
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))
        self.assertTrue(os.path.exists(other))   # not one of ours

    def test_rog_and_phone_dry_runs_print_the_exact_argv(self):
        f = touch(self.h("Downloads", "a b.txt"))
        _, msg, out = self.run_bin("send", "--dry", "testbox", json.dumps([f]), "Files")
        self.assertIn(json.dumps(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                  os.path.realpath(f), "testbox:Downloads/"]), out)
        self.assertIn("Dry run", msg)
        _, _, out = self.run_bin("send", "--dry", "phone", json.dumps([f]), "Files")
        self.assertIn(json.dumps(["tailscale", "file", "cp", os.path.realpath(f), "owners-iphone:"]), out)
        self.assertEqual(self.calls(), [])

    def test_rog_sends_one_scp_per_file(self):
        fs = [touch(self.h("Downloads", n)) for n in ("a.txt", "b.txt")]
        code, msg, _ = self.run_bin("send", "testbox", json.dumps(fs), "Files")
        self.assertEqual(code, 0, msg)
        self.assertEqual([c[0] for c in self.calls()], ["scp", "scp"])
        self.assertIn("test machine", msg)

    def test_rog_off_is_said(self):
        f = touch(self.h("Downloads", "a.txt"))
        env = dict(self.env, TESTBOX_ON="0")
        code, msg, _ = self.run_bin("send", "testbox", json.dumps([f]), "Files", env=env)
        self.assertEqual(code, 1)
        self.assertIn("isn't on", msg)
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless(shutil.which("zip"), "needs zip")
    def test_folder_is_zipped_for_the_phone(self):
        touch(self.h("Downloads", "pack", "a.txt"))
        code, msg, _ = self.run_bin("send", "phone", json.dumps([self.h("Downloads", "pack")]), "Files")
        self.assertEqual(code, 0, msg)
        sent = self.calls()[0]
        self.assertEqual(sent[:3], ["tailscale", "file", "cp"])
        self.assertTrue(sent[3].endswith(".zip"))
        self.assertTrue(os.path.exists(sent[3]))

    @unittest.skipUnless(shutil.which("zip") and shutil.which("unzip"), "needs zip")
    def test_stage_and_zip_never_follow_links(self):
        # Even if a link got past the check, the copy and the zip keep it a link, not the secret it points to.
        import importlib.machinery
        import importlib.util
        touch(self.h(".ssh", "id_ed25519"))
        with open(self.h(".ssh", "id_ed25519"), "w") as f:
            f.write("SECRETKEY")
        touch(self.h("Documents", "trip", "plan.txt"))
        os.symlink("../../.ssh", self.h("Documents", "trip", "stuff"))
        loader = importlib.machinery.SourceFileLoader("sendbin", os.path.join(BIN, "send"))
        spec = importlib.util.spec_from_loader("sendbin", loader)
        m = importlib.util.module_from_spec(spec)
        loader.exec_module(m)
        with mock.patch.multiple(m, STAGE=os.path.join(self.tmp, "stage")):
            folder = m.stage([self.h("Documents", "trip"), touch(self.h("Documents", "a.txt"))], "Trip")
            z = m.zip_folder(self.h("Documents", "trip"))
        for dirpath, _, files in os.walk(folder):
            for f in files:
                p = os.path.join(dirpath, f)
                if not os.path.islink(p):
                    with open(p) as fh:
                        self.assertNotIn("SECRETKEY", fh.read())
        self.assertNotIn("SECRETKEY", subprocess.run(["unzip", "-p", z], capture_output=True, text=True).stdout)
        # and the script itself refuses the folder
        code, msg, _ = self.run_bin("send", "laptop", json.dumps([self.h("Documents", "trip")]), "Trip")
        self.assertEqual(code, 2)
        self.assertEqual(self.calls(), [])

    def test_script_refuses_what_the_check_refuses(self):
        code, msg, _ = self.run_bin("send", "laptop", json.dumps(["/etc/passwd"]), "Files")
        self.assertEqual(code, 2)
        self.assertEqual(self.calls(), [])
        code, msg, _ = self.run_bin("send", "laptop", json.dumps(["/etc/passwd"]))
        self.assertEqual(code, 2)


# ---------- moving windows ----------

class Move(Env):
    def act(self, to="other", app=None):
        return self.run_bin("desktop", "action", "window-monitor", json.dumps({"to": to, "app": app}))

    def test_other_moves_the_active_window_with_the_exact_dispatch(self):
        c = client("0xaaa", "google-chrome", 1, focus=0)
        self.hypr(clients=[c, client("0xbbb", "kitty", 0, focus=1)], active=c)
        code, msg, _ = self.act("other")
        self.assertEqual(code, 0, msg)
        self.assertEqual(self.hypr_state()["log"],
                         ['hl.dsp.window.move({ monitor = "HDMI-A-1", window = "address:0xaaa" })'])
        self.assertEqual(msg, "Moved this window to the left screen.")

    def test_left_and_right(self):
        c = client("0xaaa", "google-chrome", 0, focus=0)
        self.hypr(clients=[c], active=c)
        code, msg, _ = self.act("right")
        self.assertEqual((code, msg), (0, "Moved this window to the right screen."))
        self.assertIn('monitor = "DP-3"', self.hypr_state()["log"][0])

    def test_already_there_does_not_dispatch(self):
        c = client("0xaaa", "google-chrome", 1, focus=0)
        self.hypr(clients=[c], active=c)
        code, msg, _ = self.act("right")
        self.assertEqual(code, 0)
        self.assertIn("already on the right screen", msg)
        self.assertNotIn("log", self.hypr_state())

    def test_three_monitors_other_is_the_next_one(self):
        c = client("0xaaa", "google-chrome", 2, focus=0)   # on the far right: wraps to the left
        self.hypr(monitors=MONITORS3, clients=[c], active=c)
        code, msg, _ = self.act("other")
        self.assertIn('monitor = "HDMI-A-1"', self.hypr_state()["log"][0])
        c = client("0xaaa", "google-chrome", 0, focus=0)
        self.hypr(monitors=MONITORS3, clients=[c], active=c)
        self.act("other")
        self.assertIn('monitor = "DP-3"', self.hypr_state()["log"][0])
        self.hypr(monitors=MONITORS3, clients=[c], active=c)
        self.act("name:dell")
        self.assertIn('monitor = "DP-4"', self.hypr_state()["log"][0])

    def test_one_screen_is_refused(self):
        c = client("0xaaa", "google-chrome", 0, focus=0)
        self.hypr(monitors=MONITORS2[:1], clients=[c], active=c)
        code, msg, _ = self.act("other")
        self.assertEqual(code, 1)
        self.assertEqual(msg, "You only have one screen right now.")

    def test_unknown_screen_is_refused(self):
        c = client("0xaaa", "google-chrome", 1, focus=0)
        self.hypr(clients=[c], active=c)
        code, msg, _ = self.act("name:tv")
        self.assertEqual(code, 2)
        self.assertIn("don't see a screen called TV", msg)
        self.assertNotIn("log", self.hypr_state())

    def test_injection_is_refused(self):
        c = client("0xaaa", "google-chrome", 1, focus=0)
        self.hypr(clients=[c], active=c)
        for to in ('"; reboot', "name:; reboot", "other; reboot", "name:dp-3\" })"):
            code, msg, _ = self.act(to)
            self.assertEqual(code, 2, to)
        code, msg, _ = self.act("other", app="x; reboot")
        self.assertEqual(code, 2)
        self.assertNotIn("log", self.hypr_state())

    def test_no_active_window_uses_the_focus_history(self):
        a = client("0xaaa", "google-chrome", 1, focus=2)
        b = client("0xbbb", "kitty", 1, focus=1)
        scratch = client("0xccc", "kitty", 0, ws=-98, focus=0)   # a scratchpad window: never the target
        self.hypr(clients=[a, b, scratch], active=None)
        code, msg, _ = self.act("other")
        self.assertEqual(code, 0, msg)
        self.assertIn("address:0xbbb", self.hypr_state()["log"][0])

    def test_nothing_to_move(self):
        self.hypr(clients=[], active=None)
        code, msg, _ = self.act("other")
        self.assertEqual(code, 1)
        self.assertIn("couldn't tell which window", msg)

    def test_window_that_stays_put_is_reported_honestly(self):
        c = client("0xaaa", "google-chrome", 1, focus=0)
        self.hypr(clients=[c], active=c, stick=True)
        code, msg, _ = self.act("other")
        self.assertEqual(code, 1)
        self.assertEqual(msg, "I tried to move it but it stayed where it was.")

    def test_named_app_moves_its_own_window_not_the_active_one(self):
        foo = client("0xfff", "fooapp", 1, focus=3)
        other = client("0xaaa", "kitty", 1, focus=0)
        self.hypr(clients=[foo, other], active=other)
        code, msg, _ = self.act("other", app="fooapp")
        self.assertEqual(code, 0, msg)
        self.assertIn("address:0xfff", self.hypr_state()["log"][0])
        self.assertEqual(msg, "Moved Foo App to the left screen.")

    def test_open_on_a_screen_waits_for_the_new_window_and_moves_it(self):
        self.hypr(clients=[client("0xaaa", "kitty", 1, focus=0)], active=None)
        code, msg, _ = self.run_bin("desktop", "app", "fooapp", "other")
        self.assertEqual(code, 0, msg)
        st = self.hypr_state()
        self.assertEqual(st["log"], ['hl.dsp.window.move({ monitor = "HDMI-A-1", window = "address:0xbeef" })'])
        self.assertEqual(msg, "Opened Foo App on the left screen.")

    def test_open_when_already_open_focuses_then_moves(self):
        foo = client("0xfff", "fooapp", 1, focus=0)
        self.hypr(clients=[foo], active=foo)
        code, msg, _ = self.run_bin("desktop", "app", "fooapp", "left")
        self.assertEqual(code, 0, msg)
        self.assertIn("address:0xfff", self.hypr_state()["log"][0])
        self.assertEqual(len(self.hypr_state()["launched"]), 1)

    def test_open_terminal_moves_the_new_window_not_an_old_one(self):
        # `omarchy launch terminal` always opens a new window; the old terminal must stay where it is.
        script(os.path.join(self.fakebin, "omarchy"), r'''
import json, os
st_path = os.environ["FAKE_HYPR"]
st = json.load(open(st_path))
for c in st["clients"]:
    c["focusHistoryID"] += 1
st["clients"].append({"address": "0xa11", "class": "Alacritty", "title": "Alacritty", "monitor": 1,
                      "workspace": {"id": 1}, "mapped": True, "hidden": False, "focusHistoryID": 0})
st["active"] = st["clients"][-1]
json.dump(st, open(st_path, "w"))
''')
        old = client("0x111", "kitty", 1, focus=0, title="claude")
        self.hypr(clients=[old], active=old)
        code, msg, _ = self.run_bin("desktop", "app", "@terminal", "other")
        self.assertEqual(code, 0, msg)
        self.assertEqual(self.hypr_state()["log"],
                         ['hl.dsp.window.move({ monitor = "HDMI-A-1", window = "address:0xa11" })'])
        self.assertEqual(msg, "Opened Terminal on the left screen.")

    def test_title_with_a_short_app_word_is_not_that_app(self):
        # "Claude Code - ..." in a terminal is not VS Code: VS Code's short words must be the whole class.
        with open(os.path.join(self.apps, "com.microsoft.VSCode.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Visual Studio Code\nExec=code %F\n"
                    "StartupWMClass=code\n")
        kitty = client("0x111", "kitty", 1, focus=0, title="Claude Code - fix the code review")
        chrome = client("0x222", "google-chrome", 1, focus=1)
        self.hypr(clients=[kitty, chrome], active=kitty)
        code, msg, _ = self.act("left", app="com.microsoft.VSCode")
        self.assertEqual(code, 1)
        self.assertIn("couldn't find Visual Studio Code open", msg)
        self.assertNotIn("log", self.hypr_state())
        vs = client("0x333", "code", 1, focus=2, title="main.py - proj - Visual Studio Code")
        self.hypr(clients=[kitty, chrome, vs], active=kitty)
        code, msg, _ = self.act("left", app="com.microsoft.VSCode")
        self.assertEqual(code, 0, msg)
        self.assertIn("address:0x333", self.hypr_state()["log"][0])
        # launch-or-focus gets the same pattern, so it won't focus the terminal either
        import re
        pat = desktop.app_command("com.microsoft.VSCode")[1]
        rx = re.compile(r"\b" + pat + r"\b", re.I)
        self.assertFalse(rx.search(kitty["title"]) or rx.search(kitty["class"]))
        self.assertTrue(rx.search("code") and rx.search(vs["title"]))

    def test_open_with_a_bad_screen_is_refused(self):
        self.hypr(clients=[], active=None)
        code, msg, _ = self.run_bin("desktop", "app", "fooapp", "; reboot")
        self.assertEqual(code, 2)
        self.assertNotIn("launched", self.hypr_state())

    def test_open_without_a_screen_is_unchanged(self):
        self.hypr(clients=[], active=None)
        for arg in ("", "{monitor}"):
            code, msg, _ = self.run_bin("desktop", "app", "fooapp", arg)
            self.assertEqual((code, msg), (0, "Opened Foo App."))
        self.assertNotIn("log", self.hypr_state())


class MoveBuild(Env):
    def test_cards(self):
        with mock.patch.object(desktop, "monitors", return_value=MONITORS2):
            b = jobs.build("desktop", "move this window to my other screen")
            self.assertEqual(b["job"]["args"], {"action": "window-monitor", "value": {"to": "other", "app": None}})
            self.assertFalse(b["job"]["needs_confirm"])
            self.assertEqual(jobs.build("desktop", "move this window to the TV screen")["kind"], "answer")
            self.assertEqual(jobs.build("desktop", "move this window to the main screen")["kind"], "answer")
            self.assertEqual(jobs.build("desktop", "move this window to the screen")["kind"], "answer")
        with mock.patch.object(desktop, "monitors", return_value=MONITORS2), \
                mock.patch.object(desktop, "find_app", return_value=("obsidian", "Obsidian", 1.0)):
            o = jobs.build("open-app", "open obsidian on my second monitor")
        self.assertEqual(o["job"]["args"], {"app": "obsidian", "name": "Obsidian", "monitor": "other"})

    def test_a_file_word_never_opens_an_app(self):
        with open(os.path.join(self.apps, "xfce4-file-manager.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=File Manager\nExec=thunar\n")
        with mock.patch.object(desktop, "monitors", return_value=MONITORS2), \
                mock.patch.object(desktop, "clients", return_value=[]):
            b = jobs.build("desktop", "move the file to the other screen")
            self.assertEqual(b["kind"], "answer")
            self.assertIn("not files", b["answer"])
            # a sure app name that isn't open still opens and moves
            o = jobs.build("desktop", "move fooapp to the left screen")
            self.assertEqual(o["job"]["id"], "open-app")

    def test_one_screen_card_is_an_answer(self):
        with mock.patch.object(desktop, "monitors", return_value=MONITORS2[:1]):
            self.assertEqual(jobs.build("desktop", "move this window to my other screen")["kind"], "answer")

    def test_check_refuses_a_changed_monitor(self):
        with mock.patch.object(desktop, "monitors", return_value=MONITORS2):
            with self.assertRaises(ValueError):
                jobs._check("desktop", {"action": "window-monitor", "value": {"to": "; reboot", "app": None}})
            with self.assertRaises(ValueError):
                jobs._check("desktop", {"action": "window-monitor", "value": {"to": "main", "app": None}})
            self.assertEqual(jobs._check("desktop", {"action": "window-monitor", "value": {"to": "left", "app": None}}),
                             {"action": "window-monitor", "value": {"to": "left", "app": None}})
            self.assertEqual(desktop.check_monitor_spec("name:lg"), "name:lg")
            with self.assertRaises(ValueError):
                desktop.check_monitor_spec("name:tv")


if __name__ == "__main__":
    unittest.main()
