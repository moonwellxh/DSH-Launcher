# 处理遗留：WBS 任务清单（Step 6）

| 字段 | 内容 |
| --- | --- |
| 文档 | pdf-parse-v3 就地升级（Step 6 WBS，九步流程·第二轮） |
| 日期 | 2026-09-09 |
| 上游 | Step 5《处理遗留-详细技术设计.md》（冻结，复审 0/0 + 归档内嵌清零）；Step 4《处理遗留-简版技术设计.md》（§5 里程碑 M1..M5）；Step 3《处理遗留-细化任务书.md》（§0 公开参数全集口径含 <pdf> 位置参数）；Step 2 需求书 |
| 定位 | 把步 5 详细设计切成可执行/可自验/可对抗测试的节点：依赖无环、节点无孤儿、出口可测；每个节点给出产物/依赖/接口/自验/执行体；★ 门通过后进 Step 7 按序编码 |
| 基线 | 7 套 114 断言 ALL_GREEN + compile + doc-consistency（现仅正向）；acceptance 基线 84 表/83 uncertain/1 fixed/84 退化 bbox/硬指标全过（baseline_acceptance.py 可复跑，WBS 审查已复现一致） |

术语口径（建议-5 固定）：**公开旗标集** = argparse 中 `--…` 公开参数（现 8，R-10 后 9）；`<pdf>` 为位置参数、SKILL 示例恒同现，不参与旗标集合差（引用步 5 R-04 口径注）。doc-consistency 校验对象=公开旗标集（正向+反向）。

## 1. 验收映射（20 项 → R → 节点 → 断言载体）

| 遗留 | R | 主实现节点 | 断言载体（文件/节） |
| --- | --- | --- | --- |
| C-1/C-A5 | R-01 | N1.1R（签名+测试机制同批） | test_orchestrator_pdf ②③ + SKIP-POSIX 行 |
| C-2/C-3 | R-02 | N2.3 + N1.1R（C-3 单判据） | test_render ⑥'；test_orchestrator_pdf ①/⑤ |
| C-4 | R-03 | N4.1 | test_triage 零页/blank_pages |
| C-6/C-A2 | R-04 | N3.2 | ci_all（pass>0/反向/找不到行 False）+ 负向脚本 |
| S9-A1/S9-A2 | R-05 | N3.1（--pages）+ N1.3R（MockM4 同形/转发） | test_orchestrator_pdf ⑥ 六例；test_ms3_ladder MockM4 |
| L-验收-2 | R-06 | N4.2 | test_orchestrator_pdf ⑦ |
| C-5 | R-07 | N2.1 | test_render ⑦ |
| C-7 | R-08 | N1.1R | test_orchestrator_pdf ⑧ |
| C-8 | R-09 | N2.2 | test_render floor；test_orchestrator_pdf ⑨ |
| C-A1 | R-10 | N1.4 | test_orchestrator_pdf ⑩ + N1.4 出口 grep |
| C-A3/C-A4 | R-11 | N1.2（marker）+ N1.1R（残导入） | test_ms1_smoke S4；test_orchestrator_pdf ⑪ |
| S9-A3 | R-12 | N1.3R | test_ms3_ladder R-12 三路径 |
| S9-1 | R-13 | N4.3（产品+断言）→ N4.4（对账） | test_ms2_replay 扩展 |
| S9-A4/L-验收-1 | R-14 | N5.2（A 区随 1.4/3.2 落地）+ Step 9 B 区 | ci_all；Step 9 清单对账 |

## 2. 节点清单

### N0 基线复跑与冻结记录（前置，无产物代码）
- 产物：基线快照文件 `docs/处理遗留-基线快照.md` 仅 A/B/C 三节（A 步 7 前基线 / B R-13 对账 N4.4 / C Step 8 CI 总数基线）；**节点执行记录独立于快照**，落 `docs/处理遗留-节点执行记录.md`（每节点时间戳+命令+输出摘要），防污染 A 节 pre 基准（N-3 收口）。
- 自验（含完整命令与模板）：
  - `C:\Users\雍远\AppData\Local\Programs\Python\Python312\python.exe tests\v4\ci_all.py`（工作目录=技能根）→ rc=0；节 A 记：RESULT TOTAL 行、各套件 pass 计数、doc-consistency ok/details、compile bad=0；
  - `C:\Users\雍远\AppData\Local\Programs\Python\Python312\python.exe D:\DeepSeekS\My Coding\_pdfv3_r13_pre\baseline_acceptance.py` → **记录协议（N-4 收口）**：脚本 JSON 部分字段（accepted/hard 五项 detail/tables_total）+ 末行 STATUS_COUNTS dict 一并转录节 A（diff 输入协议=pre/post 两节同字段表格逐键比较）。
- 依赖：步 5 冻结。执行体：本机 Python 3.12。

### N1 编排单点簇（orchestrator/defect_ladder/test_orchestrator_pdf/test_ms1_smoke/test_ms3_ladder）
- **N1.1R R-01/R-08 同批（S-1 修复：产品+测试机制合并单批，杜绝签名破坏窗口）**
  - 产品 scope（orchestrator.py）：`maybe_offer_degrade(reason, cfg, out, tty=True)` 签名 + main L470-473 传 cfg；`run_pdf` 循环前一次 `VisionClient` 构造（budget/ledger 同现）、`_scan_page_glm(pdf, pno, cfg, client, work, doc_sha1)` 传实例（删函数内构建）；`render_reg_for` 删 L195 残留 import（C-A4）。
  - 测试 scope（test_orchestrator_pdf.py，**同批**）：②③ TTY 函数级机制重写（StringIO 替换 sys.stdin + 真实 input + patch 还原，删 TextIOWrapper 双包）；① schema 单判据 `=="4.0"`；⑤ method 单值 `=="local-ocr-fallback"`（C-3）；新增 ⑧ 构造计数==1；**新增 POSIX-only [SKIP-POSIX] 显式行**。
  - 自验：`py_compile` 显式文件集=[assets/v4/orchestrator.py, tests/v4/test_orchestrator_pdf.py]；套件 `test_orchestrator_pdf` rc=0（含 ② 非 TTY 子进程段、③ 差异告知、cfg 调用不 TypeError）。
  - 依赖：无（本簇首个）。
- **N1.2 R-11（C-A3）**：产品=orchestrator `_ms1_page_loop` L431 `_marker(out/"work", …)`；测试 scope=test_ms1_smoke S4 路径断言改 `_ordir/"work"/"marks"`；**新增** test_orchestrator_pdf ⑪（MS-1 模式 stub network→mark 于 work/marks；run_pdf 模式 stub GLM 抛 network + `_scan_page_local` stub→mark 于 work/marks）。
  - 自验：`test_ms1_smoke`、`test_orchestrator_pdf` rc=0。
  - 依赖：N1.1R（其 VisionClient patch 目标与 ⑪ stub 同款，避免并行冲突）。
- **N1.3R R-12（S9-A3）+ S9-A1 MockM4 同形（R-05 部分）**
  - 产品 scope（defect_ladder.py）：L206 CROP / L229 SECOND / L274 resolve_hint 三处统一 `ctx.get("page", ctx.get("page_number"))`。
  - 测试 scope（test_ms3_ladder.py）：MockM4 同形（second_opinion/glm_reparse_crop 的 page/doc_sha1/render_reg 必填，去默认）+ recorder（calls 记录）；ctx_of/run_ladder ctx 补 `page`/`doc_sha1`/`render_reg`；**新增** R-12 三路径用例（ctx 仅带 page_number=7 + doc_sha1/render_reg → 三 mock 收 page==7）；转发断言（mock 收参与 ctx 期望一致）。
  - 自验：`test_ms3_ladder` rc=0（既有 R1..R7 保绿 + 新用例）。
  - 依赖：N1.1R（独立可并行；同 ms3 文件独占串行亦可）。
- **N1.4 R-10（C-A1）**：产品=argparse `--ignore-gpu-lib`（公开旗标区）+ `_structural_ok(skill_base, ignore_gpu_lib=False)` + main 传参；**SKILL.md §0.1 CLI 行同步加 `[--ignore-gpu-lib]`（A 区随批）**；测试 scope 新增 test_orchestrator_pdf ⑩（torch 两态：默认 False/放行 True+WARN）。
  - 出口校验（A-1 收口）：grep 断言命令——SKILL §0.1 行含 `--ignore-gpu-lib` ∧ `add_argument("--ignore-gpu-lib"` ∈ orchestrator.py（脚本 `python -c` 或预研目录内一行命令，写入节点执行记录）。
  - 自验：`test_orchestrator_pdf` rc=0 + 出口 grep 通过。
  - 依赖：N1.1R 后（独立）。
- 依赖图（N1 内）：N1.1R → N1.2/N1.4（可并）；N1.3R ↔（ms3 文件独占，与 N1.1R 无依赖，可并行但同库文件注意冲突——统一串行于 N1.1R 后）。
- 出口：`test_orchestrator_pdf`、`test_ms1_smoke`、`test_ms3_ladder` rc=0；断言计数增量登记于节点执行记录（M-4 收口：写用例节点均显式列用例编号——本簇 ②③ 改、①⑤ 改、⑧⑩⑪ 新、ms3 R-12 新）。

### N2 render 簇（render.py/_scan_page_local/orchestrator ⑨/test_render）
- **N2.1 R-07（C-5）**：render_page 双分支候选序列（缺省=dpi 档值行为不变；target_width=派生），见步 5 §2 R-07。
  - 自验：`test_render` 新增节 ⑦（噪声位图夹具 + OOM 护栏 `w×h ≤ 3e7` + 首候选前置 >10MB + 梯档可达前置 + pixel 反算 m-05）；`test_render` rc=0。
- **N2.3 R-02 测试（C-2）+ 夹具 helper 首引入节点（M-5 收口）**：test_render 新增 helper `make_dense_pdf`（≥5000pt 密铺）与噪声位图 helper；⑥'（前置 >10MB + `dpi<dpi_default` 单判据 + downsampled_from None）；oversize 独立分支用例。
  - 自验：`test_render` rc=0；校准前置断言本地实测通过（不达标不得提交）。
- **N2.2 R-09（C-8）**：render_page 增 `dpi_floor=None`（档序耗尽后 floor 末档再试，仍超→oversize）；`_scan_page_local` 重构（渲染/OCR 解耦；oversize→诚实 part note render_oversize + marker reason render_oversize）；orchestrator ⑨ mock 用例（render 恒抛 oversize→part/marker 断言；floor-reg→OCR 有产）。
  - 依赖：N2.1（render.py 同文件）∧ N2.3（floor 真实夹具复用 helper，M-5 收口）。
  - 自验：`test_render`、`test_orchestrator_pdf` rc=0。
- 依赖图（N2 内，串行防同文件冲突）：N2.1 → N2.3 → N2.2（顺序号即构建序；N2.2 依赖已在图内显式）。
- 出口：`test_render`、`test_orchestrator_pdf` rc=0；夹具校准记录（seed/尺寸/dpi）。

### N3 参数语义/守卫簇
- **N3.1 R-05 --pages（S9-A2）**：`_parse_pages(spec, page_count)`（逐 token 截交防膨胀）→ run_pdf triage 后接线、错误 stderr+exit2；test_orchestrator_pdf 新增 ⑥ 六例子进程断言。
  - 自验：`test_orchestrator_pdf` rc=0（六例 exit/产物/pages 数）。
- **N3.2 R-04（C-6/C-A2）**：ci_all 改——`total_pass>0`；doc-consistency 找不到 CLI 行→False；反向 public(公开旗标−4 兼容内部) ⊆ SKILL（旗标集口径注）。**负向自检脚本（M-2 收口）**：新增 `tests/v4/ci_negcheck_doc_consistency.py`——import ci_all，patch 模块级 SKILL 路径为临时树（合成 SKILL.md 删一公开旗标）→ 断言 check_doc_consistency False（可复跑命令本地执行，不入 SUITES 主绿；理由=不污染真实 SKILL 读取，注释声明）。
  - 自验：ci_all rc=0（现 9 公开旗标双向绿，N1.4 已同批 SKILL）+ 负向脚本（N-1 收口，退出码单值）：`ci_negcheck_doc_consistency.py` 在合成临时树删一公开旗标后调用 `check_doc_consistency` → **负向生效（返回 ok=False）→ 脚本 rc=0**；未检出（反向回归失效）→ rc=1（可失败判据单值，无歧义）。
  - 依赖：N1.4（旗标/SKILL 已批）∧ N3.1（无关，可并）。
- **N3.3（已并入 N1.3R，不再单列）**——MockM4 同形与转发断言在 N1.3R 完成，§1 映射行已指向 N1.3R。
- 出口：`test_orchestrator_pdf`、ci_all rc=0；负向脚本运行记录。

### N4 端到端守卫簇（triage/orchestrator-images/pipeline-bbox/acceptance 对账）
- **N4.1 R-03（C-4）**：test_triage 零页（pypdf PdfWriter 直写 0 页，kind==zero_page 单判据、无 skip 分支）+ `blank_pages==[2]` 强化。
  - 自验：`test_triage` rc=0。
- **N4.2 R-06（L-验收-2）**：test_orchestrator_pdf 新增 ⑦（stub `orc.VisionClient`→run_pdf 1 页扫描→pages[0].images 非空/figure_count≥1）。
  - 自验：`test_orchestrator_pdf` rc=0。
- **N4.3 R-13（S9-1）**：pipeline 产品= `_layout_table_blocks`（返回 [(bbox_int4, html)]）+ 逐位配对 + `_first_cell_eq` 首格抽查 + count 不等/order-mismatch 整页回退 + routing note 追加（note 文案见步 5）；test_ms2_replay 扩展（180 页 count/序/首格抽查回归 + page_0019 双表 bbox 互异 + 指纹互异（cache_fingerprint bbox 变体）+ 合成 count 不等 + 合成首格错序两例）。
  - 自验：`test_ms2_replay`、`test_ms5_acceptance` rc=0（翻转按 N4.4 口径）。
- **N4.4 R-13 行为对账（M-1 收口）**：复跑 `baseline_acceptance.py`（pre=N0 节 A 已存）→ post 写快照节 B。
  - 期望翻转集（引用步 5 §2 R-13）：仅"无 gate-failure 且 OCR 行存在的表"可能由 ok→resolve_hint→NoOpM4 诚实标记（uncertain 带 degraded:egress_blocked issue）；按 N0 基线分布（84 表 83 uncertain/1 fixed、全退化、无 ok 态）预期零翻转。
  - 判定规则：post STATUS_COUNTS 与 pre 相比，仅允许"表数不变；ok/fixed 合计不减；uncertain 增量为零或来自上述期望子集且每表带 issue detail（egress_blocked）；无新增 unreadable"→通过；否则停 N4 上报复审（不静默放宽）。
  - 出口断言=脚本 diff 计数（pre/post 两 JSON 摘要逐键比较文件 `docs/处理遗留-基线快照.md` 节 B 表格），非存在性断言。
  - 依赖：N4.3。
- 出口：`test_triage`/`test_orchestrator_pdf`/`test_ms2_replay`/`test_ms5_acceptance` rc=0 + 对账记录。

### N5 CI 汇总与 A 区确认
- **N5.1 全套 CI**：`python tests/v4/ci_all.py` 全绿（pass>0、双向、compile、doc-consistency）。**断言计数对账（A-2/N-2 收口）**：新增断言总数 = ci_all TOTAL − N0 节 A 记录的 114；核对依据=步 5 §4 受改预期逐条表 + **§4 文件级改动清单（按文件改/新条数）**两表并引，记录于快照节 C。
- **N5.2 A 区确认**：SKILL §0.1 含 9 公开旗标（N1.4 已落）+ ci_all 双向含 ignore-gpu-lib（N3.2）→ 一致性 grep 通过；B 区（三处冻结文档修订注：升级设计 §3.2 / v1.2 §6.13 / v1.2 §6.12）挂 Step 9，不在 N5 执行。
  - 自验：ci_all rc=0 + grep 输出记录。
- 依赖：N1..N4 全绿。
- 出口：RESULT ALL_GREEN。

## 3. 依赖图与构建序
```
N0 → N1.1R → N1.2, N1.3R, N1.4（可并/串）
   → N2.1 → N2.3 → N2.2
   → N3.1（与 N1 并域）、N3.2（依赖 N1.4）
   → N4.1, N4.2（并）、N4.3 → N4.4
   → N5.1, N5.2 → Step 8 CI★ / Step 9 CD★
```
无环；每节点出口可测（自验命令 + 对应套件 rc=0 + 节点执行记录含用例编号与断言增量）。节点无孤儿：任何节点引用的测试编号/夹具/产品符号均在依赖链前序节点引入（N1.1R 引 ②③⑧ 自含；N1.2 引 ⑪ 自含；N1.4 引 ⑩ 自含；N4.2 引 ⑦ 自含；N2.2 引 helper 依赖 N2.3）。**同文件串行约束（N-5 收口）**：N1.2/N1.3R/N1.4 与 N1.1R 同改 orchestrator.py / test_orchestrator_pdf.py / test_ms3_ladder.py → 即便逻辑独立也串行提交（建议 N1.1R → N1.2 → N1.3R → N1.4），与 N2 簇同规则。

## 4. Step 7 纪律（每节点完成即对抗测试）
- 每节点提交前：`py_compile` 显式文件集 + 节点自验断言 + 对应套件 rc=0；改动锚定遗留 ID（R-xx/C-xx/S9-xx/L-xx 于变更说明）。
- **签名/契约破坏性变更一律同批**（产品+受调用方/测试同步落，禁过渡红窗口——N1.1R 示范；同型冲突即合并批）。
- 防假绿灯：无空转 skip（POSIX-only 显式 [SKIP-POSIX] 行除外）；夹具不达前置断言不得提交（N2/N4 校准点，seed/尺寸固化）；不 or 放宽既有断言（改预期必须对应任务书条款并登记受改预期表）。
- 负向路径自动化：doc-consistency 反向负向由 `tests/v4/ci_negcheck_doc_consistency.py` 本地可复跑承接（不入 SUITES 主绿，注释说明）。
- 风险节点（N2.2 幂等/降级路径、N4.3 配对/回退路径）完成后加独立小审；发现阻断/严重即修后继续。
- 每节点执行记录追加到快照文件对应节（时间戳），供 Step 8/9 复核。

## 5. 收口映射（Step 9）
N5 全绿 → Step 8 CI（★：全套 + doc-consistency 双向 + 负向脚本 + 真实样件复验记录）→ Step 9 CD（产物清单 + B 区三处冻结文档修订注 + 遗留清单 + 完成时间落盘）。

## 6. 自证声明
- 节点切分与步 4 §5 里程碑 M1..M5 内容对照：M1↔N1、M2↔N2、M3↔N3、M4↔N4、M5↔N5+Step8/9（M5 在步 4 含文档同步与样件复验——B 区修订注归 Step 9、真实样件复验归 Step 8，差异已注——M-3 收口）。引用更正：步 5 无"§5 里程碑"节，里程碑定义在步 4 §5。
- 覆盖：§1 表 14 行对账 R-01..R-14/20 项无漏无孤儿；依赖无环；每节点出口含可执行命令（含完整路径/工作目录模板，N0 示范）。
- 诚实声明：负向注入（ci_negcheck）不入 SUITES 主绿（防污染真实读取，本地脚本承接）；夹具校准数值以本地实测为提交门槛；B 区文档修订注与样件复验按排期在 Step 9/8；N4.4 对账判定规则若触发"停 N4 上报"即如实上报，不静默放宽。
