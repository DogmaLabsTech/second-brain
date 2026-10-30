"""Tests for day/canvas.py (the nodeterm canvas as day pages). Run: python3 -I day/test_canvas.py. Made-up data only."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canvas  # noqa: E402

A, B, C = "term-aaaa1111-00000001", "term-bbbb2222-00000002", "term-cccc3333-00000003"


def ms(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp() * 1000)


def ev(i, at, node, **event):
    return {"id": f"e{i}", "ts": ms(at), "author": {"name": "nodeterm"}, "nodeId": node, "kind": "event", "event": event}


LOG = [
    ev(1, "2026-10-29 09:00", A, type="station-reported", **{"from": A, "to": "succeeded"}),
    ev(2, "2026-10-29 09:05", C, type="station-failed", **{"from": B, "to": "turn-errored", "title": "B"}),
    ev(3, "2026-10-29 09:10", B, type="agent-message", **{"from": A, "to": B, "title": "delivered"}),
    ev(4, "2026-10-29 09:11", B, type="agent-message", **{"from": A, "to": B, "title": "expired"}),
    ev(5, "2026-10-29 09:40", B, type="agent-message", **{"from": A, "to": B, "title": "expired"}),
    ev(6, "2026-10-29 10:00", A, type="card-moved", **{"from": "PLAN", "to": "Testing"}),
    ev(7, "2026-10-30 04:30", A, type="station-reported", **{"from": A, "to": "succeeded"}),   # still the 29th
    ev(8, "2026-10-30 05:30", B, type="station-reported", **{"from": B, "to": "failed"}),      # the 30th
]
PROJECT = {"nodes": [{"id": A, "kind": "terminal", "title": "Pixel office · MAIN (Opus)"},
                     {"id": "group-x", "kind": "group", "title": "Pixel office"}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.board = os.path.join(t, "agent-os", ".nodeterm")
        os.makedirs(self.board)
        self.old = {k: getattr(canvas, k) for k in ("DATA", "PAGES", "STATUS", "HOME")}
        canvas.DATA, canvas.PAGES = os.path.join(t, "data"), os.path.join(t, "pages")
        canvas.STATUS, canvas.HOME = os.path.join(t, "status.json"), t
        self.env = os.environ.get("BRAIN_CANVAS_BOARDS")
        os.environ["BRAIN_CANVAS_BOARDS"] = self.board
        self.put(LOG, PROJECT)

    def tearDown(self):
        for k, v in self.old.items():
            setattr(canvas, k, v)
        if self.env is None:
            os.environ.pop("BRAIN_CANVAS_BOARDS", None)
        else:
            os.environ["BRAIN_CANVAS_BOARDS"] = self.env
        self.tmp.cleanup()

    def put(self, log, project=None):
        with open(os.path.join(self.board, "board-log.jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in log)
        if project is not None:
            with open(os.path.join(self.board, "project.json"), "w") as f:
                json.dump(project, f)

    def page(self, day):
        with open(os.path.join(canvas.PAGES, day + ".md")) as f:
            return f.read()


class Run(Base):
    def test_page_per_day_from_five_to_five(self):
        canvas.run(quiet=True)
        self.assertEqual(sorted(os.listdir(canvas.PAGES)), ["2026-10-29.md", "2026-10-30.md"])
        p = self.page("2026-10-29")
        self.assertIn("Finished 2 · failed 1", p)
        self.assertIn("- 09:00 Pixel office · MAIN (Opus): finished", p)
        self.assertIn("- 09:05 agent bbbb2222: stopped with an error", p)
        self.assertIn("- 04:30 Pixel office · MAIN (Opus): finished", p)
        self.assertIn("card Pixel office · MAIN (Opus) moved PLAN -> Testing", p)
        self.assertIn("reported failed", self.page("2026-10-30"))

    def test_lost_messages_summed_not_listed(self):
        canvas.run(quiet=True)
        p = self.page("2026-10-29")
        self.assertIn("messages 1 arrived, 2 lost", p)
        self.assertIn("- 09:11-09:40 Pixel office · MAIN (Opus) -> agent bbbb2222: expired x2", p)
        self.assertNotIn("delivered", p)

    def test_rerun_adds_nothing(self):
        canvas.run(quiet=True)
        first = self.page("2026-10-29")
        os.remove(os.path.join(canvas.PAGES, "2026-10-29.md"))
        canvas.run(quiet=True)
        self.assertEqual(self.page("2026-10-29"), first, "a lost page is made again, the same")
        with open(canvas.archive_path()) as f:
            self.assertEqual(len(f.readlines()), len(LOG))
        self.put(LOG + [ev(9, "2026-10-29 11:00", A, type="station-reported", **{"from": A, "to": "succeeded"})])
        canvas.run(quiet=True)
        p = self.page("2026-10-29")
        self.assertEqual(p.count("- 09:00 Pixel office"), 1)
        self.assertIn("Finished 3", p)
        self.assertNotEqual(first, p)

    def test_trimmed_board_log_loses_nothing(self):
        canvas.run(quiet=True)
        self.put(LOG[-1:] + [ev(10, "2026-10-29 12:00", B, type="card-moved", **{"from": "A", "to": "B"})])
        canvas.run(quiet=True)
        p = self.page("2026-10-29")
        self.assertIn("09:00 Pixel office", p)
        self.assertIn("12:00 card agent bbbb2222 moved A -> B", p)

    def test_names_are_kept_after_a_node_closes(self):
        canvas.run(quiet=True)
        self.put(LOG + [ev(11, "2026-10-29 13:00", A, type="station-reported", **{"from": A, "to": "succeeded"})],
                 {"nodes": []})
        canvas.run(quiet=True)
        self.assertIn("13:00 Pixel office · MAIN (Opus): finished", self.page("2026-10-29"))

    def test_finished_notes_and_questions_from_status(self):
        with open(canvas.STATUS, "w") as f:
            json.dump({"inbox": {"events": [
                {"id": "n1", "ts": ms("2026-10-29 09:01"), "nodeId": A, "kind": "done", "title": "Finished",
                 "detail": "The job is done. " + "x" * 300},
                {"id": "n2", "ts": ms("2026-10-29 09:02"), "nodeId": A, "kind": "question", "title": "Which name?"},
                {"id": "n3", "ts": ms("2026-10-29 09:03"), "nodeId": A, "kind": "other", "title": "skip me"}]}}, f)
        canvas.run(quiet=True)
        canvas.run(quiet=True)
        p = self.page("2026-10-29")
        self.assertEqual(p.count("said when done: \"The job is done."), 1)
        self.assertIn("asked you: \"Which name?\"", p)
        self.assertNotIn("skip me", p)
        self.assertLess(max(len(x) for x in p.splitlines() if "said when done" in x), 240)

    def test_line_for_the_day_page(self):
        canvas.run(quiet=True)
        self.assertEqual(canvas.line(dt.date(2026, 10, 29)),
                         "Canvas: 2 finished, 1 failed, 2 messages lost (days/canvas/2026-10-29.md)")
        self.assertEqual(canvas.line(dt.date(2026, 10, 1)), "")

    def test_broken_lines_are_skipped(self):
        with open(os.path.join(self.board, "board-log.jsonl"), "a") as f:
            f.write("not json\n[1]\n" + json.dumps({"id": "x", "ts": "soon", "event": {}}) + "\n")
        self.assertEqual(canvas.run(quiet=True), 0)
        self.assertIn("Finished 2", self.page("2026-10-29"))


class OddInput(Base):
    """The checker's cases (2026-10-30): odd lines never stop the import or lose a day."""

    def test_message_without_a_title(self):
        self.put(LOG + [{"id": "x", "ts": ms("2026-10-29 11:00"), "nodeId": B,
                         "event": {"type": "agent-message", "from": A, "to": B}}])
        canvas.run(quiet=True)
        self.assertIn("09:11-11:00 Pixel office · MAIN (Opus) -> agent bbbb2222: expired x2, unknown", self.page("2026-10-29"))

    def test_impossible_times_are_skipped(self):
        self.put(LOG + [{"id": "big", "ts": 1e100, "event": {"type": "card-moved"}},
                        {"id": "nan", "ts": float("nan"), "event": {"type": "card-moved"}},
                        {"id": "yes", "ts": True, "event": {"type": "card-moved"}}])
        self.assertEqual(canvas.run(quiet=True), 0)
        self.assertIn("Finished 2", self.page("2026-10-29"))

    def test_odd_status_and_project_files(self):
        for status in ({"inbox": {"events": [{"id": "n1", "ts": ms("2026-10-29 09:00"), "kind": ["done"]}]}},
                       {"inbox": [1]}, [], {"inbox": {"events": {"a": 1}}}, {"inbox": {"events": [{"id": [1]}]}}):
            with open(canvas.STATUS, "w") as f:
                json.dump(status, f)
            self.put(LOG, [1, 2])
            self.assertEqual(canvas.run(quiet=True), 0)
        self.assertIn("Finished 2", self.page("2026-10-29"))

    def test_a_page_that_failed_is_made_next_run(self):
        real = canvas.page
        canvas.page = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            canvas.run(quiet=True)
        finally:
            canvas.page = real
        self.assertFalse(os.path.exists(os.path.join(canvas.PAGES, "2026-10-29.md")))
        canvas.run(quiet=True)
        self.assertIn("Finished 2", self.page("2026-10-29"))

    def test_duplicate_archive_lines_count_once(self):
        canvas.run(quiet=True)
        with open(canvas.archive_path()) as f:
            lines = f.readlines()
        with open(canvas.archive_path(), "a") as f:
            f.writelines(lines)   # what two runs racing without the lock would have left
        self.put(LOG + [ev(12, "2026-10-29 14:00", A, type="card-moved", **{"from": "a", "to": "b"})])
        canvas.run(quiet=True)
        self.assertIn("Finished 2 · failed 1", self.page("2026-10-29"))

    def test_runs_take_turns(self):
        import threading
        out = []
        threads = [threading.Thread(target=lambda: out.append(canvas.run(quiet=True))) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with open(canvas.archive_path()) as f:
            self.assertEqual(len(f.readlines()), len(LOG))


class Backlog(Base):
    def test_old_names_from_chat_logs_and_job_notes(self):
        chat = os.path.join(canvas.HOME, ".claude", "projects", "-x", "s.jsonl")
        os.makedirs(os.path.dirname(chat))
        with open(chat, "w") as f:
            f.write(json.dumps({"t": f'nodeterm.sh rename --node {B} --title "Testing · builder (Sonnet)"'}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"t": f"{C} [terminal] OVERSEER 3 @ -144,-2256 840x720"}) + "\n")
        note = os.path.join(canvas.HOME, "agent-os", "jobs", "20261029-0900-one-brain", "progress.md")
        os.makedirs(os.path.dirname(note))
        with open(note, "w") as f:
            f.write(f"- 08:57 fresh core builder: {C}\n- report to MAIN 3 (`{A}`)\n")
        canvas.run(quiet=True, backlog=True)
        names = canvas.load_names()
        self.assertEqual(names[B], "Testing · builder (Sonnet)")
        self.assertEqual(names[C], "OVERSEER 3", "a chat log wins over a job note")
        self.assertEqual(names[A], "Pixel office · MAIN (Opus)", "the canvas wins over both")
        self.assertIn("Testing · builder (Sonnet): stopped with an error", self.page("2026-10-29"))

    def test_job_note_names_carry_the_job(self):
        note = os.path.join(canvas.HOME, "agent-os", "jobs", "20261029-0900-one-brain", "progress.md")
        os.makedirs(os.path.dirname(note))
        with open(note, "w") as f:
            f.write(f"- 08:57 fresh core builder started: {B}\n")
        self.assertEqual(canvas.job_names()[B], "fresh core builder (one-brain)")


class Cli(Base):
    def test_line_command_rejects_a_bad_date(self):
        self.assertEqual(canvas.main(["line", "yesterday"]), 2)
        self.assertEqual(canvas.main(["nope"]), 2)


if __name__ == "__main__":
    unittest.main()
