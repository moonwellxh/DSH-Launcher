# -*- coding: utf-8 -*-
# =====================================================================
# sediment_check.py —— 沉淀/提醒信号判断（FR-24/25，纯确定性，零模型成本）
# 用法: python3 sediment_check.py [--now ISO] [--state-dir DIR] [--ns NS] [--no-persist]
# 输出: 单行 JSON:
#   {"signal": "sediment|remind|none",
#    "signals": [{"signal":"sediment","ns":..,"pending":n,"hours_since_last":h,"offpeak":bool}, ...],
#    "suppressed": [{"ns":..,"until":..,"reason":..}, ...],
#    "budget": {...}}
#   signal=多命名空间同时命中时的最高优先级（sediment > remind > none），逐条处理见 signals。
#   被会话级覆盖（overrides.json）抑制的命名空间不进 signal 判定，只在 signals 里以
#   {"signal":"suppressed"} 形式留痕，并在顶层 suppressed 汇总（用户必须看得见"为什么不沉淀"）。
# 退出码: 0 判定完成（信号含 none 亦为成功）/ 1 state.json、overrides.json 或价格表损坏等异常（按失败协议如实上报，不得静默）
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
_DAY = timedelta(hours=24)
# monthly_left_cny=None 表示月度余额控制暂不启用（所有者裁决 2026-09-06，F15）；
# 填入数值即恢复启用（建议 2.0，见设计稿 FR-27）。单次限额不受此开关影响。
_BUDGET_DEFAULT = {"single_run_max_cny": 0.5, "monthly_left_cny": None,
                   "single_input_tok_max": 120000, "single_output_tok_max": 20000}

def beijing_now():
    return datetime.now(_BJ)

def parse_dt(s):
    if not s:
        return None
    try:
        v = datetime.fromisoformat(str(s))
        if v.tzinfo is None:
            v = v.replace(tzinfo=_BJ)
        return v
    except Exception:
        return None

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

def load_state(state):
    p = state / "state.json"
    if not p.exists():
        return {"last_sediment_at": {}, "budget": dict(_BUDGET_DEFAULT),
                "last_remind_at": None, "pricing_checked_at": None, "iter_seq": 0}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        s.setdefault("budget", dict(_BUDGET_DEFAULT))
        s.setdefault("last_sediment_at", {})
        return s
    except Exception as e:
        fail(1, "state.json 读取失败: %s" % e, "损坏的 state.json 需人工检查（单一写入者：仅沉淀流程可写）")

def save_state(state, obj):
    p = state / "state.json"
    ensure_dir(state)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)

def read_pricing(root=None):
    root = root or skill_root()
    txt = (root / "references" / "pricing-models.md").read_text(encoding="utf-8")
    m = re.search(r"```json\s*\n(.*?)\n```", txt, re.S)
    if not m:
        fail(1, "pricing JSON 块缺失", "references/pricing-models.md 需含唯一 ```json 块")
    try:
        return json.loads(m.group(1))
    except Exception as e:
        fail(1, "pricing JSON 解析失败: %s" % e)

def load_overrides(state):
    """读会话级覆盖 var/overrides.json（用户明示"停止本次会话的沉淀"时由 agent 落盘）。

    结构: {"stop_sediment": null | {"ns": ["document"], "until": "ISO8601",
                                    "reason": "…", "created_at": "ISO8601"}}
    - 文件不存在 → 无覆盖（与历史行为完全一致）。
    - 文件存在但 JSON 损坏 → 报错退出（退出码 1）。**禁止静默回退**：
      静默回退会悄悄取消用户设定的抑制，属安全性静默变更。
    - ns 缺省/空 → 抑制全部命名空间；且 ns 内元素非法不影响其余元素之外的判定。
    """
    p = state / "overrides.json"
    if not p.exists():
        return {}
    try:
        # 用 utf-8-sig 而非 utf-8：本文件由 agent（非 Python save_json）写入，
        # 而 Windows PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会带 BOM，
        # 按 utf-8 读会抛 "Unexpected UTF-8 BOM" → 整条抑制功能失效。
        # utf-8-sig 在无 BOM 时与 utf-8 等价，属零代价兼容（2026-09-10 实测踩坑）。
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        fail(1, "overrides.json 读取失败: %s" % e,
             "损坏的 overrides.json 需人工检查；删除该文件即恢复默认（不抑制）行为")
    if not isinstance(obj, dict):
        fail(1, "overrides.json 顶层非 JSON 对象", "应为 {\"stop_sediment\": null | {...}}")
    return obj


def in_peak(now, pricing):
    """按价格表峰谷窗口判断是否高峰（weekday=周一~五）。窗口为闭区间。

    星期判定用 datetime.weekday()（Mon=0..Sun=6），不用 strftime("%A")——
    后者随进程 LC_TIME 本地化，非英文 locale 下周末会被误判为工作日（峰谷前提静默失效）。
    """
    wd = now.weekday()
    hm = now.strftime("%H:%M")
    for mod in pricing.get("models", []):
        pk = (mod.get("peak") or {}).get("windows") or []
        if not pk:
            continue
        days = (mod.get("peak") or {}).get("days", "weekday")
        active = (days == "*"
                  or (days == "weekday" and wd < 5)
                  or (days == "weekend" and wd >= 5))
        if not active:
            continue
        for s, e in pk:
            if s <= hm <= e:
                return True
    return False


def main():
    ap = argparse.ArgumentParser(description="沉淀/提醒信号判断（纯确定性，零模型成本）")
    ap.add_argument("--now", default=None, help="ISO8601 时间（测试用；缺省=北京时间 now）")
    ap.add_argument("--state-dir", default=None, help="状态目录覆盖（测试/演示用）")
    ap.add_argument("--ns", default=None, choices=list(_NS), help="只检查单个命名空间")
    ap.add_argument("--no-persist", action="store_true", help="不写回 state（防抖写库开关）")
    args = ap.parse_args()

    now = parse_dt(args.now) or beijing_now()
    pricing = read_pricing()
    peak = in_peak(now, pricing)
    state = load_state(resolve_state_dir(cli=args.state_dir))
    overrides = load_overrides(resolve_state_dir(cli=args.state_dir))

    def suppression_for(ns):
        """该命名空间是否被会话级覆盖抑制；返回 None 或 {until, reason, expired}。"""
        stop = overrides.get("stop_sediment")
        if not isinstance(stop, dict):
            return None
        until = parse_dt(stop.get("until"))
        if until is not None and now > until:
            return {"until": stop.get("until"), "reason": stop.get("reason"),
                    "expired": True}   # 已过期：不再抑制，但在 signals 中留痕
        nss = stop.get("ns")
        if isinstance(nss, list) and nss and ns not in nss:
            return None
        return {"until": stop.get("until"), "reason": stop.get("reason"), "expired": False}

    def hours_since(ts):
        last = parse_dt(ts)
        if last is None:
            return None          # 从未沉淀 → 视为远超阈值
        return (now - last).total_seconds() / 3600.0

    reminded_ago = None
    if state.get("last_remind_at"):
        rl = parse_dt(state["last_remind_at"])
        if rl:
            reminded_ago = (now - rl).total_seconds() / 3600.0

    signals = []
    suppressed = []
    for ns in _NS:
        if args.ns and ns != args.ns:
            continue
        pend_dir = resolve_state_dir(cli=args.state_dir) / "snapshots" / "pending" / ns
        n = 0
        if pend_dir.exists():
            n = len([f for f in pend_dir.glob("*.json") if f.is_file()])
        hs = hours_since((state.get("last_sediment_at") or {}).get(ns))
        hval = hs if hs is not None else float("inf")    # 从未沉淀 → 视为远超阈值
        hout = round(hs, 1) if hs is not None else None  # 对外输出 null，不暴露内部哨兵
        offpeak = not peak

        sup = suppression_for(ns)
        if sup and not sup.get("expired"):
            # 会话级覆盖生效：本 ns 不产生动作信号，但必须留痕（用户要看得见"为什么不沉淀"）
            signals.append({"signal": "suppressed", "ns": ns, "pending": n,
                            "hours_since_last": hout, "until": sup.get("until"),
                            "reason": sup.get("reason")})
            suppressed.append({"ns": ns, "pending": n, "until": sup.get("until"),
                               "reason": sup.get("reason")})
            continue

        if n >= 7 and hval >= 48 and offpeak:
            signals.append({"signal": "sediment", "ns": ns, "pending": n,
                            "hours_since_last": hout, "offpeak": True})
        elif n >= 10 and hval >= 72 and (reminded_ago is None or reminded_ago >= 24):
            signals.append({"signal": "remind", "ns": ns, "pending": n,
                            "hours_since_last": hout})
        if sup and sup.get("expired"):
            signals.append({"signal": "override-expired", "ns": ns,
                            "until": sup.get("until"), "reason": sup.get("reason")})

    # 单一写入者：仅本脚本（沉淀流程成员）写 state；remind 发出即记录防抖时间
    if signals and any(s["signal"] == "remind" for s in signals) and not args.no_persist:
        state["last_remind_at"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        try:
            save_state(resolve_state_dir(cli=args.state_dir), state)
        except Exception as e:
            fail(1, "last_remind_at 写回失败: %s" % e)

    # 只有 sediment/remind 参与顶层 signal 判定；suppressed / override-expired 是留痕项，
    # 不得被当作"命中"（否则用户设了抑制却仍看到 sediment 信号，抑制形同虚设）
    actionable = [s for s in signals if s["signal"] in ("sediment", "remind")]
    actionable.sort(key=lambda s: 0 if s["signal"] == "sediment" else 1)
    top = actionable[0]["signal"] if actionable else "none"
    out_json({"signal": top, "signals": signals, "suppressed": suppressed,
              "budget": state.get("budget")})


if __name__ == "__main__":
    main()
