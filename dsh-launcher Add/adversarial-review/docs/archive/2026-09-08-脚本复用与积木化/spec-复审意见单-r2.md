# spec.md · 独立对抗性复审意见单（r2 增量复审，干净上下文，非 fork）

- 复审对象：`docs/spec.md`（v1.0）；本轮只审**增量**：上轮新增严重 `NEW-sA` 的修复 + 两处小闭合 `s2-res` / `mC-res(g2)`。
- 复审性质：**微型增量复审**。只审注明改动段（§4.1 / §4.2 / §4.3 / §4.5 / §5 W1·W2·W3 / §6 / §7 M1·M3 / §8 第 1/3/4/5 条）；冻结区（§1/§2/§3/§4.4/§5 W4–W8/§7 M2/M4/M5 等未改动主体）不重审、不重述其已判结论。
- 独立性声明：本次为独立子审查者（干净上下文、非 fork）。只读取被审对象 `spec.md` 与上轮意见单 `spec-复审意见单.md`（仅用于核对要求修复项的含义），**未读取/引用** `spec-审查意见单.md`、任何其它审查意见单、需求清单审查/复审意见单，或本轮主流程/作者的任何推理——本单结论仅由本人对 `spec.md` 改动段的独立判断给出。
- 交叉独立证据（已实读）：`docs/spec.md`（改动后全文）；`references/protocols.md` §7.1（快照顶层 schema，核实 `rounds` 等既有字段）；`var/task-scripts/pdf-parse-v3/registry.json`（任务级容器实物，核实容器结构及条目是否含 task_id）。
- 判定口径：protocols §4.1（阻断/严重/轻微/建议）；通过判据 = 阻断清零 ∧ 严重清零。

---

## 一、逐条判定（复审目标）

### 1. NEW-sA（严重）：skill 级条目 task_id 的**生产链是否闭合** → **已闭合（confidence：high）**

- anchor：§4.2 第 91 行（候选 schema 含 `task_id`，注「生产源=收集器（W2）」）；§5 W2 第 140 行（`collect_candidates(task_id)` 产确定性字段 `task_id`「取任务名」）；§5 W3 第 146 行（写技能级条目含 `task_id`，来源=候选 task_id，候选缺则取被审对象名注入）；§4.3 第 104 行（技能级条目含 `task_id`）；§8 第 4 条 第 208 行（晋升链要求含 code_path+hash+task_id）。
- basis（改动后证据）：
  1. **生产者已指派**：§4.2 第 91 行明示 task_id 生产源=收集器（W2）；§5 W2 第 140 行 `collect_candidates(task_id)` 把 `task_id`（取任务名）列为**确定性字段**产出——上轮「skill 级 task_id 无生产者」的悬空被补上，且来源落到 W2。
  2. **写入者与来源已明确**：§5 W3 第 146 行「写技能级条目含 **task_id**（来源=候选 task_id；候选缺则取被审对象名注入）」——唯一写入者 phase_S3 已由「只写 code_path+hash」扩展为写 task_id，且给出确定来源。上轮所指「phase_S3 上下文 c（仅 ns/src_root/N/now/trigger）无 task_id」已由「从候选取」规避。
  3. **兜底已写明**：候选缺 task_id 时「取被审对象名注入」在 §5 W3 第 146 行白纸黑字写明（候选通常由 W2 必产，此为防御性兜底）。
  4. **验收链可达成**：§8 第 4 条 第 208 行「S3 扩展后技能级 scripts.json 条目含 code_path（绝对）+hash+task_id」——W3 写 task_id 后该判据成立，不再走空。
  5. **链完整**：候选 schema（§4.2 task_id）→ 收集器（W2 产 task_id）→ 晋升（W3 写技能级 task_id，含兜底）→ 验收（§8 第 4 条）四环闭合。
- confidence：high（生产源、写入者、来源、兜底、验收五处均实测改动且相互一致，上轮断言「无生产者」的缺口确凿被补）。
- 次生轻微（非闭合失败，见 §三 A-a）：§4.2 第 99 行生产者分工的**确定性字段列举**为 `（name/ns/version/code_path|code/environment/regression）`，**未列出 `task_id`**；而 task_id 同属 W2 产的确定性字段（第 91 行注释与 §5 W2 第 140 行均明示）。属同一修复区的表述漏列，不破坏闭合（生产源已在 schema 注释与 W2 明示），记轻微。

### 2. s2-res（轻微）：W1 是否容器化（read/write 签名返回/写入容器、保 meta） → **已闭合（confidence：high）**

- anchor：§5 W1 第 134 行（`read_registry(path) -> dict` 返回**容器** `{namespace,target,updated,location_rule,scripts:[…]}`）；第 135 行（`write_registry(path, container)` 原子写：临时文件+rename，写回整个容器，meta 由调用方原样保留）；第 136 行（`register_l0` 读容器→增/改 `scripts[]`→写回容器）。
- basis：上轮 s2-res 所指「`read_registry(path) -> list[entry]` / `write_registry(path, entries)` 仍按裸条目列表建模」已被替换——第 134 行 `read_registry` 显式返回**容器 dict**（并在注释标注「闭合 s2-res：接口显式容器化」），第 135 行 `write_registry` 显式接受**容器**参数并原子写回整个容器、meta 由调用方原样保留；第 136 行 `register_l0` 也以「读容器→合并 scripts[]→写回容器」建模。读写签名层面已容器化，不再依赖 §4.1 纪律文字兜底。同时核对了试点实物 `var/task-scripts/pdf-parse-v3/registry.json` 顶层键为 `namespace/target/updated/location_rule/scripts:[…]`，与 §4.1 第 76 行容器模型一致。
- confidence：high（签名级已改容器化，且与试点容器实物对拍一致）。
- 次生轻微（见 §三 A-b）：§5 W1 第 136 行 `register_l0` 增/改 `scripts[]` 条目「含 **task_id**」——但任务级 registry 条目 schema（§4.1 第 78–85 行）不含 task_id，试点实物各条目亦无 task_id（实测：name/ns/code_path/entrypoint/run/purpose）。属任务级条目多写一个未声明字段，不影响容器完整性（meta 仍保），记轻微。

### 3. mC-res（轻微）：reuse_ledger 扩展块是否与快照顶层既有字段冲突 → **已闭合（confidence：high）**

- anchor：§4.5 第 118 行（并入快照可选扩展块 `reuse_ledger`，不与快照顶层既有字段冲突）；第 120–122 行（块内 `{"round":"r3", "reused_scripts":[…], "new_scripts":[…], "reused_count":…, "new_count":…, "est_saved_tokens":…}`）；第 124 行（快照顶层既有 `rounds`（int）字段不变，无命名冲突；g2/mC-res 落点）。
- basis：对照 `references/protocols.md` §7.1 快照顶层 schema（第 125–148 行），既有顶层键为 `id/ts/ns/env/task/mode/rounds(int)/issues/tokens/outcome/fix_summary`。`reuse_ledger` 为**新顶层可选键**，不在既有键集合内；其块内 `round`（字符串，如 "r3"）与顶层 `rounds`（int，轮数）处于**不同作用域、不同键名**，无命名冲突；顶层 `rounds` 保持不变。上轮 mC-res/g2 所指「§6 注用 rounds 与 §4.5 round 不一致」已在第 124 行通过「快照顶层既有 rounds（int）字段不变、无命名冲突」明确二者的域属关系而消除。
- confidence：high（已对照 §7.1 既有顶层字段逐键核实，无键名撞车；顶层 `rounds` 未被覆盖）。
- 备注（轻微/建议，不重开 mC-res）：块内 `round` 与顶层 `rounds` 词形相近，阅读者可能短暂混淆；建议步骤 7 在 §4.5 加一句「块内 round=轮次标识（字符串），顶层 rounds=轮数（int）」以消歧。不构成冲突，仅作提示。

### 4. 是否引入新阻断/严重 → **无（confidence：high）**

- basis：逐项扫视改动段（§4.1/§4.2/§4.3/§4.5/§5 W1·W2·W3/§6/§7 M1·M3/§8 第 1/3/4/5 条）未见以下类致命破坏：(a) 事实错误 / 违反强制性约束 / 逻辑断裂 / 关键数据无来源；(b) 一致性问题导致某出口必然走空或验收必然失败。NEW-sA 生产链闭合后，M1/M2/M3/M5 出口与 §8 第 1/3/4/5 条均可达；s2-res 容器化后写回不丢 meta；mC-res 后 reuse_ledger 不覆盖顶层既有字段。二级判定的三个目标项本身均闭合，无连带引入新的严重/阻断。
- confidence：high（改动段范围明确，已逐点核对无新致命断点）。

---

## 二、新阻断/严重

**无。** 上轮唯一严重 NEW-sA 已在本轮闭合（见 §一 第 1 条）；两处小闭合（s2-res、mC-res）亦已闭合。本轮未引入新的阻断或严重项。

---

## 三、各级条数（本轮增量视角）

| 级别 | 条数 | 说明 |
|---|---|---|
| 阻断 | **0** | — |
| 严重 | **0** | NEW-sA 已闭合；无新的严重 |
| 轻微 | **2**（本轮新观察） | ① §4.2 第 99 行确定性字段列举漏列 `task_id`（A-a）；② §5 W1 第 136 行 `register_l0` 向任务级条目写 `task_id`，未入 §4.1 schema / 试点实物（A-b）。均为表述/字段一致性细节，不触发修复循环 |
| 建议 | **0**（本轮新增） | 另：block 内 `round` 与顶层 `rounds` 词形相近的消歧微调，见 §一 第 3 条备注，记为建议性提示 |

**上轮遗留、本轮不在增量范围（仅如实列示，不重审）**：上一轮意见单 `spec-复审意见单.md` §三 记录且未在本轮目标内闭合者——`m2-res`（run_registered 无调用方）、`m4-res`（collect_snapshot.py 现行不计算复用指标，compute-vs-承载分工未明）、`m5-a`（试点条目当前无 hash，§6 已记步骤 7 必做）、`mB-res`（去向②任务级 found_issues 无填充者）、`g1`（§4.4 积木 code_path 相对路径与绝对路径约定不一致）。这些仍开放，属步骤 5/7 顺手落实项，不构成本轮增量评审对象、也不是本轮引入。

---

## 四、结论（spec 可否进入步骤 5 plan.md 的 WBS 分解）

**可以进入步骤 5。** 逐项：

- **NEW-sA 已闭合**：task_id 生产链（候选 schema §4.2 → W2 收集器产 → W3 phase_S3 写技能级，含「候选缺则取被审对象名注入」兜底）四环齐备，§8 第 4 条「含 code_path+hash+task_id」可达成，无走空。
- **s2-res 已闭合**：W1 读写签名已显式容器化（read 返回容器、write 收容器并原子写回整个容器、保 meta），与试点容器实物一致。
- **mC-res 已闭合**：reuse_ledger 为快照新顶层可选键，与 §7.1 既有顶层字段（含 rounds）无命名冲突、不覆盖既有字段。
- **无新阻断/严重**：仅两条次生轻微（§4.2 确定性字段列举漏 task_id、register_l0 任务级条目写 task_id 未入 §4.1 schema）与一条建议性消歧提示，均不阻塞步骤 5/7 推进，可在步骤 7 实现时顺手对齐。
- 综合：spec 主体在本轮改动后**骨架自洽、无阻断、无严重**，满足「阻断清零 ∧ 严重清零」通过判据。建议进入步骤 5（plan.md WBS 分解）；上述两条轻微与上轮遗留的 m2-res/m4-res/m5-a/mB-res/g1 一并列步骤 7 实现清单，不阻塞流程。

---

*renote*：本轮 token 未单独计量（由编排者统一记录）；本单为增量复审，未重复读取上轮已判定并冻结的未改动主体（§1/§2/§3/§4.4/§5 W4–W8/§7 M2/M4/M5）。
