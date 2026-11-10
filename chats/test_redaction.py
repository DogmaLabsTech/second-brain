"""Tests for redact.py. Run from the project root:

    CRABBOX_LOCAL=1 python3 -I -m unittest chats/test_redaction.py
"""

import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact  # noqa: E402

# Fake secrets, built from pieces so this file itself never holds a real-looking key.
FAKE = "Ab3dEf9hIj2LmN0pQr5tUv8xYz1"


class OwnAddress(unittest.TestCase):
    """Your own address is dropped once you list it; other people's stay."""

    def test_a_listed_address_is_dropped_and_others_are_kept(self):
        old = os.environ.get("BRAIN_OWN_EMAILS")
        os.environ["BRAIN_OWN_EMAILS"] = "sam@mydomain.test"
        try:
            out, n = redact("write to sam@mydomain.test or to pat@other.test")
        finally:
            if old is None:
                os.environ.pop("BRAIN_OWN_EMAILS")
            else:
                os.environ["BRAIN_OWN_EMAILS"] = old
        self.assertNotIn("sam@mydomain.test", out)
        self.assertIn("[email]", out)
        self.assertIn("pat@other.test", out)
        self.assertGreaterEqual(n, 1)


class Positive(unittest.TestCase):
    """Things that must disappear."""

    def gone(self, text, secret):
        out, n = redact(text)
        self.assertNotIn(secret, out, out)
        self.assertGreaterEqual(n, 1, out)
        return out

    def test_openai_key(self):
        self.gone("my key is sk-" + FAKE + "xx ok", "sk-" + FAKE)

    def test_anthropic_key(self):
        s = "sk-ant-api03-" + FAKE + "-" + FAKE
        self.gone("export it: " + s, FAKE)

    def test_github_classic(self):
        self.gone("token ghp_" + FAKE + "abcdefghij", "ghp_" + FAKE)

    def test_github_fine_grained(self):
        self.gone("github_pat_11ABCDEFG0" + FAKE, FAKE)

    def test_aws(self):
        self.gone("aws AKIAIOSFODNN7EXAMPLE here", "AKIAIOSFODNN7EXAMPLE")

    def test_slack(self):
        self.gone("xoxb-1234567890-abcdefghij", "xoxb-1234567890")

    def test_bearer(self):
        out = self.gone("Authorization: Bearer abc.DEF_123-xyz789", "abc.DEF_123-xyz789")
        self.assertIn("Bearer", out)

    def test_key_equals(self):
        out = self.gone("curl 'https://x.io/api?api_key=hunter2abc&x=1'", "hunter2abc")
        self.assertIn("x=1", out)

    def test_password_equals(self):
        self.gone("password=correcthorse", "correcthorse")

    def test_passwd_and_secret(self):
        out, _ = redact("passwd=letmein99 secret=s3cr3tvalue")
        self.assertNotIn("letmein99", out)
        self.assertNotIn("s3cr3tvalue", out)

    def test_token_colon_json(self):
        self.gone('{"access_token": "a1b2c3d4e5f6g7"}', "a1b2c3d4e5f6g7")  # gitleaks:allow (made-up test value)

    def test_long_hex(self):
        h = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        self.gone("the value " + h + " was printed", h)

    def test_long_base64(self):
        b = "dGhpcyBpcyBhIHNlY3JldCBrZXkgZm9yIHRlc3Q5OQ=="
        self.gone("blob " + b, "dGhpcyBpcyBhIHNlY3JldCBrZXkgZm9yIHRlc3Q5OQ")

    def test_jwt(self):
        j = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"  # gitleaks:allow (the public jwt.io sample)
        self.gone("jwt " + j, "eyJhbGciOiJIUzI1NiJ9")

    def test_tailscale(self):
        self.gone("tailscale up --authkey tskey-auth-kAbCdEf1CNTRL-xyz123", "tskey-auth")

    def test_pairing_code_after(self):
        self.gone("The pairing code is 482913, type it on the phone", "482913")

    def test_pairing_code_before(self):
        self.gone("enter 55129876 to pair the device", "55129876")

    def test_env_line(self):
        out = self.gone("STRIPE_WEBHOOK_SECRET=whsec_abcdef12345\nDEBUG=1", "whsec_abcdef12345")  # gitleaks:allow (made-up test value)
        self.assertIn("DEBUG=1", out)

    def test_env_line_no_secret_word(self):
        self.gone("OPENROUTER_MODEL_HASH=zz91kd83kd9a", "zz91kd83kd9a")

    @mock.patch.dict(os.environ, {"BRAIN_OWN_EMAILS": "agent-os@users.noreply.github.com"})
    def test_email(self):
        out, n = redact("mail me at agent-os@users.noreply.github.com please")
        self.assertNotIn("agent-os@users.noreply.github.com", out)
        self.assertEqual(n, 1)

    @mock.patch.dict(os.environ, {"BRAIN_OWN_EMAILS": "agent-os@users.noreply.github.com"})
    def test_email_cut_short(self):
        out, n = redact("203.0.113.10    owners-iphone    agent-os@users.noreply.github.com   iOS")
        self.assertNotIn("example.com", out)
        self.assertEqual(n, 1)

    def test_private_key_block(self):
        pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"
        self.gone("key:\n" + pem, "b3BlbnNzaC1rZXktdjEAAAAA")

    def test_url_password(self):
        self.gone("postgres://owner:Sup3rPass@db.local/x", "Sup3rPass")

    def test_hex_without_git_context(self):
        sha = "e83c5163316f89bfbde7d9ab23ca2e25604af290"
        self.gone("the checksum file says " + sha, sha)


class Negative(unittest.TestCase):
    """Normal text that must survive untouched."""

    def same(self, text):
        out, n = redact(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_sentence(self):
        self.same("We moved the brightness widget into the right side of the bar today.")

    def test_git_commit_sha(self):
        self.same("Committed as commit 3f2a9c1e4b5d6f7a8b9c0d1e2f3a4b5c6d7e8f90 on main.")

    def test_short_sha(self):
        self.same("Fixed in a1b2c3d, see the log.")

    def test_path(self):
        self.same("Edit ~/projects/second-brain/chats/convert.py and rerun.")

    def test_uuid(self):
        self.same("Session 4a0d649b-cac5-4461-a41e-6e29ada8a5e5 ended.")

    def test_slug(self):
        self.same("Folder -home-user-projects-Projects-example-classifier exists.")

    def test_prose_key_colon(self):
        self.same("Key: the bar restarts in about five seconds.")

    def test_short_env(self):
        self.same("Run it with CRABBOX_LOCAL=1 python3 -I -m unittest.")

    def test_env_path_value(self):
        self.same("XDG_CONFIG_HOME=~/.config is the default.")

    def test_token_in_prose(self):
        self.same("Five are security fixes: the tool token comparison and basic authentication checks.")

    def test_port_number(self):
        self.same("rockceen is served on port 4197 via Tailscale.")


class NoDefaultAddress(unittest.TestCase):
    def test_no_address_is_dropped_until_you_list_yours(self):
        with mock.patch.dict(os.environ, {"BRAIN_OWN_EMAILS": "", "XDG_CONFIG_HOME": "/nonexistent-config"}):
            self.assertEqual(redact("mail agent-os@users.noreply.github.com now"), ("mail agent-os@users.noreply.github.com now", 0))


class SecretShapesThatUsedToLeak(unittest.TestCase):
    """Shapes found leaking by the 2026-11 audit: the secret must be gone and nearby words must stay."""

    PW = "Zq8Lm2Xv9Rt4Wk7Ny3Pb6Hc1"

    def gone(self, text, secret):
        out, n = redact(text)
        self.assertNotIn(secret, out)
        self.assertGreaterEqual(n, 1)
        return out

    def test_a_link_with_an_empty_user(self):
        self.gone("redis://:" + self.PW + "@host:6379", self.PW)

    def test_a_link_whose_password_holds_an_at_sign(self):
        out = self.gone("mysql://root:p@SECRET@host/db", "SECRET")
        self.assertIn("host/db", out)

    def test_the_tail_after_an_ampersand_semicolon_or_bracket(self):
        self.gone("password=abc&Xk9fP2mQz7Lw", "Xk9fP2mQz7Lw")
        self.gone("PASSWORD=ab12;cd34efghQ", "cd34efghQ")
        self.gone("db_password=Ab3)Qw8zT5nM", "Qw8zT5nM")

    def test_a_query_string_keeps_its_next_parameter(self):
        self.assertEqual(redact("?token=abc123&page=2")[0], "?token=[redacted]&page=2")

    def test_a_quoted_phrase_with_spaces(self):
        self.gone('password="correct horse battery staple"', "horse")

    def test_a_password_after_a_colon_without_a_digit(self):
        self.gone("password: correcthorsebatterystaple", "correcthorsebatterystaple")
        self.gone("api_key: abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrstuvwxyz")

    def test_an_aws_secret_key_with_slashes(self):
        key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        self.gone(key, "EXAMPLEKEY")
        self.gone("AWS Secret Access Key [None]: " + key, "EXAMPLEKEY")

    def test_curl_user_password(self):
        out = self.gone("curl -u admin:" + self.PW + " http://x", self.PW)
        self.assertIn("admin", out)

    def test_a_lowercase_private_key_header(self):
        self.gone("-----begin private key-----\nMIIEvQIBADANBgkq\n-----end private key-----", "MIIEvQIBADANBgkq")

    def test_prose_and_paths_stay(self):
        for text in ("Key: the bar restarts", "Password: required", "token: the one above",
                     "see usr/local/share/applications/MyApp/Thing for it", "git push -u origin main"):
            self.assertEqual(redact(text), (text, 0), text)

    def test_a_long_run_does_not_take_forever(self):
        import time
        start = time.time()
        redact("a-" * 4000)
        redact("secret" * 2000)
        self.assertLess(time.time() - start, 30)   # the old code needed minutes; a busy test machine needs seconds


if __name__ == "__main__":
    unittest.main()
