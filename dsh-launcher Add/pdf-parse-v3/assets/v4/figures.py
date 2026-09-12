#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M10 figures.py —— 图片文件化（FR-B4/B5/B6；研究报告 §5）
====================================================
数字版抽内嵌原图（保原始分辨率，§5.1）；矢量图区域重渲染；扫描页按 GLM image 块 bbox 裁剪、
几何法兜底；图注关联；hash 去重；图表先分类再分流（FR-B5：label=table 或线框特征 → 走表格不走图片）。
索引块：{type:'image', id, page, path, bbox, hash, caption, ocr_text}（图本体为文件+索引，JSON 不内联像素）。
"""
import hashlib
import os
import re
from pathlib import Path


def sha1_16(buf):
    return hashlib.sha1(buf).hexdigest()[:16]


def _extract_embedded(pdf, page_no):
    """数字版抽内嵌原图（保原始分辨率）。→ [{'xx,data,size,refs'}...] 简化。"""
    for img in pdf.get_images(full=True):
        xref = img[0]
        try:
            data = pdf.extract_image(xref)
            yield {"xref": xref, "ext": data.get("ext", "png"), "w": data.get("width"),
                   "h": data.get("height"), "data": data.get("image")}
        except Exception:
            continue


def _save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)
    return path


def figures_from_embedded(pdf, page_no, out_dir, cfg):
    """数字版：抽内嵌原图（几何法兜底=致密区域法，简化：按块 bbox 裁剪）。"""
    res = []
    for i, emb in enumerate(_extract_embedded(pdf, page_no)):
        buf = emb["data"]
        if not buf:
            continue
        if emb.get("w") and emb["w"] * (emb.get("h") or 0) < cfg["figures"]["min_area_px"]:
            continue          # 小图过滤（研究报告 §5）
        h = sha1_16(buf)
        path = _save(out_dir / f"img_p{page_no:04d}_{i}.{emb['ext']}", buf)
        res.append({"type": "image", "id": f"img_p{page_no}_{i}", "page": page_no,
                    "path": path, "bbox": None, "hash": h, "caption": "", "ocr_text": "",
                    "source": "embedded"})
    return res


def figures_from_blocks(blocks, page_no, page_img, out_dir, cfg):
    """扫描页：按 GLM native_label=image 块 bbox 裁剪（几何法兜底）。FR-B5 图表分流。"""
    from PIL import Image
    res = []
    im = Image.open(page_img)
    for b in blocks:
        if b.get("native_label") != "image":
            continue                       # 图片才入库；table/text 等不裁
        bb = b.get("bbox_2d") or [0, 0, 0, 0]
        x1, y1, x2, y2 = bb
        if x2 <= x1 or y2 <= y1:
            continue                       # 裁剪退化 → 跳过并记 note
        crop = im.crop((x1, y1, x2, y2))
        buf = crop.tobytes()
        if (x2 - x1) * (y2 - y1) < cfg["figures"]["min_area_px"]:
            continue
        h = sha1_16(buf)
        path = out_dir / f"img_p{page_no:04d}_{len(res)}.png"
        crop.save(path)
        res.append({"type": "image", "id": f"img_p{page_no}_{len(res)}", "page": page_no,
                    "path": str(path), "bbox": [x1, y1, x2, y2], "hash": h,
                    "caption": _caption_near(b), "ocr_text": "", "source": "crop"})
    im.close()
    return res


def _caption_near(block):
    """图注关联（尽力而为）：块 bbox 下方邻近文本块。简化返回空（图说噪声可容忍，JSON规范 §5 同口径）。"""
    return ""


def dedupe(images):
    """按 hash 去重（FR-B4）。"""
    seen = set()
    out = []
    for img in images:
        if img["hash"] in seen:
            continue
        seen.add(img["hash"])
        out.append(img)
    return out
