"""Tests for codex.py (Codex chats into notes). Run from the project root:

    CRABBOX_LOCAL=1 python3 -I -m unittest chats/test_codex.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codex  # noqa: E402

# Fake secrets, built from pieces so this file itself never holds a real-looking key.
FAKE = "Ab3dEf9hIj2LmN0pQr5tUv8xYz1"
SID = "01a146b5-2e2a-7593-a6ff-df29d3031758"


def line(t, payload, ts="2026-10-16T21:54:01.000Z"):
    return json.dumps({"timestamp": ts, "type": t, "payload": payload})


def msg(role, text, kind=None):
    kind = kind or ("output_text" if role == "assistant" else "input_text")
    return line("response_item", {"type": "message", "role": role, "content": [{"type": kind, "text": text}]})


def meta(cwd="~/projects/project-manager", source="cli", thread_source="user"):
    return line("session_meta", {"id": SID, "cwd": cwd, "source": source, "thread_source": thread_source,
                                 "timestamp": "2026-10-16T21:54:01.000Z"})


def chat(*lines, **kw):
    return [meta(**kw)] + list(lines)


TALK = [
    msg("developer", "<permissions instructions>sandbox rules</permissions instructions>"),
    msg("user", "# AGENTS.md instructions for ~\n<INSTRUCTIONS>rules</INSTRUCTIONS>"),
    msg("user", "<environment_context>\n  <cwd>~</cwd>\n</environment_context>"),
    msg("user", "Please wire the example-trader news labels; my key is sk-" + FAKE + "xx and mail me at "
        "agent-os@users.noreply.github.com when it is done. " + "More detail about the labels. " * 20),
    line("response_item", {"type": "reasoning", "summary": [{"type": "summary_text", "text": "SECRET THOUGHT"}]}),
    line("response_item", {"type": "function_call", "name": "exec", "arguments": "cat .env TOOLCALL"}),
    line("response_item", {"type": "function_call_output", "output": "API_KEY=" + FAKE + " TOOLOUT"}),
    msg("assistant", "I'll read the example-trader repo first."),
    msg("assistant", "The news labels are wired and the 624 tests pass."),
    msg("user", '<send_user_message_question_reply>\n[{"answer":"Yes, push it","question":"May I push?",'
        '"questionItemId":"x"}]\n</send_user_message_question_reply>'),
]


class Convert(unittest.TestCase):
    def note(self, lines):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "rollout-2026-10-16T17-54-01-" + SID + ".jsonl")
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return codex.build_note(p, {SID: "example-trader labels"})

    def test_only_what_was_said(self):
        name, text, red, n = self.note(chat(*TALK))
        self.assertIn("example-trader news labels", text)
        self.assertIn("**Codex**", text)
        self.assertIn("624 tests pass", text)
        for gone in ("SECRET THOUGHT", "TOOLCALL", "TOOLOUT", "AGENTS.md instructions", "environment_context",
                     "sandbox rules"):
            self.assertNotIn(gone, text)
        self.assertEqual(n, 3)   # <user>, Codex (two replies merged), <user>

    def test_redacted(self):
        name, text, red, n = self.note(chat(*TALK))
        self.assertNotIn(FAKE, text)
        self.assertNotIn("agent-os@users.noreply.github.com", text)
        self.assertIn("[email]", text)
        self.assertGreaterEqual(red, 2)

    def test_question_card_answer_is_plain(self):
        name, text, red, n = self.note(chat(*TALK))
        self.assertIn("(answered a question) May I push? -> Yes, push it", text)
        self.assertNotIn("questionItemId", text)

    def test_name_and_header(self):
        name, text, red, n = self.note(chat(*TALK))
        self.assertEqual(name, "2026-10-16-codex-project-manager-d3031758.md")
        self.assertIn("agent: codex", text)
        self.assertIn('name: "example-trader labels"', text)

    def test_helper_set_aside(self):
        name, *_ = self.note(chat(*TALK, source={"subagent": {"other": "guardian"}}, thread_source="guardian_review"))
        self.assertTrue(name.startswith("low/"))

    def test_tmp_set_aside(self):
        name, *_ = self.note(chat(*TALK, cwd="/tmp/tll-gen"))
        self.assertTrue(name.startswith("low/"))

    def test_short_chat_set_aside(self):
        name, *_ = self.note(chat(msg("user", "Reply with just OK"), msg("assistant", "OK")))
        self.assertTrue(name.startswith("low/"))

    def test_nothing_said_no_note(self):
        self.assertIsNone(self.note(chat(msg("user", "<environment_context></environment_context>"))))


class Run(unittest.TestCase):
    def test_state_and_removal(self):
        src, out = tempfile.mkdtemp(), tempfile.mkdtemp()
        p = os.path.join(src, "2026", "10", "16", "rollout-x-" + SID + ".jsonl")
        os.makedirs(os.path.dirname(p))
        with open(p, "w") as f:
            f.write("\n".join(chat(*TALK)) + "\n")
        self.assertEqual(codex.main(["--src", src, "--out", out, "--quiet"]), 0)
        notes = [n for n in os.listdir(out) if n.endswith(".md")]
        self.assertEqual(len(notes), 1)
        self.assertEqual(oct(os.stat(os.path.join(out, notes[0])).st_mode & 0o777), "0o600")
        os.remove(p)
        codex.main(["--src", src, "--out", out, "--quiet"])
        self.assertEqual([n for n in os.listdir(out) if n.endswith(".md")], [])


if __name__ == "__main__":
    unittest.main()
