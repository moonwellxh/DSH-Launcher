# 审查协议细则（protocols.md）

> 本文件是 SKILL.md 第 2/5/6 节引用的细则全文。节号沿用设计稿编号：4.x＝审查协议、6.2＝压缩决策不等式、7.1＝快照 schema，供 SKILL.md 直接锚点引用。
> 渐进式加载：仅在涉及对应环节（分级裁决/并行仲裁/热力图分配/压缩决策/快照组装）时读取本文件，勿常驻上下文。

## 4.1 缺陷分级定义

| 级别 | 定义 | 触发动作 |
|---|---|---|
| 阻断（blocking） | 导致成果不可用/错误成立：事实错误、违反强制性约束、逻辑断裂、数据无来源且影响结论 | 必须修复后才可交付；显式呈现用户裁决 |
| 严重（major） | 不致命但显著损害质量：依据不足的关键论断、一致性问题、重要边界缺失 | 触发修复循环 |
| 轻微（minor） | 表述、格式、次要完整性问题 | 记录归档，不触发循环 |
| 建议（suggestion） | 可选优化方向 | 仅列示 |

**通过判据**＝阻断清零 ∧ 严重清零（或经用户裁决豁免）。判据在审查开始前冻结，循环中不得加码（防设定值漂移）。

## 4.2 证据绑定契约（意见单 schema）

```json
{
  "issue_id": "AR-20260905-007",
  "severity": "blocking|major|minor|suggestion",
  "type": "事实性|一致性|合规性|边界|逻辑|完整性|表述",
  "anchor": "文件/章节/行号或稳定锚点（禁止复制原文段落）",
  "basis": "违反的依据：条款号/规则/可复现推理链",
  "confidence": "high|medium|low",
  "suggestion": "修复方向（一句话）",
  "evidence_ok": true
}
```

级别枚举映射：`blocking`＝阻断、`major`＝严重、`minor`＝轻微、`suggestion`＝建议。

**滤波规则（公理 4）**：`anchor` / `basis` / `confidence` 缺任一直接丢弃（不入台账）；`confidence=low` 的意见只进"待人工抽检"区，不驱动修复。丢弃与抽检均须在结论中向用户可见地说明，禁止静默。

## 4.3 台账状态机（ledger.py 强制流转）

```
提出 --confirm--> 已确认 --fix_start--> 修复中 --fix_submit--> 待验证
待验证 --verify_pass--> 已关闭
待验证 --verify_fail--> 已确认        （重开，reopen_count+1）
已关闭 --regression_fail--> 已确认    （重开，reopen_count+1）
提出/已确认 --reject(需反驳证据)--> 已驳回
```

**事件合法集**（事件名即 CLI 参数，与脚本一致）：`confirm` `fix_start` `fix_submit` `verify_pass` `verify_fail` `reject` `regression_fail`。`reject` 必须附 `--evidence "反驳证据"`（如反驳所依据的条文/可复现反例），缺证据拒绝执行。

非法转移直接报错退出（退出码 2，输出 `{"error":…}`）。`reopen_count` 是振荡指标（FR-6）：同一 issue 重开 ≥2 次时，必须暂停循环并向用户报告"修复规范可能不完整"，请求裁决而非继续空转。

CLI：`python3 scripts/ledger.py --session <session-id> <new|transition|list|export> …`
- `new`：从 stdin 读 `{"issues":[…]}`，缺失 anchor/basis/confidence（或 severity 非法）的意见被过滤（不入台账，`dropped` 计数返回）；通过者自动分配编号 `AR-<YYYYMMDD>-<NNN>` 并落盘到 `var/ledger/<session-id>.json`。
- `transition --id <issue_id> --event <事件> [--evidence …]`；`list [--status …]`；`export`（全量导出，供快照组装）。

## 4.4 收敛判定与熔断（FR-5）

轮间重合度算法：将本轮与上轮意见规范化为去重键集合（`anchor 规范化 + type`）：

```
overlap = |A_cur ∩ A_prev| / |A_cur ∪ A_prev|
收敛 ⇔ overlap ≥ 0.80 ∧ 阻断级数 = 0
熔断 ⇔ 轮数 > 5（默认）⇒ 输出当前台账与遗留清单，交用户裁决
```

重合度高的物理含义：审查者已到达定点，继续运行的边际收益≈0（公理 2）。

## 4.5 增量审查范围算法（diff_scope.py）

输入两版对象（文件对或 git diff），输出审查范围清单（仅行号区间＋理由，**不输出原文**，防 token 泄漏）：

1. 解析变更块（文件对用 `difflib.SequenceMatcher` 对齐；`--git` 用 `git diff --unified=0` 解析 hunk）；
2. 每个变更块向上下文扩展 ±N 行（默认 N=5，`--context` 参数化）；
3. **引用扩散**：提取变更段落中的标识符（章节号/条款号/函数名/标准号），全文检索其被引用位置，将被引用段标记为"受影响关联段"——因为变更可能使引用处失效；
4. 与台账未关闭项取并集（`--session <id>` 时，追加 reason 为"台账未关闭"的条目），输出 `scope: [ {file, ranges[], reason} ]`；
5. 无变更时输出空 scope（退出码 0）。

CLI：`python3 scripts/diff_scope.py --old <旧版> --new <新版> [--context N] [--session <id>]` 或 `python3 scripts/diff_scope.py --git [--git-base <rev>] [--path <子路径>] [--context N]`。无法对齐（缺文件/二进制/非 UTF-8 文本/非 git 仓库）→ 退出码 2。

## 4.6 并行审查分工与仲裁（FR-18）

**启用判据（任一）**：对象 >30,000 字符或 >10 个章节；需独立观测隔离（防上下文污染）；用户时限要求。默认串行，不满足判据不得为并行而并行。

分工矩阵＝视角（边界/一致性/合规）×对象分片，每个子审查者只拿自己的格子，独立上下文（观测独立性）。

仲裁合并协议：

1. 去重键＝规范化锚点＋类型；同键多条合并；
2. 冲突裁决：severity 取高；证据充分者优先；
3. **并集而非投票否决**：少数派意见不得被多数表决淘汰（对抗审查的价值恰在盲点）；投票仅用于提升置信度标注；
4. 合并结果回台账，走正常状态机。

## 4.7 聚焦区风险热力图（FR-7/8 的量化核心）

```
score(zone) = prior(zone) × signal(zone) × impact(zone)
prior  ：该区域的先验缺陷密度（metrics 历史统计；无历史时用命名空间清单默认先验）
signal ：本轮便宜信号 = L0脚本命中数 + 引用密度 + 数字密度 + diff覆盖度（归一化到 0~1）
impact ：失效后果权重：强制性条文/安全相关=3，对外承诺数据=2，一般=1
```

L2 预算按 score 比例分配聚焦区；每轮结束用实际检出更新 prior（后验→先验，贝叶斯更新）。默认聚焦区三类：边界条件、交叉引用一致性、外部硬约束符合性；命名空间文件给出各自的先验与高频缺陷清单。

## 4.8 导引单注入与截断协议（2026-09-10 立规，owner 裁决）

**执行者**：`scripts/guide_inject.py`（确定性、零模型判断、可复跑）。SKILL.md §0.3 只规定"做什么"，本节点规定"怎么算"。

**注入块构成**（固定顺序）：

```
## 审查预告（固定条款，不淘汰）      ← 永不截断
## 通用条款（按权重排序）            ← 通用块全部保留条款
### <本任务命名空间>                 ← 只取本任务那一类的条款
（导引单按预算截断，已弃 N 条：…）   ← 仅当发生截断时出现
```

**截断顺序（从先弃到后弃，确定性）**：

1. **命名空间块条款**，从**块尾向块首**；
2. **通用块条款**，从**块尾向块首**；
3. **保底核心集永不截断** ＝ 审查预告 ＋ 通用块权重最高的 2 条（块首 2 条）；
4. 连保底核心集都超预算 → **退出码 2 + `{"error":"保底核心集超出预算"}`**，禁止静默注入残缺导引单；
5. 截断**粒度＝整条条款**，禁止截断条款内部文字（半截条款会产生误导性约束）。

依据："条款顺序即权重"（`pregen-guide.md` 首行），同一块内越靠前权重越高，故从块尾开始弃。

**token 估算口径**（确定性，零依赖）：CJK 字符计 1.0，其他字符计 0.25（≈4 字符/token）。不使用第三方 tokenizer；该系数对中文段落略偏保守（偏大），宁可早截断不可超预算。

**输出契约**：单行 JSON `{"block","kept","dropped","est_tokens","budget","truncated","notice","reason"}`。`dropped` 必须写入本轮快照的 `guide_dropped`（见 7.1），否则 M5 观测污染隔离失效。

## 4.9 条款生命周期与反自我强化（2026-09-10 立规，owner 裁决 M1~M7）

**问题（同源污染）**：生成端按导引单写 → 审查端读同一份导引单（`namespaces/*.md` 显式映射导引单条款）→ 意见天然对准条款 → **命中率虚高** → 条款被"证明"有效而永久化。这是真实的自反馈回路，历史实现无任何护栏。

**七条措施**：

| ID | 措施 | 机制 | 切断的回路方向 |
|---|---|---|---|
| M1 | 条款试用期 | 新条款入 `trial`，观察 2 窗口；有 `basis`（实际返工证据）才升 `active`，否则转淘汰建议 | "一进导引单就永久化" |
| M2 | **命中率降级为排序权重** | 存废判据改为"零证据窗口计数 + 缺陷率（真分母=近窗口 `task.size_chars` 之和）"；**零命中≠无效** | "同源→高命中→固化" |
| M3 | 新增候选双向达标 | 频次 ≥`new_threshold`(=5) **且** ledger 中该类型曾有 issue 进入修复流程 | 偶发噪声固化为规则 |
| M4 | 条款数硬上限 | 通用 ≤10 ∧ 每命名空间 ≤4；超限必须先淘汰等量 | "只增不减" |
| M5 | 截断条款免降权 | `guide_dropped` → `demote-suppressed` | 观测污染（未生效条款被判无效） |
| M6 | 可检验性 | 不可证伪措辞**确定性拒绝**；无可检验对象出 `warn`（启发式不硬拒） | 空转条款 |
| M7 | 变更审计 | 增/降/汰 + 依据 issue 落 `guide-clauses.json` 与 `iter-N-*.json` | "凭什么进来的"不可追溯 |

**状态机**：

```
（新增条款）--apply_guide_edits--> trial --2窗口∧有basis--> active
                                    trial --2窗口∧无basis--> 淘汰建议
                                  active --连续2窗口零证据--> 降权建议
                                  active --连续4窗口零证据--> 淘汰建议
（淘汰）------retire--> 记录移除
```

**关键纪律**：
- 状态存 `var/registry/guide-clauses.json`，**注入端不读它**（保持注入零额外成本）。
- 零证据计数以 `last_counted_iter` 去重，防 resume 重复计数。
- **脚本只产建议，不自动改条款文本**；文本增删一律由 agent 撰写裁决后经 `--guide-edits` 落盘。
- `active` 条款默认**不重置**观察期：改写既有条款（upsert）保留原状态，不改写条则不动。

## 6.2 压缩决策净收益不等式（FR-17 核心）

```
压缩净收益 = 节省token费用 − 压缩调用成本 − 缓存失效损失 − 语义损失期望返工费
其中：
节省token费用  = Σ压缩token × 加权单价（按命中/未命中占比，命中按 λ）
压缩调用成本  = 压缩操作的（输入×单价 + 输出×输出单价）
缓存失效损失  = 压缩点之后稳定后缀的token × (未命中价 − 命中价)
              【前缀缓存机制：改动前部任意字节，其后全部缓存失效】
语义损失期望返工费 = P(误解|压缩) × 单轮修复费用
判定：净收益 > 0 才压缩
```

三条推论（写死在 SKILL.md 第 5 节）：

1. 稳定上下文优先"原样保留＋追加增量"，与 FR-3 同构；激进压缩命中率为 98% 的上下文在 λ=1/30 下几乎必然亏本。
2. 压缩只用于：真正的新增（未命中）内容、或触及上下文窗口上限时。
3. **净化豁免**：审查者子上下文的截断/重构/净化不适用本不等式——观测独立性优先于一切费用系数（防同余误差）。

价格与 λ 数据见 `references/pricing-models.md`（脚本只解析其中唯一 ```json 块）。

## 6.3 注入位置与缓存（2026-09-10，owner 裁决）

**规则**：导引单注入到**生成动作前的最后位置**（读完资料、开始撰写之前），**不注入上下文前部**。

**依据**：前缀缓存的失效规则是"改动前部任意字节，其后**全部**失效"。

| 注入方式 | 导引单变更时的缓存代价 |
|---|---|
| 前部注入 | 其**后全部内容**失效 —— 整个任务上下文作废 |
| **尾部注入（本规）** | 其后内容为 0 → **只失效导引单自身** |

位置只解决一半，另外两条同等重要（均见 SKILL.md §0.3）：

1. **历史不复改**——本会话已注入过的导引单文本永不回改，更新一律追加增量补丁。会话推进后旧导引单会永久留在历史中成为后续轮次的前缀，回改它等于破坏前缀。
2. **同会话不重复粘贴**——无变更只发一行指针，有变更只发增量。

**推论（与 6.2 一致）**：导引单是一个**位于上下文前部的缓存锚点**（首次注入后即成为历史前缀的一部分）。因此"沉淀越频繁 → 缓存失效越频繁"。6.2 的"稳定上下文优先原样保留＋追加增量"在这里的具体形态就是：**只追加、不回改、不重发**。

## 7.1 快照 schema（collect_snapshot.py 的输出契约）

```json
{
  "id": "snap-20260905-203015-a1b2",
  "ts": "2026-09-05T20:30:15+08:00",
  "ns": "regulation",
  "env": {
    "platform": "kimi|dsh|workbuddy",
    "host_note": "宿主版本或备注",
    "model": "当前模型标识（识别不了填 unknown）",
    "pricing_version": "pricing-models.md 的 updated_at"
  },
  "task": {"summary": "≤200字", "object_type": "文档|代码|规范|通用", "size_chars": 0},
  "mode": "closed_loop|report_only",
  "rounds": 2,
  "issues": [
    {"id": "AR-...-001", "severity": "major", "type": "合规性",
     "anchor": "第3.2节", "basis": "GB XXXXX 第X.X.X条",
     "status": "已关闭", "false_positive": false, "reopen_count": 0}
  ],
  "tokens": [{"round": 1, "input": 0, "output": 0, "cache_hit": 0}],
  "guide_dropped": ["D-002"],
  "outcome": "passed|converged|fused|aborted",
  "fix_summary": "≤200字"
}
```

**纪律**（collect_snapshot.py 强制）：
- 单条 ≤10KB（UTF-8 字节计，超限退出码 3 并提示最占字节的字段）；
- 不存原文，只存锚点与摘要；
- 必填：顶层 `id/ts/ns/env/task/mode/rounds/issues/tokens/outcome`；`env.platform/env.pricing_version`、`task.summary/object_type`、issue 的 `id/severity/type/anchor/basis/status` 缺一即拒收（退出码 2）；`false_positive`/`reopen_count` 缺省按 false/0 补；
- 每轮 token 数字由调用方按宿主可读信息填写，读不到填 null 并在 `env.host_note` 说明；
- 可选 `guide_dropped`：本轮被注入预算截断、**未实际注入**的导引单条款 ID 数组（来自 `guide_inject.py` 的 `dropped`）。缺省=无截断。**沉淀端必须据此把该条款排除出降权候选**（M5）——否则"从未生效的条款"会被其结构性零命中误判为无效；
- stdin 传入 JSON 的 `ns` 与 `--ns` 不一致时以 `--ns` 为准并告警（stderr），不拒收；
- 快照写入失败（任意非 0 退出）的运行不计入 pending 计数——计数真值在文件系统；写入失败本身必须按脚本失败协议如实上报用户，不得静默。

CLI：`python3 scripts/collect_snapshot.py --ns <general|document|code|regulation> < data.json`；成功输出 `{"written": "<绝对路径>"}`。
