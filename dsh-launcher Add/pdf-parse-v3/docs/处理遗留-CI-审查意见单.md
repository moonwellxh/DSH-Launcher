# 处理遗留：CI（Step 8）——独立对抗审查意见单（仅报告模式）

| 字段 | 内容 |
| --- | --- |
| 审查对象 | `docs/处理遗留-CI.md`（Step 8 CI 汇总）+ 其引用的门证据实物（代码/测试/冒烟产物/上游口径） |
| 审查模式 | 独立子审查者 · 对抗性分级审查 · 仅报告（不改文件） |
| 日期 | 2026-09-09 |
| 复核方法 | 一键运行器与负向脚本实跑（python312，技能根）；冒烟产物逐字段直读；代码实物直读；变异实验（负向空转验证）；上游口径对账（详细技术设计 §2/§4/§8、WBS N3.2/N0、基线快照 A/B/C） |

## 0. 实测证据（L0 确定性复核记录，零模型判断部分）

| 项 | 复核命令/操作 | 结果 |
| --- | --- | --- |
| 一键运行器（文档原命令，无额外环境变量） | `python tests\v4\ci_all.py`（技能根，输出经管道捕获） | **rc=1**：套件全过（ms1 43/ms2 15/ms3 11/ms5 8/triage 12/render 17/orch 49，合计 155/0；compile py=16 bad=0），但运行器自身打印 doc-consistency 细节行时抛 `UnicodeEncodeError: 'gbk' codec can't encode '\u2286'(⊆)` → 未打印 TOTAL/RESULT 即崩溃 |
| 一键运行器（UTF-8 环境） | `PYTHONUTF8=1 python tests\v4\ci_all.py` | rc=0：TOTAL pass=155 fail=0；compile py=16 bad=0；doc-consistency ok=True，skill 9 旗标 ⊆ argparse 13 旗标，fwd_missing=[] rev_missing=[]，mods missing=[]；RESULT CI ALL_GREEN |
| 负向自检 | `python tests\v4\ci_negcheck_doc_consistency.py` | NEG OK rc=0；details 显示 rev_missing=['--ignore-gpu-lib']（与文档 §2 声称一致） |
| 负向空转变异（实证） | 将 ci_all 反向行变异为恒空再跑负向流程（合成树原样） | ok 仍 =False → 负向仍 NEG OK rc=0（**反向失效未被检出**） |
| 负向对照变异 | 同上变异 + 合成树补全 assets/v4 模块文件 | ok=True（反向删除可被检出——证明空转根因=合成树缺模块致 ok2 恒 False） |
| 冒烟产物 | `%TEMP%\pdfv3_smoke10\glm\page_0010.json`（5337B）+ `ledger\token.jsonl`（268B） | 存在；http_status=200、response 含 data_info/layout_details/md_results/model=glm-ocr/usage、usage_extracted prompt=3571 completion=816；md_results 长 1376 字符；全文无 degrade/partial/failed/fallback/quality 等关键字；ledger 单条：cost_cny=0.000877、cache_hit=false、page=10、channel=glm（与文档行 `[ok] page 10 … cost=0.000877 md_chars=1376` 逐项吻合） |
| V-3 样件来源 | samples.json（UTF-8 读）+ 技能树 *.pdf 扫描 | note 注明"GBJ16-87 第1册扫描渲染页（1860×2714 PNG）"；page_0010.png 存在于 batch_samples（715883B）；**技能内 0 个 .pdf**（源 PDF 未捆绑属实） |
| 密钥路径 | vision_client.py + keys.json 存在性 | USER_KEY_FILE 仅 line76 `read_text`，无任何 write_text/open("w") 指向它（"未写回"属实）；`%USERPROFILE%\.config\pdf-parse-v3\keys.json` 存在 |
| 断言计数对账 | 代码逐条计数 + 算术 | triage 12 / render 17 / orch 49 与代码内 check 条数逐一相符；155=43+15+11+8+12+17+49；155−114=41=6+4−1+7+25（ms2/ms3/triage/render/orch），与基线快照 C 节及设计 §4"预估 +40~60"区间一致 |

---

## 1. 阻断级（0）

无。

## 2. 严重级（2）

### S1（严重）一键运行器 stdout 编码未钉死 → 文档化"复跑命令 rc=0"在本机默认环境不可复现（假红 + 可复现性缺陷）
- **anchor**：`tests/v4/ci_all.py` main()（约 L99-100，print doc-consistency 细节含 U+2286"⊆"；无 stdout 编码钉死）；`docs/处理遗留-CI.md` §1（宣称裸命令 rc=0 ALL_GREEN，未声明 UTF-8 前提）。
- **basis**：按文档原命令实跑一次：全部套件与 compile 通过后，打印 doc-consistency 行崩于 `UnicodeEncodeError: 'gbk' codec can't encode '\u2286'`（输出经管道捕获时 Python 采用 locale cp936），**rc=1，TOTAL/RESULT 两行未及打印**；同命令加 `PYTHONUTF8=1` 后完整复现 rc=0 全绿（155/0、16、双向 empty）。即：内容断言全部为真，但"一键复跑 rc=0"仅在 UTF-8 输出环境成立；中文 Windows 默认 GBK 控制台/重定向（正是 Step 9 CD 头less 复跑与证据留档形态）下必现假红。同库 `tests/v4/test_orchestrator_pdf.py` L90-94 已示范 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` 模式，本运行器未采用（与技能树 charset 铁律冲突）。
- **confidence**：高（双环境实跑复现）。
- **修复建议（供修复方）**：main() 入口对 sys.stdout/sys.stderr reconfigure utf-8（一行）；或文档命令改为 `python -X utf8 tests\v4\ci_all.py` 并在 §1 明示 UTF-8 前提。两者择一后按原命令复跑 rc=0 再复核。

### S2（严重）负向自检空转：doc-consistency 反向"删除旗标被检出"并非该脚本判据的真实来源（防假绿灯闭环缺口）
- **anchor**：`tests/v4/ci_negcheck_doc_consistency.py`（合成树仅放 SKILL.md + orchestrator.py，缺其余 15 个模块文件）；`tests/v4/ci_all.py` check_doc_consistency()（ok = ok1(旗标双向) and ok2(模块清单)）；`docs/处理遗留-CI.md` §2（"负向自检（防假绿灯）…NEG OK"）与 §3 表（"负向脚本负路径"）。
- **basis**：合成树中 `files_exist` 仅 {orchestrator} → ok2（模块清单）恒 False → **ok 恒 False → 脚本 rc=0 与 ok1（反向检出）完全解耦**。变异实验证实：将 ci_all 反向行替换为恒空（模拟反向失效回归），在负向脚本原样合成树上跑 check_doc_consistency → ok 仍 False → 负向仍报 NEG OK rc=0（**未检出**）；仅当合成树补全模块文件（ok2 归真）后，同一变异才使 ok=True 被检出。即该负向脚本在其声称的目标场景（反向逻辑被删）上**结构性无法失败**，details 里出现的 rev_missing=['--ignore-gpu-lib'] 只是展示正确，判据本身空转。当前反向代码正确（真树上 ci_all 双向 empty、对照变异可检出），故本项不构成现行绿/红误判，但"防假绿灯"对反向方向的回归保护实际不存在，文档对其覆盖能力的宣称过度。
- **confidence**：高（代码推演 + 双变异实验实证）。
- **修复建议（供修复方）**：负向脚本改为断言 details 内容（如 rev_missing == ['--ignore-gpu-lib'] 才 NEG OK，反向删除 → rev_missing 空 → NEG FAIL rc=1）；或合成树复制真实 assets/v4 模块使 ok2=True 后以 ok 判据；或抽出纯旗标集对账函数供负向直测。任一方案后补跑变异（反向行删掉应 NEG FAIL）再复核。

## 3. 轻微级（2）

### L1（轻微）CI 文档 §2"找不到 CLI 行分支由负向脚本同构覆盖"为论证性表述，非实际覆盖
- **anchor**：`docs/处理遗留-CI.md` §2 末句；`tests/v4/ci_negcheck_doc_consistency.py`（仅覆盖"删旗标"形态）；`tests/v4/ci_all.py` L51-52（cli_line None 分支）。
- **basis**：该分支（SKILL.md 缺 `orchestrator.py <pdf>` 行 → return (False, 缺行说明)）经代码审读成立、且 ci_all 主流程 doc_ok 会转红，风险面小；但负向脚本只构造"删旗标"场景，未直接执行 None 分支；"同构覆盖"是形态相似论证而非自动化覆盖。叠加 S2 空转，该句连"负向脚本本身可失败"的前提也不成立，语句应改口径。
- **confidence**：高（代码路径确定；覆盖性判定为论证性质）。
- **修复建议**：随 S2 修复补一条"整行删除 CLI 示例行"负向用例直接走 None 分支，或将该句改为"代码路径审读成立 + 负向机制同构论证"，不再称覆盖。

### L2（轻微）test_orchestrator_pdf.py 头注释与实物用例页型不符（陈旧注释，易误导维护者）
- **anchor**：`tests/v4/test_orchestrator_pdf.py` L7（① 描述"2 页文字层 + 1 页内嵌位图"）；L99（实际 `pages=("text","text","text")`）。
- **basis**：① 实物为 3 页纯文字层 mini.pdf，含图断言由 ①-b（pipeline payload）与 R-06 承担；头注释仍写旧页型。与 CI 文档无冲突（CI 文档 §4 表述正确），仅测试文件自述过时。
- **confidence**：高（行级核对）。
- **修复建议**：同步头注释与实物页型，或保留默认参数说明。

## 4. 建议级（2）

### A1（建议）冒烟产物留存策略未声明
- **anchor**：`docs/处理遗留-CI.md` §4（`--out <tmp>` 产物路径）。
- **basis**：`%TEMP%\pdfv3_smoke10\`（5337B+268B）经核无密钥、无敏感字段（仅规范正文 OCR + cost 台账），位于 %TEMP% 非仓库内，无泄露/污染路径；但 Step 9 收口未声明清理或留存策略，长留会堆积出域内容于临时目录。
- **confidence**：高（已逐文件核内容）。
- **建议**：Step 9 收口明确清理该临时目录或声明留存期限。

### A2（建议）审查委托描述与实物路径有一处不符（非 CI 文档缺陷）
- **anchor**：委托清单列 `assets\v4\ci_all.py`；实物为 `tests\v4\ci_all.py`（assets/v4 无 ci_all.py）。
- **basis**：CI 文档自身引用路径正确（tests\v4），仅委托方代码实物清单笔误；不影响结论，备忘防后续复用错路径。
- **confidence**：高。

## 5. 放行判定

- 分级统计：**阻断 0 / 严重 2 / 轻微 2 / 建议 2**。
- **判定：暂不放行**（阻断清零 ✓，但严重未清零：S1、S2）。
- S1、S2 均为 ≤1 行级/断言级小修（编码钉死 + 负向判据改 details 断言或补模块），且两处均不影响当前内容真值（155/0、compile16、双向 empty、NEG 细节展示、V-3 诚实性均已实证为真）；清零后按修复建议复跑（含变异复核：反向行删除须 NEG FAIL）即可满足"阻断清零 ∧ 严重清零"进 Step 9。
- 已核验为真、无需改动的关键门证据：155 断言逐套分计数与算术、41 增量落在步 5 §4 预估、doc-consistency 双向 empty 与 9/13(−4) 旗标集口径、pass>0 守卫存在、唯一 [SKIP-POSIX] 不计断言、无 or 放宽三项（schema/method/dpi<default 单判据）、幂等 ④ byte 一致、⑧ 构造计数、V-3 诚实声明（扫描=真实规范渲染页+真出域、文字=合成 mini 整本、源 PDF 未捆绑、密钥只读、冒烟 1 页 ¥0.0009）与基线快照 A/B/C、设计 §4/§8、WBS N3.2 口径全部吻合。

---
（本意见单为仅报告输出，未修改任何被审文件。）
