# 升级-补全v4入口：CI 全量大审意见单（第 1 轮 · 独立对抗审查）

| 字段 | 内容 |
| --- | --- |
| 轮次 | 第 1 轮（本文件首次生成，无既有内容需标注） |
| 审查类型 | 步骤 8 CI 全量大审（非复审）；仅报告模式（只写意见单，未进修复闭环，未改任何产物） |
| 审查者 | 独立子审查者（未 fork 编排/作者会话，只喂产物全文+冻结依据+实测输出；未喂作者推理与结论） |
| 对象 | `assets/v4/triage.py`(M1)、`assets/v4/render.py`(M2)、`assets/v4/orchestrator.py`(M12)、`SKILL.md`(§0.1/§2)、`tests/v4/{test_triage,test_render,test_orchestrator_pdf,ci_all}.py` |
| 依据 | ①冻结文档链：`docs/升级-补全v4入口-{简版需求书,细化任务书,简版技术设计,详细技术设计,WBS}.md` 及其意见单；②冻结《详细技术设计.md》v1.1（§3/§6.1/§6.2/§6.12/§10）与《需求确定书.md》v2.3（FR）；③`assets/v4/` 既有模块（textlayer/vision_client/pipeline/structurer/serialize_md/html/ocr_channel/config.default.json）与 `assets/pdf_text_probe.py`；④代码内部一致性（含 `py_compile`、实际 `import`、探针脚本实测）。 |

## 0. 实测证据（审查者本机执行，只读）

- `python tests/v4/ci_all.py` → `RESULT CI ALL_GREEN`，`TOTAL pass=111 fail=0`。
  - 逐套：test_ms1_smoke pass=43；test_ms2_replay pass=9；test_ms3_ladder pass=7；test_ms5_acceptance pass=8；test_triage pass=13；test_render pass=10；test_orchestrator_pdf pass=21（fail 全 0）。全部 7 套件退出码 0 且都带 `RESULT pass=N fail=M` 实计数——**非空跑**。
  - `compile py=16 bad=0`；`doc-consistency ok=True`，输出真实细节 `CLI: skill['--budget-glm',…,'--out'] ⊆ argparse[...,'pdf'] missing=[]`、`mods missing=[]`——**非恒真**（改 SKILL.md 参数或删模块会转 False）。
- 复用 `python -m py_compile`（本机以 `PYTHONDONTWRITEBYTECODE=1` 防产物树污染）：triage/render/orchestrator 语法均通过；`import orchestrator`、`import triage`、`import render` 均成功，所引「实物签名」齐全：`textlayer.detect_intra_regions(page,text_lines,cfg)`、`textlayer._detect_columns(page_w,lines)`、`structurer.assemble_v4(*,pages_parts,…)`、`ocr_channel.{_make_engine,ocr_page} / OcrUnavailable`、`vision_client.{VisionClient,VisionError,BudgetGate,GLM_CHANNEL,SECOND_OPINION_CHANNEL,TASK_FULL_PAGE,load_keys}`、`pipeline.process_page_md(page_no,md,cfg,*,ocr_lines,ocr_available,m4,raw_resp)`——与调用点一一对得上，无未定义符号。
- 探针 B（本机实测）：`draw_rect`+`insert_text("FIG1 示意图")` 的「img 页」被 `triage` 判为 `doc_verdict=text`、`页verdict=text`、`ratio=1.0`——即测试夹具的「内嵌位图页」实际走文字层，不进入 GLM/扫描路径（详见严重-S1）。
- 探针 A（本机实测）：`render_page(...,target_width=2000)` 返回 `dpi=72.0 pixel=[2000,2800] downsampled_from=null`——target_width 指定分支 dpi 被恒定改写，降档循环实际不降档（详见轻微-5）。

> 说明：以上为「复用上轮 L0 确定性探针+本轮独立解读」；探针只编码「输入→确定性计算」，未内置预期结论，本轮结论由审查者独立形成后与探针输出比对。

---

## 一、阻断级

**未发现阻断级问题。**

依据：三新/改文件语法与实 import 通过（编译/导入证据见 §0）；`run_pdf` 的 text/scanned/local/GLM 各分支均可达且闭环（text 页→textlayer；image/pseudo/unknown/scanned→GLM 或本地兜底；任何失败收敛到 `{"page":N,"degraded":True}` 或诚实标记，无未达分支、无必然崩溃）；弹选仅结构门触发、FR-D7 页/表级不经过；CI 非假绿灯（§0 实计数）。故无阻断。

---

## 二、严重级

### S-1（严重）`test_orchestrator_pdf` ①「含图页 images 非空」断言未实现（偏离设计 §5 / WBS 轻微-D / N7 出口判据）

- **anchor**：`tests/v4/test_orchestrator_pdf.py:89`（fixture `pages=("text","text","text")`）、`:95-103`（①内仅校验 schema_version/页数/triage.json，无任何 `images` 非空断言）、`:8-9`（docstring 自认「纯文字层 fixtures 的 images 恒空属如实」）。
- **basis**：升级《详细技术设计.md》§5（:449）明确要求「①合成微型 PDF：2 页文字层 + 1 页内嵌位图（栅格图，供 images 断言）…**含图页 images 非空断言**（raw_resp 钉定生效，防静默丢失 FR-B6/S6）」；WBS（:72 轻微-D）进一步给定离线方案「**用夹具注入**（raw_inject 或含图文字层页走 textlayer 的 images 路径）替代真出域，保离线 CI（N7）」；WBS §4（:52）N3 出口判据「test_orchestrator_pdf ①④」。实现以 3 个纯文字页代替「2 文字+1 位图」，且整段无 `images` 非空断言，等于把设计明确要求、且承载"防 raw_resp 钉定回归导致图片静默丢失"（严重-2/r3 修复链）的验收项整体放弃。
- **证据链（本机实测/代码）**：探针 B 证实测试的「内嵌位图页」被 triage 判为 `verdict=text`；`textlayer.textlayer_page` 返回顶层 `"images": []`（`assets/v4/textlayer.py:117`），栅格区只进 `routing[0].intra_page_regions`（:120）；`structurer.assemble_v4` 的 `pages[].images=part.get("images",[])`、`metadata.figure_count=sum(len(images))`（`structurer.py:94,110`）。故顶层 `pages[].images` 只可能由 GLM 路径 `pipeline.process_page_md` 的 `raw_resp.layout_details` 填充（`pipeline.py:34,85`）。当前测试既未 mock GLM 客户端注入含 image block 的 `raw_response`，也未用 `page.insert_image` 内嵌真位图后断言（即便内嵌位图，顶层 `images` 仍为空，须 mock 或断言 `routing[].intra_page_regions`），故「含图页 images 非空」客观上不可达、被静默省略。
- **confidence**：high（设计/WBS 明文要求 + 实测探针 + structurer/textlayer/pipeline 三处代码交叉一致）。
- **修复预估**：在 `tests/v4/test_orchestrator_pdf.py` ①新增一个走 GLM 路径的夹具或 mock `VisionClient.glm_parse_page`（`monkeypatch` 返回 `{"raw_response":{"response":{"md_results":…,"layout_details":[含 1 个图块]}}}`），并断言 `d["metadata"]["figure_count"]>0` 或对应 `pages[i]["images"]` 非空、且 `table_count`/`figure_count` 与注入一致；改动限于 tests 内 + 一个桩，不动产品码。

---

## 三、轻微级

### L-1（轻微）弹选 TTY 分支未经真实子进程/pty 验证（偏离设计 §5「stdio 注入」与 WBS N5）
- **anchor**：`tests/v4/test_orchestrator_pdf.py:110-137`（TTY 选 C 用函数级 `orc.maybe_offer_degrade(...,tty=True)` + monkeypatch `builtins.input`）、`:113-114`（自认「subprocess 下 isatty False → 需用 pty 才为 True」）。
- **basis**：设计 §5:449 要求「②…→ TTY 模拟（stdio 注入）选 C → exit2」；WBS N5:64 验收「TTY 选 C/B」。实现改为函数级调用，真实 `sys.stdin.isatty()` + 真实 `input()` 的端到端路径从未被验证（非 TTY 分支倒是有真实子进程覆盖 :114-122）。若真实终端下 `input()` 返回异常格式、EOF、或 `isatty` 判定与实际不符，离线 CI 不暴露。另 TTY 选 C 分支未断言「无 v4 产物」。
- **confidence**：medium。

### L-2（轻微）test_render ⑥ 未断言「降档记录」，且夹具页宽 <5000pt（偏离设计 §5：448）
- **anchor**：`tests/v4/test_render.py:106-123`（仅 `ok_size`(≤10MB) 或 `e.kind=="oversize"`，无 `dpi<dpi_default`/`downsampled_from` 断言；页 `width=2000`）。
- **basis**：设计 §5:448 要求「合成超大页（宽≥5000pt 高密度图）→ **断言触发降档（registry.dpi < dpi_default 或 downsampled_from 记录）**且最终 ≤10MB」。实现只验最终尺寸或 oversize——若该页在 dpi 220 下恰 ≤10MB，则未触发降档也判绿，10MB 降档与 `downsampled_from` 登记（FR §3.4/FR-B2 坐标链必须与实际上传小图一致）实际未被验证。
- **confidence**：medium。

### L-3（轻微）测试断言用「或」放宽判据（违反设计 §5「无"或"判据」）
- **anchor**：`test_orchestrator_pdf.py:97-100`（schema_version 用一长串 `or`：`in ("4.0","v4.0",4) or ...`）、`:181`（`"fallback" in method or "ocr" in method`）。
- **basis**：设计 §5:449-450 明确「全部真分母可失败、无"或"判据」。两处虽可失败（非恒真），但属设计明令禁止的放宽形式；schema 断言接受 4 种表示，若 schema_version 结构被改动可能漏报。
- **confidence**：medium。

### L-4（轻微）test_triage ⑤ 零页测试空转跳过；③ blank_pages 仅断言「键存在」而非内容
- **anchor**：`test_triage.py:105-122`（`made=False` 分支 `t.check(...,True,"skipped")`，fitz 拒存 0 页导致零页 `TriageError` 从未实际触发，却计 pass）、`:90-91`（`"blank_pages" in res3["degraded"]` 恒真，未断言 `blank_pages==[2]`）。
- **basis**：设计 §1.3/§5:447 要求「合成 blank 页 → blank_pages」与「零页…应对」。当前：零页路径未测（靠「跳过」凑数）、`blank_pages` 内容（实际应为 `[2]`）未对照——均属空转/弱断言。
- **confidence**：high（代码与设计对照直读）。

### L-5（轻微）`render_page` 在 `target_width` 指定时降档循环失效（dpi 恒为派生值）；该分支当前不可达且未测
- **anchor**：`assets/v4/render.py:58-62`（`for dpi in dpi_steps:` 循环内 `if target_width is not None: dpi=round(tw*72/pdf_w,4)` 恒改写为同一值，循环形同一次）、`render.py:44-53`（降档序列构建）。
- **basis**：设计 §6.2/§2.1 m-05 要求「target_width 指定 / dpi 派生 + 10MB 降档」并存；探针 A 实测 `target_width=2000` → `dpi=72.0` 恒定，即若该档超 10MB 将永不降档、直接 `oversize`。当前 `orchestrator` 全管线 `render_page` 均以 4 实参（`target_width` 默认 None）调用、`render_reg_for` 手工构图不调 render_page——故该分支实际不可达，属潜伏缺陷（一旦未来开放 target_width=指定并遇大页即触发）。
- **confidence**：medium。

### L-6（轻微）`ci_all` 汇总绿灯不要求 `total_pass>0`（防「空转假绿」守卫缺失）
- **anchor**：`ci_all.py:96`（`all_green = all(rc==0) and not bad_compile and doc_ok`）。
- **basis**：gate 只看各套件退出码、编译、文档一致性；若某套件退化为「零断言」（`pass=0 fail=0 rc=0`）仍计绿。当前 7 套件均真实（111 断言），**现状非假绿**，但无 `pass>0` 守卫无法防御未来套件被抽干断言。
- **confidence**：medium。

### L-7（轻微）`maybe_offer_degrade` 签名与设计 §3.3 不符；`run_pdf` 每扫描页重建 VisionClient
- **anchor**：`orchestrator.py:147`（`def maybe_offer_degrade(reason, out, tty=True)`）vs 设计 §3.3:353（`maybe_offer_degrade(reason, cfg, out, tty=True)`）；`orchestrator.py:265-267`（`_scan_page_glm` 内每次 `VisionClient(...)`）vs 设计 §3.2:312（循环前一次性创建）。
- **basis**：设计示例签名含 `cfg` 形参，实现删除且调用同步匹配（内存自洽，功能无碍）；`VisionClient` 由一次性改为逐扫描页构建（多页扫描时重复创建/重复读取 keys），与设计结构差异。
- **confidence**：high（代码/设计直读）。

### L-8（轻微）`_scan_page_local` 用 `except (OcrUnavailable, Exception)` 吞并 `RenderError(oversize)`，导致该扫描页落为「空文本」
- **anchor**：`orchestrator.py:226-238`（`render_page(...)` 若 `RenderError(oversize)` 被 `except Exception` 捕获 → `_marker` + 返回空文本页）。
- **basis**：冻结《详细技术设计》§3.4/§10「>10MB → 本地管线（ocr_channel+geo_rebuild）继续」，FR-D7 属地兜底；但渲染超限时本可降分辨率重渲再 OCR，现直接判空。属兜底口径的局部不符（该页仍诚实标记，不崩溃）。
- **confidence**：medium。

---

## 四、建议级

### A-1（建议）`_structural_ok` 对 torch/tensorflow「存在即拒绝启动」易误伤
- **anchor**：`orchestrator.py:121-127`。
- **basis**：设计 §6.12/FR-G3 负向探测为设计意图，但装了 GPU 库却并不用于 v4 的机器会直接整管线判不可跑；建议改「**警告 + 可配置放行**（如 `--ignore-gpu-lib` 或 config 开关）」，保留纪律又降低误伤。
- **confidence**：medium。

### A-2（建议）`check_doc_consistency` 存在空转分支，且只校验单向
- **anchor**：`ci_all.py:47-53`（SKILL.md 找不到 `orchestrator.py <pdf>` 行 → `cli_line=None` → `args_in_skill=∅` → `ok1=True` 空转恒真）、`:54`（仅校验 skill⊆argparse，未校验 argparse 全参数是否回写在 SKILL.md 示例）。
- **basis**：真实性依赖 SKILL.md 该行存在；建议找不到时直接 `ok=False`，并补反向比对（argparse ⊆ skill）。
- **confidence**：high。

### A-3（建议）`_marker` 落盘路径双模式不一致
- **anchor**：`orchestrator.py:92-98`（`out_dir/"marks"`）与调用点 `run_pdf` 传 `work`（→`out/work/marks`）、`_ms1_page_loop` 传 `out`（→`out/marks`）。
- **basis**：同一「标记」在两模式下落到不同父目录，归档口径不一致。
- **confidence**：high（直读）。

### A-4（建议）`render_reg_for` 内 `from render import render_page` 仅 `noqa F401` 占位、未实际使用
- **anchor**：`orchestrator.py:195`。
- **basas**：残留导入；若真需同口径应实际调用或改注释说明，避免误导「已被 M2.render_page 消费」。
- **confidence**：high（直读）。

### A-5（建议）`test_orchestrator_pdf` ② TTY 分支 `finally` 未还原 `sys.stdin` 原对象、`real_isatty` 未使用
- **anchor**：`test_orchestrator_pdf.py:126-137`（`real_isatty` 赋值后未用；`:136-137` 又赋新 `TextIOWrapper` 而无还原）。
- **basis**：测试卫生问题（当前因后续分支不再用 `sys.stdin` 而未破坏，但属隐患）。
- **confidence**：high（直读）。

---

## 五、收敛小结

**未发现阻断级；发现 1 条严重级（S-1：`test_orchestrator_pdf` ①「含图页 images 非空」断言未实现，偏离设计 §5 + WBS 轻微-D + N7 出口判据，且未能在离线 CI 守卫 raw_resp 钉定/FR-B6-S6 的图片防丢回退）与 8 条轻微、5 条建议。**
**预估修复范围**：产品码无需改动（orchestrator/triage/render 的语法、实 import、双模式、run_pdf 胶水、raw_resp 钉定、FR-D7 兜底、弹选语义均与冻结设计一致且可运行）；真正需补的是 **tests/v4 测试收敛**——①为 `test_orchestrator_pdf` ①新增含图夹具/GLM-mock 并加 `images 非空`断言（S-1），②补 `test_render` ⑥ 的「降档记录」断言与 ≥5000pt 夹具（L-2）、去掉 `or` 放宽（L-3）、补零页/blank_pages 内容断言（L-4）、以真实 pty 补弹选 TTY 端到端（L-1）、`ci_all` 加 `pass>0` 守护与 doc-consistency 非空转 + 反向校验（L-6/A-2）。改动全部落在 `tests/v4/` 与 `tests` 桩，预估一处中等（S-1）+ 若干小改，约 1/2 天内可收敛，风险低。
