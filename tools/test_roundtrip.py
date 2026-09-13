"""End-to-end safety test: rebuild without edits must be byte-identical,
and a synthetic translation must land exactly where it is supposed to."""
import sys, os, io, csv, re, random, tempfile, filecmp, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gustpak import Pak, rebuild
import csvspan

RES = sys.argv[1]
EXP = sys.argv[2]
TMP = sys.argv[3]
os.makedirs(TMP, exist_ok=True)
src = os.path.join(RES, "PACK01.PAK")
pak = Pak(src)

print("[1] no-op archive rebuild")
out = os.path.join(TMP, "PACK01_noop.PAK")
rebuild(pak, {}, out)
same = filecmp.cmp(src, out, shallow=False)
print("    identical to original:", same, "(%d bytes)" % os.path.getsize(out))
if not same:
    a = open(src, "rb").read(); b = open(out, "rb").read()
    print("    sizes", len(a), len(b))
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            print("    first diff at 0x%x" % i, a[i-8:i+8].hex(), "vs", b[i-8:i+8].hex()); break

print("[2] synthetic translation of 300 rows")
POOL = "这是一个测试文本用来验证汉化管线是否正确工作请勿当真"
rows_by_file = collections.defaultdict(list)
files = sorted(os.listdir(os.path.join(EXP, "script")))
random.seed(7)
picked = []
for fn in files[:12]:
    p = os.path.join(EXP, "script", fn)
    rows = list(csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")))
    for r in rows:
        if len(picked) < 300 and r["kind"] == "dialog" and random.random() < 0.05:
            zh = "\n".join("".join(POOL[(i * 7 + j) % len(POOL)] for j in range(min(len(l), 12)))
                           for i, l in enumerate(r["jp"].split("\n")))
            for t in set(re.findall(r'<[A-Za-z0-9_]{1,12}>', r["jp"])):
                zh = t + zh
            r["zh"] = zh
            picked.append(r)
    io.open(p, "w", encoding="utf-8-sig", newline="").close()
    with io.open(p, "w", encoding="utf-8-sig", newline="") as f:
        cw = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\r\n")
        cw.writeheader(); cw.writerows(rows)
print("    injected %d rows across %d files" % (len(picked), len(set(r['file'] for r in picked))))

os.system('py -3 "%s" "%s" "%s" --loose "%s"' % (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_text.py"),
    RES, EXP, os.path.join(TMP, "loose")))

print("[3] verify")
ok = bad = 0
byfile = collections.defaultdict(list)
for r in picked:
    byfile[r["file"]].append(r)
for path, rs in byfile.items():
    real = pak.get(path).name.strip("\\").replace("\\", os.sep)
    dst = os.path.join(TMP, "loose", real)
    d = io.open(dst, "rb").read()
    t = d[3:].decode("utf-8") if d.startswith(b"\xef\xbb\xbf") else d.decode("utf-8")
    spans = {(a, b): (s, e) for a, b, s, e in csvspan.scan(t)}
    for r in rs:
        s, e = spans[(int(r["row"]), int(r["col"]))]
        got = csvspan.unquote(t[s:e])
        if got == r["zh"]:
            ok += 1
        else:
            bad += 1
            if bad < 4:
                print("    MISMATCH", r["key"], repr(got[:40]), "!=", repr(r["zh"][:40]))
    # untouched cells must still equal the originals
    e0 = pak.get(path)
    od = pak.read(e0)
    ot = od[3:].decode("utf-8") if od.startswith(b"\xef\xbb\xbf") else od.decode("utf-8")
    orig = {(a, b): csvspan.unquote(ot[s:e]) for a, b, s, e in csvspan.scan(ot)}
    now = {(a, b): csvspan.unquote(t[s:e]) for a, b, s, e in csvspan.scan(t)}
    changed = {k for k in orig if orig.get(k) != now.get(k)}
    expect = {(int(r["row"]), int(r["col"])) for r in rs}
    if changed != expect:
        print("    CELL DRIFT in", path, "unexpected:", list(changed - expect)[:5],
              "missing:", list(expect - changed)[:5])
print("    cells correct: %d   wrong: %d" % (ok, bad))
