# -*- coding: utf-8 -*-
"""Send a tool's output to a UTF-8 log file as well as the console.

The installer needs both halves of this. It shows its own progress messages in
the user's language, so it runs the tools with their output hidden -- but when
something fails, the log is the only thing that says why, and a bug report is
useless without it.

It cannot simply read the tools' console output instead: NSIS decodes a child
process's pipe with the system code page, so anything non-ASCII arrives as
mojibake, and the tools' own English step labels would be printed alongside
the installer's Chinese ones, saying everything twice.
"""
import sys, io, os, time


class _Null:
    """Stands in for a stream that is not there.

    Under pythonw.exe -- which the installer uses so that no console window
    appears -- sys.stdout and sys.stderr are None, and the first print() would
    otherwise end the run before anything was logged.
    """

    def write(self, s):
        return len(s)

    def flush(self):
        pass

    def reconfigure(self, **kw):
        pass

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _Null()
if sys.stderr is None:
    sys.stderr = _Null()


class Tee:
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        try:
            self.fh.write(s)
        except Exception:
            pass
        return len(s)

    def flush(self):
        for t in (self.stream, self.fh):
            try:
                t.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


def start(path, header=""):
    """Begin appending this run's output to `path`. Returns the file handle."""
    if not path:
        return None
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    fh = io.open(path, "a", encoding="utf-8", newline="\n")
    fh.write("\n%s\n%s  %s\n%s\n"
             % ("=" * 68, time.strftime("%Y-%m-%d %H:%M:%S"), header, "=" * 68))
    fh.flush()
    sys.stdout = Tee(sys.stdout, fh)
    sys.stderr = Tee(sys.stderr, fh)
    return fh


def add_argument(ap):
    ap.add_argument("--log", help="also append everything printed to this file")
