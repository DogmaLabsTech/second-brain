"""Answers of parse_clock and team_task, taken from the code before they were split into smaller steps, so the
split is held to the same answers: python3 -I jobs/test_split_functions.py"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desktop  # noqa: E402
import jobs  # noqa: E402

NOW = dt.datetime(2026, 10, 20, 12, 47)   # a Tuesday, local time

CLOCK = [
    ('remind me at 2pm to go outside with Ollie', '2026-10-20 14:00', 'Go outside with Ollie'),
    ('at 9:30', '2026-10-20 21:30', 'Reminder'),
    ('tomorrow at 8am call mum', '2026-10-21 08:00', 'Call mum'),
    ('remind me at 7 on friday to pay rent', '2026-10-23 07:00', 'Pay rent'),
    ('at noon eat', '2026-10-21 12:00', 'Eat'),
    ('at midnight sleep', '2026-10-21 00:00', 'Sleep'),
    ('set an alarm at 6 in the morning', '2026-10-21 06:00', 'Reminder'),
    ('at 3 check the oven', '2026-10-20 15:00', 'Check the oven'),
    ('at 2 stretch', '2026-10-20 14:00', 'Stretch'),
    ('remind me tonight at 9 to lock up', '2026-10-20 21:00', 'Lock up'),
    ('at 25 nonsense', None, None),
    ('at 13pm', None, None),
    ('at 12:60', None, None),
    ("at five o'clock feed the cat", '2026-10-20 17:00', 'Feed the cat'),
    ('at 8 at night read', '2026-10-20 20:00', 'Read'),
    ('on monday at 10am dentist', '2026-10-26 10:00', 'Dentist'),
    ('at 11 on friday', '2026-10-23 11:00', 'Reminder'),
    ('hey claude remind me about the bins at 4:15 p.m.', '2026-10-20 16:15', 'The bins'),
    ('nothing to see here', None, None),
    ('at 12:47 now', '2026-10-21 12:47', 'Now'),
]
TEAM = [
    ('start a claude on example: tidy the logs', ('example', 'tidy the logs')),
    ('start an agent on example. Tidy the logs.', ('example', 'Tidy the logs')),
    ('start an agent on example. I need the logs', (None, '')),
    ('start a claude on the desk', (None, '')),
    ('start a claude on the desk to check in', ('desk', 'check in')),
    ('start a claude on example, to check in', ('example', 'check in')),
    ('start a claude on example, ok', (None, '')),
    ('start a claude on example - fix the login bug', ('example', 'fix the login bug')),
    ('start a claude on example and example-rpg', (None, '')),
    ('start a claude on example like now', (None, '')),
    ('start a claude on example to tidy the logs please', ('example', 'tidy the logs')),
    ('start a claude on example so I can watch it', (None, '')),
    ('start a claude on example then add a dark mode', ('example', 'add a dark mode')),
    ("start a claude on example's logs", (None, '')),
    ('play some music', (None, '')),
    ('start a claude on example: example-rpg', (None, '')),
]


class SplitFunctions(unittest.TestCase):
    def test_parse_clock_gives_the_same_moment_and_message(self):
        for text, when, msg in CLOCK:
            with self.subTest(text=text):
                at, said = desktop.parse_clock(text, NOW.timestamp())
                got = dt.datetime.fromtimestamp(at).strftime("%Y-%m-%d %H:%M") if at else None
                self.assertEqual((got, said), (when, msg))

    def test_team_task_gives_the_same_project_and_task(self):
        with mock.patch.object(jobs, "project_names", return_value=["example", "example-rpg", "example-board"]):
            for text, want in TEAM:
                with self.subTest(text=text):
                    self.assertEqual(jobs.team_task(text), want)


if __name__ == "__main__":
    unittest.main()
