"""What both map makers read from the search index (read-only, DECK_INDEX overrides it): one fingerprint per note piece, by note hash."""
import os, sqlite3, numpy as np
DIM = 768
def index():
    return sqlite3.connect("file:" + (os.environ.get("DECK_INDEX") or os.path.expanduser("~/.cache/qmd/index.sqlite")) + "?mode=ro", uri=True)
def pieces(c):
    """{note hash: [one 768-number vector per piece]}"""
    chunks = {r: np.frombuffer(b, dtype="<f4").reshape(-1, DIM) for r, b in c.execute("select rowid,vectors from vectors_vec_vector_chunks00")}
    byhash = {}
    for id_, ch, off in c.execute("select id,chunk_id,chunk_offset from vectors_vec_rowids"):
        h, _ = id_.rsplit("_", 1)
        if ch in chunks and off < len(chunks[ch]): byhash.setdefault(h, []).append(chunks[ch][off])
    return byhash
