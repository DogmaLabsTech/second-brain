"""brain search: the same notes `brain ask` would use (newer-first), as "path — snippet" lines."""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask  # noqa: E402

for h in ask.search(" ".join(sys.argv[1:])):
    print(f"{ask.short_path(h['path'])} — {h['snippet'][:160]}")
