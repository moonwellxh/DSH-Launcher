# -*- coding: utf-8 -*-
# =====================================================================
# sediment_run.py —— 沉淀执行器（FR-24/26，分阶段、幂等、断点续）
# 用法:
#   python3 sediment_run.py --ns <ns>                         # 产出 S1 候选后停在 S2 前（await_edits）
#   python3 sediment_run.py --ns <ns> --resume iter-<N> --guide-edits <裁决文件.json>   # 续跑 S2→S6
#   python3 sediment_run.py --ns <ns> --until S1              # 测试/演练：跑到指定阶段停
# 裁决文件格式: {"add":[{"ns":"document","line":"- [D-003] …"}],
#               "demote":["D-001"],"retire":["D-002"]}
# 阶段: S0备份 → S1聚合 → S2导引单回写(需裁决) → S3脚本泛化 → S4价格核对 → S5 ROI审计 → S6收尾迁移
# 每阶段完成写 var/sediment/iter-<N>.checkpoint；重跑同 iter 幂等（不重复条款/日志）。
# 退出码: 0 成功(含 await_edits) / 2 预算耗尽或裁决文件非法 / 1 其他错误
# =====================================================================
import argparse, json, os, re, sys, shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_BJ = timezone(timedelta(hours=8))
_NS = ("general", "document", "code", "regulation")
_PHASES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
_NS_PREFIX = {"general": "G", "document": "D", "code": "C", "regulation": "R"}
_NS_HEADING = {"general": "## 通用条款", "document": "### 文档类",
               "code": "### 代码类", "regulation": "### 规范类"}
_CLAUSE_RE = re.compile(r"^\s*-\s*\[([A-Z])-(\d{3})\]\s*(.*)$")
# monthly_left_cny=None 表示月度余额控制暂不启用（所有者裁决 2026-09-06，F15）；
# 填入数值即恢复启用（建议 2.0，见设计稿 FR-27）。单次限额不受此开关影响。
_BUDGET_DEFAULT = {"single_run_max_cny": 0.5, "monthly_left_cny": None,
                   "single_input_tok_max": 120000, "single_output_tok_max": 20000}


def beijing_now():
    return datetime.now(_BJ)


def iso(dt=None):
    dt = dt or beijing_now()
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def parse_dt(s):
    if not s:
        return None
    try:
        v = datetime.fromisoformat(str(s))
        return v if v.tzinfo else v.replace(tzinfo=_BJ)
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


def load_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(p, obj):
    p = Path(p)
    ensure_dir(p.parent)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_state(state):
    p = state / "state.json"
    if p.exists():
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(s, dict):
                raise ValueError("顶层非 JSON 对象")
        except Exception as e:
            # 与 sediment_check 一致：损坏的 state.json 必须显式失败；静默回退默认会重置 iter_seq 引发迭代号冲突
            fail(1, "state.json 读取失败: %s" % e, "损坏的 state.json 需人工检查（单一写入者：仅沉淀流程可写）")
    else:
        s = {}
    s.setdefault("last_sediment_at", {})
    s.setdefault("budget", dict(_BUDGET_DEFAULT))
    s.setdefault("last_remind_at", None)
    s.setdefault("pricing_checked_at", None)
    s.setdefault("iter_seq", 0)
    return s


def save_state(state, obj):
    save_json(state / "state.json", obj)


def read_pricing(root):
    txt = (root / "references" / "pricing-models.md").read_text(encoding="utf-8")
    m = re.search(r"```json\s*\n(.*?)\n```", txt, re.S)
    if not m:
        fail(1, "pricing JSON 块缺失", "references/pricing-models.md 需含唯一 ```json 块")
    return json.loads(m.group(1))


def guide_paths(root, ns):
    return {"pregen": root / "references" / "pregen-guide.md",
            "ns": root / "references" / "namespaces" / ("%s.md" % ns),
            "pricing": root / "references" / "pricing-models.md"}


# ---------------- 阶段实现 ----------------

def phase_S0(c, state):
    """S0 备份：本次将改动的文件 → var/backup/iter-<N>/（回滚点）。"""
    bdir = ensure_dir(state / "backup" / ("iter-%d" % c.N))
    copied, skipped = [], []
    for key, p in guide_paths(c.src_root, c.ns).items():
        if p.exists():
            dst = bdir / p.relative_to(c.src_root)
            ensure_dir(dst.parent)
            shutil.copy2(p, dst)
            copied.append(str(dst))
        else:
            skipped.append(str(p))
    reg = state / "registry" / "scripts.json"
    if reg.exists():
        dst = bdir / "registry" / "scripts.json"
        ensure_dir(dst.parent)
        shutil.copy2(reg, dst)
        copied.append(str(dst))
    return {"copied": copied, "skipped": [str(x) for x in skipped]}


def phase_S1(c, state):
    """S1 聚合：读 pending/<ns>/*.json → 频次/命中/误报统计，产出 S2 候选源。"""
    pend = state / "snapshots" / "pending" / c.ns
    files = sorted(pend.glob("*.json")) if pend.exists() else []
    if c.window and len(files) > c.window:
        # 设计 5.4“近 K 次快照”：聚合只取最近 window 条（快照 id 以时间戳开头，文件名字典序≈时间序）
        files = files[-c.window:]
    agg = {"ns": c.ns, "runs": 0, "severity": {}, "types": {}, "issues_total": 0,
           "false_positives": 0, "reopen_total": 0, "outcomes": {},
           "tokens_in": 0, "tokens_out": 0, "cache_hit": 0, "clause_hits": {},
           "corrupt": [], "snapshots": []}
    for f in files:
        snap = load_json(f)
        if not snap:
            agg["corrupt"].append(f.name)
            continue
        agg["runs"] += 1
        agg["outcomes"][snap.get("outcome") or "?"] = agg["outcomes"].get(snap.get("outcome") or "?", 0) + 1
        agg["snapshots"].append(f.stem)
        for tok in snap.get("tokens") or []:
            agg["tokens_in"] += tok.get("input") or 0
            agg["tokens_out"] += tok.get("output") or 0
            agg["cache_hit"] += tok.get("cache_hit") or 0
        for it in snap.get("issues") or []:
            agg["issues_total"] += 1
            sev = it.get("severity") or "?"
            agg["severity"][sev] = agg["severity"].get(sev, 0) + 1
            typ = it.get("type") or "?"
            agg["types"][typ] = agg["types"].get(typ, 0) + 1
            if it.get("false_positive"):
                agg["false_positives"] += 1
            agg["reopen_total"] += it.get("reopen_count") or 0
            for m in re.finditer(r"\[([A-Z])-(\d{3})\]", str(it.get("basis") or "")):
                key = "%s-%s" % (m.group(1), m.group(2))
                agg["clause_hits"][key] = agg["clause_hits"].get(key, 0) + 1
    save_json(state / "sediment" / ("iter-%d-S1.json" % c.N), agg)
    return agg


def _split_blocks(lines):
    """按标题把 pregen-guide.md 切成块；返回 [(heading或None, [lines…])]。"""
    blocks, cur = [], []
    for ln in lines:
        if ln.startswith("#"):
            if cur is not None:
                blocks.append(cur)
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        blocks.append(cur)
    return blocks


def _block_index(blocks, heading):
    for i, b in enumerate(blocks):
        if b and b[0].strip().startswith(heading):
            return i
    return None


def apply_guide_edits(c, state, edits):
    """按裁决文件改写 pregen-guide.md（幂等：条款按 ID upsert）。"""
    gp = guide_paths(c.src_root, c.ns)
    p = gp["pregen"]
    if not p.exists():
        fail(2, "pregen-guide.md 缺失: %s" % p)
    lines = p.read_text(encoding="utf-8").splitlines()
    blocks = _split_blocks(lines)

    def find_clause_line(blk_lines, cid):
        for idx, ln in enumerate(blk_lines):
            m = _CLAUSE_RE.match(ln)
            if m and "%s-%s" % (m.group(1), m.group(2)) == cid:
                return idx
        return None

    result = {"add": [], "demote": [], "retire": [], "merge": [], "skipped": []}
    # 删除/降权/新增按顺序处理（先删后移再插，避免行号漂移）
    actions = []
    for cid in edits.get("retire") or []:
        actions.append(("retire", cid, None))
    for cid in edits.get("demote") or []:
        actions.append(("demote", cid, None))
    for item in edits.get("add") or []:
        actions.append(("add", None, item))

    for kind, cid, item in actions:
        if kind == "add":
            line = (item or {}).get("line")
            ans = (item or {}).get("ns") or c.ns
            if ans not in _NS:
                result["skipped"].append("add: 未知 ns=%s" % ans)
                continue
            if not line:
                result["skipped"].append("add: line 为空")
                continue
            m = _CLAUSE_RE.match(line)
            if not m:
                result["skipped"].append("add: 行格式非法（需 - [X-###] 开头）: %s" % line)
                continue
            key = "%s-%s" % (m.group(1), m.group(2))
            heading = _NS_HEADING[ans]
            # 幂等：已有同 ID → 替换
            replaced = False
            for b in blocks:
                idx = find_clause_line(b, key)
                if idx is not None:
                    b[idx] = line.rstrip("\n")
                    replaced = True
                    break
            if not replaced:
                bi = _block_index(blocks, heading)
                if bi is not None:
                    insert_at = len(blocks[bi])  # 块尾（下一标题前）
                    # 若块尾存在空行则插到空行前
                    while insert_at > 1 and blocks[bi][insert_at - 1].strip() == "":
                        insert_at -= 1
                    blocks[bi].insert(insert_at, line)
                else:
                    # 目标小节缺失 → 追加到文件尾
                    blocks.append([heading, line])
                    result["skipped"].append("add %s: 未找到小节 %s，已追加到文件尾" % (key, heading))
            result["add"].append(key)
        else:
            key = cid
            target_block = None
            idx_in_block = -1
            for b in blocks:
                idx = find_clause_line(b, key)
                if idx is not None:
                    target_block, idx_in_block = b, idx
                    break
            if target_block is None:
                result["skipped"].append("%s %s: 导引单中无此条款" % (kind, key))
                continue
            if kind == "retire":
                target_block.pop(idx_in_block)
                result["retire"].append(key)
            else:  # demote: 移到所在块末尾（权重下沉）；保留原有块尾空行，避免与下一标题粘连
                ln = target_block.pop(idx_in_block)
                had_blank_tail = False
                while target_block and target_block[-1].strip() == "":
                    target_block.pop()
                    had_blank_tail = True
                target_block.append(ln)
                if had_blank_tail:
                    target_block.append("")
                result["demote"].append(key)
    new_text = "\n".join("\n".join(b) for b in blocks) + "\n"
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, p)  # 与包内其他落盘一致：原子写，防中断留下半成品导引单
    return result


def _build_candidates(c, agg):
    """由 S1 聚合生成 S2 候选清单（新增/降权候选；精确语义由 agent 裁决）。"""
    candidates = []
    if not agg:
        return candidates
    prefix = _NS_PREFIX[c.ns]
    for typ, cnt in sorted(agg.get("types", {}).items(), key=lambda kv: -kv[1]):
        if cnt < c.new_threshold:
            continue
        candidates.append({"kind": "new-clause-candidate", "ns": c.ns,
                           "defect_type": typ, "count": cnt,
                           "note": "近窗口出现≥%d 次，请裁决是否新增导引单条款（agent 撰写文本，格式 - [%s-###] …）"
                                   % (c.new_threshold, prefix)})
    # 降权候选（设计 5.4）：以导引单现存条款为全集，本窗口零命中者才候选——
    # clause_hits 只含命中 ≥1 次的条款，直接查 v==0 是永不成立的死分支，必须回读导引单取零命中集。
    # 另需窗口内有 ≥1 条 issue 作为证据基础：整窗零 issue 说明无任何缺陷信号，
    # 此时“零命中”不代表条款失效（可能恰是导引生效），全量误报降权只会制造噪声。
    hits = agg.get("clause_hits", {})
    if agg.get("issues_total", 0) >= 1:
        guide = guide_paths(c.src_root, c.ns)["pregen"]
        if guide.exists():
            for ln in guide.read_text(encoding="utf-8").splitlines():
                m = _CLAUSE_RE.match(ln)
                if not m:
                    continue
                cid = "%s-%s" % (m.group(1), m.group(2))
                if cid.startswith(prefix) and not hits.get(cid):
                    candidates.append({"kind": "demote-candidate", "clause": cid,
                                       "note": "本窗口零命中，建议降权/淘汰（agent 裁决）"})
    return candidates


def phase_S2(c, state, agg, edits):
    """S2 导引单回写：产出候选清单；有裁决文件才落盘改动。"""
    # 续跑（resume）时 S1 已在前次执行，聚合从落盘文件恢复，避免空数据覆盖候选
    if not agg.get("issues_total") and (state / "sediment" / ("iter-%d-S1.json" % c.N)).exists():
        agg = load_json(state / "sediment" / ("iter-%d-S1.json" % c.N), {}) or {}
    cand_file = state / "sediment" / ("iter-%d-candidates.json" % c.N)
    candidates = _build_candidates(c, agg)
    save_json(cand_file, {"iter": c.N, "ns": c.ns, "window_snapshots": len(agg.get("snapshots", [])),
                          "candidates": candidates})

    if edits is None:
        # 无裁决 → 停在 S2 前，等待 agent 撰写并续跑
        return {"applied": False, "await_edits": True, "candidates_file": str(cand_file),
                "candidates": candidates}
    applied = apply_guide_edits(c, state, edits)
    return {"applied": True, "await_edits": False, "candidates_file": str(cand_file),
            "candidates": candidates, "actions": applied}


def phase_S3(c, state):
    """S3 脚本泛化：queue/ 候选脚本回归通过才进注册表（FR-19）。"""
    qdir = ensure_dir(state / "queue" / "candidates")
    done = ensure_dir(state / "queue" / "done")
    failed = ensure_dir(state / "queue" / "failed")
    reg_file = state / "registry" / "scripts.json"
    reg = load_json(reg_file, {"scripts": []}) or {"scripts": []}
    promoted, rejected = [], []
    for f in sorted(qdir.glob("*.json")):
        cand = load_json(f)
        if not cand or not cand.get("name"):
            continue
        regres = cand.get("regression") or {}
        rec = {"name": cand["name"], "ns": cand.get("ns", c.ns),
               "version": cand.get("version", "0.1"), "hits": 0, "false_positives": 0,
               "registered_at": iso()}
        if regres.get("passed"):
            reg["scripts"].append(rec)
            save_json(reg_file, reg)
            shutil.move(str(f), str(done / f.name))
            promoted.append(rec["name"])
        else:
            shutil.move(str(f), str(failed / f.name))
            rejected.append(cand["name"])
    return {"promoted": promoted, "rejected": rejected, "registered_total": len(reg["scripts"])}


def phase_S4(c, state):
    """S4 价格表核对：>30 天且有官方源才提示更新；脚本不擅自落盘外部数据。"""
    try:
        pricing = read_pricing(c.src_root)
    except Exception as e:
        return {"status": "error", "note": "读取失败: %s" % e}
    updated = parse_dt(pricing.get("updated_at"))
    days = (c.now - updated).days if updated else None
    urls = [u for u in re.split(r"[,;\s]+", os.environ.get("ADV_REVIEW_PRICE_URLS", "").strip()) if u]
    out = {"status": "fresh", "updated_at": pricing.get("updated_at"), "days_since": days}
    if days is None or days <= 30:
        return out
    out["status"] = "due"
    if not urls:
        out["note"] = "已超 30 天且未配置 ADV_REVIEW_PRICE_URLS；请 agent 人工核对官方定价后更新 pricing-models.md 的 updated_at"
    else:
        import urllib.request
        fetched = None
        for u in urls:
            try:
                with urllib.request.urlopen(u, timeout=10) as resp:
                    raw = resp.read(200000)
                try:
                    fetched = {"url": u, "parsed": json.loads(raw.decode("utf-8", errors="replace"))}
                    break
                except Exception:
                    continue
            except Exception:
                continue
        if fetched:
            save_json(state / "sediment" / ("iter-%d-price-candidate.json" % c.N), fetched)
            out["note"] = "取到候选数据见 iter-%d-price-candidate.json，请 agent 核对后人工更新价格表" % c.N
        else:
            out["note"] = "未取得可解析价格数据；请 agent 人工核对（S4 已记 pricing_checked_at，避免每轮重试）"
    st = load_state(state)
    st["pricing_checked_at"] = iso(c.now)
    save_state(state, st)
    return out


def phase_S5(c, state):
    """S5 ROI 审计：按 metrics.jsonl 算各轮费用代理指标，产出降权/退役与预算建议。"""
    mfile = state / "metrics.jsonl"
    rows = []
    if mfile.exists():
        for ln in mfile.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    stats = {"rows": len(rows), "by_ns": {}, "output_tokens_sum": 0, "runs_closed": 0}
    per_run_cost = []
    for r in rows:
        ns = r.get("ns", "?")
        d = stats["by_ns"].setdefault(ns, {"runs": 0, "output": 0, "closed": 0})
        d["runs"] += 1
        d["output"] += r.get("output_tokens") or 0
        d["closed"] += 1 if r.get("outcome") in ("passed", "converged", "fused") else 0
        stats["output_tokens_sum"] += r.get("output_tokens") or 0
        if r.get("cost_cny") is not None:
            per_run_cost.append(r["cost_cny"])
    suggestions = []
    if len(per_run_cost) >= 5:
        p80 = sorted(per_run_cost)[int(len(per_run_cost) * 0.8) - 1]
        suggestions.append({"kind": "budget-adjust", "note": "累计≥5 次，P80×1.2=%s；请 agent 按预算自调整规则更新 state.budget 并记 changelog" % round(p80 * 1.2, 3)})
    if not rows:
        suggestions.append({"kind": "no-history", "note": "metrics.jsonl 无历史，暂不给出 ROI 结论"})
    save_json(state / "sediment" / ("iter-%d-roi.json" % c.N),
              {"iter": c.N, "ns": c.ns, "stats": stats, "suggestions": suggestions})
    return {"stats": stats, "suggestions": suggestions}


def phase_S6(c, state, results):
    """S6 收尾：pending→settled 迁移；changelog.md 追加；state.json 更新。"""
    pend = state / "snapshots" / "pending" / c.ns
    setl = ensure_dir(state / "snapshots" / "settled" / c.ns)
    moved, skipped = [], []
    if pend.exists():
        for f in sorted(pend.glob("*.json")):
            dst = setl / f.name
            if dst.exists() and dst.read_bytes() == f.read_bytes():
                # 内容一致才视为重复迁移（仅比 size 会误丢同尺寸异内容的快照）；文件 ≤10KB，比对代价可忽略
                f.unlink()
                skipped.append(f.name)
                continue
            shutil.move(str(f), str(dst))
            moved.append(f.name)

    bullets = []
    s1 = results.get("S1") or {}
    bullets.append("快照：处理 %d 条（runs=%d, issues=%d, 误报=%d, 重开=%d）"
                   % (len(moved) + len(skipped), s1.get("runs", 0), s1.get("issues_total", 0),
                      s1.get("false_positives", 0), s1.get("reopen_total", 0)))
    s2 = results.get("S2") or {}
    if s2.get("applied"):
        ac = s2.get("actions") or {}
        parts = []
        if ac.get("add"):
            parts.append("新增 %s" % ", ".join(ac["add"]))
        if ac.get("demote"):
            parts.append("降权 %s" % ", ".join(ac["demote"]))
        if ac.get("retire"):
            parts.append("淘汰 %s" % ", ".join(ac["retire"]))
        bullets.append("导引单：%s" % ("；".join(parts) if parts else "无改动（裁决未含变更）"))
    else:
        bullets.append("导引单：未改动（候选见 iter-%d-candidates.json）" % c.N)
    s3 = results.get("S3") or {}
    if s3.get("promoted"):
        bullets.append("脚本：%s 泛化晋升，回归通过" % ", ".join(s3["promoted"]))
    else:
        bullets.append("脚本：无晋升")
    s4 = results.get("S4") or {}
    if s4.get("status") == "fresh":
        bullets.append("价格表：未变（数据日期 %s）" % s4.get("updated_at"))
    else:
        bullets.append("价格表：%s（%s）" % (s4.get("status"), (s4.get("note") or "需人工核对")))
    s5 = results.get("S5") or {}
    if s5.get("suggestions"):
        bullets.append("ROI 建议：%s" % "；".join(x.get("note") for x in s5["suggestions"]))
    else:
        bullets.append("ROI：无建议")
    bdir = state / "backup" / ("iter-%d" % c.N)
    bullets.append("回滚点：%s" % bdir)

    changelog = state / "changelog.md"
    entry = "\n## iter-%d · %s · 触发:%s · ns:%s\n" % (c.N, iso(c.now), c.trigger, c.ns)
    entry += "\n".join("- %s" % b for b in bullets) + "\n"
    prev = changelog.read_text(encoding="utf-8") if changelog.exists() else "# 修订日志（changelog.md）\n"
    if ("## iter-%d " % c.N) not in prev:
        changelog.write_text(prev.rstrip("\n") + "\n" + entry, encoding="utf-8")

    st = load_state(state)
    st["last_sediment_at"][c.ns] = iso(c.now)
    # 单调递增：resume 旧迭代补跑 S6 时不得回退计数器，否则后续迭代号冲突
    st["iter_seq"] = max(int(st.get("iter_seq") or 0), c.N)
    save_state(state, st)
    return {"moved": moved, "skipped_migrate": skipped, "changelog": str(changelog)}


def main():
    ap = argparse.ArgumentParser(description="沉淀执行器（S0→S6，幂等断点续）")
    ap.add_argument("--ns", required=True, choices=list(_NS))
    ap.add_argument("--resume", default=None, help="iter-N：从该迭代 checkpoint 续跑")
    ap.add_argument("--guide-edits", default=None, help="agent 裁决文件 JSON 路径")
    ap.add_argument("--until", default=None, choices=_PHASES, help="测试/演练：跑到该阶段停")
    ap.add_argument("--now", default=None, help="ISO8601 时间（测试用）")
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--skill-root", default=None, help="技能根覆盖（测试/隔离用；默认=脚本上级）")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--new-threshold", type=int, default=3)
    ap.add_argument("--trigger", default="静默", choices=["静默", "提醒", "显式"])
    args = ap.parse_args()

    c = argparse.Namespace(ns=args.ns, now=parse_dt(args.now) or beijing_now(),
                           trigger=args.trigger, window=args.window,
                           new_threshold=args.new_threshold,
                           src_root=Path(args.skill_root).resolve() if args.skill_root else skill_root(),
                           N=None)
    state = resolve_state_dir(cli=args.state_dir)

    # 预算闸（FR-27/设计 6.4）：月度余量 ≤0 → 拒绝启动（退出码 2 预算耗尽）
    st = load_state(state)
    monthly = (st.get("budget") or {}).get("monthly_left_cny")
    if monthly is not None and float(monthly) <= 0:
        fail(2, "预算耗尽中断", "state.budget.monthly_left_cny<=0；请用户裁决追加或下月再沉淀")

    # 迭代号：--resume 优先；否则 state.iter_seq+1
    if args.resume:
        m = re.match(r"iter-(\d+)$", args.resume or "")
        if not m:
            fail(2, "--resume 格式非法", "应为 iter-<N>")
        c.N = int(m.group(1))
    else:
        c.N = int((st.get("iter_seq") or 0)) + 1

    sed_dir = ensure_dir(state / "sediment")
    ckpt_file = sed_dir / ("iter-%d.checkpoint" % c.N)
    ckpt = load_json(ckpt_file, {"phases_done": []}) or {"phases_done": []}
    done = set(ckpt.get("phases_done") or [])

    # 保证骨架目录存在
    for sub in ("snapshots/pending", "snapshots/settled", "backup", "queue/candidates", "registry"):
        ensure_dir(state / sub)
    ensure_dir(state / "snapshots" / "pending" / c.ns)
    ensure_dir(state / "snapshots" / "settled" / c.ns)

    edits = None
    if args.guide_edits:
        edits = load_json(Path(args.guide_edits))
        if edits is None:
            fail(2, "裁决文件不可读/非法: %s" % args.guide_edits)

    results = {}
    ran = []
    for ph in _PHASES:
        if ph in done:
            continue
        if ph == "S2" and edits is None:
            # 停在 S2 前等裁决（S0/S1 已落盘 checkpoint，resume 续跑）
            if args.until and _PHASES.index(args.until) >= _PHASES.index("S2"):
                pass  # --until S2 也属“等待”边界
            break
        if args.until and _PHASES.index(ph) > _PHASES.index(args.until):
            break
        if ph == "S0":
            r = phase_S0(c, state)
        elif ph == "S1":
            r = phase_S1(c, state)
        elif ph == "S2":
            r = phase_S2(c, state, results.get("S1") or {}, edits)
        elif ph == "S3":
            r = phase_S3(c, state)
        elif ph == "S4":
            r = phase_S4(c, state)
        elif ph == "S5":
            r = phase_S5(c, state)
        else:
            r = phase_S6(c, state, results)
        results[ph] = r
        done.add(ph)
        ran.append(ph)
        save_json(ckpt_file, {"iter": c.N, "ns": c.ns, "phases_done": sorted(done),
                              "updated_at": iso(c.now)})

    # 汇总
    await_edits = "S2" not in done and "S0" in done and (edits is None)
    final = {"status": "await_edits" if await_edits else "done",
             "iter": "iter-%d" % c.N, "ns": c.ns, "phases_run": ran,
             "phases_done": sorted(done), "checkpoint": str(ckpt_file)}
    if await_edits:
        s1 = results.get("S1") or {}
        if not s1.get("issues_total"):
            s1 = load_json(sed_dir / ("iter-%d-S1.json" % c.N), {}) or {}
        # 停等时即产出候选清单（S2 未执行，故由主流程补齐），供 agent 裁决后 resume
        cand_file = sed_dir / ("iter-%d-candidates.json" % c.N)
        if not cand_file.exists():
            save_json(cand_file, {"iter": c.N, "ns": c.ns,
                                  "window_snapshots": len(s1.get("snapshots", [])),
                                  "candidates": _build_candidates(c, s1)})
        cand = load_json(cand_file, {"candidates": []}) or {}
        final["message"] = ("已产出聚合与候选清单。请撰写新条款文本（格式 - [%s-###] …）后执行: "
                            "sediment_run.py --ns %s --resume iter-%d --guide-edits <裁决文件>" % (_NS_PREFIX[c.ns], c.ns, c.N))
        final["stats"] = {"runs": s1.get("runs", 0), "issues_total": s1.get("issues_total", 0)}
        final["candidates"] = cand.get("candidates", [])
    else:
        s6 = results.get("S6") or {}
        if s6:
            final["moved_to_settled"] = s6.get("moved", [])
            final["changelog"] = str(s6.get("changelog", ""))
        else:
            final["message"] = "无新阶段执行（该迭代已全部完成或仅查询）"
    out_json(final)


if __name__ == "__main__":
    main()
