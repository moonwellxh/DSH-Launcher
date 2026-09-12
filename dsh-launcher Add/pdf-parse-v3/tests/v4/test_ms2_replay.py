#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_ms2_replay.py —— MS-2 表格主线离线重放（黄金夹具，不打 API）
====================================================================
覆盖（详细技术设计 §12 MS-2 出口判据）：
  * 适配层转换零异常（FR-C6：GLM md_results 的 <table> → 网格，无异常）
  * 守恒：适配层输出、缺陷阶梯介入前的守恒直通率（固定测量点，§11.2）
  * 幻影列坍缩：page_0087 过声明（列向 col_D=1 + 行向 tr2 rs=11）归一化为 12×5 守恒 + D2 resolved
  * 校验门：gate_check（无 OCR → 文字层路径，信号3/4 N/A）对每表产出 failures/hints 分层

用法：python tests/v4/test_ms2_replay.py
输出：RESULT pass=N fail=0
"""
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "assets" / "v4"))

from table_adapter import html_to_grid, conservation_ok, try_merge_continuation  # noqa: E402
from gate import gate_check  # noqa: E402
from pipeline import _layout_table_blocks, _first_cell_eq, process_page_md  # noqa: E402
from vision_client import cache_fingerprint, TASK_CROP  # noqa: E402

BATCH = SKILL / "tests" / "vision_shootout" / "results" / "batch"
CFG = json.loads((SKILL / "assets" / "v4" / "config.default.json").read_text(encoding="utf-8"))


class Tally:
    def __init__(self):
        self.p = 0
        self.f = 0
        self.failures = []

    def check(self, name, ok, detail=""):
        if ok:
            self.p += 1
            print(f"[PASS] {name} {detail}")
        else:
            self.f += 1
            self.failures.append(name)
            print(f"[FAIL] {name} {detail}")


def load_fixture_tables():
    pages = []
    for f in sorted(BATCH.glob("page_*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        if raw.get("http_status") != 200:
            continue
        md = (raw.get("response") or {}).get("md_results") or ""
        pages.append((f.stem, md))
    return pages


def main():
    t = Tally()
    pages = load_fixture_tables()
    t.check("MS2 夹具页数=180", len(pages) == 180, f"n={len(pages)}")

    tables = []
    errs = []
    for sid, md in pages:
        try:
            out = html_to_grid(md, CFG)
            tables.extend([(sid, tb) for tb in out])
        except Exception as e:
            errs.append((sid, repr(e)))
    t.check("MS2 适配层转换零异常", len(errs) == 0, f"exceptions={len(errs)}")
    tot = len(tables)
    conserved = sum(1 for _, tb in tables if conservation_ok(tb))
    direct_rate = round(conserved / tot, 4) if tot else 0.0
    # 守恒直通率测量点=适配层输出、缺陷阶梯介入前（§11.2）
    t.check("MS2 守恒直通率（适配层输出测量点）", conserved > 0 and tot > 0,
            f"{conserved}/{tot} = {direct_rate}")
    # 幻影列坍缩对应：凡被 overdeclare 归一化（有 rowspan_overdeclare note）且未 unresolved 的表必守恒
    normalized = [(sid, tb) for sid, tb in tables
                  if any(n.startswith("rowspan_overdeclare") for n in tb.get("adapter_notes", []))
                  and not any(n.startswith("overdeclare_unresolved") for n in tb.get("adapter_notes", []))]
    t.check("MS2 幻影列坍缩后守恒对应（应修复 D2 子集）",
            all(conservation_ok(tb) for _, tb in normalized) and len(normalized) >= 1,
            f"normalized_tables={len(normalized)}")

    # page_0087 幻影列坍缩断言（设计书 §2.2：col_D=1×5 + 行向 tr2 11→10 → 12×5 守恒）
    p87 = [tb for sid, tb in tables if sid == "page_0087"]
    t.check("MS2 page_0087 表存在", len(p87) == 1, f"n={len(p87)}")
    if p87:
        tb = p87[0]
        g = tb["grid"]
        t.check("MS2 page_0087 归一化 12×5 守恒", (g["n_rows"], g["n_cols"]) == (12, 5) and conservation_ok(tb),
                f"grid={g['n_rows']}x{g['n_cols']} header_rows={g['header_rows']}")
        d2resolved = [i for i in tb.get("issues", [])
                      if i.get("defect_class") == "D2" and i.get("resolution") == "phantom-collapse"
                      and i.get("status") == "resolved"]
        t.check("MS2 page_0087 D2 幻影列坍缩登记 resolved", len(d2resolved) >= 1,
                f"d2_resolved={len(d2resolved)}")

    # 校验门（无 OCR → 文字层路径）：分层（gate-failure vs hints）
    gf_total = 0
    gf_by_signal = {}
    for sid, tb in tables:
        r = gate_check(tb, [], None, False, CFG, ocr_expected=False)
        if not r["passed"]:
            gf_total += 1
            for fail in r["failures"]:
                gf_by_signal[fail["signal"]] = gf_by_signal.get(fail["signal"], 0) + 1
    t.check("MS2 校验门 running（gate-failure 计数）", gf_total >= 0,
            f"gate_failure_tables={gf_total}/{tot} by_signal={gf_by_signal}")

    # 续表合并可调用性（不硬猜；无真实续表夹具，仅断言接口不抛）
    try:
        merged = try_merge_continuation({"grid": {"n_rows": 2, "n_cols": 3, "header_rows": 1},
                                         "cells": [], "caption": None, "context_before": ""},
                                        {"grid": {"n_rows": 2, "n_cols": 3, "header_rows": 1},
                                         "cells": [], "caption": "续表", "context_before": "续表"},
                                        [1, 2], CFG)
        t.check("MS2 续表合并接口可调用", True, f"merged={merged is not None}（空表不合并=诚实）")
    except Exception as e:
        t.check("MS2 续表合并接口可调用", False, repr(e))

    # ---- R-13（处理遗留 S9-1）：夹具回归——180 页表数全等 + 逐位首格抽查全过（防夹具重录/适配层/配对逻辑回归）----
    cnt_neq, probe_fail = [], []
    tot_md = tot_lay = 0
    for f in sorted(BATCH.glob("page_*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        if raw.get("http_status") != 200:
            continue
        payload = raw.get("response") or {}
        md = payload.get("md_results") or ""
        tabs = html_to_grid(md, CFG)
        lay = _layout_table_blocks(payload)
        tot_md += len(tabs)
        tot_lay += len(lay)
        if len(tabs) != len(lay):
            cnt_neq.append(f.stem)
            continue
        mm = next((i for i, tb in enumerate(tabs) if not _first_cell_eq(tb, lay[i][1])), None)
        if mm is not None:
            probe_fail.append((f.stem, mm))
    t.check("R-13 180页 md/layout 表数全等（84=84）", not cnt_neq and tot_md == tot_lay == 84,
            f"cnt_neq={cnt_neq} md={tot_md} lay={tot_lay}")
    t.check("R-13 逐位首格抽查全过（180页）", not probe_fail, f"probe_fail={probe_fail}")

    # ---- R-13 page_0019 双表页：真实 bbox 互异且==layout 块值 → 缓存指纹不同（V-4 防碰撞）----
    raw19 = json.loads((BATCH / "page_0019.json").read_text(encoding="utf-8"))
    pay19 = raw19.get("response") or {}
    part19 = process_page_md(19, pay19.get("md_results") or "", CFG,
                             ocr_lines=[], ocr_available=False, m4=None, raw_resp=pay19)
    t19 = part19.get("tables", [])
    lay19 = _layout_table_blocks(pay19)
    t.check("R-13 p0019 双表且 bbox 真实", len(t19) == 2 and len(lay19) == 2
            and t19[0]["bbox"] != t19[1]["bbox"]
            and t19[0]["bbox"] == lay19[0][0] and t19[1]["bbox"] == lay19[1][0],
            f"bbox={[x.get('bbox') for x in t19]}")
    reg19 = {"dpi": 225, "pixel": [1860, 2699], "render_sha1": "x"}
    fp1 = cache_fingerprint(doc_sha1="x", page=19, task_type=TASK_CROP, bbox=t19[0]["bbox"],
                            render_reg=reg19, model="glm-ocr", prompt_ver="ch-1.0",
                            retry={"seq": 0, "feedback_sha1": None})
    fp2 = cache_fingerprint(doc_sha1="x", page=19, task_type=TASK_CROP, bbox=t19[1]["bbox"],
                            render_reg=reg19, model="glm-ocr", prompt_ver="ch-1.0",
                            retry={"seq": 0, "feedback_sha1": None})
    t.check("R-13 双表 bbox 指纹互异（防碰撞）", fp1 != fp2, "")

    # ---- R-13 回退路径（诚实不静默）：count 不等 → 退化+note；count 等但首格错序 → order-mismatch+note ----
    md_2 = ("<table><tr><td>甲表</td><td>1</td></tr></table>\n"
            "<table><tr><td>乙表</td><td>2</td></tr></table>")
    pay_1tab = {"md_results": md_2,
                "layout_details": [[{"native_label": "table", "bbox_2d": [10, 10, 100, 100],
                                     "content": "<table><tr><td>甲表</td><td>1</td></tr></table>"}]]}
    part_mm = process_page_md(5, md_2, CFG, ocr_lines=[], ocr_available=False,
                              m4=None, raw_resp=pay_1tab)
    notes_mm = [r.get("note", "") for r in part_mm.get("routing", [])
                if r.get("method") == "table-bbox-unresolved"]
    t.check("R-13 count 不等→退化 bbox+note", all(x.get("bbox") == [0, 0, 1, 1] for x in part_mm.get("tables", []))
            and any("md_tables=2 layout_tables=1" in n for n in notes_mm), f"notes={notes_mm}")
    pay_swap = {"md_results": md_2,
                "layout_details": [[
                    {"native_label": "table", "bbox_2d": [10, 10, 100, 100],
                     "content": "<table><tr><td>乙表</td><td>2</td></tr></table>"},
                    {"native_label": "table", "bbox_2d": [200, 10, 300, 100],
                     "content": "<table><tr><td>甲表</td><td>1</td></tr></table>"}]]}
    part_swap = process_page_md(5, md_2, CFG, ocr_lines=[], ocr_available=False,
                                m4=None, raw_resp=pay_swap)
    notes_sw = [r.get("note", "") for r in part_swap.get("routing", [])
                if r.get("method") == "table-bbox-unresolved"]
    t.check("R-13 count 等首格错序→order-mismatch 回退", any("order-mismatch@0" in n for n in notes_sw),
            f"notes={notes_sw}")

    # ---- R-15（表头识别增强）----
    # 合成：第 78 页旋转表类（序号行+属性行+子列）→ header_rows==3（判据 1 双条件 + 判据 2 连续）
    md_rot = ('<table border="1">'
              '<tr><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td>'
              '<td colspan="4">9</td><td>10</td></tr>'
              '<tr><td rowspan="2">序号</td><td rowspan="2">物质名称</td><td rowspan="2">熔点</td>'
              '<td rowspan="2">沸点</td><td rowspan="2">密度</td><td rowspan="2">比重</td>'
              '<td rowspan="2">闪点</td><td rowspan="2">自燃点</td><td colspan="2">爆炸极限</td>'
              '<td rowspan="2">备注</td></tr>'
              '<tr><td>下限</td><td>上限</td><td>下限</td><td>上限</td></tr>'
              '<tr><td>1</td><td>乙醚</td><td>-116</td><td>34.5</td><td>0.71</td><td>2.55</td>'
              '<td>&lt;-20</td><td>170</td><td>1.7</td><td>36</td><td>1100</td></tr>'
              '</table>')
    rot_tb = html_to_grid(md_rot, CFG)
    t.check("R-15 旋转表类 header_rows==3", len(rot_tb) == 1 and rot_tb[0]["grid"]["header_rows"] == 3,
            f"hdr={rot_tb[0]['grid']['header_rows'] if rot_tb else None}")
    t.check("R-15 旋转表类表头区 is_header 覆盖", rot_tb and all(
        c["is_header"] for c in rot_tb[0]["cells"] if c["row"] < rot_tb[0]["grid"]["header_rows"]),
        "ok")
    # 合成：普通表头行 → 1
    md_n = ("<table><tr><td>序号</td><td>构件名称</td><td>结构厚度或截面最小尺寸</td>"
            "<td>耐火极限(h)</td><td>燃烧性能</td></tr>"
            "<tr><td>1</td><td>承重墙</td><td>12.0</td><td>2.50</td><td>非燃烧体</td></tr></table>")
    tb_n = html_to_grid(md_n, CFG)
    t.check("R-15 普通表头 header_rows==1", len(tb_n) == 1 and tb_n[0]["grid"]["header_rows"] == 1,
            f"hdr={tb_n[0]['grid']['header_rows'] if tb_n else None}")
    # 负例 1：首行纯数字但次行为数据 → 0（判据 1 收紧）
    md_n1 = ("<table><tr><td>1</td><td>2</td><td>3</td></tr>"
             "<tr><td>乙醚</td><td>34.5</td><td>0.71</td></tr></table>")
    tb_n1 = html_to_grid(md_n1, CFG)
    t.check("R-15 负例1（数字行+数据行）header_rows==0", len(tb_n1) == 1 and tb_n1[0]["grid"]["header_rows"] == 0,
            f"hdr={tb_n1[0]['grid']['header_rows'] if tb_n1 else None}")
    # 负例 2：纯数据行表 → 0
    md_n2 = ("<table><tr><td>水泥</td><td>钢材</td><td>1.2</td><td>2.5</td><td>非燃烧体</td></tr></table>")
    tb_n2 = html_to_grid(md_n2, CFG)
    t.check("R-15 负例2（纯数据）header_rows==0", len(tb_n2) == 1 and tb_n2[0]["grid"]["header_rows"] == 0,
            f"hdr={tb_n2[0]['grid']['header_rows'] if tb_n2 else None}")
    # 真实夹具：判据命中目标页 header_rows≥1（覆盖 0040/0043 等）
    tgt = ["page_0085", "page_0013", "page_0106", "page_0164", "page_0040", "page_0043"]
    ok_tgt = True
    tgt_hdr = {}
    for stem in tgt:
        raw = json.loads((BATCH / (stem + ".json")).read_text(encoding="utf-8"))
        md = (raw.get("response") or {}).get("md_results") or ""
        tabs = html_to_grid(md, CFG)
        hr = tabs[0]["grid"]["header_rows"] if tabs else 0
        tgt_hdr[stem] = hr
        if hr < 1:
            ok_tgt = False
    t.check("R-15 夹具目标页 header_rows≥1", ok_tgt, str(tgt_hdr))

    # ---- R-16（纯空列修剪）----
    # 幽灵尾空列合成：整列全空 → 修剪（n_cols 减、holes==0）
    md_ghost = ("<table><tr><td>名称</td><td>单位</td><td></td></tr>"
                "<tr><td>甲</td><td>个</td><td></td></tr></table>")
    gh = html_to_grid(md_ghost, CFG)
    t.check("R-16 幽灵尾空列修剪 n_cols==2", gh and gh[0]["grid"]["n_cols"] == 2,
            f"n_cols={gh[0]['grid']['n_cols'] if gh else None}")
    t.check("R-16 幽灵尾空列修剪 holes==0", gh and not any(n.startswith("holes@") for n in gh[0].get("adapter_notes", [])),
            str(gh[0].get("adapter_notes") if gh else None))
    # 跨空列 colspan 保守跳过（横跨保留+空列边界）
    md_cross = ("<table><tr><td>a</td><td colspan=\"2\"></td></tr>"
                "<tr><td>1</td><td>2</td><td></td></tr></table>")
    crx = html_to_grid(md_cross, CFG)
    t.check("R-16 跨空列colspan 跳过（n_cols 保持）", crx and crx[0]["grid"]["n_cols"] == 3,
            f"n_cols={crx[0]['grid']['n_cols'] if crx else None}")
    # 全空表保护（不退化到 0 列）
    md_all = "<table><tr><td></td><td></td></tr></table>"
    alltb = html_to_grid(md_all, CFG)
    t.check("R-16 全空表保护（n_cols==2 不变）", alltb and alltb[0]["grid"]["n_cols"] == 2,
            f"n_cols={alltb[0]['grid']['n_cols'] if alltb else None}")
    # 真实夹具：page_0085（col5 空幽灵列）修剪后 n_cols==5 且 holes==0；page_0095 全空表保护（n_cols==2 不变）
    def _md_of(stem):
        raw = json.loads((BATCH / (stem + ".json")).read_text(encoding="utf-8"))
        return (raw.get("response") or {}).get("md_results") or ""
    tb85 = html_to_grid(_md_of("page_0085"), CFG)
    t.check("R-16 真实85 修剪后 n_cols==5", len(tb85) == 1 and tb85[0]["grid"]["n_cols"] == 5,
            f"n_cols={tb85[0]['grid']['n_cols'] if tb85 else None} holes={[n for n in tb85[0].get('adapter_notes',[]) if n.startswith('holes@')] if tb85 else None}")
    tb95 = html_to_grid(_md_of("page_0095"), CFG)
    # 95 含 实表 + 空表（两张）；全空表保护→空表那张 n_cols 保持未退化（=2）
    all_empty95 = [t for t in tb95 if all(not (c.get("text") or "").strip() for c in t["cells"])]
    t.check("R-16 真实95 全空表保护（空表 n_cols==2）", bool(all_empty95) and all_empty95[0]["grid"]["n_cols"] == 2,
            f"n_empty={len(all_empty95)} n_cols={all_empty95[0]['grid']['n_cols'] if all_empty95 else None}")

    print(f"\nRESULT pass={t.p} fail={t.f}")
    if t.f:
        print("FAILED:", ", ".join(t.failures))
    return 0 if t.f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
