---
name: pdf-parse-v3
description: PDF 解析与结构化 JSON（先分诊后选引擎：文本层→版式坐标，扫描→GLM-OCR（API 主通道）/RapidOCR·WinRT（本地兜底）；再按 Schema v3.0 拆章节/条文/表图并溯源）。v4.0 管线：任意 PDF → 可溯源结构化 JSON（网格表格+图片索引）+ 附件图片库，全自动、失败诚实标记、成本可预算。触发词：读 PDF/PDF 是扫描件吗/规范 PDF/扫描 PDF/OCR 识别/标准条文/PDF 转 JSON/分章节分条文/文字版 PDF/PDF 版式/坐标/字体提取。
version: 2.1.1
---

# pdf-parse-v3：PDF 解析 → 结构化（Schema v3.0 / v4.0）JSON

读任何 PDF 前先**分诊**，再按「承载形态」选引擎。默认可产出 **v4.0** 可溯源 JSON
（网格表格 + lines[] 坐标 + 图片索引 + 附件图片库）；兼容 v3.0。
**输出标准**：`docs\PDF解析输出JSON规范.md`（Schema v3.0）；v4.0 字段级见 `docs\详细技术设计.md` §5。

## 0.1) v4 管线（Schema v4.0；设计书《详细技术设计.md》v1.3（含入口补全升级、处理遗留修订注与 2026-09-27 并发化/B1-B2-S1 修复））
```powershell
# 全自动：任意 PDF → v4.0 JSON（默认唯一产物）+ 附件图片库；MD/HTML 按需（--md/--html，接线 M13）
python assets\v4\orchestrator.py <pdf> --out <workdir> [--no-egress] [--no-cache] [--concurrency 6] [--md] [--html] [--pages 1-10] [--budget-glm X] [--budget-review Y] [--ignore-gpu-lib]
# 离线验收（黄金夹具重放，零网络；不改旧资产）
python tests\v4\test_ms1_smoke.py && python tests\v4\test_ms2_replay.py && python tests\v4\test_ms3_ladder.py && python tests\v4\test_ms5_acceptance.py && python tests\v4\test_triage.py && python tests\v4\test_render.py && python tests\v4\test_orchestrator_pdf.py && python tests\v4\test_fix_falsifiability.py && python tests\v4\test_budget_confirm.py && python tests\v4\test_concurrency.py
```
- **引擎降级口径（必读，禁止无感降级）**：v4 **整管线结构性不可跑**（M1/M2 缺失、依赖不满足等无法产出 v4）时，orchestrator **先弹出选择项**（A 解决依赖重跑 v4 / B 显式降级 v3.0 并告知产物差异 / C 取消），用户选择后才能降级——**未选择不产出、禁止静默改走 v3**；非交互（CI/管道）环境中止 + 退出码 + 留痕 `work/degrade_choice.json`。**页/表级视觉不可用**（无 key / `--no-egress` / 断网）属 FR-D7 自动本地兜底 + 诚实标记，**不弹窗**。**预算超限（FR-D5）例外**：交互环境弹选「1 继续（超额放行，本次运行该通道不再询问）/ 2 停止该通道（降级）」，非交互环境不弹窗、按 FR-D7 降级；两种情形都写 `work/budget_choice.json` 留痕，`chosen` 取三值：`allow_exceed`（用户放行超额）/ `degrade`（用户选停止，或非交互环境自动降级）/ `error`（交互不可用，视为未获答复——不记忆、不静默）；`reason` 区分 `channel_limit`（通道预算）与 `peak_cap`（峰谷封顶），放行只豁免同一 `reason`。`budget.confirm_on_exceed=false` 可关掉弹选、退回旧行为。
- **模块**（`assets\v4\`）：`config.default.json`（参数集中）、`triage(M1 分诊)`、`render(M2 页渲染+坐标登记)`、
  `vision_client(M4 唯一出域点)`、`textlayer(M3)`、`ocr_channel(M5)`、`table_adapter(M6 适配层)`、`gate(M7 校验门四信号分层)`、
  `defect_ladder(M8 阶梯)`、`structurer(M9 v4 组装)`、`figures(M10 图片文件化)`、`quality(M11 指标/台账)`、
  `orchestrator(M12 CLI/编排)`、`serialize_md/html(M13)`、`geo_rebuild(M14 几何重建)`、`pipeline(离线验收)`。
- **设计锚点**：唯一坐标=渲染页像素系；表格=网格模型（守恒 Σ(rs*cs)=R*C）；图=文件+索引不内联像素；
  校验门四信号分两层（gate-failure 否决 / hints 引导二意见）；D3 终裁在第二意见窄任务转写；
  任何失败收敛「诚实标记+原文保留」，不静默覆盖；密钥只读用户级配置目录；`--no-egress` 全局短路出域。
- **兼容**：旧 v1–v3 JSON 读取路径永久保留（FR-G5）；schema_version 字段治理版本；orchestrator 保留 `--page-image` 兼容模式（离线验收/既有测试用）。

## 0) 新机器首装：依赖自检 + 一键安装
```powershell
powershell -File assets\check-env.ps1          # 只检查
powershell -File assets\check-env.ps1 -Install  # 检查并自动补装缺失包
```
探测：DSH 专用 Python（`$DSH_HOME/runtime\python*`）→ 依次验证/安装
`pypdf` `rapidocr_onnxruntime` `pymupdf` `pdfplumber`（清华镜像，失败回退默认源）→
PowerShell 5.1 与 zh-Hans OCR 语言包 → curl。缺 `$DSH_HOME/runtime` 的 Python 时给出指引
（装 3.12 到该目录或设 `$env:DSH_PYTHON`）。输出 `[OK]/[MISS]/[WARN]` + `RESULT ok/warn/fail`。

## 1) 分诊（先测后读）
```powershell
powershell -File assets\pdf-inspect.ps1 -Pdf "X.pdf"   # verdict: text | scanned | hybrid（抽样判）
powershell -File assets\pdf-extract.ps1 -Pdf "X.pdf" -IncludeText   # 逐页路由：文本页直抽 / 扫描页 OCR
```

## 2) 引擎决策（第一性：PDF 内容=文字对象 or 图像）
> **默认主路径 = v4 全自动**（`orchestrator.py <pdf>`，分诊/逐页路由/降级弹选全内置，见 §0.1）。
> 下表为 **v3 兼容引擎表**（旧流程/按需手工路由用；整管线降级到 v3 须先弹选经用户确认，见 §0.1）。
| 引擎 | 适用 | 入口 | 说明 |
|---|---|---|---|
| **layout** | 有文本层（电子版） | `python assets\pdf_layout.py X.pdf out.json` | PyMuPDF 逐行坐标(y,x,x1)/字号/字体；阅读序；页眉页脚按 y 带+重复+页码归一剔除；单/双栏判定 |
| **RapidOCR** | 扫描件（**本地备份/兜底**，默认不启用） | `powershell render-pages.ps1` → `python rapid_ocr_pages.py` | onnxruntime CPU；对拍完胜 WinRT；**每页报进度+每页落盘+断点续跑**；**本机单进程顺序跑（防 CPU 抢占卡机）**；不参与双源交叉校验 |
| **WinRT OCR** | 快速预览/兜底 | `winrt-ocr.ps1`（PS5.1） | 零依赖 |

## 3) 结构化 v3.0（章/条/表/图 + 溯源）
```powershell
python assets\pdf2v3.py --parts "p1.json,p2.json" --out out_v3.json --name 名称 --code 编号 `
  --year 1987 --doc-class compilation --type "正文（OCR提取）" --sources "a.pdf,b.pdf" --engine rapid [--json-issues i.json]
python assets\finalize_v3.py out_v3.json report.json   # A3/A6 质检 + 抽样报告
```
- `pages[]` 页容器（text+tables+figures 归位）、`chapters/articles` 带物理页码、列项拆分、
  目录行/页眉页脚剔除、章号前缀过滤；**解析失败不强行拆条，原文始终在 pages[].text**（A1/A2）。
- 输入兼容：`pdf-extract -IncludeText` 的 extract.json 或 `rapid_ocr_pages` 的 rapid.json（`{"pages":[{page,text}]}`）。

## 4) 并行/并发纪律（按引擎分治，勿混用）
- **本地 RapidOCR：单进程顺序跑**——多进程会抢满本机 CPU；该纪律**只约束本地引擎**，不是全局口径；确需并行则 `$env:OMP_NUM_THREADS=4`。
- **GLM-OCR 出域通道：有界并发**——API 端不受本机 CPU 约束，串行纯属无谓瓶颈；用 `--concurrency N`（默认 6，`N=1` 回退串行）——它是**页级调度并发度**，主路径与 `--page-image` 兼容模式都受其管辖（出域与本地渲染并行；本地 RapidOCR 由引擎锁串行、PDF 后端由 `render.PDF_BACKEND_LOCK` 串行）；429/5xx 指数退避、`Retry-After` 优先；并发下台账/预算/缓存/registry 与本地兜底产物 `work/ocr/ocr_pages.json` 均加锁。**按引擎分治**：页级并发只作用于出域与渲染，本地 RapidOCR 仍是单实例 + 调用串行。
- **本地 OCR 不参与双源**：v4 主路径扫描页以 GLM 整页解析为唯一内容源；RapidOCR 仅在无 key／`--no-egress`／视觉不可用时作 FR-D7 本地兜底（默认不跑、不作交叉校验信号）。历史文档「本地 OCR 校验通道默认开启」已作废。**GLM 主路径不消费本地行盒产物**（该产物只按页号索引、无文档标识，跨文档或复跑会串页）。
- OCR 老扫描件章题偶有错字（页码可信、文字按页回查）；表格单元数据不回造，原文在 text。
- 新机器依赖：直接 `powershell -File assets\check-env.ps1 -Install`（自动装 pypdf/rapidocr_onnxruntime/pymupdf/pdfplumber）；缺 `$DSH_HOME/runtime` Python 时按提示安装或设 `$env:DSH_PYTHON`。

## 5) 与其他技能协作
- 查标准状态/编号 → **`std-official-search`**；其 openstd 图档页图下载后可用本技能 render/OCR 解析。
- 测试：`tests\run-tests.ps1` 四层自测 35 项（语法/环境/check-env/layout/rapid/结构化，离线全绿；官方源实网冒烟在 std-official-search）。
- 输出规范：内置 `docs\PDF解析输出JSON规范.md`。拆分自原 `gb-standard-direct`（2026-09）。

## 6) 经验与踩坑速查（实测沉淀）
- **引擎=承载形态**：有文本层 → layout(PyMuPDF 坐标/阅读序/版式)；纯扫描 → RapidOCR(量产)；快速预览 → WinRT。
- **RapidOCR 决策数据**：1987 老扫描同页对拍完胜 WinRT（乱码→干净，表格注文可读）；`det_limit_side_len=960`，CPU ~2-11s/页；**单进程顺序**（仅本机约束），每页报进度+每页落盘+断点续跑（重跑自动跳过已完成页）；该对拍只与 WinRT 比过，**未与 GLM-OCR 同场景对照**。**定位＝本地备份/兜底，默认不启用、不参与双源**。
- **长任务纪律**：进度读磁盘产物，不依赖后台回传；checkpoint 文件即真相。
- **分诊阈值**：文本页=可读率≥50% 且 ≥5 可读字符（封面/标题短页仍走文本直抽）；可读率<30% 判伪文本层按 OCR。
- **结构解析启发式**：目录页按"一页≥3 个章行"整体剔除；条文号须匹配当前章号前缀（防表格数字行误判）；拆条失败留 `pages[].text` 不强行拆（A1）。
- **条文号分隔符口径**（2026-09-19）：`clean_line` 只折 `. ． · ‧ ∙ ⋅`；**不折 `, ，、`**——实测折逗号/顿号会造出假条文（`5、6 项说明`→条文 `5.6`、`1，234 件设备`→`1.234`）。WinRT 把小数点认成 `，` 的情形在 `winrt-ocr.ps1` 内局部归一化（仅行首「数字，1–2 位数字」）。
- **页脚页码形态规则**（2026-09-19）：`RE_PAGER` 剔除 `第N页(共M页)` 与 `- N -`（逐页变化，L71 重复计数永远抓不到）；**不认 `N/M`**（真实语料有裸行 `687/891` 是表格数据）。
- **pypdf 加密坑**：锁态访问页抛 `FileNotDecryptedError` → 先探测 encrypted/locked 再优雅报错。
- **夹具先验**：手造测试 PDF 的 XObject 引用号/结构必须先自检——坏夹具曾造成"OCR 全空"假警报（先验夹具再判产品缺陷）。
- **编码铁律**：含中文 .ps1 必须 UTF-8 BOM（PS5.1 无 BOM 按 GBK 解析即炸）；数据文件统一 UTF-8。
- **WinRT(PS5.1)**：类型需先注册；`IAsyncAction`(RenderToStream)与 `IAsyncOperation<T>` 用不同 AsTask 封装；pwsh7 无 WinRT 投影，须经 `powershell.exe -File` 调用。
