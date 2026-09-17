# 修订日志（changelog.md）

## 手动条目 · 2026-09-17 · 任务 SK-20260917-f3fix（fire-check-consolidation / f3_register.py 修复）
- **背景**：连云港监狱查验项目实跑 F3 暴露四处缺陷；两轮独立对抗复审（R1 首轮 + R2 增量），并按其意见修复。台账 `var/ledger/SK-20260917-f3fix.json`（20 条：首轮 10 已关闭 + 二轮 8 待验证 + 2 提议中）。
- **落盘义务（§2）补做**：两轮独立复审者的一次性探针共 13 个（R1 六、R2 七）原先散落于会话临时目录 `.tmp_fire_lianyungang\`、`.tmp_rev_r2\`，本轮转存为任务级脚本 → `var/task-scripts/SK-20260917-f3fix/`，**逐字节原样**（仅改名）以保观测独立性，并写 `registry.json`（sha1、绝对 code_path、run、purpose）。
- **命名与模板合规的如实说明**：该批**刻意不用 `l0_` 前缀**（用 `rev_r1_*`/`rev_r2_*`）。R1 说明模板要求 `l0_*` 脚本含"作用/输入/输出/复跑"四行 docstring 且以 `def main(` 为入口；本批为复审者临时探针、13 个中 7 个是模块级执行（无任何函数），**不冒充模板合规资产**。因此 `l0_registry_check.py` 对它们报 `bad=7`（entry=`<module>`）；13 条中 6 条（有真实函数名作 entrypoint）为 `OK`。若将来要晋升为技能级 L0 资产，须先按模板重构（加四行 docstring + `main()` 包装）。
- **其余**：`run` 统一带 `-X utf8`（探针会 print 上标²/阿拉伯数字等，GBK 控制台下原样运行会 `UnicodeEncodeError`）；`rev_r2_info_arg_states.py` 依赖的 8 份 docx 副本（`.tmp_rev_r2\corpus_same_names\`）未一并转存，避免技能目录内堆积大文件。
- **回滚点**：本条目仅新增 `var/task-scripts/SK-20260917-f3fix/` 与 `var/backup/ledger_SK-20260917-f3fix_*.json`，未改动既有脚本/条款/价格表。

## iter-1 · 2026-09-11T01:15:27+08:00 · 触发:静默 · ns:document
- 快照：处理 7 条（runs=0, issues=0, 误报=0, 重开=0）
- 导引单：无改动（裁决未含变更）
- 条款生命周期：在册 14 条｜新增 trial 无｜转正 无｜试用到期待裁决 无｜降权建议 无｜淘汰建议 无
- 脚本：无晋升
- 价格表：未变（数据日期 2026-09-05）
- ROI 建议：metrics.jsonl 无历史，暂不给出 ROI 结论
- 回滚点：C:\Users\雍远\.agents\skills\adversarial-review\var\backup\iter-1
