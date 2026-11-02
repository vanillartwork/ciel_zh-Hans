# -*- coding: utf-8 -*-
"""Read cielzh-trace.txt, the record-only display layer's own output.

  py -3 read_trace.py <cielzh-trace.txt> [--texts N]

Stage one has to answer four things, and reading a few thousand CSV rows by eye
answers none of them:

  * is the sample complete, or did something get cut off
  * which threads set and read UI text
  * which call sites do it, and how many widgets each one touches
  * does anything read text back -- and for which widgets does the text change,
    which is what decides whether a display copy can be separated from the
    original

What it cannot answer is whether a value that was read reaches a comparison.
The records say that it was read and from where; the caller addresses printed
here are the ones worth disassembling next.  Nothing below should be read as
evidence about object lifetime either: an id identifies an address, and a widget
freed with another allocated at the same address shares one.
"""
import sys, io, csv, collections

BASE_HINT = 0x140000000     # the image base the RVAs are relative to


def load(path):
    head, rows = [], []
    with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
        for line in f:
            if line.startswith("#"):
                head.append(line.rstrip("\n"))
            else:
                break
        rdr = csv.DictReader(f, fieldnames=[
            "first_seq", "last_seq", "op", "class", "thread", "object", "obs",
            "caller_rva", "hits", "truncated", "text"])
        first = True
        for r in rdr:
            if first and r["first_seq"] == "first_seq":
                first = False
                continue
            first = False
            if not r["first_seq"]:
                continue
            for k in ("first_seq", "last_seq", "thread", "obs", "hits"):
                r[k] = int(r[k] or 0)
            r["object"] = int(r["object"] or "0", 16)
            r["caller_rva"] = int(r["caller_rva"] or "0", 16)
            r["truncated"] = r["truncated"] == "1"
            rows.append(r)
    return head, rows


def field(head, name):
    for line in head:
        for part in line.lstrip("# ").split():
            if part.startswith(name + "="):
                return part[len(name) + 1:]
    return None


def main(argv):
    rest = list(argv[1:])
    ntexts = 6
    if "--texts" in rest:
        i = rest.index("--texts")
        ntexts = int(rest[i + 1])
        del rest[i:i + 2]            # the value is not a second file
    args = [a for a in rest if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    head, rows = load(args[0])

    print("=== 这份记录是怎么来的")
    for line in head:
        print("  " + line.lstrip("# "))

    # --- completeness -------------------------------------------------------
    print("\n=== 样本是否完整")
    doubts = []
    dropped = int(field(head, "dropped") or 0)
    lost = int(field(head, "objects_lost") or 0)
    early = int(field(head, "early_calls") or 0)
    fails = int(field(head, "auto_failures") or 0)
    reason = field(head, "reason")
    if dropped:
        doubts.append("有 %d 次调用没能记下（表满）。下面所有数字都是下限，不是总数。"
                      % dropped)
    if lost:
        doubts.append("有 %d 个地址没能跟踪（地址表满），它们的记录会缺少 obs。" % lost)
    if early:
        doubts.append("有 %d 次调用发生在安装完成之前：已原样转发，但没有记录。"
                      % early)
    if fails:
        doubts.append("有 %d 次自动写出失败，中间可能缺一段。" % fails)
    if reason == "auto":
        doubts.append("这份文件是游戏还在运行时自动写下的：最后一次写出之后的记录不在里面。"
                      "正常退出会再写一次（reason=exit）。")
    elif reason == "exit":
        print("  reason=exit：这是退出时写的，记录到进程结束为止。")
    if field(head, "armed") == "0":
        doubts.append("armed=0：钩子并没有装上，下面的记录不可能来自游戏的界面。")
    for d in doubts:
        print("  ! " + d)
    if not doubts:
        print("  没有发现被截断的迹象。")

    # --- the display layer ----------------------------------------------------
    display = None
    for line in head:
        if line.lstrip("# ").startswith("display="):
            display = line.lstrip("# ")
    if display is not None:
        print("\n=== 显示层")
        status = display.split(" whole=")[0][len("display="):]
        print("  状态：%s" % status)
        if status.startswith("off"):
            print("  ! 替换没有开启，屏幕上是游戏原本的文字。原因见上一行。")
        whole = int(field(head, "whole") or 0)
        names = int(field(head, "names") or 0)
        hits = int(field(head, "guard_hits") or 0)
        full = int(field(head, "guard_full") or 0)
        print("  整句替换 %d 次，名字替换 %d 次" % (whole, names))
        callers = field(head, "guard_callers") or ""
        if hits:
            print("  ! 有 %d 次读取来自界面以外的代码，已交还日文原文。调用点：%s"
                  % (hits, callers or "?"))
            print("    这是阶段一没见过的读取，值得去看那几个调用点在做什么。")
        else:
            print("  没有任何界面以外的代码读回过被替换的文字。")
        if full:
            print("  ! 有 %d 次替换因为没处记下原文而没有做，那些地方仍是日文。" % full)
    print("  记录条数 %d，其中 %d 条文字被截断（只存了前缀）。"
          % (len(rows), sum(1 for r in rows if r["truncated"])))

    if not rows:
        print("\n一条记录也没有。要么界面还没画过文字，要么钩子没有生效——"
              "先看上面的 armed 和 cielzh-loader.log。")
        return 0

    # --- threads ------------------------------------------------------------
    print("\n=== 哪些线程在写、在读")
    per = collections.defaultdict(lambda: collections.Counter())
    objs = collections.defaultdict(set)
    for r in rows:
        per[r["thread"]][r["op"]] += r["hits"]
        per[r["thread"]]["rows_" + r["op"]] += 1
        objs[r["thread"]].add(r["obs"])
    print("  %-10s %8s %8s %8s %8s %8s" %
          ("tid", "set调用", "get调用", "set条", "get条", "控件"))
    for tid in sorted(per, key=lambda t: -(per[t]["set"] + per[t]["get"])):
        c = per[tid]
        print("  %-10s %8d %8d %8d %8d %8d"
              % ("0x%x" % tid, c["set"], c["get"], c["rows_set"], c["rows_get"],
                 len(objs[tid])))
    if len(per) > 1:
        print("  多于一个线程：安装必须在主线程同步完成，钩子必须是线程安全的。")

    # --- call sites ---------------------------------------------------------
    print("\n=== 调用点（rva，加上 0x%x 是运行时地址）" % BASE_HINT)
    sites = collections.defaultdict(lambda: collections.Counter())
    site_objs = collections.defaultdict(set)
    site_text = {}
    for r in rows:
        key = (r["caller_rva"], r["op"], r["class"])
        sites[key][r["thread"]] += r["hits"]
        site_objs[key].add(r["obs"])
        site_text.setdefault(key, r["text"])
    print("  %-12s %-4s %-13s %7s %7s %6s  %s"
          % ("rva", "op", "class", "调用", "控件", "线程", "第一条文字"))
    for key in sorted(sites, key=lambda k: -sum(sites[k].values())):
        rva, op, klass = key
        print("  0x%-10x %-4s %-13s %7d %7d %6d  %s"
              % (rva, op, klass, sum(sites[key].values()), len(site_objs[key]),
                 len(sites[key]), site_text[key][:40].replace("\n", " ")))

    # --- reads --------------------------------------------------------------
    print("\n=== 读回：哪些控件被读过")
    ops = collections.defaultdict(lambda: collections.Counter())
    texts = collections.defaultdict(list)
    for r in rows:
        ops[r["obs"]][r["op"]] += r["hits"]
        if r["op"] == "set":
            texts[r["obs"]].append((r["first_seq"], r["text"]))
    read_only = [o for o in ops if ops[o]["get"] and not ops[o]["set"]]
    both = [o for o in ops if ops[o]["get"] and ops[o]["set"]]
    print("  被读过的控件 %d 个；其中 %d 个我们也见过它被写，"
          "%d 个只见读、没见写。"
          % (len(read_only) + len(both), len(both), len(read_only)))
    if read_only:
        print("  ! 只见读不见写的那些，文字来自我们没有挂钩的地方——"
              "替换显示文字时这一条路径会被漏掉。")
    if both:
        print("  ! 写完又被读回：读到的值有可能参与逻辑。要确定，就去反汇编上面"
              "那些 get 的调用点。")

    # --- text that changes --------------------------------------------------
    print("\n=== 文字变过的控件（决定原文与显示副本是否必须分开）")
    changed = []
    for o, seq in texts.items():
        uniq = []
        for _s, t in sorted(seq):
            if not uniq or uniq[-1] != t:
                uniq.append(t)
        if len(set(uniq)) > 1:
            changed.append((o, uniq))
    changed.sort(key=lambda kv: -len(kv[1]))
    if not changed:
        print("  没有控件的文字发生过变化。")
    for o, uniq in changed[:ntexts]:
        print("  obs=%d  %d 次不同的文字  get=%d"
              % (o, len(uniq), ops[o]["get"]))
        for t in uniq[:8]:
            print("      %s" % t.replace("\n", "\\n")[:70])
    if len(changed) > ntexts:
        print("  ……还有 %d 个（--texts 可以多看几个）" % (len(changed) - ntexts))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
