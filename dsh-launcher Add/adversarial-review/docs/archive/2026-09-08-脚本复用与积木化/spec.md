# 技术设计：adversarial-review 脚本复用与积木化升级（spec.md）

| 字段 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-09-07 |
| 上位依据 | 《升级需求清单.md》v1.0（R1–R8 + A–F 裁决 + §八/§九；下称**需求清单**）；用户 9 步流程之步骤 3 |
| 需求复审输入 | 《升级需求清单-审查意见单.md》（轨 A）、《升级需求清单-审查意见单-K3.md》（轨 B K3）、《升级需求清单-复审意见单.md》（增量复审：阻断/严重已清零） |
| 覆盖项 | 复审归档 c-m1 / c-m2 / c-m3 / c-m4 / c-s1（本设计 §6 逐条落点） |
| 现状资产 | `SKILL.md` §2（已同步双轨）；`var\task-scripts\pdf-parse-v3\`（R1/R3 试点）；`scripts\sediment_run.py`、`scripts\{ledger,diff_scope,collect_snapshot}.py` |
| 非目标 | 真插件/包管理系统、全自动测试生成器、语义 prompts 库（需求清单 F） |

---

## 1. 目标与范围

把 L0 确定性验证脚本从「每轮重写」升级为「一次推导、多地复用、保持独立、浪费可计量」的机制，按需求清单 R1–R8 落地：

- **R1/R6**：任务级脚本落盘与同任务跨轮复用（已部分落地，补齐执行器）；
- **R2/R3**：候选采集与双轨 registry（任务级=可执行事实源；技能级=晋升注册表）；
- **R4/R5**：沉淀拆解为跨任务通用函数积木 + 跨任务可用清单；
- **R7**：复用收益可观测；
- **R8**：跨任务复用通道。

**验证方式（试点）**：以 pdf-parse-v3 v4 审查（已有意见单/脚本/任务级 registry）为首个试点，全流程回放验证。

---

## 2. 总体架构（两级资产 + 三级 registry 语义）

```
任务级（per-task）                         技能级（cross-task）
adversarial-review\var\task-scripts\        adversarial-review\var\registry\scripts.json
  <task-id>\                                （S3 晋升注册表：元数据索引，不直接运行）
    l0_*.py        ————————— code_path/hash 互指 —————————
    registry.json（任务级，可执行事实源）
    README.md
                              skills\_shared\bricks\        （跨任务通用函数积木库）
                                registry.json（积木注册表）
                                catalog.md / catalog.json  （R5 可用积木清单）
链路：落盘(R1) → 采集(R2,candidates) → 自动收集(§6 收尾,C) → 回归晋升(S3 扩展) →
      拆解积木(R4) → 清单(R5) → 同任务复用(R6) / 跨任务 import(R8) → 观测(R7)
```

**双轨不变式**：任务级 registry 是事实源（脚本真实存在可运行）；技能级 scripts.json 是索引（元数据）；不合并，靠 `code_path`（+hash）互指。技能级两类资产（scripts.json 脚本晋升注册表 / bricks+catalog 函数积木）在 §6 c-m2 处统一建模。

---

## 3. 目录布局（目标文件树）

```
adversarial-review\
  var\
    task-scripts\<task-id>\        # R1：任务级脚本目录（试点 pdf-parse-v3 已存在）
      l0_<用途>.py                  # docstring 四行模板
      registry.json                # 任务级（可执行事实源）
      README.md
    queue\
      candidates\<name>.json       # R2：候选（自动收集写入）
      done\  failed\               # S3 晋升/失败归档（新建）
    registry\
      scripts.json                 # 技能级晋升注册表（S3 扩展写入）
    snapshot\…（既有，按 §7.1 扩展）
skills\_shared\bricks\             # R4：跨任务通用函数积木库（本设计定稿位置）
    <brick>.py                     # 参数化纯函数（形参带默认值）
    registry.json                  # 积木注册表（版本/参数变更说明/hash/code_path）
    catalog.md / catalog.json      # R5：可用积木清单（脚本生成，随晋升同步）
```

---

## 4. 数据 Schema（定稿）

### 4.1 任务级 registry（`var\task-scripts\<task-id>\registry.json`，可执行事实源）

文件为**容器结构**（闭合 s2：与试点实物一致）：`{namespace, target, updated, location_rule, scripts:[…]}`；下述为 `scripts[]` 内条目：

```jsonc
{"name": "l0_x", "ns": "code",
 "code_path": "<绝对路径>/var/task-scripts/<task-id>/l0_x.py",
 "entrypoint": "main",
 "run": "python …", "purpose": "…",
 "hash": "<内容 sha1>",
 "found_issues": ["…"]}            // 可选（R2 采集维度承载，c-m3 落点；语义字段见 s1 生产者约定）
```

**容器元数据纪律**：读写必须保留 `namespace/target/updated/location_rule`（README 引用了 location_rule），任何写回不得覆盖容器元数据（闭合 s2）。

### 4.2 候选（`var\queue\candidates\<name>.json`，R2）
```jsonc
{"name": "l0_x", "ns": "code", "task_id": "<pdf-parse-v3>",   // 闭合 NEW-sA：task_id 的生产源=收集器（W2）
 "version": "r1",
 "code_path": "<…>", 或 "code": "<内联源码>",   // 二选一（phase_S3 兼容两种来源）
 "description": "…", "test_problem": "…", "environment": "…",
 "found_issues": ["…"],                 // 语义字段：确定性脚本不产（闭合 s1）
 "regression": {"passed": true|false, "evidence": "输出快照/路径"}}
```

**字段生产者分工（闭合 s1/A-a）**：确定性字段（**name/ns/task_id**/version/code_path|code/environment/regression）由收集器 W2 产出；语义字段 **description/test_problem/found_issues 由评审者（LLM）回填**（description/test_problem 亦可由 docstring 四行模板派生后评审确认；found_issues 仅在评审/复审后回填，回填前允许 `null` + `"pending_review": true` 标注）——候选「R2 全字段」验收口径按此判定（见 §8 第 3 条），确定性字段缺即不合格，语义字段 `null`+pending 不算缺。

### 4.3 技能级晋升注册表条目（`var\registry\scripts.json`，S3 扩展写入）
```jsonc
{"name": "l0_x", "ns": "code", "version": "r1",
 "task_id": "<pdf-parse-v3>",                 // 补：跨任务同名去重的隔离维度（闭合 m2）
 "code_path": "<绝对路径，指回任务级脚本>", "hash": "<内容 sha1>",
 "hits": 0, "false_positives": 0, "registered_at": "…"}
```

### 4.4 积木注册表条目（`skills\_shared\bricks\registry.json`）
```jsonc
{"name": "norm_num", "version": "1.0.0",
 "code_path": "skills/_shared/bricks/norm_num.py", "hash": "<sha1>",
 "params": {"s": {"type": "str", "default": ""}},
 "changelog": "…", "source": {"task_id": "pdf-parse-v3", "script": "gate.py"},
 "catalog_ref": true}
```

### 4.5 复用台账（R7；并入快照可选扩展块 `reuse_ledger`，不与快照顶层既有字段冲突）
```jsonc
{"round": "r3", "reused_scripts": ["l0_x"], "new_scripts": [],
 "reused_count": 1, "new_count": 0,
 "est_saved_tokens": <reused_count × ceil(字符数/2)>}   // 相对量估算口径
```
并入方式：收尾快照顶层增可选 `"reuse_ledger": {…}`（快照顶层既有 `rounds`（int）字段不变，无命名冲突；g2/mC-res 落点）。

---

## 5. 模块分解与接口契约（签名级）

> 执行体分工遵需求清单 §九：下列均为确定性脚本；LLM 仅评审判断与「拆/归并」裁决。

### W1 目录与 registry 读写层（`scripts\_registry_io.py`，新建）
- `task_registry_path(task_id) -> Path`（var\task-scripts\<task-id>\registry.json）
- `read_registry(path) -> dict`（返回**容器** `{namespace,target,updated,location_rule,scripts:[…]}`，闭合 s2-res：接口显式容器化）
- `write_registry(path, container)`（**原子写**：临时文件+rename；写回整个容器，meta 由调用方原样保留）
- `register_l0(task_id, script_path, purpose, found_issues=None)`：读 `<task-id>` 容器 → 增/改 `scripts[]` 条目（含 hash、可选 found_issues；**不写 task_id**——任务级目录本身即任务标识，task_id 仅用于候选 §4.2 与技能级 §4.3，闭合 A-b）→ 写回容器
- `compute_hash(path) -> sha1`

### W2 候选自动收集器（`scripts\_collect_candidates.py`，新建；触发点=收尾 §6 / collect_snapshot 后）
- `collect_candidates(task_id) -> list[candidate]`：扫描 `var\task-scripts\<task-id>\` 下未登记进 candidates/done 的 `l0_*.py`；对每个生成候选（确定性字段：**task_id**（取任务名）、code_path、environment=python/依赖、regression=运行结果快照、version 取 docstring/注册版本；`run` 取 docstring 四行「复跑」行；description/test_problem 由 docstring 派生并待评审确认）
- **语义字段回填点**：`found_issues`（及 test_problem 终稿）由评审者（LLM）在收尾/复审时回填（`_registry_io.record_found_issues(name, issues)`），回填前候选置 `"found_issues": null, "pending_review": true`（闭合 s1，确定性脚本不造语义字段）
- 门槛：仅 `regression.passed=True` 的进 candidates；失败的记 failed 证据。

### W3 phase_S3 扩展（改 `scripts\sediment_run.py` `phase_S3`）
- 读：R2 全字段（name/ns/**task_id**/version/code_path|code/description/test_problem/environment/found_issues/regression）；
- 写：技能级 `var\registry\scripts.json` 条目含 **task_id**（来源=候选 task_id；候选缺则取被审对象名注入）+`code_path`（绝对）+`hash`（compute_hash）——闭合 NEW-sA（task_id 生产者链：W2 候选 → W3 晋升写入）；
- 归档：`var\queue\{done,failed}\`（新建目录）按 regression.passed 归置；
- 幂等：同 hash 已存在 → 只更新 registered_at/version，不重复注册。

### W4 积木提取器（`scripts\_extract_bricks.py`，新建；沉淀阶段触发）
- 准入（R4）：片段持来源 `regression.passed` 且 命中计数（跨 ≥2 任务 或 同任务 ≥3 轮代跑）→ 才可晋升；
- 拆解：从候选脚本中识别通用片段（剥离任务特定逻辑为「胶水」），产出**参数化纯函数**（形参带默认值）→ 写 `skills\_shared\bricks\<name>.py`；
- 登记：积木注册表（version/params/changelog/hash/code_path/source）；扩参=版本升级（v.x+，登记变更说明）。
- **LLM 裁决点**：「何时该拆 / 归并到哪」由评审/编排 LLM 判断（低频），提取与去重机械动作由脚本完成。

### W5 catalog 生成器（`scripts\_gen_catalog.py`，新建；随晋升同步）
- `gen_catalog(bricks_dir) -> (catalog.md, catalog.json)`：从 bricks 目录+注册表确定性生成清单（积木名→作用→适用 ns→路径→entrypoint→复跑法）。

### W6 复用观测钩子（改 `scripts\_registry_io.py` 运行入口 + `collect_snapshot.py`）
- `run_registered(name, task_id)`：代跑前查任务级 registry；**代跑一次→对应技能级条目 hits+1**（若已晋升）；未晋升脚本计数记 `reused_scripts[]`（R7 台账来源之一）。
- `record_false_positive(name)`：复审/收尾判定误报 → 技能级条目 false_positives+1。
- 收尾：`collect_snapshot.py` 增复用台账字段（§7.1 schema 扩展：round/reused_scripts[]/new_scripts[]/counts/est_saved_tokens）。

### W7 SKILL.md 条文（已同步，2026-09-07）
§2 已含：L0 指任务级 registry、registry 双轨、落盘 var\task-scripts、docstring 四行模板。R8 条文（跨任务先查 catalog）按需求清单 §六 待写（R1/R3 稳定后一并落）。

### W8 试点验证（`tests\` 或 `var\task-scripts\pdf-parse-v3\`）
- 用 pdf-parse-v3 v4 审查场景回放：模拟新审查轮启动 → 先查任务级 registry → 复用 l0_config_keys / l0_registry_check（hits+1）→ 新发现脚本落盘登记 → 收尾自动收集候选 → S3 晋升（写技能级 code_path/hash）→ 提取 1 个示例积木 → catalog 生成 → R7 台账非空。

---

## 6. 复审归档项的设计落点（c-m1..c-m4 / c-s1）

| 复审项 | 设计落点 |
| --- | --- |
| c-m1 hash/code_path 实现缺口 | W1 `compute_hash` + W3 phase_S3 写技能级 `code_path/hash`（§5）；步骤 7 必做 |
| c-m2 §八 模型缺技能级 scripts.json 框 | §2 架构图与 §4.3 并列技能级两类资产（scripts.json 晋升注册表 / bricks+catalog） |
| c-m3 任务级 schema 缺 found_issues | §4.1 任务级 schema 增**可选** `found_issues` 字段（R2 去向②承载） |
| c-m4 R4「同任务≥3 轮命中」口径 | 命中 = 编排者代跑该脚本一次（hits 事件）；「≥3 轮」= 该脚本在 ≥3 个不同轮次被代跑（以快照 round 计数）；写入准入规则（§5 W4） |
| c-s1 task-scripts 通用化升共享根路径 | 定稿：通用化后 task-scripts 迁入 `~\.agents\skills\_shared\task-scripts\<task-id>\`（与 bricks 同根），迁移时更新 registry `code_path` |

**spec 对抗审查（步骤 4）闭合与归档（2026-09-07）**：
- **s1 已闭合**：§4.2 字段生产者分工 + §5 W2 回填点 + §8 第 3 条口径（found_issues 允许 null+pending_review，确定性字段全齐即过）。
- **s2 已闭合**：§4.1 容器模型 + §5 W1 容器读写（保 meta，不裸数组覆盖）。
- **m2 已闭合**：§4.3 技能级条目增 `task_id`（跨任务同名去重隔离）。
- **m9 已处理**：M3/§8 第 5 条改「机制验证（合成夹具产出/无片段诚实空）」，消除走空风险。
- **A-a/A-b 已闭合**：§4.2 确定性字段列举补 `task_id`；W1 `register_l0` 任务级条目不写 `task_id`（目录即任务标识），与 §4.1/试点实物一致。
- **r2 复审遗留（步骤 7 实现清单，非阻塞）**：m2-res（`run_registered` 需调用方——收尾/编排流程接线时定）、m4-res（`collect_snapshot.py` 现行不自行算复用指标——W6 落码时加）、m5-a（试点条目当前无 hash——步骤 7 回填 + `l0_registry_check.REQUIRED` 加 hash）、mB-res（去向②任务级 `found_issues` 无填充者——与 s1 同评审回填路径，落码补 `record_found_issues` 调用点）、g1（§4.4 积木 code_path 相对/绝对约定——定绝对、与 R3 一致）。
- **归档（步骤 5/7 落实）**：m1（W2 `run` 取 docstring「复跑」行——已在 W2 注明）、m3（≥3 轮计数以快照 round 落点——见 c-m4 行）、m4（复用台账承载=快照扩展字段，见 §4.5）、m5（`l0_registry_check.REQUIRED` 增 `hash`——**步骤 7 落码必做**，届时需回填试点条目 hash）、m6（W4 拆解触发挂 phase_S3 之后、沉淀阶段 S2/S3 之间，耦合位实现时定）、m7/m8（时序依赖：M5 回放先于 §8 第 1/4 条真实计时序执行）、m9（见上）、g1–g4（g2：快照字段名用 `rounds` 与既有 schema 一致；其余设计/命名细节步骤 7 顺手）。

---

## 7. 实现里程碑（为步骤 5 plan.md 预分解）

| 里程碑 | 内容 | 出口判据 |
| --- | --- | --- |
| M1 骨架（W1+W2） | registry 读写层 + 候选自动收集器 | 收集器对 pdf-parse-v3 目录产出 ≥1 合法候选：**确定性字段按 R2 schema 校验通过**（found_issues 允许 null+pending_review，闭合 s1） |
| M2 晋升（W3） | phase_S3 扩展（读新字段/写 code_path+hash/归档 done/failed/幂等） | 候选晋升后技能级条目含 code_path+hash；重跑不重复注册 |
| M3 积木（W4+W5） | 积木提取器 + catalog 生成器 | **机制验证**：对含通用片段的合成夹具产出积木（入库+登记+catalog 含条目）；对无片段输入如实输出空并声明（试点脚本小、可能无通用片段——诚实空结果即过，不虚构积木，闭合 m9 走空风险） |
| M4 观测（W6） | hits/false_positives 钩子 + 复用台账并入快照 | 试点回放生成的 snapshot 含复用字段且计数 >0 |
| M5 试点（W7+W8） | pdf-parse-v3 全链路回放 | 验收 §8 全项通过 |

---

## 8. 验收标准（试点，pdf-parse-v3 v4 审查）

1. **防重写**：模拟新一轮审查启动，任务级 registry 命中既有 `l0_config_keys`/`l0_registry_check` 并代跑（hits+1），**未重新编写同名脚本**（若该脚本尚未晋升技能级，其复用计入 R7 `reused_scripts[]`，闭环口径）；
2. **可执行**：`l0_registry_check.py` 对任务级 registry 判 bad=0；
3. **采集链**：收尾自动收集 ≥1 候选——**确定性字段全齐且 R2 schema 校验通过**；语义字段 `found_issues` 允许 null+pending_review（评审回填点存在即可；闭合 s1）；
4. **晋升链**：S3 扩展后技能级 `scripts.json` 条目含 code_path（绝对）+hash+task_id；幂等重跑不重复；
5. **积木链**：机制验证——对合成夹具（含通用片段）抽取 ≥1 积木入库+登记+catalog 含条目；对试点无通用片段如实声明（跨任务实例留后续任务补验，不虚构）；
6. **观测链**：snapshot 含复用台账（reused_count≥1、est_saved_tokens>0、含 est_saved_tokens 估算口径注明）。

---

## 9. 自证声明（G-008）

**关键决策清单**：① 双轨 registry（任务级事实源/技能级索引，code_path+hash 互指）——依据需求清单 R3 双轨裁决 + 复审 B1/S1 闭合；② 积木库单一位置 `~\.agents\skills\_shared\bricks\`——依据 A-S5 闭合；③ 准入=回归证据+命中计数——依据 A-S2 闭合 + S3「回归通过才晋升」；④ hits 写入者=编排者代跑钩子、归属技能级——依据 K3-M2/M3 闭合；⑤ c-m4「命中=代跑一次、≥3 轮=跨轮次代跑」——补 R4 口径（依据 R1 轮次入 version 与 R7 hits 定义）；⑥ 快照 schema 增复用字段——依据 R7 + protocols §7.1。

**已自检项**：G-001（阈值「跨≥2/≥3 轮」为设计给定初值，注明初值+校准点=试点沉淀后校准）；G-002（交叉引用指向真实文件：SKILL.md §2、sediment_run.py phase_S3、protocols §7.1）；G-005（边界显式：未晋升脚本复用记 reused_scripts[]、code_path|code 二来源兼容、幂等哈希去重）；G-006（无「原则上/一般情况下」措辞）；G-007（W1–W8、R1–R8 编号连续）。

**诚实声明（粒度边界）**：① 本设计为**模块分解+接口契约级**；W4 的「通用片段识别」给判据与边界，实际识别规则在步骤 7 以试点数据校准；② 「跨≥2 任务 / 同任务≥3 轮」为准入**初值**（设计给定，非实测；校准点=首批沉淀后）；③ est_saved_tokens 为**估算相对量**（W≈字符数/2），非精确账单；④ W7 试点回放用模拟轮次，不依赖真实 LLM 评审（确定链路验证）；⑤ R8 条文未写入 SKILL.md（按需求清单 §六 待写，R1/R3 稳定后落）。
