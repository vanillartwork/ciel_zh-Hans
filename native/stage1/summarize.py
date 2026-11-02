# -*- coding: utf-8 -*-
"""Turn a stage-one cdb log into the ordering and per-thread tables.

  py -3 summarize.py <log>

Reading these by eye is how "the main thread joined in later" gets missed, so
the counting is done here.  The totals printed at the end are the ones the run
is allowed to claim; anything a quota cut off is reported as cut off rather
than silently dropped.
"""
import sys, io, re, collections

ORDER = re.compile(r"^\[(\d+)\]\s+(\S+)[^\n]*?tid=([0-9a-fA-F]+)\s+main=(\d)")
QUOTA = re.compile(r"^\[(SET|GET)\s+t(\d)\s+(\d+)/(\d+)\s+call#(\d+)\]\s+"
                   r"tid=([0-9a-fA-F]+)\s+main=(\d)(?:\s+text=(.*))?$")
INIT = re.compile(r"INIT_CALL\s+\S+\s+hit\s+#(\d+)")
TOTALS = re.compile(r"^SET total=(\d+)\s+GET total=(\d+)")
OVERFLOW = re.compile(r"^calls from a 5th thread onward[^:]*:\s*(\d+)")
SLOTS = re.compile(r"^thread slots:\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    text = io.open(argv[1], encoding="utf-8", errors="replace").read()

    order, threads, init_hits = [], collections.defaultdict(
        lambda: collections.Counter()), 0
    samples = collections.defaultdict(list)
    totals = overflow = slots = None
    for line in text.splitlines():
        line = line.strip()
        m = TOTALS.match(line)
        if m:
            totals = (int(m.group(1)), int(m.group(2)))
            continue
        m = OVERFLOW.match(line)
        if m:
            overflow = int(m.group(1))
            continue
        m = SLOTS.match(line)
        if m:
            slots = [g for g in m.groups() if g != "0"]
            continue
        m = ORDER.match(line)
        if m:
            order.append((int(m.group(1)), m.group(2), m.group(3), m.group(4) == "1"))
            h = INIT.search(line)
            if h:
                init_hits = max(init_hits, int(h.group(1)))
            continue
        m = QUOTA.match(line)
        if m:
            op, _, used, cap, _, tid, is_main, txt = m.groups()
            threads[tid][op] += 1
            threads[tid]["main"] = 1 if is_main == "1" else 0
            threads[tid][op + "_cap"] = int(cap)
            threads[tid][op + "_used"] = max(threads[tid][op + "_used"], int(used))
            if txt and len(samples[tid]) < 6:
                samples[tid].append("%s %s" % (op, txt))

    print("== 首次发生顺序 ==")
    for n, what, tid, is_main in order:
        print("  %3d  %-34s tid=%-6s %s" % (n, what, tid, "主线程" if is_main else "后台"))

    print("\n== INIT_CALL 命中次数 ==")
    print("  %d  %s" % (init_hits,
                        "（本次运行未重复）" if init_hits <= 1 else "【会重复执行】"))

    print("\n== 按线程统计的文字调用 ==")
    if not threads:
        print("  无（普通版脚本只记录首次调用，线程统计需要 -Threads）")
    for tid, c in sorted(threads.items(), key=lambda kv: -(kv[1]["SET"] + kv[1]["GET"])):
        tag = "主线程" if c["main"] else "后台"
        cut = []
        for op in ("SET", "GET"):
            if c[op + "_cap"] and c[op + "_used"] >= c[op + "_cap"]:
                cut.append(op)
        note = ("  配额已用尽：%s（实际调用更多）" % "、".join(cut)) if cut else ""
        print("  tid=%-6s %-6s SET=%-4d GET=%-4d%s" % (tid, tag, c["SET"], c["GET"], note))
        for s in samples[tid]:
            print("      %s" % s[:90])

    mains = [t for t, c in threads.items() if c["main"]]
    if threads:
        print("\n== 结论 ==")
        if totals:
            print("  调用总数（不受配额影响）：SET=%d  GET=%d" % totals)
        else:
            print("  调用总数：未知——日志里没有结束时的汇总行。")
            print("  （游戏未经 RtlExitUserProcess 退出，或用的是旧版脚本）")
        seen = len(slots) if slots is not None else len(threads)
        print("  占到槽位的线程数：%d" % seen)
        if overflow is None:
            print("  第 5 个及以后线程的调用数：未知——同上。")
        elif overflow:
            print("  【第 5 个及以后的线程也调用了文字函数：%d 次，无调用栈】" % overflow)
        else:
            print("  第 5 个及以后的线程：无")
        print("  主线程是否参与：%s" % ("是" if mains else "否（本次运行中）"))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
