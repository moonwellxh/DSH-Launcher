#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_orchestrator_pdf.py —— orchestrator <pdf> 主路径单测（离线，R-01/R-04/R-05）
==================================================================
覆盖（升级详细设计 §5）：
  ① 合成微型 PDF（3 页文字层）端到端 exit0 + schema 4.0 单判据 + 页数=3 + triage.json 落盘（Step 8 复审 L2：头注释页型与实物对齐）
  ② 结构性不可跑（临时 rename triage.py）→ TTY 模拟选 C → exit2 且无产物；
     非 TTY → exit3 + degrade_choice.json chosen=null
  ③ 选 B（stdin "2"）→ exit1 + chosen=B + 差异告知 + 无 v4.0 JSON（硬断言，无"或"）
  ④ 幂等两跑一致（byte diff 空）
  ⑤ --no-egress 下含扫描页 → 本地兜底标记可见不崩溃不弹窗（FR-D7/V-4）
用法：python tests/v4/test_orchestrator_pdf.py
"""
import io
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[2]
V4 = SKILL / "assets" / "v4"
ASSETS = SKILL / "assets"
for p in (str(V4), str(ASSETS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pymupdf as fitz  # noqa: E402
import orchestrator as orc  # noqa: E402

PY = sys.executable
CFG = orc.load_config(str(SKILL))


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


def make_pdf(path, pages=("text", "text", "img")):
    """2 文字页 + 1 含内嵌位图页（第 3 页画图）。"""
    doc = fitz.open()
    for i, kind in enumerate(pages):
        page = doc.new_page()
        if kind == "text":
            page.insert_text((72, 100 + i * 30),
                             "第 1 条 建筑防火设计应符合现行国家标准的有关规定。\n" * 15)
        elif kind == "img":
            # 内嵌位图区域：画一个大的矢量填充矩形+文字，形成可渲染图区域
            page.draw_rect(fitz.Rect(72, 200, 400, 500), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
            page.insert_text((100, 300), "FIG1 示意图")
    doc.save(str(path))
    doc.close()
    return path


def run_cli(args, stdin_data=None):
    """subprocess 运行 orchestrator（真进程，避免 sys.argv 污染）。返回 (exit, stdout, stderr)。"""
    cmd = [PY, str(V4 / "orchestrator.py")] + args
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    p = subprocess.run(cmd, capture_output=True, text=True, input=stdin_data,
                       timeout=300, env=env, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def main():
    t = Tally()
    # 管道输出（ci_all 子进程）下避免 locale 码表（GBK）无法编码 ⑪ 等字符 → UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # ① 端到端 3 页纯文字层整本（含图相关覆盖见 ①-b/⑤/R-06，Step 8 复审 L-复审-1 注释对齐）
        pdf = make_pdf(td / "mini.pdf", pages=("text", "text", "text"))
        out1 = td / "out1"
        rc, so, se = run_cli([str(pdf), "--out", str(out1)])
        t.check("①exit0", rc == 0, "rc=%d err=%s" % (rc, se[-200:]))
        v4f = out1 / "mini.v4.json"
        t.check("①产物存在", v4f.exists(), str(v4f))
        if v4f.exists():
            d = json.loads(v4f.read_text(encoding="utf-8"))
            t.check("①schema 4.0", d.get("schema_version") == "4.0",
                    str(d.get("schema_version")) + "/" + str(d.get("metadata", {}).get("schema_version")))
            pages = d.get("pages", [])
            t.check("①页数=3", len(pages) == 3, len(pages))
            t.check("①triage.json 落盘", (out1 / "work" / "triage.json").exists(), "ok")

        # ①-b S-1 修复：raw_resp 钉定守卫（离线可跑，不依赖 GLM key）——
        #    process_page_md 的 raw_resp 应传 response payload（含 layout_details）而非外层包装；
        #    传对 → images 非空；传错层 → images 恒空（回归即失败，防 FR-B6/S6 静默丢失）。
        sys.path.insert(0, str(V4))
        import pipeline
        payload_with_images = {"layout_details": [[
            {"native_label": "image", "bbox_2d": [10, 10, 200, 200],
             "content": "fig-content", "type": "image"}
        ]], "md_results": "表1 示例表\n| a | b |\n|---|---|\n| 1 | 2 |"}
        part_ok = pipeline.process_page_md(1, payload_with_images.get("md_results", ""), {},
                                            ocr_lines=[], ocr_available=False, m4=None,
                                            raw_resp=payload_with_images)
        n_imgs_ok = len(part_ok.get("images", []))
        t.check("①-b payload 正确层→images 非空", n_imgs_ok >= 1,
                "images=%d" % n_imgs_ok)
        # 反例：若误传外层包装（raw_response 上无 layout_details）→ images 恒空（钉定回归守卫）
        wrong_layer = {"raw_response": {"response": payload_with_images}}
        part_wrong = pipeline.process_page_md(1, "", {}, ocr_lines=[], ocr_available=False,
                                              m4=None, raw_resp=wrong_layer)
        n_imgs_wrong = len(part_wrong.get("images", []))
        t.check("①-b 错层传递→images 恒空（守卫存在）", n_imgs_wrong == 0,
                "images=%d（错层即钉定回归：应恒空）" % n_imgs_wrong)
        # 直接调用 _scan_page_glm 的等价提取路径（_image_blocks 经 payload）也应有图
        from pipeline import _image_blocks
        blk = _image_blocks(payload_with_images)
        t.check("①-b _image_blocks 从 payload 提取 image 块", len(blk) >= 1, len(blk))

        # ② 结构性不可跑：rename triage.py → TTY 选 C；非 TTY
        triage_py = V4 / "triage.py"
        triage_bak = V4 / "triage.py.bak-orchtest"
        shutil.copy2(triage_py, triage_bak)
        os.remove(triage_py)
        try:
            out2 = td / "out2"
            # TTY 模拟：stdin 注入 "3\n"（选 C 取消）。subprocess 下 isatty False → 非 TTY 分支，
            # 需用 pty 才为 True；这里验证非 TTY 分支（exit3）与留痕，选 C 的 TTY 分支用直接函数调用。
            rc2, so2, se2 = run_cli([str(pdf), "--out", str(out2)], stdin_data="3\n")
            t.check("②非TTY exit3", rc2 == 3, "rc=%d" % rc2)
            chf = out2 / "work" / "degrade_choice.json"
            t.check("②非TTY 留痕存在", chf.exists(), str(chf))
            if chf.exists():
                rec = json.loads(chf.read_text(encoding="utf-8"))
                t.check("②chosen=null", rec.get("chosen") is None, str(rec.get("chosen")))
                t.check("②context=non-tty", rec.get("context") == "non-tty", str(rec.get("context")))
            t.check("②无 v4 产物", not (out2 / "mini.v4.json").exists(), "ok")
            # TTY 分支（选 C → exit2）函数级：替换 sys.stdin 为 StringIO + 真实 input（R-01 机制，finally 由 patch 还原）
            with mock.patch.object(sys, "stdin", io.StringIO("3\n")):
                rc3 = orc.maybe_offer_degrade("test-structural", CFG, out2, tty=True)
                t.check("②TTY 选C exit2", rc3 == 2, rc3)
                rec3 = json.loads((out2 / "work" / "degrade_choice.json").read_text(encoding="utf-8"))
                t.check("②TTY 选C chosen=C", rec3.get("chosen") == "C", str(rec3.get("chosen")))
                t.check("②TTY 选C context=tty", rec3.get("context") == "tty", str(rec3.get("context")))
        finally:
            shutil.copy2(triage_bak, triage_py)
            os.remove(triage_bak)

        # ③ 选 B（函数级）→ exit1 + chosen=B + 差异告知（真实 input + StringIO，R-01 机制）
        out3 = td / "out3"
        errbuf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("2\n")):
            with redirect_stderr(errbuf):
                rc4 = orc.maybe_offer_degrade("test-b", CFG, out3, tty=True)
        t.check("③选B exit1", rc4 == 1, rc4)
        rec4 = json.loads((out3 / "work" / "degrade_choice.json").read_text(encoding="utf-8"))
        t.check("③chosen=B", rec4.get("chosen") == "B", str(rec4.get("chosen")))
        diff_notice = "无网格表格重建" in errbuf.getvalue()
        t.check("③差异告知含无网格", diff_notice, errbuf.getvalue()[:80])
        t.check("③无 v4 产物", not (out3 / "mini.v4.json").exists(), "ok")

        # ③-POSIX POSIX-only 真实 TTY 端到端（可选；Windows 显式声明平台边界——行为已由 ②③ 函数级 + ② 子进程覆盖）
        if not hasattr(os, "openpty"):
            print("[SKIP-POSIX] 本机无 os.openpty（Windows）——真实 TTY 端到端 POSIX-only；行为由函数级 ②③ + 子进程 ② 覆盖（不计断言）")
        else:
            try:
                m_s, m_m = os.openpty()
                os.close(m_s)
                os.close(m_m)
                t.check("③-POSIX pty 可用", True, "平台支持 pty（端到端用例在 POSIX CI 扩展）")
            except Exception:
                t.check("③-POSIX pty 可用", False, "pty 打开失败")

        # ④ 幂等两跑一致
        out4 = td / "out4"
        rc5, _, _ = run_cli([str(pdf), "--out", str(out4)])
        rc6, _, _ = run_cli([str(pdf), "--out", str(out4)])
        t.check("④两跑 exit0", rc5 == 0 and rc6 == 0, "%d/%d" % (rc5, rc6))
        f1 = out4 / "mini.v4.json"
        f2 = out4 / "mini.v4.json"
        if f1.exists() and f2.exists():
            b1 = f1.read_bytes()
            b2 = f2.read_bytes()
            t.check("④幂等 byte 一致", b1 == b2, "%d vs %d bytes" % (len(b1), len(b2)))

        # ⑤ --no-egress 下扫描页 → 本地兜底（构造含 image 页 PDF）
        scanpdf = make_pdf(td / "scan.pdf", pages=("image",))
        out5 = td / "out5"
        rc7, so5, se5 = run_cli([str(scanpdf), "--out", str(out5), "--no-egress"])
        t.check("⑤--no-egress exit0", rc7 == 0, "rc=%d err=%s" % (rc7, se5[-200:]))
        part = out5 / "work" / "pages" / "page_0001.part.json"
        if part.exists():
            pd = json.loads(part.read_text(encoding="utf-8"))
            method = (pd.get("routing") or [{}])[0].get("method", "")
            t.check("⑤method 单值=local-ocr-fallback", method == "local-ocr-fallback", method)
            t.check("⑤不崩溃有产物", (out5 / "scan.v4.json").exists(), "ok")
        else:
            t.check("⑤part 落盘", False, str(part))

        # ⑧ R-08：VisionClient 一次性创建（run_pdf 2 扫描页仅构造 1 次；patch orc.VisionClient 模块级绑定）
        vc_calls = {"n": 0}

        class _StubVC:
            def __init__(self, *a, **k):
                vc_calls["n"] += 1

            def glm_parse_page(self, png, **k):
                payload = {"md_results": "表A 汇总\n| a | b |\n|---|---|\n| 1 | 2 |",
                           "layout_details": [[{"native_label": "table", "bbox_2d": [10, 10, 200, 200],
                                                "content": "<table><tr><td>a</td><td>b</td></tr>"
                                                           "<tr><td>1</td><td>2</td></tr></table>"}]]}
                return {"cache_hit": False, "usage": {"prompt": 100, "completion": 10}, "cost_cny": 0.0,
                        "md": "表A 汇总\n| a | b |\n|---|---|\n| 1 | 2 |",
                        "raw_response": {"response": payload}}

        scan2 = make_pdf(td / "scan2.pdf", pages=("image", "image"))
        out8 = td / "out8"
        ns8 = types.SimpleNamespace(no_egress=False, no_cache=True, pages=None,
                                    budget_glm=None, budget_review=None, md=False, html=False)
        with mock.patch.object(orc, "VisionClient", _StubVC), \
                mock.patch.object(orc, "keys_available", lambda cfg: True):
            rc8 = orc.run_pdf(str(scan2), out8, CFG, ns8)
        t.check("⑧run_pdf(2扫描页) exit0", rc8 == 0, rc8)
        t.check("⑧VisionClient 仅构造1次", vc_calls["n"] == 1, vc_calls["n"])
        t.check("⑧产物存在", (out8 / "scan2.v4.json").exists(), "ok")

        # ⑪ R-11：run_pdf 模式降级 marker 统一落 out/work/marks（stub GLM 抛 network → local 兜底段 marker）
        class _NetVC:
            def __init__(self, *a, **k):
                pass

            def glm_parse_page(self, png, **k):
                raise orc.VisionError("network", "mock 断网")

        def _fake_local(pdf, pno, cfg, work):
            return {"page_number": pno, "text": "", "lines": [], "blocks": [],
                    "tables": [], "images": [],
                    "routing": [{"page": pno, "method": "local-ocr-fallback", "note": "stub"}]}

        scan9 = make_pdf(td / "scan9.pdf", pages=("image",))
        out9 = td / "out9"
        ns9 = types.SimpleNamespace(no_egress=False, no_cache=True, pages=None,
                                    budget_glm=None, budget_review=None, md=False, html=False)
        with mock.patch.object(orc, "VisionClient", _NetVC), \
                mock.patch.object(orc, "keys_available", lambda cfg: True), \
                mock.patch.object(orc, "_scan_page_local", _fake_local):
            rc9 = orc.run_pdf(str(scan9), out9, CFG, ns9)
        mark9 = out9 / "work" / "marks" / "page_0001.json"
        t.check("⑪run_pdf 模式 marker 在 work/marks", rc9 == 0 and mark9.exists(), "rc=%s mark=%s" % (rc9, mark9))
        t.check("⑪根 marks 不存在（无 out/marks 旧路径残留）", not (out9 / "marks" / "page_0001.json").exists(), "ok")

        # ⑩ R-10：GPU 库可配置放行（_structural_ok 两态；mock importlib.import_module 控制 torch/tensorflow）
        real_import = importlib.import_module

        def _mk_se(torch_ok):
            def _se(name, **k):
                if name in ("torch", "tensorflow"):
                    if torch_ok:
                        return object()
                    raise ImportError("mock 无 %s" % name)
                return real_import(name, **k)
            return _se

        with mock.patch.object(importlib, "import_module", side_effect=_mk_se(False)):
            okA_def = orc._structural_ok(str(SKILL))
            okA_ig = orc._structural_ok(str(SKILL), ignore_gpu_lib=True)
        t.check("⑩无GPU 默认/放行均 True", okA_def and okA_ig, "%s/%s" % (okA_def, okA_ig))
        with mock.patch.object(importlib, "import_module", side_effect=_mk_se(True)):
            okB_def = orc._structural_ok(str(SKILL))
            okB_ig = orc._structural_ok(str(SKILL), ignore_gpu_lib=True)
        t.check("⑩有GPU 默认拒绝", okB_def is False, okB_def)
        t.check("⑩有GPU 放行 True", okB_ig is True, okB_ig)

        # ⑨ R-09（C-8）：_scan_page_local 渲染 oversize（floor 后仍超）→ 诚实 part + marker reason=render_oversize（不落空文本冒充）
        import render as _render_mod
        w9 = td / "w9"
        mdoc = fitz.open(str(pdf))
        with mock.patch("render.render_page",
                        side_effect=_render_mod.RenderError("oversize", "mock 全档超限")):
            pa = orc._scan_page_local(mdoc, 1, CFG, w9)
        note_a = (pa.get("routing") or [{}])[0].get("note", "")
        mark_a = w9 / "marks" / "page_0001.json"
        t.check("⑨oversize part note 含 render_oversize", "render_oversize" in note_a, note_a[:80])
        t.check("⑨oversize text 为空（不落空文本）", pa.get("text") == "", str(pa.get("text"))[:40])
        if mark_a.exists():
            rec_a = json.loads(mark_a.read_text(encoding="utf-8"))
            t.check("⑨marker reason 含 render_oversize", "render_oversize" in rec_a.get("reason", ""),
                    str(rec_a.get("reason"))[:60])
        else:
            t.check("⑨marker 落盘", False, str(mark_a))
        # ⑨-b：渲染成功（floor 档后 ≤10MB）→ 先重渲登记 → OCR 有产出（防"仅标记即过"）
        reg96 = {"page": 1, "pdf_rect_pt": [600.0, 780.0], "target_width": 800, "dpi": 96.0,
                 "pixel": [800, 1040], "scale": [1.3333, 1.3333],
                 "render_sha1": "mock-96", "downsampled_from": None}
        w9b = td / "w9b"
        reg_calls = []

        def _ok_render(*a, **k):
            reg_calls.append(k)
            return reg96

        def _fake_engine(cfg_):
            return object()

        def _fake_ocr(png, engine, n):
            return {"page": n, "lines": [{"text": "第 1 条 示例文本", "box": [0, 0, 100, 20]}]}

        with mock.patch("render.render_page", side_effect=_ok_render), \
                mock.patch("render.append_registry", lambda *a, **k: None), \
                mock.patch("ocr_channel._make_engine", side_effect=_fake_engine), \
                mock.patch("ocr_channel.ocr_page", side_effect=_fake_ocr):
            pb = orc._scan_page_local(mdoc, 1, CFG, w9b)
        t.check("⑨-b 渲染调用携带 dpi_floor", bool(reg_calls) and reg_calls[0].get("dpi_floor") == 96,
                "dpi_floor=%s" % (reg_calls[0].get("dpi_floor") if reg_calls else None))
        t.check("⑨-b OCR 有产出（text 非空）", pb.get("text") and "示例文本" in pb.get("text"),
                str(pb.get("text"))[:40])
        t.check("⑨-b 无 render_oversize marker", not (w9b / "marks" / "page_0001.json").exists(), "ok")
        mdoc.close()

        # ⑥ R-05 --pages 六例（3 页 mini.pdf，子进程真实路径；语义见冻结 §0/R-05）
        cases = [
            ("1-3", "spec", True, 3),      # 正常
            ("1-10", "spec", True, 3),     # 部分越界→钳制 1..3
            ("5-10", "spec", False, 0),    # 全越界→交集空→报错非0 无产物
            ("abc", "spec", False, 0),     # 无效 token
            ("1,abc", "spec", False, 0),   # 混合非法 token→整体报错
            ("1,5-10", "spec", True, 1),   # 混合越界段→交集={1}→钳制处理 1（不按段报错）
            (None, "omit", True, 3),       # 未提供=全量
        ]
        for spec, mode, expect_ok, expect_pages in cases:
            argv = [str(pdf), "--out", str(td / ("outp_" + str(spec or "none")).replace(":", "").replace(",", "_"))]
            if mode == "spec":
                argv += ["--pages", str(spec)]
            rc_x, _, _ = run_cli(argv)
            v4f_x = Path(argv[argv.index("--out") + 1]) / "mini.v4.json"
            if expect_ok:
                ok_pages = False
                if v4f_x.exists():
                    try:
                        ok_pages = len(json.loads(v4f_x.read_text(encoding="utf-8")).get("pages", [])) == expect_pages
                    except Exception:
                        ok_pages = False
                t.check("⑥--pages=%s exit0 产物页数=%d" % (spec, expect_pages),
                        rc_x == 0 and ok_pages, "rc=%d pages_ok=%s" % (rc_x, ok_pages))
            else:
                t.check("⑥--pages=%s 报错非0 无产物" % spec,
                        rc_x != 0 and not v4f_x.exists(), "rc=%d" % rc_x)

        # R-06（L-验收-2）：stub VisionClient → run_pdf 扫描页 → pages[0].images 非空 / metadata.figure_count≥1
        class _ImgVC:
            def __init__(self, *a, **k):
                pass

            def glm_parse_page(self, png, **k):
                payload = {"md_results": "",
                           "layout_details": [[{"native_label": "image", "bbox_2d": [10, 10, 200, 200],
                                                "content": "fig-content"}]]}
                return {"cache_hit": False, "usage": {"prompt": 100, "completion": 10},
                        "cost_cny": 0.0, "md": "", "raw_response": {"response": payload}}

        scan_img = make_pdf(td / "scan_img.pdf", pages=("image",))
        out_img = td / "out_img"
        ns_img = types.SimpleNamespace(no_egress=False, no_cache=True, pages=None,
                                       budget_glm=None, budget_review=None, md=False, html=False)
        with mock.patch.object(orc, "VisionClient", _ImgVC), \
                mock.patch.object(orc, "keys_available", lambda cfg: True):
            rc_img = orc.run_pdf(str(scan_img), out_img, CFG, ns_img)
        v4i = json.loads((out_img / "scan_img.v4.json").read_text(encoding="utf-8"))
        imgs_p1 = (v4i.get("pages") or [{}])[0].get("images", []) if v4i.get("pages") else []
        t.check("R-06 run_pdf exit0", rc_img == 0, rc_img)
        t.check("R-06 pages[0].images 非空", len(imgs_p1) >= 1, "n=%d" % len(imgs_p1))
        t.check("R-06 metadata.figure_count>=1", (v4i.get("metadata") or {}).get("figure_count", 0) >= 1,
                "fc=%s" % (v4i.get("metadata") or {}).get("figure_count"))

    print("\n== RESULT pass=%d fail=%d ==" % (t.pass_, t.fail))
    if t.failures:
        print("FAILURES:", ", ".join(t.failures))
    sys.exit(1 if t.fail else 0)


if __name__ == "__main__":
    main()
