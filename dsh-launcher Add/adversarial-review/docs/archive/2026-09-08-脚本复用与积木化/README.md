# 归档批次：脚本复用与积木化升级（2026-09-08 收口）

本目录为 adversarial-review「脚本复用与积木化」一次升级（需求→spec→plan→代码→CI→CD）的完整历史批次。

- **收口状态**：六段链路各自对抗审查清零；CI `ci_all.py` 8/8 + compile 0；节点自测 65 断言；试点 registry 真实核验 hash 数值一致（详见 `交付验收报告.md`）。
- **现行落地**：条文在技能根 `SKILL.md` §2（registry 双轨/task-scripts 落盘/docstring 四行/跨任务复用）；代码在 `scripts/`（`_registry_io.py`、`_collect_candidates.py`、`_extract_bricks.py`、`_gen_catalog.py`、`sediment_run.py` phase_S3 扩展）；任务级试点在 `var/task-scripts/pdf-parse-v3/`；积木库骨架在 `~/.agents/skills/_shared/bricks/`。

## 互引说明

批次内文件互相以 `docs/<name>.md` 引用（审查意见单引用其对象等）——这些引用是**批次内相对引用**，读本目录文件时请理解为指本目录下同名文件，而非技能根 `docs/`。本批次收口后不参与现行运行，未按新路径改写正文（保留审查/复审原始记录，忠实可溯源）。

## 批次文件

- `升级需求清单.md`（需求，R1–R8 + 裁决）及三份意见单（审查/复审/K3）
- `spec.md`（技术设计 v1.0）及三份意见单（审查/复审 r1/r2）
- `plan.md`（WBS v1.0）及两份意见单
- `代码-M1M4-审查意见单.md`、`代码-CI-审查意见单.md`（步骤 7/8 代码层审查）
- `交付验收报告.md`（步骤 9 收口结论）
