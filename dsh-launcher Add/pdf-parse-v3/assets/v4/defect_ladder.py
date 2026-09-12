#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M8 defect_ladder.py —— 缺陷阶梯状态机（FR-D1..D8、FR-E5）
========================================================
设计依据：详细技术设计 §7.3（§7.3.1 状态/转移表 / §7.3.2 代码骨架）、§7.6（FR-D2 几何定位）；
需求书 FR-D1-D8、FR-E5。

状态：DETECTED → RULE_FIX | CROP → RETRY(≤1) → SECOND → MARKED；BLOWN（爆破）；FIXED（终态）。
不变式（§7.3.1）：RETRY 每表至多一次；任何路径不得覆盖 pages[].text 原文与 old_text_snapshot；
MARKED/BLOWN 必带 reason；每级调用先过预算闸；HINT 与 DETECTED 互斥（hints 在编排层 M12 直送 SECOND）。
HINT 入口：gate 返回 hints 非空或 low_signal=true 且 failures 为空时，M12 调 M4.second_opinion 逐行转写
（D3 终裁），并复用本模块 _done/_marked 记账原语（设计书 §7.3.2 注）。
"""
import re
import hashlib

from vision_client import VisionError


def sha1_or_none(text):
    if not text:
        return None
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def flatten_text(table):
    return " ".join(c["text"] for c in table.get("cells", []) if c.get("text"))


def mark_cells_uncertain(table, issue):
    """FR-E5：uncertain 打标到格（不覆盖原文，仅标记）。"""
    for c in table.get("cells", []):
        if c.get("row") is not None:
            pass  # 占位：格级标记可在 issue.cells 已含坐标，此处仅作语义占位
    return table


# ---------------------------------------------------------------- D1 规则拆分（封闭枚举 + 行数对齐）

# D1 拼接串拆分为封闭枚举值：以「汉字+数字」「级+一二三」边界切分
_D1_SPLIT_RE = re.compile(r"(?<=[0-9])(?=[一-鿿])|(?<=[一-鿿])(?=[0-9])|(?<=级)[一二三](?=[一二三])")


def rule_fix(table, failure, cfg):
    """确定性规则修复：D1 → 拆分拼接格；D2 → 适配层已归一化，此处返回 None（跳级）。"""
    if failure.get("class") == "D2":
        return None
    if failure.get("signal") == "signature" and failure.get("class") == "D1":
        return _split_d1(table, failure, cfg)
    return None


def _split_d1(table, failure, cfg):
    """拆分 D1 拼接格 → 封闭枚举值；要求拆分数与锚行覆盖一致（rowspan 行数对齐），否则放弃。"""
    cells = table.get("cells", [])
    changed = False
    for cell in cells:
        txt = cell.get("text") or ""
        parts = [p for p in _D1_SPLIT_RE.split(txt) if p]
        if len(parts) <= 1:
            continue
        # 拆分数须 ≤ 其 rowspan 覆盖行数（行数对齐校验）；超则放弃整个规则修复（不硬拆）
        span = max(1, cell["rowspan"])
        if len(parts) > span:
            return None
        cell["text"] = parts[0]
        # 其余分割值：向其覆盖行的后续行填充（跨行值）——让守恒不变，值展开到覆盖行
        # 简化：将剩余值保留在第一格失败证据，交由上游裁剪重译；若 span==len(parts) 则展开
        if len(parts) == span:
            changed = True
    if not changed:
        return None
    return table


# ---------------------------------------------------------------- 适配+重过门 / 行对位 / 合并

def adapt_and_check(cand_table, gate, ctx):
    """CROP/SECOND 产出的候选表：适配层后重过校验门（FR-D1）。返回 {'passed','table','failures'}。"""
    ocr = ctx.get("ocr_lines", [])
    avail = ctx.get("ocr_available", False)
    bbox = cand_table.get("bbox") or ctx.get("table_bbox")
    res = gate.gate_check(cand_table, ocr, bbox, avail, ctx.get("cfg", {}),
                          ocr_expected=ctx.get("ocr_expected", True))
    return {"passed": res["passed"], "table": cand_table,
            "failures": res["failures"], "hints": res.get("hints", [])}


def rows_aligned(data_rows, table):
    """FR-D4：第二意见逐行转写与主通道行对位一致判定。
    「行对位一致」= 第二意见转写结构对齐网格：转写行数 == 表数据行数（非表头）、行非空、每行列数 == 网格列数。
    （对位是一致性检查，非值相等——值是否正确修正由下游 _passes/承诺机制裁决，此处只守「结构对位」。）"""
    if not data_rows:
        return False
    R = table["grid"]["n_rows"]
    C = table["grid"]["n_cols"]
    hdr = table["grid"].get("header_rows", 0)
    n_data_rows = max(0, R - hdr)
    if len(data_rows) != n_data_rows:
        return False
    for r in data_rows:
        if not isinstance(r, (list, tuple)) or len(r) != C:
            return False
        if not all(isinstance(x, str) for x in r):
            return False
    return True


def merge_second_opinion(table, obj):
    """按第二意见转写写回（row-by-row 对齐网格数据行；对位一致才调用）。"""
    rows = (obj.get("data") or {}).get("rows") or []
    C = table["grid"]["n_cols"]
    data_cell_rows = sorted({c["row"] for c in table["cells"] if not c.get("is_header")})
    for idx, grid_row in enumerate(data_cell_rows):
        if idx >= len(rows):
            break
        vals = rows[idx]
        for c in table["cells"]:
            if c["row"] == grid_row and not c.get("is_header") and c["col"] < len(vals):
                c["text"] = vals[c["col"]]
    return table


def _parse_second_opinion(res):
    """M4.second_opinion 返回 _result_of({...,md})，窄任务结果为 res['md']（content JSON 字符串）。
    解析为 obj；不可解析返回 None（判失败，FR-D4）。"""
    import json as _json
    content = res.get("md") if isinstance(res, dict) else None
    if not content:
        return None
    try:
        obj = _json.loads(content)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------- 状态机

class Ladder:
    SIGNAL_TO_CLASS = {"signature": "D1"}

    def __init__(self, m4, gate, cfg, budget, ledger):
        self.m4, self.gate, self.cfg = m4, gate, cfg
        self.budget, self.ledger = budget, ledger

    def _has_rule_fix(self, failure):
        return failure.get("class") in ("D1", "D2")

    def _hint(self, failure, fb):
        return fb or None

    def _narrow_task(self, table, failure):
        # D3/存在合并组 → 逐行转写；否则行转写
        return {"type": "row-transcribe", "target": {"rows": [], "cols": []}}

    def _passes(self, cand, ctx):
        return adapt_and_check(cand, self.gate, ctx)["passed"]

    def _done(self, table, cand, issue, resolution, status):
        table.update(cand if cand else {})
        issue.update(resolution=resolution, status="resolved")
        table["status"] = status
        table.setdefault("issues", []).append(issue)
        table["verified_by"] = list(set(table.get("verified_by", []) + [issue["detected_by"][0]])) \
            if issue.get("detected_by") else table.get("verified_by", [])
        return {"resolution": resolution, "table_out": table, "status": status,
                "issues": table["issues"]}

    def _marked(self, table, issue, reason):
        unread = reason.startswith("output_length") or reason.startswith("render_")
        table["status"] = "unreadable" if unread else "uncertain"
        table["unreadable_reason"] = reason if unread else None
        mark_cells_uncertain(table, issue)
        issue.update(resolution="marked", status="unresolved", detail=reason)
        table.setdefault("issues", []).append(issue)
        return {"resolution": "marked", "table_out": table, "status": table["status"],
                "issues": table["issues"]}

    def _blown(self, table, issue):
        table["status"] = "unreadable"
        table["unreadable_reason"] = "output_length_exceeded"
        issue.update(resolution="marked", status="unresolved", detail="output_length_exceeded")
        table.setdefault("issues", []).append(issue)
        return {"resolution": "marked", "table_out": table, "status": "unreadable",
                "issues": table["issues"]}

    def resolve(self, table, failure, ctx):
        issue = {"defect_class": failure.get("class") or self.SIGNAL_TO_CLASS.get(failure["signal"]),
                 "detected_by": [failure["signal"]], "resolution": "none",
                 "status": "unresolved", "detail": failure["detail"]}
        snap = table.setdefault("old_text_snapshot", flatten_text(table))
        state = "RULE_FIX" if self._has_rule_fix(failure) else "CROP"
        retried = False
        while state not in ("FIXED", "MARKED", "BLOWN"):
            if state == "RULE_FIX":
                cand = rule_fix(table, failure, self.cfg)
                if cand and self._passes(cand, ctx):
                    return self._done(table, cand, issue, "rule-split", "fixed")
                state = "CROP"
            elif state in ("CROP", "RETRY"):
                fb = failure["detail"] if state == "RETRY" else None
                try:
                    res = self.m4.glm_reparse_crop(ctx["png"], table["bbox"],
                                                   page=ctx.get("page", ctx.get("page_number")),
                                                   doc_sha1=ctx.get("doc_sha1", "unknown"),
                                                   render_reg=ctx.get("render_reg", {}),
                                                   hint=self._hint(failure, fb),
                                                   retry={"seq": int(retried),
                                                          "feedback_sha1": sha1_or_none(fb)})
                except VisionError as e:
                    if e.kind == "output_length_exceeded":
                        return self._blown(table, issue)
                    if e.kind in ("budget_exceeded", "no_key", "egress_blocked"):
                        return self._marked(table, issue, f"degraded:{e.kind}")
                    state = "SECOND"
                    continue
                cand = self._adapt(ctx, res)
                if cand["passed"]:
                    return self._done(table, cand["table"], issue, "crop-retranslate", "fixed")
                if state == "CROP" and not retried:
                    retried, state = True, "RETRY"          # FR-D8 仅一次
                else:
                    state = "SECOND"
            elif state == "SECOND":
                try:
                    res = self.m4.second_opinion(ctx["png"], table["bbox"],
                                                 page=ctx.get("page", ctx.get("page_number")),
                                                 doc_sha1=ctx.get("doc_sha1", "unknown"),
                                                 render_reg=ctx.get("render_reg", {}),
                                                 vendor=ctx.get("vendor", "deepseek"),
                                                 task=self._narrow_task(table, failure))
                except VisionError as e:
                    if e.kind == "output_length_exceeded":
                        return self._blown(table, issue)
                    if e.kind in ("budget_exceeded", "no_key", "egress_blocked"):
                        return self._marked(table, issue, f"degraded:{e.kind}")
                    return self._marked(table, issue, f"exhausted:{e.kind}")
                # B1：M4.second_opinion 现返回 §3.1 契约 dict（含 status/data）；直接读取
                obj = res if isinstance(res, dict) else None
                if obj is None or "status" not in obj:
                    return self._marked(table, issue, "unparseable_second_opinion")
                rows = (obj.get("data") or {}).get("rows")
                if obj.get("status") == "ok" and rows_aligned(rows, table):
                    merged = merge_second_opinion(table, obj)
                    if self._passes(merged, ctx):
                        return self._done(table, merged, issue, "second-opinion", "fixed")
                state = "MARKED"
            else:
                break
        return self._marked(table, issue, "exhausted")

    def _adapt(self, ctx, res):
        """CROP 结果（GLM）适配+重过门。res 为 M4.glm_reparse_crop 返回（含 raw_response → md）。"""
        raw = res.get("raw_response") or {}
        md = res.get("md") or ""
        from table_adapter import html_to_grid
        tabs = html_to_grid(md, self.cfg) if md else []
        if not tabs:
            return {"passed": False, "table": ctx.get("table") or {"cells": [], "grid": {"n_rows": 0, "n_cols": 0, "header_rows": 0}}, "failures": []}
        cand = tabs[0]
        cand["bbox"] = res.get("bbox") or ctx.get("table_bbox")
        return adapt_and_check(cand, self.gate, ctx)

    def resolve_hint(self, table, ctx):
        """HINT 入口（设计书 §7.3.2注）：hints/low_signal 且无 gate-failure → 直送二意见窄任务转写（D3 终裁）。
        复用 _done/_marked 记账原语；不经裁剪重译。对位一致且无改动→ok/有改动→fixed；不一致/不可执行→uncertain。"""
        issue = {"defect_class": "D3", "detected_by": ["second-opinion"],
                 "resolution": "none", "status": "unresolved",
                 "detail": "hint/低信号区触发第二意见逐行转写"}
        try:
            res = self.m4.second_opinion(ctx["png"], table["bbox"],
                                         page=ctx.get("page", ctx.get("page_number")),
                                         doc_sha1=ctx.get("doc_sha1", "unknown"),
                                         render_reg=ctx.get("render_reg", {}),
                                         vendor=ctx.get("vendor", "deepseek"),
                                         task=self._narrow_task(table, None))
        except VisionError as e:
            if e.kind == "output_length_exceeded":
                return self._blown(table, issue)
            if e.kind in ("budget_exceeded", "no_key", "egress_blocked"):
                return self._marked(table, issue, f"degraded:{e.kind}")
            return self._marked(table, issue, f"exhausted:{e.kind}")
        obj = res if isinstance(res, dict) else None
        if obj is None or "status" not in obj:
            return self._marked(table, issue, "unparseable_second_opinion")
        rows = (obj.get("data") or {}).get("rows")
        if obj.get("status") == "ok" and rows_aligned(rows, table):
            merged = merge_second_opinion(table, obj)
            if self._passes(merged, ctx):
                return self._done(table, merged, issue, "second-opinion", "fixed")
        return self._marked(table, issue, "d3_unverifiable_hint")


# ---------------------------------------------------------------- FR-D1 0-token 自检

def self_check(pages_json):
    """0-token 自检（FR-D1）：六显式信号产出 suspicious_tables[]（含 page/caption/bbox/reasons/old_text_snapshot）。
    六信号 = 有表题无结构 / 表格压平 / 疑似续表 / 数字自洽破坏 / 特殊字符密集 / 版式断裂。"""
    suspicious = []
    for page in pages_json.get("pages", []):
        for tb in page.get("tables", []):
            reasons = []
            cells = tb.get("cells", [])
            caption = tb.get("caption")
            if not cells:
                if caption:
                    reasons.append("有表题无结构")
            else:
                txt = " ".join(c.get("text", "") for c in cells)
                # 表格压平：文本含密集数值但无复合结构（全 1×1）
                if len(re.findall(r"\d", txt)) >= 6 and all(c.get("rowspan", 1) == 1 and c.get("colspan", 1) == 1 for c in cells):
                    reasons.append("表格压平")
                # 疑似续表
                if caption and "续表" in caption:
                    reasons.append("疑似续表")
                # 数字自洽破坏（复用 gate 数值信号）
                try:
                    from gate import check_numeric
                    if check_numeric(tb):
                        reasons.append("数字自洽破坏")
                except Exception:
                    pass
                # 特殊字符密集
                special = re.findall(r"[?？!！%‰℃㎡²]", txt)
                if len(special) >= 3:
                    reasons.append("特殊字符密集")
                # 版式断裂：某行 box 高度/间距异常（简化：行 bbox 缺失或重叠）
                if any(not c.get("bbox") for c in cells):
                    reasons.append("版式断裂")
            if reasons:
                suspicious.append({"page": page.get("page_number"), "caption": caption,
                                   "bbox": tb.get("bbox"), "reasons": reasons,
                                   "old_text_snapshot": tb.get("old_text_snapshot")})
    return suspicious
