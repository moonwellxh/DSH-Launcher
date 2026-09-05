# -*- coding: utf-8 -*-
# =====================================================================
# collect_snapshot.py —— 运行末快照落盘（FR-20）
# 用法: python3 collect_snapshot.py --ns <general|document|code|regulation> < data.json
# 输出: 单行 JSON {"written": "<绝对路径>"}；失败输出 {"error":…,"hint":…}
# 退出码: 0 成功 / 2 schema 校验失败 / 3 超 10KB / 1 IO 错误
# 纪律: 不存原文只存锚点摘要；单条 ≤10KB；stdin 的 ns 与 --ns 不一致时以 --ns 为准并告警。
# =====================================================================
import argparse, json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # 统一 UTF-8 输出，避免 GBK 控制台报错
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_BJ = timezone(timedelta(hours=8))
_NS = ("general", "document", "code", "regulation")

def beijing_now():
    return datetime.now(_BJ)

def skill_root():
    return Path(__file__).resolve().parents[1]

def _probe_writable(p):
    try:
        p.write_text("ok", encoding="utf-8"); p.unlink(); return True
    except Exception:
        return False

def resolve_state_dir(root=None, cli=None):
    """三级回落: ADV_REVIEW_HOME → <技能根>/var → ~/.adversarial-review"""
    root = root or skill_root()
    if cli:
        return Path(cli)
    env = os.environ.get("ADV_REVIEW_HOME")
    if env:
        return Path(env)
    cand = root / "var"
    try:
        cand.mkdir(parents=True, exist_ok=True)  # 先建目录再探测：否则新装技能 var/ 缺失，探测必失败而永远回落 home
    except Exception:
        pass
    return cand if _probe_writable(cand / ".probe") else Path.home() / ".adversarial-review"

def ensure_dir(p):
    p.mkdir(parents=True, exist_ok=True)
    return p

def out_json(obj):
    print(json.dumps(obj, ensure_ascii=False))

def fail(code, error, hint=None):
    d = {"error": error}
    if hint:
        d["hint"] = hint
    out_json(d)
    sys.exit(code)

# ---- 必填字段校验（缺一即拒收，退出码 2）----
TOP_REQUIRED = ["id", "ts", "ns", "env", "task", "mode", "rounds", "issues", "tokens", "outcome"]
ENV_REQUIRED = ["platform", "pricing_version"]     # host_note/model 允许缺失或 null
TASK_REQUIRED = ["summary", "object_type"]
ISSUE_REQUIRED = ["id", "severity", "type", "anchor", "basis", "status"]
SEVERITIES = {"blocking", "major", "minor", "suggestion"}
MODES = {"closed_loop", "report_only"}
OUTCOMES = {"passed", "converged", "fused", "aborted"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate(obj, ns_flag):
    """返回错误串列表；空列表=通过。"""
    errs = []
    if not isinstance(obj, dict):
        return ["顶层必须是 JSON 对象"]
    for k in TOP_REQUIRED:
        if k not in obj:
            errs.append("缺顶层字段: %s" % k)
    if "mode" in obj and obj["mode"] not in MODES:
        errs.append("mode 非法(期望 closed_loop|report_only): %s" % obj["mode"])
    if "outcome" in obj and obj["outcome"] not in OUTCOMES:
        errs.append("outcome 非法: %s" % obj["outcome"])
    env = obj.get("env")
    if isinstance(env, dict):
        for k in ENV_REQUIRED:
            if k not in env:
                errs.append("env 缺字段: %s" % k)
    else:
        errs.append("env 必须是对象")
    task = obj.get("task")
    if isinstance(task, dict):
        for k in TASK_REQUIRED:
            if k not in task:
                errs.append("task 缺字段: %s" % k)
    else:
        errs.append("task 必须是对象")
    issues = obj.get("issues")
    if isinstance(issues, list):
        for i, it in enumerate(issues):
            if not isinstance(it, dict):
                errs.append("issues[%d] 非对象" % i)
                continue
            for k in ISSUE_REQUIRED:
                if k not in it:
                    errs.append("issues[%d] 缺字段: %s" % (i, k))
            if it.get("severity") not in SEVERITIES:
                errs.append("issues[%d] severity 非法: %s" % (i, it.get("severity")))
    else:
        errs.append("issues 必须是数组")
    if not isinstance(obj.get("tokens"), list):
        errs.append("tokens 必须是数组")
    try:
        int(obj.get("rounds"))
    except (TypeError, ValueError):
        errs.append("rounds 必须是整数")
    return errs


def main():
    ap = argparse.ArgumentParser(description="对抗性审查运行快照落盘（FR-20）")
    ap.add_argument("--ns", required=True, choices=list(_NS), help="命名空间（与 JSON 内 ns 不一致时以此为准）")
    ap.add_argument("--state-dir", default=None, help="状态目录覆盖（测试/演示用）")
    args = ap.parse_args()

    raw = sys.stdin.buffer.read()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail(2, "stdin 非 UTF-8", "请以 UTF-8 编码传入快照 JSON")
    try:
        obj = json.loads(txt)
    except Exception as e:
        fail(2, "JSON 解析失败: %s" % e)

    json_ns = obj.get("ns") if isinstance(obj, dict) else None
    if json_ns != args.ns:
        sys.stderr.write(json.dumps({"warning": "JSON 内 ns=%r 与 --ns=%s 不一致，已以 --ns 为准" % (json_ns, args.ns)},
                                    ensure_ascii=False) + "\n")
        if json_ns is not None:
            # “以 --ns 为准”须落到内容：落盘 JSON 的 ns 与目录归属保持一致
            # （ns 整体缺失时不补，仍由下方 schema 校验按“缺顶层字段”拒收）
            obj["ns"] = args.ns

    errs = validate(obj, args.ns)
    if errs:
        fail(2, "schema 校验失败", "；".join(errs[:8]) + ("（等 %d 项）" % len(errs) if len(errs) > 8 else ""))

    # protocols 7.1 纪律：issue 的 false_positive/reopen_count 缺省按 false/0 补齐后再落盘
    for it in obj.get("issues") or []:
        if isinstance(it, dict):
            it.setdefault("false_positive", False)
            it.setdefault("reopen_count", 0)

    # 大小纪律: UTF-8 字节 ≤10KB，超限退出码 3 并提示最占字节字段
    canon = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    nbytes = len(canon.encode("utf-8"))
    if nbytes > 10240:
        sizes = sorted(
            ((k, len(json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
             for k, v in obj.items() if k != "issues"),
            key=lambda kv: -kv[1])[:3]
        sizes.append(("issues", len(json.dumps(obj.get("issues"), ensure_ascii=False).encode("utf-8"))))
        top = ", ".join("%s=%dB" % (k, v) for k, v in sorted(sizes, key=lambda kv: -kv[1])[:3])
        fail(3, "快照超 10KB 上限（%dB）" % nbytes, "最占字节字段: " + top + "；请压缩摘要或裁剪锚点")

    sid = obj.get("id")
    if not sid or not ID_RE.match(str(sid)):
        fail(2, "id 非法", "id 应形如 snap-YYYYMMDD-HHMMSS-xxxx（字母数字._-）")

    state = resolve_state_dir(cli=args.state_dir)
    pend = ensure_dir(state / "snapshots" / "pending" / args.ns)
    target = pend / ("%s.json" % sid)
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(canon, encoding="utf-8")
        os.replace(tmp, target)
    except Exception as e:
        fail(1, "快照写入失败: %s" % e, "写入失败计入脚本失败协议，必须如实上报；本次运行不计入 pending 计数")
    out_json({"written": str(target.resolve())})


if __name__ == "__main__":
    main()
