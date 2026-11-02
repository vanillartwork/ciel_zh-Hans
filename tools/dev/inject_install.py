# -*- coding: utf-8 -*-
"""Put each install safeguard back the wrong way, one at a time, and report which
self-test checks notice.

  py -3 tools/dev/inject_install.py            all cases
  py -3 tools/dev/inject_install.py layout     one case

A test that passes is only evidence if it fails without the fix.  Several checks
in these suites once passed for the wrong reason -- a fixture path containing
the word being searched for, a refusal arriving one step later for a different
reason -- and the only way that was found was by reverting the fix and looking.

Every case is a list of exact replacements; a missing anchor is reported, never
silently skipped.  The sources are restored from an in-memory copy after every
case, and checked for a leftover "FAULT" marker before each one.
"""
import io, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
INST = os.path.join(TOOLS, "install.py")
NF = os.path.join(TOOLS, "newfiles.py")
SUITES = ["selftest_newfiles.py", "selftest_install_flow.py"]

CASES = {
    # --no-loader deletes on the strength of the record alone.
    "remove": [(NF,
        '''            if here != known.get("installed_sha256"):
                raise Stop("%s is not the copy this patch installed, so it will "
                           "not be removed (%s... on disk, %s... recorded).\\n"
                           "  Nothing was changed."
                           % (rel, here[:12],
                              str(known.get("installed_sha256"))[:12]))
''',
        '            pass   # FAULT: deletes without checking the hash\n')],

    # Per-file cleanup: each step throws its own undo away when it succeeds.
    "scope": [(NF,
        '    txn.mark(step)\n    report("  installed %s" % rel)',
        '    txn.mark(step)\n'
        '    shutil.rmtree(txn.dir, ignore_errors=True)   # FAULT\n'
        '    report("  installed %s" % rel)')],

    # Ownership refusals go back into the forceable pile.
    "force": [(INST,
        '''    if blockers:
        print("\\nStopping without changing anything:")
        for p in blockers:
            print("  - %s" % p)
        print("\\nThese are about files this patch installs, not about which\\n"
              "version of the game you have, so --force does not apply.")
        return 1
''',
        '    problems.extend(blockers)   # FAULT: forceable again\n')],

    # Recover during the dry run, before the running check.
    "dryrun": [(INST,
        '''    pending_tx = stale_tx = None
    found_tx = None
    try:
        found_tx = newfiles.load_tx(backup)''',
        '''    pending_tx = stale_tx = None
    found_tx = None
    try:
        found_tx = newfiles.load_tx(backup)
        if found_tx and not newfiles.committed(found_tx):   # FAULT: writes
            newfiles.roll_back(game, backup, found_tx,
                               report=lambda m: None)
            found_tx = None''')],

    # Rolling back a replaced created file deletes it when the copy is missing.
    "rbcopy": [(NF,
        '''            # An upgrade.  A missing copy must never be read as "we created this
            # file", which deletes the version the player had working.
            bad = _copy_back(keep, dst, before, rel, rdir)
            if bad:
                return bad
            report("  put %s back" % rel)
            return None''',
        '''            if keep and os.path.exists(keep):   # FAULT
                shutil.copyfile(keep, dst)
            else:
                os.remove(dst)                  # FAULT: no copy means delete
            return None''')],

    # The created-file steps are registered on the way past, not up front.
    "regwindow": [
        (NF,
         '''    for act in actions:
        mode = act["mode"]
        if mode == "current":
            act["step"] = None''',
         '''    for act in actions:
        act["step"] = None          # FAULT: registered on the way past instead
    if actions:
        return actions
    for act in actions:
        mode = act["mode"]
        if mode == "current":
            act["step"] = None'''),
        (NF,
         '''        if self.data["phase"] != "planned":
            raise Stop("internal: %s was registered after the install had "
                       "already started" % rel)
        os.makedirs(self.dir, exist_ok=True)
        keep = None''',
         '''        os.makedirs(self.dir, exist_ok=True)   # FAULT: no phase guard
        keep = None'''),
        (NF,
         '''    if mode == "remove":
        os.remove(dst)''',
         '''    if mode == "remove":
        step = txn.add("created_remove", rel, here, None, save_path=dst,
                       extra={"before_record": action["old_record"]})
        os.remove(dst)'''),
        (NF,
         '    bad = _place(action["src"], dst, action["new_hash"], rel, txn.dir)',
         '''    step = txn.add("created", rel, here, action["new_hash"],
                   save_path=dst if mode == "replace" else None,
                   extra={"before_record": action["old_record"]})
    bad = _place(action["src"], dst, action["new_hash"], rel, txn.dir)'''),
    ],

    # A committed transaction is rolled back like any other.
    "commit": [
        (INST, '    if newfiles.committed(found_tx):',
               '    if False and newfiles.committed(found_tx):   # FAULT'),
        (NF,
         '''    if committed(tx):
        raise Stop("that install had already finished (phase=done); it is not "
                   "undone here.")
''',
         '    pass   # FAULT: undoes an install that had already committed\n'),
    ],

    # Rollback copies are neither required nor verified.
    "verifycopy": [(NF,
        '''    if not keep or not os.path.exists(keep):
        return ("%s: the copy of the version installed before it is missing, so "
                "it cannot be put back" % rel)
    if sha256(keep) != want:
        return ("%s: the copy of the version installed before it is damaged "
                "(%s..., expected %s...)"
                % (rel, sha256(keep)[:12], str(want)[:12]))
    return _place(keep, dst, want, rel, spool)''',
        '''    if not keep or not os.path.exists(keep):
        return None                     # FAULT: a missing copy is skipped
    return _place(keep, dst, want, rel, spool)   # FAULT: copy not verified''')],

    # The ownership record is moved back even for a step that failed.
    "recclaim": [(NF,
        '''        if why:
            failed.append(why)
            continue
        if "before_record" in step:''',
        '''        if why:
            failed.append(why)
        if "before_record" in step:     # FAULT: restored even when it failed''')],

    # The undo writes straight onto the target.
    "undoinplace": [(NF,
        '    return _place(keep, dst, want, rel, spool)',
        '''    with open(keep, "rb") as f, open(dst, "wb") as o:   # FAULT
        shutil.copyfileobj(f, o)
    if sha256_or_none(dst) != want:
        return "%s: it did not read back" % rel
    return None''')],

    # A target that is neither version is "left untouched" and called a success.
    "tornok": [(NF,
        '''        # Neither version.  This used to be let through for a step that had not
        # been marked done, on the grounds that we could not have written it --
        # but an undo that was itself interrupted could, and then a partial DLL
        # was reported as "left untouched" and the recovery data deleted.  Both
        # our install and our undo replace the file in one step, so anything
        # else needs a person to look at it.
        return''',
        '''        if step.get("state") != "done":
            report("  %s left untouched" % rel)   # FAULT
            return None
        return''')],

    # The restore plan is written outside the transaction.
    "planoutside": [(INST,
        '''        if plan:
            prel = "Backup/" + PLAN
            pfile = os.path.join(backup, PLAN)
            had = sha256(pfile) if os.path.isfile(pfile) else None
            txn.add("backup_file", prel, had, None,
                    save_path=pfile if had else None)
''',
        '        pass   # FAULT: inplace.json is not part of the transaction\n')],

    # --restore keeps the plan it read before the rollback.
    "stalerestore": [(INST,
        '        plan = load_applied_plan(backup) or plan\n',
        '        pass   # FAULT: keeps the plan read before the rollback\n')],

    # The stale folders are removed inside the transaction again.
    "staleinside": [
        (INST,
         '''    for d in STALE:
        p = os.path.join(game, d)
        if os.path.isdir(p):
            try:
                shutil.rmtree(p)
                print("removed stale %s" % d)
            except OSError as e:
                print("could not remove the stale %s folder (%s); it is ignored "
                      "by the game and can be deleted by hand" % (d, e))
''',
         '    pass   # FAULT: moved back inside the transaction, below\n'),
        (INST,
         '''        # Written last, once everything above has succeeded: this is the file
        # the uninstaller reads, and it must describe an install that happened.
        save_plan(backup, plan)''',
         '''        for d in STALE:                       # FAULT: undoes a working install
            p = os.path.join(game, d)
            if os.path.isdir(p):
                shutil.rmtree(p)
        save_plan(backup, plan)'''),
    ],

    # No gate on a build that patches a different range.
    "layout": [
        (INST, '        blockers.extend(layout_refusals(game, backup, plan))\n',
               '        pass   # FAULT: no layout gate\n'),
        (INST, '''        stops = layout_refusals(game, backup, plan)
        if stops:''',
               '''        stops = []                       # FAULT: no layout gate
        if stops:'''),
    ],

    # The gate counts a plan left over from a --restore as still installed.
    "layoutstale": [(INST,
        '''        state = range_state(game, st)
        if state != "original":
            out.append((st, state))''',
        '''        state = range_state(game, st)
        out.append((st, state))          # FAULT: "restored" counts as installed''')],

    # The gate runs before the rollback, on a state about to be replaced.
    "layoutearly": [
        (INST,
         '''    if pending_tx:
        print("  the ranges this build writes are checked against the installed\\n"
              "  patch after that is undone, which is when it can be decided")
    else:''',
         '''    blockers.extend(layout_refusals(game, backup, plan))   # FAULT: too early
    if pending_tx:
        pass
    else:'''),
        (INST, '        blockers.extend(layout_refusals(game, backup, plan))\n',
               '        pass\n'),
        (INST, '''        stops = layout_refusals(game, backup, plan)
        if stops:''',
               '''        stops = []                       # FAULT: not checked again
        if stops:'''),
    ],

    # Two states again: anything that is not the old output is "restored".
    "twostate": [(INST,
        '''    if cur == st.get("sha256_after"):
        return "patched"
    return "unknown"''',
        '''    if cur == st.get("sha256_after"):
        return "patched"
    return "original"               # FAULT: not ours, so assumed pristine''')],

    # The undo spools to a fixed name and clears whatever is there first.
    "tmpname": [(NF,
        '''    os.makedirs(spool, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=spool, prefix="undo-", suffix=".part")''',
        '''    tmp = dst + ".cielzh-undo"           # FAULT: a name, not a claim
    if os.path.exists(tmp):
        os.remove(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_BINARY", 0))''')],

    # "Already restored" sweeps up anything with a name like ours.
    "tmpsweep": [(NF,
        '''        # Nothing to sweep up next to the target: both installing and undoing
        # spool their copy inside Backup/rollback, which the transaction clears.
        # Deleting files in the game folder because their name looked like ours
        # was the same mistake as adopting a cielzh.dll we had not written.
        return None''',
        '''        for stray in (dst + ".cielzh-new", dst + ".cielzh-undo"):
            if os.path.exists(stray):
                os.remove(stray)         # FAULT: claimed by name
        return None''')],

    # A loader build without its text table installs anyway.
    "notable": [(NF,
        '''CREATED = [("cielzh.dll", "cielzh.dll"),
           ("cielzh-text.bin", "cielzh-text.bin")]''',
        '''CREATED = [("cielzh.dll", "cielzh.dll")]   # FAULT: the table is not managed''')],
}


def run_suites():
    hits = []
    for suite in SUITES:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, suite)],
                           cwd=TOOLS, capture_output=True)
        out = p.stdout.decode("utf-8", "replace")
        for line in out.splitlines():
            # the status column, not a check whose NAME ends in 失败
            if line.startswith("  ") and line.rstrip().endswith("失败"):
                hits.append(line.strip())
        if "Traceback" in out or "Traceback" in p.stderr.decode("utf-8", "replace"):
            hits.append("%s: crashed" % suite)
    return hits


def main(argv):
    names = argv[1:] or list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        print("unknown case(s): %s\ncases: %s" % (" ".join(unknown), " ".join(CASES)))
        return 2
    pristine = {p: io.open(p, encoding="utf-8").read() for p in (INST, NF)}
    for p, s in pristine.items():
        if "FAULT" in s:
            print("%s already has an injection in it; restore it first" % p)
            return 2
    missed = []
    try:
        for name in names:
            text = dict(pristine)
            bad_anchor = None
            for path, old, new in CASES[name]:
                if old not in text[path]:
                    bad_anchor = path
                    break
                text[path] = text[path].replace(old, new, 1)
            if bad_anchor:
                print("%-12s anchor missing in %s" % (name, os.path.basename(bad_anchor)))
                missed.append(name)
                continue
            for p, s in text.items():
                io.open(p, "w", encoding="utf-8", newline="").write(s)
            hits = run_suites()
            for p, s in pristine.items():
                io.open(p, "w", encoding="utf-8", newline="").write(s)
            print("%-12s %d 项失败" % (name, len(hits)))
            for h in hits[:4]:
                print("    " + h)
            if not hits:
                missed.append(name)
    finally:
        for p, s in pristine.items():
            io.open(p, "w", encoding="utf-8", newline="").write(s)
    print()
    if missed:
        print("没有被任何检查抓住：%s" % ", ".join(missed))
        return 1
    print("每个注入都至少被一项检查抓住（源文件已还原）")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
