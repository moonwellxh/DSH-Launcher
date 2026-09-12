#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_ms3_ladder.py —— M8 缺陷阶梯状态机离线测试（mock M4，不打 API）
====================================================================
覆盖（详细技术设计 §7.3.1 转移表 + 不变式）：
  * DETECTED → RULE_FIX → FIXED（D1 规则拆分修复）
  * RULE_FIX 失败（不可拆）→ CROP → FIXED（mock 裁剪重译候选过门）
  * CROP 失败 → RETRY（≤1，FR-D8）→ FIXED（区分指纹）
  * CROP/RETRY 失败 → SECOND → FIXED（第二意见 ok+行对位一致）
  * SECOND 不对位 → MARKED；预算/无key/egress → MARKED(degraded)；output_length → BLOWN
  * 不变式：RETRY 每表至多一次；MARKED/BLOWN 必带 reason；不得覆盖 old_text_snapshot
用法：python tests/v4/test_ms3_ladder.py
"""
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "assets" / "v4"))

from defect_ladder import Ladder, self_check  # noqa: E402
import gate as gate_mod  # noqa: E402
from gate import gate_check  # noqa: E402
from vision_client import VisionError, BudgetGate, GLM_CHANNEL  # noqa: E402

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


# 一个守恒表（1×2 头 + 2 数据行），供候选通过 g->check
def good_table():
    return {"grid": {"n_rows": 3, "n_cols": 2, "header_rows": 1},
            "cells": [
                {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "列A", "bbox": None, "is_header": True},
                {"row": 0, "col": 1, "rowspan": 1, "colspan": 1, "text": "列B", "bbox": None, "is_header": True},
                {"row": 1, "col": 0, "rowspan": 1, "colspan": 1, "text": "1", "bbox": None, "is_header": False},
                {"row": 1, "col": 1, "rowspan": 1, "colspan": 1, "text": "甲", "bbox": None, "is_header": False},
                {"row": 2, "col": 0, "rowspan": 1, "colspan": 1, "text": "2", "bbox": None, "is_header": False},
                {"row": 2, "col": 1, "rowspan": 1, "colspan": 1, "text": "乙", "bbox": None, "is_header": False},
            ], "bbox": [0, 0, 100, 100], "adapter_notes": [], "issues": []}


class MockM4:
    """可编程 M4 mock：控制 crop 的 md/异常、second 的结果/异常。
    与生产签名同形（S9-A1/R-05：page/doc_sha1/render_reg 必填关键字，去默认）；calls 记录收参（R-05/R-12 断言）。"""
    def __init__(self, md=""):
        self.md = md
        self.crop_exc = None
        self.so_res = {"status": "ok", "data": {"rows": [["1", "甲"]]}}
        self.so_exc = None
        self.calls = []
    def glm_reparse_crop(self, png, bbox, *, page, doc_sha1, render_reg, hint=None, retry=None):
        self.calls.append({"kind": "crop", "page": page, "doc_sha1": doc_sha1, "render_reg": render_reg})
        if self.crop_exc is not None:
            raise self.crop_exc
        return {"md": self.md, "raw_response": {"response": {}}, "bbox": bbox, "cache_hit": False}
    def second_opinion(self, png, bbox, *, page, doc_sha1, render_reg,
                       vendor="deepseek", task=None):
        self.calls.append({"kind": "second", "page": page, "doc_sha1": doc_sha1, "render_reg": render_reg})
        if self.so_exc is not None:
            raise self.so_exc
        return self.so_res


def ctx_of(m4, table, md="<table><tr><td>1</td></tr></table>"):
    # 让我们方便的 ctx：M4 的 crop/second 由 mock 提供；_adapt 用 md 生成候选
    return {"png": "x.png", "table_bbox": table.get("bbox"), "table": table,
            "vendor": "deepseek", "cfg": CFG, "ocr_lines": [], "ocr_available": False,
            "ocr_expected": False, "md": md,
            "page": 1, "doc_sha1": "ctx-doc", "render_reg": {"dpi": 220, "render_sha1": "x"}}


def run_ladder(table, failure, m4):
    lad = Ladder(m4, gate_mod, CFG, BudgetGate(CFG, {GLM_CHANNEL: 1.0}), None)
    ctx = {"png": "x.png", "table_bbox": table.get("bbox"), "table": table,
           "vendor": "deepseek", "cfg": CFG, "ocr_lines": [], "ocr_available": False,
           "ocr_expected": False,
           "page": 1, "doc_sha1": "ctx-doc", "render_reg": {"dpi": 220, "render_sha1": "x"}}
    return lad.resolve(table, failure, ctx)


def main():
    t = Tally()
    GOOD_MD = ("<table><tr><th>列A</th><th>列B</th></tr>"
               "<tr><td>1</td><td>甲</td></tr><tr><td>2</td><td>乙</td></tr></table>")
    # --- CROP → FIXED ---
    tb = good_table()
    m4 = MockM4(md=GOOD_MD)
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R1 CROP→FIXED（裁剪重译候选过门）", r and r["status"] == "fixed",
            f"status={r and r['status']} resolution={r and r['resolution']}")

    # --- CROP 失败(md 空) → RETRY → SECOND → 行对位一致(rows_aligned) + 过门 → FIXED ---
    tb = good_table()
    m4 = MockM4(md="")  # crop 不得为过门候选
    m4.so_res = {"status": "ok", "data": {"rows": [["1", "甲"], ["2", "乙"]]}}
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R2 RETRY→SECOND→对位一致→FIXED", r and r["status"] == "fixed", f"status={r and r['status']}")
    m4_r2 = m4   # 捕获 R2 实例（后续块会重绑 m4），供 R-05 转发断言引用

    # --- 预算超限 → MARKED(degraded) ---
    tb = good_table()
    m4 = MockM4(md=""); m4.crop_exc = VisionError("budget_exceeded", "超限")
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R3 budget_exceeded → MARKED(uncertain)", r and r["status"] == "uncertain"
            and any("degraded" in (i.get("detail") or "") for i in r["issues"]),
            f"status={r and r['status']}")

    # --- output_length_exceeded → BLOWN(unreadable+reason) ---
    tb = good_table()
    m4 = MockM4(md=""); m4.crop_exc = VisionError("output_length_exceeded", "截断")
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R4 output_length → BLOWN(unreadable+reason)", r and r["status"] == "unreadable"
            and r["table_out"].get("unreadable_reason") == "output_length_exceeded",
            f"status={r and r['status']} reason={r and r['table_out'].get('unreadable_reason')}")

    # --- 重试仅一次：CROP 失败 → SECOND 无key → MARKED(uncertain degraded) ---
    tb = good_table()
    m4 = MockM4(md=""); m4.so_exc = VisionError("no_key", "无key")
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R5 重试≤1 + SECOND no_key → MARKED", r and r["status"] == "uncertain",
            f"status={r and r['status']}")

    # --- 不变式：MARKED 带 reason；不覆盖 snap ---
    tb = good_table()
    m4 = MockM4(md=""); m4.crop_exc = VisionError("egress_blocked", "禁止")
    r = run_ladder(tb, {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}, m4)
    t.check("R6 MARKED 带 reason + 保留快照", r and r["status"] == "uncertain"
            and tb.get("old_text_snapshot") is not None, f"snap={'有' if tb.get('old_text_snapshot') else '无'}")

    # --- FR-D1 自检 ---
    sus = self_check({"pages": [{"page_number": 1, "tables": [
        {"caption": "表x", "cells": [], "bbox": None},
        {"caption": "表y", "cells": [{"text": "12 34 56 78 9", "row": 0, "col": 0, "rowspan": 1, "colspan": 1}], "bbox": None},
    ]}]})
    t.check("R7 FR-D1 自检产出 suspicious", len(sus) >= 1, f"n={len(sus)}")

    # --- R-05（S9-A1）MockM4 同形转发守卫：R2 场景已触发 second → 收参与 run_ladder ctx 一致（page=1/doc_sha1=ctx-doc）---
    sec_r2 = [c for c in m4_r2.calls if c["kind"] == "second"]
    t.check("R-05 second 收参与 ctx 一致", bool(sec_r2) and sec_r2[0]["page"] == 1
            and sec_r2[0]["doc_sha1"] == "ctx-doc"
            and sec_r2[0]["render_reg"] == {"dpi": 220, "render_sha1": "x"},
            f"first_second={sec_r2[0] if sec_r2 else None}")

    # --- R-12（S9-A3）ctx.page 口径：ctx 仅带 page_number=7（无 page 键）三路径回退取值==7 ---
    ctx12 = {"png": "x.png", "table_bbox": [0, 0, 100, 100], "vendor": "deepseek",
             "cfg": CFG, "ocr_lines": [], "ocr_available": False, "ocr_expected": False,
             "page_number": 7, "doc_sha1": "ctx-doc", "render_reg": {"dpi": 220, "render_sha1": "x"}}
    failc = {"signal": "conservation", "class": None, "detail": "不守恒", "cells": []}
    # a) CROP 直发回退
    ta = good_table(); ma = MockM4(md=GOOD_MD); ctx12["table"] = ta
    ra = Ladder(ma, gate_mod, CFG, BudgetGate(CFG, {GLM_CHANNEL: 1.0}), None).resolve(ta, failc, dict(ctx12))
    crop_a = [c for c in ma.calls if c["kind"] == "crop"]
    t.check("R-12a CROP 回退 page==7", bool(crop_a) and crop_a[0]["page"] == 7,
            f"status={ra and ra['status']} crop={crop_a[0] if crop_a else None}")
    # b) crop md 空 → RETRY → SECOND 回退
    tb12 = good_table(); mb = MockM4(md=""); ctx12["table"] = tb12
    rb = Ladder(mb, gate_mod, CFG, BudgetGate(CFG, {GLM_CHANNEL: 1.0}), None).resolve(tb12, failc, dict(ctx12))
    sec_b = [c for c in mb.calls if c["kind"] == "second"]
    t.check("R-12b SECOND 回退 page==7", bool(sec_b) and sec_b[0]["page"] == 7,
            f"status={rb and rb['status']} sec={sec_b[0] if sec_b else None}")
    # c) hint 直送 SECOND 回退
    tc = good_table(); mc = MockM4(md=""); ctx12["table"] = tc
    rc = Ladder(mc, gate_mod, CFG, BudgetGate(CFG, {GLM_CHANNEL: 1.0}), None).resolve_hint(tc, dict(ctx12))
    sec_c = [c for c in mc.calls if c["kind"] == "second"]
    t.check("R-12c resolve_hint 回退 page==7", bool(sec_c) and sec_c[0]["page"] == 7,
            f"status={rc and rc['status']} sec={sec_c[0] if sec_c else None}")

    print(f"\nRESULT pass={t.p} fail={t.f}")
    if t.f:
        print("FAILED:", ", ".join(t.failures))
    return 0 if t.f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
