import os, sqlite3, json, sys, numpy as np, pathlib
P = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/share/second-brain/viz")) / "data.js"
raw = P.read_text(); B = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";")); D = B["docs"]
c = sqlite3.connect("file:" + os.path.expanduser("~/.cache/qmd/index.sqlite") + "?mode=ro", uri=True); DIM = 768
chunks = {r: np.frombuffer(b, dtype="<f4").reshape(-1, DIM) for r, b in c.execute("select rowid,vectors from vectors_vec_vector_chunks00")}
byhash = {}
for id_, ch, off in c.execute("select id,chunk_id,chunk_offset from vectors_vec_rowids"):
    h, _ = id_.rsplit("_", 1)
    if ch in chunks and off < len(chunks[ch]): byhash.setdefault(h, []).append(chunks[ch][off])
vec = {}
for did, h in c.execute("select id,hash from documents where active=1"):
    if h in byhash: v = np.mean(byhash[h], axis=0); vec[did] = v / (np.linalg.norm(v) + 1e-9)
for d in D:
    v = vec[d["id"]]; d["ns"] = [round(float(v @ vec[D[j]["id"]]), 3) for j in d["nb"]]
P.write_text("window.BRAIN=" + json.dumps(B, separators=(",", ":")) + ";")
print("ok", D[0]["ns"], min(min(d["ns"]) for d in D))
