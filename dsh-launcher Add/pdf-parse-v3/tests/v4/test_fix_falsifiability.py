# -*- coding: utf-8 -*-
"""变异探针：证明 ⑨⑩⑪ 三条修复断言具备鉴别力（去掉修复即失败）。

不修改任何产品文件。三种手法互不相同，勿混说成"一律替换成未修复形态"：
  M-⑩：把 `_OCR_STORE_LOCK` 换成空锁，并在 `Path.read_text` 注入屏障强制 8 线程读同一初值
        → 走**真实** `_scan_page_local` 确定性丢页（真变异 + 不依赖调度）
  M-⑨：把 `_ENGINE_LOCK` 在内存里换成空锁 → 本地引擎并发同时在跑应 >1（真变异）
  M-⑪：不做替换，改做**同一输入下的 A/B 对照 + 负对照**——A 面用真实
        `_ocr_lines_for` 对真实残留文件求值（B 面跑现网 `_scan_page_glm` 捕获实传值），
        并以"空 work 目录必须返回 []"作负对照，三者任一恒真即失败。
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

import orchestrator as orc      # noqa: E402
import ocr_channel as oc        # noqa: E402
import render as rnd            # noqa: E402
import vision_client as vc2     # noqa: E402
import pipeline                 # noqa: E402

CFG = orc.load_config(str(SKILL))
pass_, fail = 0, 0


def check(name, ok, detail=""):
    global pass_, fail
    if ok:
        pass_ += 1
        print("[PASS] %s %s" % (name, detail))
    else:
        fail += 1
        print("[FAIL] %s %s" % (name, detail))


class NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # M-⑩：**真变异 + 确定性**——走真实 `_scan_page_local`，只把 `_OCR_STORE_LOCK` 换成空锁，
        #      并在 `Path.read_text` 注入屏障：8 个线程都读到同一初值后才允许任何一次写回。
        #      （形态一：真变异但靠竞态自发生 → 概率性假红；形态二：确定性但另抄一份 racy RMW
        #       → 与产品解耦、恒真。本形态同时避开两者。）
        w = td / "w10"
        (w / "ocr").mkdir(parents=True, exist_ok=True)
        (w / "ocr" / "ocr_pages.json").write_text(
            json.dumps({"engine": "rapidocr_onnxruntime", "pages": []}), encoding="utf-8")
        bar = threading.Barrier(8, timeout=20)
        real_read = Path.read_text

        def slow_read(self, *a, **kw):
            txt = real_read(self, *a, **kw)
            if self.name == "ocr_pages.json":
                bar.wait()                # 8 个读者全读完，才放行写回
            return txt

        with mock.patch.object(orc, "_OCR_STORE_LOCK", NoLock()), \
                mock.patch.object(Path, "read_text", slow_read), \
                mock.patch.object(rnd, "render_page",
                                  lambda pdf, pno, out_dir, cfg, dpi_floor=None: {"page": pno}), \
                mock.patch.object(rnd, "append_registry", lambda p, e: None), \
                mock.patch.object(oc, "_make_engine", lambda cfg: object()), \
                mock.patch.object(oc, "ocr_page",
                                  lambda png, e, pno: {"page": pno,
                                                       "lines": [{"box": [0, 0, 1, 1], "text": "t"}]}):
            ths = [threading.Thread(target=orc._scan_page_local, args=(None, i, CFG, w))
                   for i in range(1, 9)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        lost = sorted(int(p["page"]) for p in json.loads(
            (w / "ocr" / "ocr_pages.json").read_text(encoding="utf-8"))["pages"])
        check("M-⑩ 空锁+真函数+屏障 → 确定性丢页（⑩ 可失败）", lost != list(range(1, 9)),
              "pages=%s（真锁版应为 1..8）" % lost)
        # 建议-2：屏障若被打破（某线程未到达），BrokenBarrierError 会被产品读段的
        # `except Exception: prev = []` 吞掉 → 探针静默退化成"无同步竞态"。故显式可见化。
        check("M-⑩ 屏障未被打破（8 线程均到达）", not bar.broken, "broken=%s" % bar.broken)

        # M-⑩b 正向对照：同一场景走**真实** _scan_page_local（真 _OCR_STORE_LOCK）不丢页
        w10b = td / "w10b"
        with mock.patch.object(rnd, "render_page",
                               lambda pdf, pno, out_dir, cfg, dpi_floor=None: {"page": pno}), \
                mock.patch.object(rnd, "append_registry", lambda p, e: None), \
                mock.patch.object(oc, "_make_engine", lambda cfg: object()), \
                mock.patch.object(oc, "ocr_page",
                                  lambda png, e, pno: {"page": pno,
                                                       "lines": [{"box": [0, 0, 1, 1], "text": "t"}]}):
            ths = [threading.Thread(target=orc._scan_page_local, args=(None, i, CFG, w10b))
                   for i in range(1, 9)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        got = sorted(int(p["page"]) for p in json.loads(
            (w10b / "ocr" / "ocr_pages.json").read_text(encoding="utf-8"))["pages"])
        check("M-⑩b 加锁版同场景 8/8", got == list(range(1, 9)), "pages=%s" % got)

        # M-⑨：空锁下本地引擎应并发同时在跑
        st, lk = {"active": 0, "max": 0}, threading.Lock()

        class _SlowEngine:
            def __call__(self, png):
                with lk:
                    st["active"] += 1
                    st["max"] = max(st["max"], st["active"])
                time.sleep(0.05)
                with lk:
                    st["active"] -= 1
                return ([], None)

        eng = _SlowEngine()
        with mock.patch.object(oc, "_ENGINE_LOCK", NoLock()):
            ths = [threading.Thread(target=oc.ocr_page, args=("p%d.png" % i, eng, i))
                   for i in range(1, 9)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        check("M-⑨ 空锁下确实并发（断言有鉴别力）", st["max"] > 1, "max_active=%d" % st["max"])

        # M-⑪：恢复消费时残留行盒会被喂入
        w11 = td / "w11"
        (w11 / "ocr").mkdir(parents=True, exist_ok=True)
        (w11 / "ocr" / "ocr_pages.json").write_text(
            json.dumps({"engine": "rapidocr_onnxruntime",
                        "pages": [{"page": 1, "lines": [{"box": [0, 0, 9, 9], "text": "stale"}]}]},
                       ensure_ascii=False), encoding="utf-8")
        cap = {}

        def _fake_ppm(pno, md, cfg, **kw):
            cap.update(kw)
            return {"page_number": pno}

        class _FC:
            def glm_parse_page(self, png, **kw):
                return {"raw_response": {"response": {"md_results": "md"}}}

        # A 面：修复前的两行实现（逐字重演），对同一份 w11 真实求值
        old_lines = orc._ocr_lines_for(1, w11)
        check("M-⑪ A面：修复前形态会喂入非空行盒", bool(old_lines) is True,
              "lines=%d（即旧码会传 ocr_available=True）" % len(old_lines))
        # 负对照：空 work 目录下行盒为空 —— 证明 A 面结论依赖真实文件、非 mock 自证
        check("M-⑪ 负对照：空目录行盒为空（A 面非恒真）",
              orc._ocr_lines_for(1, td / "w11b") == [], "empty work -> []")
        # B 面：现网 _scan_page_glm 对同一份 w11 实际传入 pipeline 的值（真实行为断言）
        with mock.patch.object(rnd, "render_page",
                               lambda pdf, pno, out_dir, cfg, dpi_floor=None: {"page": pno}), \
                mock.patch.object(rnd, "append_registry", lambda p, e: None), \
                mock.patch.object(pipeline, "process_page_md", _fake_ppm):
            orc._scan_page_glm(None, 1, CFG, _FC(), w11, "sha")
        check("M-⑪ B面：现网函数对同一输入传空",
              cap.get("ocr_available") is False and cap.get("ocr_lines") == [],
              "ocr_available=%s lines=%s" % (cap.get("ocr_available"), cap.get("ocr_lines")))

        # ---- M-⑫ 取消"拒绝记忆"：同通道应被反复询问（⑧ 可失败）
        class _NoMem:
            def __contains__(self, x):
                return False

            def add(self, x):
                pass

        asked12 = {"n": 0}

        def _no12(**kw):
            asked12["n"] += 1
            return False

        c12 = vc2.VisionClient(CFG, egress_allow=True, no_cache=True,
                               budget=vc2.BudgetGate(CFG, {vc2.GLM_CHANNEL: 0.0}),
                               budget_confirm=_no12, ledger_path="nul")
        c12._budget_refused = _NoMem()          # 模拟"拒绝不记忆"的旧实现
        for _ in range(3):
            try:
                c12.glm_parse_page(Path("p.png"), page=1, doc_sha1="d",
                                   render_reg={"dpi": 220, "pixel": [1, 1], "render_sha1": "x"},
                                   raw_inject={"md_results": "t",
                                               "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
            except vc2.VisionError:
                pass
        check("M-⑫ 取消拒绝记忆 → 3 次调用问 3 次（⑧ 可失败）", asked12["n"] == 3,
              "asked=%d" % asked12["n"])

        # ---- M-⑬ 取消互斥：并发应重复询问（⑨ 可失败）
        asked13 = {"n": 0}
        bb13 = threading.Barrier(6, timeout=20)      # a-2：屏障强制 6 线程都进入窗口

        def _yes13(**kw):
            asked13["n"] += 1
            try:
                bb13.wait()
            except Exception:
                pass
            return True

        c13 = vc2.VisionClient(CFG, egress_allow=True, no_cache=True,
                               budget=vc2.BudgetGate(CFG, {vc2.GLM_CHANNEL: 0.0}),
                               budget_confirm=_yes13, ledger_path="nul")
        c13._budget_lock = NoLock()             # 模拟"无互斥"的旧实现

        def _w13():
            try:
                c13.glm_parse_page(Path("p.png"), page=1, doc_sha1="d",
                                   render_reg={"dpi": 220, "pixel": [1, 1], "render_sha1": "x"},
                                   raw_inject={"md_results": "t",
                                               "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
            except Exception:
                pass

        ths = [threading.Thread(target=_w13) for _ in range(6)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        check("M-⑬ 取消互斥 → 6 线程问 6 次（⑨ 可失败）", asked13["n"] == 6,
              "asked=%d" % asked13["n"])
        check("M-⑬ 屏障未被打破", not bb13.broken, "broken=%s" % bb13.broken)

        # ---- M-⑭ 取消留痕锁 + 屏障强制交错：应确定性丢记录（⑩ 可失败）
        w14 = td / "w14"
        (w14 / "work").mkdir(parents=True, exist_ok=True)
        (w14 / "work" / "budget_choice.json").write_text("[]", encoding="utf-8")
        bar14 = threading.Barrier(8, timeout=20)
        real_read14 = Path.read_text

        def slow_read14(self, *a, **kw):
            txt = real_read14(self, *a, **kw)
            if self.name == "budget_choice.json":
                try:
                    bar14.wait()                # 8 个读者全读完才放行写回
                except Exception:
                    pass
            return txt

        with mock.patch.object(orc, "_BUDGET_CHOICE_LOCK", NoLock()), \
                mock.patch.object(Path, "read_text", slow_read14):
            ths = [threading.Thread(target=orc._write_budget_choice, args=(w14, {"seq": i}))
                   for i in range(8)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
        n14 = len(json.loads((w14 / "work" / "budget_choice.json").read_text(encoding="utf-8")))
        check("M-⑭ 取消留痕锁+屏障 → 丢记录（⑩ 可失败）", n14 < 8, "n=%d/8" % n14)
        check("M-⑭ 屏障未被打破", not bar14.broken, "broken=%s" % bar14.broken)

    print("RESULT pass=%d fail=%d" % (pass_, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
