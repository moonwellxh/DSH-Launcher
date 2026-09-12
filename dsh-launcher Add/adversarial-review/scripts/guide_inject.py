# -*- coding: utf-8 -*-
# =====================================================================
# guide_inject.py —— 前置导引单注入块生成（确定性，零模型判断）
# 作用: 读 references/pregen-guide.md，按命名空间与 token 预算产出「注入块」文本，
#       并按固定截断顺序给出 kept/dropped 清单（供快照记录、供沉淀端排除降权候选）。
# 输入: --ns <general|document|code|regulation> [--budget 600] [--no-truncate] [--guide <path>]
# 输出: 单行 JSON {"block":…, "kept":[…], "dropped":[…], "dropped_by_block":{…},
#                  "est_tokens":N, "budget":N, "no_truncate":bool, "truncated":bool,
#                  "notice":str|null, "reason":null}
#       失败: {"error":…, "hint":…} + 退出码 2（含"保底核心集仍超预算"、"--budget 非法"）
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
#
# 预算参数语义（S1 修复，2026-09-10 独立审查发现）：
#   --budget 是"必守上限"，**必须 ≥1**；"取全集不截断"由独立开关 --no-truncate 表达。
#   早期实现用 `--budget 0` 兼作豁免，使同一参数承担两种互斥语义（既声明预算又声明无预算），
#   且负值走相反分支 —— 已废除，0/负数一律报错。
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


def render(fixed_lines, general, ns_lines, ns_heading, notice):
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
    if notice:
        out.append("")
        out.append(notice)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="前置导引单注入块生成（确定性截断）")
    ap.add_argument("--ns", required=True, choices=list(_NS))
    ap.add_argument("--budget", type=int, default=600,
                    help="token 预算，须 ≥1（注入路径的必守上限）")
    ap.add_argument("--no-truncate", action="store_true",
                    help="输出全集、不做预算截断（仅供调试/测试取全集；注入路径必须走预算截断）")
    ap.add_argument("--guide", default=None, help="导引单路径覆盖（默认 <技能根>/references/pregen-guide.md）")
    args = ap.parse_args()

    if args.budget < 1:
        fail(2, "--budget 非法: %d" % args.budget,
             "预算必须 ≥1；如需不截断请显式使用 --no-truncate"
             "（0/负数不再被当作豁免，避免同一参数承担两种互斥语义）")
    limit = None if args.no_truncate else args.budget

    guide = Path(args.guide) if args.guide else (skill_root() / "references" / "pregen-guide.md")
    if not guide.exists():
        fail(2, "导引单缺失: %s" % guide, "检查 references/pregen-guide.md 是否存在")

    # 导引单为 UTF-8；用 utf-8-sig 兼容被 PS 5.1 `Set-Content -Encoding UTF8` 写入 BOM 的情形
    # （BOM 会让首行标题匹配失效 → 整份导引单被判"缺小节"，故此处必须容错）
    lines = guide.read_text(encoding="utf-8-sig").splitlines()
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
    ns_block_present = nb is not None
    ns_orig_count = len(ns_lines)

    floor = general[:FLOOR_GENERAL]
    order = []          # 弃置顺序（先弃在前）：[(scope, clause_id), …]
    ctl = {"suppress_notice": False}

    def notice_text():
        # 截断说明**必须定长**：早期实现把被弃条款 ID 全量列出，说明文本随截断条数增长，
        # 反过来把块顶超预算，触发"截断后仍超预算"报错（自测抓出的真缺陷，2026-09-10）。
        # 被弃条款 ID 走结构化字段 dropped / dropped_by_block，注入正文只需说明规模与归属。
        if ctl["suppress_notice"] or not order:
            return None
        d_ns = sum(1 for s, _ in order if s == "ns")
        d_g = sum(1 for s, _ in order if s == "general")
        parts = []
        if d_ns:
            allgone = "（本命名空间条款全部未注入）" if d_ns == ns_orig_count else ""
            parts.append("本命名空间 %d 条未注入%s" % (d_ns, allgone))
        if d_g:
            parts.append("通用 %d 条未注入" % d_g)
        return "（导引单按预算截断：已弃 %d 条 —— %s；被弃条款 ID 见 guide_dropped）" % (len(order), "；".join(parts))

    def current():
        return render(fixed_lines, general, ns_lines, _NS_HEADING[args.ns], notice_text())

    # 保底核心集本身必须装得下
    if limit is not None:
        floor_text = render(fixed_lines, floor, [], _NS_HEADING[args.ns], None)
        if est_tokens(floor_text) > limit:
            fail(2, "保底核心集超出预算",
                 "审查预告+通用条款前 %d 条 估算 %d token > 预算 %d；请上调预算或精简固定条款"
                 % (FLOOR_GENERAL, est_tokens(floor_text), limit))

        # 截断顺序：命名空间块尾→块首，再通用块尾→块首（保底核心集除外）
        while est_tokens(current()) > limit:
            if ns_lines:
                order.append(("ns", clause_id(ns_lines.pop())))
            elif len(general) > FLOOR_GENERAL:
                order.append(("general", clause_id(general.pop())))
            else:
                break  # 保底核心集，前面已校验装得下

    # 兜底：若仅因截断说明导致超预算，弃说明而不是放弃整份注入（注入价值 > 说明完备性）
    notice_omitted = False
    if limit is not None and est_tokens(current()) > limit:
        ctl["suppress_notice"] = True
        notice_omitted = True

    block = current()
    if limit is not None and est_tokens(block) > limit:
        fail(2, "截断后仍超预算（不应发生）",
             "估算 %d > 预算 %d；请上报缺陷（保底核心集校验已通过，说明另有长度来源）"
             % (est_tokens(block), limit))

    dropped = [c for _, c in order]
    out_json({
        "block": block,
        "kept": [clause_id(x) for x in general] + [clause_id(x) for x in ns_lines],
        "dropped": dropped,
        "dropped_by_block": {"ns": [c for s, c in order if s == "ns"],
                             "general": [c for s, c in order if s == "general"]},
        "ns_block_present": ns_block_present,
        "est_tokens": est_tokens(block),
        "budget": args.budget,
        "no_truncate": bool(args.no_truncate),
        "truncated": bool(order),
        "notice": notice_text(),
        "notice_omitted": notice_omitted,
        "reason": None,
    })


if __name__ == "__main__":
    main()
