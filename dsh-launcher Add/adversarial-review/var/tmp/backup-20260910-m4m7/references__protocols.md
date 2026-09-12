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
  "outcome": "passed|converged|fused|aborted",
  "fix_summary": "≤200字"
}
```

**纪律**（collect_snapshot.py 强制）：
- 单条 ≤10KB（UTF-8 字节计，超限退出码 3 并提示最占字节的字段）；
- 不存原文，只存锚点与摘要；
- 必填：顶层 `id/ts/ns/env/task/mode/rounds/issues/tokens/outcome`；`env.platform/env.pricing_version`、`task.summary/object_type`、issue 的 `id/severity/type/anchor/basis/status` 缺一即拒收（退出码 2）；`false_positive`/`reopen_count` 缺省按 false/0 补；
- 每轮 token 数字由调用方按宿主可读信息填写，读不到填 null 并在 `env.host_note` 说明；
- stdin 传入 JSON 的 `ns` 与 `--ns` 不一致时以 `--ns` 为准并告警（stderr），不拒收；
- 快照写入失败（任意非 0 退出）的运行不计入 pending 计数——计数真值在文件系统；写入失败本身必须按脚本失败协议如实上报用户，不得静默。

CLI：`python3 scripts/collect_snapshot.py --ns <general|document|code|regulation> < data.json`；成功输出 `{"written": "<绝对路径>"}`。
