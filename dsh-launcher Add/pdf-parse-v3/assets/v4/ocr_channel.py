#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M5 ocr_channel.py —— 本地 OCR 行级识别，保留四点 box（FR-B1 扫描双源；交叉对位/几何错位信号源）
==================================================================
设计依据：详细技术设计 §6.5（修复 rapid_ocr_pages.py 第 86–87 行丢弃 box 缺陷——本模块核心改造点）；
需求书 FR-B1（扫描路径坐标双源：GLM 块级 + 本地 OCR 行四点 box）。

产物（每页）：{"page":N, "lines":[{"box":[x1,y1,x2,y2], "box4":[[x,y]x4], "text":"...", "source":"ocr"}]}
box = box4 的轴对齐外接框；box4 保留原始四点供倾斜页。行排序沿用 sort_key（y/12 量化 + x）。
断点续跑：每页落盘，重跑跳过已完成页（FR-G1）。OCR 引擎缺失/失败 → OcrUnavailable（信号缺失纪律）。
"""
import glob
import json
import os
import re
import sys
import time
from pathlib import Path


class OcrUnavailable(Exception):
    def __init__(self, detail=""):
        self.detail = detail
        super().__init__(f"OcrUnavailable: {detail}")


def sort_key(box4):
    ys = [p[1] for p in box4]
    xs = [p[0] for p in box4]
    return (round(min(ys) / 12.0), min(xs))


def _bbox(box4):
    xs = [p[0] for p in box4]
    ys = [p[1] for p in box4]
    return [int(round(min(xs))), int(round(min(ys))),
            int(round(max(xs))), int(round(max(ys)))]


def _make_engine(cfg):
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as e:
        raise OcrUnavailable(f"rapidocr_onnxruntime 缺失/失败: {e}")
    det = cfg.get("ocr", {}).get("det_limit_side_len", 960)
    return RapidOCR(det_limit_side_len=int(det))


def ocr_page(png_path, engine, page):
    """单页 OCR。返回 {"page":N, "lines":[{"box","box4","text","source":"ocr"}]}。"""
    try:
        res, _ = engine(png_path)
    except Exception as e:
        raise OcrUnavailable(f"OCR 失败 {page}: {e}")
    lines = []
    if res:
        for r in sorted(res, key=lambda rr: sort_key(rr[0])):
            box4 = [[float(p[0]), float(p[1])] for p in r[0]]
            lines.append({"box": _bbox(box4), "box4": box4,
                          "text": r[1], "source": "ocr"})
    return {"page": page, "lines": lines}


def ocr_pages(png_dir, cfg, out_json):
    """OCR 目录内 page_*.png → 每页落盘（断点续跑）。返回 {"pages":[...]}。"""
    det = cfg.get("ocr", {}).get("det_limit_side_len", 960)
    engine = _make_engine(cfg)
    out = Path(out_json)
    done = {}
    if out.exists():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            for p in prev.get("pages", []):
                done[int(p["page"])] = p
        except Exception:
            done = {}
    files = sorted(glob.glob(str(Path(png_dir) / "page_*.png")),
                   key=lambda p: int(re.search(r"page_(\d+)_?\.png$", p).group(1)))
    pages = list(done.values())
    t_all = time.time()
    for i, f in enumerate(files, 1):
        pno = int(re.search(r"page_(\d+)_?\.png$", f).group(1))
        if pno in done:
            continue
        try:
            page_res = ocr_page(f, engine, pno)
        except OcrUnavailable as e:
            print(f"[skip] page {pno} -> {e}")
            continue
        pages.append(page_res)
        pages.sort(key=lambda p: p["page"])
        out.write_text(json.dumps({"engine": "rapidocr_onnxruntime", "det_limit_side_len": det,
                                   "pages": pages}, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] page {pno} lines={len(page_res['lines'])} elapsed={round(time.time()-t_all,1)}s", flush=True)
        time.sleep(0.3)
    print(f"DONE pages={len(pages)} total={round(time.time()-t_all,1)}s -> {out_json}")
    return {"pages": pages}
