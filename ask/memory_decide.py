"""The memory system's choices, asked of the decider (agent memory job 9, phase A; <user>'s yes 2026-10-28).

The start hook, the librarian and the flags used simple word rules for five choices. Each now asks decider (the second decider first;
the local decider once <user> has switched a task on), and keeps today's word rule as the fallback: every function here returns None
when the decider is not sure, is off, is slow, or anything at all goes wrong, and the caller then uses its old rule.

  real_task(prompt)                  decider task memory-real-task       True / False   the first prompt is a real task
  same_note(title, body, summary)    memory-same-note                    True / False   the draft says what the note says
  relation(newer, older)             memory-conflict                     "agrees" | "conflicts" | "unrelated"
  kind_of(text)                      memory-kind                         "rule" | "lesson"
  lesson_worth(title, body)          memory-lesson-worth                 True / False   the job is worth a lesson

Switch: BRAIN_MEMORY_DECIDER=on|off (default on). Off: nothing here asks anything and every caller uses its word rule.
Private text goes to the second decider for these five tasks only (decider tasks.THE SECOND DECIDER_PRIVATE_ALLOWED, <user> 2026-10-28: "the five memory
tasks may send private text to the second decider; nothing else changes"); decider removes secrets, emails and private names first and
sends nothing when it cannot (then the answer is None). Each call is one line in memory-decider.jsonl in the state
folder (task, answer, backend, milliseconds: never the text). decider's own log holds the caller and a hash.
decider lives in ~/projects/decider (BRAIN_DECIDER_PATH moves it); `decide` never raises. Tests set
`decide_fn` to a fake: they never call the real the second decider. Standard library only here.
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True

ENV = "BRAIN_MEMORY_DECIDER"
TASKS = {"memory-real-task": "real_task", "memory-same-note": "same_or_new", "memory-conflict": "relation",
         "memory-kind": "kind", "memory-lesson-worth": "worth"}
decide_fn = None       # tests put a fake here; None = decider's own `decide`
_loaded = []


def enabled():
    return os.environ.get(ENV, "on").strip().lower() not in ("off", "0", "no", "false")


def state_dir():
    return os.path.expanduser(os.environ.get("BRAIN_HOOK_STATE") or "~/.local/state/second-brain")


def _decide():
    if decide_fn:
        return decide_fn
    if not _loaded:
        path = os.path.expanduser(os.environ.get("BRAIN_DECIDER_PATH") or "~/projects/decider")
        if path not in sys.path:
            sys.path.insert(0, path)
        from decider import decide
        _loaded.append(decide)
    return _loaded[0]


def note(event, **fields):
    """One line in memory-decider.jsonl (never any note text). A failure to write is ignored."""
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(os.path.join(state_dir(), "memory-decider.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(fields, event=event, when=time.strftime("%Y-%m-%dT%H:%M:%S"))) + "\n")
    except OSError:
        pass


def ask(task, state, seconds=None):
    """The choice text ("yes"/"no" or the option) the decider is sure of, else None. Never raises."""
    if not enabled() or not isinstance(state, str) or not state.strip():
        return None
    try:
        res = _decide()(task, state, timeout=seconds, caller=task)
        answer = (res.get("answers") or {}).get(TASKS[task]) if res.get("sure") else None
        choice = answer.get("choice") if isinstance(answer, dict) else None
        note("ask", task=task, choice=choice, sure=bool(res.get("sure")), backend=res.get("backend"), ms=res.get("ms"),
             **({} if res.get("sure") else {"reason": str(res.get("reason") or "")[:120]}))
        return choice if isinstance(choice, str) else None
    except Exception as why:  # noqa: BLE001  the memory system never fails because of the decider
        note("ask", task=task, choice=None, sure=False, reason="error: %s" % type(why).__name__)
        return None


def same_state(title, body, summary):
    return "NEW LESSON:\n%s\n%s\n\nKEPT NOTE:\n%s" % (title, body, summary)


def relation_state(newer, older):
    return "NEWER NOTE:\n%s\n\nOLDER NOTE:\n%s" % (newer, older)


def worth_state(title, body):
    return "JOB SIGNALS AND RECORDS:\n%s\n\n%s" % (title, body)


def _yes(choice):
    return None if choice is None else choice == "yes"


def real_task(prompt, seconds=None):
    return _yes(ask("memory-real-task", prompt, seconds))


def same_note(title, body, summary, seconds=None):
    got = ask("memory-same-note", same_state(title, body, summary), seconds)
    return None if got is None else got == "same"


def relation(newer, older, seconds=None):
    got = ask("memory-conflict", relation_state(newer, older), seconds)
    return got if got in ("agrees", "conflicts", "unrelated") else None


def kind_of(text, seconds=None):
    got = ask("memory-kind", text, seconds)
    return got if got in ("rule", "lesson") else None


def lesson_worth(title, body, seconds=None):
    return _yes(ask("memory-lesson-worth", worth_state(title, body), seconds))
