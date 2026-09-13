"""Span-preserving CSV scanner for the game's event scripts.

The game ships RFC4180-ish CSV (CRLF rows, quoted fields may contain
newlines, some fields are quoted unnecessarily).  Re-serialising with
csv.writer changes those redundant quotes, so instead of rewriting whole
files we record the character span of every field and splice translated
text into the original string.  Untouched bytes stay bit-identical.
"""

QUOTE_NEEDED = ',"\r\n'


def scan(t):
    """Yield (row, col, start, end) character spans of every raw field."""
    i = n = 0
    n = len(t)
    row = col = 0
    start = 0
    in_q = False
    while i < n:
        c = t[i]
        if in_q:
            if c == '"':
                if i + 1 < n and t[i + 1] == '"':
                    i += 2
                    continue
                in_q = False
            i += 1
            continue
        if c == '"' and i == start:
            in_q = True
            i += 1
            continue
        if c == ',':
            yield row, col, start, i
            col += 1
            i += 1
            start = i
            continue
        if c == '\r' and i + 1 < n and t[i + 1] == '\n':
            yield row, col, start, i
            row += 1
            col = 0
            i += 2
            start = i
            continue
        if c == '\n':
            yield row, col, start, i
            row += 1
            col = 0
            i += 1
            start = i
            continue
        i += 1
    if start < n or (n and t[n - 1] == ','):
        yield row, col, start, n


def unquote(raw):
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('""', '"')
    return raw


def quote(val):
    if any(ch in val for ch in QUOTE_NEEDED):
        return '"' + val.replace('"', '""') + '"'
    return val


def rows(t):
    """Return list of lists of unquoted values (for analysis)."""
    out, cur, r = [], [], 0
    for row, col, s, e in scan(t):
        while row > r:
            out.append(cur)
            cur = []
            r += 1
        cur.append(unquote(t[s:e]))
    out.append(cur)
    if out and out[-1] == ['']:
        out.pop()          # trailing CRLF does not start a real row
    return out


def splice(t, edits):
    """edits: list of (start, end, new_raw_text). Returns new string."""
    edits = sorted(edits, key=lambda x: x[0])
    out = []
    pos = 0
    for s, e, new in edits:
        if s < pos:
            raise ValueError("overlapping edits")
        out.append(t[pos:s])
        out.append(new)
        pos = e
    out.append(t[pos:])
    return "".join(out)
