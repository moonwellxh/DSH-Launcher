# 处理遗留：CI（Step 8）——复审2意见单（仅报告 · 最小证据绑定 · 第二处增量）

| 字段 | 内容 |
| --- | --- |
| 复审对象 | Step 8 CI 门修复增量**第二处**（两项）：S-复审-1 修复（`ci_negcheck_doc_consistency.py` main() 开头 reconfigure utf-8）、L-复审-1 修复（`test_orchestrator_pdf.py` L96 行内注释口径对齐） |
| 复审模式 | 独立对抗复审者（无共享上下文）· 增量复审 · 仅报告（未修改任何被审文件） |
| 日期 | 2026-09-09 |
| 复核方法 | L0 裸命令复跑（cwd=技能根，python312，**无 PYTHONUTF8/-X utf8**，管道捕获=文档化复跑形态）+ 行级直读两实物 + 文件 mtime 对账（修改范围仅两目标文件）+ 文件内关联锚点（①-b/⑤/R-06）存在性核对 |
| 依据 | 任务指定上轮单 `docs/处理遗留-CI-复审意见单.md`（§2 S-复审-1 严重、§3 L-复审-1 轻微 原文语义）；**未读本目录其它意见单** |

## 0. L0 实测证据（零模型判断部分）

| 项 | 操作（技能根；python312；裸命令） | 结果 |
| --- | --- | --- |
| 负向脚本复跑（S-复审-1 目标形态） | `python tests\v4\ci_negcheck_doc_consistency.py`（显式清除 PYTHONUTF8/PYTHONIOENCODING，无 -X utf8，2>&1 捕获） | **rc=0**：`NEG OK: 反向检出缺失 -> ok=False 且 rev_missing=['--ignore-gpu-lib']；details=["CLI: skill[...] ⊆ argparse[...] fwd_missing=[] rev_missing=['--ignore-gpu-lib']", 'mods missing=[]']`——⊆ 行完整打印，无 UnicodeEncodeError |
| 主路径单测复跑（L-复审-1 所在文件） | `python tests\v4\test_orchestrator_pdf.py`（同上裸命令） | **rc=0**，`RESULT pass=49 fail=0`；尾部 `R-06 pages[0].images 非空 n=1`、`metadata.figure_count>=1 fc=1` 等含图断言全 pass |
| 与上轮失败形态对照 | 上轮单 §0：同形态 rc=1 `UnicodeEncodeError: 'gbk' codec can't encode '\u2286'` | 本轮同形态 rc=0 → 崩溃形态已消除（假红关闭） |
| 修改范围对账 | tests\v4 目录 py mtime | 晚于上轮单（21:50:18）的仅两目标文件：`ci_negcheck_doc_consistency.py` 21:50:42、`test_orchestrator_pdf.py` 21:50:49；`ci_all.py` 21:44:44 未动 → 本轮无越界改动信号（mtime 佐证，非 diff 基线） |

## 1. 两项清零复核（逐条）

| 上轮项 | 结论 | anchor / basis / confidence |
| --- | --- | --- |
| S-复审-1 严重（负向脚本成功路径打印 ⊆ 未钉死 → 裸命令 rc=1 假红，文档化 NEG OK 不可复现） | **已清零** | anchor：`tests/v4/ci_negcheck_doc_consistency.py` L30-35——main() 首部 `try: sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(...) except Exception: pass`，置于任何 print 之前（首 print 在 L48/66 分支）；L2 声明 `# -*- coding: utf-8 -*-`。basis：① 位置满足"main() 开头新增"，且与姊妹脚本同款范式（`test_orchestrator_pdf.py` L88-92、`ci_all.py` L77-82，errors="replace"+try/except 包裹）；② 裸命令（无 PYTHONUTF8/-X utf8，管道捕获=Step 9 CD 复跑形态）实跑 rc=0、NEG OK 行含 rev_missing=['--ignore-gpu-lib']、details 内 ⊆ 完整打印——上轮 rc=1 UnicodeEncodeError('gbk','\u2286') 复现形态消失；③ reconfigure 仅改输出流编码，正/负控与 rev_hit 绑定逻辑（L41-66）零改动，不引入逻辑回归（上轮 S2 绑定结论不受影响）。confidence：高（实跑 + 行级直读 + 逻辑未触）。附带效应：CI 文档 §2 文档化"NEG OK rc=0"现可原样复现，上轮"文档化结果不可复现"缺陷关闭。 |
| L-复审-1 轻微（L96 行内注释仍称 ① "文字层+含图"，与 ① 实跑 3 页纯文字不符） | **已清零** | anchor：`tests/v4/test_orchestrator_pdf.py` L96 现文 `# ① 端到端 3 页纯文字层整本（含图相关覆盖见 ①-b/⑤/R-06，Step 8 复审 L-复审-1 注释对齐）`；L97 实跑 `make_pdf(td / "mini.pdf", pages=("text","text","text"))`；同簇头注释 L7 已同口径（3 页文字层）。basis：① 新注释与 ① 实跑页型一致，不再以"含图"描述 ① 自身；② 含图覆盖指认的 ①-b/⑤/R-06 在本文件内真实存在——①-b = L111+（raw_resp 钉定守卫，payload 层 image 断言），⑤/R-06 = 文件内 scan.pdf/scan_img 含图路径（本轮实跑输出 `R-06 pages[0].images 非空 n=1`、scan_img.v4.json 生成佐证），指认非空指；③ 纯注释改动，无功能/CI 影响。confidence：高（行级直读 + 文件内锚点核对 + 实跑佐证）。 |

## 2. 分级统计

- 本轮新增：**阻断 0 / 严重 0 / 轻微 0 / 建议 0**。
- 上轮遗留清零复核：S-复审-1（严重）✓、L-复审-1（轻微）✓。
- 上轮已清零的首轮六项（S1/S2 逻辑/L1/L2 头注释/A1/A2）：本轮文件修改范围仅上述两目标文件且仅含对应增量（mtime 对账），无回退信号，不做冻结区重审。

## 3. 放行判定

- **阻断清零 ✓ ∧ 严重清零 ✓（含本轮 0 新增）→ 判定：放行。**
- Step 8 CI 门两处增量证据绑定闭合：文档化裸命令（无 PYTHONUTF8/-X utf8）下 `ci_negcheck_doc_consistency.py` rc=0 + NEG OK（rev_missing=['--ignore-gpu-lib']，⊆ 不崩）、`test_orchestrator_pdf.py` rc=0 + RESULT pass=49 fail=0，均与预期逐字相符。
- 备注（非阻塞）：放行有效性以任务给定复跑形态（管道捕获、无 PYTHONUTF8）为前提；若未来 CI 宿主改为 UTF-8 控制台直连形态，reconfigure 幂等、无副作用。L-复审-1 注释改动与修复建议口径一致，无残留。
- 未清零项 anchor 摘要：**无**（本轮无新阻断/严重，无遗留）。

---

（本复审2意见单为仅报告输出，未修改任何被审文件；仅读取任务指定的上轮依据单 `docs/处理遗留-CI-复审意见单.md`，未读本目录其它审查/复审意见单。）
