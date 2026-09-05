# -*- coding: utf-8 -*-
# =====================================================================
# diff_scope.py —— 增量审查范围提取（FR-3，输出仅行号区间+理由，不输出原文）
# 用法:
#   python3 diff_scope.py --old <旧版文件> --new <新版文件> [--context N] [--session <sid>] [--state-dir D]
#   python3 diff_scope.py --git [--git-base <rev>] [--path <子路径>] [--context N] [--session <sid>] [--state-dir D]
# 输出: 单行 JSON {"scope":[{"file":..,"ranges":[{"start":..,"end":..,"reason":..}],"reason":..},…]}
#   ledger 未关闭项以 {"ledger_issue":id,"status":..,"anchor":..,"reason":"台账未关闭:…"} 并入 scope。
# 退出码: 0 / 2 无法对齐（文件缺失/二进制/非仓库等）
# =====================================================================
import argparse, difflib, json, os, re, subprocess, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_NS = ("general", "document", "code", "regulation")

def skill_root():
    return Path(__file__).resolve().parents[1]

def _probe_writable(p):
    try:
        p.write_text("ok", encoding="utf-8"); p.unlink(); return True
    except Exception:
        return False

def resolve_state_dir(root=None, cli=None):
    root = root or skill_root()
    if cli:
        return Path(cli)
    env = os.environ.get("ADV_REVIEW_HOME")
    if env:
        return Path(env)
    cand = root / "var"
    try:
        cand.mkdir(parents=True, exist_ok=True)  # 先建目录再探测：否则新装技能 var/ 缺失，探测必失败而永远回落 home
    except Exception:
        pass
    return cand if _probe_writable(cand / ".probe") else Path.home() / ".adversarial-review"

def out_json(obj):
    print(json.dumps(obj, ensure_ascii=False))

def fail(code, error, hint=None):
    d = {"error": error}
    if hint:
        d["hint"] = hint
    out_json(d)
    sys.exit(code)

# ---- 引用扩散用标识符（章节/条款/表图/标准号/函数名）----
_CHAPTER = re.compile(r"[第][0-9一二三四五六七八九十百千万]+(?:\s*[.．、\-]\s*[0-9一二三四五六七八九十百千万]+)*\s*[章节条款]")
_REFNUM = re.compile(r"(?:见|详|参照|依据|参见|按)\s*[第]?\d+(?:\.\d+)+")
_TABLE = re.compile(r"(?:表|图)\s*\d+(?:[-.]\d+)*")
_STD = re.compile(r"\b(?:GB|GB/T|JGJ|JGJ/T|CJJ|CJJ/T|DL|DL/T|YD|YD/T|DB)\s*\d+(?:[.\-]\d+)*")
_FUNC = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")

def extract_tokens(lines):
    """从行集合中提取可做引用扩散的标识符。"""
    toks = set()
    for ln in lines:
        for rx in (_CHAPTER, _REFNUM, _TABLE, _STD, _FUNC):
            for m in rx.finditer(ln):
                t = m.group(1) if rx is _FUNC and m.lastindex else m.group(0)
                toks.add(re.sub(r"\s+", "", t))
    return toks


def read_text(p):
    p = Path(p)
    if not p.exists():
        fail(2, "文件不存在: %s" % p)
    data = p.read_bytes()
    if b"\x00" in data[:4096]:
        fail(2, "疑似二进制文件: %s" % p, "无法对齐")
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def expand(start, end, n, total):
    """行号 1-based 闭区间 [start,end]；n=0 表示零长区间（删除点）。"""
    if n == 0:
        return (start, end)
    s = max(1, start - n)
    e = min(total, end + n)
    if s > e:
        return (start, end)
    return (s, e)


def merge_ranges(ranges):
    """合并相交/相邻区间，保留并累积理由（ranges: (start,end,reason) 三元组或二元组）。"""
    if not ranges:
        return []
    items = []
    for r in ranges:
        if len(r) == 3:
            items.append([r[0], r[1], [r[2]]])
        else:
            items.append([r[0], r[1], ["changed"]])
    items.sort(key=lambda r: (r[0], r[1]))
    out = [items[0]]
    for s, e, rs in items[1:]:
        if s <= out[-1][1] + 1:
            if e > out[-1][1]:
                out[-1][1] = e
            out[-1][2].extend(rs)
        else:
            out.append([s, e, rs])
    return [{"start": s, "end": e, "reason": "；".join(dict.fromkeys(rs))}
            for s, e, rs in out]


def in_ranges(idx, ranges):
    return any(s <= idx <= e for s, e, *_ in ranges)


def pair_scope(old_p, new_p, ctx):
    old_txt = read_text(old_p)
    new_txt = read_text(new_p)
    old_lines = old_txt.splitlines()
    new_lines = new_txt.splitlines()
    if not new_lines and not old_lines:
        return {"file": str(new_p), "ranges": [], "reason": "both-empty"}

    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    core = []             # (start,end,reason) 未扩展核心变更区间（新文件坐标，1-based）
    diff_src_lines = []   # 参与变更的行（新旧两版），供标识符提取
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old_seg = old_lines[i1:i2]
        new_seg = new_lines[j1:j2]
        diff_src_lines.extend(old_seg)
        diff_src_lines.extend(new_seg)
        if tag == "delete":
            if j1 < len(new_lines):
                # 删除点后仍有新内容：标记其后第一行
                core.append((j1 + 1, j1 + 1, "deletion@oldL%d-%d" % (i1 + 1, i2)))
            else:
                # 删除发生于文件尾（含整文件清空）：新版无残留行可标，须在新版末尾留下
                # 审查落点，否则 ranges 为空会被误报为 no-change（删除本身即是变更）
                tail = max(1, len(new_lines))
                core.append((tail, tail, "deletion@EOF(oldL%d-%d)" % (i1 + 1, i2)))
        elif tag == "insert":
            core.append((j1 + 1, j2, "insert@oldL%d-%d" % (i1 + 1, i2)))
        else:  # replace
            core.append((j1 + 1, j2, "replace@oldL%d-%d" % (i1 + 1, i2)))
    if not core and not diff_src_lines:
        return {"file": str(new_p), "ranges": [], "reason": "no-change"}

    total = max(1, len(new_lines))
    ranges = []
    for s, e, reason in core:
        s, e = expand(s, e, ctx, total)
        if e < s:
            e = s
        ranges.append((s, e, reason))

    # 引用扩散：变更段标识符在新版其余（核心变更区之外）位置检索
    for tok in extract_tokens(diff_src_lines):
        if len(tok) < 2:
            continue
        for idx, ln in enumerate(new_lines, start=1):
            if tok in ln and not in_ranges(idx, core):
                ranges.append((idx, idx, "引用扩散:%s" % tok))

    merged = merge_ranges(ranges)
    if not merged:
        return {"file": str(new_p), "ranges": [], "reason": "no-change"}
    return {"file": str(new_p), "ranges": merged,
            "reason": "changed+context(%d)+diffusion" % ctx}


def parse_unified0(diff_text, ctx):
    """解析 `git diff --unified=0` 输出。

    返回 (files, deleted, contents)：
      files    — {file: [(start,end,reason)]}（新文件坐标）；二进制文件以 None 占位
      deleted  — 被删除文件名集合（+++ /dev/null）；其 hunk 在新版坐标下无落点，须单列
      contents — {file: [增删行文本]}，供引用扩散提取标识符（设计 4.5 第 3 步）
    """
    files, deleted, contents = {}, set(), {}
    cur = None
    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    for ln in diff_text.splitlines():
        if ln.startswith("diff --git "):
            m = re.search(r" b/(.+)$", ln)
            cur = m.group(1) if m else ln
            files.setdefault(cur, [])
        elif ln.startswith("Binary files "):
            files.setdefault(cur or "?", []).append(None)
        elif ln.startswith("+++ /dev/null"):
            if cur:
                deleted.add(cur)
        elif ln.startswith("@@"):
            m = hunk_re.match(ln)
            if not m:
                continue
            nl = int(m.group(3)); nc = int(m.group(4) or 0)
            if cur is None:
                cur = "?"
                files.setdefault(cur, [])
            if nc == 0:
                # 纯删除：影响点=删除位置两侧（新文件该行即后移内容）
                if nl >= 1:
                    files[cur].append((nl, nl, "deletion"))
            else:
                start = nl if nl > 0 else 1
                files[cur].append((start, start + nc - 1, "changed"))
        elif cur and ln[:1] in ("+", "-") and not ln.startswith(("+++", "---")):
            contents.setdefault(cur, []).append(ln[1:])
    return files, deleted, contents


def git_scope(base, subpath, ctx):
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    except Exception as e:
        fail(2, "git 不可用: %s" % e)
    if r.returncode != 0:
        fail(2, "非 git 仓库", "在 git 仓库内运行，或改用 --old/--new 文件对模式")
    # core.quotepath=false：非 ASCII 路径不按八进制转义，保证后续按名读文件
    cmd = ["git", "-c", "core.quotepath=false", "diff", "--unified=0", base, "--"]
    if subpath:
        cmd.append(subpath)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    except Exception as e:
        fail(2, "git diff 执行失败: %s" % e)
    if p.returncode != 0:
        fail(2, "git diff 失败: %s" % (p.stderr or "").strip())
    parsed, deleted, contents = parse_unified0(p.stdout, ctx)
    scope = []
    binary_files = []
    for fname, hunks in parsed.items():
        if any(h is None for h in hunks):
            binary_files.append(fname)
            continue
        if fname in deleted:
            # 被删文件无新版行号可标，但必须显式列出——删除会使引用处失效，禁止静默丢弃
            scope.append({"file": fname, "ranges": [],
                          "reason": "file-deleted(引用该文件/其条款处可能失效)"})
            continue
        core = [h for h in hunks if h is not None]
        if not core:
            continue
        # 获取新文件行数以夹逼上下文；读不到则不扩展
        total = None
        new_lines = None
        try:
            new_lines = read_text(fname).splitlines()
            total = max(1, len(new_lines))
        except Exception:
            total = None
        merged = []
        for s, e, reason in core:
            if total:
                s, e = expand(s, e, ctx, total)
            merged.append((s, e, reason))
        # 引用扩散（与文件对模式同构，设计 4.5 第 3 步）：从增删行提取标识符，
        # 检索新版核心变更区之外的位置，命中即为受影响关联段
        if new_lines is not None:
            for tok in extract_tokens(contents.get(fname) or []):
                if len(tok) < 2:
                    continue
                for idx, ln2 in enumerate(new_lines, start=1):
                    if tok in ln2 and not in_ranges(idx, core):
                        merged.append((idx, idx, "引用扩散:%s" % tok))
        scope.append({"file": fname, "ranges": merge_ranges(merged),
                      "reason": "git-diff(%s)" % base})
    if not scope and binary_files:
        fail(2, "diff 含二进制文件无法对齐", "请排除二进制文件后重试")
    for fname in binary_files:
        # 与文本变更并存时显式列出而非静默跳过
        scope.append({"file": fname, "ranges": [], "reason": "binary-skipped(无法对齐，需人工复核)"})
    return scope


def ledger_items(state_dir, sid):
    if not sid:
        return []
    p = resolve_state_dir(cli=state_dir) / "ledger" / ("%s.json" % sid)
    if not p.exists():
        return []
    try:
        ledger = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = []
    for i in ledger.get("issues", []):
        if i.get("status") in ("已确认", "修复中", "待验证"):
            items.append({"ledger_issue": i.get("id"), "status": i.get("status"),
                          "anchor": i.get("anchor"),
                          "reason": "台账未关闭:%s(%s)" % (i.get("id"), i.get("status"))})
    return items


def main():
    ap = argparse.ArgumentParser(description="增量审查范围提取（FR-3）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--old", default=None)
    g.add_argument("--git", action="store_true", dest="gitmode")
    ap.add_argument("--new", default=None)
    ap.add_argument("--git-base", default="HEAD")
    ap.add_argument("--path", default=None, help="git 模式子路径")
    ap.add_argument("--context", type=int, default=5)
    ap.add_argument("--session", default=None)
    ap.add_argument("--state-dir", default=None)
    args = ap.parse_args()

    if args.old and not args.new:
        fail(2, "缺 --new", "--old/--new 需成对给出")
    if args.gitmode and args.old:
        fail(2, "参数互斥", "--git 与 --old/--new 二选一")
    if args.context < 0:
        fail(2, "--context 不能为负")

    scope = []
    if args.old:
        scope.append(pair_scope(args.old, args.new, args.context))
    else:
        scope = git_scope(args.git_base, args.path, args.context)

    scope.extend(ledger_items(args.state_dir, args.session))
    out_json({"scope": scope, "note": "ranges 为新文件 1-based 行号区间；ledger 项无行号，按 anchor 复核"})


if __name__ == "__main__":
    main()
