#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2 render.py —— PDF 页渲染 + 变换登记（FR-B2）+ 10MB 降档
==================================================================
作用：PDF+页码 → work/pages/page_NNNN.png + registry 条目（渲染像素系坐标登记）。
输入：pdf(fitz doc) + page_no + out_dir + cfg；输出：registry 条目 dict。
复跑：由 orchestrator 调用 render_page/render_pages/append_registry；单测直跑。
改造源：assets/render-pages.ps1（WinRT）→ 提炼进 Python（PyMuPDF get_pixmap，KD7）。
设计锚点：升级详细技术设计 §2；冻结详细技术设计 §3（坐标系/登记 m-05）/§6.2/§10。
"""
import hashlib
import json
import threading
from pathlib import Path

_MAX_PNG_BYTES = 10 * 1024 * 1024     # GLM 单图上限（冻结 §3.4/需求书 §10）

_REGISTRY_LOCK = threading.Lock()     # v1.3：编排并发后 registry.jsonl 追加须互斥

# #12（2026-09-27）：MuPDF / pdfminer 官方均声明非线程安全。口径（m-3 收窄，2026-09-27）：
#   * 每线程各持一份 Document（`orchestrator._thread_doc`），不跨线程共享句柄；
#   * **重活串行**——本模块的 get_pixmap/save、textlayer 的取字/取图/pdfplumber 全走此锁。
#   * 未纳入锁的轻量访问：`fitz.open`（建句柄）与 `doc[pno-1]`/`page.rect`（取页与尺寸），
#     由"每线程独立 Document"保证；如需绝对保守可一并纳入。
# 网络出域并发不受影响——渲染是每页毫秒~秒级，相对 GLM 的秒级调用占比很小。
PDF_BACKEND_LOCK = threading.RLock()


class RenderError(Exception):
    """oversize | crop_degenerate | render_failed —— 编排层据 FR-D7 处理。"""

    def __init__(self, kind, detail=""):
        self.kind = kind
        self.detail = detail
        super().__init__("RenderError(%s): %s" % (kind, detail))


def _png_size_ok(png_path):
    return Path(png_path).stat().st_size <= _MAX_PNG_BYTES


def render_page(pdf, page_no, out_dir, cfg, target_width=None, dpi_floor=None):
    """单页渲染。target_width 指定优先；缺省由 cfg.render.dpi_default 反推（登记口径 m-05）。
        超 10MB 按档候选降档（处理遗留 R-07/C-5：target_width 指定时亦真降档——候选=请求宽+各档派生宽严格递减；
        处理遗留 R-09/C-8：dpi_floor 为档序耗尽后的末档兜底，仍超 → RenderError(oversize)）。
        登记口径：缺省路径 dpi=档值（既有行为）；target_width 路径 dpi=按实渲宽度派生（两向满足 m-05）。
        返回 registry 条目 dict。"""
    with PDF_BACKEND_LOCK:                 # #12：MuPDF 非线程安全
        page = pdf[page_no - 1]
        rect = page.rect
        pdf_w, pdf_h = rect.width, rect.height
    if pdf_w <= 0 or pdf_h <= 0:
        raise RenderError("render_failed", "page %d 尺寸非法 %s" % (page_no, [pdf_w, pdf_h]))
    render_cfg = cfg.get("render", {})
    dpi_default = float(render_cfg.get("dpi_default", 220))
    steps = render_cfg.get("resolution_steps", [dpi_default])
    # dpi 档位去重保序；dpi_default 优先
    seen, dpi_steps = set(), []
    for s in steps:
        s = float(s)
        if s not in seen:
            seen.add(s)
            dpi_steps.append(s)
    if dpi_default not in dpi_steps:
        dpi_steps.insert(0, dpi_default)

    def w_of(d):
        return int(round(pdf_w * float(d) / 72.0))

    # 候选 (登记 dpi, 渲染宽 tw)：严格递减，避免同宽重渲
    tries = []          # 元素: (reg_dpi, tw)
    if target_width is not None:
        req = int(target_width)
        if req <= 0:
            raise RenderError("render_failed", "page %d target_width 非法 %s" % (page_no, req))
        cur = req
        tries.append((round(req * 72.0 / pdf_w, 4), req))
        for d in dpi_steps:
            cw = w_of(d)
            if cw < cur:
                tries.append((round(cw * 72.0 / pdf_w, 4), cw))
                cur = cw
        if dpi_floor is not None:
            fw = w_of(float(dpi_floor))
            if fw < cur:
                tries.append((round(fw * 72.0 / pdf_w, 4), fw))
    else:
        for d in dpi_steps:
            cw = w_of(d)
            if not tries or cw < tries[-1][1]:
                tries.append((float(d), cw))
        if dpi_floor is not None:
            fw = w_of(float(dpi_floor))
            if fw < tries[-1][1]:
                tries.append((float(dpi_floor), fw))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    last_err = None
    for reg_dpi, tw in tries:
        import pymupdf as fitz
        mat = fitz.Matrix(reg_dpi / 72.0, reg_dpi / 72.0)
        try:
            with PDF_BACKEND_LOCK:
                pix = page.get_pixmap(matrix=mat)
        except Exception as e:
            last_err = RenderError("render_failed", "page %d dpi=%s: %s" % (page_no, reg_dpi, e))
            continue
        png = out / ("page_%04d.png" % page_no)
        try:
            with PDF_BACKEND_LOCK:
                pix.save(str(png))
        except Exception as e:
            last_err = RenderError("render_failed", "save %s: %s" % (png, e))
            continue
        if _png_size_ok(png):
            px_w, px_h = pix.width, pix.height
            return {"page": page_no,
                    "pdf_rect_pt": [round(pdf_w, 2), round(pdf_h, 2)],
                    "target_width": tw,
                    "dpi": round(reg_dpi, 4),
                    "pixel": [px_w, px_h],
                    "scale": [round(px_w / pdf_w, 4), round(px_h / pdf_h, 4)],
                    "render_sha1": hashlib.sha1(Path(png).read_bytes()).hexdigest(),
                    "downsampled_from": None}
        # >10MB：降档重渲覆盖（last_err 保持 None = 无硬失败，继续下一候选）
        last_err = None
    if last_err is not None:
        raise last_err
    raise RenderError("oversize", "page %d 全档位（含 dpi_floor）仍 >10MB" % page_no)


def render_pages(pdf, page_nos, out_dir, cfg):
    """批量渲染（断点由编排层管理）。返回 registry 条目列表。"""
    regs = []
    for pno in page_nos:
        regs.append(render_page(pdf, pno, out_dir, cfg))
    return regs


def append_registry(reg_path, entries):
    """registry.jsonl 追加（每页一条 JSON line，UTF-8）。"""
    reg_path = Path(reg_path)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    with _REGISTRY_LOCK:
        with reg_path.open("a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


def px_to_pt(box, reg):
    """像素系 → PDF 点系（FR-B2 复算）。"""
    sx, sy = reg["scale"]
    return [box[0] / sx, box[1] / sy, box[2] / sx, box[3] / sy]


def pt_to_px(box, reg):
    """PDF 点系 → 像素系（文字层路径入库前换算）。"""
    sx, sy = reg["scale"]
    return [round(box[0] * sx), round(box[1] * sy),
            round(box[2] * sx), round(box[3] * sy)]


def crop_png(png_path, box_px, out_path, pad=8):
    """按像素 bbox 裁剪页图（pad 安全边际）。越界/退化 → RenderError(crop_degenerate)。"""
    from PIL import Image
    im = Image.open(png_path)
    x1, y1, x2, y2 = box_px
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(im.width, x2 + pad)
    y2 = min(im.height, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        raise RenderError("crop_degenerate", "%s on %s" % (box_px, png_path))
    im.crop((x1, y1, x2, y2)).save(out_path)
    return {"bbox_px": [x1, y1, x2, y2], "pad": pad}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python render.py <pdf> <out_dir> [pages '1,2,3']")
        sys.exit(2)
    import pymupdf as fitz
    import json as _json
    pdf_path, out_dir = sys.argv[1], sys.argv[2]
    spec = sys.argv[3] if len(sys.argv) > 3 else ""
    pages = [int(x) for x in spec.split(",") if x.strip()] or None
    doc = fitz.open(pdf_path)
    cfg = {"render": {"dpi_default": 220, "resolution_steps": [220, 180, 150]}}
    nos = pages or list(range(1, doc.page_count + 1))
    regs = render_pages(doc, nos, out_dir, cfg)
    print(_json.dumps(regs, ensure_ascii=False, indent=1))
