#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_render.py —— M2 render 单测（离线，R-03）
==================================================================
覆盖（升级详细设计 §2.3 + R-03 验收）：
  ① 小 PDF 3 页 → PNG 存在 + registry 字段齐全（page/pdf_rect_pt/target_width/dpi/pixel/scale/render_sha1）
  ② 换算自检：pt_to_px(px_to_pt(b)) 与 b 逐轴差 ≤1px（10 随机 bbox）
  ③ registry 口径 m-05：dpi == round(pixel_w/pdf_w*72)
  ④ 坐标换算可复算裁剪区：crop_png 产出非空
  ⑤ 渲染失败/降档路径：超大页（高密度图）触发降档或 oversize 之一（分别断言，不互斥为或）
用法：python tests/v4/test_render.py
"""
import io
import random
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
V4 = SKILL / "assets" / "v4"
for p in (str(V4), str(SKILL / "assets")):
    if p not in sys.path:
        sys.path.insert(0, p)

import pymupdf as fitz  # noqa: E402
import render  # noqa: E402
from PIL import Image  # noqa: E402

CFG = {"render": {"dpi_default": 220, "resolution_steps": [220, 180, 150]}}
CFG_SINGLE220 = {"render": {"dpi_default": 220, "resolution_steps": [220]}}
CFG_FLOOR = {"render": {"dpi_default": 150, "resolution_steps": [150]}}   # floor 补测：档序=仅 150，floor 96 为末档兜底


def make_noise_pdf(path, w_pt, h_pt, img_w=2200, img_h=2860, seed=7):
    """整页嵌入高熵噪声位图（RGB 随机）——PNG 大小∝像素数，供降档/floor 夹具校准（处理遗留 R-02/R-07/R-09）。"""
    doc = fitz.open()
    page = doc.new_page(width=w_pt, height=h_pt)
    r = random.Random(seed)
    buf = io.BytesIO()
    Image.frombytes("RGB", (img_w, img_h), r.randbytes(img_w * img_h * 3)).save(buf, "PNG")
    page.insert_image(fitz.Rect(0, 0, w_pt, h_pt), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()
    return path


class Tally:
    def __init__(self):
        self.pass_ = 0
        self.fail = 0
        self.failures = []

    def check(self, name, ok, detail=""):
        if ok:
            self.pass_ += 1
            print("[PASS] %s %s" % (name, detail))
        else:
            self.fail += 1
            self.failures.append(name)
            print("[FAIL] %s %s" % (name, detail))


def make_small_pdf(path, pages=3):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100 + i * 20), "render test page %d line1\nline2" % (i + 1))
    doc.save(str(path))
    doc.close()
    return path


def main():
    t = Tally()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pdf_path = make_small_pdf(td / "small.pdf", pages=3)
        doc = fitz.open(str(pdf_path))

        # ① 渲染 3 页
        regs = render.render_pages(doc, [1, 2, 3], td / "pages", CFG)
        t.check("①渲染 3 页返回 3 登记", len(regs) == 3, len(regs))
        need = {"page", "pdf_rect_pt", "target_width", "dpi", "pixel", "scale", "render_sha1"}
        missing = need - set(regs[0].keys())
        t.check("①registry 字段齐全", not missing, "missing=%s" % sorted(missing))
        for pno in (1, 2, 3):
            png = td / "pages" / ("page_%04d.png" % pno)
            t.check("①PNG 存在 page %d" % pno, png.exists() and png.stat().st_size > 0, str(png))
        # ② 换算自检
        reg0 = regs[0]
        ok_px = True
        worst = 0
        random.seed(7)
        for _ in range(10):
            b = [random.uniform(50, 500), random.uniform(50, 700),
                 random.uniform(600, 900), random.uniform(800, 1000)]
            round_trip = render.pt_to_px(render.px_to_pt(b, reg0), reg0)
            worst = max(worst, max(abs(round_trip[i] - b[i]) for i in range(4)))
            if any(abs(round_trip[i] - b[i]) > 1 for i in range(4)):
                ok_px = False
        t.check("②换算自检 ≤1px", ok_px, "worst=%.2f" % worst)
        # ③ m-05：dpi == round(pixel_w/pdf_w*72)
        pdf_w = reg0["pdf_rect_pt"][0]
        dpi_calc = round(reg0["pixel"][0] / pdf_w * 72, 4)
        t.check("③dpi 派生口径 m-05", abs(reg0["dpi"] - dpi_calc) <= 0.5,
                "reg.dpi=%s calc=%s" % (reg0["dpi"], round(dpi_calc, 2)))
        # ④ crop 复算
        png = td / "pages" / "page_0001.png"
        crop_out = td / "crop.png"
        try:
            r = render.crop_png(str(png), [100, 100, 400, 400], str(crop_out))
            t.check("④crop_png 产出", crop_out.exists() and crop_out.stat().st_size > 0, r)
        except render.RenderError as e:
            t.check("④crop_png 产出", False, str(e))
        # ⑤ registry.jsonl 追加
        regf = td / "registry.jsonl"
        render.append_registry(regf, regs)
        lines = regf.read_text(encoding="utf-8").strip().splitlines()
        t.check("⑤registry.jsonl 3 行", len(lines) == 3, len(lines))
        doc.close()          # Windows 释放 small.pdf

        # ⑥' R-02 降档登记（处理遗留 C-2）：噪声高熵夹具——夹具有效性前置（单档 220 >10MB）→ dpi<default 单判据
        # 校准实测（calibrate_noise.py，seed=7）：600×780pt → 220dpi png≈11.9MB、180dpi≈7.7MB、150dpi≈5.2MB
        noise = td / "noise.pdf"
        make_noise_pdf(noise, 600, 780, seed=7)
        ndoc = fitz.open(str(noise))
        try:
            try:
                render.render_page(ndoc, 1, td / "np220", CFG_SINGLE220)
                t.check("⑥'前置 单档220 超限（夹具有效）", False, "未抛 oversize——夹具无效需重校准")
            except render.RenderError as e:
                t.check("⑥'前置 单档220 oversize", e.kind == "oversize", e.kind)
            nreg = render.render_page(ndoc, 1, td / "npfull", CFG)
            npng = td / "npfull" / "page_0001.png"
            t.check("⑥'降档登记 dpi<220（唯一判据）", nreg["dpi"] < CFG["render"]["dpi_default"],
                    "dpi=%s" % nreg["dpi"])
            t.check("⑥'png ≤10MB", npng.stat().st_size <= 10 * 1024 * 1024,
                    "bytes=%d" % npng.stat().st_size)
            t.check("⑥'downsampled_from=None", nreg.get("downsampled_from") is None,
                    str(nreg.get("downsampled_from")))
        finally:
            ndoc.close()

        # ⑦ R-07 target_width 指定也真降档（处理遗留 C-5）：请求 3000 宽首候选必然 >10MB（≈35MB）→ 梯档可达 ≤10MB
        ndoc2 = fitz.open(str(noise))
        try:
            treg = render.render_page(ndoc2, 1, td / "nptw", CFG, target_width=3000)
            tpng = td / "nptw" / "page_0001.png"
            pdf_w = treg["pdf_rect_pt"][0]
            t.check("⑦终态 tw<请求 3000", treg["target_width"] < 3000,
                    "tw=%s" % treg["target_width"])
            t.check("⑦降档 dpi<220", treg["dpi"] < CFG["render"]["dpi_default"],
                    "dpi=%s" % treg["dpi"])
            t.check("⑦png ≤10MB", tpng.stat().st_size <= 10 * 1024 * 1024,
                    "bytes=%d" % tpng.stat().st_size)
            t.check("⑦m-05 pixel 反算口径", abs(treg["pixel"][0] / pdf_w * 72 - treg["dpi"]) <= 0.5,
                    "%s vs %s" % (round(treg["pixel"][0] / pdf_w * 72, 3), treg["dpi"]))
        finally:
            ndoc2.close()

        # ⑧ R-09 floor 真实重渲（交付审查 S1 补测）：150 档仍超、floor 96 落 ≤10MB（真实渲染非 mock）
        # 夹具：1100×1100pt seed=11，嵌入位图 3356×3356（≈页宽×220dpi）；校准实测（floor_calibrate.py 同族尺寸）
        #   150dpi png≈13.76MiB（>10MiB 判限，余量 +3.8MiB）、96dpi≈5.17MiB（≤10MiB，余量 −4.8MiB）——单位 MiB
        floor_pdf = td / "floor.pdf"
        make_noise_pdf(floor_pdf, 1100, 1100, img_w=3356, img_h=3356, seed=11)
        fdoc = fitz.open(str(floor_pdf))
        try:
            try:
                render.render_page(fdoc, 1, td / "fl150", CFG_FLOOR)
                t.check("⑧前置 150档未超限（夹具无效）", False, "未抛 oversize——夹具需重校准")
            except render.RenderError as e:
                t.check("⑧150档仍超→oversize", e.kind == "oversize", e.kind)
            freg = render.render_page(fdoc, 1, td / "fl96", CFG_FLOOR, dpi_floor=96)
            fpng = td / "fl96" / "page_0001.png"
            fw_pt = freg["pdf_rect_pt"][0]
            t.check("⑧floor 命中 dpi==96", freg["dpi"] == 96.0, "dpi=%s" % freg["dpi"])
            t.check("⑧png ≤10MB", fpng.stat().st_size <= 10 * 1024 * 1024,
                    "bytes=%d" % fpng.stat().st_size)
            t.check("⑧downsampled_from=None", freg.get("downsampled_from") is None,
                    str(freg.get("downsampled_from")))
            t.check("⑧m-05 pixel 反算口径", abs(freg["pixel"][0] / fw_pt * 72 - freg["dpi"]) <= 0.5,
                    "%s vs %s" % (round(freg["pixel"][0] / fw_pt * 72, 3), freg["dpi"]))
        finally:
            fdoc.close()
    print("\n== RESULT pass=%d fail=%d ==" % (t.pass_, t.fail))
    if t.failures:
        print("FAILURES:", ", ".join(t.failures))
    sys.exit(1 if t.fail else 0)


if __name__ == "__main__":
    main()
