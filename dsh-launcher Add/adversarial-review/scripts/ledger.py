# -*- coding: utf-8 -*-
# =====================================================================
# ledger.py —— 问题台账状态机（FR-4/6 强制流转）
# 用法:
#   python3 ledger.py --session <id> new                 # stdin: {"issues":[…]}
#   python3 ledger.py --session <id> transition --id <issue_id> --event <事件> [--evidence "反驳证据"]
#   python3 ledger.py --session <id> list [--status <状态>]
#   python3 ledger.py --session <id> export
# 输出: 单行 JSON；非法转移退出码 2。
# 状态机: 提出→已确认→修复中→待验证→(已关闭|已确认[重开])；已关闭--regression_fail-->已确认；reject 需反驳证据。
# =====================================================================
import argparse, json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_BJ = timezone(timedelta(hours=8))
_NS = ("general", "document", "code", "regulation")
_SEVERITIES = {"blocking", "major", "minor", "suggestion"}
_CONFIDENCES = {"high", "medium", "low"}
_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# 状态机: 当前状态 -> {合法事件: 目标状态}
TRANSITIONS = {
    "提出":   {"confirm": "已确认", "reject": "已驳回"},
    "已确认": {"fix_start": "修复中", "reject": "已驳回"},
    "修复中": {"fix_submit": "待验证"},
    "待验证": {"verify_pass": "已关闭", "verify_fail": "已确认"},
    "已关闭": {"regression_fail": "已确认"},
    "已驳回": {},
}
REOPEN_EVENTS = {"verify_fail", "regression_fail"}
ALL_EVENTS = set()
for _m in TRANSITIONS.values():
    ALL_EVENTS.update(_m.keys())


def beijing_now():
    return datetime.now(_BJ)


def iso_now():
    return beijing_now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def skill_root():
    return Path(__file__).resolve().parents[1]


def _probe_writable(p):
    try:
        p.write_text("ok", encoding="utf-8"); p.unlink(); return True
    except Exception:
        return False


def resolve_state_dir(root=None, cli=None):
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


def ledger_path(state, sid):
    return state / "ledger" / ("%s.json" % sid)


def load_ledger(state, sid, must=True):
    p = ledger_path(state, sid)
    if not p.exists():
        if must:
            fail(1, "台账不存在: %s" % sid, "先执行 ledger.py --session %s new" % sid)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        fail(1, "台账读取失败: %s" % e)


def save_ledger(p, ledger):
    ensure_dir(p.parent)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def cmd_new(args, state, sid):
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except Exception as e:
        fail(2, "stdin JSON 解析失败: %s" % e)
    issues_in = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(issues_in, list):
        fail(2, "payload 缺 issues 数组", 'stdin 应为 {"issues":[…]}, 每项含 anchor/basis/confidence/severity')

    p = ledger_path(state, sid)
    if p.exists() and not args.force:
        fail(2, "台账已存在: %s" % sid, "如需重建请加 --force（重建会覆盖旧台账，谨慎）")

    now = iso_now()
    issues_out, dropped, seq = [], [], 0
    for it in issues_in:
        if not isinstance(it, dict):
            dropped.append({"reason": "非对象条目"})
            continue
        missing = [k for k in ("anchor", "basis", "confidence") if not str(it.get(k) or "").strip()]
        if it.get("confidence") not in _CONFIDENCES:
            missing.append("confidence(枚举)")
        if it.get("severity") not in _SEVERITIES:
            missing.append("severity(枚举)")
        if missing:
            dropped.append({"reason": "缺字段/非法: %s" % ", ".join(missing)})
            continue
        seq += 1
        iid = "AR-%s-%03d" % (beijing_now().strftime("%Y%m%d"), seq)
        issues_out.append({
            "id": iid,
            "severity": it.get("severity"),
            "type": it.get("type") or "未分类",
            "anchor": str(it.get("anchor")),
            "basis": str(it.get("basis")),
            "confidence": it.get("confidence"),
            "suggestion": str(it.get("suggestion") or ""),
            "status": "提出",
            "reopen_count": 0,
            "created_at": now,
            "updated_at": now,
            "history": [{"event": "new", "at": now}],
        })
    ledger = {"session": sid, "created_at": now, "updated_at": now,
              "issues": issues_out}
    save_ledger(p, ledger)
    out_json({"created": len(issues_out), "dropped": len(dropped),
              "dropped_reasons": dropped, "ids": [i["id"] for i in issues_out],
              "file": str(p.resolve())})


def cmd_transition(args, state, sid):
    if args.event not in ALL_EVENTS:
        fail(2, "未知事件: %s" % args.event, "合法事件: %s" % ", ".join(sorted(ALL_EVENTS)))
    if args.event == "reject" and not str(args.evidence or "").strip():
        fail(2, "reject 必须附反驳证据", '加 --evidence "反驳依据（条文号/可复现反例）"')
    ledger = load_ledger(state, sid)
    issue = next((i for i in ledger["issues"] if i["id"] == args.id), None)
    if issue is None:
        fail(2, "issue 不存在: %s" % args.id)
    cur = issue["status"]
    allowed = TRANSITIONS.get(cur, {})
    if args.event not in allowed:
        fail(2, "非法转移: %s --%s--> ? 不允许" % (cur, args.event),
             "当前状态 %s 允许的事件: %s" % (cur, ", ".join(sorted(allowed)) or "无(已终态)"))
    new_status = allowed[args.event]
    issue["status"] = new_status
    issue["updated_at"] = iso_now()
    issue["history"].append({"event": args.event, "at": iso_now(), "from": cur})
    if args.event in REOPEN_EVENTS:
        issue["reopen_count"] = int(issue.get("reopen_count") or 0) + 1
    ledger["updated_at"] = iso_now()
    save_ledger(ledger_path(state, sid), ledger)
    out_json({"id": issue["id"], "event": args.event, "from": cur, "to": new_status,
              "reopen_count": issue["reopen_count"]})


def cmd_list(args, state, sid):
    ledger = load_ledger(state, sid)
    issues = ledger["issues"]
    if args.status:
        issues = [i for i in issues if i["status"] == args.status]
    counts = {}
    for i in ledger["issues"]:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    out_json({"issues": issues, "counts": counts})


def cmd_export(args, state, sid):
    ledger = load_ledger(state, sid)
    out_json(ledger)


def main():
    ap = argparse.ArgumentParser(description="问题台账状态机（FR-4/6）")
    ap.add_argument("--session", required=True, help="审查会话标识（文件名安全字符）")
    ap.add_argument("--state-dir", default=None, help="状态目录覆盖（测试/演示用）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="新建台账（stdin 读 issues）")
    p_new.add_argument("--force", action="store_true")
    p_new.set_defaults(func=cmd_new)

    p_tr = sub.add_parser("transition", help="状态转移")
    p_tr.add_argument("--id", required=True)
    p_tr.add_argument("--event", required=True)
    p_tr.add_argument("--evidence", default=None)
    p_tr.set_defaults(func=cmd_transition)

    p_ls = sub.add_parser("list", help="列出（可按状态过滤）")
    p_ls.add_argument("--status", default=None)
    p_ls.set_defaults(func=cmd_list)

    p_ex = sub.add_parser("export", help="全量导出（供快照组装）")
    p_ex.set_defaults(func=cmd_export)

    args = ap.parse_args()
    if not _SESSION_RE.match(args.session):
        fail(2, "session 标识非法", "仅允许字母数字 . _ -")
    state = resolve_state_dir(cli=args.state_dir)
    args.func(args, state, args.session)


if __name__ == "__main__":
    main()
