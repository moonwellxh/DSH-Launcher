# 实施计划：adversarial-review 脚本复用与积木化（plan.md · WBS）

| 字段 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-09-07 |
| 上位依据 | `spec.md` v1.0（§5 W1–W8 / §7 M1–M5 / §8 验收）；需求清单 R1–R8；用户 9 步流程之步骤 5 |
| 流程映射 | 步骤 7：逐 WBS 节点编写代码 + 每节点对抗性测试；步骤 8：CI + 对抗性测试；步骤 9：CD + 对抗性测试 |

## 一、WBS 节点清单（构建块 = 一个可独立完成+验证的代码/落盘单元）

| 节点 | 名称 | 产物 | 依赖 | 关键接口/行为 | 节点自验 | 执行体 |
| --- | --- | --- | --- | --- | --- | --- |
| WBS-1.1 | registry 读写层 | `scripts\_registry_io.py` | — | 容器 read/write（原子写保 meta）、`register_l0(task_id,…)`（任务级条目不写 task_id）、`compute_hash`、`record_found_issues(name,issues)` | 单元：对临时容器读写往返一致；meta 不丢 | 脚本 |
| WBS-1.2 | 候选生成器 | `scripts\_collect_candidates.py` | WBS-1.1 | `collect_candidates(task_id)`：确定性字段全产（含 task_id），`found_issues=null+pending_review` | 对试点目录产出 ≥1 合法候选（确定性字段校验过） | 脚本（语义字段留 LLM） |
| WBS-1.3 | 候选校验器 | `_validate_candidate.py`（或并入 1.2） | WBS-1.2 | R2 确定性字段 schema 校验；found_issues null+pending 不算缺 | 正/反例各过 | 脚本 |
| WBS-2.1 | phase_S3 扩展 | 改 `sediment_run.py` | WBS-1.2/1.3 | 读 R2 全字段 → 写技能级条目（task_id/code_path/hash）→ done/failed 归档 → 幂等（同 hash 不重复） | 候选晋升后技能级含三字段；重跑不重复 | 脚本 |
| WBS-3.1 | 积木提取器 | `scripts\_extract_bricks.py` | WBS-2.1 + WBS-4.1 | 准入（回归证据+命中计数：跨≥2 任务/同任务≥3 轮——**计数数据源=4.1 的 hits**）；剥任务逻辑→参数化纯函数（形参带默认值）；hash 去重；积木注册表登记（version/params/changelog） | 合成夹具（含通用片段）产出积木并登记；无片段输入如实空 | 脚本（拆/归并决策=LLM 低频） |
| WBS-3.2 | catalog 生成器 | `scripts\_gen_catalog.py` | WBS-3.1 | 从积木库+注册表生成 `catalog.md/json`（名→作用→ns→路径→entrypoint→复跑） | catalog 与积木库一致、可被脚本消费 | 脚本 |
| WBS-4.1 | 复用观测钩子 | `_registry_io.run_registered` + `record_false_positive` | WBS-1.1/2.1 | **代跑两分支（闭合 S1）**：代跑前查任务级 registry → ① 已晋升技能级：代跑一次→技能级 hits+1；② 未晋升：记入本轮 `reused_scripts[]`（§4.5 reuse_ledger 产端）；误报判定→技能级 false_positives+1 | 两分支均可观察（已晋升/未晋升各测） | 脚本 |
| WBS-4.2 | 快照扩展 | 改 `collect_snapshot.py` | WBS-4.1 | 快照顶层可选 `reuse_ledger{round,reused_scripts[],new_scripts[],counts,est_saved_tokens}`（不冲突顶层 rounds） | 生成快照含 reuse_ledger 且计数>0 | 脚本 |
| WBS-5.1 | 试点准备 | var 落盘 | — | `var\queue\{candidates,done,failed}\` 建目录；试点 registry 条目回填 hash；`skills\_shared\bricks\` 骨架 + catalog 占位；`l0_registry_check.REQUIRED` 加 hash | 目录/骨架齐全；l0_registry_check bad=0 | 脚本 |
| WBS-5.2 | 试点端到端回放 | `var\task-scripts\pdf-parse-v3\e2e_replay.py` | 1.1–4.2 | **两阶段序列（闭合 S2/w1）**：A 晋升轮——注册脚本→**先做一次未晋升代跑（记 `reused_scripts[]`，满足 §8#6）**→收尾自动收集→S3 晋升（技能级有条目）；B 复用轮——再次代跑：因已晋升 → **hits+1（§8#1；hits 记技能级，不进 reuse_ledger）**。两段独立成序 | spec §8 六条全过（第 5 条用合成夹具） | 脚本 |
| WBS-5.3 | 步骤7 补记落点 | 代码补丁 | 各节点 | m2-res（run_registered 调用方=收尾流程）、m4-res（collect_snapshot 算复用指标）、mB-res（record_found_issues 调用点=复审回填）、g1（积木 code_path 定绝对） | 与 spec §6 清单逐项对应 | 脚本 |
| WBS-5.4 | SKILL.md R8 条文 | 改 `SKILL.md` §2 | — | 跨任务启动先查 `_shared\bricks\catalog`，import 积木；独立性纪律同 R6 | 条文与 §2 双轨文本一致 | 文本（一次性） |

## 二、依赖图（DAG）
```
WBS-1.1 → WBS-1.2 → WBS-1.3 → WBS-2.1 → WBS-4.1 → WBS-4.2
                                          │
                                          └→ WBS-3.1 → WBS-3.2   （闭合 S3：3.1 准入计数消费 4.1 的 hits）
WBS-1.1 … WBS-4.2 → WBS-5.1 → WBS-5.2 →（验收）WBS-5.3 → WBS-5.4（条文可并行/尾随）
```
构建顺序：**1.1→1.2→1.3→2.1→4.1→(4.2 ‖ 3.1→3.2)→5.1→5.2→5.3**；5.4 独立可随时落。注：3.1 准入计数依赖 4.1 的 hits 数据（真实计数跨 ≥2 任务/≥3 轮才达标）；试点阶段机制验证用合成夹具（spec §8 第 5 条诚实口径），真实计数随多任务/多轮沉淀后自然触发。

## 三、每节点完成时的对抗性测试（对应流程步骤 7 后段）
- 每 WBS 节点完成后：**独立对抗性测试**——对节点产物跑「边界/反例/接口契约」审查（小、快；用子代理或确定性对拍），通过才进入下一节点（spec §8 不在此阶段整体跑）。
- 关键节点（2.1/3.1/4.2）的对抗性测试优先：幂等、容器保 meta、准入不可绕过、快照不冲突。

## 四、与 spec/需求的映射与验收
- WBS-1.x ↔ spec §5 W1/W2、§4.1/4.2、需求 R1/R2/R3 任务级
- WBS-2.1 ↔ spec §5 W3、§4.3、需求 R3 技能级/R2 采集（C 自动收集入 candidates 在 1.2+2.1 收尾触发）
- WBS-3.x ↔ spec §5 W4/W5、§4.4、需求 R4/R5
- WBS-4.x ↔ spec §5 W6、§4.5、需求 R7
- WBS-5.x ↔ spec §7 M1–M5、§8 验收、需求 R6/R8 + c-m1..c-m4/c-s1 + m* 遗留
- 整体验收 = spec §8 六条（试点 pdf-parse-v3 v4 审查回放）。

## 五、诚实声明与遗留
- 本 plan 为**实施分解**；WBS-3.1「通用片段识别」判据给边界，实际规则以合成夹具定稿（spec §8 第 5 条诚实口径）。
- 语义字段（found_issues/test_problem 终稿）由评审 LLM 回填——相应节点的「对抗性测试」用占位样例而非真 LLM。
- 未做：CI/CD 流水线脚本本身（步骤 8/9 产出）；plan 层未引入新接口，全部以 spec §5 契约为准。

## 六、对抗审查闭合与归档（步骤 6，2026-09-07）
- **S1 已闭合**：WBS-4.1 补两分支（已晋升→技能级 hits+1；未晋升→reused_scripts[]，§4.5 产端明确）。
- **S2 已闭合**：WBS-5.2 重构为「A 晋升轮 → B 复用轮」两阶段，消除 §8#1/#6 同轮时序矛盾。
- **S3 已闭合**：DAG 增 `4.1→3.1` 边（积木准入计数消费 hits；试点机制验证用合成夹具，真实计数跨多任务沉淀后触发）；WBS-3.1 依赖更新为 2.1+4.1。
- **w1 已闭合**：WBS-5.2 A 轮含「未晋升代跑→reused_scripts[]」（满足 §8#6），B 轮已晋升代跑→hits+1（技能级，不进 reuse_ledger），两段独立。
- **归档（轻微/建议，步骤 7 落码时顺手）**：上轮 m1–m7 / a1–a3 + **w2**（准入计数口径校准：hits 记总次数不区分轮次，「同任务≥3 轮」按 spec §6 c-m4 以快照 round 计、「跨≥2 任务」读技能级 task 维度——准入仍为设计初值+试点合成夹具口径）、契约枚举不全、需求清单与 phase_S3 的 done/failed 表述差异（以代码为准复核 §二 措辞）、catalog 相对/绝对路径统一。
