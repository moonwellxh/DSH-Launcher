# 升级 WBS 任务清单：补全 v4 入口与引擎降级显式化

| 字段 | 内容 |
| --- | --- |
| 文档 | pdf-parse-v3 就地升级（Step 6 WBS，九步流程） |
| 日期 | 2026-09-09 |
| 上游（全冻结） | Step 2 简版需求书（R-01..08）；Step 3 细化任务书（D-1..D-3）；Step 4 简版技术设计（D-4..D-7）；Step 5 详细技术设计（§1-§6） |
| 定位 | 可执行的节点清单：产物/依赖/接口/自验/执行体；依赖图无环、节点无孤儿、出口可测 |

---

## 1. 节点清单

| 节点 | 产物 | 依赖 | 接口（调用/被调） | 自验（确定性，离线） | 执行体 |
| --- | --- | --- | --- | --- | --- |
| N1 | `assets/v4/triage.py`（M1） | 冻结 §1 详细设计；assets/pdf_text_probe.py | 出：`triage(pdf_path,cfg)->dict`、`TriageError`；被 N6 调 | test_triage.py：合成 text/blank/加密 → verdict/blank_pages/TriageError/字段齐全；verdict 抽样对照 pdf-inspect（A1-，用合成夹具+真实样件各一） | 编码 |
| N2 | `assets/v4/render.py`（M2） | 冻结 §2 详细设计 | 出：`render_page/render_pages/px_to_pt/pt_to_px/crop_png/build_registry_entry/append_registry`、`RenderError`；被 N6 调 | test_render.py：PNG/registry/换算自检/降档/oversize | 编码 |
| N3 | `assets/v4/orchestrator.py` 升级（M12） | N1/N2 + 冻结 §3 详细设计 | 入：`<pdf> --out …`；复用 pipeline/structurer/textlayer/VisionClient/M13 | test_orchestrator_pdf.py：端到端/弹选/幂等/--no-egress | 编码 |
| N4 | SKILL.md §0.1/§1/§2 修正（R-06） | N1-N3 实物 | SKILL.md CLI/模块清单/降级口径 = 实物 | 一致性脚本：SKILL.md 所列 CLI 与 argparse 一致、模块清单对文件 | 编码 |
| N5 | 弹选接线验证（R-05 收尾） | N3 | maybe_offer_degrade TTY/非TTY/选B 硬断言 | test_orchestrator_pdf ②③⑤ | 编码 |
| N6 | M13 `--md/--html` 接线 + 键集校验（D-6） | N3 + serialize_md/html | to_md(v4)/to_html(v4,badges)；键集前置比对 | 键集脚本 + md/html 冒烟（文字层样件） | 编码 |
| N7 | 测试三件 + 回归（R-07） | N1-N6 | test_triage/render/orchestrator_pdf + ms1..ms3+ms5 | CI 一键全绿（离线） | 编码 |
| N8 | 文档链并入（R-08） | 全部 | 需求书 v2.4 修订稿 + 设计 v1.2 修订稿（§4.1/4.2 差异清单） | diff 检查：仅相关章；存档沿用（v2.3/v1.1 存档） | CD |
| N9 | **扫描样件出域真跑验收（V-2，S1 修复：单列节点）** | **N3+N7（CI 绿前置）+ D-3 样件** | 扫描 PDF 前 N 页（N≤10）出域真跑 | 无离线确定性自验（W3 修正）；验收=§4 N9 行出口判据（routing.method=glm、台账 cost/usage、表 status 非空，分母=检出表数），**人工门**（出域依赖 key/网络，不并入离线 CI） | CD 阶段人工/出域执行 |

## 2. 依赖图

```
N1(M1) ──┐
N2(M2) ──┤
         ├→ N3(orchestrator 升级) ─→ N5(弹选验证) ─┐
N4(SKILL.md 修) ← N3 实物 ──────────────────────┤
N6(M13 接线) ← N3 ────────────────────────────────┤→ N7(测试+CI) → N8(文档并入/CD)
                                                    └→ N9(扫描出域真跑验收，CD 阶段人工门)
```
依赖无环；N1/N2 无孤儿（被 N3 消费）；N4/N5/N6 均锚定 N3；N9 锚定 N3+N7（出域真跑不并入离线 CI）。

## 3. 构建顺序与并行

- 串行主线：N1 → N2 → N3 → N5/N6 → N7 → N8。
- N9（扫描样件出域真跑）依赖 N3 完成且样件到位，在 CD 阶段执行（出域+人工门），不与离线 CI 混跑。
- 可提前并行：N4 的 SKILL.md 修正可在 N3 代码稳定后即做（依赖实物，不必等 N7）。
- N7 的 test_orchestrator_pdf 依赖 N3 完成；test_triage/test_render 可随 N1/N2 同步写（先写测试后实现或同批）。
- **样件来源（吸收建议 A2）**：文字层样件与扫描样件由用户指定路径（D:\W 规范搜集 13 文件取 1 文字层小文件整本 + 1 扫描文件前 N 页）；N9 执行前向用户确认样件路径与 N（≤10）与出域预算。

## 4. 验收映射（节点 → 上游验收项）

| 节点 | 上游验收映射 | 出口判据 |
| --- | --- | --- |
| N1 | 详细 §1.3 + R-02（含 pdf-inspect 抽样对照） | test_triage 全绿 + verdict 抽样对照 |
| N2 | 详细 §2.3 + R-03 | test_render 全绿 |
| N3 | 详细 §3 + R-01/R-04 | test_orchestrator_pdf ①④ + 文字层样件端到端 |
| N5 | R-05 + 详细 §3.3 | test ②③⑤（TTY 选 C/B、非 TTY、--no-egress） |
| N6 | D-6 + R-01(--md/--html) | 键集校验过 + md/html 冒烟产出非空 |
| N7 | R-07 | 三件新测 + ms1..ms3+ms5 全绿（CI，离线） |
| N9 | R-01 扫描半部 + 详细 U-MS-4 V-2 | routing.method=glm、台账 cost/usage、表 status 非空（分母=检出表数）；人工门 |
| N8 | R-08 | v2.4/v1.2 修订稿生成、diff 仅相关章、存档沿用 |

## 5. 风险节点（每节点完成即对抗测试，以下加独立小审）

| 节点 | 风险 | 小审重点 |
| --- | --- | --- |
| N3 | 双模式兼容破坏 ms1 测试；弹选 TTY/非TTY 边界；run_pdf 未定义符号残留 | build_render_reg/--page-image 保留；isatty 分支；helper 全定义 |
| N5 | 选 B 许可语义与上层 v3 委托衔接 | 许可码/留痕/差异告知硬断言 |
| N6 | M13 键集不匹配静默空输出 | 键集前置校验脚本 |
| N9 | 出域依赖 key/网络/预算；扫描页 OCR 交叉校验旁路（ocr_pages 单文件产物 vs _ocr_lines_for 读法，见 §6 轻微-C——**功能缺陷，编码时修正冻结 §3.2 描述**） | 真跑前先离线验证 ocr_lines 喂入非空；台账断言 |

## 6. 搭车注意（吸收各层轻微，不单独开任务）

- 详细复审轻微-B：main 需 `sys.exit(main())` 传播退出码（N3 落实）。
- 轻微-C（**功能缺陷，非纯措辞**）：`ocr_pages`（批量）产物为**单 JSON `{"pages":[{page,lines}]}`**、无逐页文件；`ocr_page`（单页）返回内存 dict 不落盘——`_ocr_lines_for` 若按"逐页文件"读法则恒空（A2- 精确化：仅 ocr_pages 写单文件）。N3 编码须改为读 ocr_pages 单文件产物（冻结 §3.2 描述据此修正；否则扫描页 ocr_lines 恒空、交叉校验静默旁路）。N3 编码 + N9 离线预验证。
- 轻微-D：test① images 非空若依赖 GLM 出域不封密——用**夹具注入**（raw_inject 或含图文字层页走 textlayer 的 images 路径）替代真出域，保离线 CI（N7）。
- 轻微-E：_scan_page_glm body 内 client/png 未定义——N3 编码时在 body 内构造 client、由 render_page 返回 png 路径（详细 §3.2 已含，编码对齐）。
- 步 3 复审轻微（--no-cache 已并入 D-5/详细 §3.4）；步 4 轻微（hybrid/skip_degraded 词表、unknown 无来源、M14 未列表）——N1/N3 编码时按需收敛并在自证声明注明。
- 建议 A3（N1 detect_intra 签名）：textlayer.detect_intra_regions 实参为 (page, text_lines, cfg) 3 参——N1 编码以实物签名为准（Step 5 §1.2 占位 4 参描述随之修正）。

---

（本文件为九步流程 Step 6 WBS；审查通过后进 Step 7 节点编码。）
