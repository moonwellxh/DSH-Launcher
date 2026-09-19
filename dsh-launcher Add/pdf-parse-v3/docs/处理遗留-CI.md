# 处理遗留：CI（Step 8 汇总）

| 字段 | 内容 |
| --- | --- |
| 文档 | pdf-parse-v3 就地升级（Step 8 CI，九步流程·第二轮） |
| 日期 | 2026-09-09 |
| 上游 | Step 7 编码（N0..N5 完成，节点执行记录见 `处理遗留-节点执行记录.md`）；WBS《处理遗留-WBS.md》 |
| 定位 | ★ 门证据汇总：一键运行器结果 + 防假绿灯负向 + 真实样件复验 + 诚实声明；阻断/严重清零后进 Step 9 |

## 1. 一键运行器（复跑命令，零网络）
- 命令（技能根）：`C:\Users\<用户名>\AppData\Local\Programs\Python\Python312\python.exe tests\v4\ci_all.py`
- 结果（2026-09-09）：**TOTAL pass=155 fail=0，RESULT CI ALL_GREEN（rc=0）**；compile py=16 bad=0；doc-consistency ok=True。
- 逐套：test_ms1_smoke 43 / test_ms2_replay 15 / test_ms3_ladder 11 / test_ms5_acceptance 8 / test_triage 12 / test_render 17 / test_orchestrator_pdf 49（fail 均 0）。
- 断言增长对账：155 − 114（基线）= **41**（落在步 5 预估 +40~60）；文件级核对入 `处理遗留-基线快照.md` C 节。

## 2. doc-consistency（R-04/R-10 双向）
- 输出：`fwd_missing=[] rev_missing=[]`（9 公开旗标 ⊆ argparse ∧ argparse 公开旗标 −4 兼容内部 ⊆ SKILL；位置参数 `<pdf>` 不参与旗标集合差——口径注）。
- 负向自检（防假绿灯，不入主绿）：`python tests\v4\ci_negcheck_doc_consistency.py` → **NEG OK（全量模块正控 ok=True；合成 SKILL 删 --ignore-gpu-lib → ok=False 且 details[0] 含 rev_missing=['--ignore-gpu-lib']），rc=0**——负向判定与反向缺失绑定（Step 8 复审 S2 修复）。
- 找不到 CLI 行分支：代码显式返回 (False, 缺行说明)（非空转恒真）——为代码常量路径，Step 9 直读核对；负向脚本覆盖的是"反向删旗标"数据路径回归（口径注，L1 收口）。

## 3. 防假绿灯自检清单（逐项）
| 项 | 证据 |
| --- | --- |
| pass>0 守卫 | ci_all all_green 含 total_pass>0（155>0 生效；删除即红路径在代码） |
| 无空转 skip | 唯一显式 [SKIP-POSIX] 打印（不计断言，Windows 平台边界）；triage 零页旧 skip 分支已换 pypdf 真夹具 |
| 无 or 放宽 | ① schema 单判据、⑤ method 单值、R-02 dpi<default 唯一判据（均单断言） |
| 夹具真可失败 | render ⑥'前置（单档220 oversize）+⑦可达性前置；负向脚本负路径 |
| 幂等/断点 | ④ 幂等两跑 byte 一致；⑧ 幂等路径 + client 计数==1 |

## 4. 真实样件复验（V-3；诚实声明来源）
- **扫描样件（真实规范渲染页 + GLM 出域）**：`orchestrator.py --page-image tests\vision_shootout\batch_samples\page_0010.png --page 10 --out <tmp>` → exit0；`[ok] page 10 cache_hit=False cost=0.000877 md_chars=1376`；产物 `glm/page_0010.json`（5337B）+ `ledger/token.jsonl`（268B，含 cost_cny）。样件来源：GBJ16-87 第 1 册扫描渲染页 PNG（tests/vision_shootout/samples/samples.json 注明；源 PDF 未随技能捆绑）。
- **文字层整本（离线端到端）**：合成 mini.pdf 3 页文字层整本端到端在 test_orchestrator_pdf ①/④ 覆盖（exit0、schema 4.0、页数=3、幂等 byte 一致）——技能内无真实文字层 PDF 样件，如实声明以合成整本+真实渲染页两种口径覆盖，未冒充"真实规范 PDF 全本"。
- GLM 出域密钥走 `%USERPROFILE%\.config\pdf-parse-v3\keys.json`（只读，zhipu 通道），未写回。复验临时产物 `%TEMP%\pdfv3_smoke10\`（非仓库内、不含密钥）在 Step 9 收口时清理，本文档保留结论行（A1 收口）。

## 5. 诚实声明
- 真实 GLM 冒烟仅 1 页（成本 ¥0.0009，避免长任务预算）；复验非回归门（网络出域，CI 主绿不含）。
- 无真实 PDF 文件在技能内：扫描侧以真实规范渲染页 PNG 出域、文字侧以合成整本离线覆盖；未重开"批量重转 D:\W"等非目标。
- POSIX 真实 TTY 端到端仍未在本机实测（平台边界显式声明，行为由函数级+子进程覆盖）。

## 6. 门判定
证据汇总如上。送 ★ 独立审查，阻断/严重清零后进 Step 9 CD。
