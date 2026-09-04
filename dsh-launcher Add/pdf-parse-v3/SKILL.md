---
name: pdf-parse-v3
description: PDF 解析与结构化 JSON（先分诊后选引擎：文本层→版式坐标，扫描→RapidOCR/WinRT；再按 Schema v3.0 拆章节/条文/表图并溯源）。触发词：读 PDF/PDF 是扫描件吗/规范 PDF/扫描 PDF/OCR 识别/标准条文/PDF 转 JSON/分章节分条文/文字版 PDF/PDF 版式/坐标/字体提取。
version: 1.0.0
---

# pdf-parse-v3：PDF 解析 → 结构化（Schema v3.0）JSON

读任何 PDF 前先**分诊**，再按「承载形态」选引擎，最后用 `pdf2v3` 产出**可溯源**的
v3.0 JSON。**输出标准 = 本技能内置规范**：`docs\PDF解析输出JSON规范.md`
（《PDF 解析输出 JSON 制作规范》，含 Schema v3.0、溯源/表图/图说、质检 A3/A6）。

## 0) 新机器首装：依赖自检 + 一键安装
```powershell
powershell -File assets\check-env.ps1          # 只检查
powershell -File assets\check-env.ps1 -Install  # 检查并自动补装缺失包
```
探测：DSH 专用 Python（`~/.dsh/runtime\python*`）→ 依次验证/安装
`pypdf` `rapidocr_onnxruntime` `pymupdf` `pdfplumber`（清华镜像，失败回退默认源）→
PowerShell 5.1 与 zh-Hans OCR 语言包 → curl。缺 `~/.dsh/runtime` 的 Python 时给出指引
（装 3.12 到该目录或设 `$env:DSH_PYTHON`）。输出 `[OK]/[MISS]/[WARN]` + `RESULT ok/warn/fail`。

## 1) 分诊（先测后读）
```powershell
powershell -File assets\pdf-inspect.ps1 -Pdf "X.pdf"   # verdict: text | scanned | hybrid（抽样判）
powershell -File assets\pdf-extract.ps1 -Pdf "X.pdf" -IncludeText   # 逐页路由：文本页直抽 / 扫描页 OCR
```

## 2) 引擎决策（第一性：PDF 内容=文字对象 or 图像）
| 引擎 | 适用 | 入口 | 说明 |
|---|---|---|---|
| **layout** | 有文本层（电子版） | `python assets\pdf_layout.py X.pdf out.json` | PyMuPDF 逐行坐标(y,x,x1)/字号/字体；阅读序；页眉页脚按 y 带+重复+页码归一剔除；单/双栏判定 |
| **RapidOCR** | 扫描件（量产） | `powershell render-pages.ps1` → `python rapid_ocr_pages.py` | onnxruntime CPU；对拍完胜 WinRT；**每页报进度+每页落盘+断点续跑**；单进程顺序跑防卡机 |
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

## 4) 并行纪律与故障
- RapidOCR 多进程会抢满 CPU → 单进程顺序跑；确需并行则 `$env:OMP_NUM_THREADS=4`。
- OCR 老扫描件章题偶有错字（页码可信、文字按页回查）；表格单元数据不回造，原文在 text。
- 缺 pypdf/rapidocr/pymupdf：脚本内置 `Ensure-PyPdf` 自动补装；其余 `pip install rapidocr_onnxruntime pymupdf pdfplumber`。

## 5) 与其他技能协作
- 查标准状态/编号 → **`std-official-search`**；其 openstd 图档页图下载后可用本技能 render/OCR 解析。
- 测试：`tests\run-tests.ps1` 四层自测 22 项（语法/环境/layout/rapid/结构化，离线全绿；官方源实网冒烟在 std-official-search）。
- 输出规范：内置 `docs\PDF解析输出JSON规范.md`。拆分自原 `gb-standard-direct`（2026-09）。
