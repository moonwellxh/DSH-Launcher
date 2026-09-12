#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M11 quality.py —— 需求书 §7.1 指标测量 + TEDS 接口（FR-E7）+ D2 修复率（V-2）+ 质检（FR-E9/FR-D5）
==================================================================
设计依据：需求书 §7.1（13 项指标，硬指标=守恒写回/标记完备/台账捕捉/溯源/成本可观测）、§6.11；
详细技术设计 §6.11（measure_volume/measure_d2_repair_rate/teds_score）、§8.2（V-4）。
TEDS：仅在存在真值文件时调用，无标注不调用、不虚构指标（FR-E7）。
"""
import json
from pathlib import Path

from gate import sig_defect_signature, sig_conservation, sig_structure  # noqa: E402


def conservation_ok(table):
    R = table["grid"]["n_rows"]
    C = table["grid"]["n_cols"]
    seen, area = set(), 0
    for cell in table.get("cells", []):
        r, c, rs, cs = cell["row"], cell["col"], cell["rowspan"], cell["colspan"]
        if r < 0 or c < 0 or r + rs > R or c + cs > C:
            return False
        for i in range(r, r + rs):
            for j in range(c, c + cs):
                if (i, j) in seen:
                    return False
                seen.add((i, j))
        area += rs * cs
    return area == R * C


def _all_tables(v4_json):
    for page in v4_json.get("pages", []):
        for tb in page.get("tables", []):
            yield page, tb


def measure_volume(v4_json, ledgers, cfg=None):
    """验收报告（§7.1 硬指标）。ledgers = {'token': [...] , 'defect': [...]} 或路径。返回 dict。
    **非真空口径**（对抗审查修正）：每项硬指标都如实测量、可失败；空集/零台账即如实判负。"""
    tables = list(_all_tables(v4_json))
    # 1) 守恒写回 100%（uncertain/unreadable 不计数——FR-E5 保留原文并标记，不视为守恒写回）
    writeback = [tb for _, tb in tables if tb.get("status") in ("ok", "fixed")]
    if writeback:
        cons_ok = sum(1 for tb in writeback if conservation_ok(tb))
        cons_rate = round(cons_ok / len(writeback), 4)
    else:
        cons_rate = 0.0          # 无任何写回表（全部标记）→ 信息未恢复，如实判负
    cons_passed = cons_rate >= 1.0 and len(writeback) > 0
    # 2) 诚实标记完备率：uncertain/unreadable 带 reason 与定位（打标到格）
    marked = [tb for _, tb in tables if tb.get("status") in ("uncertain", "unreadable")]
    mark_ok = sum(1 for tb in marked
                  if tb.get("unreadable_reason") or any(i.get("detail") for i in tb.get("issues", [])))
    mark_rate = round(mark_ok / len(marked), 4) if marked else 1.0
    # 3) 缺陷台账捕捉率（FR-E9 无静默通过）：有缺陷证据的表须登记 issues[]；全有=100%，缺=如实判负
    needs = []
    seen_ids = set()
    for page, tb in tables:
        has_issue = bool(tb.get("issues"))
        has_evidence = False
        if cfg:
            gf = sig_defect_signature(tb, cfg) + sig_conservation(tb) + sig_structure(tb)
            has_evidence = bool(gf)
        if has_issue or has_evidence:
            if id(tb) not in seen_ids:
                seen_ids.add(id(tb))
                needs.append(tb)
    captured = sum(1 for tb in needs if tb.get("issues"))
    defect_rate = round(captured / len(needs), 4) if needs else 1.0
    defect_passed = defect_rate >= 1.0
    # 4) 溯源完整率：表锚定于 pages[]（含页码）；图需 page+bbox；任一缺口如实判负
    tbls = len(tables)
    tbl_src = sum(1 for page, tb in tables if page.get("page_number") is not None)
    imgs = sum(len(p.get("images", [])) for p in v4_json.get("pages", []))
    img_src = sum(1 for p in v4_json.get("pages", []) for im in p.get("images", [])
                  if im.get("page") is not None and im.get("bbox") is not None)
    denom = tbls + imgs
    got = tbl_src + img_src
    src_rate = round(got / denom, 4) if denom else 1.0
    src_passed = (src_rate >= 1.0) and (tbl_src == tbls) and (img_src == imgs)
    # 5) 成本可观测率：有表/页即须有逐调用 token 台账（含 cost_cny）；零台账如实判负
    token_led = _load(ledgers.get("token")) if isinstance(ledgers.get("token"), (str, Path)) else (ledgers.get("token") or [])
    if not isinstance(token_led, list):
        token_led = []
    has_tables_or_pages = bool(tables or v4_json.get("pages"))
    if has_tables_or_pages and token_led:
        cost_ok = all(isinstance(r, dict) and "cost_cny" in r for r in token_led)
        cost_rate = 1.0 if cost_ok else 0.0
    else:
        cost_rate = 0.0          # 零台账 → 成本可观测 0%，如实判负
    cost_passed = cost_rate >= 1.0 and len(token_led) > 0

    hard = {
        "conservation_writeback": {"passed": cons_passed, "rate": cons_rate,
                                   "detail": f"{cons_ok}/{len(writeback)}" if writeback else "无写回表"},
        "honest_marking": {"passed": mark_rate >= 1.0, "rate": mark_rate,
                           "detail": f"{mark_ok}/{len(marked)}"},
        "defect_capture": {"passed": defect_passed, "rate": defect_rate,
                           "detail": f"{captured}/{len(needs)}"},
        "source_locatable": {"passed": src_passed, "rate": src_rate,
                             "detail": f"tables={tbl_src}/{tbls} imgs={img_src}/{imgs}"},
        "cost_observable": {"passed": cost_passed, "rate": cost_rate,
                            "detail": f"ledger_rows={len(token_led)}"},
    }
    accepted = all(v["passed"] for v in hard.values())
    return {"accepted": accepted, "hard_metrics": hard,
            "tables_total": tbls, "marked_total": len(marked),
            "writeback_total": len(writeback),
            "summary": "PASS" if accepted else "FAIL[RED]"}


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return []


def measure_d2_repair_rate(ledger):
    """V-2：D2 裁剪重译修复率。分母=台账中全部 D2 缺陷（含经阶梯处理者），分子=经 crop-retranslate 且 resolved 的 D2。
    注：设计 §6.11 分母为「进入裁剪重译环节的 D2 数」；台账当前只记录最终 resolution，无法区分「裁剪尝试后转二意见/标记」
    与「未进裁剪」，故以「检测到的 D2 总数」为分母（保守、非恒真；defect_class=D2）。"""
    all_d2 = [i for i in ledger if i.get("defect_class") == "D2"]
    if not all_d2:
        return None
    ok = sum(1 for i in all_d2
             if i.get("resolution") == "crop-retranslate" and i.get("status") == "resolved")
    return round(ok / len(all_d2), 4)


def teds_score(pred_table, truth_table):
    """FR-E7：TEDS（树编辑距离相似度）。无标注不调用——调用方确保有真值。
    简化口径：比较 n_rows/n_cols + 逐格文本匹配均匀度。"""
    gp, gt = pred_table.get("grid", {}), truth_table.get("grid", {})
    structure = 1.0 if (gp.get("n_rows") == gt.get("n_rows") and gp.get("n_cols") == gt.get("n_cols")) else 0.0
    pred_cells = {c["row"] * gt.get("n_cols", 1) + c["col"]: c.get("text", "")
                  for c in pred_table.get("cells", [])}
    truth_cells = {c["row"] * gt.get("n_cols", 1) + c["col"]: c.get("text", "")
                   for c in truth_table.get("cells", [])}
    if not truth_cells:
        return structure
    text_sim = sum(1 for k, v in truth_cells.items() if pred_cells.get(k) == v) / len(truth_cells)
    return round(0.5 * structure + 0.5 * text_sim, 4)
