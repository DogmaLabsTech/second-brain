"""Tests for the Deck's voice gate and talk helpers: python3 -I deck/server/test_talk.py
Starts its own server on DECK_TEST_PORT (8799) with a stand-in `brain` (DECK_BRAIN) that only writes down what it was asked, so no
real job ever runs. Checks: a job runs only from the server's own copy of the plan, once, after a Yes click or a plain spoken yes;
a spoken no, silence or an unclear answer does nothing; a plan the page makes up is refused; /talk/warm answers at once;
the pre-roll (talking over the brain) is joined in front of the recording. The stand-in brain is a shell script, so on Windows
(the test machine) these tests are skipped: run them here with CRABBOX_LOCAL=1."""
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("DECK_TEST_PORT", "8799"))
FAKE_BRAIN = r"""#!/bin/sh
# a stand-in for `brain`: ask proposes a job (or answers), job run and outcome only write a line to $FAKE_LOG
case "$1" in
  ask) for q; do :; done
       case "$q" in
         *question*) printf '%s\n' '{"event":"first","text":"A short answer."}' '{"kind":"answer","answer":"A short answer. And the rest.","sources":[],"id":"t27-q","writer":"test"}' ;;
         *) printf '%s\n' "{\"kind\":\"job\",\"answer\":\"I'll add it to your remembered list.\",\"sources\":[],\"id\":\"t27-$$\",\"writer\":\"test\",\"job\":{\"id\":\"remember\",\"label\":\"Remember: zz test\",\"needs_confirm\":true,\"args\":{\"text\":\"zz test\"}}}" ;;
       esac ;;
  job) printf 'job %s\n' "$*" >> "$FAKE_LOG"; printf '%s\n' '{"message":"Got it. I wrote it in your remembered list."}' ;;
  outcome) printf 'outcome %s\n' "$*" >> "$FAKE_LOG" ;;
esac
"""


def call(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    h = {"Host": f"127.0.0.1:{PORT}", "X-Deck": "1", "Content-Type": "application/json", **(headers or {})}
    c.request(method, path, body=json.dumps(body).encode() if isinstance(body, dict) else body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def post(path, body, **k):
    code, data = call("POST", path, body, **k)
    return code, json.loads(data)


def wav_bytes(secs, rate=16000, level=0):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(int(level * ((k // 20) % 2 * 2 - 1)).to_bytes(2, "little", signed=True) for k in range(int(secs * rate))))
    return b.getvalue()


@unittest.skipIf(os.name == "nt", "the stand-in brain is a shell script: run with CRABBOX_LOCAL=1")
class Talk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            call("GET", "/health")
            raise RuntimeError(f"port {PORT} is busy: stop that server or set DECK_TEST_PORT")
        except OSError:
            pass
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "data.js").write_text("window.BRAIN={docs:[]};")
        brain = cls.tmp / "brain"
        brain.write_text(FAKE_BRAIN)
        brain.chmod(0o755)
        cls.log = cls.tmp / "fake.log"
        env = dict(os.environ, DECK_PORT=str(PORT), DECK_DATA=str(cls.tmp / "data.js"), DECK_TALK_LOG=str(cls.tmp / "talk.jsonl"),
                   DECK_ASKS_LOG=str(cls.tmp / "asks.jsonl"), DECK_SEARCHES_LOG=str(cls.tmp / "searches.jsonl"), DECK_BRAIN=str(brain),
                   FAKE_LOG=str(cls.log), DECK_NO_WARM="1", BRAIN_STT_URL="http://127.0.0.1:9/transcribe")
        cls.srv = subprocess.Popen([sys.executable, "-I", str(HERE / "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                call("GET", "/health")
                return
            except OSError:
                time.sleep(0.1)
        cls.srv.kill()
        raise RuntimeError("test server did not start: " + cls.srv.stderr.read().decode()[-500:])

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(10)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ran(self):
        return [l for l in (self.log.read_text().splitlines() if self.log.exists() else []) if l.startswith("job ")]

    def plan(self, q="remember zz test"):
        code, data = call("POST", "/talk/ask", {"q": q, "how": "voice"})
        self.assertEqual(code, 200)
        done = [json.loads(l) for l in data.decode().splitlines() if l.strip()][-1]
        self.assertEqual(done["kind"], "job")
        return done["id"]

    def test_a_click_runs_the_servers_own_plan_once(self):
        i, before = self.plan(), len(self.ran())
        code, r = post("/talk/job", {"id": i, "confirmed": True, "job": {"id": "send-file", "args": {"to": "evil"}}})
        self.assertEqual(code, 200)
        self.assertTrue(r["ok"])
        runs = self.ran()[before:]
        self.assertEqual(len(runs), 1)
        self.assertIn("job run remember", runs[0])   # the page's made-up send-file was ignored
        self.assertNotIn("send-file", runs[0])
        code, r = post("/talk/job", {"id": i, "confirmed": True})
        self.assertEqual(code, 409)                   # a plan runs once
        self.assertEqual(len(self.ran()), before + 1)

    def test_a_plan_the_page_made_up_is_refused(self):
        before = len(self.ran())
        code, _ = post("/talk/job", {"id": "made-up-id", "confirmed": True, "job": {"id": "remember", "args": {"text": "x"}}})
        self.assertEqual(code, 409)
        code, _ = post("/talk/job", {"id": self.plan()})   # no confirmed: true
        self.assertEqual(code, 400)
        self.assertEqual(len(self.ran()), before)

    def test_a_plain_spoken_yes_runs_it(self):
        for said in ("Yes, go ahead.", "yeah do it", "Okay.", "Sure, please do."):
            with self.subTest(said=said):
                i, before = self.plan(), len(self.ran())
                code, r = post("/talk/confirm", {"id": i, "said": said})
                self.assertEqual((code, r["decision"], r["ok"]), (200, "yes", True))
                self.assertEqual(len(self.ran()), before + 1)

    def test_no_silence_or_unclear_does_nothing(self):
        for said, want in (("No, don't.", "no"), ("nope", "no"), ("", "unclear"), ("um", "unclear"), ("Yes, but wait.", "unclear"),
                           ("Yes. What does it do?", "unclear"), ("what is on my remember list", "unclear"), ("maybe", "unclear"),
                           ("yes I think so but not right now please hold on a second", "unclear"), ("Don't do it.", "no")):
            with self.subTest(said=said):
                i, before = self.plan(), len(self.ran())
                code, r = post("/talk/confirm", {"id": i, "said": said})
                self.assertEqual((code, r["decision"]), (200, want))
                self.assertEqual(len(self.ran()), before)
                code, _ = post("/talk/job", {"id": i, "confirmed": True})   # after a no the plan is gone; after unclear a click still works
                self.assertEqual(code, 409 if want == "no" else 200)

    def test_an_answer_keeps_no_plan(self):
        code, data = call("POST", "/talk/ask", {"q": "a question", "how": "voice"})
        lines = [json.loads(l) for l in data.decode().splitlines() if l.strip()]
        self.assertEqual([l["event"] for l in lines], ["first", "done"])
        code, _ = post("/talk/job", {"id": lines[-1]["id"], "confirmed": True})
        self.assertEqual(code, 409)

    def test_warm_answers_at_once(self):
        t = time.monotonic()
        code, r = post("/talk/warm", {})
        self.assertEqual(code, 200)
        self.assertLess(time.monotonic() - t, 2)
        self.assertEqual(r["stt"], "slow")   # BRAIN_STT_URL points at nothing

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_preroll_is_joined_in_front(self):
        pre, rest = wav_bytes(.5), wav_bytes(1.0, rate=48000)
        code, r = post("/talk/stt", pre + rest, headers={"Content-Type": "audio/wav", "X-Preroll": str(len(pre))})
        self.assertEqual(code, 200, r)
        self.assertAlmostEqual(r["secs"], 1.5, delta=.05)
        self.assertEqual((r["heard"], r.get("why")), (False, "silent"))   # silence never reaches the transcriber
        code, r = post("/talk/stt", b"not-a-wav..." + rest, headers={"Content-Type": "audio/wav", "X-Preroll": "12"})
        self.assertEqual(code, 400)   # a pre-roll that is not a WAV


if __name__ == "__main__":
    unittest.main()
