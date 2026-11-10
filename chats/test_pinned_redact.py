"""What redact.redact gives for a wide set of texts (every kind of secret, the near misses it must keep, and
mixes), taken before its long body was split into steps, so the split changes nothing:
python3 -I chats/test_pinned_redact.py"""
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "test_pinned_redact.gold")
sys.path.insert(0, HERE)
from redact import redact  # noqa: E402

# Fake secrets, built from pieces so this file itself never holds a real-looking key.
F = "Ab3dEf9hIj2LmN0pQr5tUv8xYz1"
H = "0123456789abcdef" * 3
TEXTS = [
    "", "plain words only", "my key is sk-" + F + "xx ok", "export it: sk-ant-api03-" + F + "-" + F,
    "token ghp_" + F + "abcdefghij", "gho_" + F + "abcdefgh and ghs_" + F + "abcdefgh", "github_pat_11ABCDEFG0" + F,
    "glpat-" + F, "aws AKIAIOSFODNN7EXAMPLE here and ASIAIOSFODNN7EXAMPLE", "xoxb-1234567890-abcdefghij xapp-1-A1B2C3D4E5F6",
    "tskey-auth-kABCDEFG1234", "AIza" + F + "abcdefg", "hf_" + F + "abcdefg", "npm_" + F + "abcdefg",
    "pk_live_" + F + " sk_test_" + F, "bot 123456789:" + F + "abcdefghi", "eyJhbGciOi" + F + ".eyJzdWIiOi" + F + ".sig_" + F,
    "eyJ" + F + "abcdefghijk", "hook https://hooks.slack.com/services/T000/B000/XXXXXXXX",
    "https://discord.com/api/webhooks/123456/abc_DEF-123", "https://discordapp.com/api/webhooks/123456/abc_DEF-123",
    "Authorization: Bearer abc.DEF_123-xyz789", "Bearer short", "Bearer " + F + F, "Basic dXNlcjpwYXNzMTIz", "Token abc123def456",
    "Bearer onlyletters", "db postgres://user:p4ssw0rd@host:5432/db", "https://user:secret@example.com/x",
    "http://example.com/no-creds", "api_key=" + F, "API_KEY = '" + F + "'", "password: hunter2hunter2", "password: true", "secret=${SECRET}",
    "token=<token>", "auth=[redacted]", "key: some prose here", "Key: something longer than eight but with 1 digit", "cookie: sessionabc123xyz",
    "mykey=abc", "session_id=abcd1234", "private: ~/keys/id", "passphrase: /home/me/pass1", "secret: http://x/1234567",
    "export SOME_VALUE=abcdefghij123", "  FOO_BAR=\"longervalue123\"", "BAZ_QUX=/usr/local/bin/x", "run X_Y_Z=abcdefghi1 now",
    "PORT=4197", "DATABASE_URL=http://localhost:5432/db", "API_URL=http://127.0.0.1:8080/x", "HOME_DIR=~/stuff/here", "TOKEN_X=$VAR_LONG_NAME",
    "pairing code 123-456 for the tv", "pair with 123456 now", "123 456 pairing", "paired 1234567 ok", "pair at 10.0.0.1:123456",
    "commit " + H[:40], "sha256: " + H, "git show " + H[:40], "the hash " + H + " alone", "a hex " + H + H, "id " + H[:32],
    "rev abcdef1234567890abcdef1234567890abcdef12 and more", "tree " + H[:40] + " blob " + H[:40],
    "random " + F + F + "ZZ", "path ~/projects/some-long-project-name/file.md", "slug some-very-long-slug-name-with-many-words-in-it",
    "a_long_snake_case_identifier_with_many_words", "LongCamelCaseIdentifierWithManyWordsInsideItAndMore", "digits " + "1234567890" * 4,
    "mixed Ab3dEf9hIj2LmN0pQr5tUv8xYz1/Ab3dEf9hIj2LmN0pQr5tUv8xYz1.suffix", "word " * 5 + F + "Zz9 end",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIabc123\n-----END RSA PRIVATE KEY----- after", "-----BEGIN PRIVATE KEY-----\nnever ends",
    "mail agent-os@users.noreply.github.com and agent-os@users.noreply.github.com and agent-os@users.noreply.github.com in a table", "mail someone@else.com stays",
    "multi\nline PASSWORD=" + F + "\nnext line TOKEN: " + F + "\nok",
    "mix sk-" + F + "xx and AKIAIOSFODNN7EXAMPLE and api_key=" + F + " and 123-456 pairing and " + H,
    "tailscale up --authkey tskey-auth-kABCDEFG1234-xyz", "curl -H 'Authorization: Bearer " + F + "' https://x", "ssh://git:pw12345@host/repo.git",
    "unicode ключ=" + F, "Ab3dEf9hIj2LmN0pQr5tUv8xYz1Ab3dEf9hIj2LmN0pQr5tUv8xYz1=", "x" * 40, "A" * 33 + "b",
]


def collect():
    # the gold file was made with this one address listed as the owner's own
    with mock.patch.dict(os.environ, {"BRAIN_OWN_EMAILS": "agent-os@users.noreply.github.com"}):
        return {f"{i}: {t[:50]!r}": list(redact(t)) for i, t in enumerate(TEXTS)}


class Pinned(unittest.TestCase):
    maxDiff = None

    def test_every_text_gives_the_same_answer(self):
        with open(GOLD) as f:
            self.assertEqual(json.loads(json.dumps(collect())), json.load(f))


if __name__ == "__main__":
    unittest.main()
