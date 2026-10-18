// Add the Codex notes' vectors made on the test machine (index/codex-testbox.sh) to the live qmd index here.
// node merge_vectors.mjs <testbox-index.sqlite> <live-index.sqlite> [collection]
// Only for notes of that collection that are in the live index and have no vectors yet, and only when the test machine
// made every chunk of the note with the same model and fingerprint. Uses qmd's own sqlite and sqlite-vec.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import path from "node:path";

const [rogPath, livePath, collection = "codex"] = process.argv.slice(2);
const qmdDir = path.join(execSync("npm root -g").toString().trim(), "@tobilu", "qmd");
const require = createRequire(path.join(qmdDir, "package.json"));
const Database = require("better-sqlite3");
const { getLoadablePath } = require("sqlite-vec");

const open = (p, readonly) => {
  const db = new Database(p, { readonly, timeout: 15000 });
  db.loadExtension(getLoadablePath());
  return db;
};
const testbox = open(rogPath, true), live = open(livePath, false);
// A fresh index has no vector table until its first embed: make it the same as the test machine's.
const table = "SELECT sql FROM sqlite_master WHERE name = 'vectors_vec'";
if (!live.prepare(table).get()) live.exec(testbox.prepare(table).get().sql);

const need = live.prepare(`SELECT DISTINCT d.hash FROM documents d WHERE d.collection = ? AND d.active = 1
  AND NOT EXISTS (SELECT 1 FROM content_vectors cv WHERE cv.hash = d.hash)`).all(collection).map(r => r.hash);
const rows = testbox.prepare(`SELECT hash, seq, pos, model, embed_fingerprint, total_chunks, embedded_at
  FROM content_vectors WHERE hash = ? ORDER BY seq`);
const vec = testbox.prepare(`SELECT embedding FROM vectors_vec WHERE hash_seq = ?`);
// The model and fingerprint the live index already uses (the brain's other notes), so search treats these the same.
const liveModel = live.prepare(`SELECT model, embed_fingerprint FROM content_vectors
  GROUP BY model, embed_fingerprint ORDER BY COUNT(*) DESC LIMIT 1`).get();

const addCv = live.prepare(`INSERT OR REPLACE INTO content_vectors (hash, seq, pos, model, embed_fingerprint,
  total_chunks, embedded_at) VALUES (?, ?, ?, ?, ?, ?, ?)`);
const delVec = live.prepare(`DELETE FROM vectors_vec WHERE hash_seq = ?`);
const addVec = live.prepare(`INSERT INTO vectors_vec (hash_seq, embedding) VALUES (?, ?)`);

let added = 0, missing = 0, skipped = 0;
const tx = live.transaction(() => {
  for (const hash of need) {
    const rs = rows.all(hash);
    if (!rs.length) { missing++; continue; }
    const ok = rs.length === rs[0].total_chunks && (!liveModel || rs.every(r => r.model === liveModel.model
      && r.embed_fingerprint === liveModel.embed_fingerprint));
    const vs = rs.map(r => vec.get(`${hash}_${r.seq}`));
    if (!ok || vs.some(v => !v)) { skipped++; continue; }
    rs.forEach((r, i) => {
      addCv.run(r.hash, r.seq, r.pos, r.model, r.embed_fingerprint, r.total_chunks, r.embedded_at);
      delVec.run(`${hash}_${r.seq}`);
      addVec.run(`${hash}_${r.seq}`, vs[i].embedding);
    });
    added++;
  }
});
tx();
console.log(`codex vectors: ${need.length} notes needed them, ${added} added from the test machine, ${missing} not made yet, ${skipped} skipped (other model or incomplete)`);
testbox.close(); live.close();
