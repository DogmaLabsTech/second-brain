"""The details test (router upgrade 3): does the job get the right details (which app, file, device, action,
project) from how <user> really talks? Word rules alone against word rules + the local writer (details.py).

  python3 -I jobs/test/details_test.py make          details-test.tsv from details-canonical.tsv: Haiku says each
                                                    plain command the messy way people talk (done once, kept)
  python3 -I jobs/test/details_test.py run [--save]  score both ways; --save writes results.json and, if the
                                                    writer gets more right and no more wrong jobs that run
                                                    without asking first, switches it on (config/details.json)

details-test.tsv: job<TAB>what was said<TAB>the plain command it means ("-": no job should be made). The
expected details are what the word rules build from the plain command today, so files that change (the latest
screenshot) are compared fairly. <user>'s real island asks are at the end, marked "# real".
Right = same job and the same details; wrong = a job with other details (worse than none); none = no job.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.dirname(HERE)
sys.path.insert(0, JOBS)
import details  # noqa: E402
import jobs  # noqa: E402

KEYS = {"open-app": ("app", "monitor"), "open-file": ("path",), "open-note": ("path",), "send-file": ("device", "paths"),
        "desktop": ("action", "value"), "start-claude": ("project",), "tv": ("action",), "music": ("action",)}


def tsv(name):
    with open(os.path.join(HERE, name)) as f:
        return [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("#")]


def make():
    sys.path.insert(0, os.path.join(os.path.dirname(JOBS), "deciders", "tools"))
    import haiku
    rows = tsv("details-canonical.tsv")
    out = []
    for i in range(0, len(rows), 20):
        chunk = rows[i:i + 20]
        listed = "\n".join("%d. %s" % (k + 1, t) for k, (_, t) in enumerate(chunk))
        said = haiku.ask_json(
            "<user> talks to his desktop assistant by voice. For each plain command below, write how he might really "
            "say it: casual, indirect or slangy wording, filler words, different word order, and sometimes a "
            "speech-to-text slip (\"lap top\", \"tavern light\", \"example-game\", \"rogue\" for test machine). Keep exactly the "
            "same meaning and the same names, numbers, screens and devices. Mix the styles; not every one needs "
            "filler. Commands:\n" + listed + "\nReturn a JSON array with one string per command, in order.",
            "You write realistic practice data. Reply with a JSON array of strings only.")
        if len(said) != len(chunk):
            raise SystemExit("haiku returned %d for %d" % (len(said), len(chunk)))
        out += [(j, " ".join(str(s).split()), t) for (j, t), s in zip(chunk, said)]
    with open(os.path.join(HERE, "details-test.tsv"), "w") as f:
        f.write("# Made by details_test.py make (Haiku said each plain command the messy way), 2026-10-15.\n")
        f.writelines("%s\t%s\t%s\n" % r for r in out)
        f.write(REAL)
    print(len(out), "written")


# <user>'s real island asks (asks.jsonl, from: island, 2026-10-15) with the details they should give.
REAL = """# real
open-file	open my downloads folder	open my downloads folder
open-app	Open Spotify.	open spotify
open-app	Can you open up VS Code on my second monitor?	open visual studio code on my other screen
open-app	Can you open up Chrome?	open google chrome
send-file	Can you send the latest example-game files to the laptop?	send the latest example-game files to the laptop
send-file	Send a screenshot to the laptop.	send the latest screenshot to the laptop
desktop	Can you turn my brightness up to eighty percent?	-
send-file	I'm gonna send it over to the laptop. I don't want it if the laptop	-
"""


def key(r):
    j = r.get("job") if r.get("kind") == "job" else None
    if not j:
        return None
    a = j.get("args", {})
    vals = []
    for k in KEYS.get(j["id"], ()):
        v = a.get(k)
        if isinstance(v, dict) and "message" in v:   # a reminder: the minutes, and its words in any case
            v = {**v, "message": str(v["message"]).lower().strip(" .")}
        vals.append(sorted(v) if isinstance(v, list) else v or None)
    return json.dumps([j["id"]] + vals, sort_keys=True)


def run(save=False):
    rows = tsv("details-test.tsv")
    res = {"rules": {"right": 0, "wrong": 0, "none": 0, "ms": []}, "writer": {"right": 0, "wrong": 0, "none": 0, "ms": [],
                                                                          "local_ms": [], "used": 0}}
    lines = []
    real = {"rules": 0, "writer": 0, "n": 0}
    for i, (job, said, plain) in enumerate(rows):
        want = None if plain == "-" else key(jobs.build(job, plain))
        t0 = time.monotonic()
        a = jobs.build(job, said)
        res["rules"]["ms"].append((time.monotonic() - t0) * 1000)
        t0 = time.monotonic()
        b = jobs.build_with_details(job, said, fill=details.fill)
        ms = (time.monotonic() - t0) * 1000
        res["writer"]["ms"].append(ms)
        if b.get("details") == "local":
            res["writer"]["used"] += 1
        if b.get("details") in ("local", "none"):
            res["writer"]["local_ms"].append(ms)
        is_real = i >= len(rows) - 8
        for name, r in (("rules", a), ("writer", b)):
            got = key(r)
            v = "right" if got == want else "none" if got is None else "wrong"
            res[name][v] += 1
            if v == "wrong" and not r["job"].get("needs_confirm"):
                res[name]["wrong_unasked"] = res[name].get("wrong_unasked", 0) + 1   # ran without a Yes / No
            if is_real and v == "right":
                real[name] += 1
        real["n"] += is_real
        lines.append("%-5s %-5s %-12s %s%s" % ("ok" if key(a) == want else "-", "ok" if key(b) == want else
                                               ("WRONG" if key(b) else "-"), job, said[:70],
                                               "  [writer: %s]" % json.dumps(b.get("form")) if b.get("form") else ""))
    for name in res:
        ms = sorted(res[name].pop("ms"))
        res[name]["ms_middle"] = round(ms[len(ms) // 2], 1)
        lm = sorted(res[name].pop("local_ms", []))
        if lm:
            res[name]["writer_ms_middle"] = round(lm[len(lm) // 2])
            res[name]["writer_ms_slowest"] = round(lm[-1])
    res["n"], res["real"], res["when"] = len(rows), real, time.strftime("%Y-%m-%d %H:%M")
    print("\n".join(lines))
    print(json.dumps(res, indent=1))
    if save:
        with open(os.path.join(HERE, "results.json"), "w") as f:
            json.dump(res, f, indent=1)
        # More right, and no more wrong jobs that would run without asking (a wrong send still shows its card).
        better = res["writer"]["right"] > res["rules"]["right"] and \
            res["writer"].get("wrong_unasked", 0) <= res["rules"].get("wrong_unasked", 0)
        with open(details.CONFIG, "w") as f:
            json.dump({"on": better, "why": "details test %s: writer %d right %d wrong, word rules %d right %d wrong"
                       % (res["when"], res["writer"]["right"], res["writer"]["wrong"], res["rules"]["right"],
                          res["rules"]["wrong"])}, f, indent=1)
            f.write("\n")
        print("switched", "on" if better else "off")
    return res


if __name__ == "__main__":
    if sys.argv[1:2] == ["make"]:
        make()
    elif sys.argv[1:2] == ["run"]:
        os.environ["BRAIN_DETAILS"] = "1"
        run("--save" in sys.argv)
    else:
        print(__doc__)
