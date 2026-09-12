# 处理遗留：CI（Step 8）——复审意见单（仅报告 · 增量证据绑定复审）

| 字段 | 内容 |
| --- | --- |
| 复审对象 | Step 8 CI 门修复增量（S1/S2/L1/L2/A1/A2，六项），见 `docs/处理遗留-CI.md`（修订后）及其实物 |
| 复审模式 | 独立子审查者（无共享上下文）· 对抗性复审 · 仅报告（未修改任何被审文件） |
| 日期 | 2026-09-09 |
| 复核方法 | L0 实跑（裸命令+管道捕获，无 PYTHONUTF8）+ `-X utf8` 对照 + S2 变异探针（恒空集突变，不改仓库文件，副本在 %TEMP%）+ 行级直读；上游对账：`处理遗留-详细技术设计.md` R-04/R-10 口径、`处理遗留-基线快照.md` C 节 |
| 依据 2 | `docs/处理遗留-CI-审查意见单.md`（首轮：阻断 0 / 严重 2 / 轻微 2 / 建议 2）——逐条复核清零 |

## 0. L0 实测证据（零模型判断部分）

| 项 | 操作（技能根；python312） | 结果 |
| --- | --- | --- |
| ci_all 裸命令（S1 复跑） | `python tests\v4\ci_all.py`（输出重定向捕获，无 PYTHONUTF8/-X utf8） | **rc=0**：逐套 43/15/11/8/12/17/49 全 rc=0；compile py=16 bad=0；doc-consistency ok=True 且 ⊆ 行正常打印（无 UnicodeEncodeError）；`TOTAL pass=155 fail=0`；`RESULT CI ALL_GREEN` |
| 负向脚本裸命令（S2 复跑） | `python tests\v4\ci_negcheck_doc_consistency.py`（无 PYTHONUTF8/-X utf8，管道/重定向捕获） | **rc=1**：逻辑跑完判 NEG OK 后，L60 `print(details)`（details[0] 含 U+2286 ⊆）抛 `UnicodeEncodeError: 'gbk' codec can't encode '\u2286'` → traceback，rc=1（两次独立复现一致） |
| 负向脚本对照 | 同命令加 `-X utf8` | rc=0：`NEG OK: 反向检出缺失 -> ok=False 且 rev_missing=['--ignore-gpu-lib']` |
| S2 变异探针（闭环证明） | 驱动脚本导入真 ci_all vs 变异副本（`missing_rev = public - args_in_skill` → `missing_rev = set()`），同一临时树跑负向判据逻辑 | 真模块：负向判定 rc=0（ok=False、rev_hit=True、rev_missing=['--ignore-gpu-lib']）；变异模块：rc=1（ok=True、rev_hit=False）→ **CLOSURE-OK：反向行损坏 ⇒ 负向必 FAIL，绑定成立** |
| SKILL/实物旗标对账 | 正控真实 SKILL CLI 行 9 旗标、argparse 13 旗标（−4 兼容内部=9） | 双向 empty 成立；负控删 `[--ignore-gpu-lib]` 后仅 rev_missing=['--ignore-gpu-lib']（与 CI 文档 §2 一致） |
| CI 文档路径引用 | 子串核对 | 引用 `tests\v4\ci_all.py`（正确）、`ci_negcheck_doc_consistency.py`；全文无 `assets\v4\ci_all.py` → A2 备忘笔误属实且无文件缺陷 |
| 冒烟临时产物 | `%TEMP%\pdfv3_smoke10` 存在性 | 仍存在（清理属 Step 9 收口职责，文档已声明）→ A1 措辞收口成立 |

## 1. 首轮六项清零复核（逐条）

| 首轮项 | 结论 | anchor / basis / confidence |
| --- | --- | --- |
| S1 严重（stdout 编码未钉死） | **已清零** | anchor：`tests/v4/ci_all.py` main() L77-82（stdout+stderr reconfigure utf-8，errors="replace"，try/except 包裹，置于任何 print 前）。basis：裸命令重定向复跑 rc=0、ALL_GREEN、⊆ 行完整打印（首轮同一形态 rc=1 崩溃已消除）。confidence：高（实跑证据）。 |
| S2 严重（负向自检空转） | **逻辑已清零**（见 §2 新严重 S-复审-1：同文件仍带 S1 类编码缺陷） | anchor：`tests/v4/ci_negcheck_doc_consistency.py` ① 正控 L35-43（真实 SKILL + `_copy_v4_tree` 全量模块 → ok=True）；② 负控 L44-59（SKILL 删 `[--ignore-gpu-lib]` + 全量模块 → ok=False 且 rev_hit 断言 details[0] 含 rev_missing=['--ignore-gpu-lib']）；L55 rev_hit 判定绑定 details，非仅 ok。basis：ok2 不再恒 False（全量模块拷入），ok 判据与反向检出解耦消除；变异探针实证 reverse 行损坏 ⇒ NEG FAIL rc=1。confidence：高（代码直读 + 双模块变异 A/B）。 |
| L1 轻微（§2"同构覆盖"论证性表述） | **已清零** | anchor：`docs/处理遗留-CI.md` §2 末句（L19）。basis：现文改口径为"找不到 CLI 行分支…代码显式返回 (False, 缺行说明)（非空转恒真）——为代码常量路径，Step 9 直读核对；负向脚本覆盖的是'反向删旗标'数据路径回归"，不再宣称负向脚本覆盖 None 分支。confidence：高（直读措辞）。 |
| L2 轻微（头注释页型不符） | **锚点已清零；同簇残留 1 处行内注释**（见 §3 L-复审-1） | anchor：`tests/v4/test_orchestrator_pdf.py` L7（现为"① 合成微型 PDF（3 页文字层）…"并标注 L2 收口）；实跑 L97 `pages=("text","text","text")`。confidence：高（行级核对）。 |
| A1 建议（冒烟产物清理策略未声明） | **已清零** | anchor：`docs/处理遗留-CI.md` §4 L33。basis：现文声明"复验临时产物 %TEMP%\pdfv3_smoke10\（非仓库内、不含密钥）在 Step 9 收口时清理，本文档保留结论行（A1 收口）"。confidence：高（直读措辞 + 目录实测）。 |
| A2 建议（委托清单路径笔误） | **已清零（备忘级，无需文件改动）** | anchor：CI 文档引用核对。basis：文档引用 `tests\v4\ci_all.py` 正确，无 `assets\v4\ci_all.py`；A2 为委托侧备忘笔误，非文档缺陷，本轮无需任何修改。confidence：高（子串核对）。 |

## 2. 严重级（新 1 项）

### S-复审-1（严重）负向脚本成功路径打印 ⊆ 未钉死 → CI 文档 §2 文档化"NEG OK rc=0"在裸命令/重定向形态不可复现（S1 同类假红，落点在被 S2 改写的文件内）
- **anchor**：`tests/v4/ci_negcheck_doc_consistency.py` L60（`print("NEG OK: …details=%s" % details)`，details[0] 含 U+2286 "⊆"）；全文件 L29-61 无 stdout/stderr reconfigure（对照 `ci_all.py` L77-82、`test_orchestrator_pdf.py` L88-92 既有范式）；`docs/处理遗留-CI.md` §2 L18 命令行无 UTF-8 前提、宣称"→ NEG OK（…）rc=0"。
- **basis**：任务给定复跑命令（裸命令、无 PYTHONUTF8）在本机管道/重定向捕获形态（Step 9 CD 头less 复跑与证据留档形态，首轮 S1 同款判据）实跑两次：逻辑判得 NEG OK 后，print 含 ⊆ 的 details 时抛 `UnicodeEncodeError: 'gbk' codec can't encode '\u2286'`，rc=1，NEG OK 行未及打印——文档化结果不可复现（假红）；`-X utf8` 对照 rc=0 NEG OK 且含 rev_missing=['--ignore-gpu-lib']，证明内容真值无错、纯输出编码层缺陷。即：S1 在 ci_all 内被修复，但其 S2 修复改写的姊妹脚本 ci_negcheck 未同步该修复，把同一类假红带进了负向自检证据链。逻辑判定本身经变异探针证实绑定（§0），故不影响 S2 绑定结论，但"防假绿灯"脚本自身在其文档化复跑下假红，Step 9 无法按文档复现负向证据。
- **confidence**：高（两次独立实跑复现 + 对照实验 + 行级定位）。
- **修复建议（供修复方，仅报告不代改）**：① 在 `ci_negcheck_doc_consistency.py` main() 入口加 `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`（与 ci_all/test_orchestrator_pdf 同款，一行级）；或 ② CI 文档 §2 命令改 `python -X utf8 …` 并明示 UTF-8 前提。择一后按裸命令复跑 rc=0（NEG OK + rev_missing 行）再送复核查验。当前内容真值（双向 empty、正负控、绑定）无需改动。

## 3. 轻微级（新 1 项）

### L-复审-1（轻微）test_orchestrator_pdf.py 行内注释 L96 仍称 ① "文字层+含图"，与 ① 实跑 3 页纯文字不符（L2 同簇残留）
- **anchor**：`tests/v4/test_orchestrator_pdf.py` L96（`# ① 端到端文字层+含图（文字层走 textlayer；含图页由 textlayer intra 或 text 承载）`）紧邻 L97 实跑 `pages=("text","text","text")`。
- **basis**：① CLI 端到端为 3 页纯文字层（首轮 L2 已认定），含图承载断言实际由 ①-b（payload 层 L111-132）与 ⑤/R-06（scan.pdf / scan_img 各 `("image",)` 页，L205/L379-389）承担；L96 注释描述的画面在 ① 处不存在，属 L2 修复（仅动 L7 头注释）遗漏的同簇陈旧注释，易误导维护者。功能与 CI 无影响。
- **confidence**：高（行级核对 + 全文件 make_pdf 调用点枚举）。
- **修复建议**：L96 行内注释与 L7 头注释同口径（去掉"含图/含图页"表述，或注明含图覆盖在 ①-b/⑤/R-06）。

## 4. 建议级（0）

首轮 A1/A2 均已清零，无新增建议项。

## 5. 放行判定

- 分级统计（本轮）：**阻断 0 / 严重 1（新 S-复审-1）/ 轻微 1（新 L-复审-1）/ 建议 0**。
- 首轮六项清零复核：S1 ✓ / S2 逻辑 ✓（其文件暴露 S-复审-1）/ L1 ✓ / L2 头注释 ✓（L96 残留 L-复审-1）/ A1 ✓ / A2 ✓。
- **判定：暂不放行**（阻断清零 ✓，但严重未清零：S-复审-1）。进 Step 9 前需清零 S-复审-1（负向脚本编码钉死或文档命令加 UTF-8 前提，一行级），修复后按裸命令复跑 `rc=0` + NEG OK 行（含 rev_missing=['--ignore-gpu-lib']）再复核；L-复审-1 为注释级，可随严重项一并收口，不单独阻塞。
- 未清零项 anchor 摘要：S-复审-1 = `ci_negcheck_doc_consistency.py` L60 print(details)（⊆ 于 GBK 输出崩溃）+ 全文件缺 reconfigure + `处理遗留-CI.md` §2 L18 文档化命令无 UTF-8 前提；L-复审-1 = `test_orchestrator_pdf.py` L96 行内注释与 ① 实跑页型不符。

---
（本复审意见单为仅报告输出，未修改任何被审文件；本轮未阅读本目录其它审查/复审意见单，仅用依据 2 指定首轮单。）
