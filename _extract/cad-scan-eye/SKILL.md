---
name: cad-scan-eye
description: |
  CAD扫描之眼：多手段自动调度读取与理解 DWG 图纸内容 + DWG 图纸自动修复。四路提取互补并用（A COM 在线提取文字/块属性/标注/表格/引线，带图层/坐标/字高/handle；B LibreDWG 离线结构化；C 双通道二进制扫描兜底；D 转 T3 后读），自动检测天正等代理实体并静默转 T3（原名_AiT3.dwg 原子写 + mtime/size/快哈希三重增量判定），XREF 检测报告（可选递归），结果按内容归并保留 occurrences、按 source 溯源，输出 LLM 友好 JSON 并支持 --summary/--filter/--bbox/--handle 投影。DWG 修复：多级修复链（AUDIT/PURGE/字典清理/RECOVER/字体/外部参照），输出 原名_fix.dwg 不覆盖源文件，支持「仅修复」「修复+转T3」「修复+提取」三种模式。AutoCAD 未运行时提醒用户打开，不自行启动。
  触发词：「读取/提取/扫描 CAD 图纸」「DWG 文字提取」「图纸提资提取」「设备/电气/暖通提资」「天正图纸读取」「图纸内容核对/清单比对」「CAD扫描之眼」「提取图面文字」「从打开的 AutoCAD 读取」「机房/设备参数提取」「修复 DWG」「CAD 图纸修复」「DWG 文件修复」「修复损坏图纸」「CAD 修复」「修复后转 T3」「修复并提取」。
---

# CAD 扫描之眼（cad-scan-eye）

大模型理解 DWG 的「眼睛」：解析 → 整合 → 按需投影。一句话：**多手段自动调度 + 代理实体检测转 T3 + 归并整合为 LLM 友好结构**。

## 适用场景

设备专业提资提取（电气/暖通/给排水）、图纸内容核对、清单与图纸比对、机房设备参数抓取、图面文字批量提取、天正图纸文字读取、**DWG 图纸损坏修复（多级修复链）**。

---

## 前置检查（第一步，必做）

0. **CAD 系统变量崩溃兜底自检**：orchestrator 启动时自动检测上次提取是否崩溃/卡死残留系统变量快照（`FILEDIA/CMDDIA` 停在 0 会导致 Ctrl+O 等不弹对话框）。发现残留时打印告警与恢复命令；恢复方法：先打开 AutoCAD，然后运行 `python "<本目录>/extract.py" --restore-guards` 或 `python "<本目录>/tz3_convert.py" --restore-guards`。
1. **AutoCAD 是否运行**：A 路（COM）与转 T3 依赖运行中的 AutoCAD。
   ```python
   import comtypes.client
   app = comtypes.client.GetActiveObject("AutoCAD.Application", dynamic=True)  # 失败=未运行
   ```
2. **AutoCAD 未运行时**：
   - 只需离线提取（B/C 路）→ 直接 `orchestrator.py <dwg路径>`；
   - 需要转 T3 → orchestrator 会**自动启动 AutoCAD、打开图纸、发 TZ3 命令、轮询产物**（见 `tz3_convert.py`），无需手动操作；用 `--no-auto-t3` 可禁用自动转。
3. **AutoCAD 已运行但目标图未打开**：A 路会跳过并标注错误（按设计不自行打开文件，除非走自动转 T3）。

## 环境（已装好，勿重复安装）

| 组件 | 路径 | 用途 |
|------|------|------|
| Python（本机无 venv，用 WorkBuddy 自带解释器） | `C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe` | 全部脚本运行环境（comtypes/ezdxf/pyautocad/numpy/pywin32 已装） |
| LibreDWG 0.14 | 探测 `~/.workbuddy/bin/libredwg/`（dwgread/dwg2dxf，本机已装） | B 路离线解析 + 代理实体离线检测 |
| TZ3 插件 dll | 本目录 `TZ3Converter.fx48.dll` / `.net8.dll` | 静默转 T3（注册方式见「系统级改动清单」） |
| 天正环境 | AutoCAD 内已装天正（tch_kernal.arx） | T3 转换前提（SaveAsTArch3 动态解析，跨天正版本） |

## 决策树（模型可执行版）

```
输入 DWG（路径或文档名关键词）
 0. 修复模式（--repair/--repair-t3/--repair-extract/--rebuild）：
    ├─ --repair → dwg_repair.repair() → 原地修复链 → 输出 原名_fix.dwg
    │             → 修复后自动验证（WBLOCK 全图导出试存）
    │             → 仍报错则自动降级 XREF 重建（最终方案）
    ├─ --rebuild → 跳过原地修复，直接 XREF 重建
    ├─ --repair-t3 → 修复 → 转 T3（原名_fix_AiT3.dwg）→ 结束
    └─ --repair-extract → 修复 → 提取 原名_fix.dwg → 输出 JSON
    【何时用最终方案（XREF 重建）】原地修复后 WBLOCK 验证仍触发
    「保存时出错」→ 损坏在数据库深层（多为天正代理对象/逻辑错误）→
    新建空白图 → 源图作 XREF 插入 → bind 绑定 → 另存。纯 COM 同步，
    完成判定靠块表 IsXRef 状态（不读 CMDACTIVE）。
 1. 文件健康检查：不存在/空/不可读 → 结构化报错
 2. 代理实体检测（离线轨 dwgread 数实例；CAD 运行时叠加在线轨 COM 枚举）
    ├─ 天正代理（verdict=convert_t3）
    │   ├─ 存在有效 _AiT3（mtime+size+快哈希 sidecar 三重全一致）→ 读 _AiT3
    │   └─ 否则需转 T3：
    │       ├─ CAD 未运行 → 提示打开 CAD + 图纸；离线 B/C 路兜底继续
    │       └─ CAD 运行 → 引导：已装插件输 TZ3；未装插件运行
    │           python tz3_install.py --register（需重启 CAD 生效），
    │           或当次免重启 APPLOAD tz3_register.lsp → REGDLL / 直接 NETLOAD
    ├─ 非天正代理（verdict=report_only）→ 不转，proxy_report 警告「相关文字可能缺失」
    └─ 无代理 → 直接提取
 3. XREF：默认输出 xrefs[] 清单（Attach/Overlay/丢失状态）；--xref 递归（深度≤3、防循环、Overlay 跳过）
 4. 提取（读取对象三元判断：有效 _AiT3 → 读 _AiT3；否则读源文件）
    ├─ CAD 运行且图已打开 → A 路 COM（弹窗防护+5min 看门狗；默认快模式，--full 全量）
    ├─ B 路 LibreDWG+ezdxf 离线（恒跑）
    └─ C 路双通道二进制扫描（AC1021+ 加 UTF-16LE 通道；恒跑，天正文字兜底）
 5. 归并：同内容合并保留 occurrences[]；source 优先级 A>D>B>C
 6. 输出统一 JSON + 投影（--summary/--filter/--bbox/--handle）
```

## 用法

```bash
PY="C:/Users/雍远/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 总调度（推荐）：决策树 + 四路提取 + 归并 + 输出
$PY "<本目录>/orchestrator.py" "D:/xx.dwg"                          # 默认
$PY "<本目录>/orchestrator.py" "提资"                                # 文档名关键词（需 CAD 运行）
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --full                   # A 路全量（标注/表格）
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --xref                    # 递归解析参照
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --summary                 # 投影：图层×类型矩阵
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --filter "消防" --layers 暖通-风管
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --bbox 0,0,50000,50000
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --handle 3A7F

# 修复模式（2026-08-18 新增）
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --repair          # 仅修复，输出 _fix.dwg
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --repair-t3       # 修复 + 转 T3
$PY "<本目录>/orchestrator.py" "D:/xx.dwg" --repair-extract  # 修复 + 提取

# 单路直调（按需）
$PY "<本目录>/extract.py" "关键词"           # A 路：COM（CAD 运行中）
$PY "<本目录>/scan_dwg_structured.py" --file "D:/xx.dwg"   # B 路：离线结构化
$PY "<本目录>/scan_dwg_text.py" --file "D:/xx.dwg"         # C 路：二进制扫描
$PY "<本目录>/proxy_detect.py" "D:/xx.dwg"                 # 代理实体检测
$PY "<本目录>/tz3_install.py" --register / --unregister / --status   # T3 插件注册
```

各脚本均支持 `--out <目录>` 指定输出目录；未指定时先试图纸同目录，可写性探测失败自动降级系统临时目录（**禁止硬编码任何用户目录**）。

## 输出 JSON Schema（核心字段）

```json
{
  "dwg": "电气提资.dwg",
  "mode": "texts",
  "filter_criteria": "type in [TEXT,MTEXT,...] and content non-empty",
  "elapsed_sec": 19,
  "texts": [
    {"content": "梁下净高4.5m", "type": "单行", "source": "A",
     "occurrences": [{"x": 123.4, "y": 567.8, "layer": "F-COM-TEXT",
                      "handle": "3A7F"}],
     "height": 350.0, "plot_height": 3.5,
     "layer_state": "on", "space": "model",
     "block_name": null, "is_field": false}
  ],
  "dims":   [{"measurement": 3600.0, "text_override": "3600（复核）",
              "is_overridden": true, "source": "A", "handle": "41B2"}],
  "attrs":  [{"tag": "编号", "value": "M1025", "source": "A"}],
  "tables": [{"table_no": 1, "cells": [{"row": 1, "col": 1, "value": "..."}]}],
  "xrefs":  [{"name": "AXIS", "path": "..\\底图\\轴网.dwg", "type": "attach",
              "status": "loaded"}],
  "proxy_report": {"verdict": "convert_t3|report_only|none",
                   "proxy_count": 256, "is_tianzheng": true, "classes": []},
  "errors": []
}
```

**字段约定（LLM 解读要点）**：
1. `occurrences`：同内容文字合并为一条但保留全部位置——同内容在不同位置承载不同语义（如同一梁编号标注在不同跨）；回图定位按 occurrence 展开；
2. `handle`：DWG 实体句柄，图内唯一、跨次提取稳定，人工回图复核靠它对齐；
3. `dims` 双层值：`measurement`（真实测量值）为准，`text_override` 是人为改写文本，`is_overridden` 标志——**默认信 measurement**；
4. `source`：A(COM)>D(T3后读)>B(LibreDWG)>C(二进制) 溯源；
5. `layer_state`：frozen/off 图层上的文字带标志（可能是草稿或有意隐藏）；
6. `space`：model 或 layout:名——遍历模型空间+全部布局；
7. `block_name`/`block_insert`/`block_scale`/`block_rotation`：块内文字已变换为世界坐标，块信息留作溯源；
8. `errors[]`：任何一路失败/降级都会记录，**从不静默**。

## 系统级改动清单（本 skill 会做的全部系统改动）

| 改动 | 位置 | 回滚方法 |
|------|------|----------|
| 注册表 `Applications\TZ3Converter`（DESCRIPTION/LOADER/LOADCTRLS=2/MANAGED=1） | `HKCU\Software\Autodesk\AutoCAD\R2x.x\<产品键>\Applications\`（全版本键全写） | `python tz3_install.py --unregister` |
| `TRUSTEDPATHS` 追加本 skill 目录 | 同上注册表 `<产品键>\Profiles\<<Unnamed Profile>>\Variables` | 注销时按日志自动回滚（改动前后值记录在 tz3_install.log.json） |
| dll 落盘 | 本 skill 目录（不动用户目录） | 删除本 skill 目录即可 |
| T3 转换产物 | 图纸同目录 `原名_AiT3.dwg` + `.meta.json` sidecar（源文件永不修改） | 删除这两个文件即可 |
| DWG 修复产物 | 图纸同目录 `原名_fix.dwg` + `.meta.json` sidecar（源文件永不修改） | 删除这两个文件即可 |

安全措施：注册前校验 dll SHA-256 与 `TZ3Converter.sha256` 清单一致，不匹配拒绝注册；TRUSTEDPATHS 只追加不覆盖；所有改动记录改动前后值。

## 关键坑（实测结论，勿再踩）

- **连接方式**：COM 只用 Python comtypes（PowerShell `New-Object -ComObject` 被安全策略拦截）；
- **弹窗防护（最小化）**：extract.py 为纯读取，**不修改任何系统变量**；tz3_convert.py 仅在 `SendCommand("TZ3")` 时临时设 `CMDDIA=0`（防命令对话框挂起），用完立即恢复。**主动兜底**：tz3_convert 设变量后启动 30s 看门狗线程，超时未恢复则强制恢复（缩小崩溃窗口期）；另写快照到 `%TEMP%/cad-scan-eye/guards_snapshot.json` 供 `--restore-guards` 一键恢复；
- **LibreDWG 对大图不可靠**：30 万对象图 dwg2dxf 输出会在 BLOCKS 段截断（skill 已做 BINARY 修复+段截断修复+errors 标注），超大图优先 A 路；
- **LibreDWG 块名编码缺陷**：模型主体内容可能被输出到乱码块名并挂 INSERT，skill 已做「被引用块经 INSERT 展开+孤儿布局块直接提取」处理；含不可变换代理实体的块 virtual_entities 会整块抛 TypeError，已降级为手动矩阵变换；
- **转 T3 命令定稿**：静默靠 `SaveAsTArch3` 直调（TZ3 插件，原子写输出 `_AiT3`）；`TSAVEAS` 弹框、`TXDC/LCJB/JTZH/PLZJ/TCHGVER` 无效、`-EXPORTTOAUTOCAD` 卡死、FILEDIA=0 无效；
- **自动转 T3**：`orchestrator.py` 默认检测到天正代理且无有效 `_AiT3` 时，自动连接/启动 CAD → 打开图 → 发 `TZ3` → 轮询产物并写 sidecar（`tz3_convert.py`）；`--no-auto-t3` 禁用；
- **proxy_detect 判据局限**：天正转 T3 后 CLASSES 段 instance_count 可能残留（不同天正版本行为不一），对 `_AiT3` 图跑 proxy_detect 可能误报 convert_t3。主流程不受影响——orchestrator 只对源图跑检测，转后走 sidecar 三重增量判定读 `_AiT3`；请勿用 proxy_detect 判断「是否已转 T3」；
- **注册表 demand-load 需重启 CAD 生效**；当次会话立即使用走 APPLOAD/NETLOAD；
- **SMB 映射盘（X/U/V/W 等）盘符只读、UNC 可写**：受限环境（agent 沙箱）对盘符路径（`X:/...`）写报 PermissionError，但其 UNC 形式（`//server/share/...`）可正常读写。skill 已内置 `path_util.py`：输出目录探测顺序为「图纸同目录 → 同目录 UNC 形式 → 系统临时目录」，盘符写不进时自动转 UNC 落盘到图纸同目录（而非降级临时目录），降级模式标注 `mode=unc`；盘符→UNC 映射读自注册表 `HKCU\Network\<盘符>\RemotePath`；
- **AutoLISP 必须 GBK**（tz3_register.lsp 已做成纯 ASCII 兼容两编码）；JSON 一律 UTF-8；
- **编号↔门窗顺序配对是启发式**（scan_tianzheng 兜底），正路是转 T3 后编号变 TEXT 精确关联；
- **修复模式**：`--repair` 原地修复+自动验证（输出 `原名_fix.dwg`）、`--rebuild` 直接 XREF 重建、`--repair-t3` 修复+转T3、`--repair-extract` 修复+提取；修复链 7 级递进（AUDIT→PURGE→SCALELISTEDIT→字典清理→RECOVER→字体→外部参照），源文件永不修改。**打开逻辑防误关**：同名文档仅当 `DBMOD=0`（无用户改动）才自动关，`DBMOD≠0` 报错请用户处理，绝不擅自关用户图纸；
- **修复链命令通道（2026-08-18 定稿，LISP 通道）**：audit/purge/scalelist/dicts/regen 一律走 `_cmd_lisp()`——把逻辑写进 `.lsp`，用 LISP `(command ...)` **同步执行**（与 env.lsp 一致），末尾 LISP 写标记文件，Python 轮询**文件出现**判定完成。**切勿用 CMDACTIVE 轮询判定完成**：SendCommand 异步执行后 CMDACTIVE 会卡住不归零（CAD 侧命令早已完成、命令行已回「命令:」，但标志未复位，用户手动 ESC 才强制归零），PeekMessage 泵不动。也勿用 `.scr`+`USERS1` 回传（LISP 表达式混入 .scr 易因转义/换行卡命令行）。`_cmd_lisp` 返回 `(ok, result)`，LISP 里对 `_RESULT` 赋值即写进标记文件回传（GBK 编码、路径用正斜杠防转义）；
- **LISP 信任路径（2026-08-19 新增）**：LISP 固定放 `lisp_tmp/`（skill 目录下，**不用临时目录**——路径变化会导致信任失效，且 SECURELOAD=1 会弹「安全-可执行文件」需手动点运行）。双保险加信任：①注册表级（tz3_install 的 `enum_acad_versions`+`append_trusted`，重启 CAD 永久生效）②内存级（COM `SetVariable("TRUSTEDPATHS",...)` 当前会话即时生效）。`_ensure_lisp_trusted()` 每次发 LISP 前自动调用；
- **COM 字典操作局限**：`doc.NamedObjectsDictionary` 动态绑定拿不到（报 "Name NamedObjectsDictionary not found"），字典探测/清理走 LISP `(namedobjdict)`+`(dictsearch)`+`(dictremove)`，结果经 `_RESULT` 回传解析；
- **SaveAs 后文档跟踪**：SaveAs 后 doc 指向 `_fix` 文件，需更新跟踪路径为 `_fix`，否则 finally 关不掉残留的 `_fix` 文档；
- **XREF 重建通道（2026-08-19 定稿，纯 COM 同步）**：`rebuild_via_xref` 全程**纯 COM 同步**，不经 LISP、**不读 CMDACTIVE**（新建文档命令泵未热时 `_wait_idle` 会卡死）。流程：`Documents.Add("acad.dwt")` 新建 → `SendCommand` attach/bind → **完成判定靠数据库实际状态**（attach 完成=块表出现源图名 XRef 块且 `IsXRef=True`；bind 完成=`IsXRef` 变 False）→ `SaveAs` 同步存。注意新建文档未保存就操作会留 `DBMOD≠0` 残留，中断需手动关。

## 文件清单

| 文件 | 职责 |
|------|------|
| `SKILL.md` | 本文件 |
| `orchestrator.py` | 总调度（决策树/多路提取/归并/投影） |
| `extract.py` | A 路 COM 提取（弹窗防护/看门狗/布局/块变换/XREF） |
| `scan_dwg_structured.py` | B 路 LibreDWG+ezdxf（BINARY 修复/段截断修复/块展开降级） |
| `scan_dwg_text.py` | C 路双通道二进制扫描（GBK+UTF-16LE/分块/三级降噪） |
| `scan_tianzheng.py` | 天正门窗「编号↔尺寸」兜底（启发式配对，带警告） |
| `proxy_detect.py` | 代理实体双轨检测（离线数实例/在线 COM 枚举） |
| `tz3_install.py` | T3 插件静默注册/注销（哈希校验/TRUSTEDPATHS 追加回滚/日志） |
| `tz3_convert.py` | 自动转 T3（连接/启动 CAD→打开图→发 TZ3→轮询产物+写 sidecar） |
| `cad_text_clean.py` | 表驱动 MTEXT 格式码清洗器（堆叠/换段/字段） |
| `merge_normalize.py` | 归并（occurrences/source 优先级/块坐标变换） |
| `query.py` | 投影接口（summary/filter/bbox/handle） |
| `path_util.py` | 路径工具（SMB 盘符→UNC 转换 + 可写目录探测 direct→unc→temp） |
| `cad_guard.py` | CAD 系统变量崩溃兜底（快照持久化/残留检测/一键恢复） |
| `dwg_repair.py` | DWG 自动修复（多级修复链：AUDIT/PURGE/字典清理/RECOVER/字体/外部参照） |
| `TZ3Converter.cs` + `.fx48.dll`/`.net8.dll` + `compile.bat` + `.sha256` | 静默转 T3 插件（双运行时产物） |
| `tz3_register.lsp` | 备用人工注册工具（REGDLL/UNREGDLL，纯 ASCII） |
| `tests/` | 单元测试与回归（详见 tests/README 说明） |

故障排查与常见问题见 `references/troubleshooting.md`。
各配套工具（Python/LibreDWG/TZ3/AutoCAD COM/天正）的**路径、AI 调用模板、踩坑**见
`references/tools-ai-usage.md`（按 skill-install-ops 规范安装后必读）。
