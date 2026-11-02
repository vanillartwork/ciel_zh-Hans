# -*- coding: utf-8 -*-
"""Hardcoded executable strings that are lookup keys, not display text.

The executable builds some Japanese strings to look things up with.  The one
that cost us a release is the character name:

    0x140518b50   std::string("イオン")     -- constructed at 27 call sites

charanamemap.inc, charaactionmap.inc and charabodystancemap.inc all index by
that exact literal.  Rewriting it to 依恩 in the executable leaves the data
files saying イオン, every lookup misses, and the game dies in Chara's name
hash map with an access violation the moment free-roam needs it.  Same class of
mistake as translating column 11 of an event script: the string was shown on
screen *and* used as a key, so translating it looked right.

This is a HOLDING MEASURE, not a decision procedure.  It flags a string when it
also appears in one of the game's definition tables -- the *_data.inc /
*_tag.inc / *_enum.inc families under inc/ -- and that test is a plain substring
search over the whole file, comments included.  Known consequences:

  * セーブ is flagged by a comment, "// セーブ画面を呼び出す".
  * はい is flagged inside longer Japanese descriptions in item_clothes_data.inc.
  * お昼寝中 sits in { "お昼寝中", TaskDB::TASK_NAPPING, ... }, a record that
    carries its own enum id -- so the Japanese may well be a label, not the key.

So the count this produces is a set of CANDIDATES to analyse, and the rows it
lets through are not thereby proven safe: a key can also live in a compiled
table, another archive, or code this never looks at.

The .inc families also differ from one another, and must not be lumped together.
Exactly four are named in the executable, at 0x1406f9590, which feeds them to
three different loaders:

    Inc/Event/CharaNameMap.inc          -> 0x1403fcfb1
    Inc/Event/CharaBodyStanceMap.inc    -> 0x1403f2ccd  (r8d = 0)
    Inc/Event/CharaFaceStanceMap.inc    -> 0x1403f2ccd  (r8d = 1)
    Inc/Event/CharaActionMap.inc        -> 0x140404766

Those four are read at run time, so what they index by matters directly.  The
rest -- task, actiontiming, activecall, item -- are named nowhere in the
executable and their contents are compiled into it, which makes a match there
evidence about the executable's own tables rather than about a file being
parsed.  Note the capitalisation: searching for "charanamemap" finds nothing.

Proving a string is a key takes the code: イオン was settled by finding
std::string("イオン") built at 0x140518b50 and called from 27 sites.  Until each
candidate is settled that way, or a display-layer hook makes the question moot,
they stay Japanese because that is the state we know does not crash.
"""
import os

SCRIPT_PREFIXES = ("inc/event/res/", "inc/event/resdebug/")
DATA_SUFFIXES = (".inc", ".bas", ".txt")


def is_definition(path):
    p = path.lower()
    if not p.startswith("inc/"):
        return False
    if p.startswith(SCRIPT_PREFIXES):
        return False
    return p.endswith(DATA_SUFFIXES)


def defined_in_data(pak, strings):
    """Which of `strings` the game's definition tables index by."""
    want = [s for s in strings if s]
    if not want:
        return set()
    found = set()
    for e in pak:
        if not is_definition(e.path):
            continue
        try:
            text = pak.read(e).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        for s in want:
            if s not in found and s in text:
                found.add(s)
        if len(found) == len(want):
            break
    return found


def split(pak, todo):
    """(safe, held_back) out of patch_exe_strings.load()'s todo rows."""
    keys = defined_in_data(pak, [jp for _, jp, _, _ in todo])
    safe = [t for t in todo if t[1] not in keys]
    held = [t for t in todo if t[1] in keys]
    return safe, held


def write_report(path, held):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("uid,jp,zh_withheld\n")
        for uid, jp, zh, _cap in sorted(held, key=lambda t: t[1]):
            f.write('%s,"%s","%s"\n' % (uid, jp.replace('"', '""'),
                                        zh.replace('"', '""')))
