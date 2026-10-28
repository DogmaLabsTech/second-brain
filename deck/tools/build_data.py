import os, sqlite3, struct, json, re, sys, numpy as np, pathlib, time
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/share/second-brain/viz"))
c = sqlite3.connect("file:" + os.path.expanduser("~/.cache/qmd/index.sqlite") + "?mode=ro", uri=True)
DIM = 768
chunks = {r: np.frombuffer(b, dtype="<f4").reshape(-1, DIM) for r, b in c.execute("select rowid,vectors from vectors_vec_vector_chunks00")}
byhash = {}
for id_, ch, off in c.execute("select id,chunk_id,chunk_offset from vectors_vec_rowids"):
    h, seq = id_.rsplit("_", 1)
    if ch in chunks and off < len(chunks[ch]):
        byhash.setdefault(h, []).append(chunks[ch][off])
docs = c.execute("select id,collection,path,title,hash,modified_at from documents where active=1").fetchall()
rows, vecs = [], []
for id_, col, path, title, h, mod in docs:
    if h not in byhash: continue
    v = np.mean(byhash[h], axis=0); v /= (np.linalg.norm(v) + 1e-9)
    rows.append(dict(id=id_, c=col, p=path, t=title, d=mod[:10], n=len(byhash[h]))); vecs.append(v)
X = np.array(vecs, dtype=np.float64); n = len(X)
print("docs with fingerprints:", n)
# neighbours (cosine) for "connections"
S = X @ X.T; np.fill_diagonal(S, -1)
nb = np.argsort(-S, axis=1)[:, :6]
for i, r in enumerate(rows): r["nb"] = [int(j) for j in nb[i]]
# PCA to 40 dims, then a small t-SNE (numpy)
Xc = X - X.mean(0); U, s, Vt = np.linalg.svd(Xc, full_matrices=False); P = Xc @ Vt[:40].T
D = ((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)
def affinities(D, perp=30.0):
    Pm = np.zeros_like(D); logU = np.log(perp)
    for i in range(len(D)):
        lo, hi, beta = 0.0, np.inf, 1.0
        d = np.delete(D[i], i)
        for _ in range(40):
            p = np.exp(-d * beta); sp = p.sum() + 1e-12
            H = np.log(sp) + beta * (d * p).sum() / sp
            if abs(H - logU) < 1e-4: break
            if H > logU: lo = beta; beta = beta * 2 if hi == np.inf else (beta + hi) / 2
            else: hi = beta; beta = (beta + lo) / 2
        p = p / sp; Pm[i, np.arange(len(D)) != i] = p
    Pm = (Pm + Pm.T) / (2 * len(D)); return np.maximum(Pm, 1e-12)
def tsne(Pm, dims, iters=600, seed=1):
    rng = np.random.default_rng(seed); Y = rng.normal(0, 1e-2, (len(Pm), dims)); V = np.zeros_like(Y); lr = 200.0
    for it in range(iters):
        sq = (Y ** 2).sum(1); d2 = sq[:, None] + sq[None, :] - 2 * Y @ Y.T
        Q = 1 / (1 + d2); np.fill_diagonal(Q, 0); Qn = np.maximum(Q / Q.sum(), 1e-12)
        ex = 12.0 if it < 100 else 1.0
        W = (ex * Pm - Qn) * Q
        G = 4 * (W.sum(1)[:, None] * Y - W @ Y)
        V = (0.5 if it < 100 else 0.8) * V - lr * G; Y = Y + V; Y -= Y.mean(0)
    return Y
t = time.time(); Pm = affinities(D); print("aff", round(time.time() - t))
Y3 = tsne(Pm, 3); print("3d", round(time.time() - t)); Y2 = tsne(Pm, 2, seed=2); print("2d", round(time.time() - t))
def norm(Y):
    Y = Y / np.percentile(np.abs(Y), 98); return np.clip(Y, -1.3, 1.3)
Y3, Y2 = norm(Y3), norm(Y2)
for i, r in enumerate(rows):
    r["xyz"] = [round(float(v), 4) for v in Y3[i]]; r["uv"] = [round(float(v), 4) for v in Y2[i]]
# scores
scores = []
for l in open(pathlib.Path(__file__).resolve().parents[2] / "eval" / "scores.tsv").read().splitlines()[1:]:
    f = l.split("\t"); m1 = re.match(r"(\d+)/(\d+)", f[1]); m3 = re.match(r"(\d+)/(\d+)", f[2])
    if m1 and m3: scores.append(dict(when=f[0], top1=int(m1[1]), top3=int(m3[1]), of=int(m3[2]), note=f[-1][:80]))
# canned "ask" demos via keyword search (lex) so the lighting-up can be shown
asks = {}
for q in ["testbox handheld tests", "top bar", "weather", "voice island", "backup", "hdd offload"]:
    ids = [r[0] for r in c.execute("select rowid from documents_fts where documents_fts match ? order by bm25(documents_fts) limit 14", ('"' + q + '"',))]
    asks[q] = ids
OUT.mkdir(parents=True, exist_ok=True); (OUT / "data.js").write_text("window.BRAIN=" + json.dumps(dict(docs=rows, scores=scores, asks=asks), separators=(",", ":")) + ";")
print("wrote", (OUT / "data.js").stat().st_size // 1024, "KB")
