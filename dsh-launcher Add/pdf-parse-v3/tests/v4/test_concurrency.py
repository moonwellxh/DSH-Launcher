#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_concurrency.py —— 有界并发与线程安全单测（离线，v1.3 / 2026-09-27）
==================================================================
覆盖（对应详细技术设计 §6.4 限流与并发条）：
  ① 429 退避重试：requests.post 依次 429/429/200 → 返回 200，实际调用 3 次
  ② 429 退避耗尽：恒 429 → 抛 VisionError(http_4xx)，调用次数 = max_retries，且确有退避 sleep
  ③ Retry-After 优先：429 带 Retry-After: 5 → 退避取 max(1.0, 5.0) = 5.0
  ④ 其余 4xx 不重试：400 → 调用 1 次即抛 http_4xx（旧纪律不回归）
  ⑤ 台账并发完整性：8 线程 × 25 次追加 = 200 行全部可解析且序号无丢无重
  ⑥ 预算闸并发不丢账：8 线程 × 25 次 register(0.001) → 累计 0.2（无 lost update）
  ⑦ 编排真并发 + 页序稳定：6 页 / concurrency=4 → 同时在跑 ≥2、线程数 ≥2、页号升序
  ⑧ concurrency=1 回退串行：同桩下同时在跑恒为 1
用法：python tests/v4/test_concurrency.py
"""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[2]
V4 = SKILL / "assets" / "v4"
if str(V4) not in sys.path:
    sys.path.insert(0, str(V4))

import pymupdf as fitz          # noqa: E402
import vision_client as vc      # noqa: E402
import orchestrator as orc      # noqa: E402
import ocr_channel as oc        # noqa: E402
import render as rnd            # noqa: E402
import pipeline                 # noqa: E402

CFG = orc.load_config(str(SKILL))
GLM = vc.GLM_CHANNEL


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


class FakeResp:
    """最小 requests 响应替身。"""

    def __init__(self, status, headers=None, text="body"):
        self.status_code = status
        self.headers = headers or {}
        self.text = text

    def json(self):
        return {"md_results": "ok"}


def make_pdf(path, pages=6):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), "page %d 第 1 条 示例条文。" % (i + 1))
    doc.save(str(path))
    doc.close()
    return path


def run_http(scripted, *, max_retries=3):
    """按 scripted 序列返回响应；返回 (结果或异常, 调用次数, sleep 参数列表)。"""
    calls = {"n": 0}
    sleeps = []

    def fake_post(url, json=None, headers=None, timeout=None):   # noqa: A002
        calls["n"] += 1
        i = min(calls["n"] - 1, len(scripted) - 1)
        return scripted[i]

    def fake_sleep(s):
        sleeps.append(s)

    out, err = None, None
    with mock.patch.object(vc.requests, "post", fake_post), \
            mock.patch.object(vc.time, "sleep", fake_sleep):
        try:
            out = vc._http_post_json("test", "https://example.invalid", {}, {},
                                     max_retries=max_retries)
        except vc.VisionError as e:
            err = e
    return out, err, calls["n"], sleeps


def main():
    t = Tally()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ① 429 → 429 → 200
    r, e, n, sleeps = run_http([FakeResp(429), FakeResp(429), FakeResp(200)])
    t.check("①429重试后成功", r is not None and e is None and n == 3,
            "calls=%d err=%s" % (n, e))
    t.check("①429确有退避", sleeps == [1.0, 3.0] or sleeps == [1.0, 3.0, 9.0], "sleeps=%s" % sleeps)

    # ② 恒 429 → 耗尽
    r, e, n, sleeps = run_http([FakeResp(429)])
    t.check("②429耗尽抛 http_4xx", e is not None and e.kind == "http_4xx", "err=%s" % e)
    t.check("②429耗尽调用数=max_retries", n == 3, "calls=%d" % n)

    # ③ Retry-After 优先
    r, e, n, sleeps = run_http([FakeResp(429, {"Retry-After": "5"}), FakeResp(200)])
    t.check("③Retry-After(=5) 优先于内置退避", sleeps and sleeps[0] == 5.0, "sleeps=%s" % sleeps)

    # ④ 400 不重试
    r, e, n, sleeps = run_http([FakeResp(400)])
    t.check("④400 不重试（旧纪律不回归）", n == 1 and e is not None and e.kind == "http_4xx",
            "calls=%d err=%s" % (n, e))
    t.check("④400 无退避 sleep", sleeps == [], "sleeps=%s" % sleeps)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # ⑤ 台账并发完整性
        lp = td / "ledger" / "token.jsonl"

        def ledger_worker(k):
            for i in range(25):
                vc.append_token_ledger({"ts": "t", "channel": GLM, "seq": k * 25 + i}, lp)

        ths = [threading.Thread(target=ledger_worker, args=(k,)) for k in range(8)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        lines = lp.read_text(encoding="utf-8").splitlines()
        bad = 0
        seqs = []
        for ln in lines:
            try:
                seqs.append(json.loads(ln)["seq"])
            except Exception:
                bad += 1
        t.check("⑤台账行数=8×25", len(lines) == 200, "lines=%d" % len(lines))
        t.check("⑤无残缺行（逐行可解析）", bad == 0, "bad=%d" % bad)
        t.check("⑤序号无丢无重", sorted(seqs) == list(range(200)),
                "n=%d uniq=%d" % (len(seqs), len(set(seqs))))

        # ⑥ 预算闸并发不丢账
        bg = vc.BudgetGate(CFG, {GLM: None})

        def budget_worker():
            for _ in range(25):
                bg.register(GLM, 0.001)

        ths = [threading.Thread(target=budget_worker) for _ in range(8)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        # m7 诚实标注：CPython 下该 RMW 有 GIL 保护，本断言**无鉴别力**（加锁/不加锁同值）；
        # 其保留价值仅为"累计未被破坏"的冒烟检查，不构成对 _lock 的验证。
        t.check("⑥预算累计不丢账（冒烟·无鉴别力，见 m7）",
                abs(bg.costs[GLM] - 0.2) < 1e-6, "cost=%s" % bg.costs[GLM])

        # ⑦/⑧ 编排并发与页序
        pdf = make_pdf(td / "c.pdf", pages=6)
        recs = [{"page": i, "verdict": "scanned"} for i in range(1, 7)]

        def build_stub(state, lock):
            def fake_glm(doc, pno, cfg, client, work, doc_sha1):
                with lock:
                    state["active"] += 1
                    state["max"] = max(state["max"], state["active"])
                    state["tids"].add(threading.get_ident())
                time.sleep(0.05)
                with lock:
                    state["active"] -= 1
                return {"page_number": pno, "text": "t", "lines": [], "blocks": [],
                        "tables": [], "images": [], "routing": [{"page": pno, "method": "stub"}]}
            return fake_glm

        st7, lk7 = {"active": 0, "max": 0, "tids": set()}, threading.Lock()
        with mock.patch.object(orc, "_scan_page_glm", build_stub(st7, lk7)), \
                mock.patch.object(orc, "keys_available", lambda cfg: True):
            p7 = orc._run_pages(recs, pdf_path=str(pdf), cfg=CFG, client=object(),
                                work=td / "w7", doc_sha1="sha", no_egress=False, concurrency=4)
        t.check("⑦真并发（同时在跑≥2）", st7["max"] >= 2, "max_active=%d" % st7["max"])
        t.check("⑦多线程参与（线程数≥2）", len(st7["tids"]) >= 2, "tids=%d" % len(st7["tids"]))
        t.check("⑦页序稳定升序", [p["page_number"] for p in p7] == [1, 2, 3, 4, 5, 6],
                str([p["page_number"] for p in p7]))
        t.check("⑦每页 part 落盘", all((td / "w7" / "pages" / ("page_%04d.part.json" % i)).exists()
                                     for i in range(1, 7)), "6/6")

        st8, lk8 = {"active": 0, "max": 0, "tids": set()}, threading.Lock()
        with mock.patch.object(orc, "_scan_page_glm", build_stub(st8, lk8)), \
                mock.patch.object(orc, "keys_available", lambda cfg: True):
            p8 = orc._run_pages(recs, pdf_path=str(pdf), cfg=CFG, client=object(),
                                work=td / "w8", doc_sha1="sha", no_egress=False, concurrency=1)
        t.check("⑧concurrency=1 回退串行", st8["max"] == 1, "max_active=%d" % st8["max"])
        t.check("⑧串行结果同序同数", [p["page_number"] for p in p8] == [1, 2, 3, 4, 5, 6],
                str([p["page_number"] for p in p8]))

        # ⑫ A3 修复：并发度解析（默认 / 覆盖 / 越界钳制），上线与下限对称
        class _A:
            def __init__(self, c):
                self.concurrency = c

        cfg11 = json.loads(json.dumps(CFG))          # 改过 config 才证明"确实读 config"
        cfg11.setdefault("egress", {})["concurrency"] = 11
        t.check("⑫解析：None→读 config（改 11 应得 11）",
                orc._resolve_concurrency(_A(None), cfg11) == 11,
                "cfg=11 -> %d" % orc._resolve_concurrency(_A(None), cfg11))
        t.check("⑫解析：--concurrency 覆盖 config（3 胜 11）",
                orc._resolve_concurrency(_A(3), cfg11) == 3,
                "args=3,cfg=11 -> %d" % orc._resolve_concurrency(_A(3), cfg11))
        t.check("⑫解析：1 保持串行", orc._resolve_concurrency(_A(1), CFG) == 1, "1")
        t.check("⑫解析：999 钳到上限", orc._resolve_concurrency(_A(999), CFG) == orc._CONCURRENCY_MAX,
                "max=%d" % orc._CONCURRENCY_MAX)
        t.check("⑫解析：0 钳到 1", orc._resolve_concurrency(_A(0), CFG) == 1, "0->1")

        # ⑨ B2 修复：本地引擎单实例复用 + 调用串行化
        sentinel = object()
        det9 = int(CFG.get("ocr", {}).get("det_limit_side_len", 960))   # m-2：随 CFG，勿硬编码
        oc._ENGINE_CACHE.clear()
        oc._ENGINE_CACHE[det9] = sentinel
        t.check("⑨本地引擎复用已建实例", oc._make_engine(CFG) is sentinel, "det=%d" % det9)
        oc._ENGINE_CACHE.clear()
        st9, lk9 = {"active": 0, "max": 0}, threading.Lock()

        class _SlowEngine:
            def __call__(self, png):
                with lk9:
                    st9["active"] += 1
                    st9["max"] = max(st9["max"], st9["active"])
                time.sleep(0.05)
                with lk9:
                    st9["active"] -= 1
                return ([], None)

        eng9 = _SlowEngine()
        ths = [threading.Thread(target=oc.ocr_page, args=("p%d.png" % i, eng9, i))
               for i in range(1, 9)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        t.check("⑨本地引擎调用串行（同时在跑=1）", st9["max"] == 1, "max_active=%d" % st9["max"])

        # ⑩ B1 修复：本地兜底产物并发读-改-写不丢页
        w10 = td / "w10"

        def _part(i):
            return orc._scan_page_local(None, i, CFG, w10)

        with mock.patch.object(rnd, "render_page",
                               lambda pdf, pno, out_dir, cfg, dpi_floor=None: {"page": pno}), \
                mock.patch.object(rnd, "append_registry", lambda p, e: None), \
                mock.patch.object(oc, "_make_engine", lambda cfg: object()), \
                mock.patch.object(oc, "ocr_page",
                                  lambda png, e, pno: {"page": pno,
                                                       "lines": [{"box": [0, 0, 1, 1], "text": "t"}]}):
            ths = [threading.Thread(target=_part, args=(i,)) for i in range(1, 9)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        got10 = json.loads((w10 / "ocr" / "ocr_pages.json").read_text(encoding="utf-8"))["pages"]
        t.check("⑩并发兜底不丢页（8/8）",
                sorted(int(p["page"]) for p in got10) == list(range(1, 9)),
                "pages=%s" % sorted(int(p["page"]) for p in got10))

        # ⑪ S1 修复：GLM 主路径不消费本地行盒（即便存在同页残留产物）
        w11 = td / "w11"
        (w11 / "ocr").mkdir(parents=True, exist_ok=True)
        (w11 / "ocr" / "ocr_pages.json").write_text(
            json.dumps({"engine": "rapidocr_onnxruntime",
                        "pages": [{"page": 1, "lines": [{"box": [0, 0, 9, 9], "text": "stale"}]}]},
                       ensure_ascii=False), encoding="utf-8")
        cap = {}

        def _fake_ppm(pno, md, cfg, **kw):
            cap.update(kw)
            return {"page_number": pno, "text": md, "lines": [], "blocks": [],
                    "tables": [], "images": [], "routing": []}

        class _FC:
            def glm_parse_page(self, png, **kw):
                return {"raw_response": {"response": {"md_results": "md"}}}

        with mock.patch.object(rnd, "render_page",
                               lambda pdf, pno, out_dir, cfg, dpi_floor=None: {"page": pno}), \
                mock.patch.object(rnd, "append_registry", lambda p, e: None), \
                mock.patch.object(pipeline, "process_page_md", _fake_ppm):
            orc._scan_page_glm(None, 1, CFG, _FC(), w11, "sha")
        t.check("⑪GLM 路径不喂本地行盒",
                cap.get("ocr_available") is False and cap.get("ocr_lines") == [],
                "ocr_available=%s lines=%s" % (cap.get("ocr_available"), cap.get("ocr_lines")))

    # ⑬ m-1 回归：兼容模式同页号多图并发 → 只出域一次（保留串行版"已存在即跳过"语义）
    import tempfile as _tf
    from PIL import Image as _Img

    class _Args:
        pass

    with _tf.TemporaryDirectory() as td13:
        td13 = Path(td13)
        pngs = []
        for i in range(3):
            p = td13 / ("p%d.png" % i)
            _Img.new("RGB", (80, 80), (250, 250, 250)).save(p)
            pngs.append(str(p))
        calls13 = {"n": 0}

        class _VC:
            def __init__(self, *a, **kw):
                pass

            def glm_parse_page(self, png, **kw):
                calls13["n"] += 1
                time.sleep(0.05)
                return {"raw_response": {"response": {"md_results": "m"}}, "md": "m"}

        a13 = _Args()
        a13.page_image = pngs
        a13.page = 5                 # 三张图同页号 → 串行版只出域 1 次
        a13.render_reg_json = None
        a13.doc_sha1 = None
        a13.no_cache = True
        a13.no_egress = False
        a13.budget_glm = None
        a13.budget_review = None
        a13.concurrency = 3
        out13 = td13 / "out"
        with mock.patch.object(orc, "VisionClient", _VC):
            rc13 = orc._ms1_page_loop(a13, CFG, out13)
        t.check("⑬兼容模式同页号并发只出域一次", rc13 == 0 and calls13["n"] == 1,
                "rc=%s calls=%d" % (rc13, calls13["n"]))

    print("RESULT pass=%d fail=%d" % (t.pass_, t.fail))
    if t.failures:
        print("FAILED: %s" % ", ".join(t.failures))
    return 0 if t.fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
