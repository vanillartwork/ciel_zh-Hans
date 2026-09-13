# -*- coding: utf-8 -*-
"""Report how far along a long step is, for a caller that cannot see inside.

The installer runs these tools as child processes. It cannot read their output
while they work -- NSIS blocks on the call -- so instead each tool writes the
overall percentage into a small file, and the installer polls it.

Each invocation is told the slice of the overall bar it owns:

    --progress "<file>" --progress-range 45 60

so the font build reporting "halfway" writes 52, not 50. That keeps the
arithmetic in one place and lets the phases be reordered or reweighted without
any of them knowing about the others.

Each write goes to a temporary file and is then renamed over the real one, so
a reader polling it never sees half a line.

The file is UTF-16LE without a BOM, because the reader is NSIS: its FileRead
decodes with the system code page and would turn a UTF-8 label into mojibake,
while FileReadUTF16LE reads this exactly.
"""
import io, os, sys

_state = {"path": None, "lo": 0.0, "hi": 100.0, "last": -1, "label": "",
          "base_lo": 0.0, "base_hi": 100.0, "high_water": -1.0}


def configure(path, lo=0.0, hi=100.0):
    _state.update(path=path, lo=float(lo), hi=float(hi),
                  base_lo=float(lo), base_hi=float(hi), last=-1, high_water=-1.0)
    if path:
        report(0.0)


def slice(a, b):
    """Narrow to a fraction of this run's own range, for one sub-step.

    A phase often has more than one long loop in it -- extraction and merging,
    say. Without this they would each sweep the whole phase's range and the
    bar would visibly jump backwards between them.
    """
    lo, hi = _state["base_lo"], _state["base_hi"]
    span = hi - lo
    _state["lo"] = lo + span * float(a)
    _state["hi"] = lo + span * float(b)


def add_arguments(ap):
    ap.add_argument("--progress", help="write percent-complete to this file")
    ap.add_argument("--progress-range", nargs=2, type=float, metavar=("LO", "HI"),
                    default=(0.0, 100.0),
                    help="the slice of the overall bar this run owns")


def from_args(a):
    configure(getattr(a, "progress", None), *getattr(a, "progress_range", (0, 100)))


def label(text):
    """What is happening now, shown beside the bar."""
    _state["label"] = text or ""
    report(None)


def report(fraction):
    """`fraction` is 0..1 within this run's own slice; None just re-labels."""
    path = _state["path"]
    if not path:
        return
    if fraction is not None:
        f = 0.0 if fraction < 0 else (1.0 if fraction > 1 else float(fraction))
        pct = _state["lo"] + f * (_state["hi"] - _state["lo"])
        # never go backwards: a caller that re-runs a loop, or a sub-step that
        # starts lower than the last one ended, should not rewind the bar
        if pct < _state["high_water"]:
            pct = _state["high_water"]
        _state["high_water"] = pct
        _state["last"] = pct
    pct = _state["last"]
    if pct < 0:
        return
    _atomic(path, "%d\n%s\n" % (int(round(pct)), _state["label"]))


def _atomic(path, text):
    """Replace the file in one step, and in the encoding the reader expects.

    Two things the reader needs. It polls while we write, so the file is built
    under a temporary name and renamed over the real one -- a rename is atomic,
    so a poller never catches half a line. And the reader is NSIS, whose
    FileRead decodes with the system code page: a UTF-8 label would arrive as
    mojibake, while FileReadUTF16LE reads UTF-16LE without a BOM exactly.
    """
    tmp = path + ".tmp"
    try:
        with io.open(tmp, "wb") as fh:
            fh.write(text.encode("utf-16-le"))
        os.replace(tmp, path)
    except OSError:
        pass                       # progress is never worth failing a build over


def over(total, every=1):
    """Wrap a loop: `for i, x in over(len(items))` style counter.

    Returns a function to call with the number done so far.
    """
    total = max(1, int(total))

    def tick(done):
        if every <= 1 or done % every == 0 or done >= total:
            report(done / float(total))
    return tick


def finish(path, code, label_text=""):
    """Tell the caller this run is over, and with what exit status.

    A detached process gives its launcher no exit code, so this file is how it
    comes back.
    """
    if not path:
        return
    _atomic(path, "%d\n%s\n" % (int(code), label_text))
