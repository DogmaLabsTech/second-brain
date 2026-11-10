"""Blank out anything in chat text that looks like a secret.

Stdlib only. `redact(text)` returns (clean_text, number_of_redactions).
The rules err on the side of redacting: a false positive costs a few
characters of a note, a false negative leaks a key into the search index.
See README.md, "How redaction works", for the reasoning behind each rule.
"""

import math
import os
import re

MARK = "[redacted]"
EMAIL_MARK = "[email]"

# Your own address(es): always dropped. Add yours with BRAIN_OWN_EMAILS (comma separated) or one address per line in
# ~/.config/second-brain/own-emails. Other people's addresses are left as they are.
OWN_EMAILS = ()


def own_addresses():
    found = list(OWN_EMAILS) + [e.strip() for e in os.environ.get("BRAIN_OWN_EMAILS", "").split(",") if "@" in e]
    path = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "second-brain", "own-emails")
    try:
        with open(path, encoding="utf-8") as f:
            found += [line.strip() for line in f if "@" in line and not line.lstrip().startswith("#")]
    except OSError:
        pass
    return found

# 1. Whole blocks (run first so the inner lines are not half-redacted).
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)",
    re.S | re.I,
)

# 2. Known token shapes: the whole match is replaced.
_TOKEN_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),                      # OpenAI / Anthropic (sk-ant-...)
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),     # GitHub classic tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),                 # GitHub fine-grained tokens
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}"),                    # GitLab
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                  # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),                # Slack
    re.compile(r"\bxapp-[A-Za-z0-9\-]{10,}"),                      # Slack app token
    re.compile(r"\btskey-[A-Za-z0-9\-]{8,}"),                      # Tailscale auth / api keys
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),                      # Google API key
    re.compile(r"\bhf_[A-Za-z0-9]{30,}"),                          # Hugging Face
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),                         # npm
    re.compile(r"\b(?:pk|sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"),  # Stripe
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b"),                # Telegram bot token
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]*)?"),  # JWT
    re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}"),                       # lone base64 JSON header/payload
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+"),
    re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_\-]+"),
]

# 3. Bearer / Basic auth headers: keep the word, drop the credential.
_AUTH_HEADER = re.compile(r"\b([Bb]earer|BEARER|Basic|Token)(\s+)(?=[A-Za-z0-9._~+/=\-]*\d)([A-Za-z0-9._~+/=\-]{8,})")

_BEARER_LONG = re.compile(r"\b([Bb]earer)(\s+)([A-Za-z0-9._~+/=\-]{20,})")

# 4. Passwords inside URLs: scheme://user:pass@host. The user may be empty (redis://:pass@host) and the password may
# hold an "@": it runs to the last "@" before the host.
_URL_CREDS = re.compile(r"([a-z][a-z0-9+.\-]*://[^\s:/@]*:)([^\s/]+)(@)")
# curl -u user:pass / --user user:pass
_CURL_USER = re.compile(r"((?<![\w\-])(?:-u|--user)[ =]+[^\s:]+:)(\S+)")

# 5. name=value / name: value where name mentions a secret word.
# The name starts where a run of word characters starts ((?<![\w\-.]) instead of \b): with \b every position inside a long
# run began its own scan and a long token took quadratic time.
_SECRET_WORDS = r"(?:key|token|secret|password|passwd|passphrase|pwd|credential|auth|cookie|session_?id|api_?key|private)"
_ASSIGN_EQ = re.compile(
    r"(?i)((?<![\w\-.])[\w\-.]*" + _SECRET_WORDS + r"[\w\-.]*[\"']?\s*=\s*[\"']?)([^\s\"'`,;&)<>\]]{3,})"
)
_ASSIGN_COLON = re.compile(
    r"(?i)((?<![\w\-.])[\w\-.]*" + _SECRET_WORDS + r"[\w\-.]*[\"']?\s*:\s*[\"']?)([^\s\"'`,;&)<>\]]{8,})"
)
# Names that are clearly a password or a secret: the whole value goes, however it is written. A quoted value runs to
# the closing quote (spaces and all); an unquoted one runs to a space or a quote, and over "&" or ";" unless "&name="
# starts the next query parameter. The ":" form needs no digit here.
_STRONG_WORDS = r"(?:password|passwd|passphrase|pwd|secret|token|api_?key)"
_STRONG_VALUE = r"(\"[^\"\n]{3,}\"|'[^'\n]{3,}'|(?:[^\s\"'`&]|&(?!\w+=)){%d,})"
_STRONG_EQ = re.compile(r"(?i)((?<![\w\-.])[\w\-.]*" + _STRONG_WORDS + r"[\w\-.]*[\"']?\s*=\s*)" + _STRONG_VALUE % 3)
_STRONG_COLON = re.compile(r"(?i)((?<![\w\-.])[\w\-.]*" + _STRONG_WORDS + r"[\w\-.]*[\"']?\s*:\s*)" + _STRONG_VALUE % 8)
_HARMLESS_VALUES = {"true", "false", "null", "none", "undefined", "yes", "no", "on", "off",
                    "required", "optional", "string", "number", "redacted", "[redacted]"}

# 6. .env-like lines: UPPER_SNAKE=value (value longer than 8 chars).
_ENV_LINE = re.compile(r"(?m)^(\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=\s*[\"']?)([^\s\"'#]{9,})")
_ENV_INLINE = re.compile(r"\b([A-Z][A-Z0-9]*_[A-Z0-9_]+=[\"']?)([^\s\"'`;&|)]{9,})")

# 7. Pairing codes: 6-8 digits near the word pair/pairing.
_PAIR_AFTER = re.compile(r"(?i)(\bpair(?:ing|ed)?\b[^\n]{0,60}?)(?<![\d.\-:/])\b(\d{3}[ \-]?\d{3,5})\b(?![\d.:/])")
_PAIR_BEFORE = re.compile(r"(?i)(?<![\d.\-:/])\b(\d{3}[ \-]?\d{3,5})\b(?![\d.:/])([^\n]{0,40}?\bpair(?:ing|ed)?\b)")

# 8. Long hex (>= 32) and long base64-ish (>= 32) runs.
_HEX = re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{32,}(?![A-Za-z0-9])")
_GIT_CONTEXT = re.compile(
    r"(?i)(?:\bcommit|\bsha(?:1|256)?|\bhash|\brev(?:ision)?|\bHEAD|\bmerge|\bcherry-pick|\brevert|\bgit\s+\w+|\bblob|\btree|@)[\s:=#`'\"]*(?:[0-9a-fA-F]{7,40}[\s,`'\")]*)*$"
)
_B64 = re.compile(r"(?<![A-Za-z0-9+/=_\-])[A-Za-z0-9+/_\-]{32,}={0,2}(?![A-Za-z0-9+/=_\-])")


def _entropy(s):
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _looks_random(piece):
    """True for a run that looks like key material rather than a word or a path."""
    if len(piece) < 20:
        return False
    has_digit = any(c.isdigit() for c in piece)
    has_upper = any(c.isupper() for c in piece)
    has_lower = any(c.islower() for c in piece)
    if not has_digit:
        # Pure letters: only when it mixes cases heavily and is very random.
        return has_upper and has_lower and len(piece) >= 32 and _entropy(piece) >= 4.5
    if not (has_upper or has_lower):
        return len(piece) >= 32  # long digit runs
    return _entropy(piece) >= 3.7


def _b64_sub(m):
    tok = m.group(0)
    if re.fullmatch(r"[0-9a-fA-F]+", tok):
        return tok  # pure hex was already judged by the hex rule (git ids are kept there)
    # Paths and slugs: judge each part between separators on its own.
    if len(tok) == 40 and re.fullmatch(r"[A-Za-z0-9/+]+", tok) and _looks_random(tok):
        return MARK  # an AWS secret access key: its "/" must not split it into short harmless pieces
    pieces = re.split(r"[/_\-.]", tok)
    if any(_looks_random(p) for p in pieces) or (len(pieces) == 1 and _looks_random(tok)):
        return MARK
    if "/" not in tok and "-" not in tok and "_" not in tok and _looks_random(tok):
        return MARK
    return tok


def _hex_sub(text):
    out, last, n = [], 0, 0
    for m in _HEX.finditer(text):
        h = m.group(0)
        before = text[max(0, m.start() - 40):m.start()]
        if len(h) <= 40 and _GIT_CONTEXT.search(before):
            continue  # a git commit / blob id: keep
        out.append(text[last:m.start()])
        out.append(MARK)
        last = m.end()
        n += 1
    out.append(text[last:])
    return "".join(out), n


def _own_emails(text):
    total = 0
    for email in own_addresses():
        text, k = re.subn(re.escape(email), EMAIL_MARK, text, flags=re.I)
        total += k
        # Cut short by a column ("agent-os@users.noreply.github.com" in a tailscale status table): still your address.
        text, k = re.subn(re.escape(email.split("@")[0] + "@") + r"(?![\w.-])", EMAIL_MARK, text, flags=re.I)
        total += k
    return text, total


def _known_tokens(text):
    text, total = _PRIVATE_KEY.subn(MARK, text)
    for pat in _TOKEN_PATTERNS:
        text, k = pat.subn(MARK, text)
        total += k
    return text, total


def _auth_and_urls(text):
    total = 0
    for pat in (_AUTH_HEADER, _BEARER_LONG):
        text, k = pat.subn(lambda m: m.group(1) + m.group(2) + MARK, text)
        total += k
    text, k = _URL_CREDS.subn(lambda m: m.group(1) + MARK + m.group(3), text)
    text, k2 = _CURL_USER.subn(lambda m: m.group(1) + MARK, text)
    return text, total + k + k2


def _assign(m):
    val = m.group(2)
    if val.lower() in _HARMLESS_VALUES or val.startswith(("$", "{", "<", "[redacted")):
        return m.group(0)
    return m.group(1) + MARK


def _strong(m):
    raw = m.group(2)
    val = raw.strip("\"'")
    if val.lower() in _HARMLESS_VALUES or val.startswith(("$", "{", "<", "/", "~", "http", "[redacted")):
        return m.group(0)
    quote = raw[0] if raw[0] in "\"'" else ""
    return m.group(1) + quote + MARK + quote


def _assign_colon(m):
    val = m.group(2)
    # Prose like "Key: something" is fine; only token-shaped values go.
    if val.lower() in _HARMLESS_VALUES or val.startswith(("$", "{", "<", "/", "~", "http", "[redacted")):
        return m.group(0)
    if not any(c.isdigit() for c in val):
        return m.group(0)
    return m.group(1) + MARK


def _env(m):
    val = m.group(2)
    if val.startswith(("/", "~", "$", ".", "[redacted", "http://localhost", "http://127.")):
        return m.group(0)
    return m.group(1) + MARK


def _sub_counting(patterns_and_fns, text):
    """Apply each (pattern, replacer) in turn; how many marks they added."""
    total = 0
    for pat, fn in patterns_and_fns:
        new = pat.sub(fn, text)
        total += new.count(MARK) - text.count(MARK)
        text = new
    return text, total


def _assignments(text):
    return _sub_counting(((_STRONG_EQ, _strong), (_STRONG_COLON, _strong), (_ASSIGN_EQ, _assign),
                          (_ASSIGN_COLON, _assign_colon)), text)


def _env_lines(text):
    return _sub_counting(((_ENV_LINE, _env), (_ENV_INLINE, _env)), text)


def _pairing_codes(text):
    new = _PAIR_AFTER.sub(lambda m: m.group(1) + MARK, text)
    new = _PAIR_BEFORE.sub(lambda m: MARK + m.group(2), new)
    return new, new.count(MARK) - text.count(MARK)


def _long_runs(text):
    text, total = _hex_sub(text)
    new = _B64.sub(_b64_sub, text)
    return new, total + new.count(MARK) - text.count(MARK)


STEPS = (_own_emails, _known_tokens, _auth_and_urls, _assignments, _env_lines, _pairing_codes, _long_runs)


def redact(text):
    """Return (redacted_text, count)."""
    if not text:
        return text, 0
    total = 0
    for step in STEPS:
        text, k = step(text)
        total += k
    return text, total
