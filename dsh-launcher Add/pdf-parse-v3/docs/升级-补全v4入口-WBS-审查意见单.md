# 升级 WBS 审查意见单（Step 6 · 第一轮独立对抗性审查）

| 字段 | 内容 |
| --- | --- |
| 文档 | pdf-parse-v3 就地升级 Step 6 WBS 任务清单 |
| 审查对象 | `docs/升级-补全v4入口-WBS.md`（全文，72 行） |
| 审查轮次 | 第一轮（独立对抗性审查，非复审） |
| 日期 | 2026-09-09 |
| 审查依据 | 冻结上游：简版需求书（R-01..08/VG-1..6）、细化任务书（R-01..08/D-1..3）、简版技术设计（D-4..7/§3.1-3.5）、详细技术设计（§1-§6）；实物：`assets/v4/` 各模块、`assets/pdf_text_probe.py`、`tests/v4/` 既有四件、`assets/v4/config.default.json` |
| 结论 | **0 阻断 · 1 严重 · 6 轻微 · 4 建议**（见下文，按严重度排序） |

> 说明：审查仅依据上述冻结文档与实际文件，未采用作者/编排者的推理与结论。所有引用一律用锚点（章节/字段/行号/文件名），不复制原文长段。

---

## 一、阻断（0 条）

无。N1/N2/N3 编码所需的全部上游规格（字段级 Schema、局部代码、接口签名）、既有模块（pipeline/structurer/textlayer/vision_client/serialize_md/html/ocr_channel）、复用资产（files/pdf_text_probe.py）与配置（config.default.json 含 `render.resolution_steps` 等）均已实读存在；依赖图无环、无孤儿、串行链 N1→N2→N3→N5/N6→N7→N8 可行，编码可开始。

---

## 二、严重（1 条）

### S1. V-2 / R-01「扫描样件出域真跑」验收未映射到任何节点出口判据 —— 里程碑 U-MS-4 出口被截断
- **anchor**：WBS §4 N3 出口判据行、WBS §4 N7 出口判据行；对照 §5 风险表。
- **basis**：R-01 验收含「扫描样件（前 N 页）出域跑通」（P0）；细化任务书 §6 验收路径 V-2 =「扫描样件 N 页出域：routing=glm、台账 cost/usage、表 status 非空（分母=检出表数）」，属真分母可失败验收；简版技术设计 §5 里程碑 U-MS-4 出口明确写「CI 绿 + V-2 台账」。而 WBS §4 N3 出口判据仅写「test_orchestrator_pdf ①④ + 文字层样件端到端」（只覆盖 R-01 的文字层半部），§4 N7 出口判据仅写「三件新测 + ms1..ms5 全绿（CI）」——均为离线 CAS；真实扫描样件出域、台账/status 留痕这一 P0 验收在 8 个节点中无任何出口承接口。设计 §5 test① 用的是合成微型 PDF + 夹具注入（§6 轻微-D），并非真实出域，不能替代 V-2。
- **confidence**：中。理由：真实出域需 API+外部样件，可能被作者当作「节点外人工验收」，但 WBS 以「每节点出口可测」为定位（L8），且未在任何节点/小节注明该人工门，导致 U-MS-4 的「+ V-2 台账」出口被静默截断；建议显式补入（N7 出口加「+ 扫描样件出域真跑（人工门，routing=glm/台账/身status）」或单列验收节点）。

---

## 三、轻微（6 条）

### L1. 「ms1..ms5」区间记法暗含并不存在的 ms4，与上游显式列法不符
- **anchor**：WBS §4 N7 出口判据「三件新测 + ms1..ms5 全绿（CI）」。
- **basis**：`tests/v4/` 实测仅有 test_ms1_smoke/test_ms2_replay/test_ms3_ladder/test_ms5_acceptance 四件，**无 test_ms4**；上游（细化任务书 §R-01/§4、需求书 R-07/§6 验收4、参考依据「既有四件 ms1/ms2/ms3/ms5」）均显式逐件列出 ms1/ms2/ms3/ms5，不用区间。「ms1..ms5」会在检索/CI 脚本按区间 glob 时误引入不存在的 ms4。
- **confidence**：高。

### L2. test_orchestrator_pdf.py 的断言归属在 N3 与 N5 间重叠，且与 N7「测试三件」重复，节点边界模糊
- **anchor**：WBS §1 N3 自验列「端到端/弹选/幂等/--no-egress」；§1 N5 自验列「test_orchestrator_pdf ②③⑤」；§1 N7 产物「测试三件 + 回归」。
- **basis**：设计 §5 测试①..⑤ 中，②③=弹选（TTY 选 C/B、非 TTY）明确归 N5，⑤=--no-egress 亦然；但 N3 自验却同时写「弹选/--no-egress」，与 N5 的 ②③⑤ 交叉；且 test_triage/test_render 已在 N1/N2 自验出现、test_orchestrator_pdf 在 N3/N5 出现，N7 又以「测试三件」作为自身产物——同几处断言被三个节点重复声称归属，难以界定各节点「完成」边界。
- **confidence**：中。

### L3. R-02 验收项「verdict 与 pdf-inspect 判据一致（抽样页对照）」未在 N1 自验/出口判据体现
- **anchor**：WBS §1 N1 自验「test_triage.py：合成 text/blank/加密 → verdict/blank_pages/TriageError/字段齐全」、WBS §4 N1 出口判据「test_triage 全绿」。
- **basis**：细化任务书 R-02 验收明确含「对文字层样件与扫描样件各跑一次：verdict 与 pdf-inspect 现判据一致（抽样页对照）」。N1 自验只列 合成页→verdict/blank/异常/字段齐全，未含「抽样页对照 pdf-inspect」这一可失败断言；若仅凭 test_triage 全绿，R-02 的该子验收无对应出口。
- **confidence**：高。

### L4. N4 自验仅校验 CLI/模块清单与实物一致，未校验 SKILL.md 的降级弹选口径（R-06 修正点 4 / R-05 验收 3）
- **anchor**：WBS §1 N4 自验「一致性脚本：SKILL.md 所列 CLI 与 argparse 一致、模块清单对文件」；WBS §5 N5。
- **basis**：R-05 验收要点（需求书 §5）要求「SKILL.md 与 CLI 均有对应口径与行为」；细化任务书 R-06 修正点 4 明确「§1 分诊节/§2 引擎决策表：注明『整管线结构性降级须先征询用户（R-05）』」。N4 自验只比对 CLI 参数与模块清单，未设断言校验「降级必询/弹选口径」是否已写入 SKILL.md 对应节，而 N5 自验仅验证运行行为，未回检查 SKILL.md 文字——口径文字与实际行为是否闭环无节点把关。
- **confidence**：中。

### L5. N8 出口判据未含 R-08 的「存档惯例沿用」与内容级校验
- **anchor**：WBS §4 N8 出口判据「v2.4/v1.2 修订稿生成、diff 仅相关章」。
- **basis**：细化任务书 R-08 验收为「v2.3/v1.1 冻结内容不重开；diff 仅相关章/增条目；存档文件保留」；设计 §4.1/4.2 差异清单给出需增内容（§3.1 例外界定、§3.3-2 修订、FR-A5、§10 TTY 收敛行等）。N8 出口仅「修订稿生成 + diff 仅相关章」，既未含「存档文件保留」，也未对「差异清单所载项是否实际写入」设断言，可能以「diff 只动相关章」通过却漏写 FR-A5 等条目。
- **confidence**：中。

### L6. N8 标注「CD 前」而执行体列「CD」，上下游口径为「CD 阶段并入」
- **anchor**：WBS §1 N8 行：产物括号「（R-08，CD 前）」、执行体「CD」。
- **basis**：细化任务书 §1.1 第 4 项与 R-08 均写「CD 阶段并入」；设计 §4.1/4.2 标注「CD 阶段执行」。同一节点「CD 前」与「CD」并见，且与执行体「CD」并存，指向含糊（是 CD 前置自检，还是 CD 阶段交由 CD 执行体完成）。
- **confidence**：高。

---

## 四、建议（4 条）

### A1. §6 轻微-C 实为冻结 §3.2 的功能性缺陷，被归为「轻微·搭车」偏轻；建议升级为「需修正冻结设计」项并纳入 §5 风险
- **anchor**：WBS §6 第 65 行（轻微-C）；对照 §5 风险表。
- **basis**：`ocr_channel.ocr_pages`（实物）输出单文件 `{"pages":[...]}`（L65-98，不写逐页文件）；而详细设计 §3.2 `_ocr_lines_for` 读 `work/ocr/page_NNNN.json`（逐页文件）。二者不一致 → ocr_lines 恒空 → 扫描页 OCR 双源（FR-B1）静默失效，属「静默降级」同源问题，正是本次升级要根除的缺陷类型。WBS §6 中仅以「轻微」并按「据此修正 §3.2 描述」处理，等价于在冻结层上改规格，但未在 §5 风险表列为需重点守住的修正项。
- **confidence**：中。

### A2. 样件（文字层整本 / 扫描前 N 页）不在仓库，亦无节点负责获取/定位，N3/N6 自验依赖它
- **anchor**：WBS §4 N3 出口「文字层样件端到端」、§1 N6 自验「md/html 冒烟（文字层样件）」。
- **basis**：全库 glob 未见任何样件 PDF（仅 `tests/vision_shootout/` 下的 PNG）；设计 §7 风险提到「50016 全 464 页」等真实样件属外部文件；细化 D-3 定「1 文字层整本 + 1 扫描前 N 页」但未指定其来源/路径，也未将其归入任一节点产物。若无样件，N3/N6 的自验与出口判据无从执行。
- **confidence**：中。

### A3. N1 依赖未列 textlayer（供 detect_intra_regions），且其调用签名与实物不符（占位）
- **anchor**：WBS §1 N1 依赖（只列「冻结 §1 详细设计；assets/pdf_text_probe.py」）；对照详细设计 §1.2 `detect_intra`。
- **basis**：设计 §1.2 `detect_intra` 以 `(page, doc, page_no, cfg)` 四参调用 `textlayer.detect_intra_regions`，而实物签名（textlayer.py L123）为 `(page, text_lines, cfg)` 三参；设计明确「Step 7 编码修正」为占位。N1 依赖栏未提 textlayer 这一现成模块，接口契约不完整，编码时易漏对齐其真实签名。
- **confidence**：中。

### A4. N3 承载面较宽（双模式+run_pdf+maybe_offer_degrade+helperset），建议按可测单元分组自验或拆分
- **anchor**：WBS §1 N3（产物/接口/自验跨 双模式 与 弹选 与 编排）；§5 N3 风险「run_pdf 未定义符号残留」。
- **basis**：设计 §3.1-3.3 的 run_pdf 含 结构性自检/_ms1_page_loop/_scan_page_glm/_scan_page_local/_ocr_lines_for/render_reg_for/maybe_offer_degrade 等十余个 helper；单节点承担过多，节点级「编码→自验」边界难聚焦。建议在 N3 内部按「双模式兼容」「run_pdf 主链」「弹选」分组（§5 已把 helper 全定义列为小审点，可在编码任务书层面进一步分组以利逐项验收）。
- **confidence**：低-中。

---

## 收敛小结

未发现阻断级问题（编码可开始、依赖图无环无孤儿）；发现 **1 条严重**——V-2/R-01「扫描样件出域真跑」验收未映射到任何节点出口判据、U-MS-4 出口被静默截断（建议在 N7 出口补人工门或单列验收节点）；另有 6 条轻微（ms1..ms5 记法、test_orchestrator_pdf 断言归属重叠/三件重复、N1 缺 pdf-inspect 对照、N4 未校验降级口径、N8 缺存档/内容校验、N8「CD 前/CD」措辞）与 4 条建议（§6 轻微-C 实为冻结缺陷建议移入风险、样件来源未定、N1 依赖/签名、N3 拆分）。预估修复范围：**以 WBS 文档内措辞与出口判据的修订为主（如实测 + 出口判据 + 节点归属），不涉及改已冻结上游文件**；唯 S1 需明确 V-2 归属、A1 需把「样件来源」与「轻微-C 修正」在原 WBS §6/§5 内补齐，整体为低-中工作量的小幅修订。
