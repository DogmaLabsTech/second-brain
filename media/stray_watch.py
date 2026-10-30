"""Nightly watch for stray media (2026-10-30): counts the png/mp4/gif/webm files lying in code folders per project (the
same count as `media stray`) and tells the deputy ONE line, only when a project has MORE strays than at the last run.
The last counts are kept in ~/.local/state/second-brain/media-stray-counts.json. Run by media-stray.timer.
  python3 -I media/stray_watch.py [--dry-run]     (--dry-run prints the line and changes nothing)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import media  # noqa: E402

STATE = os.path.expanduser("~/.local/state/second-brain/media-stray-counts.json")
DEPUTY = "term-mvv3rfj4-2500fc78"
AGENT_OS = os.path.expanduser("~/agent-os/bin/agent-os")


def counts():
    """{project: number of stray files}, the same numbers `media stray` prints."""
    out = {}
    for p in media.stray():
        name = media.project_of(os.path.dirname(p)) or "(other)"
        out[name] = out.get(name, 0) + 1
    return out


def load_last():
    try:
        with open(STATE) as f:
            data = json.load(f)
        return {str(k): int(v) for k, v in data.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def save(now):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(now, f, sort_keys=True)
    os.replace(tmp, STATE)


def news(now, last):
    """The projects with more strays than at the last run: {project: (before, now)}."""
    return {n: (last.get(n, 0), c) for n, c in sorted(now.items()) if c > last.get(n, 0)}


def line(new):
    top = sorted(new.items(), key=lambda kv: kv[1][0] - kv[1][1])[:5]  # the biggest rises; one line stays short
    parts = ", ".join(f"{n} +{c - b} ({c})" for n, (b, c) in top)
    more = f" and {len(new) - len(top)} more project(s)" if len(new) > len(top) else ""
    return f"New stray media in code folders: {parts}{more}. `media stray` counts them; `media add <file> --why \"...\"` files them."


def tell(text):
    r = subprocess.run([AGENT_OS, "tell", DEPUTY, text, "--from", "media-stray-watch"], capture_output=True, timeout=60)
    return r.returncode == 0


def main(argv=None):
    dry = "--dry-run" in (argv if argv is not None else sys.argv[1:])
    now, last = counts(), load_last()
    new = news(now, last)
    if new:
        text = line(new)
        if dry:
            print(text)
            return 0
        if not tell(text):
            print("media-stray-watch: could not tell the deputy; counts not saved, so tomorrow tries again", file=sys.stderr)
            return 1
        print(text)
    elif dry:
        print("no new strays")
    if not dry:
        save(now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
