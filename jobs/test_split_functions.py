"""Answers of team_task, taken from the code before they were split into smaller steps, so the
split is held to the same answers: python3 -I jobs/test_split_functions.py"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jobs  # noqa: E402

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
    def test_team_task_gives_the_same_project_and_task(self):
        with mock.patch.object(jobs, "project_names", return_value=["example", "example-rpg", "example-board"]):
            for text, want in TEAM:
                with self.subTest(text=text):
                    self.assertEqual(jobs.team_task(text), want)


if __name__ == "__main__":
    unittest.main()
