#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py —— 离线管线：黄金夹具 md_results → 适配层 → 校验门 → 缺陷阶梯 → structurer v4 → quality 硬指标
==================================================================
用于 MS-5 验收（黄金夹具离线重放，零网络）。真实出域（GLM 整页解析）由 M4 承担；
本模块只在既有 GLM 响应（md_results）上做确定性变换与组装（FR-C6/C1/E8/D1..D8/F1，全部离线）。
"""
import json
from pathlib import Path

from table_adapter import html_to_grid, conservation_ok
import gate as gate_mod
from gate import gate_check
from defect_ladder import Ladder
from structurer import assemble_v4
from quality import measure_volume
from vision_client import BudgetGate, GLM_CHANNEL

_DET_SIGNALS = ("structure", "conservation", "signature", "numeric")


class NoOpM4:
    """离线验收用 M4 占位：ladder 的 crop/second 在离线口径下不可用 → 走 MARKED（诚实标记）。
    这样不虚构修复、不调真 API，符合 FR-D7/保真原则。"""
    def glm_reparse_crop(self, *a, **k):
        from vision_client import VisionError
        raise VisionError("egress_blocked", "离线验收：裁剪重译不可用")
    def second_opinion(self, *a, **k):
        from vision_client import VisionError
        raise VisionError("egress_blocked", "离线验收：第二意见不可用")


def _image_blocks(raw_resp):
    """从 GLM layout_details 提取 image 块 → 图片索引条目（page+bbox+hash；FR-B4/B6/S6）。"""
    out = []
    pages_blk = (raw_resp or {}).get("layout_details") or []
    if pages_blk and isinstance(pages_blk[0], list):
        for b in pages_blk[0]:
            if not isinstance(b, dict):
                continue
            if b.get("native_label") != "image":
                continue
            bb = b.get("bbox_2d") or [0, 0, 0, 0]
            import hashlib
            h = hashlib.sha1((b.get("content") or str(bb)).encode("utf-8")).hexdigest()[:16]
            out.append({"type": "image", "id": f"img_p{int(bb[0])}_{len(out)}", "page": None,
                        "path": None, "bbox": [int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])],
                        "hash": h, "caption": "", "ocr_text": "", "source": "crop"})
    return out


def _layout_table_blocks(payload):
    """layout_details[0] 中 native_label=='table' 的块，保序返回 [(bbox_int4, content_html)]（处理遗留 R-13/S9-1）。
    bbox_int4=[x1,y1,x2,y2]（像素系，int）；content_html 供首格抽查 _first_cell_eq。"""
    out = []
    for page_blocks in (payload or {}).get("layout_details") or []:
        if not isinstance(page_blocks, list):
            continue
        for b in page_blocks:
            if not isinstance(b, dict):
                continue
            if (b.get("native_label") or b.get("label")) != "table":
                continue
            bb = b.get("bbox_2d") or [0, 0, 0, 0]
            out.append(([int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])], b.get("content") or ""))
    return out


def _first_cell_eq(md_tb, layout_html):
    """md 表首格文本 与 layout 块 HTML 首格文本归一化相等，或双方均为空 → True（顺序对位抽查，R-13/建议-2）。
    抽查仅"首格+双空"口径；其余错位形态首格仍同则无法探测（如实声明残余风险）。"""
    import re as _re
    from bs4 import BeautifulSoup as _BS
    md_first = _re.sub(r"\s+", "", (md_tb.get("cells") or [{}])[0].get("text", "")) \
        if md_tb.get("cells") else ""
    lay_first = ""
    if layout_html:
        soup = _BS(layout_html, "html.parser")
        first = soup.find(["td", "th"])
        if first is not None:
            lay_first = _re.sub(r"\s+", "", first.get_text(" ", strip=True))
    return (not md_first and not lay_first) or (md_first and lay_first == md_first)


def process_page_md(page_no, md, cfg, *, ocr_lines=None, ocr_available=None, m4=None,
                    raw_resp=None, png=None, doc_sha1=None, render_reg=None):
    """单页 md_results → page part。扫描路径（GLM）：信号3/4 参与；hints/low_signal 直送二意见；
    verified_by 不伪造；补 confidence；从 GLM layout_details 提取图片索引（S6）。
    png/doc_sha1/render_reg：真实页图与登记（供 ladder 缺陷修复裁剪重读/二意见）；缺省 None（离线夹具口径）。
    表 bbox（R-13/S9-1）：md 表序 == layout table 块序（预研 180/180 成立）→ 逐位配对真实 bbox；
    数不等或首格抽查失败 → 本页表回退退化 [0,0,1,1] + routing 追加 table-bbox-unresolved note（诚实不静默）。"""
    ocr_lines = ocr_lines or []
    tables = html_to_grid(md, cfg)
    lay = _layout_table_blocks(raw_resp)
    unresolved = None
    if tables and len(lay) == len(tables):
        mismatch_i = next((i for i, tb in enumerate(tables)
                           if not _first_cell_eq(tb, lay[i][1])), None)
        if mismatch_i is None:
            for tb, (bb, _h) in zip(tables, lay):
                tb["bbox"] = bb
        else:
            for tb in tables:
                tb["bbox"] = [0, 0, 1, 1]
            unresolved = "table_bbox_unresolved: order-mismatch@%d" % mismatch_i
    elif tables:
        for tb in tables:
            tb["bbox"] = [0, 0, 1, 1]
        unresolved = "table_bbox_unresolved: md_tables=%d layout_tables=%d" % (len(tables), len(lay))
    lad = Ladder(m4 or NoOpM4(), gate_mod, cfg, BudgetGate(cfg, {GLM_CHANNEL: 1.0}), None)
    for tb in tables:
        bbox = tb.get("bbox") or [0, 0, 1, 1]
        tb["bbox"] = bbox
        av = bool(ocr_lines) if ocr_available is None else ocr_available
        fr = gate_check(tb, ocr_lines, bbox, av, cfg, ocr_expected=True)   # 扫描路径：信号3/4 参与
        tb["verified_by"] = sorted(set(_DET_SIGNALS) - {f["signal"] for f in fr["failures"]})
        tb.setdefault("confidence", None)
        tb.setdefault("method", "glm-ocr")
        tb.setdefault("issues", [])
        ctx = {"png": png, "table_bbox": bbox, "table": tb, "vendor": "deepseek",
               "cfg": cfg, "ocr_lines": ocr_lines, "ocr_available": av, "ocr_expected": True,
               "page": page_no,
               "doc_sha1": doc_sha1 or f"batch-{page_no}",
               "render_reg": render_reg or {}}
        if fr["failures"]:
            for fail in fr["failures"]:
                out = lad.resolve(tb, fail, ctx)
                tb = out["table_out"]
                break                                  # 首个 gate-failure 驱动阶梯
        elif fr["hints"] or fr["low_signal"]:
            out = lad.resolve_hint(tb, ctx)             # HINT：直送二意见（D3 终裁）
            tb = out["table_out"]
        if not tb.get("status"):
            tb["status"] = "fixed" if conservation_ok(tb) else "uncertain"
        if not tb.get("confidence"):
            tb["confidence"] = None
        if not tb.get("issues"):
            tb["issues"] = []
    imgs = _image_blocks(raw_resp)
    for im in imgs:
        im["page"] = page_no
    routing = [{"page": page_no, "method": "glm"}]
    if unresolved:
        routing.append({"page": page_no, "method": "table-bbox-unresolved", "note": unresolved})
    return {"page_number": page_no, "text": md, "lines": [],
            "blocks": [], "tables": tables, "images": imgs, "routing": routing}


def _load_ocr_lines(ocr_path):
    """加载 M5 ocr_pages 产物（{"pages":[{page, lines}]}）→ {page_no: lines}。"""
    if not ocr_path or not Path(ocr_path).exists():
        return {}
    try:
        d = json.loads(Path(ocr_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for p in d.get("pages", []):
        out[int(p["page"])] = p.get("lines", [])
    return out


def run_fixture(cfg, batch_dir, *, m4=None, standard_info=None, ocr_lines_map=None):
    """黄金夹具 180 页离线重放 → v4 JSON。ocr_lines_map 可选（扫描路径 D3/hint 用）。"""
    ocr_lines_map = ocr_lines_map or {}
    pages_parts = []
    for f in sorted(Path(batch_dir).glob("page_*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        if raw.get("http_status") != 200:
            continue
        page_no = int(f.stem.split("_")[1])
        md = (raw.get("response") or {}).get("md_results") or ""
        pages_parts.append(process_page_md(page_no, md, cfg, m4=m4,
                                           ocr_lines=ocr_lines_map.get(page_no, []),
                                           raw_resp=raw.get("response") or {}))
    return assemble_v4(pages_parts=pages_parts, standard_info=standard_info or {"name": "GBJ16-87-1"},
                       transform_registry_ref="work/render/registry.jsonl")


def acceptance_offline(cfg, batch_dir, ledger_path=None, ocr_path=None):
    """跑 fixture → v4 → measure_volume（硬指标）。ledger_path 默认夹具 batch_ledger.jsonl；
    ocr_path 默认 tests/v4/ocr_batch.json（M5 OCR 行级，扫描路径 D3/hint 验证）。返回 (v4_json, report)。"""
    if not ocr_path:
        ocr_path = Path(__file__).resolve().parents[2] / "tests" / "v4" / "ocr_batch.json"
    ocr_lines_map = _load_ocr_lines(ocr_path)
    v4 = run_fixture(cfg, batch_dir, ocr_lines_map=ocr_lines_map)
    if not ledger_path:
        ledger_path = Path(batch_dir).parent / "batch_ledger.jsonl"
    token_led = []
    if ledger_path and Path(ledger_path).exists():
        for l in Path(ledger_path).read_text(encoding="utf-8").splitlines():
            if l:
                rec = json.loads(l)
                if "est_cost_cny" in rec and "cost_cny" not in rec:
                    rec["cost_cny"] = rec["est_cost_cny"]   # 归一化夹具台账键名（shootout est_cost_cny）
                token_led.append(rec)
    report = measure_volume(v4, {"token": token_led}, cfg=cfg)
    return v4, report
