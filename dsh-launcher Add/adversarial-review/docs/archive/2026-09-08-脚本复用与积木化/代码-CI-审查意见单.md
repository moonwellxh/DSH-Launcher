# 代码 + CI 对抗审查意见单（步骤 7/8 产物 · 全量首审）

| 字段 | 内容 |
| --- | --- |
| 审查对象 | 脚本复用与积木化 步骤 7（_registry_io / _collect_candidates / sediment_run phase_S3 / _extract_bricks / _gen_catalog / collect_snapshot reuse_ledger）+ 步骤 8（tests_node/*, e2e_replay, ci_all）+ 试点（pdf-parse-v3 registry/l0_*）+ SKILL.md §2 |
| 审查性质 | 独立子审查者（干净上下文、非 fork），仅喂对象全文 + 交叉依据，未喂编排/作者推理或他轮结论 |
| 判定基准 | spec.md §4/§5/§7/§8、plan.md WBS、升级需求清单 R1–R8、SKILL.md §2 |
| 运行证据 | `C:\Users\雍远\.dsh\runtime\python312\python.exe scripts\tests_node\ci_all.py` → `RESULT ci_pass=7 ci_fail=0 compile_fail=0`（零 API、离线复跑通过） |
| 通过判据 | 阻断清零 ∧ 严重清零（按默认门限） |

> 证据说明：L0 确定性脚本由编排者侧复跑七项全部通过；另对**真实试点**做了三项只读核验（registry 条目 hash 重算、l0_registry_check、l0_config_keys），结论见下文「严重」首条。以下每条均含 anchor/basis/confidence，禁原文复述。

## 阻断（0 条）

无。

## 严重（1 条）

### S-1 试点 registry 的 l0_registry_check 条目 hash 与现文件内容不符（R3「hash=内容 sha1」契约在试点事实源上被破坏，且保障脚本无法暴露）
- **anchor**：`var\task-scripts\pdf-parse-v3\registry.json` → `scripts[]` 中 `name=l0_registry_check` 的 `hash` 字段（registry.json 第 14 行）；对照 `var\task-scripts\pdf-parse-v3\l0_registry_check.py`（其 `REQUIRED` 含 `hash`，即自证依赖该字段）。
- **basis**：重算该条目 `code_path` 所指文件的实际 sha1 = `180f3736…`，而 registry 存储值 = `584e9b64…`，不一致；同文件其余 6 条目（l0_config_keys/suite_ms1..ms5/run_acceptance）均与实际 sha1 一致。spec §4.1 及 §8 第 1/2/4 条以 registry 为「可执行事实源」且 hash=内容 sha1；此失配表明该脚本在登记后曾被修改（猜测为步骤 7 落码给本机加 hash 校验/四行 docstring 检查时未回刷自身 hash），违反 spec §6 r2 遗留 m5「步骤 7 需回填试点条目 hash」的完整兑现。同时 `l0_registry_check` 只校验 hash 字段**存在**、不校验其**数值正确性**，故其 `bad=0`（已复跑确认）无法暴露该失配——所谓「R1/R3 保障」对 hash 数值维度实际不闭合。
- **confidence**：high（事实经重算双验；「变更时机」为推断，已如实标注）。

## 轻微（6 条）

### m-1 _extract_bricks CLI 参数解析与自身文档化用法不一致，文档化调用即返回 refused
- **anchor**：`scripts\_extract_bricks.py` `__main__`（第 241–247 行，按位置读 `sys.argv[4]/[5]` 且要求 `--admission=`/`--task=` 前缀）+ docstring 第 9 行（`--task <tid> --admission '{json}'`）。
- **basis**：按 docstring 顺序复跑 `python _extract_bricks.py src norm_num --task cliA --admission '{"cross_task":2}'`，得到 `{"action":"refused","reason":"…cross_task=0…"}`（exit 1）；仅当把 `--admission=<json>`、`--task=<tid>` 写成等号连接的单 token 才可解析，与文档化用法不符。API 直调（自测/e2e 走 `extract_brick`）不受影响。
- **confidence**：high（两序复跑实证）。

### m-2 est_saved_tokens 以脚本名/最大名长代理「字符数」，且 build_reuse_ledger 注释声称「有文件则取文件字符数」但实现恒用 len(name)，且该函数无任何调用点
- **anchor**：`scripts\_registry_io.py` `build_reuse_ledger`（第 142–153 行，恒 `total += len(name)`）+ `var\task-scripts\pdf-parse-v3\e2e_replay.py`（第 80–82 行，`count×ceil(max(name)/2)`）。
- **basis**：spec §4.5 / R7 分母口径＝`reused_count × ceil(脚本字符数/2)`（字符数指脚本长度，见 R7「按脚本长度估算」）；实现与 e2e 用**脚本名长度**代理，量级偏小，与 spec「相对量估算」虽相容但低估严重。且 `build_reuse_ledger` 全库无引用（grep 仅 1 处定义），e2e 台账为手工构造。
- **confidence**：high（公式与实现直读；低估幅度为判断）。

### m-3 validate_candidate 强制要求 code_path，与 spec §4.2「code_path 或内联 code 二选一」契约冲突
- **anchor**：`scripts\_collect_candidates.py` `DETERMINISTIC`（第 22 行含 code_path 不含 code）+ `validate_candidate`（第 31–33 行判「确定性字段缺 code_path」）。
- **basis**：spec §4.2 / §5 W2 允许候选为 `code_path` 或内联 `code` 二来源；`validate_candidate` 会把仅含 `code`、无 `code_path` 的合法候选判为缺 code_path。收集器（W2）恒产 code_path，故实践中不触发；但其校验口径与 phase_S3（兼容 code 来源）不自洽。
- **confidence**：high（口径直读）。

### m-4 candidate regression 用 evidence_tail 而非 spec §4.2 的 evidence
- **anchor**：`scripts\_collect_candidates.py` `_run_evidence`（第 66–67 行返回 `{passed,exit,evidence_tail}`）。
- **basis**：spec §4.2 / R2 schema 为 `regression:{passed, evidence}`；实现字段名为 `evidence_tail` 且无 `evidence`。validate_candidate 未校验该字段名，phase_S3 只读 `passed`，故无功能影响，属 schema 命名偏差。
- **confidence**：high（字段名直读）。

### m-5 phase_S3 对「既无 code 又无 code_path」的候选（regression.passed=true）会注册出 hash=None 条目并造成潜在错误去重
- **anchor**：`sediment_run.py` `phase_S3`（第 402–422 行：code/cp 均缺→content_hash=None，注册 hash=None；第 420–421 行 dedup 用 `r.get("hash")==rec["hash"]` 匹配）。
- **basis**：若两候选均无 code/code_path，其 hash 均为 None，第二次会误入 dedup-update 分支（把第二候选当第一候选去重，不新增条目、只更新版本/时间），造成数据丢失。phase_S3 未调用 validate_candidate，依赖上游（收集器恒产 code_path）——属边界缺口，非当前路径触发。
- **confidence**：medium（结构推断；未构造反例复跑）。

### m-6 CI 门未纳入 l0_registry_check 对真实试点 registry 的 bad=0 校验（spec §8 第 2 条验收项未进回归门），e2e 也仅断言 hash 字段存在
- **anchor**：`scripts\tests_node\ci_all.py` `JOBS`（第 14–22 行，7 项不含 registry_check）+ `e2e_replay.py` E1（第 110–111 行，只查 `"hash" in s`）。
- **basis**：spec §8 第 2 条「l0_registry_check 判 bad=0」是显式验收项，但 CI 与 e2e 均未执行 registry_check 于真实 registry，也未校验 hash 数值正确性——这正是 S-1 的 hash 失配未被 CI 捕获的原因。CI 作为「确定性回归门」对试点真实一致性的覆盖不完整。
- **confidence**：high（任务列表直读）。

## 建议（6 条）

### a-1 collect_candidates 的 version 未按 spec §5 W2「取 docstring/注册版本」，且 _next_version 仅扫 CAND_DIR 不含 DONE_DIR
- **anchor**：`scripts\_collect_candidates.py` `_next_version`（第 72–82 行）。
- **basis**：实现以既有候选计数自增至 r{N}；候选晋升移入 done 后，新版本扫描不见 done 记录，可能重号。R1 裁决「轮次信息入 R2 version 字段」未从 docstring 取。
- **confidence**：medium。

### a-2 R7 复用台账产端（reused_scripts[] 聚合、hits+1 触发）无自动化接线，靠调用方/编排者手工构造
- **anchor**：`_registry_io.py` `run_registered`（第 115–128 行，reused 分支仅返回 branch/detail，不落 reused_scripts[]）+ `e2e_replay.py`（第 79–83 行手工聚合）。
- **basis**：spec §6 r2 遗留 m2-res/m4-res 已声明「留待接线」，实现与之一致；但作为「控制论反馈传感器」，R7 的闭环仍依赖编排者显式调用 run_registered 并建 reuse_ledger，非自包含。
- **confidence**：high（m2-res 文案对接一致）；严重度按「已声明遗留」降为建议。

### a-3 spec §8 第 6 条「含 est_saved_tokens 估算口径注明」未落到 reuse_ledger（无口径 note 字段）
- **anchor**：`scripts\collect_snapshot.py` `validate` reuse_ledger 分支（第 124–127 行，仅校验 round/reused_count/new_count/est_saved_tokens）。
- **basis**：spec §8 第 6 条要求「含 est_saved_tokens 估算口径注明」；当前 ledger 与校验不承载该注明，落在 spec §9 诚实声明的文档层而非快照内。
- **confidence**：medium。

### a-4 _extract_bricks CLI 对 refused 输出 {action,reason}，与 SKILL.md 附「失败输出单行 {error,hint} 并退出非 0」的失败协议不一致
- **anchor**：`_extract_bricks.py` `__main__`（第 246 行）+ SKILL.md 附 L118。
- **basis**：五个主脚本的失败协议为 `{"error":…,"hint":…}`；CLI 路径改用 `{"action","reason"}`（虽退出码非 0），协议未统一。
- **confidence**：medium。

### a-5 l0_registry_check 对非 l0_* 脚本也打印 doc4lines=yes（实际未做 docstring 四行校验），输出具误导性
- **anchor**：`var\task-scripts\pdf-parse-v3\l0_registry_check.py`（第 52–56 行，doc_ok 仅对 l0_* 设值，但打印不分）。
- **basis**：对 suite_ms* / run_acceptance 走非 l0 分支，doc 未校验却显示 yes，与 R1「四行模板只强约束 l0_*」相符但日志易误导对拍。
- **confidence**：high（逻辑直读）。

### a-6 试点 var\queue\{candidates,done,failed} 子目录与 var\registry\scripts.json、_shared\bricks\catalog.json 均未落盘（WBS-5.1 骨架未完整；占位未生成机器可读清单）
- **anchor**：`var\queue`（空）、`var\registry`（无 scripts.json）、`C:\Users\雍远\.agents\skills\_shared\bricks\`（仅 registry.json 空桶 + catalog.md 占位，无 catalog.json）。
- **basis**：spec §3 目标文件树与 WBS-5.1 声明「queue\{candidates,done,failed} 建目录」及「catalog.md/catalog.json」；当前为未触发 S3 的预期态（目录脚本可自建），但与目标树不完全一致，且跨任务机器可读清单（catalog.json）尚未生成。
- **confidence**：high（目录树直检）。

## 结论摘要

- **各级条数**：阻断 0 ／ 严重 1 ／ 轻微 6 ／ 建议 6（共 13 条）。
- **是否可进入步骤 9（内部交付收口）**：按默认门限「阻断清零 ∧ 严重清零」，**先修复 S-1 再进入步骤 9 更稳妥**。S-1 属真实数据完整性缺陷（试点事实源的 hash 失配 + 保障脚本对 hash 数值不闭合），非机制性硬失败；其余轻微/建议不阻断收口。
- **CI/回归门是否可信**：**基本可信但覆盖有缺口**。七项全通过、断言非恒真（各节点均有逐项 PASS/FAIL 与反例，且对隔离临时 state 实跑验证）；但 CI 未纳入 spec §8 第 2 条（registry_check 真实 bad=0）与 hash 数值正确性校验，故无法捕获 S-1 这类「字段齐全但数值过期」的问题。

## 收口建议（供主导者裁决，非本审结论）
1. 修复 S-1：刷新试点 registry 中 l0_registry_check 的 hash 为当前文件实际 sha1；并建议 `l0_registry_check` 增加 hash 数值重算比对（否则 hash 保障维度永远不闭合）。
2. 建议把 l0_registry_check 真实 bad=0（含 hash 数值校验）纳入 ci_all.py JOBS，使回归门覆盖 spec §8 第 2 条。
3. 其余 m-1..m-6 / a-1..a-6 按需择机随步骤 9 顺手消化，均不构成阻断。
