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

# ---- 导引单条款生命周期与反自我强化（M1~M7，owner 裁决 2026-09-10）----
# M4 条款数上限由 600 token 注入预算反推：guide_inject.est_tokens 实测
#   审查预告 + 通用 10 条 + 命名空间 4 条 ≈ 493 token < 600，留出安全余量。
CLAUSE_CAP = {"general": 10, "per_ns": 4}
TRIAL_WINDOWS_REQUIRED = 2   # M1：新条款 trial 态需观察的沉淀窗口数，达标才升 active
ZERO_EVIDENCE_DEMOTE = 2     # M7：连续零证据窗口 → 降权（移到块尾）
ZERO_EVIDENCE_RETIRE = 4     # M7：连续零证据窗口 → 淘汰
LIFECYCLE_NAME = "guide-clauses.json"   # 落 <state>/registry/ 下；注入端不读它（零成本）
# M6：不可证伪措辞黑名单（确定性拒绝）——这类条款无法被任何证据否定，进导引单即噪声
_UNFALSIFIABLE = ("认真", "重视", "尽量", "尽可能", "严格", "加强", "提高意识")
# M6：可检验对象的存在性启发式（缺失只告警不拒绝——启发式不做硬门，避免误杀）
_CHECKABLE_RE = re.compile(
    r"[0-9]|[条款章节图表号]|单位|边界|来源|位置|字段|数值|编号|引用|定义|公式|阈值|接口|参数|目录|文件名")
# M3：判定"实际返工"的事件/状态集合
_FIX_EVENTS = {"fix_start", "fix_submit", "verify_pass", "verify_fail", "regression_fail"}
_FIX_STATUS = {"修复中", "待验证", "已关闭"}


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


def guide_clause_ids(path):
    """读导引单，返回 [(block_kind, clause_id, line)]，block_kind ∈ general|<ns>。

    block_kind 由所在标题决定（不靠条款前缀猜），使上限校验按真实块归属计数。
    """
    if not Path(path).exists():
        return []
    out = []
    kind = None
    for ln in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if ln.startswith("#"):
            if ln.startswith("## 通用条款"):
                kind = "general"
            elif ln.startswith("### "):
                kind = ln[4:].strip()          # 规范类/文档类/代码类
            else:
                kind = None
            continue
        m = _CLAUSE_RE.match(ln)
        if m and kind:
            out.append((kind, "%s-%s" % (m.group(1), m.group(2)), ln))
    return out


def lifecycle_file(state):
    return state / "registry" / LIFECYCLE_NAME


def load_lifecycle(state):
    """读条款生命周期 sidecar；不存在则返回空骨架（= 向后兼容，行为与旧版一致）。"""
    obj = load_json(lifecycle_file(state), None)
    if obj is None:
        return {"updated_at": None, "clauses": []}
    if not isinstance(obj, dict) or not isinstance(obj.get("clauses"), list):
        fail(1, "guide-clauses.json 结构非法", "应为 {\"clauses\": [...]}；需人工检查")
    return obj


def save_lifecycle(state, obj):
    obj["updated_at"] = iso()
    save_json(lifecycle_file(state), obj)


def sync_lifecycle(c, state):
    """M1/M7：把 sidecar 与导引单现状对齐，并推进 trial 观察窗口。

    - 导引单中已存在但 sidecar 无记录的条款 → 补录（既有条款视为 active：祖父条款），
      新增条款由 apply_guide_edits 显式写入 state=trial，二者不会混淆。
    - sidecar 有记录但导引单已无该条款 → 删除记录（已淘汰/手工删除）。
    - trial 条款：windows_observed+1；达 TRIAL_WINDOWS_REQUIRED 且有效证据成立 → active；
      否则 → 提出 retire 建议（不自动删文本——文本改动一律由 agent 裁决后经 --guide-edits 落盘）。
    - active 条款：连续零证据窗口达 ZERO_EVIDENCE_DEMOTE / RETIRE → 出建议。
    每窗口只推进一次（以 last_counted_iter 去重，防 resume 重复计数）。
    """
    lc = load_lifecycle(state)
    by_id = {x.get("id"): x for x in lc["clauses"] if isinstance(x, dict) and x.get("id")}
    present = {cid: kind for kind, cid, _ in guide_clause_ids(guide_paths(c.src_root, c.ns)["pregen"])}

    added_entries, removed = [], []
    for cid, kind in present.items():
        if cid not in by_id:
            e = {"id": cid, "block": kind, "state": "active", "added_iter": None,
                 "basis": [], "windows_observed": 0, "zero_evidence_windows": 0,
                 "last_counted_iter": None, "evidence": {"hits": 0}}
            lc["clauses"].append(e)
            by_id[cid] = e
            added_entries.append(cid)
    for cid in list(by_id):
        if cid not in present:
            lc["clauses"] = [x for x in lc["clauses"] if x.get("id") != cid]
            by_id.pop(cid, None)
            removed.append(cid)

    agg = load_json(state / "sediment" / ("iter-%d-S1.json" % c.N), {}) or {}
    hits = agg.get("clause_hits") or {}
    promote, trial_expired, demote_sug, retire_sug = [], [], [], []
    for e in lc["clauses"]:
        if not isinstance(e, dict):
            continue
        if e.get("last_counted_iter") == c.N:
            continue                      # 同一迭代重复进入（resume）不重复计数
        e["last_counted_iter"] = c.N
        cid = e.get("id")
        h = int(hits.get(cid) or 0)
        e.setdefault("evidence", {})["hits"] = h
        # M2：命中率**不作存废判据**，此处只作"参与度信号"——是否有人在审查中引用过它。
        # 计零证据窗口的语义：本窗口既无引用（hits=0）又无绑定证据（basis 空）→ 该条款
        # 在本窗口没产生任何可观测作用，窗口 +1。反过来说，**条款被遵守会表现为零命中**
        # （没人违反它 → 没人引用它），单凭零命中判失效是反向误杀；只有"长期既无引用又无
        # 绑定证据"才累计到降权/淘汰建议。注意：hits 不能用于"升格"（trial→active 只认 basis），
        # 因此它无法把条款"证明成有效"，自我强化被限制在"最多避免被淘汰"这一上界内。
        has_basis = bool(e.get("basis"))
        e["windows_observed"] = int(e.get("windows_observed") or 0) + 1
        if has_basis or h > 0:
            e["zero_evidence_windows"] = 0
        else:
            e["zero_evidence_windows"] = int(e.get("zero_evidence_windows") or 0) + 1

        if e.get("state") == "trial":
            if e["windows_observed"] >= TRIAL_WINDOWS_REQUIRED and has_basis:
                e["state"] = "active"
                promote.append(cid)
            elif e["windows_observed"] >= TRIAL_WINDOWS_REQUIRED:
                trial_expired.append(cid)   # 试用到期无正面证据 → 建议淘汰（保守）
        elif e.get("state") == "active":
            z = e["zero_evidence_windows"]
            if z >= ZERO_EVIDENCE_RETIRE:
                retire_sug.append(cid)
            elif z >= ZERO_EVIDENCE_DEMOTE:
                demote_sug.append(cid)

    save_lifecycle(state, lc)
    return {"clauses": len(lc["clauses"]), "registered": added_entries, "dropped_entries": removed,
            "promoted": promote, "trial_expired": trial_expired,
            "demote_suggest": demote_sug, "retire_suggest": retire_sug}


def ledger_fix_types(state):
    """M3：扫 var/ledger/*.json，返回 (曾实际进入修复流程的类型集合, {类型: [issue_id,…]})。

    "实际进入修复流程" = 状态 ∈ _FIX_STATUS 或 history 中出现 _FIX_EVENTS 事件。
    仅统计"曾提出"不够——提议会被驳回，只有真的动手修过的类型才算有返工成本证据。
    """
    types, ids = set(), {}
    ldir = state / "ledger"
    if not ldir.exists():
        return types, ids
    for f in sorted(ldir.glob("*.json")):
        obj = load_json(f)
        if not isinstance(obj, dict):
            continue
        for it in obj.get("issues") or []:
            if not isinstance(it, dict):
                continue
            evs = {h.get("event") for h in (it.get("history") or []) if isinstance(h, dict)}
            if it.get("status") in _FIX_STATUS or (evs & _FIX_EVENTS):
                t = it.get("type") or "?"
                types.add(t)
                ids.setdefault(t, []).append(it.get("id"))
    return types, ids


def dropped_clause_ids(state, ns, window):
    """M5：汇总近 window 条 pending 快照中被预算截断的条款 ID。

    这些条款**根本没被注入**，其"零命中"是结构性的、不是有效性证据；
    若不排除，沉淀端会把从未生效的条款当"无效条款"淘汰——观测污染。
    """
    dropped = set()
    pend = state / "snapshots" / "pending" / ns
    files = sorted(pend.glob("*.json")) if pend.exists() else []
    if window and len(files) > window:
        files = files[-window:]
    for f in files:
        snap = load_json(f)
        if not isinstance(snap, dict):
            continue
        for cid in (snap.get("guide_dropped") or []):
            if isinstance(cid, str):
                dropped.add(cid)
    return dropped


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
           "size_chars_sum": 0, "guide_dropped": [],
           "corrupt": [], "snapshots": []}
    for f in files:
        snap = load_json(f)
        if not snap:
            agg["corrupt"].append(f.name)
            continue
        agg["runs"] += 1
        # M2 真分母：缺陷率 = 该类型 issue 数 / (对象规模/千字符)；无规模数据时留 0 并告警
        agg["size_chars_sum"] += int((snap.get("task") or {}).get("size_chars") or 0)
        # M5：收集本轮被预算截断的条款 ID，供降权候选排除
        for cid in (snap.get("guide_dropped") or []):
            if isinstance(cid, str) and cid not in agg["guide_dropped"]:
                agg["guide_dropped"].append(cid)
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
    new_basis = {}          # M3/M1：新增条款 → 绑定过的实际返工 issue（写入生命周期 sidecar）
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
            # M6：不可证伪措辞确定性拒绝（这类条款无法被任何证据否定，进导引单即噪声）
            bad = [w for w in _UNFALSIFIABLE if w in line]
            if bad:
                result["skipped"].append(
                    "add %s: 含不可证伪措辞 %s（M6），须改写为可客观检验的要求" % (key, "/".join(bad)))
                continue
            if not _CHECKABLE_RE.search(line):
                # 启发式，不硬拒（避免误杀）；但必须可见
                result.setdefault("warn", []).append(
                    "add %s: 未识别到可检验对象（位置/字段/数值/编号/条款号），请人工确认可验证性（M6）" % key)
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
                # M4：块满即拒新增（retire 在本函数中先于 add 执行，故此处计数已反映同批淘汰）
                if bi is not None:
                    cap = CLAUSE_CAP["general"] if ans == "general" else CLAUSE_CAP["per_ns"]
                    used = len([1 for ln in blocks[bi][1:] if _CLAUSE_RE.match(ln)])
                    if used >= cap:
                        result["skipped"].append(
                            "add %s: 块「%s」已达上限 %d 条（M4），须在同一裁决文件中淘汰等量条款"
                            % (key, heading, cap))
                        continue
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
            new_basis[key] = list(item.get("basis") or [])
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

    # M1/M7：条款变更同时登记进生命周期 sidecar（新增→trial；淘汰→移除记录；改写→保留原状态）
    lc = load_lifecycle(state)
    by_id = {x.get("id"): x for x in lc["clauses"] if isinstance(x, dict) and x.get("id")}
    trial_new = []
    for key in result["add"]:
        e = by_id.get(key)
        basis = list(new_basis.get(key) or [])
        if e is None:
            e = {"id": key, "block": None, "state": "trial", "added_iter": c.N,
                 "basis": [], "windows_observed": 0, "zero_evidence_windows": 0,
                 "last_counted_iter": None, "evidence": {"hits": 0}}
            lc["clauses"].append(e)
            by_id[key] = e
            trial_new.append(key)
        e["basis"] = sorted(set(list(e.get("basis") or []) + basis))
        e.setdefault("evidence", {})
    for key in result["retire"]:
        lc["clauses"] = [x for x in lc["clauses"] if x.get("id") != key]
        by_id.pop(key, None)
    save_lifecycle(state, lc)
    result["lifecycle"] = {"trial_registered": trial_new, "removed": list(result["retire"])}
    return result


def _build_candidates(c, state, agg):
    """由 S1 聚合生成 S2 候选清单（新增/降权候选；精确语义由 agent 裁决）。

    反自我强化（M2/M3/M4/M5，owner 裁决 2026-09-10）：
      - M3 新增候选须双向达标：类型在近窗口出现 ≥ c.new_threshold 次，
        **且**该类型在 ledger 中曾有 issue 实际进入修复流程（仅"提出过"不算——
        提议会被驳回，只有真动手修过才产生返工成本，才值得固化为条款）。
      - M4 目标块已满 CLAUSE_CAP 时不再产生新增候选（超限必须先淘汰等量才准新增）。
      - M5 降权候选排除本窗口被预算截断的条款——未注入条款的"零命中"是结构性的，
        不是有效性证据；把它当无效淘汰属观测污染。
      - M2 命中率不参与存废判定，只作排序权重（见 sync_lifecycle）。
    """
    candidates, warnings = [], []
    if not agg:
        return candidates
    prefix = _NS_PREFIX[c.ns]
    cap = CLAUSE_CAP["general"] if c.ns == "general" else CLAUSE_CAP["per_ns"]
    clauses = guide_clause_ids(guide_paths(c.src_root, c.ns)["pregen"])
    block_kind = "general" if c.ns == "general" else _NS_HEADING[c.ns][4:].strip()
    used = len([1 for k, _, _ in clauses if k == block_kind])
    at_cap = used >= cap

    size = int(agg.get("size_chars_sum") or 0)
    if size <= 0:
        warnings.append("近窗口快照缺 task.size_chars，缺陷率分母不可用；"
                        "本次降权/存废建议仅依据零证据窗口计数（M2 降级）")

    fix_types, fix_ids = ledger_fix_types(state)
    for typ, cnt in sorted(agg.get("types", {}).items(), key=lambda kv: -kv[1]):
        if cnt < c.new_threshold:
            continue
        if at_cap:
            continue
        if typ not in fix_types:
            # M3：只有频次、无实际返工 —— 不进候选，但留痕供人工判断
            candidates.append({"kind": "new-clause-rejected", "ns": c.ns, "defect_type": typ,
                               "count": cnt, "reason": "no-fix-evidence",
                               "note": "近窗口出现 %d 次但 ledger 中无该类型进入修复流程的 issue；"
                                       "按 M3 不生成新增候选（防偶发噪声固化为条款）" % cnt})
            continue
        rate = (cnt / (size / 1000.0)) if size else None
        candidates.append({"kind": "new-clause-candidate", "ns": c.ns,
                           "defect_type": typ, "count": cnt,
                           "defect_rate_per_kchar": round(rate, 4) if rate is not None else None,
                           "basis_issues": sorted(set(fix_ids.get(typ) or []))[:10],
                           "note": "近窗口出现≥%d 次且有实际返工证据，请裁决是否新增导引单条款"
                                   "（agent 撰写文本，格式 - [%s-###] …）" % (c.new_threshold, prefix)})
    if at_cap:
        warnings.append("块「%s」已满上限 %d 条（M4）：本次不产生新增候选；"
                        "如需新增，须在裁决文件中同时淘汰等量条款" % (block_kind, cap))

    # 降权候选（设计 5.4 语义保留，但按 M2 收紧判据）
    # M2 一致性要求：零命中**只是线索**，不足以判失效（条款被遵守恰恰表现为零命中）。
    # 因此本函数只按"零证据窗口计数"（由 sync_lifecycle 维护、以 hits/basis 双信号重置）
    # 决定是产出 **降权候选**（达阈值，可驱动裁决）还是 **降权线索**（未达阈值，仅供参考）。
    # 这样"零命中"不再是独立的第二条降权信号源，消除与 sync_lifecycle 的判断冲突。
    hits = agg.get("clause_hits", {})
    dropped = dropped_clause_ids(state, c.ns, c.window)
    lc_by_id = {x.get("id"): x for x in load_lifecycle(state)["clauses"] if isinstance(x, dict)}
    if agg.get("issues_total", 0) >= 1:
        for _kind, cid, _ln in clauses:
            if not cid.startswith(prefix):
                continue
            if hits.get(cid):
                continue
            if cid in dropped:
                # M5：该条款本窗口被预算截断，根本没被注入 → 零命中不可作证据
                candidates.append({"kind": "demote-suppressed", "clause": cid,
                                   "reason": "budget-truncated",
                                   "note": "本窗口该条款被注入预算截断、从未生效，"
                                           "零命中不计入降权候选（M5 防观测污染）"})
                continue
            zew = int((lc_by_id.get(cid) or {}).get("zero_evidence_windows") or 0)
            if zew >= ZERO_EVIDENCE_DEMOTE:
                candidates.append({"kind": "demote-candidate", "clause": cid,
                                   "zero_evidence_windows": zew,
                                   "note": "已连续 %d 个窗口既无引用又无绑定返工证据（阈值 %d），"
                                           "建议降权/淘汰（agent 裁决）" % (zew, ZERO_EVIDENCE_DEMOTE)})
            else:
                candidates.append({"kind": "demote-hint", "clause": cid,
                                   "zero_evidence_windows": zew,
                                   "note": "本窗口零命中，但零证据窗口仅 %d（阈值 %d）——"
                                           "零命中只作线索，不足以判失效（M2）；请结合缺陷率人工判断"
                                           % (zew, ZERO_EVIDENCE_DEMOTE)})
    # 告警以候选条目形式回传，保证 agent/用户看得见（禁止静默降级）
    return candidates + [{"kind": "warning", "note": w} for w in warnings]


def phase_S2(c, state, agg, edits):
    """S2 导引单回写：产出候选清单；有裁决文件才落盘改动。"""
    # 续跑（resume）时 S1 已在前次执行，聚合从落盘文件恢复，避免空数据覆盖候选
    if not agg.get("issues_total") and (state / "sediment" / ("iter-%d-S1.json" % c.N)).exists():
        agg = load_json(state / "sediment" / ("iter-%d-S1.json" % c.N), {}) or {}
    cand_file = state / "sediment" / ("iter-%d-candidates.json" % c.N)
    candidates = _build_candidates(c, state, agg)
    save_json(cand_file, {"iter": c.N, "ns": c.ns, "window_snapshots": len(agg.get("snapshots", [])),
                          "clause_cap": (CLAUSE_CAP["general"] if c.ns == "general" else CLAUSE_CAP["per_ns"]),
                          "new_threshold": c.new_threshold,
                          "guide_dropped": agg.get("guide_dropped") or [],
                          "candidates": candidates})

    if edits is None:
        # 无裁决 → 停在 S2 前，等待 agent 撰写并续跑
        return {"applied": False, "await_edits": True, "candidates_file": str(cand_file),
                "candidates": candidates}
    applied = apply_guide_edits(c, state, edits)
    # M1/M7：条款集变更后推进生命周期（trial 观察窗口、零证据计数、转正/降权/淘汰建议）
    lc = sync_lifecycle(c, state)
    # M7 审计：本轮"凭什么改条款"单独落一份 iter-N-guide-changes.json
    # （含裁决原文、实际生效/被拒条目、生命周期结论、本轮截断条款），供事后追溯
    changes_file = state / "sediment" / ("iter-%d-guide-changes.json" % c.N)
    save_json(changes_file, {
        "iter": c.N, "ns": c.ns, "at": iso(c.now), "trigger": c.trigger,
        "edits_requested": {"add": edits.get("add") or [],
                            "demote": edits.get("demote") or [],
                            "retire": edits.get("retire") or []},
        "edits_applied": applied,
        "lifecycle": lc,
        "guide_dropped": agg.get("guide_dropped") or [],
        "clause_cap": (CLAUSE_CAP["general"] if c.ns == "general" else CLAUSE_CAP["per_ns"]),
        "new_threshold": c.new_threshold})
    return {"applied": True, "await_edits": False, "candidates_file": str(cand_file),
            "candidates": candidates, "actions": applied, "lifecycle": lc,
            "changes_file": str(changes_file)}


def phase_S3(c, state):
    """S3 脚本泛化：queue/ 候选脚本回归通过才进注册表（FR-19）。
    WBS-2.1 扩展：读 R2 全字段（含 task_id/code_path|code）；技能级条目写 task_id+code_path+hash
    （hash=内容 sha1，内联 code 取 code 文本哈希）；幂等：同 hash 已存在只更新 registered_at/version。"""
    import hashlib as _hashlib
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
        cp = cand.get("code_path")
        code = cand.get("code")
        if not cp and not code:
            # m5：无源码来源（无 code_path/code）→ 不可验证，判失败（不注册 hash=None、不参与去重）
            shutil.move(str(f), str(failed / f.name))
            rejected.append(cand["name"] + " (no-source)")
            continue
        if code:
            content_hash = _hashlib.sha1(code.encode("utf-8")).hexdigest()
        elif cp:
            try:
                content_hash = _hashlib.sha1(open(cp, "rb").read()).hexdigest()
            except Exception:
                content_hash = None
        else:
            content_hash = None
        rec = {"name": cand["name"], "ns": cand.get("ns", c.ns),
               "task_id": cand.get("task_id"),                    # NEW：来源=候选（缺则调用方注入）
               "version": cand.get("version", "0.1"),
               "code_path": str(Path(cp).resolve()).replace("\\", "/") if cp else None,
               "hash": content_hash,
               "hits": 0, "false_positives": 0,
               "registered_at": iso()}
        if regres.get("passed") is True:   # S-2：只有确证 exit 0 才算通过
            if rec["hash"] is not None:
                hit = next((r for r in reg["scripts"] if r.get("hash") == rec["hash"]), None)
                if hit is not None:                       # 幂等：同内容只更新版本/时间，不重复注册
                    hit["version"] = rec["version"]
                    hit["registered_at"] = iso()
                    save_json(reg_file, reg)
                    shutil.move(str(f), str(done / f.name))
                    promoted.append(rec["name"] + " (dedup-update)")
                    continue
            reg["scripts"].append(rec)
            save_json(reg_file, reg)
            shutil.move(str(f), str(done / f.name))
            promoted.append(rec["name"])
        elif regres.get("passed") is False:
            shutil.move(str(f), str(failed / f.name))
            rejected.append(cand["name"])
        else:
            continue    # passed=None（未决/需带参调用）：留在 candidates，不晋升也不判失败（S-2）
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
        if ac.get("skipped"):
            bullets.append("导引单被拒条目：%s" % "；".join(ac["skipped"]))
        if ac.get("warn"):
            bullets.append("导引单告警：%s" % "；".join(ac["warn"]))
        lc = s2.get("lifecycle") or {}
        if lc:
            def _j(seq):
                return ", ".join(seq) if seq else "无"
            # trial_registered 出自 apply_guide_edits（条款变更），不在 sync_lifecycle 的返回里；
            # 早期实现从 lc 取该键 → 恒为 None → changelog 永远打印"新增 trial 无"（真 bug，已修）。
            new_trial = ((ac.get("lifecycle") or {}).get("trial_registered")) or []
            bullets.append("条款生命周期：在册 %d 条｜新增 trial %s｜转正 %s｜试用到期待裁决 %s｜降权建议 %s｜淘汰建议 %s"
                           % (lc.get("clauses", 0), _j(new_trial),
                              _j(lc.get("promoted")), _j(lc.get("trial_expired")),
                              _j(lc.get("demote_suggest")), _j(lc.get("retire_suggest"))))
        dropped = s1.get("guide_dropped") or []
        if dropped:
            bullets.append("注入截断：近窗口有 %d 条条款因超预算未注入（%s），已按 M5 排除出降权候选"
                           % (len(dropped), ", ".join(dropped)))
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
    # M3：新增门槛 3→5（owner 裁决 2026-09-10）；同时要求该类型有实际返工证据，见 _build_candidates
    ap.add_argument("--new-threshold", type=int, default=5)
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
                                  "clause_cap": (CLAUSE_CAP["general"] if c.ns == "general" else CLAUSE_CAP["per_ns"]),
                                  "new_threshold": c.new_threshold,
                                  "guide_dropped": s1.get("guide_dropped") or [],
                                  "candidates": _build_candidates(c, state, s1)})
        cand = load_json(cand_file, {"candidates": []}) or {}
        final["message"] = ("已产出聚合与候选清单。请撰写新条款文本（格式 - [%s-###] …）后执行: "
                            "sediment_run.py --ns %s --resume iter-%d --guide-edits <裁决文件>" % (_NS_PREFIX[c.ns], c.ns, c.N))
        final["stats"] = {"runs": s1.get("runs", 0), "issues_total": s1.get("issues_total", 0),
                          "size_chars_sum": s1.get("size_chars_sum", 0),
                          "guide_dropped": s1.get("guide_dropped", [])}
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
