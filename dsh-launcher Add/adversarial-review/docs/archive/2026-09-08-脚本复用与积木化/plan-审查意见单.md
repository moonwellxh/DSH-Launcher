# plan.md 对抗性审查意见单（独立子审查者 · 干净上下文 · 非 fork）

| 字段 | 内容 |
| --- | --- |
| 审查对象 | `docs\plan.md`（v1.0，WBS 实施分解） |
| 审查视角 | ① WBS 完整性 ② 节点自洽 ③ 依赖与顺序 ④ 可测性 ⑤ 流程映射 |
| 审查方式 | 独立子审查者，仅依 plan.md + spec.md + 升级需求清单.md + 现行代码/试点交叉核对；不沿用任何会话结论 |
| 结论 | **0 阻断；3 严重；7 轻微；3 建议** |

> 判定基准：spec v1.0（§4/§5/§6/§7/§8）；需求清单 R1–R8/§九；`scripts\sediment_run.py`（phase_S3 385–409、596）；`scripts\collect_snapshot.py`；`var\task-scripts\pdf-parse-v3\`（registry.json / l0_registry_check.py / README.md）；`scripts\` 全目录。
> 已核实事实：`scripts\_registry_io.py`/**`_collect_candidates.py`/**`_extract_bricks.py`/**`_gen_catalog.py` 不存在；`var\queue`、`var\registry`、`skills\_shared\`、`var\queue\candidates\*.json` 均为空；现行 `scripts\*.py` 无 run_registered/record_false_positive/reuse_ledger/catalog/bricks 相关代码——plan 各新建/扩展节点均属实，非空中楼阁。

---

## 〇、结论摘要（是否可进入步骤 7）

**结论：plan 可进入步骤 7，但应先消化 3 条严重项。**

- **结构可执行**：WBS 逐节点均映射到 spec §5 W1–W8 与 §7 M1–M5（§四映射表），无孤儿 W（W7 的残留=SKILL.md §2 R8 条文，由 WBS-5.4 承接，经核对 SKILL.md §2 确实缺 R8 条文——落点真实）；§8 六条均有承接连线（1–6 → WBS-1.x/2.1/4.x/5.2），§6 归档遗留 c-m*/m*/g1 均有落脚（5.1/5.3）。
- **但有 3 条严重缺口会打折扣**：① WBS-4.1 行为未覆盖 spec W6/§8#1 的「未晋升→reused_scripts[]」「代跑前查任务级 registry」分支与台账产端；② WBS-5.2 单轮叙事把「代跑 hits+1」与「首次 S3 晋升」同轮，与 §8#1 时序冲突；③ WBS-3.1 准入「命中计数」依赖 4.1 的 hits 数据，但 DAG 缺 4.1→3.1 边。
- **建议**：进步骤 7 前先补（a）WBS-4.1 行为补齐 W6 两分支并给 reuse_ledger 产/收端一个明确承载节点；（b）WBS-5.2 重构为「晋升一轮 → 复用一轮」两段序列；（c）DAG 增加 4.1→3.1 边。此三项不影响节点可编码，但直接影响 §8#1/#6 验收与机制生产链的正确性。

---

## 一、阻断（0 条）

无。

---

## 二、严重

### S1. WBS-4.1 行为缺 spec W6 的「未晋升→reused_scripts[]」与「代跑前查任务级 registry」分支，导致 §8#1 明确分支与台账产端断链
- **anchor**：plan 行 20（WBS-4.1 关键接口/行为）；plan 行 21（WBS-4.2 行为）；plan 行 23（WBS-5.2）。
- **basis**：spec §5 W6（spec 行 160–161）规定 `run_registered(name, task_id)`「代跑前**查任务级 registry**；代跑一次→技能级 hits+1（**若已晋升**）；**未晋升脚本计数记 reused_scripts[]**（R7 台账来源之一）」；spec §8 第 1 条（spec 行 207）明确「**若该脚本尚未晋升技能级，其复用计入 R7 reused_scripts[]**」；spec §4.5（spec 行 119–124）reuse_ledger 含 `reused_scripts[]`。plan WBS-4.1 行为只写「代跑已登记脚本→技能级 hits+1；误报判定→技能级 false_positives+1」，未写「代跑前查任务级 registry」，**更缺**「未晋升→reused_scripts[]」分支；WBS-4.2 只读字段（生成快照含 reuse_ledger）不产 `reused_scripts[]`。故「未晋升即计 reused_scripts[]」的产端无任何节点承载，§8#1 该分支与该观测链在 plan 层断链。
- **confidence**：高。

### S2. WBS-5.2 单轮叙事把「代跑 hits+1」与「首次 S3 晋升」同轮，与 §8#1 时序矛盾（试点技能级 registry 为空，首轮代跑应得 reused_scripts[] 而非 hits+1）
- **anchor**：plan 行 23（WBS-5.2 关键接口/行为 = 「模拟新轮：…→代跑（hits+1，不重写）→新脚本落盘登记→收尾自动收集→S3 晋升→…」）。
- **basis**：spec §8 第 1 条（spec 行 207）「命中既有 l0_config_keys/l0_registry_check 并代跑（hits+1）」以「**已晋升技能级**」为前提，未晋升则计入 reused_scripts[]；spec §7 M5/§8 验收以试点回放验证。已核实试点现状：`var\registry\scripts.json` 不存在、`var\queue\candidates\*.json` 为空（无一脚本晋升过技能级）。故 5.2 在同一序列里「代跑（hits+1）」时脚本尚未晋升→按 §8#1 应得 `reused_scripts[]`，**而非** hits+1；「S3 晋升」又在代跑之后。要让 §8#1 的 hits+1 可证，必须先完成一轮「采集+S3 晋升」把 l0_* 晋入技能级，再在**新一轮**代跑才 hits+1。plan 单轮线性叙事掩盖了此两轮前置关系，回放脚本若照此实现，验收第 6 条（reused_count≥1 等）与第 1 条的 hits+1 无法同轮成立。
- **confidence**：高。

### S3. WBS-3.1 准入「命中计数」消费 hits 数据（由 WBS-4.1 产出），但 DAG 缺 4.1→3.1 边且二者被规划为并行
- **anchor**：plan 行 18（WBS-3.1 关键接口/行为 = 「准入（回归证据+命中计数：跨≥2 任务/同任务≥3 轮）」）；plan 行 29–33（DAG：`2.1→3.1→3.2`、`2.1→4.1→4.2`，3.1 仅依赖 2.1，4.1 在 2.1 后即可并行）。
- **basis**：spec §5 W4（spec 行 151）准入「命中计数（跨 ≥2 任务 或 同任务 ≥3 轮代跑）」；spec 自证声明 ④⑤（spec 行 218）hits 写入者=编排者代跑钩子（即 WBS-4.1 的 run_registered），「≥3 轮=跨轮次代跑、以快照 round 计数」。故 3.1 的「命中计数」须读 WBS-4.1 维护的 hits/round 数据。plan DAG 未列 4.1→3.1 依赖边，且构建顺序把 3.1 与 4.1 并行（plan 行 33「4.1 在 2.1 后即可并行」），导致机制准入在真实数据路径上只能拿到 2.1 写入的初始 hits=0，无法据实判定「≥2 任务/≥3 轮」。试点以合成夹具规避（plan §五诚实口径），故不挡 M3/§8#5，但机制生产链（plan 标题即「脚本复用与积木化」）缺一条依赖边。
- **confidence**：中。

---

## 三、轻微

### m1. 复用台账 `new_scripts[]` 产端与「收尾自动收集」触发点无节点承载（且不在 WBS-5.3 补记清单）
- **anchor**：plan 行 21（WBS-4.2 只读 reuse_ledger）；plan 行 24（WBS-5.3 补记清单 = m2-res/m4-res/mB-res/g1，不含 collect_candidates 触发）；plan 行 41（§四「C 自动收集入 candidates 在 1.2+2.1 收尾触发」）。
- **basis**：spec §4.5（spec 行 120–121）reuse_ledger 含 `new_scripts[]`；spec §5 W2（spec 行 139）「触发点=收尾 §6 / collect_snapshot 后」。plan 无任何节点说明 `new_scripts[]`（本轮新写脚本）由谁累积，也未把「收尾触发 collect_candidates」落成节点或明确其为编排者手动动作；WBS-5.3 补记清单只覆盖 run_registered 调用方（m2-res），未覆盖 collect_candidates 触发（§8 第 3 条采集链依赖）。
- **confidence**：中。

### m2. WBS-1.1 关键接口未列举 spec W1 的 `task_registry_path(task_id)`
- **anchor**：plan 行 14（WBS-1.1 关键接口/行为）。
- **basis**：spec §5 W1（spec 行 133）接口清单含 `task_registry_path(task_id) -> Path`。plan WBS-1.1 只列「容器 read/write、register_l0、compute_hash、record_found_issues」，未列该路径辅助函数。为文档完整性/契约对齐缺口，非结构性。实现大概率仍会写，但节点契约未全枚举。
- **confidence**：高。

### m3. WBS-3.1 积木注册表登记未含 spec §4.4 的 `source` 与 `catalog_ref`
- **anchor**：plan 行 18（WBS-3.1 行为「积木注册表登记（version/params/changelog）」）；plan 行 19（WBS-3.2 catalog）。
- **basis**：spec §4.4（spec 行 111–115）积木条目含 `params/changelog/hash/code_path/source{task_id,script}/catalog_ref`。plan WBS-3.1 登记仅列 version/params/changelog，未列 source（溯源到任务/脚本）与 catalog_ref；而 WBS-3.2 生成 catalog 需 source 溯源。属登记字段不完整。
- **confidence**：高。

### m4. plan §四映射行「WBS-5.x ↔ spec §7 M1–M5」错置（M1–M4 实为 WBS-1.x–4.x）
- **anchor**：plan 行 44（§四「WBS-5.x ↔ spec §7 M1–M5、§8 验收、…」）。
- **basis**：spec §7（spec 行 195–201）M1 骨架=W1+W2（即 WBS-1.x）、M2 晋升=W3（WBS-2.1）、M3 积木=W4+W5（WBS-3.x）、M4 观测=W6（WBS-4.x）、M5 试点=W7+W8（WBS-5.x）。plan §四将 M1–M5 一并归到 WBS-5.x，与 §四前四行（WBS-1.x↔W1/W2 等）及 WBS 自身结构自相矛盾；应为「WBS-1.x–5.x ↔ M1–M5」或「WBS-5.x ↔ M5」。
- **confidence**：高。

### m5. 上位需求对现行 `sediment_run.py` 的「不建 done/failed」表述与现行 phase_S3 不符（交叉资料事实核查）
- **anchor**：plan 行 22（WBS-5.1 行为「var\queue\{candidates,done,failed}\ 建目录」）；plan 行 17（WBS-2.1 done/failed 归档）；对照 `scripts\sediment_run.py` 行 387–389。
- **basis**：需求清单 §二（行 25）称「sediment_run.py（596 行）只 ensure_dir("queue/candidates")、不建 done/failed」。但现行 `phase_S3` 行 387–389 已 `ensure_dir(state/"queue"/"done")` 与 `ensure_dir(state/"queue"/"failed")`——即 phase_S3 运行时确实创建 done/failed（仅 596 骨架循环 `("snapshots/pending","snapshots/settled","backup","queue/candidates","registry")` 不含 done/failed）。需求清单该句混淆了「骨架循环(596)」与「phase_S3(387–389)」。plan 继承该前提（WBS-5.1 建目录），与现行代码兼容故无结构性影响，但上位依据表述失准，且 plan 未识别此差异。
- **confidence**：高。

### m6. WBS-2.1 直接依赖未列 WBS-1.1（compute_hash），且未含 spec W3「候选缺 task_id 则取被审对象名注入」回退
- **anchor**：plan 行 17（WBS-2.1 依赖 = WBS-1.2/1.3；行为 = 写技能级条目 task_id/code_path/hash）。
- **basis**：spec §5 W3（spec 行 146）「写技能级 var\registry\scripts.json 条目含 task_id（来源=候选 task_id；**候选缺则取被审对象名注入**）…+hash（compute_hash）」。plan WBS-2.1 依赖未列 WBS-1.1（compute_hash 来自 1.1，目前靠 1.2→1.1 传递），且行为未记「候选缺 task_id 注入被审对象名」回退。属数据链细节缺失。经核对现行 phase_S3（行 391–409）确无 task_id 注入与 hash 计算——WBS-2.1 需新增。
- **confidence**：中。

### m7. WBS-5.3 的 g1「积木 code_path 定绝对」与 spec §4.4 示例相对路径不符（plan 继承 spec 内部不一致）
- **anchor**：plan 行 24（WBS-5.3 g1「积木 code_path 定绝对」）→ 与 spec §4.4 对照。
- **basis**：spec §4.4（spec 行 112）积木示例 `"code_path": "skills/_shared/bricks/norm_num.py"`（相对路径），而 spec §6 归档项 g1（spec 行 188）「积木 code_path 相对/绝对约定——定绝对、与 R3 一致」。spec 两处不一致；plan（WBS-5.3）采纳「定绝对」，但 plan WBS-3.1 登记（行 18）未明示 code_path 绝对值，与 WBS-3.1 登记产物之间需在落码时统一。
- **confidence**：中。

---

## 四、建议

### s1. WBS-1.3 自验「正/反例各过」应点名具体夹具
- **anchor**：plan 行 16（WBS-1.3 节点自验 = 「正/反例各过」）。
- **basis**：spec §4.2/§8 第 3 条口径（确定性字段全齐即过、found_issues null+pending 不算缺）。「正/反例」未给出反例构造点（如缺 name/ns/task_id、regression 残缺、found_issues null 带 pending 等），实际执行时易空转或边界不清。建议列出 R2 schema 的最小正例/反例清单。
- **confidence**：低。

### s2. plan §五 诚实声明只标 WBS-3.1 合成夹具，未明示 2.1/4.x 自验依赖试点渐进数据（非仅 3.1 需夹具）
- **anchor**：plan 行 48–50（§五诚实声明与遗留）。
- **basis**：已核实 `var\queue`、`var\registry`、`skills\_shared\` 均为空，试点现仅任务级 registry + 2 个 l0 脚本。2.1/4.1/4.2 的自验依赖前序节点先跑出 candidates/技能级条目/快照（链式用试点自身数据），此依赖 path 未在诚实声明中说明，易被误读为「各节点可独立空跑」。建议补充「节点自验按 1.2→2.1→4.x 渐进用试点数据，仅 3.1（通用片段识别）需合成夹具」的说明。
- **confidence**：低。

### s3. WBS-5.1「建 queue\{candidates,done,failed}」与现行 phase_S3 已建的 done/failed 冗余，可注明仅为确认/幂等
- **anchor**：plan 行 22（WBS-5.1 行为）；对照 `sediment_run.py` 行 387–389。
- **basis**：phase_S3 行 388–389 已 `ensure_dir(queue/done)`、`ensure_dir(queue/failed)`。WBS-5.1 预建目录不冲突，但建议注明其角色（补数/幂等确认），避免与 phase_S3 职责重复表述。
- **confidence**：低。

---

## 五、审查过程说明（独立性与证据边界）

- 未 fork、仅喂「对象+交叉依据」；未使用任何会话历史结论。
- 试点目录另含 `fire-xlsx-zhuze-xuebu`、`登记表竹箦对抗审查` 两个任务级目录（已见 `var\task-scripts\`），说明「跨≥2 任务」准入在数据面有真实载体（与 S3 相关）；本审查未深入其脚本是否含可复用通用片段，留待步骤 7 以实际数据校准。
- 全部锚点以行号/节点号标注，未复述原文；每条均含 anchor/basis/confidence。
