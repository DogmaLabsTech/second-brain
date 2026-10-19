"""Tests for jobs/bin/alarm (no timers, no desktop: BRAIN_ALARM_DRY=1). Run: python3 -I jobs/test_alarm.py"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ALARM = os.path.join(HERE, "bin", "alarm")


class Alarm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, BRAIN_ALARM_DIR=os.path.join(self.tmp.name, "a"),
                        BRAIN_ALARM_UNITS=os.path.join(self.tmp.name, "u"), BRAIN_ALARM_DRY="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_alarm(self, *args):
        out = subprocess.run([sys.executable, "-I", ALARM, *args], capture_output=True, text=True, env=self.env)
        return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])

    def test_set_list_fire(self):
        at = int(time.time()) + 3600
        code, got = self.run_alarm("set", str(at), "Go outside with Ollie")
        self.assertEqual(code, 0)
        self.assertIn("Go outside with Ollie", got["message"])
        aid = got["id"]
        timer = open(os.path.join(self.tmp.name, "u", f"brain-alarm-{aid}.timer")).read()
        self.assertIn("OnCalendar=" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(at)), timer)
        self.assertIn("Persistent=true", timer)       # a reminder missed while the computer was off still goes off
        self.assertIn("WantedBy=timers.target", timer)
        service = open(os.path.join(self.tmp.name, "u", f"brain-alarm-{aid}.service")).read()
        self.assertIn(f"fire {aid}", service)
        self.assertIn("1 reminder", self.run_alarm("list")[1]["message"])
        code, got = self.run_alarm("fire", aid)
        self.assertEqual(code, 0)
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, "u")), [])   # the timer is gone after it fired
        fired = [json.loads(l) for l in open(os.path.join(self.tmp.name, "a", "fired.jsonl"))]
        self.assertEqual((fired[0]["message"], fired[0]["how"]), ("Go outside with Ollie", "dry"))
        self.assertEqual(self.run_alarm("list")[1]["message"], "You have no reminders coming up.")
        self.assertIn("Done not pressed yet", self.run_alarm("history")[1]["message"])
        self.assertEqual(self.run_alarm("done", aid, "key"), (0, {"message": "Noted."}))
        out = subprocess.run([sys.executable, "-I", ALARM, "history", "--json"], capture_output=True, text=True,
                             env=self.env)
        row = json.loads(out.stdout)[0]
        self.assertEqual((row["message"], row["by"]), ("Go outside with Ollie", "key"))
        self.assertGreaterEqual(row["done"], row["fired"])
        self.assertIn("Done pressed", self.run_alarm("history")[1]["message"])

    def test_done_needs_a_real_fired_alarm(self):
        self.assertEqual(self.run_alarm("done", "20261018-1400-abcd")[0], 1)       # never went off
        self.assertEqual(self.run_alarm("done", "../../etc")[0], 2)                # not an alarm id

    def test_refuses_the_past_and_far_ahead(self):
        self.assertEqual(self.run_alarm("set", str(int(time.time()) - 10), "x")[0], 2)
        self.assertEqual(self.run_alarm("set", str(int(time.time()) + 8 * 24 * 3600), "x")[0], 2)
        self.assertEqual(self.run_alarm("set", "2pm", "x")[0], 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "u")) and os.listdir(os.path.join(self.tmp.name, "u")))

    def test_cancel_all(self):
        for k in (1, 2):
            self.run_alarm("set", str(int(time.time()) + 3600 * k), f"thing {k}")
        self.assertIn("2 reminders", self.run_alarm("cancel", "all")[1]["message"])
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, "u")), [])


if __name__ == "__main__":
    unittest.main()
