# 技术设计 spec.md · 独立对抗性审查意见单（干净上下文，非 fork）

- 审查对象：`docs/spec.md`（「adversarial-review 脚本复用与积木化升级」技术设计，v1.0）
- 判定基准：`docs/升级需求清单.md`（R1–R8 + A–F 裁决 + §八/§九）；`SKILL.md §2`；`scripts/sediment_run.py`（phase_S3 385–409/596 行）；`scripts/collect_snapshot.py`；`scripts/{ledger,diff_scope}.py`；`references/protocols.md`；`docs/升级需求清单-复审意见单.md`（c-m1..m4 / c-s1）；`var/task-scripts/pdf-parse-v3/` 实测（registry.json、l0_config_keys.py、l0_registry_check.py、README.md）。
- 立场：独立子审查者，不预设结论，不沿用任何会话结论；只依据上述材料独立判断。
- 判定口径：同 protocols.md §4.1（阻断/严重/轻微/建议），通过判据=阻断清零∧严重清零。

---

## 一、各级条数

| 级别 | 条数 |
|---|---|
| 阻断 | **0** |
| 严重 | **2**（s1 / s2） |
| 轻微 | **9**（m1–m9） |
| 建议 | **4**（g1–g4） |

---

## 二、严重（触发修复循环）

### s1·严重·高——R2 候选的语义字段（found_issues）无生产者，W2 无法产出「全字段齐全」的合法候选
- **anchor**：spec.md §5 W2（128–130 行）、§4.2 候选 schema（85–91 行）、§8 验收第 3 条（188 行）；对照需求清单 §九 R2（228 行）。
- **basis**：W2 `collect_candidates` 明示生成 `code_path / description / test_problem / environment / regression` 五个字段，**未生成 `found_issues`**；而 §4.2 候选 schema 与需求清单 §七 R2（148–150 行）均把 `found_issues` 列为候选字段，§8 验收第 3 条更要求「R2 全字段齐全」。`found_issues`（该脚本测出的问题）是**审查语义产物**，确定性脚本无法凭空产生，且 §九 R2 只把 LLM 的一处语义判断指派给 `description/test_problem`，**未指派 `found_issues` 的填充者**。故：W2 产出的候选**缺 `found_issues`**，与「R2 全字段齐全/校验通过」（§7 M1 出口、§8 第 3 条）直接冲突——M1 的出口判据在 W2 原样实现下不可达成。
- **confidence**：high（W2 字段清单、§4.2/§七 R2 schema、验收第 3 条均实测比对，缺口确凿）。

### s2·严重·中——W1 registry 读写接口与试点 registry.json 的容器结构不闭合
- **anchor**：spec.md §4.1（74–82 行）、§5 W1（122–126 行）；对照 `var/task-scripts/pdf-parse-v3/registry.json`（实测为 `{namespace, target, updated, location_rule, scripts:[条目]}`）、`l0_registry_check.py` 第 24 行 `data.get("scripts", [])`。
- **basis**：§4.1 把任务级 registry「条目」schema 定义为裸对象（name/ns/code_path/entrypoint/run/purpose/hash/found_issues），W1 `read_registry(path) -> list[entry]` / `write_registry(path, entries)` 亦按「裸条目列表」建模；但试点 `registry.json` 实际是**带容器包装**的对象（含 `namespace/target/updated/location_rule` 及 `scripts` 数组，`l0_registry_check` 以 `data["scripts"]` 读取证实）。W1 若按 `write_registry` 写回一条裸数组，会**覆盖/丢失**容器层既有元数据（尤其 `location_rule`——该字段在 README.md 第 4 行作为 R1/R3 定稿说明被引用，第 25 行亦显式援引）。模块接口与既有数据容器不闭合，「可落地到既有代码」在此点存在风险。
- **confidence**：medium（容器结构已在实物核实；接口能改写为兼容写法，故降为严重而非阻断）。

---

## 三、轻微（记录归档，不触发修复循环）

### m1·轻微·中——W2 回归运行的运行命令/参数取参来源未指定
- **anchor**：spec.md §5 W2（129 行）；对照 `l0_config_keys.py`（需传被审对象根参数，见 README.md 第 19 行）、`l0_registry_check.py`（无需参数）。
- **basis**：W2 扫描 `l0_*.py` 生成候选并取 `regression=运行结果快照`，但未指明「如何运行」——命令与参数从何而来（任务级 registry 的 `run` 字段，还是 docstring 复跑行）未定义。试点中 `l0_config_keys` 必须带 `<pdf-parse-v3 根>` 参数，W2 若只按文件名裸跑会失败/取到错误回归证据。属可落地性缺口（步骤 7 应明确取参规则）。

### m2·轻微·中——run_registered 的触发接线点未定，且技能级条目按 name 寻址、无 task_id 去重
- **anchor**：spec.md §5 W6（147–148 行）、§4.3（93–98 行）；对照 `SKILL.md §2` 第 43 行（「代跑一次即 hits+1」）。
- **basis**：W6 给出 `run_registered(name, task_id)` 签名与「技能级条目 hits+1（若已晋升）」语义，但未说明该运行入口由**哪个既有流程/脚本**调用；`SKILL.md §2` 仅述「编排者侧运行」，当前五个脚本（sediment_run/collect_snapshot/ledger/diff_scope/sediment_check）均不调用它。此外 §4.3 技能级条目以 `name` 为唯一寻址键、字段表**无 task_id**，跨任务若出现同名脚本（如不同任务各有 `l0_gate.py`），hits 会记错目标。需补充接线点与去重键。

### m3·轻微·低-中——W4 准入「同任务 ≥3 轮代跑」的跨轮计数无落点
- **anchor**：spec.md §6 c-m4（167 行）、§5 W4（139 行）、§4.3（93–98 行）、§4.5（109–114 行）。
- **basis**：c-m4 界定「命中=编排者代跑一次、≥3 轮=不同轮次被代跑（以快照 round 计数）」，作为 W4 准入口径；但**未晋升候选脚本**的「被代跑」只逐条记在各轮 R7 台账 `reused_scripts[]` 中（§4.5，随 snapshot 逐轮存），而 `hits` 仅对**已晋升**技能级条目计数（§4.3，`hits` 字段在技能级条目）。跨轮累计「≥3 轮」需要跨快照扫描聚合，spec 未定义该聚合的数据来源/落点。准入计数实际取数路径不明。

### m4·轻微·中——「每轮一行」复用台账与「并入一次性快照（聚合多轮）」尺度不一致；collect_snapshot.py 并不计算复用指标
- **anchor**：spec.md §4.5（109–114 行「每轮一行，并入 §7.1 快照扩展字段」）、§5 W6 收尾（150 行）、§7 M4（179 行）；对照 `references/protocols.md` §7.1（123–148 行，`rounds` 为整数、`tokens` 为逐轮数组）、`collect_snapshot.py`（`validate` 只校验必含/枚举，`main` 只解析+落盘，无 registry/脚本访问）。
- **basis**：`collect_snapshot.py` 本身不读取任务 registry、不跑脚本、不算复用命中，因此「复用台账字段」只能由**调用方**在 stdin JSON 中提供；且快照是单次运行聚合多轮（`rounds` 整数），而 §4.5 台账是「每轮一行」单轮对象——两者尺度不同。W6 措辞「collect_snapshot.py 增复用台账字段」易被误读为脚本自行计算。需说明复用台账在快照内的承载方式（逐轮数组 vs 顶层对象）与填充方。

### m5·轻微·中——l0_registry_check 未校验 hash，使 §4.1 声称的必填 hash 不受「事实源自洽」守护
- **anchor**：spec.md §4.1（80 行，hash 为必填）、§8 验收第 2/4 条（187/189 行）；对照 `l0_registry_check.py` 第 13 行 `REQUIRED = ("name","ns","code_path","entrypoint","run","purpose")`（不含 hash）。
- **basis**：§4.1 把 `hash` 定为任务级条目必填，但确定性自洽守护 `l0_registry_check.py` 的 REQUIRED 集合不含 `hash`；因此若某任务级条目漏填 hash（c-m1 缺口在试点期未补），验收第 2 条 `bad=0` 仍通过、第 4 条「技能级条目含 code_path+hash」也不会红。c-m1 的 hash 实现缺口头在「可执行事实源自洽」层缺一道确定性防线。

### m6·轻微·低——W4 独立脚本 vs 需求 R4「S3 扩展」的耦合关系未注明
- **anchor**：spec.md §5 W4（138 行）、§5 W3（132 行）；对照需求清单 §三 R4 动作（62 行「沉淀时把任务脚本拆解/归并为积木」）、§九 R4 分工（230 行）。
- **basis**：需求 R4 把「拆积木」表述为 phase_S3（`sediment_run.py`）的**扩展动作**；spec 却将其拆为独立新脚本 `_extract_bricks.py`（W4）「沉淀阶段触发」，且未注明 W4 在 `phase_S3` 内的调用位（是与 W3 并列的 S3 子步，还是沉淀流程的独立阶段）。界限可落地但不含需求所述「S3 扩展」的耦合说明。

### m7·轻微·低——M5「验收 §8 全项通过」未覆盖 R8 条文
- **anchor**：spec.md §7 M5（180 行）、§5 W7（152–153 行）、§9 诚实声明⑤（200 行）。
- **basis**：M5 出口为「验收 §8 全项通过」，但 §5 W7 与 §9⑤ 均明示 R8 条文（跨任务先查 catalog）**尚未写入 SKILL.md**（按需求清单 §六 待 R1/R3 稳定后落）。R8 的**能力**（跨任务 import）虽由 §8 第 5 条覆盖，R8 **条文**本身未纳入任何里程碑/验收——与需求 §六 一致（已登记待办），但「全项通过」措辞不完备，宜注明 R8 条文不在 M5 出口内。

### m8·轻微·中——验收第 1 条（hits+1）与第 4 条（晋升链）存在时序依赖且未阐明
- **anchor**：spec.md §8 第 1 条（186 行）、第 4 条（189 行）、§5 W6（148 行「若已晋升」）、§5 W8 回放顺序（156 行）。
- **basis**：hits+1 依定义仅对**已晋升**技能级条目计数（§5 W6「若已晋升」）；而 W8 回放把「复用 l0_config_keys/l0_registry_check（hits+1）」排在「S3 晋升」**之前**（156 行）。在首次/新轮试点（技能级 scripts.json 尚空，§二 现状已证 `var/registry/scripts.json` 不存在）下，脚本尚未晋升、hits 无从 +1——第 1 条的「hits+1」需在「先前轮已晋升」的前提下才能演示。回放顺序与验收第 1 条之间存在前置关系未阐明。

### m9·轻微·低——M3 示例积木在试点脚本中未见明显可提取的通用片段
- **anchor**：spec.md §7 M3（178 行「如 `norm_num`/`cluster_1d`」）、§5 W8（156 行）；对照试点脚本 `l0_config_keys.py`（cfg 键路径一致性，任务特定）、`l0_registry_check.py`（registry 自洽）。
- **basis**：M3 出口为「≥1 示例积木入库且 catalog 含其条目」，举例 `norm_num`/`cluster_1d`；但试点仅两条 `l0_*` 脚本均**任务特定**（pdf-parse-v3 的 cfg 键、registry 自洽），从中抽取「跨任务通用纯函数」（数值聚类/规格归一）并无显然来源。M3 的示例积木当从哪个片段提取、是否符合 R4 硬约束 a（剥掉任务特定逻辑、保留参数化纯函数），需在试点回放中先有实际候选再定，否则 M3 出口可能空转。

---

## 四、建议（仅列示，不驱动修复）

### g1·建议·低——§4.4 积木条目 `code_path` 用相对路径，与 §4.1/§4.3 的绝对路径约定不一致
- **anchor**：spec.md §4.4（103 行 `"code_path": "skills/_shared/bricks/norm_num.py"`）；对照 §4.1（77 行）、§4.3（96 行，均「绝对路径」）、§6 c-s1（168 行「迁移时更新 registry code_path」）。
- **basis**：任务级/技能级条目均按 R3 定稿用**绝对路径**（可执行事实源），§4.4 积木条目却是相对路径 `skills/_shared/bricks/…`。积木库统一迁至共享根（§9 ②/§6 c-s1）后，相对路径解析基准易漂移；建议统一为绝对路径（或明确其解析基准）。

### g2·建议·低——§4.5 复用台账字段名 `round` 与 §7.1 顶层 `rounds` 易混
- **anchor**：spec.md §4.5（111 行 `"round": "r3"`）；对照 protocols.md §7.1（138 行顶层 `"rounds": 2`）。
- **basis**：单轮台账用 `round`、快照顶层用 `rounds`，含义相邻、命名易混淆；建议把复用字段置于顶层对象（如 `"reuse": [{…}]`）并在协议 §7.1 中作唯一命名，避免语义歧义。

### g3·建议·低——§5 W5 catalog 清单内容缺「适用任务」维度
- **anchor**：spec.md §5 W5（145 行，积木名→作用→适用 ns→路径→entrypoint→复跑法）；对照需求清单 R5（73 行，积木名→作用→**适用 ns/任务**→模块路径→entrypoint→单测/复跑法）。
- **basis**：需求 R5 清单含「适用 ns/**任务**」，W5 `gen_catalog` 只列「适用 ns」，缺少「任务」维度；跨任务发现（R8 先查 catalog）时缺任务来源线索，建议补齐。

### g4·建议·低——§3 树将 done/failed 标为「新建」，实为 phase_S3 已建
- **anchor**：spec.md §3 目录树（60 行 `done\ failed\ # S3 晋升/失败归档（新建）`）；对照 `sediment_run.py` phase_S3（388–389 行 `done = ensure_dir(state/"queue"/"done")`、`failed = ensure_dir(...)`）。
- **basis**：phase_S3 执行时已 `ensure_dir` 建 `done`/`failed`（387–389 行），并非「新建」类未落盘项；需求清单 §二 K3-m4 已把该点更正为「骨架声明、未落盘」（即目录只因 phase_S3 未运行才不存在）。§3「新建」标注与代码现状口径不符，建议更正为「phase_S3 运行时创建」，以保持与交叉资料一致。

---

## 五、结论（spec 可否进入步骤 5 plan.md 的 WBS 分解）

**可进入，但有 2 项严重需在步骤 5/7 前闭合；无阻断项。** 逐项证据与缺口：

**承接忠实性（①）——总体忠实，无走样。**
- 双轨 registry 语义（任务级=可执行事实源/技能级=晋升索引，code_path+hash 互指、不合并）：spec §2 不变式 / §4.1 / §4.3 与需求清单 §七 R3 双轨、SKILL.md §2 一致。
- 任务目录 `var\task-scripts\<task-id>\`：spec §2/§3 与需求清单 §七 R1、README.md 第 3 行一致。
- 积木库单一位置：§2/§3 树把 `skills\_shared\bricks\` 画为 `adversarial-review\` 的**同级**（即 `~\.agents\skills\_shared\bricks\`），与 §4.4 相对路径 `skills/_shared/bricks/…`、§6 c-s1、§9 ② 及需求 R4/A-S5（单一确定位置）一致——**无位置矛盾**（已核实缩进层级）。
- 准入「回归+计数」、R7「归属技能级+写入者」、自动收集触发点（收尾 §6 / collect_snapshot 后）：均已在 spec §4.3/§5 W2/W4/W6 有落点且与需求 §九 对拍不冲突。
- **缺口**：仅 s1（found_issues 无生产者、W2 与 §九 R2 在语义字段上有冲突）与 s2（W1 接口未闭合试点容器）。

**自洽性（②）——schema 主体闭合，两处崩口。**
- 任务级/候选/技能级/积木注册表/复用台账的字段互引总体闭合（§4.1/4.2/4.3/4.4/4.5）；found_issues 在任务级 registry（§4.1 可选）与候选（§4.2）两处均有，符合 c-m3/R2 去向②。
- **缺口**：s2（W1 read/write 接口与试点容器包装不闭合）；以及 m2（技能级条目无 task_id，跨任务同名去重缺失）、m5（hash 不受 l0_registry_check 守护）等次要非闭合点。

**可落地性（③）——对既有代码的扩展/改写点均存在且可接。**
- phase_S3（385–409 行，读 name/ns/version/regression.passed → 写 {name,ns,version,hits,false_positives,registered_at} → 归档 done/failed）确实存在，W3「读 R2 全字段/写 code_path+hash/幂等哈希去重/按 regression.passed 归档」的各接点在代码中是真实可改位。sediment_run.py 596 行骨架 build（queue/candidates、registry）属实；SKILL.md §2 已含双轨/task-scripts/docstring 四行条文。
- **缺口**：m1（W2 取 run 参数来源）、m6（W4 与 phase_S3 耦合位）、m3（≥3 轮计数落点）等接线细节未闭。新增脚本（_registry_io/_collect_candidates/_extract_bricks/_gen_catalog）与既有 ledger/diff_scope/collect_snapshot/sediment_run 职责边界清晰，无冲突。

**度量口径（④）——与 protocols §7.1 兼容。**
- 复用台账字段并入快照：`collect_snapshot.py` 的 `validate()`（74–119 行）只校验必含字段/枚举，**不拒绝多余顶层字段**，故新增 reuse 字段与 §7.1 兼容；`W≈ceil(字符数/2)` 与需求 R7 §九 分母口径一致（相对量、注明估算口径，见 spec §9 诚实声明③）。无硬冲突，仅 m4（承载方式/填充方）与 g2（命名 `round` vs `rounds`）两处细节。

**里程碑/验收可测性（⑤）——主体可测，两处出口风险。**
- M1/M2/M4/M5 出口（合法候选/技能级含 code_path+hash 且幂等/snapshot 含复用字段且计数>0/§8 全项）均可实测。
- **风险**：M1 出口「R2 schema 校验通过」在 s1（found_issues 未产）下有走空风险；M3 出口「≥1 示例积木」在 m9（试点脚本无显然通用片段）下有走空风险；此外 §8 第 1/4 条存在 m8 的时序依赖待澄清。

**综合**：spec 作为「模块分解+接口契约级」技术设计，骨架自洽、对需求 R1–R8/A–F/§八/§九 承接总体忠实、跨引用类目（c-m1..m4/c-s1）均已在 §6/§4 有落点且经核对真实覆盖（唯一例外：c-m1 的 hash 守护在 l0_registry_check 层缺口，见 m5）。建议顺序：先闭合 s1（为 found_issues/test_problem 明确生产者，或把 W2 产出的候选放宽为「字段可事后填充」并修正验收第 3 条口径）与 s2（W1 接口补充容器包装读写），再进入步骤 5 plan.md 的 WBS 分解；其余轻微/建议可在步骤 5/7 顺手落实。
