import os, json, sys, numpy as np, pathlib
P = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/share/second-brain/viz")) / "data.js"
raw = P.read_text(); B = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";")); D = B["docs"]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from vectors import index, pieces   # the shared index reader
c = index(); byhash = pieces(c)
vec = {}
for did, h in c.execute("select id,hash from documents where active=1"):
    if h in byhash: v = np.mean(byhash[h], axis=0); vec[did] = v / (np.linalg.norm(v) + 1e-9)
for d in D:
    v = vec[d["id"]]; d["ns"] = [round(float(v @ vec[D[j]["id"]]), 3) for j in d["nb"]]
P.write_text("window.BRAIN=" + json.dumps(B, separators=(",", ":")) + ";")
print("ok", D[0]["ns"], min(min(d["ns"]) for d in D))
