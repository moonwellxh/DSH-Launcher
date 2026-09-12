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
        self.assertTrue(any(c["kind"] == "new-clause-candidate" and c["count"] >= 3
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
        """F2: 导引单现存条款本窗口零命中 → 产出降权候选（修复死分支）。"""
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
        self.assertIn(("demote-candidate", "D-002"), kinds)       # D-002 零命中 → 降权候选
        self.assertNotIn(("demote-candidate", "D-001"), kinds)    # D-001 有命中 → 不降权

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
