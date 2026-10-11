#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_budget_confirm.py —— 预算超限确认闸单测（#4，2026-09-27；离线、零出域）
==================================================================
① 无 budget_confirm → 超限直接抛 budget_exceeded（旧行为不回归）
② confirm 返回 True → 放行；**同一通道第二次调用直通、不再询问**
③ confirm 返回 False → 抛 budget_exceeded
④ confirm 抛异常 → 视为不放行（异常不外泄）
⑤ config.budget.confirm_on_exceed=false → _make_budget_confirm 返回 None
⑥ 非 TTY：回调返回 False 且写 work/budget_choice.json（context=non-tty, chosen=degrade）
⑦ TTY：输入 1 → True（chosen=allow_exceed）；输入 2 → False（chosen=degrade）
用法：python tests/v4/test_budget_confirm.py
"""
import builtins
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[2]
V4 = SKILL / "assets" / "v4"
if str(V4) not in sys.path:
    sys.path.insert(0, str(V4))

import vision_client as vc      # noqa: E402
import orchestrator as orc      # noqa: E402

CFG = orc.load_config(str(SKILL))
GLM = vc.GLM_CHANNEL
REG = {"dpi": 220, "pixel": [100, 100], "render_sha1": "x"}
INJ = {"md_results": "t", "usage": {"prompt_tokens": 10, "completion_tokens": 10}}


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


def client(confirm=None, limit=0.0):
    return vc.VisionClient(CFG, egress_allow=True, no_cache=True,
                           budget=vc.BudgetGate(CFG, {GLM: limit}),
                           budget_confirm=confirm,
                           ledger_path="nul" if sys.platform == "win32" else "/dev/null")


def call(c):
    return c.glm_parse_page(Path("p.png"), page=1, doc_sha1="d", render_reg=REG, raw_inject=INJ)


def main():
    t = Tally()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ① 无回调：旧行为
    err = None
    try:
        call(client())
    except vc.VisionError as e:
        err = e
    t.check("①无回调→抛 budget_exceeded", err is not None and err.kind == "budget_exceeded",
            "kind=%s" % (err.kind if err else None))

    # ② 确认放行 + 第二次直通（不再询问）
    asked = {"n": 0}

    def yes(**kw):
        asked["n"] += 1
        return True

    c2 = client(yes)
    ok1 = ok2 = False
    try:
        r1 = call(c2)
        ok1 = r1.get("md") == "t" or r1.get("cache_hit") is False
    except vc.VisionError:
        ok1 = False
    try:
        call(c2)
        ok2 = True
    except vc.VisionError as e:
        ok2 = False
    t.check("②确认放行后调用成功", ok1, "ok1=%s" % ok1)
    t.check("②同通道第二次直通（不再询问）", ok2 and asked["n"] == 1,
            "ok2=%s asked=%d" % (ok2, asked["n"]))

    # ③ 拒绝 → 抛错
    err = None
    try:
        call(client(lambda **kw: False))
    except vc.VisionError as e:
        err = e
    t.check("③拒绝→抛 budget_exceeded", err is not None and err.kind == "budget_exceeded",
            "kind=%s" % (err.kind if err else None))

    # ④ 回调抛异常 → 不外泄、按不放行
    def boom(**kw):
        raise RuntimeError("confirm-boom")

    err = None
    try:
        call(client(boom))
    except vc.VisionError as e:
        err = e
    t.check("④回调异常不外泄→budget_exceeded", err is not None and err.kind == "budget_exceeded",
            "kind=%s" % (err.kind if err else None))

    # ⑤ 开关关闭 → 无回调
    cfg_off = json.loads(json.dumps(CFG))
    cfg_off.setdefault("budget", {})["confirm_on_exceed"] = False
    with tempfile.TemporaryDirectory() as td:
        t.check("⑤confirm_on_exceed=false→None", orc._make_budget_confirm(cfg_off, Path(td)) is None,
                "None")

        # ⑥ 非 TTY
        with mock.patch.object(sys.stdin, "isatty", lambda: False):
            cb = orc._make_budget_confirm(CFG, Path(td))
            got = cb(channel=GLM, spent=1.0, limit=1.0, peak=False)
            f = Path(td) / "work" / "budget_choice.json"
            rec = json.loads(f.read_text(encoding="utf-8"))[-1] if f.exists() else {}
        t.check("⑥非 TTY→False 且留痕", got is False and rec.get("chosen") == "degrade"
                and rec.get("context") == "non-tty", "got=%s rec=%s" % (got, rec.get("chosen")))

        # ⑦ TTY：1 / 2
        with mock.patch.object(sys.stdin, "isatty", lambda: True), \
                mock.patch.object(builtins, "input", lambda *a: "1"):
            got1 = orc._make_budget_confirm(CFG, Path(td))(channel=GLM, spent=1.0, limit=1.0, peak=False)
        with mock.patch.object(sys.stdin, "isatty", lambda: True), \
                mock.patch.object(builtins, "input", lambda *a: "2"):
            got2 = orc._make_budget_confirm(CFG, Path(td))(channel=GLM, spent=1.0, limit=1.0, peak=False)
        recs = json.loads((Path(td) / "work" / "budget_choice.json").read_text(encoding="utf-8"))
        t.check("⑦TTY 选 1→放行并留痕", got1 is True and recs[-2].get("chosen") == "allow_exceed",
                "got1=%s" % got1)
        t.check("⑦TTY 选 2→降级并留痕", got2 is False and recs[-1].get("chosen") == "degrade",
                "got2=%s" % got2)

        # ⑧ S-1：拒绝也要记忆 —— 同通道再调用不再询问（契约"停止该通道"）
        asked_r = {"n": 0}

        def no(**kw):
            asked_r["n"] += 1
            return False

        c8 = client(no)
        for _ in range(3):
            try:
                call(c8)
            except vc.VisionError:
                pass
        t.check("⑧拒绝后不再重复询问（3 次调用只问 1 次）", asked_r["n"] == 1,
                "asked=%d" % asked_r["n"])

        # ⑨ S-1：并发只问一次（互斥 + 状态机）
        asked_y = {"n": 0}
        import threading as _th

        def slow_yes(**kw):
            asked_y["n"] += 1
            time.sleep(0.05)
            return True

        c9 = client(slow_yes)
        errs9 = []

        def worker9():
            try:
                call(c9)
            except Exception as e:      # noqa: BLE001
                errs9.append(repr(e))

        ths = [_th.Thread(target=worker9) for _ in range(6)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        t.check("⑨6 线程并发只问一次", asked_y["n"] == 1 and not errs9,
                "asked=%d errs=%d" % (asked_y["n"], len(errs9)))

        # ⑩ S-1：留痕并发不丢（8 线程 × 5 条 = 40）
        w10 = Path(td) / "w10"
        for i in range(40):                     # 顺序阶段（标记 1000+，不参与无丢无重判定）
            orc._write_budget_choice(w10, {"ts": 0, "seq": 1000 + i})

        def w_worker(k):                        # 并发阶段：8×5=40 条，seq 0..39
            for j in range(5):
                orc._write_budget_choice(w10, {"ts": 0, "seq": k * 5 + j})

        ths = [_th.Thread(target=w_worker, args=(k,)) for k in range(8)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        recs10 = json.loads((w10 / "work" / "budget_choice.json").read_text(encoding="utf-8"))
        seqs = [r.get("seq") for r in recs10]
        cc = sorted(s for s in seqs if s is not None and s < 1000)
        t.check("⑩留痕并发不丢（并发 40 条无丢无重）",
                len(recs10) == 80 and cc == list(range(40)),
                "n=%d concurrent=%d uniq=%d" % (len(recs10), len(cc), len(set(cc))))

        # ⑪ S-1 回归：提示串在 **cp936 严格编码** 的 stdout 下不得抛（且仍留痕）
        class _Cp936Out:
            encoding = "gbk"

            def __init__(self):
                self.buf = []

            def write(self, s):
                s.encode("gbk")             # 严格编码：¥(U+00A5) 在此抛 UnicodeEncodeError
                self.buf.append(s)

            def flush(self):
                pass

            def isatty(self):
                return False

        fake = _Cp936Out()
        with mock.patch.object(sys, "stdout", fake), \
                mock.patch.object(sys.stdin, "isatty", lambda: True), \
                mock.patch.object(builtins, "input", lambda *a: "1"):
            got11 = orc._make_budget_confirm(CFG, Path(td))(
                channel=GLM, spent=1.0, limit=1.0, peak=False)
        joined = "".join(fake.buf)
        f11 = Path(td) / "work" / "budget_choice.json"
        rec11 = json.loads(f11.read_text(encoding="utf-8"))[-1] if f11.exists() else {}
        t.check("⑪cp936 严格编码下提示不抛且留痕",
                got11 is True and rec11.get("chosen") == "allow_exceed" and "预算超限" in joined,
                "got=%s chosen=%s" % (got11, rec11.get("chosen")))

        # ⑫ 建议-3：显式触发 `_safe_print` 的 **fallback** 分支（⑪ 只证明"¥ 已换掉"）

        class _StrictGbk:
            encoding = "gbk"

            def __init__(self):
                self.buf = []

            def write(self, s):
                s.encode("gbk")         # 严格编码
                self.buf.append(s)

            def flush(self):
                pass

            def isatty(self):
                return False

        f12 = _StrictGbk()
        raised12 = None
        with mock.patch.object(sys, "stdout", f12):
            try:
                orc._safe_print("prefix \u00a5 suffix")     # ¥ 在 gbk 下不可编码 → 必走 fallback
            except Exception as e:                           # noqa: BLE001
                raised12 = e
        t.check("⑫fallback 分支真生效（非 gbk 字符不抛且已降级输出）",
                raised12 is None and len(f12.buf) == 2 and "?" in "".join(f12.buf),
                "raised=%s writes=%d" % (raised12, len(f12.buf)))

    print("RESULT pass=%d fail=%d" % (t.pass_, t.fail))
    if t.failures:
        print("FAILED: %s" % ", ".join(t.failures))
    return 0 if t.fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
