# spec.md · 独立对抗性复审意见单（增量复审，干净上下文，非 fork）

- 复审对象：`docs/spec.md`（v1.0，改动段：§4.1 容器模型 / §4.2 字段生产者分工 / §4.3 task_id / §5 W1·W2 / §6 闭合与归档 / §7 M1·M3 / §8 第 1/3/4/5 条 / §9 诚实声明）；关联改动 `docs/升级需求清单.md` §九 R2 行。
- 复审性质：**增量复审**。只审改动段 + 上轮未关闭项（s1/s2 + m5）；冻结区（§1/§2/§3/§4.4/§5 W3–W8/§7 M2/M4/M5 等未改动主体）不重审、不重述其已判结论。
- 上轮意见单：`docs/spec-审查意见单.md`（阻断 0 / 严重 2：s1、s2；轻微 9：m1–m9；建议 4：g1–g4）。本单只用于核对「要求修复项」，未读取/引用除其外的任何其它审查结论。
- 判定口径：同 protocols.md §4.1（阻断/严重/轻微/建议），通过判据 = 阻断清零 ∧ 严重清零。
- 交叉资料（已实读）：`var/task-scripts/pdf-parse-v3/registry.json`（容器实例）、`scripts/sediment_run.py`（phase_S3 385–409）、`scripts/collect_snapshot.py`、`references/protocols.md` §7.1、`docs/升级需求清单.md` §七/§八/§九。

---

## 一、各级条数

| 级别 | 条数 |
|---|---|
| 阻断 | **0** |
| 严重 | **1**（新增 NEW-sA；上轮 s1/s2 均已闭合） |
| 轻微 | **6**（上轮尚未闭合/次生的报告性记录，详见 §三） |
| 建议 | **1**（g1 仍开放；见 §四） |

---

## 二、上轮严重项判定（逐条：已闭合 / 未闭合 / 引入新问题）

### s1·严重·高——R2 候选的语义字段 found_issues 无生产者 → **已闭合**

- anchor：改后 §4.2（第 89–98 行）、§5 W2（第 136–139 行）、§8 第 3 条（第 204 行）、§7 M1（第 192 行）、§6「s1 已闭合」（第 180 行）。
- basis（改动后证据）：
  1. **生产者已指派**：§4.2 字段生产者分工明示语义字段 `description/test_problem/found_issues` 由**评审者（LLM）回填**；W2 第 138 行给回填点 = 收尾/复审时 `_registry_io.record_found_issues(name, issues)`；§5 W2 第 136 行并列描述 `description/test_problem` 由 docstring 派生后评审确认——语义字段不再悬空。
  2. **null+pending 口径成立且回填前合法**：W2 第 138 行、§4.2 第 98 行均置回填前候选为 `"found_issues": null, "pending_review": true`，并明示「确定性字段缺即不合格；语义字段 null+pending 不算缺」。
  3. **验收/出口不再冲突**：M1（第 192 行）与 §8 第 3 条（第 204 行）同步改为「**确定性字段**按 R2 schema 校验通过，found_issues 允许 null+pending_review（评审回填点存在即可）」。原先「R2 全字段齐全」的口径已替换，M1 出口**不再因 found_issues 未产而走空**。
  4. **与下位依据对齐**：需求清单 §九 R2 行（第 228 行）已改为「candidate description/test_problem/found_issues 语义=评审者 LLM（必要；found_issues 回填前允许 null+pending_review，见 spec §4.2）」——spec 与需求清单对 found_issues 的 null+pending 语义**一致**，上轮所指的 spec↔§九 R2 冲突已消除。
- confidence：high（生产者、null/pending 口径、验收 §8/@M1、§九 R2 四处均实测改动，缺口确凿被补）。
- 注（非新问题）：R2 采集维度 **去向②**（同任务跨次回查之任务级 registry 可选 `found_issues`）的填充者仍未在 spec 明示——W2 回填点只写到候选（去向①），W1 `register_l0(..., found_issues=None)` 有参却未指明调用者。因 §4.1 该字段为**可选**且非本轮验收项，记为轻微 `m2-res`，不构成本轮严重。

### s2·严重·中——W1 接口 vs 试点容器结构不闭合 → **已闭合（留有极轻签名歧义）**

- anchor：改后 §4.1（第 76、87 行）、§5 W1（第 130–134 行）、§6「s2 已闭合」（第 181 行）；对照试点 `var/task-scripts/pdf-parse-v3/registry.json`（`{namespace, target, updated, location_rule, scripts:[…]}`）。
- basis：
  1. **容器模型已声明**：§4.1 第 76 行明示文件为容器结构 `{namespace, target, updated, location_rule, scripts:[…]}`，与试点实物一致（试点顶层键实测 `namespace`，非 `ns`——注意与条目内 `ns` 区分，spec 表述正确）。
  2. **保 meta 纪律已写入**：§4.1 第 87 行「读写必须保留 namespace/target/updated/location_rule；任何写回不得覆盖容器元数据（闭合 s2）」；§6 第 181 行「§4.1 容器模型 + §5 W1 容器读写（保 meta，不裸数组覆盖）」。上轮「write_registry 写回裸数组覆盖 location_rule」的风险已被显式不变式封堵——**核心已闭合**。
- 残留（轻微 `s2-res`）：§5 W1 接口签名（`read_registry(path) -> list[entry]` / `write_registry(path, entries)`）仍按「裸条目列表」建模，未在签名层面体现容器包装；容器 wrap/meta 保留寄托于 §4.1 纪律文字而非接口自身。不构成新严重（不变式已白纸黑字，实现者遵 §4.1 即可），建议步骤 7 把 `write_registry` 明示为「读回容器→合并 scripts[]→原子写回」或签名改为容器对象，以消除歧义。
- confidence：medium（容器已实物核实、纪律已写入；残留为接口表述层面，非结构性缺口）。

---

## 三、轻微（报告性记录，不触发修复循环）

除上轮已记 m1/m3/m6 等已在上轮被 §6 注明并在改动段落实外，本轮**新增/仍开放**的轻微如下（均为低-中，不阻断）：

| 编号 | 内容 | 说明 |
|---|---|---|
| s2-res | §5 W1 签名仍为裸列表读写 | 见 §二 s2 残留；建议接口显式容器化 |
| m2-res | run_registered 触发接线点仍未闭 | §6「m2 已闭合」只闭合了 task_id 去重；W6 `run_registered(name, task_id)` **仍无调用方**（sediment_run/collect_snapshot/ledger/diff_scope/sediment_check 均不调用）。K3/R6「编排者侧调用」未落到具体脚本。旧 m2 前半未真正闭合 |
| m4-res | collect_snapshot.py 不计算复用指标，compute-vs-承载分工未明 | 实测 `collect_snapshot.py`（validate/main）不读 registry、不跑脚本；W6「collect_snapshot.py 增复用台账字段」易被误读为脚本自行计算。§6 m4 注明「承载=快照扩展字段」但**未注明「由调用方在 stdin JSON 提供」**，复用计数真实写入者不明 |
| m5-a | §4.1 称 hash 必填，试点条目当前无 hash | 试点 `registry.json` 各条目确无 `hash`；§6 第 184 行 m5 已记「步骤 7 落码必做，届时回填试点条目 hash」——**按要求已记为必做**（见 §五），此处仅点明现状与 §4.1 必填暂不一致，属步骤 7 待办 |
| mB-res | 去向② task 级 registry `found_issues` 无填充者 | 见 §二 s1 注；可选字段，非本轮验收项 |
| mC-res | `pending_review` 未入 §4.2 schema 示例 | §4.2 schema 片段（89–96 行）只列 `found_issues`，`pending_review` 仅见于第 98 行生产者分工段与 W2；建议在 schema 示例补注 null+pending_review 态，免歧义 |

**未算作新严重/阻断的说明**：m2-res / m4-res / m5-a / mB-res / mC-res / s2-res 均为「字段/接线细节未明」或「现状与声明暂差」，不破坏核心验收链、不导致某出口必然走空（M1/M2/M3 出口均不受影响），故只作轻微记录。

---

## 四、建议

- **g1 仍开放**：§4.4 积木条目 `code_path` 用相对路径 `skills/_shared/bricks/…`，与 §4.1/§4.3 绝对路径约定、§6 c-s1（迁移更新 code_path）不一致；建议统一绝对路径或明示解析基准。（g2 已在上轮指明「用 rounds」方向，见 §6 第 184 行 g2 注——但 §4.5 第 119 行仍写 `"round": "r3"`，§6 注与 §4.5 正文不一致，随手归入 mC-res 一类，步骤 7 统一命名即可。）

---

## 五、m5 归档项核对（按要求只判「是否已记为必做」）

- **已记为必做**：§6 第 184 行 m5 明示「`l0_registry_check.REQUIRED` 增 `hash`——**步骤 7 落码必做**，届时需回填试点条目 hash」。
- 实测印证：`var/task-scripts/pdf-parse-v3/l0_registry_check.py` 第 13 行 `REQUIRED = ("name","ns","code_path","entrypoint","run","purpose")` **仍不含 hash**（m5 所述缺口真实存在）；§6 已把它列为步骤 7 必做，符合「不要求现在实现、仅记录必做」的要求。✅ 已按要求归档。

---

## 六、结论（spec 可否进入步骤 5 plan.md 的 WBS 分解）

**可进入，但有 1 项本轮新引入的严重需在步骤 5/7 前闭合；无阻断项。** 逐项：

- **s1 已闭合、s2 已闭合**：found_issues 生产者（评审 LLM 回填 + null/pending_review）与容器读写（保 meta）均已落到 §4.2/§5 W2/§8@M1 与 §4.1/§6，且与需求清单 §九 R2 对拍一致，无走空 / 无裸数组覆盖风险。
- **承接与自洽**：§4.2 null+pending 与 §4.1（可选 found_issues）、需求清单 §九 R2 语义一致；§4.3 task_id 与 R7（hits/false_positives 归技能级）兼容——task_id 作为跨任务同名去重维度，与 R7 的「技能级条目记 hits」不冲突（新增隔离键，不改变指标归属）；M3「合成夹具/诚实空」出口与 §8 第 5 条一致且可测（对含通用片段夹具→≥1 积木；对无片段输入→如实输出空并声明；两者均能实测判定，消除 m9 走空风险）。
- **新问题（唯一需处理）**：**NEW-sA**——skill 级条目 `task_id` 有 schema（§4.3）与验收（§8 第 4 条）要求，但**无生产者**。§5 W3（唯一写入者 phase_S3）只写 `code_path+hash`（第 143 行）；候选 schema（§4.2）无 `task_id`；phase_S3 上下文 `c`（建 context，实证仅 `ns/src_root/N/now/trigger`）无 task_id；需求 §八 R3 技能级条目本也无 task_id（task_id 为 spec 上轮 m2 闭合时新增）。故按 W3 契约实现时，技能级条目缺 `task_id`，§8 第 4 条「含 code_path+hash+task_id」判据不可达成——**与 s1 同一缺陷类（声明字段无生产者）**。修正极轻：spec 需在 W3 补「写 task_id」并指定其来源（候选由 W2 写入 task_id，或 phase_S3 由被审对象名注入）。
- **综合**：spec 主体（数据 schema / 模块契约 / 验收口径）在本轮改动后**骨架自洽、无阻断**；仅 NEW-sA 一项新严重。建议：先在 §5 W3 + §4.2/§4.3 补 task_id 的写入与来源（一处补丁），再进入步骤 5 plan.md 的 WBS 分解；其余轻微/建议（s2-res / m2-res / m4-res / mB-res / mC-res / g1）可在步骤 5/7 顺手落实，不阻塞。
