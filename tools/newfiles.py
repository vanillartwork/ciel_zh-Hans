# -*- coding: utf-8 -*-
"""Install bookkeeping: what the patch owns, and how one install undoes itself.

Two records, doing different jobs.

    Backup/created.json     what we believe is installed, after the fact
      cielzh.dll:
        existed_before   was something already at that path before us
        installed_sha256 what we last wrote there
        patch_version    which build wrote it

    Backup/install_tx.json  one transaction covering the WHOLE install, written
                            before the first byte changes, with a copy of every
                            file it is about to touch under Backup/rollback/

The transaction is install-wide because a per-file one is not enough.  With one
record per file, each step tidied up after itself and deleted its own rollback
copy the moment it succeeded -- so a failure in a later step found the earlier
ones already "finished", and the only thing left to restore from was Backup/,
which holds the ORIGINAL.  An upgrade that failed halfway therefore produced the
original executable beside the new DLL: neither the old version nor the new one.

So: every step records the state it is replacing, nothing is cleaned up until
the whole install has succeeded, and a rollback that cannot finish leaves the
transaction and the copies exactly where they are for the next run.

Four rules the transaction has to keep, in this order:

  1. The whole undo plan is on disk before the first byte changes.  Adding a
     step on the way past is not enough: apply_one() used to register the DLL
     step itself, so between replacing the DLL and saving the transaction there
     was a window in which the file had changed and no record of it existed.  A
     process killed there came back to an executable put back to the old
     version, a DLL left at the new one, and the transaction deleted.
  2. phase="done" is the commit point.  After it, an interrupted run may only
     finish tidying up.  Undoing a committed install meant deleting the DLL it
     had just installed, because the rollback copies were already gone and
     "there is no copy" was read as "we created this file".
  3. Recovery data is deleted only once every step has been verified back.  A
     rollback that skipped a missing copy, or wrote a damaged one over the
     target, used to report success and then delete the evidence.
  4. Undoing a step is itself interruptible, so it puts a file back the same way
     the install put it there: a copy of its own, verified, then one os.replace.
     Writing straight onto the target left a partial file behind when the undo
     was cut short -- and a partial file is neither version, which the retry then
     reported as "left untouched" before deleting the recovery data.  A target
     that is neither version now stops the undo and keeps everything.

cielzh.dll is the only file with no original to fall back on, which is why it
also has an ownership record.  A file at that path we do not recognise stops the
install; it is never adopted and never overwritten, and never deleted either --
including by a --no-loader install, which used to remove it on the strength of
the record alone without looking at what was actually on disk.
"""
import os, io, json, hashlib, shutil, subprocess, tempfile, time

RECORD = "created.json"
TX = "install_tx.json"
ROLLBACK_DIR = "rollback"

# (name in the staged build, path inside the game folder)
#
# The DLL and the table it reads.  The table is generated on the player's
# machine from the player's own data, so it has no original either, and the
# same ownership rules apply: never adopted, never overwritten or removed unless
# it is still the copy we wrote.
CREATED = [("cielzh.dll", "cielzh.dll"),
           ("cielzh-text.bin", "cielzh-text.bin")]

RECORD_VERSION = 1
TX_VERSION = 2


class Stop(Exception):
    """Refuse to continue.  Nothing has been changed."""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                return h.hexdigest()
            h.update(b)


def sha256_or_none(path):
    return sha256(path) if os.path.exists(path) else None


def running_state(exe="CielnosurgeDX.exe"):
    """'running', 'stopped', or 'unknown'.

    Unknown is not stopped.  Reporting a failed query as "not running" is how a
    check like this quietly stops covering anything.
    """
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + exe, "/NH"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if r.returncode != 0:
        return "unknown"
    return "running" if exe.lower() in (r.stdout or "").lower() else "stopped"


# --- json helpers -------------------------------------------------------------
def _write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


# --- the ownership record -----------------------------------------------------
def record_path(backup):
    return os.path.join(backup, RECORD)


def load_record(backup):
    p = record_path(backup)
    if not os.path.exists(p):
        return {"version": RECORD_VERSION, "files": {}}
    rec = _read_json(p)
    if rec.get("version") != RECORD_VERSION:
        raise Stop("%s says version %r, this build understands %d"
                   % (RECORD, rec.get("version"), RECORD_VERSION))
    rec.setdefault("files", {})
    return rec


def save_record(backup, rec):
    _write_json(record_path(backup), rec)


# --- the install transaction --------------------------------------------------
def tx_path(backup):
    return os.path.join(backup, TX)


def rollback_dir(backup):
    return os.path.join(backup, ROLLBACK_DIR)


def load_tx(backup):
    p = tx_path(backup)
    if not os.path.exists(p):
        return None
    try:
        tx = _read_json(p)
    except ValueError:
        raise Stop("%s is unreadable. Move it and Backup/%s aside, then run the "
                   "installer again." % (TX, ROLLBACK_DIR))
    if tx.get("version") != TX_VERSION:
        raise Stop("%s says version %r, this build understands %d"
                   % (TX, tx.get("version"), TX_VERSION))
    return tx


class Txn:
    """One install's worth of undo information."""

    def __init__(self, game, backup, version):
        self.game = game
        self.backup = backup
        self.dir = rollback_dir(backup)
        self.data = {"version": TX_VERSION, "patch_version": version,
                     "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "phase": "planned", "steps": []}
        self._n = 0

    # -- building -----------------------------------------------------------
    def add(self, kind, rel, before, after, save_path=None, extra=None):
        """Registers one step and keeps a verified copy of what it will replace.

        Every step must be registered before begin(); registering one later
        leaves a window in which the file has changed and the transaction does
        not know about it.
        """
        if self.data["phase"] != "planned":
            raise Stop("internal: %s was registered after the install had "
                       "already started" % rel)
        os.makedirs(self.dir, exist_ok=True)
        keep = None
        if save_path is not None:
            if not os.path.exists(save_path):
                raise Stop("internal: nothing to copy at %s for the %s step"
                           % (save_path, kind))
            keep = "s%02d_%s" % (self._n, os.path.basename(rel))
            full = os.path.join(self.dir, keep)
            shutil.copyfile(save_path, full)
            # Checked now, while nothing has been touched yet: a copy that does
            # not match is useless later, and later is after the change.
            if sha256(full) != before:
                raise Stop("the copy kept of %s does not match the file itself; "
                           "nothing was changed" % rel)
        step = dict(kind=kind, rel=rel, before_sha256=before,
                    after_sha256=after, rollback=keep, state="pending")
        if extra:
            step.update(extra)
        self.data["steps"].append(step)
        self._n += 1
        return step

    def add_range_copy(self, kind, rel, before, after, blob, extra=None):
        """Same, for a byte range kept as its own blob rather than a whole file."""
        if self.data["phase"] != "planned":
            raise Stop("internal: %s was registered after the install had "
                       "already started" % rel)
        if hashlib.sha256(blob).hexdigest() != before:
            raise Stop("internal: the bytes kept for %s are not the bytes "
                       "recorded" % rel)
        os.makedirs(self.dir, exist_ok=True)
        keep = "s%02d_%s.range" % (self._n, os.path.basename(rel))
        with open(os.path.join(self.dir, keep), "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        step = dict(kind=kind, rel=rel, before_sha256=before,
                    after_sha256=after, rollback=keep, state="pending")
        if extra:
            step.update(extra)
        self.data["steps"].append(step)
        self._n += 1
        return step

    def begin(self):
        self.data["phase"] = "committing"
        _write_json(tx_path(self.backup), self.data)

    def mark(self, step, state="done"):
        step["state"] = state
        _write_json(tx_path(self.backup), self.data)

    def finish(self, report=None):
        """The commit point.

        Once phase="done" is on disk the install has happened, and a run that
        finds it may only finish tidying up.  The in-memory phase moves only
        after that write succeeds, so a failure here is still undoable.
        """
        data = dict(self.data, phase="done")
        _write_json(tx_path(self.backup), data)
        self.data = data
        cleanup(self.backup, report or (lambda _m: None))


def committed(tx):
    """True once phase="done" was written: that install is not undone any more."""
    return tx is not None and tx.get("phase") == "done"


def cleanup(backup, report=print):
    """Removes the recovery data, copies first and the transaction last.

    Only ever called once the transaction has been seen all the way through --
    either committed or verified back.  The transaction file goes last so that a
    failure here leaves copies that something still points at.
    """
    rdir = rollback_dir(backup)
    shutil.rmtree(rdir, ignore_errors=True)
    if os.path.isdir(rdir):
        report("  could not remove Backup/%s; it will be tidied up on the next "
               "run" % ROLLBACK_DIR)
        return False
    p = tx_path(backup)
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError as e:
        report("  could not remove %s: %s" % (TX, e))
        return False
    return True


def describe(tx):
    """A read-only account of an interrupted transaction."""
    done = [s for s in tx["steps"] if s["state"] == "done"]
    left = [s for s in tx["steps"] if s["state"] != "done"]
    return dict(version=tx.get("patch_version"), started=tx.get("started"),
                phase=tx.get("phase"), committed=committed(tx),
                done=done, pending=left)


def _range_token(path, step):
    """The hash of the byte range a `range` step covers, or None."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        f.seek(step["offset"])
        blob = f.read(step["size"])
    if len(blob) != step["size"]:
        return None
    return hashlib.sha256(blob).hexdigest()


def _place(src, dst, want, rel, spool):
    """Puts src at dst without ever leaving dst half-written.

    A copy of its own, verified, then one os.replace.  Writing straight onto dst
    meant a step that was cut short left a partial file -- and a partial file is
    neither version, which the retry then had to make sense of.  Interrupted
    here, dst is either untouched or complete.

    The copy is made inside `spool`, which is Backup/rollback: a directory this
    patch owns and already clears when the transaction is over.  It used to be
    dst + a fixed suffix, removed first if something was already there -- and
    O_EXCL protects the creation, not that removal, so a file of that name we
    had never written was deleted.  Nothing is claimed by its name here: the only
    path removed is the one mkstemp just made.
    """
    os.makedirs(spool, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=spool, prefix="undo-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
            shutil.copyfileobj(f, out)
            out.flush()
            os.fsync(out.fileno())
        if sha256(tmp) != want:
            return ("%s: the copy did not come out right; the disk may be full"
                    % rel)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    if sha256_or_none(dst) != want:
        return "%s: it did not read back as the copy just written" % rel
    return None


def _copy_back(keep, dst, want, rel, spool):
    """Restores dst from a copy, verifying the copy, the write and the result.

    Returns None on success or the reason it stopped.  None of the three is
    optional: a missing copy used to be skipped silently, a damaged one used to
    be written over the target, and the write itself used to go straight onto
    the target -- and all three reported success.
    """
    if not keep or not os.path.exists(keep):
        return ("%s: the copy of the version installed before it is missing, so "
                "it cannot be put back" % rel)
    if sha256(keep) != want:
        return ("%s: the copy of the version installed before it is damaged "
                "(%s..., expected %s...)"
                % (rel, sha256(keep)[:12], str(want)[:12]))
    return _place(keep, dst, want, rel, spool)


def _undo(game, backup, step, report):
    """Undoes one step.  None if it is back as it was, else why it stopped."""
    rel = step["rel"]
    dst = os.path.join(game, rel)
    rdir = rollback_dir(backup)
    keep = os.path.join(rdir, step["rollback"]) if step.get("rollback") else None
    before, after = step["before_sha256"], step["after_sha256"]
    kind = step["kind"]

    if kind == "record_only":
        return None                      # nothing on disk; the record is below

    if kind == "range":
        if not os.path.exists(dst):
            return ("%s is not there, so the bytes this install changed cannot "
                    "be put back" % rel)
        if _range_token(dst, step) == before:
            return None                  # already as it was
        # Anything else gets the recorded bytes written back, including a write
        # that was cut short and left neither state -- that is the case that
        # most needs repairing, so it must not be skipped as "unexplained".
        if not keep or not os.path.exists(keep):
            return "%s: the copy of the bytes it replaced is missing" % rel
        with open(keep, "rb") as f:
            blob = f.read()
        if (len(blob) != step["size"]
                or hashlib.sha256(blob).hexdigest() != before):
            return "%s: the copy of the bytes it replaced is damaged" % rel
        with open(dst, "r+b") as f:
            f.seek(step["offset"])
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        if _range_token(dst, step) != before:
            return "%s: the bytes did not read back as they were" % rel
        report("  put back the bytes in %s" % rel)
        return None

    token = sha256_or_none(dst)
    if token == before:
        # Nothing to sweep up next to the target: both installing and undoing
        # spool their copy inside Backup/rollback, which the transaction clears.
        # Deleting files in the game folder because their name looked like ours
        # was the same mistake as adopting a cielzh.dll we had not written.
        return None                      # already as it was, or never done

    if kind == "backup_file":
        # One of our own files under Backup/: put back exactly what was there,
        # or take it away again if there was nothing.
        if before is None:
            os.remove(dst)
            if os.path.exists(dst):
                return "%s: could not be removed" % rel
            report("  removed %s" % rel)
            return None
        bad = _copy_back(keep, dst, before, rel, rdir)
        if bad:
            return bad
        report("  put %s back" % rel)
        return None

    if kind == "created":
        # token is None here means the file has gone missing since -- and since
        # before is not None (that case matched above), the version installed
        # before it belongs back at that path.  There is nothing there to
        # destroy, so putting it back is safe as well as right.
        if token == after or token is None:
            if before is None:
                os.remove(dst)
                if os.path.exists(dst):
                    return "%s: could not be removed" % rel
                report("  removed %s" % rel)
                return None
            # An upgrade.  A missing copy must never be read as "we created this
            # file", which deletes the version the player had working.
            bad = _copy_back(keep, dst, before, rel, rdir)
            if bad:
                return bad
            report("  put %s back" % rel)
            return None
        # Neither version.  This used to be let through for a step that had not
        # been marked done, on the grounds that we could not have written it --
        # but an undo that was itself interrupted could, and then a partial DLL
        # was reported as "left untouched" and the recovery data deleted.  Both
        # our install and our undo replace the file in one step, so anything
        # else needs a person to look at it.
        return ("%s is neither the version this install replaced nor the one it "
                "installed, so it was left exactly as it is.\n"
                "  Move that file aside (or delete it) and run the installer "
                "again." % rel)

    if kind == "created_remove":
        if token is None:
            bad = _copy_back(keep, dst, before, rel, rdir)
            if bad:
                return bad
            report("  put %s back" % rel)
            return None
        return ("%s is not the file this install removed, so it was left as it "
                "is" % rel)

    bad = _copy_back(keep, dst, before, rel, rdir)     # a whole replaced file
    if bad:
        return bad
    report("  put %s back" % rel)
    return None


def roll_back(game, backup, tx, report=print):
    """Puts back everything the transaction recorded, verifying each step.

    Keeps its own records if it cannot finish -- clearing them first would throw
    away the only information a later attempt has.  The ownership record is
    moved back one step at a time, and only for the steps that really did come
    back: announcing the record of a file that is still the new version made the
    next run refuse for the wrong reason.
    """
    if committed(tx):
        raise Stop("that install had already finished (phase=done); it is not "
                   "undone here.")
    rec = load_record(backup)
    failed = []
    # Reverse order: later steps are undone before the ones they were built on.
    for step in reversed(tx["steps"]):
        try:
            why = _undo(game, backup, step, report)
        except OSError as e:
            why = "%s: %s" % (step["rel"], e)
        if why:
            failed.append(why)
            continue
        if "before_record" in step:
            if step["before_record"] is None:
                rec["files"].pop(step["rel"], None)
            else:
                rec["files"][step["rel"]] = step["before_record"]
    save_record(backup, rec)

    if failed:
        for why in failed:
            report("  %s" % why)
        report("  nothing else was changed. %s and Backup/%s are left in place "
               "for the next run." % (TX, ROLLBACK_DIR))
        return False
    cleanup(backup, report)
    return True


def verify_committed(game, tx):
    """After a committed install: the files it recorded that no longer match.

    Informational.  A file changed after the install finished is the ownership
    check's business; it is not a reason to undo an install that happened.
    """
    odd = []
    for step in tx["steps"]:
        want = step["after_sha256"]
        if step["kind"] == "record_only" or want is None:
            continue
        dst = os.path.join(game, step["rel"])
        token = (_range_token(dst, step) if step["kind"] == "range"
                 else sha256_or_none(dst))
        if token != want:
            odd.append(step["rel"])
    return odd


# --- planning the created files ----------------------------------------------
def plan(game, backup, built, version, loader_enabled=True, record=None,
         report=print):
    """What to do with each created file.  Reads only; raises Stop to refuse."""
    rec = record if record is not None else load_record(backup)
    actions = []
    for name, rel in CREATED:
        dst = os.path.join(game, rel)
        known = rec["files"].get(rel)
        here = sha256_or_none(dst)

        if not loader_enabled:
            if known is None:
                if here is not None:
                    report("  %-26s left alone (not installed by us)" % rel)
                continue
            if here is None:
                report("  %-26s already gone" % rel)
                actions.append(dict(rel=rel, src=None, dst=dst, new_hash=None,
                                    mode="forget", old_hash=None,
                                    old_record=known))
                continue
            # The record alone is not permission to delete.  Removing a file
            # somebody has replaced is the same mistake as overwriting one.
            if here != known.get("installed_sha256"):
                raise Stop("%s is not the copy this patch installed, so it will "
                           "not be removed (%s... on disk, %s... recorded).\n"
                           "  Nothing was changed."
                           % (rel, here[:12],
                              str(known.get("installed_sha256"))[:12]))
            actions.append(dict(rel=rel, src=None, dst=dst, new_hash=None,
                                mode="remove", old_hash=here,
                                old_record=known))
            continue

        src = built.get(name)
        if not src or not os.path.exists(src):
            raise Stop("this build has the display layer enabled but did not "
                       "produce %s.\n  Nothing was changed." % name)
        new_hash = sha256(src)

        if here is None:
            # Said out loud: a dry run that lists every file it replaces and
            # nothing about the one it adds is not a full account of the install.
            report("  %-26s %-10s -> new file (the display layer)"
                   % (rel, "%.1f MB" % (os.path.getsize(src) / 1e6)))
            actions.append(dict(rel=rel, src=src, dst=dst, new_hash=new_hash,
                                mode="create", old_hash=None,
                                old_record=known))
            continue
        if known is None:
            raise Stop("%s is already in the game folder and this patch has no "
                       "record of putting it there.\n"
                       "  Nothing was changed. Move that file aside if it is "
                       "not needed, or tell us about it." % rel)
        if here != known.get("installed_sha256"):
            raise Stop("%s is not the copy this patch installed (%s... on disk, "
                       "%s... recorded).\n  Nothing was changed."
                       % (rel, here[:12],
                          str(known.get("installed_sha256"))[:12]))
        if here == new_hash:
            report("  %-26s already this build" % rel)
            actions.append(dict(rel=rel, src=src, dst=dst, new_hash=new_hash,
                                mode="current", old_hash=here,
                                old_record=known))
            continue
        report("  %-26s %s -> %s" % (rel, known.get("patch_version"), version))
        actions.append(dict(rel=rel, src=src, dst=dst, new_hash=new_hash,
                            mode="replace", old_hash=here, old_record=known))
    return rec, actions


def register(txn, actions):
    """Puts every created-file step into `txn` before the install begins.

    apply_one() used to add its own step on the way past, so the transaction on
    disk said nothing about the DLL until after the DLL had been replaced and
    the ownership record saved.  A process killed in that window came back to an
    executable put back to the old version, a DLL left at the new one, a record
    still naming the old one -- and the transaction deleted.
    """
    for act in actions:
        mode = act["mode"]
        if mode == "current":
            act["step"] = None
        elif mode == "forget":
            # No file to put back, but the record changes, and that has to be
            # undoable as well.
            act["step"] = txn.add("record_only", act["rel"], None, None,
                                  extra={"before_record": act["old_record"]})
        elif mode == "remove":
            act["step"] = txn.add("created_remove", act["rel"],
                                  act["old_hash"], None, save_path=act["dst"],
                                  extra={"before_record": act["old_record"]})
        else:                                        # create, replace
            act["step"] = txn.add(
                "created", act["rel"], act["old_hash"], act["new_hash"],
                save_path=act["dst"] if mode == "replace" else None,
                extra={"before_record": act["old_record"]})
    return actions


def apply_one(game, backup, rec, action, version, txn, report=print):
    """Carries out one created-file step that register() already recorded."""
    rel, dst = action["rel"], action["dst"]
    mode = action["mode"]
    if mode == "current":
        return False
    if "step" not in action:
        raise Stop("internal: %s was not registered before the install began"
                   % rel)
    step = action["step"]

    if mode == "forget":
        rec["files"].pop(rel, None)
        save_record(backup, rec)
        txn.mark(step)
        report("  forgot %s (it was already gone)" % rel)
        return True

    # Checked again here, not only at plan time: the folder may have changed in
    # between, and both removing and replacing must refuse to act on a file that
    # is no longer the one we recorded.
    here = sha256_or_none(dst)
    if mode in ("replace", "remove") and here != action["old_hash"]:
        raise Stop("%s changed while installing; stopping" % rel)
    if mode == "create" and here is not None:
        raise Stop("%s appeared while installing; stopping" % rel)

    if mode == "remove":
        os.remove(dst)
        rec["files"].pop(rel, None)
        save_record(backup, rec)
        txn.mark(step)
        report("  removed %s" % rel)
        return True

    # The same spooled, verified, one-os.replace write the undo uses.  It used to
    # copy to dst + ".cielzh-new", which was left behind if the copy failed and
    # was then deleted by name on the way out.
    bad = _place(action["src"], dst, action["new_hash"], rel, txn.dir)
    if bad:
        raise Stop(bad)
    rec["files"][rel] = dict(existed_before=False,
                             installed_sha256=action["new_hash"],
                             patch_version=version)
    save_record(backup, rec)
    txn.mark(step)
    report("  installed %s" % rel)
    return True


def remove_all(game, backup, report=print):
    """Uninstall: removes only what still matches what we last wrote."""
    try:
        rec = load_record(backup)
    except Stop as e:
        report("  %s" % e)
        return 0, 1
    removed = left = 0
    for _name, rel in CREATED:
        known = rec["files"].get(rel)
        dst = os.path.join(game, rel)
        if known is None:
            if os.path.exists(dst):
                report("  leaving %s alone: no record that we installed it" % rel)
                left += 1
            continue
        if not os.path.exists(dst):
            report("  %s is already gone" % rel)
        elif sha256(dst) != known.get("installed_sha256"):
            report("  leaving %s alone: it is not the copy we installed" % rel)
            left += 1
            continue
        else:
            os.remove(dst)
            report("  removed %s" % rel)
            removed += 1
        rec["files"].pop(rel, None)
        save_record(backup, rec)
    return removed, left
