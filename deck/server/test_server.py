"""Tests for viz/server/server.py: it serves the Deck from web/, the private data.js from outside git, and keeps the Host check.
Starts its own server on DECK_TEST_PORT (8796), never the real 8765. The /note check needs this computer's search index
(run with CRABBOX_LOCAL=1); without the index it is skipped."""
import http.client
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIZ = HERE.parent
PORT = int(os.environ.get("DECK_TEST_PORT", "8796"))
INDEX = Path("~/.cache/qmd/index.sqlite").expanduser()


def get(path, host=f"127.0.0.1:{PORT}"):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    c.request("GET", path, headers={"Host": host})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, dict(r.getheaders()), body


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:   # another server on the port would answer instead of ours
            get("/deck.html")
            raise RuntimeError(f"port {PORT} is busy: stop that server or set DECK_TEST_PORT")
        except OSError:
            pass
        cls.tmp = Path(tempfile.mkdtemp())
        (cls.tmp / "data.js").write_text("window.BRAIN={docs:[]};/*from-outside*/")
        env = dict(os.environ, DECK_PORT=str(PORT), DECK_DATA=str(cls.tmp / "data.js"), DECK_TALK_LOG=str(cls.tmp / "talk.jsonl"),
                   DECK_ASKS_LOG=str(cls.tmp / "asks.jsonl"), DECK_SEARCHES_LOG=str(cls.tmp / "searches.jsonl"))
        cls.srv = subprocess.Popen([sys.executable, "-I", str(HERE / "server.py")], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                get("/deck.html")
                return
            except OSError:
                time.sleep(0.1)
        cls.srv.kill()
        raise RuntimeError("test server did not start: " + cls.srv.stderr.read().decode()[-500:])

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(10)
        subprocess.run(["rm", "-rf", str(cls.tmp)], check=True, timeout=30)

    def test_deck_page_is_served_from_web_with_the_live_token(self):
        code, head, body = get("/deck.html")
        self.assertEqual(code, 200)
        self.assertIn(b"<title>", body)
        self.assertNotIn(b'<meta name="deck-live" content="">', body)
        self.assertIn(b'<meta name="deck-live" content="', body)
        self.assertEqual(head.get("Cache-Control"), "no-store")

    def test_old_address_and_root_lead_to_the_deck(self):
        for path in ("/", "/hud/deck.html"):
            code, head, _ = get(path)
            self.assertEqual((code, head.get("Location")), (302, "/deck.html"))

    def test_data_comes_from_outside_the_repo(self):
        code, _, body = get("/data.js")
        self.assertEqual(code, 200)
        self.assertIn(b"/*from-outside*/", body)

    def test_page_files_load(self):
        for path in ("/common.js", "/hud.js", "/hud.css", "/skins/index.js", "/vendor/three.module.min.js"):
            self.assertEqual(get(path)[0], 200, path)

    def test_wrong_host_is_refused(self):
        for path in ("/deck.html", "/data.js", "/note?id=2347"):
            self.assertEqual(get(path, host="evil.example:8796")[0], 403, path)

    def test_no_path_outside_web(self):
        code, _, body = get("/../server/server.py")
        self.assertNotIn(b"LIVE_TOKEN", body)

    @unittest.skipUnless(INDEX.exists(), "needs this computer's search index (CRABBOX_LOCAL=1)")
    def test_note_reads_a_note(self):
        code, _, body = get("/note?id=2347")
        self.assertEqual(code, 200)
        self.assertIn(b'"title"', body)
        self.assertIn(b'"text"', body)


class Repo(unittest.TestCase):
    def test_private_files_are_ignored(self):
        for f in ("viz/data.js", "viz/web/data.js", "viz/talk-log.jsonl", "viz/server/talk-log.jsonl"):
            r = subprocess.run(["git", "-C", str(VIZ), "check-ignore", "-q", f.removeprefix("viz/")], timeout=30)
            self.assertEqual(r.returncode, 0, f + " is not git-ignored")

    def test_page_has_no_paths_out_of_web(self):
        for f in (VIZ / "web").rglob("*.html"):
            self.assertNotIn('src="../', f.read_text(), f.name)


if __name__ == "__main__":
    unittest.main()
