# -*- coding: utf-8 -*-
# =====================================================================
# sediment_check.py —— 沉淀/提醒信号判断（FR-24/25，纯确定性，零模型成本）
# 用法: python3 sediment_check.py [--now ISO] [--state-dir DIR] [--ns NS] [--no-persist]
# 输出: 单行 JSON:
#   {"signal": "sediment|remind|none",
#    "signals": [{"signal":"sediment","ns":..,"pending":n,"hours_since_last":h,"offpeak":bool}, ...],
#    "budget": {...}}
#   signal=多命名空间同时命中时的最高优先级（sediment > remind > none），逐条处理见 signals。
# 退出码: 0 判定完成（信号含 none 亦为成功）/ 1 state.json 或价格表损坏等异常（按失败协议如实上报，不得静默）
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
        if n >= 7 and hval >= 48 and offpeak:
            signals.append({"signal": "sediment", "ns": ns, "pending": n,
                            "hours_since_last": hout, "offpeak": True})
        elif n >= 10 and hval >= 72 and (reminded_ago is None or reminded_ago >= 24):
            signals.append({"signal": "remind", "ns": ns, "pending": n,
                            "hours_since_last": hout})

    # 单一写入者：仅本脚本（沉淀流程成员）写 state；remind 发出即记录防抖时间
    if signals and any(s["signal"] == "remind" for s in signals) and not args.no_persist:
        state["last_remind_at"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        try:
            save_state(resolve_state_dir(cli=args.state_dir), state)
        except Exception as e:
            fail(1, "last_remind_at 写回失败: %s" % e)

    signals.sort(key=lambda s: 0 if s["signal"] == "sediment" else 1)
    top = signals[0]["signal"] if signals else "none"
    out_json({"signal": top, "signals": signals, "budget": state.get("budget")})


if __name__ == "__main__":
    main()
