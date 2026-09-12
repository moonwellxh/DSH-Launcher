# 审查脚本库（pdf-parse-v3 v4 代码命名空间 · 任务级）—— 使用纪律

**位置（R1/R3 定稿）**：本目录 = `adversarial-review\var\task-scripts\pdf-parse-v3\`（任务脚本目录，不污染被审树 pdf-parse-v3）。
任务级 `registry.json` = 可执行事实源；技能级 `var\registry\scripts.json` = 晋升注册表（元数据），靠 code_path 互指不合并。

**目的**：确定性校验脚本（L0，只编「输入→确定性计算」、**禁止内置结论断言**）持久化登记，
跨会话/跨轮复用，**禁止每次重写**。审查者独立解读输出并形成结论。

## 一、Registry（登记表）
机器可读：`registry.json`（name → code_path/entrypoint/run/用途，绝对路径）。规则：
1. **先查 registry 复用**：凡已登记检查项，审查/自检直接运行，不重写。
2. **新写必须登记**：审查者或自检若新写确定性校验脚本，落盘到本目录（`l0_*.py` 命名，docstring 四行模板：作用/输入/输出/复跑）+ 更新 `registry.json`。
3. 脚本只编码「输入 → 确定性输出」；预期值由当轮审查者独立形成后比对（防观测独立性污染）。

## 二、既有持久检查（registry.json 为事实源；下表人读对照）
| 登记名 | 说明 | 运行 |
|---|---|---|
| l0_registry_check | registry 条目字段/文件/docstring 四行自洽校验 | `python l0_registry_check.py` |
| l0_config_keys | cfg 键路径一致性（config.default.json vs 代码取键） | `python l0_config_keys.py <pdf-parse-v3 根>` |
| suite_ms1..ms5 / run_acceptance | 被审对象 pdf-parse-v3 的自带离线套件（43/9/7/8 断言 + 终验） | `python <pdf-parse-v3>\tests\v4\test_*.py` |

## 三、编码纪律
- 全 ASCII 优先；含中文 .py 用 UTF-8（Python 默认），无 BOM 约束（数据文件规范）。
- 离线优先，不打真实 API；不改被审文件。
- 确定性输出一行可 grep（如 `MISSING_TOP=none`、`REGISTRY_CHECK entries=7 bad=0`），便于机械对拍。
