# -*- coding: utf-8 -*-
"""test_scripts.py —— adversarial-review 五脚本单元测试（设计稿 11.1）。

运行: python3 tests/test_scripts.py -v   （任意 Python 3.9+，零第三方依赖）
覆盖:
  1) collect_snapshot: 合法落盘 / 缺字段拒收(2) / 超10KB拒收(3) / ns 双源告警
  2) sediment_check: pending/间隔/峰谷 信号分支 + remind 防抖
  3) ledger: 过滤与编号 / 状态机 / 非法转移(2) / 重开计数 / reject 需证据
  4) diff_scope: 文件对范围 / 引用扩散 / 无变更空范围 / git 模式(有 git 才跑) / 台账并集
  5) sediment_run: S0→S6 全链路 / await_edits 分界 / resume 幂等 / 断点续跑
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

_BJ = timezone(timedelta(hours=8))


def run(script, *args, stdin=None, env_extra=None):
    """调用技能脚本，返回 (rc, stdout_text, stderr_text)。"""
    p = subprocess.run([PY, str(ROOT / "scripts" / script), *args],
                       input=None if stdin is None else stdin.encode("utf-8"),
                       capture_output=True, env={**ENV, **(env_extra or {})})
    return (p.returncode,
            p.stdout.decode("utf-8", "replace").strip(),
            p.stderr.decode("utf-8", "replace").strip())


def outj(out):
    return json.loads(out)


def mk_snap(i, ns="document", extra_issue=True):
    """构造一条最小合法快照（供落盘/计数用）。"""
    return {
        "id": "snap-20260905-2030%02d-s%03d" % (i % 60, i),
        "ts": "2026-09-05T20:30:%02d+08:00" % (i % 60),
        "ns": ns,
        "env": {"platform": "dsh", "host_note": "test", "model": "test-model",
                "pricing_version": "2026-09-05"},
        "task": {"summary": "单测快照 %d" % i, "object_type": "文档", "size_chars": 100},
        "mode": "closed_loop",
        "rounds": 2,
        "issues": ([{"id": "AR-T-001", "severity": "major", "type": "一致性",
                     "anchor": "第2.1节", "basis": "自检依据 [D-001]", "status": "已关闭"}]
                   if extra_issue else []),
        "tokens": [{"round": 1, "input": 100, "output": 50, "cache_hit": 0},
                   {"round": 2, "input": 20, "output": 10, "cache_hit": 0}],
        "outcome": "converged",
        "fix_summary": "已修复",
    }


class TestCollectSnapshot(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = self._td.name

    def _pend_dir(self, ns="document"):
        d = Path(self.state) / "snapshots" / "pending" / ns
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_ok_writes(self):
        rc, out, _ = run("collect_snapshot.py", "--ns", "document",
                         "--state-dir", self.state,
                         stdin=json.dumps(mk_snap(1), ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        written = Path(outj(out)["written"])
        self.assertTrue(written.exists())
        self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["id"],
                         "snap-20260905-203001-s001")

    def test_missing_field_rejected(self):
        snap = mk_snap(2)
        del snap["rounds"]
        rc, out, _ = run("collect_snapshot.py", "--ns", "document",
                         "--state-dir", self.state, stdin=json.dumps(snap))
        self.assertEqual(rc, 2)
        self.assertIn("schema", outj(out)["error"])

    def test_oversize_rejected(self):
        snap = mk_snap(3)
        snap["task"]["summary"] = "X" * 12000
        rc, out, _ = run("collect_snapshot.py", "--ns", "document",
                         "--state-dir", self.state, stdin=json.dumps(snap))
        self.assertEqual(rc, 3)
        self.assertIn("10KB", outj(out)["error"])

    def test_ns_mismatch_warns_but_writes(self):
        snap = mk_snap(4, ns="code")
        rc, out, err = run("collect_snapshot.py", "--ns", "document",
                           "--state-dir", self.state, stdin=json.dumps(snap))
        self.assertEqual(rc, 0, out)
        self.assertIn("不一致", err)
        self.assertTrue((self._pend_dir("document") / "snap-20260905-203004-s004.json").exists())


class TestSedimentCheck(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = self._td.name
        Path(self.state).mkdir(parents=True, exist_ok=True)

    def _pending(self, ns, n):
        d = Path(self.state) / "snapshots" / "pending" / ns
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / ("f%d.json" % i)).write_text(json.dumps({"id": "f%d" % i}), encoding="utf-8")

    def _state(self, last=None, remind=None):
        Path(self.state, "state.json").write_text(json.dumps({
            "last_sediment_at": last or {},
            "budget": {"single_run_max_cny": 0.5, "monthly_left_cny": 2.0,
                       "single_input_tok_max": 120000, "single_output_tok_max": 20000},
            "last_remind_at": remind,
        }, ensure_ascii=False), encoding="utf-8")

    def _check(self, now):
        rc, out, _ = run("sediment_check.py", "--state-dir", self.state, "--now", now)
        self.assertEqual(rc, 0, out)
        return outj(out)

    def test_none_below_thresholds(self):
        self._pending("general", 6)
        self._state(last={"general": "2026-09-05T00:00:00+08:00"})
        res = self._check("2026-09-07T20:00:00+08:00")  # 周一 20:00 峰谷外, 44h
        self.assertEqual(res["signal"], "none")

    def test_peak_suppresses_sediment(self):
        self._pending("general", 7)
        self._state(last={"general": "2026-09-05T10:00:00+08:00"})  # 48h 整
        res = self._check("2026-09-07T10:30:00+08:00")  # 周一高峰
        self.assertEqual(res["signal"], "none")

    def test_sediment_offpeak_after_48h(self):
        self._pending("general", 7)
        self._state(last={"general": "2026-09-05T10:00:00+08:00"})
        res = self._check("2026-09-07T20:00:00+08:00")  # 周一峰谷外 58h
        self.assertEqual(res["signal"], "sediment")
        self.assertEqual(res["signals"][0]["ns"], "general")

    def test_remind_at_72h_and_debounce(self):
        self._pending("regulation", 10)
        self._state(last={"regulation": "2026-09-04T10:00:00+08:00"})  # 73h
        res = self._check("2026-09-07T11:00:00+08:00")  # 周一高峰也不影响 remind
        self.assertEqual(res["signal"], "remind")
        # 24h 防抖：立即重跑不再 remind
        res2 = self._check("2026-09-07T11:05:00+08:00")
        self.assertEqual(res2["signal"], "none")

    def test_multi_ns_offpeak_all_sediment(self):
        self._pending("document", 7)
        self._pending("code", 10)
        self._state(last={"document": "2026-09-04T10:00:00+08:00",   # 50h ≥48
                          "code": "2026-09-02T10:00:00+08:00"})     # 98h ≥72
        res = self._check("2026-09-06T12:00:00+08:00")  # 周日整天峰谷外
        self.assertEqual(res["signal"], "sediment")
        self.assertEqual({s["signal"] for s in res["signals"]}, {"sediment"})
        self.assertEqual({s["ns"] for s in res["signals"]}, {"document", "code"})
        self.assertIn("budget", res)

    def test_peak_remind_even_with_pending7(self):
        # 高峰：document 7 条被峰谷抑制（无 sediment）；code 10 条超期 → remind
        self._pending("document", 7)
        self._pending("code", 10)
        self._state(last={"document": "2026-09-04T10:00:00+08:00",
                          "code": "2026-09-02T10:00:00+08:00"})
        res = self._check("2026-09-07T10:30:00+08:00")  # 周一高峰
        self.assertEqual(res["signal"], "remind")
        self.assertEqual([s["ns"] for s in res["signals"]], ["code"])


class TestLedger(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = self._td.name
        self.sid = "session-u1"
        self._base = ["--session", self.sid, "--state-dir", self.state]

    def _issues(self):
        return {"issues": [
            {"anchor": "第2.1节", "basis": "数据无来源", "confidence": "high",
             "severity": "blocking", "type": "事实性"},
            {"anchor": "第3.2节", "basis": "编号不一致", "confidence": "medium",
             "severity": "major", "type": "一致性"},
            {"anchor": "无依据段落", "confidence": "high", "severity": "minor"},   # 缺 basis
            {"anchor": "a", "basis": "b", "confidence": "sure?", "severity": "major"},  # confidence 非法
        ]}

    def _new(self):
        rc, out, _ = run("ledger.py", *self._base, "new",
                         stdin=json.dumps(self._issues(), ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        return outj(out)

    def test_new_filters_and_ids(self):
        res = self._new()
        self.assertEqual(res["created"], 2)
        self.assertEqual(res["dropped"], 2)
        self.assertTrue(res["ids"][0].startswith("AR-"))
        rc, out, _ = run("ledger.py", *self._base, "new",
                         stdin=json.dumps(self._issues(), ensure_ascii=False))
        self.assertEqual(rc, 2)  # 重复建台账拒绝

    def test_state_machine_and_reject_evidence(self):
        res = self._new()
        iid = res["ids"][0]
        def tr(ev, extra=()):
            return run("ledger.py", *self._base, "transition", "--id", iid,
                       "--event", ev, *extra)
        for ev, want in [("confirm", "已确认"), ("fix_start", "修复中"),
                         ("fix_submit", "待验证"), ("verify_pass", "已关闭")]:
            rc, out, _ = tr(ev)
            self.assertEqual(rc, 0, out)
            self.assertEqual(outj(out)["to"], want)
        # 已关闭 → 再 confirm 非法
        rc, out, _ = tr("confirm")
        self.assertEqual(rc, 2)
        self.assertIn("非法转移", outj(out)["error"])
        # reject 需证据
        iid2 = res["ids"][1]
        rc, out, _ = run("ledger.py", *self._base, "transition", "--id", iid2,
                         "--event", "reject")
        self.assertEqual(rc, 2)
        rc, out, _ = run("ledger.py", *self._base, "transition", "--id", iid2,
                         "--event", "reject", "--evidence", "反驳：条款已由新版替代")
        self.assertEqual(rc, 0, out)
        self.assertEqual(outj(out)["to"], "已驳回")

    def test_reopen_count(self):
        res = self._new()
        iid = res["ids"][1]  # major
        steps = ["confirm", "fix_start", "fix_submit", "verify_fail"]
        for ev in steps:
            rc, out, _ = run("ledger.py", *self._base, "transition", "--id", iid,
                             "--event", ev)
            self.assertEqual(rc, 0, out)
        rc, out, _ = run("ledger.py", *self._base, "export")
        self.assertEqual(rc, 0, out)
        ledger = outj(out)
        issue = next(i for i in ledger["issues"] if i["id"] == iid)
        self.assertEqual(issue["status"], "已确认")
        self.assertEqual(issue["reopen_count"], 1)
        # 已关闭 → regression_fail 重开
        for ev in ["fix_start", "fix_submit", "verify_pass", "regression_fail"]:
            rc, out, _ = run("ledger.py", *self._base, "transition", "--id", iid,
                             "--event", ev)
            self.assertEqual(rc, 0, out)
        rc, out, _ = run("ledger.py", *self._base, "export")
        issue = next(i for i in outj(out)["issues"] if i["id"] == iid)
        self.assertEqual(issue["reopen_count"], 2)


class TestDiffScope(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name)

    def _write(self, name, lines):
        p = self.dir / name
        p.write_text("\n".join(lines), encoding="utf-8")
        return str(p)

    def test_pair_ranges_and_diffusion(self):
        old = self._write("doc-old.md", [
            "# 测试文档",
            "## 3 主体",
            "### 第3.2节 旧实现",
            "本段被修改 123",
            "后文依赖 第3.2节 的定义。",
            "## 4 收尾",
        ])
        new = self._write("doc-new.md", [
            "# 测试文档",
            "## 3 主体",
            "### 第3.3节 新实现",
            "本段被修改 456",
            "后文依赖 第3.2节 的定义。",
            "## 4 收尾",
        ])
        rc, out, _ = run("diff_scope.py", "--old", old, "--new", new,
                         "--context", "0")
        self.assertEqual(rc, 0, out)
        entry = outj(out)["scope"][0]
        self.assertTrue(any(3 <= r["start"] <= 4 for r in entry["ranges"]))   # 变更区
        reasons = "；".join(r["reason"] for r in entry["ranges"])
        self.assertIn("引用扩散", reasons)  # 第3.2节 在 L5 的引用被捕获

    def test_no_change_empty_scope(self):
        p = self._write("same.md", ["一行", "两行"])
        rc, out, _ = run("diff_scope.py", "--old", p, "--new", p, "--context", "0")
        self.assertEqual(rc, 0, out)
        self.assertEqual(outj(out)["scope"][0]["ranges"], [])

    def test_ledger_union(self):
        sid = "sess-diff"
        rc, out, _ = run("ledger.py", "--session", sid, "--state-dir", self.dir, "new",
                         stdin=json.dumps({"issues": [
                             {"anchor": "第9节", "basis": "x", "confidence": "high",
                              "severity": "major"}]}, ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        rc, out, _ = run("ledger.py", "--session", sid, "--state-dir", self.dir, "export")
        iid = outj(out)["issues"][0]["id"]
        rc, out, _ = run("ledger.py", "--session", sid, "--state-dir", self.dir,
                         "transition", "--id", iid, "--event", "confirm")
        self.assertEqual(rc, 0, out)
        p = self._write("a.md", ["x"])
        rc, out, _ = run("diff_scope.py", "--old", p, "--new", p, "--context", "0",
                         "--session", sid, "--state-dir", self.dir)
        self.assertEqual(rc, 0, out)
        items = outj(out)["scope"]
        self.assertTrue(any(i.get("reason", "").startswith("台账未关闭") for i in items))

    def test_git_mode(self):
        if shutil.which("git") is None:
            self.skipTest("git 不可用")
        repo = self.dir / "repo"
        repo.mkdir()
        (repo / "a.txt").write_text("第1行\n第2行\n第3行\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        (repo / "a.txt").write_text("第1行\n第2行改了\n第3行\n", encoding="utf-8")
        # git 模式以仓库目录为 cwd
        p = subprocess.run([PY, str(ROOT / "scripts" / "diff_scope.py"),
                            "--git", "--context", "0"],
                           capture_output=True, cwd=str(repo),
                           env={**ENV, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))
        scope = outj(p.stdout.decode("utf-8", "replace").strip())["scope"]
        self.assertTrue(any(r["start"] == 2 for r in scope[0]["ranges"]))


GUIDE_SRC = """# 前置导引单

## 通用条款
- [G-001] 数据必须标注来源。

## 命名空间条款
### 文档类
- [D-001] 图表数据与正文表述一致。
- [D-002] 标题层级、编号连续。
"""

PRICING_SRC = """# 价格
```json
{"updated_at": "2026-09-05", "currency": "CNY/1M tokens", "timezone": "Asia/Shanghai", "models": []}
```
"""


def make_scratch_skill(tmp):
    """构造隔离的技能根（sediment_run --skill-root 用），避免触碰真实 references/。"""
    root = Path(tmp) / "skill"
    (root / "references" / "namespaces").mkdir(parents=True)
    (root / "references" / "pregen-guide.md").write_text(GUIDE_SRC, encoding="utf-8")
    (root / "references" / "pricing-models.md").write_text(PRICING_SRC, encoding="utf-8")
    (root / "references" / "namespaces" / "document.md").write_text("# 文档类清单\n", encoding="utf-8")
    return str(root)


class TestSedimentRun(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.state = str(self.tmp / "state")
        self.skill = make_scratch_skill(self.tmp)
        self.now = "2026-09-05T20:00:00+08:00"

    def _pending(self, n):
        d = Path(self.state) / "snapshots" / "pending" / "document"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            snap = mk_snap(i, ns="document")
            snap["issues"] = [{"id": "AR-I-%d" % i, "severity": "major",
                               "type": "一致性", "anchor": "第%d节" % i,
                               "basis": "[D-001]", "status": "已关闭",
                               "false_positive": False, "reopen_count": 0}]
            (d / ("%s.json" % snap["id"])).write_text(
                json.dumps(snap, ensure_ascii=False), encoding="utf-8")

    def _sr(self, *extra):
        args = ["--ns", "document", "--state-dir", self.state,
                "--skill-root", self.skill, "--now", self.now]
        return run("sediment_run.py", *(list(extra) + args))

    def test_await_edits_then_resume_full_flow(self):
        self._pending(3)
        # 第一次：无裁决 → await_edits（S0/S1 完成，出候选）
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        r1 = outj(out)
        self.assertEqual(r1["status"], "await_edits")
        self.assertIn("S0", r1["phases_done"])
        self.assertIn("S1", r1["phases_done"])
        cand = Path(self.state) / "sediment" / "iter-1-candidates.json"
        self.assertTrue(cand.exists())
        # 2026-09-10 规格变更（M3）：new_threshold 3→5，且新增候选须有实际返工证据。
        # 本用例仅 3 条同类 issue 且无 ledger → 不再产出新增候选（旧断言 count>=3 已废）。
        self.assertFalse(any(c["kind"] == "new-clause-candidate"
                             for c in outj(cand.read_text(encoding="utf-8"))["candidates"]))
        it = r1["iter"]
        # 第二次：resume + 裁决文件 → S2→S6 全跑通
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({
            "add": [{"ns": "document", "line": "- [D-003] 交叉引用必须指向现存章节（测试条款）。"}],
            "demote": ["D-001"],
        }, ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--resume", it, "--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        r2 = outj(out)
        self.assertEqual(r2["status"], "done")
        self.assertEqual(set(r2["phases_done"]), {"S0", "S1", "S2", "S3", "S4", "S5", "S6"})
        self.assertEqual(len(r2["moved_to_settled"]), 3)
        # 导引单已回写：D-003 新增且只出现一次；D-001 降权后排到 D-002 之后
        guide = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertEqual(guide.count("- [D-003]"), 1)
        self.assertLess(guide.index("- [D-002]"), guide.index("- [D-001]"))
        # changelog 与 state 更新
        changelog = (Path(self.state) / "changelog.md").read_text(encoding="utf-8")
        self.assertIn("## iter-1 ", changelog)
        state = json.loads((Path(self.state) / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["iter_seq"], 1)
        self.assertIn("document", state["last_sediment_at"])
        # pending 已清空、settled 已有 3 条
        self.assertEqual(len(list((Path(self.state) / "snapshots" / "pending" / "document").glob("*.json"))), 0)
        self.assertEqual(len(list((Path(self.state) / "snapshots" / "settled" / "document").glob("*.json"))), 3)

        # 第三次：同 iter resume 重跑 → 幂等，无重复条款/日志
        rc, out, _ = self._sr("--resume", it)
        self.assertEqual(rc, 0, out)
        self.assertEqual(outj(out)["status"], "done")
        guide2 = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertEqual(guide2.count("- [D-003]"), 1)
        changelog2 = (Path(self.state) / "changelog.md").read_text(encoding="utf-8")
        self.assertEqual(changelog2.count("## iter-1 "), 1)

    def test_breakpoint_resume_from_until(self):
        self._pending(1)
        rc, out, _ = self._sr("--until", "S1")
        self.assertEqual(rc, 0, out)
        self.assertEqual(outj(out)["status"], "await_edits")
        edits = self.tmp / "edits2.json"
        edits.write_text(json.dumps({
            "add": [{"ns": "document", "line": "- [D-004] 断点续跑新增条款。"}],
        }, ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--resume", "iter-1", "--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        guide = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertIn("- [D-004]", guide)
        self.assertNotEqual(outj(out)["status"], "await_edits")


class TestRegressionFixes(unittest.TestCase):
    """2026-09-05 对抗性审查修复项的回归测试（编号对应审查意见单 F1~F12）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.state = str(self.tmp / "state")

    def test_eof_and_full_deletion_flagged(self):
        """F1: 文件尾删除与整文件清空不得误报 no-change。"""
        old = self.tmp / "o.md"; new = self.tmp / "n.md"
        old.write_text("a\nb\nc\nd\n", encoding="utf-8")
        new.write_text("a\nb\n", encoding="utf-8")
        rc, out, _ = run("diff_scope.py", "--old", str(old), "--new", str(new), "--context", "0")
        self.assertEqual(rc, 0, out)
        entry = outj(out)["scope"][0]
        self.assertTrue(any("deletion@EOF" in r["reason"] for r in entry["ranges"]), out)
        new.write_text("", encoding="utf-8")  # 整文件清空
        rc, out, _ = run("diff_scope.py", "--old", str(old), "--new", str(new), "--context", "0")
        self.assertEqual(rc, 0, out)
        entry = outj(out)["scope"][0]
        self.assertTrue(any("deletion@EOF" in r["reason"] for r in entry["ranges"]), out)

    def test_git_deleted_file_listed(self):
        """F11: git 模式必须显式列出被删文件（删除会使引用处失效，禁止静默丢弃）。"""
        if shutil.which("git") is None:
            self.skipTest("git 不可用")
        repo = self.tmp / "repo"
        repo.mkdir()
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        (repo / "b.txt").unlink()
        p = subprocess.run([PY, str(ROOT / "scripts" / "diff_scope.py"), "--git", "--context", "0"],
                           capture_output=True, cwd=str(repo), env={**ENV, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))
        scope = outj(p.stdout.decode("utf-8", "replace").strip())["scope"]
        self.assertTrue(any(e["file"].endswith("b.txt") and "file-deleted" in e["reason"]
                            for e in scope), p.stdout.decode("utf-8", "replace"))

    def test_snapshot_ns_rewrite_and_defaults(self):
        """F7: ns 双源时落盘 JSON 以 --ns 为准；缺省 false_positive/reopen_count 补齐。"""
        snap = mk_snap(21, ns="code")
        rc, out, err = run("collect_snapshot.py", "--ns", "document",
                           "--state-dir", self.state, stdin=json.dumps(snap, ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        self.assertIn("不一致", err)
        stored = json.loads(Path(outj(out)["written"]).read_text(encoding="utf-8"))
        self.assertEqual(stored["ns"], "document")
        self.assertIs(stored["issues"][0]["false_positive"], False)
        self.assertEqual(stored["issues"][0]["reopen_count"], 0)

    def test_never_settled_hours_null(self):
        """F8: 从未沉淀时 hours_since_last 输出 null，不暴露 1e9 内部哨兵。"""
        pend = Path(self.state) / "snapshots" / "pending" / "general"
        pend.mkdir(parents=True, exist_ok=True)
        for i in range(7):
            (pend / ("g%d.json" % i)).write_text("{}", encoding="utf-8")
        rc, out, _ = run("sediment_check.py", "--state-dir", self.state,
                         "--now", "2026-09-06T20:00:00+08:00")
        self.assertEqual(rc, 0, out)
        res = outj(out)
        self.assertEqual(res["signal"], "sediment")
        self.assertIsNone(res["signals"][0]["hours_since_last"])

    def test_in_peak_locale_independent(self):
        """F5: 峰谷星期判定用 weekday()，与进程 LC_TIME 无关。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("sediment_check_mod",
                                                      ROOT / "scripts" / "sediment_check.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pricing = {"models": [{"peak": {"days": "weekday",
                                        "windows": [["09:00", "12:00"], ["14:00", "18:00"]]}}]}
        self.assertFalse(mod.in_peak(datetime(2026, 9, 6, 10, 0, tzinfo=_BJ), pricing))  # 周日
        self.assertTrue(mod.in_peak(datetime(2026, 9, 7, 10, 0, tzinfo=_BJ), pricing))   # 周一高峰
        self.assertFalse(mod.in_peak(datetime(2026, 9, 7, 13, 0, tzinfo=_BJ), pricing))  # 周一午间空档

    def test_demote_candidate_for_zero_hit_clause(self):
        """F2/M2（2026-09-10 规格变更）: 零命中**只作线索**（demote-hint）；
        判失效须达"零证据窗口"阈值，故此处不得产出 demote-candidate。"""
        skill = make_scratch_skill(self.tmp)
        pend = Path(self.state) / "snapshots" / "pending" / "document"
        pend.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            snap = mk_snap(i, ns="document")
            snap["issues"] = [{"id": "AR-Z-%d" % i, "severity": "major", "type": "一致性",
                               "anchor": "a", "basis": "[D-001]", "status": "已关闭"}]
            (pend / ("%s.json" % snap["id"])).write_text(json.dumps(snap, ensure_ascii=False),
                                                         encoding="utf-8")
        rc, out, _ = run("sediment_run.py", "--ns", "document", "--state-dir", self.state,
                         "--skill-root", skill, "--now", "2026-09-05T20:00:00+08:00")
        self.assertEqual(rc, 0, out)
        kinds = {(c["kind"], c.get("clause")) for c in outj(out)["candidates"]}
        self.assertIn(("demote-hint", "D-002"), kinds)            # 零命中但未达阈值 → 仅线索
        self.assertNotIn(("demote-candidate", "D-002"), kinds)    # 不得仅凭零命中判失效
        self.assertNotIn(("demote-hint", "D-001"), kinds)         # D-001 有命中 → 不提名

    def test_clean_window_no_demote_spam(self):
        """F2 补充: 整窗零 issue（无缺陷信号）时不得误产全量降权候选。"""
        skill = make_scratch_skill(self.tmp)
        pend = Path(self.state) / "snapshots" / "pending" / "document"
        pend.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            snap = mk_snap(i, ns="document", extra_issue=False)   # issues=[]
            (pend / ("%s.json" % snap["id"])).write_text(json.dumps(snap, ensure_ascii=False),
                                                         encoding="utf-8")
        rc, out, _ = run("sediment_run.py", "--ns", "document", "--state-dir", self.state,
                         "--skill-root", skill, "--now", "2026-09-05T20:00:00+08:00")
        self.assertEqual(rc, 0, out)
        cands = outj(out).get("candidates") or []
        self.assertFalse(any(c["kind"] == "demote-candidate" for c in cands),
                         json.dumps(cands, ensure_ascii=False))

    def test_iter_seq_not_regressed_by_old_resume(self):
        """F3: resume 旧迭代补跑 S6 不得回退 state.iter_seq。"""
        skill = make_scratch_skill(self.tmp)
        sed = Path(self.state) / "sediment"
        sed.mkdir(parents=True, exist_ok=True)
        (sed / "iter-1.checkpoint").write_text(
            json.dumps({"phases_done": ["S0", "S1", "S2", "S3", "S4", "S5"]}), encoding="utf-8")
        Path(self.state, "state.json").write_text(json.dumps({
            "last_sediment_at": {}, "iter_seq": 5,
            "budget": {"single_run_max_cny": 0.5, "monthly_left_cny": 2.0,
                       "single_input_tok_max": 120000, "single_output_tok_max": 20000},
        }, ensure_ascii=False), encoding="utf-8")
        pend = Path(self.state) / "snapshots" / "pending" / "document"
        pend.mkdir(parents=True, exist_ok=True)
        (pend / "x.json").write_text(json.dumps(mk_snap(31), ensure_ascii=False), encoding="utf-8")
        rc, out, _ = run("sediment_run.py", "--ns", "document", "--state-dir", self.state,
                         "--skill-root", skill, "--now", "2026-09-05T20:00:00+08:00",
                         "--resume", "iter-1")
        self.assertEqual(rc, 0, out)
        st = json.loads(Path(self.state, "state.json").read_text(encoding="utf-8"))
        self.assertEqual(st["iter_seq"], 5)

    def test_corrupt_state_fails_loud(self):
        """F10: 损坏的 state.json 必须显式失败（退出码 1），禁止静默回退默认。"""
        skill = make_scratch_skill(self.tmp)
        Path(self.state).mkdir(parents=True, exist_ok=True)
        Path(self.state, "state.json").write_text("{not-json", encoding="utf-8")
        rc, out, _ = run("sediment_run.py", "--ns", "document", "--state-dir", self.state,
                         "--skill-root", skill, "--now", "2026-09-05T20:00:00+08:00")
        self.assertEqual(rc, 1, out)
        self.assertIn("state.json", out)

    def test_demote_keeps_blank_separator(self):
        """F12: demote 移动条款后保留块尾空行，不与下一标题粘连。"""
        skill = make_scratch_skill(self.tmp)
        (Path(skill) / "references" / "pregen-guide.md").write_text(
            "# G\n\n## 通用条款\n- [G-001] a\n\n## 命名空间条款\n### 文档类\n"
            "- [D-001] x\n- [D-002] y\n\n### 代码类\n- [C-001] z\n", encoding="utf-8")
        pend = Path(self.state) / "snapshots" / "pending" / "document"
        pend.mkdir(parents=True, exist_ok=True)
        (pend / "x.json").write_text(json.dumps(mk_snap(32), ensure_ascii=False), encoding="utf-8")
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({"demote": ["D-001"]}, ensure_ascii=False), encoding="utf-8")
        rc, out, _ = run("sediment_run.py", "--ns", "document", "--state-dir", self.state,
                         "--skill-root", skill, "--now", "2026-09-05T20:00:00+08:00",
                         "--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        guide = (Path(skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertIn("- [D-002] y\n- [D-001] x\n\n### 代码类", guide)


GUIDE_FULL = """# 前置导引单（生成前必读）

## 审查预告（固定条款，不淘汰）
- 本成果交付后将接受对抗性审查：问题按阻断/严重/轻微/建议分级，每条意见须附位置与依据，无证据不成立。

## 通用条款（按权重排序，沉淀机制维护）
- [G-001] 数据必须标注来源（文件名＋条款号）。
- [G-002] 交叉引用必须指向真实存在的位置。
- [G-003] 数值必须带单位。

## 命名空间条款
### 文档类
- [D-001] 图表数据与正文表述一致。
- [D-002] 标题层级、编号连续。
### 代码类
- [C-001] 公开接口显式处理非法输入。
"""


class TestGuideInject(unittest.TestCase):
    """guide_inject.py：注入位置/预算/截断顺序均须为确定性可复跑计算（M-截断规格）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.guide = self.tmp / "guide.md"
        self.guide.write_text(GUIDE_FULL, encoding="utf-8")

    def _gi(self, ns="document", budget=600, no_truncate=False):
        args = ["guide_inject.py", "--ns", ns, "--guide", str(self.guide)]
        if no_truncate:
            args.append("--no-truncate")
        else:
            args += ["--budget", str(budget)]
        rc, out, _ = run(*args)
        return rc, (outj(out) if out else {})

    def test_budget_must_be_positive(self):
        """S1 修复：--budget 是必守上限，0/负数一律报错；豁免改由独立开关 --no-truncate 表达。"""
        for bad in ("0", "-5"):
            rc, out, _ = run("guide_inject.py", "--ns", "document", "--budget", bad,
                             "--guide", str(self.guide))
            self.assertEqual(rc, 2, "budget=%s 应报错，实际 rc=%d out=%s" % (bad, rc, out))
            self.assertIn("--budget", outj(out)["error"])

    def test_no_truncate_switch(self):
        rc, r = self._gi(no_truncate=True)
        self.assertEqual(rc, 0, r)
        self.assertTrue(r["no_truncate"])
        self.assertFalse(r["truncated"])
        self.assertEqual(sorted(r["kept"]), ["D-001", "D-002", "G-001", "G-002", "G-003"])

    def test_notice_splits_dropped_by_block(self):
        """M-1 修复：命名空间块被整体弃空时须显式说明，避免被误读为"该 ns 无条款"。"""
        rc, r = self._gi(ns="document", budget=1)
        self.assertEqual(rc, 2)                      # 预算过小 → 保底核心集都不够
        rc, full = self._gi(ns="document", no_truncate=True)
        self.assertEqual(rc, 0)
        rc, r = self._gi(ns="document", budget=full["est_tokens"] - 15)
        self.assertEqual(rc, 0, r)
        self.assertTrue(r["truncated"])
        self.assertIn("D-002", r["dropped_by_block"]["ns"])
        self.assertIn("D-001", r["dropped_by_block"]["ns"])   # ns 两条都未被注入
        self.assertTrue(r["ns_block_present"])
        # 说明文本必须定长，且点明"本命名空间全部未注入"（ID 走结构化字段）
        self.assertTrue(r["notice"] is None or "本命名空间" in r["notice"] or r["notice_omitted"])

    def test_within_budget_keeps_all(self):
        rc, r = self._gi(budget=600)
        self.assertEqual(rc, 0, r)
        self.assertFalse(r["truncated"])
        self.assertEqual(r["dropped"], [])
        self.assertIn("[G-001]", r["block"])
        self.assertIn("[D-002]", r["block"])
        self.assertNotIn("[C-001]", r["block"])      # 非本命名空间条款不得注入
        self.assertLess(r["est_tokens"], 600)

    def test_truncates_ns_before_general_tail(self):
        """截断顺序：先弃命名空间块（尾→首），再弃通用块（尾→首）。"""
        rc, r = self._gi(budget=1)          # 极小预算 → 触发兜底
        self.assertEqual(rc, 2)             # 保底核心集都装不下 → 必须报错，不得静默残缺注入
        self.assertIn("保底核心集", r["error"])

    def test_partial_truncation_order(self):
        # 找一个小到必须截断、又大于保底核心集的预算
        rc, full = self._gi(no_truncate=True)
        self.assertEqual(rc, 0)
        budget = full["est_tokens"] - 15
        rc, r = self._gi(budget=budget)
        self.assertEqual(rc, 0, r)
        self.assertTrue(r["truncated"], r)
        # D-002 是文档块块尾 → 必须最先被弃
        self.assertIn("D-002", r["dropped"])
        # G-001/G-002 属保底核心集 → 永不截断
        self.assertIn("G-001", r["kept"])
        self.assertIn("G-002", r["kept"])

    def test_missing_fixed_block_fails(self):
        self.guide.write_text("## 通用条款\n- [G-001] a\n", encoding="utf-8")
        rc, r = self._gi(budget=600)
        self.assertEqual(rc, 2)
        self.assertIn("审查预告", r["error"])

    def test_est_tokens_deterministic(self):
        _, a = self._gi(budget=600)
        _, b = self._gi(budget=600)
        self.assertEqual(a["est_tokens"], b["est_tokens"])

    def test_general_ns_not_duplicated(self):
        """回归（实测缺陷）：general 的条款块＝通用块本身，曾被渲染两遍（8→16 条、373→588 token）。"""
        rc, r = self._gi(ns="general", no_truncate=True)
        self.assertEqual(rc, 0, r)
        self.assertEqual(r["block"].count("- [G-001]"), 1)
        self.assertEqual(sorted(r["kept"]), ["G-001", "G-002", "G-003"])


class TestOverrides(unittest.TestCase):
    """var/overrides.json：会话级"停止沉淀"必须机械生效，不依赖 agent 记忆。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.state = Path(self._td.name)
        pend = self.state / "snapshots" / "pending" / "document"
        pend.mkdir(parents=True, exist_ok=True)
        for i in range(7):
            (pend / ("s%d.json" % i)).write_text('{"id":"s"}', encoding="utf-8")
        self.now = "2026-09-10T22:39:00+08:00"      # 周四 22:39 = 非高峰

    def _ck(self, now=None):
        rc, out, _ = run("sediment_check.py", "--ns", "document",
                         "--state-dir", str(self.state), "--now", now or self.now)
        return rc, outj(out)

    def test_baseline_fires_sediment(self):
        rc, r = self._ck()
        self.assertEqual(rc, 0)
        self.assertEqual(r["signal"], "sediment")

    def test_override_suppresses(self):
        import io
        (self.state / "overrides.json").write_text(
            json.dumps({"stop_sediment": {"ns": ["document"],
                                          "until": "2026-09-11T22:00:00+08:00",
                                          "reason": "用户指示"}}, ensure_ascii=False),
            encoding="utf-8")
        rc, r = self._ck()
        self.assertEqual(rc, 0)
        self.assertEqual(r["signal"], "none")                 # 抑制生效
        self.assertEqual(r["suppressed"][0]["ns"], "document")
        self.assertTrue(any(s["signal"] == "suppressed" for s in r["signals"]))
        self.assertFalse(any(s["signal"] == "sediment" for s in r["signals"]))

    def test_override_bom_tolerated(self):
        """PS 5.1 `Set-Content -Encoding UTF8` 会带 BOM；带 BOM 也必须能读。"""
        raw = json.dumps({"stop_sediment": {"ns": ["document"],
                                            "until": "2026-09-11T22:00:00+08:00"}},
                         ensure_ascii=False).encode("utf-8")
        (self.state / "overrides.json").write_bytes(b"\xef\xbb\xbf" + raw)
        rc, r = self._ck()
        self.assertEqual(rc, 0)
        self.assertEqual(r["signal"], "none")

    def test_override_expiry_restores_signal(self):
        (self.state / "overrides.json").write_text(
            json.dumps({"stop_sediment": {"ns": ["document"],
                                          "until": "2026-09-09T00:00:00+08:00"}},
                       ensure_ascii=False), encoding="utf-8")
        rc, r = self._ck()
        self.assertEqual(r["signal"], "sediment")
        self.assertTrue(any(s["signal"] == "override-expired" for s in r["signals"]))

    def test_override_other_ns_unaffected(self):
        (self.state / "overrides.json").write_text(
            json.dumps({"stop_sediment": {"ns": ["code"],
                                          "until": "2026-09-11T22:00:00+08:00"}},
                       ensure_ascii=False), encoding="utf-8")
        rc, r = self._ck()
        self.assertEqual(r["signal"], "sediment")

    def test_corrupt_override_fails_loud(self):
        (self.state / "overrides.json").write_text("{not-json", encoding="utf-8")
        rc, r = self._ck()
        self.assertEqual(rc, 1)
        self.assertIn("overrides.json", r["error"])


class TestAntiSelfReinforce(unittest.TestCase):
    """M1~M7：切断"生成端与审查端同源 → 高命中 → 条款固化"的自我强化闭环。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.state = str(self.tmp / "state")
        self.skill = make_scratch_skill(self.tmp)
        self.now = "2026-09-10T22:39:00+08:00"

    def _pending(self, n, typ="事实性", dropped=None):
        d = Path(self.state) / "snapshots" / "pending" / "document"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            snap = mk_snap(i, ns="document")
            snap["issues"] = [{"id": "AR-N-%d" % i, "severity": "major", "type": typ,
                               "anchor": "第%d节" % i, "basis": "[D-001]",
                               "status": "已关闭", "false_positive": False, "reopen_count": 0}]
            if dropped:
                snap["guide_dropped"] = dropped
            (d / ("%s.json" % snap["id"])).write_text(json.dumps(snap, ensure_ascii=False),
                                                      encoding="utf-8")

    def _ledger(self, typ="事实性"):
        ld = Path(self.state) / "ledger"
        ld.mkdir(parents=True, exist_ok=True)
        (ld / "sess-1.json").write_text(json.dumps({
            "session": "sess-1",
            "issues": [{"id": "AR-L-001", "severity": "major", "type": typ,
                        "anchor": "a", "basis": "b", "status": "已关闭",
                        "history": [{"event": "new"}, {"event": "fix_start"}]}]
        }, ensure_ascii=False), encoding="utf-8")

    def _sr(self, *extra):
        args = ["--ns", "document", "--state-dir", self.state,
                "--skill-root", self.skill, "--now", self.now]
        return run("sediment_run.py", *(list(extra) + args))

    def _kinds(self, out):
        return [(c["kind"], c.get("clause") or c.get("defect_type")) for c in outj(out)["candidates"]]

    # ---- M3：新增门槛 5 且须有实际返工证据 ----
    def test_threshold_5_not_4(self):
        self._pending(4)
        self._ledger()
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        self.assertNotIn(("new-clause-candidate", "事实性"), self._kinds(out))

    def test_threshold_5_fires_with_fix_evidence(self):
        self._pending(5)
        self._ledger()
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        self.assertIn(("new-clause-candidate", "事实性"), self._kinds(out))

    def test_no_fix_evidence_rejects_new_clause(self):
        """M3：仅频次达标、ledger 中无实际返工 → 拒绝生成新增候选。"""
        self._pending(5)                      # 不写 ledger
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        self.assertNotIn(("new-clause-candidate", "事实性"), self._kinds(out))
        self.assertIn(("new-clause-rejected", "事实性"), self._kinds(out))

    # ---- M5：被截断条款不得进降权候选 ----
    def test_truncated_clause_excluded_from_demote(self):
        self._pending(3, dropped=["D-002"])
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        kinds = self._kinds(out)
        self.assertIn(("demote-suppressed", "D-002"), kinds)
        self.assertNotIn(("demote-candidate", "D-002"), kinds)

    # ---- M4：条款数上限 ----
    def test_clause_cap_blocks_add(self):
        (Path(self.skill) / "references" / "pregen-guide.md").write_text(
            "# G\n\n## 通用条款\n- [G-001] a\n\n## 命名空间条款\n### 文档类\n"
            "- [D-001] x\n- [D-002] y\n- [D-003] z\n- [D-004] w\n", encoding="utf-8")
        self._pending(1)
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({"add": [{"ns": "document", "line": "- [D-005] 新增条款须含编号"}]},
                                    ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        ac = outj(out)["phases_run"]
        guide = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertNotIn("D-005", guide)                       # 超上限 → 不得写入
        self.assertIn("S2", ac)

    # ---- M6：不可证伪措辞拒绝 ----
    def test_unfalsifiable_wording_rejected(self):
        self._pending(1)
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({"add": [{"ns": "document",
                                              "line": "- [D-009] 生成时应认真重视质量"}]},
                                    ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        guide = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertNotIn("D-009", guide)

    # ---- M1/M7：生命周期 trial → active ----
    def test_lifecycle_trial_then_promote(self):
        self._pending(1)
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({"add": [{"ns": "document",
                                              "line": "- [D-007] 每张表须标注表号并与正文一致",
                                              "basis": ["AR-20260910-001"]}]},
                                    ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        lcf = Path(self.state) / "registry" / "guide-clauses.json"
        lc = json.loads(lcf.read_text(encoding="utf-8"))
        ent = next(x for x in lc["clauses"] if x["id"] == "D-007")
        self.assertEqual(ent["state"], "trial")                # 新条款一律先试用
        self.assertEqual(ent["basis"], ["AR-20260910-001"])

        # 第二个窗口：再次沉淀 → 观察期达标且有返工证据 → 转正
        self._pending(2)
        edits2 = self.tmp / "edits2.json"
        edits2.write_text("{}", encoding="utf-8")
        rc, out2, _ = self._sr("--guide-edits", str(edits2))
        self.assertEqual(rc, 0, out2)
        lc = json.loads(lcf.read_text(encoding="utf-8"))
        ent = next(x for x in lc["clauses"] if x["id"] == "D-007")
        self.assertEqual(ent["state"], "active")

    def test_lifecycle_retire_removes_entry(self):
        self._pending(1)
        edits = self.tmp / "edits.json"
        edits.write_text(json.dumps({"retire": ["D-002"]}, ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        guide = (Path(self.skill) / "references" / "pregen-guide.md").read_text(encoding="utf-8")
        self.assertNotIn("D-002", guide)
        lc = json.loads((Path(self.state) / "registry" / "guide-clauses.json").read_text(encoding="utf-8"))
        self.assertNotIn("D-002", [x["id"] for x in lc["clauses"]])

    def _seed_lifecycle(self, entries):
        reg = Path(self.state) / "registry"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / "guide-clauses.json").write_text(
            json.dumps({"clauses": entries}, ensure_ascii=False), encoding="utf-8")
        return reg / "guide-clauses.json"

    def test_demote_candidate_requires_zero_evidence_windows(self):
        """M2 一致性：零证据窗口达阈值才产出 demote-candidate（不再仅凭零命中）。"""
        self._pending(3)
        self._seed_lifecycle([{"id": "D-002", "block": "文档类", "state": "active",
                               "added_iter": None, "basis": [], "windows_observed": 2,
                               "zero_evidence_windows": 2, "last_counted_iter": None,
                               "evidence": {"hits": 0}}])
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        kinds = self._kinds(out)
        self.assertIn(("demote-candidate", "D-002"), kinds)
        self.assertNotIn(("demote-hint", "D-002"), kinds)

    def test_hits_reset_zero_evidence_counter(self):
        """真 bug 回归：既有条款 basis 恒为空，若只认 basis 计零证据，4 窗口后会被集体判淘汰。
        现行语义＝hits 或 basis 任一存在即重置计数（hits 作"参与度"信号，不能用于升格）。"""
        self._pending(1)                      # 快照 basis 含 [D-001] → D-001 有引用
        lcf = self._seed_lifecycle([{"id": "D-001", "block": "文档类", "state": "active",
                                     "added_iter": None, "basis": [], "windows_observed": 0,
                                     "zero_evidence_windows": 3, "last_counted_iter": None,
                                     "evidence": {"hits": 0}}])
        edits = self.tmp / "e0.json"
        edits.write_text("{}", encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        lc = json.loads(lcf.read_text(encoding="utf-8"))
        e = next(x for x in lc["clauses"] if x["id"] == "D-001")
        self.assertEqual(e["zero_evidence_windows"], 0)       # 有引用 → 重置，不会被误判淘汰

    def test_guide_changes_file_written_for_audit(self):
        """M7 审计：本轮"凭什么改条款"须落 iter-N-guide-changes.json。"""
        self._pending(1)
        edits = self.tmp / "e.json"
        edits.write_text(json.dumps({"add": [{"ns": "document",
                                              "line": "- [D-008] 表号须与正文一致",
                                              "basis": ["AR-20260910-002"]}]},
                                    ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(edits))
        self.assertEqual(rc, 0, out)
        cf = Path(self.state) / "sediment" / "iter-1-guide-changes.json"
        self.assertTrue(cf.exists())
        d = json.loads(cf.read_text(encoding="utf-8"))
        self.assertEqual(d["edits_requested"]["add"][0]["basis"], ["AR-20260910-002"])
        self.assertEqual(d["edits_applied"]["add"], ["D-008"])
        # 新增条款须以 trial 登记（生命周期结论随审计文件落盘）
        self.assertIn("D-008", d["edits_applied"]["lifecycle"]["trial_registered"])
        lc = json.loads((Path(self.state) / "registry" / "guide-clauses.json").read_text(encoding="utf-8"))
        e = next(x for x in lc["clauses"] if x["id"] == "D-008")
        self.assertEqual(e["state"], "trial")
        self.assertEqual(e["basis"], ["AR-20260910-002"])     # 依据随审计链保留

    def _pending_no_hit(self, n):
        """构造 basis 不含任何条款 ID 的快照 → 所有条款本窗口零命中。"""
        d = Path(self.state) / "snapshots" / "pending" / "document"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            snap = mk_snap(i, ns="document")
            snap["id"] = "snap-nohit-%03d" % (len(list(d.glob("*.json"))) + i)
            snap["issues"] = [{"id": "AR-NH-%d" % i, "severity": "major", "type": "表述",
                               "anchor": "a", "basis": "无条款引用", "status": "已关闭",
                               "false_positive": False, "reopen_count": 0}]
            (d / ("%s.json" % snap["id"])).write_text(json.dumps(snap, ensure_ascii=False),
                                                      encoding="utf-8")

    def _run_window(self, tag):
        e = self.tmp / ("e-%s.json" % tag)
        e.write_text("{}", encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(e))
        return rc, out

    def test_basis_does_not_permanently_exempt_clause(self):
        """B1 回归（独立审查阻断项）：basis 是累积字段且永不清除，若用它判"本窗口有证据"，
        任何曾绑定 basis 的条款将永久豁免降权/淘汰——最该被抗固化的"经流程升格条款"反而免疫。
        现按窗口判证据（last_evidence_iter == 本轮 N），故此类条款仍会累计零证据窗口。"""
        self._seed_lifecycle([{"id": "D-001", "block": "文档类", "state": "active",
                               "added_iter": 1, "basis": ["AR-OLD"],
                               "windows_observed": 0, "zero_evidence_windows": 0,
                               "last_counted_iter": None, "last_evidence_iter": 0,
                               "evidence": {"hits": 0}}])
        last = None
        for w in range(1, 5):                       # 连续 4 个窗口，均零命中且无新 basis
            self._pending_no_hit(1)
            rc, out = self._run_window("w%d" % w)
            self.assertEqual(rc, 0, out)
            last = out
        cf = Path(self.state) / "sediment" / "iter-4-guide-changes.json"
        self.assertTrue(cf.exists())
        d = json.loads(cf.read_text(encoding="utf-8"))
        lc = json.loads((Path(self.state) / "registry" / "guide-clauses.json").read_text(encoding="utf-8"))
        e = next(x for x in lc["clauses"] if x["id"] == "D-001")
        self.assertEqual(e["basis"], ["AR-OLD"])                  # 累积 basis 仍在（未被清）
        self.assertGreaterEqual(e["zero_evidence_windows"], 2)    # 但仍累计 → 不被永久豁免
        self.assertIn("D-001", d["lifecycle"]["retire_suggest"])  # 4 窗口 → 出淘汰建议

    def test_bom_in_lifecycle_file_is_read_not_silently_reset(self):
        """BOM 回归：load_json 原用 utf-8，遇 BOM 抛异常被 except 吞掉 → 静默返回默认值
        （var/registry/scripts.json 实测带 BOM，会导致 S3 注册表被覆盖为空）。现用 utf-8-sig。"""
        raw = json.dumps({"clauses": [{"id": "D-001", "block": "文档类", "state": "active",
                                       "added_iter": None, "basis": [], "windows_observed": 0,
                                       "zero_evidence_windows": 3, "last_counted_iter": None,
                                       "last_evidence_iter": None, "evidence": {"hits": 0}}]},
                         ensure_ascii=False).encode("utf-8")
        reg = Path(self.state) / "registry"
        reg.mkdir(parents=True, exist_ok=True)
        (reg / "guide-clauses.json").write_bytes(b"\xef\xbb\xbf" + raw)
        self._pending_no_hit(1)
        rc, out = self._run_window("bom")
        self.assertEqual(rc, 0, out)
        lc = json.loads((reg / "guide-clauses.json").read_text(encoding="utf-8-sig"))
        e = next(x for x in lc["clauses"] if x["id"] == "D-001")
        # 若 BOM 让它被静默重置，该条会被当新条目重建、计数从 0 起；读到则 3→4
        self.assertEqual(e["zero_evidence_windows"], 4)

    def test_checkable_heuristic_warns_on_vague_clause(self):
        """S2 回归：早期 _CHECKABLE_RE 用字符类，任一常见汉字即命中 → warn 分支形同虚设。"""
        self._pending(1)
        e = self.tmp / "vague.json"
        e.write_text(json.dumps({"add": [{"ns": "document",
                                          "line": "- [D-021] 提升代码质量与整体可维护性"}]},
                                ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(e))
        self.assertEqual(rc, 0, out)
        d = json.loads((Path(self.state) / "sediment" / "iter-1-guide-changes.json")
                       .read_text(encoding="utf-8"))
        self.assertIn("D-021", d["edits_applied"]["add"])          # 启发式不硬拒 → 仍写入
        self.assertTrue(any("D-021" in w for w in (d["edits_applied"].get("warn") or [])),
                        d["edits_applied"].get("warn"))

    def test_checkable_heuristic_passes_clause_with_real_anchor(self):
        """反面：含真实可核对锚点（编号/数值/单位）的条款不得告警。"""
        self._pending(1)
        e = self.tmp / "ok.json"
        e.write_text(json.dumps({"add": [{"ns": "document",
                                          "line": "- [D-022] 表号须与正文一致，数值保留 2 位小数并带单位"}]},
                                ensure_ascii=False), encoding="utf-8")
        rc, out, _ = self._sr("--guide-edits", str(e))
        self.assertEqual(rc, 0, out)
        d = json.loads((Path(self.state) / "sediment" / "iter-1-guide-changes.json")
                       .read_text(encoding="utf-8"))
        self.assertFalse(any("D-022" in w for w in (d["edits_applied"].get("warn") or [])))

    def test_m5_full_pipeline_await_then_resume(self):
        """关闭审查未完成项：M5 走完整 await_edits → resume 链路仍正确，且截断清单入审计文件。"""
        self._pending(2, dropped=["D-002"])
        rc, out, _ = self._sr()
        self.assertEqual(rc, 0, out)
        k1 = self._kinds(out)
        self.assertIn(("demote-suppressed", "D-002"), k1)
        self.assertNotIn(("demote-candidate", "D-002"), k1)
        it = outj(out)["iter"]
        e = self.tmp / "r.json"
        e.write_text("{}", encoding="utf-8")
        rc, out2, _ = self._sr("--resume", it, "--guide-edits", str(e))
        self.assertEqual(rc, 0, out2)
        self.assertEqual(outj(out2)["status"], "done")
        d = json.loads((Path(self.state) / "sediment" / "iter-1-guide-changes.json")
                       .read_text(encoding="utf-8"))
        self.assertEqual(d["guide_dropped"], ["D-002"])           # 截断清单已入审计链

    def test_guide_dropped_accepted_by_snapshot(self):
        """M5：collect_snapshot 必须接受 guide_dropped（否则观测链断）。"""
        snap = mk_snap(7)
        snap["guide_dropped"] = ["D-002"]
        rc, out, _ = run("collect_snapshot.py", "--ns", "document",
                         "--state-dir", self.state, stdin=json.dumps(snap, ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        snap["guide_dropped"] = "D-002"                        # 类型错 → 拒收
        rc2, out2, _ = run("collect_snapshot.py", "--ns", "document",
                           "--state-dir", self.state, stdin=json.dumps(snap, ensure_ascii=False))
        self.assertEqual(rc2, 2, out2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
