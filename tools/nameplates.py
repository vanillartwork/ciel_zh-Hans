# -*- coding: utf-8 -*-
"""Chinese nameplates without touching the character key.

Column 11 of an event script is the character key -- charanamemap.inc looks up
models by it, down to a trailing fullwidth space -- and the game also prints it
above the dialogue.  Translating it breaks every lookup (see
docs/reverse-engineering/event-script.md), so the key stays Japanese and the
label is set through the game's own command instead:

    ,,,,,,,,,,,,,EVENT_PROCESS_CHANGE_DISPLAY_NAME,イオン,依恩,

One of those per character is inserted right after the script's header row.
The original does exactly this -- 113 times, and in 54 of them the rename runs
*before* the character is placed (me09_08.txt renames ネロＢ 76 rows before it
appears), which is what makes a single block at the top workable.

Two things this deliberately does not do:

  * It never writes to column 11, column 14, or any command argument.
  * A script that renames characters itself still gets defaults, because the
    defaults go in first and the original's own calls run later and override
    them.  me09_02.txt hides ネロ behind ？？？ at row 70 and reveals
    ウルゥリィヤ at row 122; ネロ's first line is row 78, so the disguise is
    already in place before she speaks and a default of 妮诺 set at the top
    never leaks the identity early.

Insertion changes the number of records in a file.  Control flow here is
tag-based (7,619 EVENT_PROCESS_TAG against 4,737 EVENT_PROCESS_JUMP, plus
EVENT_PROCESS_RETURN_PARENT_TOP which returns to a parent's top rather than an
offset), and the system save carries no script paths, event names or record
indices -- but whether a mid-event save resumes by record index has not been
proved, so this runs on an explicit list of scripts, not everything.
"""
import sys, os, io, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import csvspan

FIELDS = 17
CMD_COL = 13
SPEAKER_COL = 11
DIALOG_COL = 12
RENAME = "EVENT_PROCESS_CHANGE_DISPLAY_NAME"

# Scripts this is enabled for.  Grow it only as each one is confirmed in game.
# Every event script the game ships under res/.  resdebug/ is left out: it
# holds debug twins nothing plays.  Patching a script that turns out to be
# unreachable is harmless -- it just does nothing -- so reachability only
# matters when you are trying to *test* a particular scene.  (me01_00h.txt
# looks like the opening and holds the same 100 lines, but the chain is
# me01_00.txt -> me01_00_load01.txt -> ME01_00_Main.)
PREFIX = "inc/event/res/"


def enabled(path):
    return path.startswith(PREFIX) and path.endswith(".txt")

CHARAMAP = "inc/event/charanamemap.inc"


def known_actors(pak):
    """Keys charanamemap actually defines, exactly as written.

    Column 11 also carries things that are not characters at all -- bare 女 and
    男 in the opening, システム文 for system lines, narration, groups.  Renaming
    something the map does not define is at best a no-op and at worst an error,
    so only keys that appear here are ever touched.
    """
    e = pak.get(CHARAMAP)
    if e is None:
        return set()
    out = set()
    for line in pak.read(e).decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith('"'):
            end = line.find('"', 1)
            if end > 1:
                out.add(line[1:end])
    return out


def command_row(actor_key, label, eol="\r\n"):
    """One rename record, in the original's own 17-field shape."""
    f = [""] * FIELDS
    f[CMD_COL] = RENAME
    f[CMD_COL + 1] = actor_key          # exact, never stripped
    f[CMD_COL + 2] = label
    return ",".join(csvspan.quote(v) for v in f) + eol


def actors(rows):
    """Character keys this script uses, in the order they first appear."""
    seen = []
    for r in rows:
        if len(r) > SPEAKER_COL:
            k = r[SPEAKER_COL]
            if k.strip() and k not in seen:
                seen.append(k)
    return seen


def renames_itself(rows):
    return any(len(r) > CMD_COL and r[CMD_COL].strip() == RENAME for r in rows)


def header_end(text):
    """Character offset just past the first record -- the `event` header row.

    Found through the scanner, because a dialogue field can hold newlines and
    splitting on them would land inside one.
    """
    spans = [(row, en) for row, col, s, en in csvspan.scan(text)]
    if not spans:
        return None
    first = min(r for r, _ in spans)
    end = max(en for r, en in spans if r == first)
    # step over the record separator that follows it
    for sep in ("\r\n", "\n"):
        if text.startswith(sep, end):
            return end + len(sep)
    return None


def plan(text, labels, known=None):
    """(edits, used) for one script.

    `labels` maps character key -> Chinese; `known` limits it to the keys
    charanamemap defines.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    at = header_end(text)
    if at is None:
        return [], []
    eol = "\r\n" if "\r\n" in text else "\n"
    used = [k for k in actors(rows)
            if labels.get(k) and (known is None or k in known)]
    if not used:
        return [], []
    block = "".join(command_row(k, labels[k], eol) for k in used)
    return [(at, at, block)], used
