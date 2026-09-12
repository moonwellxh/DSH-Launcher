# -*- coding: utf-8 -*-
# =====================================================================
# guide_inject.py —— 前置导引单注入块生成（确定性，零模型判断）
# 作用: 读 references/pregen-guide.md，按命名空间与 token 预算产出「注入块」文本，
#       并按固定截断顺序给出 kept/dropped 清单（供快照记录、供沉淀端排除降权候选）。
# 输入: --ns <general|document|code|regulation> [--budget 600] [--guide <path>]
# 输出: 单行 JSON {"block":…, "kept":[…], "dropped":[…], "est_tokens":N,
#                  "budget":N, "truncated":bool, "notice":str|null, "reason":null}
#       失败: {"error":…, "hint":…} + 退出码 2（含"保底核心集仍超预算"）
# 复跑: python3 scripts/guide_inject.py --ns document --budget 600
# 依赖: Python 3.9+ 标准库
#
# 截断顺序（SKILL.md §0.3 / protocols.md 4.8，从先弃到后弃）：
#   1) 命名空间块条款，从块尾向块首
#   2) 通用块条款，从块尾向块首
#   3) 保底核心集永不截断 = 审查预告 + 通用块权重最高的 2 条（块首 2 条）
#   4) 连保底核心集都超预算 → 报错退出码 2，禁止静默注入残缺导引单
#   5) 截断粒度＝整条条款，禁止截断条款内部文字
# 「条款顺序即权重」：同一块内越靠前权重越高，故从块尾开始弃。
# =====================================================================
import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_NS = ("general", "document", "code", "regulation")
_NS_HEADING = {"general": "## 通用条款", "document": "### 文档类",
               "code": "### 代码类", "regulation": "### 规范类"}
_FIXED_HEADING = "## 审查预告"
_CLAUSE_RE = re.compile(r"^\s*-\s*\[([A-Z])-(\d{3})\]\s*(.*)$")
# 保底核心集：通用块中权重最高的 N 条（块首 N 条）永不截断
FLOOR_GENERAL = 2


def skill_root():
    return Path(__file__).resolve().parents[1]


def out_json(obj):
    print(json.dumps(obj, ensure_ascii=False))


def fail(code, error, hint=None):
    d = {"error": error}
    if hint:
        d["hint"] = hint
    out_json(d)
    sys.exit(code)


def est_tokens(text):
    """确定性 token 估算：CJK 记 1.0，其他记 0.25（≈4 字符/token）。

    不使用第三方 tokenizer（零依赖纪律），也不做启发式猜测；
    该系数对中文段落略偏保守（偏大），宁可早截断不可超预算。
    """
    cjk = 0
    other = 0
    for ch in text:
        if "\u2e80" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef":
            cjk += 1
        else:
            other += 1
    return int(round(cjk * 1.0 + other * 0.25))


def split_blocks(lines):
    """按标题切块；返回 [(heading或None, [lines…])]。"""
    blocks, cur = [], None
    for ln in lines:
        if ln.startswith("#"):
            if cur is not None:
                blocks.append(cur)
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        blocks.append(cur)
    return blocks


def find_block(blocks, heading):
    for b in blocks:
        if b and b[0].strip().startswith(heading):
            return b
    return None


def clause_lines(block):
    """取块内条款行（保持文件顺序＝权重降序）。"""
    if not block:
        return []
    return [ln for ln in block[1:] if _CLAUSE_RE.match(ln)]


def non_clause_body(block):
    """取块内非条款正文行（如审查预告的说明句），去空行。"""
    if not block:
        return []
    return [ln for ln in block[1:] if ln.strip() and not _CLAUSE_RE.match(ln)]


def clause_id(line):
    m = _CLAUSE_RE.match(line)
    return "%s-%s" % (m.group(1), m.group(2)) if m else None


def render(fixed_lines, general, ns_lines, ns_heading, dropped):
    out = []
    out.append(_FIXED_HEADING + "（固定条款，不淘汰）")
    out.extend(fixed_lines)
    out.append("")
    out.append("## 通用条款（按权重排序，沉淀机制维护）")
    out.extend(general)
    if ns_lines:
        out.append("")
        out.append(ns_heading)
        out.extend(ns_lines)
    if dropped:
        out.append("")
        out.append("（导引单按预算截断，已弃 %d 条：%s）" % (len(dropped), ", ".join(dropped)))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="前置导引单注入块生成（确定性截断）")
    ap.add_argument("--ns", required=True, choices=list(_NS))
    ap.add_argument("--budget", type=int, default=600,
                    help="token 预算；0 表示不截断（调试用）")
    ap.add_argument("--guide", default=None, help="导引单路径覆盖（默认 <技能根>/references/pregen-guide.md）")
    args = ap.parse_args()

    guide = Path(args.guide) if args.guide else (skill_root() / "references" / "pregen-guide.md")
    if not guide.exists():
        fail(2, "导引单缺失: %s" % guide, "检查 references/pregen-guide.md 是否存在")

    lines = guide.read_text(encoding="utf-8").splitlines()
    blocks = split_blocks(lines)

    fb = find_block(blocks, _FIXED_HEADING)
    if fb is None:
        fail(2, "导引单缺少 %s 小节" % _FIXED_HEADING, "审查预告为固定条款，缺失即导引单损坏")
    fixed_lines = non_clause_body(fb)

    gb = find_block(blocks, "## 通用条款")
    if gb is None:
        fail(2, "导引单缺少 ## 通用条款 小节")

    # general 命名空间的条款块**就是**通用条款块本身（_NS_HEADING["general"] 与之同名）。
    # 若在此处 find_block 取同一块，通用条款会被渲染两遍（实测 8 条→16 条、373→588 token）。
    nb = None if args.ns == "general" else find_block(blocks, _NS_HEADING[args.ns])

    general = clause_lines(gb)
    ns_lines = clause_lines(nb)

    floor = general[:FLOOR_GENERAL]
    dropped = []

    def current():
        return render(fixed_lines, general, ns_lines, _NS_HEADING[args.ns], dropped)

    # 保底核心集本身必须装得下（预算=0 视为不限制）
    floor_text = render(fixed_lines, floor, [], _NS_HEADING[args.ns], [])
    if args.budget and est_tokens(floor_text) > args.budget:
        fail(2, "保底核心集超出预算",
             "审查预告+通用条款前 %d 条 估算 %d token > 预算 %d；请上调预算或精简固定条款"
             % (FLOOR_GENERAL, est_tokens(floor_text), args.budget))

    if args.budget:
        # 截断顺序：命名空间块尾→块首，再通用块尾→块首（保底核心集除外）
        while est_tokens(current()) > args.budget:
            if ns_lines:
                dropped.insert(0, clause_id(ns_lines.pop()))
            elif len(general) > FLOOR_GENERAL:
                dropped.insert(0, clause_id(general.pop()))
            else:
                break  # 保底核心集，前面已校验装得下

    block = current()
    if args.budget and est_tokens(block) > args.budget:
        fail(2, "截断后仍超预算（不应发生）",
             "估算 %d > 预算 %d；请上报缺陷" % (est_tokens(block), args.budget))

    kept = [clause_id(x) for x in general] + [clause_id(x) for x in ns_lines]
    out_json({
        "block": block,
        "kept": kept,
        "dropped": dropped,
        "est_tokens": est_tokens(block),
        "budget": args.budget,
        "truncated": bool(dropped),
        "notice": ("（导引单按预算截断，已弃 %d 条：%s）" % (len(dropped), ", ".join(dropped))) if dropped else None,
        "reason": None,
    })


if __name__ == "__main__":
    main()
