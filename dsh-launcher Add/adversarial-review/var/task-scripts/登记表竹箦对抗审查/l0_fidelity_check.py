# -*- coding: utf-8 -*-
"""docstring: 竹箦成品表 vs 13份源docx dump 的逐格保真比对
作用: 对成品表 r4..75 的 J/K/M/O 与对应源记录表数据行做逐格比对
输入: 成品dump路径; docx dump目录; 建筑块->文件映射
输出: 差异清单(区分 仅尾部标点/空白差异 与 内容差异), 覆盖统计
复跑: python l0_fidelity_check.py ; 依赖 两目录下txt文本
"""
import re, sys, io, os

FINAL = r"D:\DeepSeekS\My Projcet\_fire_xlsx_work\dumps\final\消防隐患联合排查整治行动情况登记表 - 竹箦.txt"
DOCXDIR = r"D:\DeepSeekS\My Projcet\_fire_xlsx_work\dumps\docx"

MAPPING = [
    ("1-1(1号监舍楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-1号监舍楼-1-1）.txt"),
    ("1-2(2号监舍楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-2号监舍楼1-2）.txt"),
    ("2-1(1号厂房)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-1号厂房-2-1）.txt"),
    ("2-2(2号厂房)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-2号厂房-2-2）.txt"),
    ("2-3(六层劳务厂房)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-六层劳务厂房-2-3）.txt"),
    ("3-1(1号总仓)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-1号总仓-3-1）.txt"),
    ("3-2(制茶楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-制茶楼-3-2）.txt"),
    ("4-1(伙房)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-伙房-4-1）.txt"),
    ("8-1(会见楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-会见楼-8-1）.txt"),
    ("10-1(门楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-门楼-10-1）.txt"),
    ("17-1(样品楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-样品楼-17-1）.txt"),
    ("17-2(2#钢结构)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-2#钢结构-17-2）.txt"),
    ("18-1(办公楼)", "消防安全隐患问题排查-现场记录表（竹箦分监狱-办公楼18-1） .txt"),
]

def readp(p):
    with io.open(p, encoding="utf-8-sig") as f:
        return f.read()

def parse_final(text):
    """-> dict blockName -> list of rows(dict col->value)"""
    rows = []
    for ln in text.splitlines():
        m = re.match(r"ROW r=(\d+) : (.*)$", ln)
        if not m:
            continue
        r = int(m.group(1))
        cells = {}
        for part in m.group(2).split(" || "):
            part = part.strip()
            mm = re.match(r"^([A-P])(\d+) \(s=\d+\) = (.*)$", part)
            if mm:
                col = mm.group(1)
                if mm.group(2) == str(r):
                    cells[col] = mm.group(3)
        rows.append((r, cells))
    blocks = []
    cur = None
    for r, cells in rows:
        if r < 4:
            continue
        cells = dict(cells)
        cells["_r"] = r
        if cells.get("B"):
            if cur:
                blocks.append(cur)
            cur = {"name": cells["B"], "rows": []}
        cur["rows"].append(cells)
    if cur:
        blocks.append(cur)
    return blocks

def parse_docx(path):
    text = readp(path)
    lines = text.splitlines()
    out = []
    in_tab = False
    for ln in lines:
        if ln.strip() == "==TABLE==":
            in_tab = True
            continue
        if ln.strip() == "==END TABLE==":
            in_tab = False
            continue
        if not in_tab:
            continue
        if "序号" in ln and "问题描述" in ln:  # header
            continue
        cells = [c.strip() for c in ln.split("||")]
        if len(cells) < 6:
            continue
        seq, prof, prob, clause, photo, advice = cells[0], cells[1], cells[2], cells[3], cells[4], cells[5]
        if not prob and not prof and not clause and not advice:
            continue
        out.append({"K": prof, "J": prob, "M": clause, "O": advice})
    return out

def norm_tail(s):
    # 去掉常见单元格尾部装饰(空格/换行标记/分号/句号/图片占位)
    s = s.rstrip()
    while True:
        t = s
        for pat in (" / ", "；", "。", "[IMG]", "；/"):
            if s.endswith(pat):
                s = s[: -len(pat)].rstrip()
        if t == s:
            break
    return s.rstrip()

def main():
    final_blocks = parse_final(readp(FINAL))
    fmap = {b["name"]: b for b in final_blocks}
    content_diffs = []
    tail_diffs = []
    checked = 0
    for bname, fname in MAPPING:
        src = parse_docx(os.path.join(DOCXDIR, fname))
        fb = fmap[bname]
        frows = fb["rows"]
        n = min(len(src), len(frows))
        if len(src) != len(frows):
            content_diffs.append(("【行数不一致】%s 源=%d 成品=%d" % (bname, len(src), len(frows)), ""))
        # 对齐: 优先按 J 逐字(先去尾)配对, 否则按顺序
        used = set()
        for i, srow in enumerate(src):
            target = None
            for j, frow in enumerate(frows):
                if j in used:
                    continue
                if norm_tail(frow.get("J", "")) == norm_tail(srow["J"]) and srow["J"]:
                    target = j
                    break
            if target is None:
                for j, frow in enumerate(frows):
                    if j not in used and norm_tail(frow.get("J", "")):
                        target = j
                        break
            if target is None:
                content_diffs.append(("【无对齐目标】%s 源第%d行 J=%r" % (bname, i + 1, srow["J"][:20]), ""))
                continue
            used.add(target)
            frow = frows[target]
            checked += 1
            for col in ("J", "K", "M", "O"):
                a = srow.get(col, "")
                b = frow.get(col, "")
                if a == b:
                    continue
                if norm_tail(a) == norm_tail(b):
                    tail_diffs.append("%s 块成品r=%s %s列: 仅尾部差异 源=%r 成=%r" % (bname, frow.get("_r", "?"), col, a[-18:], b[-18:]))
                else:
                    content_diffs.append(("%s 块成品r=%s %s列 内容差异\n    源=%r\n    成=%r" % (bname, frow.get("_r", "?"), col, a, b), srow["J"][:30]))
    print("== 覆盖行数:", checked, "/ 源总行数统计见上 ==")
    print("\n===== 内容差异 (%d) =====" % len(content_diffs))
    for d in content_diffs:
        print("-", d[0])
    print("\n===== 仅尾部差异 (%d) =====" % len(tail_diffs))
    for d in tail_diffs:
        print("-", d)

if __name__ == "__main__":
    main()
