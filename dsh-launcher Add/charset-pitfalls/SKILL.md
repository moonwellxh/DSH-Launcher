---
name: charset-pitfalls
description: >
  中文/编码/乱码全局避坑汇总。**铁律：编写/修改任何脚本、批处理或配置文件
  （.ps1/.bat/.cmd/.sh/.json/.md/.tmpl 等，尤其可能含中文）之前，必须先载入本技能**，
  不要等出乱码再查。同时适用于中文解析、GBK/UTF-8/BOM、乱码（mojibake）、
  PowerShell/批处理中文、HTTP/RPC 中文传输、控制台代码页、中文路径报错
  （DirectoryNotFound 乱码路径）等任务；症状为"中文变 ??/�/乱码、路径找不到、
  脚本报意外标记、文件内容错乱"时也先查本技能。
---

# 中文 / 编码 / 乱码 全局避坑汇总

## 铁律：动手写文件之前，先载入本技能

**任何编写/修改脚本、批处理、配置文件的任务（.ps1 / .bat / .cmd / .sh / .json / .md /
.tmpl …），动手前第一步就是载入本技能**：对照第一节编码表确定目标文件的编码，再开始写。
**不要等出现乱码/语法错误后再回来查**。宁可多花 10 秒，不撞墙半小时。

## G0、编码守卫闸门（MANDATORY GATE —— 未过闸门不得写文件）

> 编号说明：本节是**第一个执行闸门**，编号沿用 ASCII 的 `G0`，不改动下方既有章节编号（零、一…九），以免打断全篇交叉引用。
> 本节是**执行闸门**，不是参考知识。第零～九节告诉你怎么做；本节规定**动手前必须先做、且留下可核查证据**。
> 与第三节的关系（单一事实源）：编码选路的**方法本体在第三节**；本节只规定「何时做、分几步、按什么结果选哪条路、拿什么证明做了」。冲突时以第三节方法为准。
> **设立与修订理由（真实事故，2026-09-13～14）**：某次会话**已在本技能上下文中**仍违反本技能（含中文补丁 `.ps1` 无 BOM → 中文锚点被 GBK 误读、两次"修改成功"为假；命令行内联中文路径 → `DirectoryNotFound`）。
> 首版闸门经独立子审查者实测判为**阻断 1 / 严重 5**：其"按 BOM 判两类即路由"的设计会把**本技能自己认定为合法的 GBK 无 BOM 文件**转成禁止格式或 U+FFFD 乱码（真实受害文件实测：按 UTF-8 读产生 221 个 `U+FFFD`）。故闸门重构为下面三段式。

### 三段式（探测 → 确认 → 按结果选路）

**入口脚本（本节唯一入口）**：`scripts/enc-guard.ps1`（相对本技能目录；`-Path` 传目标文件）

| 步 | 命令 | 作用 |
|---|---|---|
| **① 探测** | `scripts/enc-guard.ps1 -Action detect -Path <文件>` | 快速探测（BOM / ASCII / 强 UTF-8 / legacy）；未决的走**候选梯子**并按置信度排序给出候选。**只读** |
| **② 确认** | `scripts/enc-guard.ps1 -Action confirm -Path <文件> -Page <页> [-Old <锚点> -New <替换>]` | 写前**字节级无损校验**：整文件 round-trip 逐字节一致 + 严格解码 + 编辑前缀字节不变 + 新字符可往返 |
| **③ 选路** | `scripts/enc-guard.ps1 -Action decide -Path <文件>` | 综合①②给出决策；**exit 0 = 可按所选页写**，**exit 2 = 只报不写** |

> **设计原理（关键）**：8 位编码之间**不可判定**（同一字节串可同时是合法 GBK / Latin-1 / UTF-8；实测 `'值'` 的 GBK 字节 `D6 B5` 也是合法 UTF-8）。所以正确性**不建立在"猜得准"上，而建立在"写必须可证无损"上**：只要按**同一代码页**写回，即使该页只是"假定"，字节也不变。这把一个不可判定问题转成了可判定检查。
> 该做法与业界一致：chardet 用分阶段流水线且 **UTF-8 置信度随多字节序列占比缩放**（见 [chardet how-it-works](https://chardet.readthedocs.io/en/latest/how-it-works.html)）；ICU 返回**按置信度排序的候选**并声明"detection is at best an imprecise operation"、短样本不可靠（见 [ICU ucsdet.h](https://unicode-org.github.io/icu-docs/apidoc/dev/icu4c/ucsdet_8h.html)）；uchardet 专门提供"取全部候选及置信度"的 API。

### G1 触发判据（命中任一即必须过闸门）

- 将**创建或修改**任何文本文件（脚本 / 配置 / 数据 / 文档；第一节速查表覆盖的类型优先）；
- **或**将在命令行内联写入非 ASCII 内容（中文路径、中文参数、中文 here-string）；
- **或**刚出现下列任一症状：中文变 `??` / `�` / 乱码、`DirectoryNotFound` 但路径存在、`Unexpected token`、解析错误、文件内容错乱。

**不适用**：纯只读检索、不落盘的会话内分析。未触发时不要求输出 G4 落痕行。

### G2 判定与选路（由①②的输出直接决定）

`detect` 给出的判定与 `decide` 的出口：

| 判定 | 置信 | 路线 |
|---|---|---|
| `ASCII` | definitive | **直接编辑**（edit 工具可用；按目标编码写） |
| `UTF8-BOM` / `UTF16-LE` / `UTF16-BE` | definitive | **按原编码读写**，禁转换 |
| `UTF8-NOBOM`（多字节序列 ≥2） | strong | 按 UTF-8 读写；**可**补 BOM（先过②确认） |
| `UTF8-WEAK`（合法 UTF-8 但证据不足） | low | **按原字节读、不转换**；确需改则用 **ASCII 锚点在字节层**替换 |
| `LEGACY-8BIT`（非合法 UTF-8） | **assumed** | **先过②确认**：通过 → 按其页读写（**可以修**）；不通过 → 报用户，不动 |
| 候选梯子 top 分差 < 门槛 / 样本过小 | — | **只报不写**：把候选排序交用户裁决 |
| 无法确定 | — | **只报不写**，不动文件 |

**核心禁令（一句话）**：**GBK 文件绝不改写成 UTF-8；UTF-8 文件绝不改写成 GBK。** 行尾按原风格保留；含中文 `.bat/.cmd` 必须 GBK + CRLF。**唯一允许的定向转码**：给 `UTF8-NOBOM` 的 `.ps1` 补 BOM，且必须②通过。

### G3 新建文件与补丁脚本

| 目标 | 目标编码 | 行尾 |
|---|---|---|
| 纯 ASCII 内容（任何类型） | 任意（推荐 UTF-8 带 BOM） | 随原；新建用 CRLF |
| 含中文 `.ps1` / `.psm1` | UTF-8 **带 BOM**，或 ANSI/GBK 无 BOM（皆合法） | 随原 |
| 含中文 `.bat` / `.cmd` | **GBK** | **必须 CRLF** |
| `.md` / `.json` / `.tmpl` / `.txt` | UTF-8 **无 BOM** | 随原 |

- **新建文件**（`detect` 会报 `EXISTS=False`）：按上表目标编码直接写，不套用 `confirm`（没有"原字节"可比）。
- **含中文的补丁/临时脚本自身**：**纯 ASCII 化**——路径用 `$env:TEMP` / `$PSScriptRoot` 运行时解析，**脚本内不写中文路径字面量**；中文锚点用 `[char]` 码点构造，或从带 BOM 的锚点文件读入（纯 ASCII 脚本无法内联中文锚点）。
- **命令行内联中文**：把中文写进带 BOM 的脚本文件，以 `-File <脚本>` 调用；禁止 `-Command "...中文..."`。

### G4 落痕（把证据绑到动作上）

未触发 G1 时不需要。触发时在回复写出下列一行，**并附 `detect`/`decide`/`confirm` 的真实输出**（只报一句"查过了"不构成证据）：

```
编码闸门：<文件> | 判定=<...> | 页=<...> | 路线=<直接编辑|按原编码改写|补BOM写入|新建直写|只报不写>
```

### G5 完成判据（不要用"我觉得没问题"结案）

1. **编码与行尾不变**：改完重跑 `detect`/`decide`，判定与改前一致——除非本次意图就是给 `UTF8-NOBOM` 补 BOM（则应为 `UTF8-BOM`）；
2. **解码干净**：用目标页读回，关键中文串**逐字命中**；`U+FFFD` 数量**不增加**（以改前实测计数为基线——本文件正文自身就有若干 `U+FFFD` 作症状示例，别误判成新增）；
3. **`.ps1` 实跑**：`& powershell -NoProfile -File <脚本>` 一次，确认中文输出正常、无 `Unexpected token`；
4. **未降级**：`.ps1` 未留在 `UTF8-NOBOM`；`.bat/.cmd` 未留在 UTF-8 且为 CRLF。

> **语法自检两个陷阱（实测）**：① `[scriptblock]::Create((Get-Content -Raw -LiteralPath $p))` 能区分合法/非法语法，但**失败时抛的是非终止异常、进程退出码恒为 0**——不能当自动闸门，必须用 `try/catch` 判定，**不要看退出码**；② 它**检不出编码错误**：把合法 GBK `.ps1` 转成 UTF-8 无 BOM 后仍返回 True，只有第 1～3 条能发现。

### G6 失败模式（出现即回第①步重做，不要就地打补丁）

| 失败模式 | 现象 |
|---|---|
| **把合法 GBK 当 UTF-8 处理** | 中文变 `���`；且可能被改成"UTF-8 无 BOM"这一禁止格式；**解析仍通过，静默** |
| **只按 BOM 下判断** | 合法 GBK 与非法 UTF-8 无 BOM 字节特征相同，必错一半 |
| **从单个字节对下结论** | `D6 B5`（"值"的 GBK）恰是合法 UTF-8；样本越小越不可靠 |
| **用启发式静默替换字节** | `GetEncoding(936)` 默认 BestFit 会把 `E9`→`3F` 丢掉拉丁字符；判定必须用严格 fallback |
| **漏判无 BOM UTF-16** | NUL 密度对**纯中文** UTF-16 可能为 0%——须靠候选梯子而非单一启发式 |
| **含中文的补丁脚本无 BOM** | 中文锚点被 GBK 误读 → 替换"看起来成功"但文件未变，或误替换 |
| **脚本内联中文路径字面量** | `DirectoryNotFound`（字面量被误解成乱码）。把脚本放 ASCII 目录**不**能解决 |
| **验收只看"能解析"或退出码** | 编码已错的文件照样通过；语法失败时退出码仍为 0 |
| **用"这次没坏"当证据** | 同类工具历史上静默破坏过；单次未坏不构成允许 |

## 零、技能载入顺序（联动）

| 任务 | 必载技能（按顺序） |
|---|---|
| 写 .ps1（PowerShell 脚本/模板） | **charset-pitfalls（最先）** → 相关技能（如 dsh-launcher） |
| 写 .bat / .cmd | **charset-pitfalls（最先）** → **batch-files** |
| 打包/校验/修复 zip | charset-pitfalls → zip-archive-ops |

## 配套维护提醒（dsh-launcher 一键启动技能）

本技能是 `dsh-launcher`（DSH 一键启动）的**配套技能**，已打包进其
`assets\配套技能\`，安装一键启动时会自动装上本技能。

**修改本技能后，同步分发（缺一不可；Z: 网络盘归档已废弃，分发一律走 GitHub 私有仓库）**：
1. 打包 `charset-pitfalls__skillhub.zip`（根目录=技能名），归档到 GitHub 仓库
   `releases\<当前版本>\`（与主包同目录归档）＋ 更新仓库内配套源树 `dsh-launcher Add\charset-pitfalls\`；
2. 把新 zip 复制进 `dsh-launcher\assets\配套技能\`（覆盖旧包）；
3. 重打包 `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\`，git commit + push
   （setup.ps1 按版本/时间戳自动分发新版）。

本技能是本机长期踩坑经验的**唯一汇总地**。任何涉及中文文本、文件编码、脚本解析、
网络传输中文的场景，先对照本清单，避免重复踩坑。

## 一、文件编码速查表（写入约定）

| 文件类型 | 编码 | 说明 |
|---|---|---|
| `.ps1` | **含中文 → 二选一（均为合法）：UTF-8 带 BOM 或 ANSI/GBK 无 BOM（ISE 保存格式）**；**唯一禁止：UTF-8 无 BOM（PS 5.1 按 ANSI/GBK 解析 → 必炸）**；纯 ASCII → 任意编码均可 | Windows PowerShell 5.1 无 BOM 时按 ANSI/GBK 解析。两种合法格式都兼容 PS 5.1：① UTF-8 带 BOM（新写文件推荐，跨机器安全）；② **ANSI/GBK 无 BOM**（PowerShell ISE 5.1 默认保存格式，2026-08-29 实测 D:\Download\configure-git-credentials.ps1 即此格式，PS 5.1 直接可跑）。**绝不能写 UTF-8 无 BOM 的含中文 .ps1**。字节检测判据见「二、6」 |
| `.bat` / `.cmd` | **GBK + CRLF、无 BOM** | cmd.exe 按 ANSI 代码页解析；UTF-8 无 BOM → 中文乱码/命令错乱 |
| `.md` / `.json` / `.tmpl` / `.txt` | UTF-8 无 BOM | 常规文本 |
| zip 内条目名 | UTF-8 | 见第五节 |

## 二、PowerShell 中文坑（最高频）

1. **含中文的 `.ps1` 两种合法编码（替换旧铁律「必须 UTF-8 带 BOM」，2026-08-29 修订）**：
   - **UTF-8 带 BOM**：新写脚本推荐。`UTF8Encoding($false).GetBytes()` 不写 BOM！
     必须显式前置 `[byte[]](0xEF,0xBB,0xBF)` 再 `[System.IO.File]::WriteAllBytes()`。
   - **ANSI/GBK 无 BOM**：PowerShell ISE 5.1 默认保存格式，PS 5.1 按 ANSI 解析中文
     正常、直接可跑（2026-08-29 实测：D:\Download\configure-git-credentials.ps1）。
     用 ISE 编辑含中文脚本时保持 GBK 即可，**不要**另存为「UTF-8 无 BOM」。
   - **唯一禁止：UTF-8 无 BOM 的含中文 .ps1**——PS 5.1 按 ANSI/GBK 误解 → 中文乱码、
     字符串变乱码、`Unexpected token` ParserError、中文路径"找不到"。
   - 纯 ASCII 的 .ps1 任意编码均可（字节一致）；但写新文件仍推荐 UTF-8 带 BOM，
     与团队约定统一、跨机器安全。
   实例：setup.ps1 曾被误写成 GBK（含中文），本机 PS5.1 能跑但违反旧约定 → 已转回
   UTF-8+BOM（新约定下 GBK 也合法，可保留）。
2. **用 write/edit 工具创建的 .ps1 是无 BOM UTF-8（=禁止格式）**，PS 5.1 会按 GBK
   误读。创建后必须转成两种合法格式之一：补 BOM（UTF-8 带 BOM）或转 ANSI/GBK；
   **临时测试脚本尽量纯 ASCII**（路径用 `$env:TEMP` 运行时解析，脚本内
   不写中文路径字面量），否则 `Set-Content` 到中文路径会报
   `找不到路径 ... DirectoryNotFound`（路径已被 GBK 误解成乱码）。
3. **读文件统一显式编码**：
   `[System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)`，
   或 `Get-Content -Raw -Encoding UTF8`。不要依赖默认编码。
4. **语法自检**（不改文件）：
   `[scriptblock]::Create((Get-Content -Raw -LiteralPath $f))` 返回非空即 PARSE-OK。
5. **大块替换勿用内嵌 here-string**：在 `pwsh -Command` 里内嵌 `@'...'@` 可能丢
   尾随换行，`Replace` 拼接后会把两行粘成一行（如 `...Add('x')$miInfo ...` 报
   `Unexpected token`）。**模板/脚本整段替换用函数级提取（IndexOf 切片）**，或从
   基准文件提取替换文本，别依赖 here-string 的精确行尾。
6. **判断一个 .ps1 到底什么编码（字节检测，2026-08-29 实测沉淀）**：
   - 读前 2~3 字节：`EF BB BF` = UTF-8 BOM（PS 5.1 正常）；`FF FE` = UTF-16 LE
     BOM（PS 5.1 正常，ISE「另存为 Unicode」）；无 BOM 则按 ANSI/GBK 解析。
   - 无 BOM 时用 GBK(936) 与 UTF-8 分别解码同一段中文：**GBK 正常 + UTF-8 乱码
     = ANSI/GBK 编码**（PowerShell ISE 5.1 默认保存格式，PS 5.1 直接可跑）；
     **GBK 乱码 + UTF-8 正常 = UTF-8 无 BOM**（PS 5.1 必炸，需补 BOM 或转 GBK）。
   - 判定命令：`[Text.Encoding]::GetEncoding(936).GetString($bytes)` vs
     `[Text.Encoding]::UTF8.GetString($bytes)`，看哪边中文正常。
   - 实例（2026-08-29）：D:\Download\configure-git-credentials.ps1 为 ISE 保存的
     ANSI/GBK 无 BOM，PS 5.1 运行正常；而同批 GitHub 66 分支的 `dsh-sync.ps1`
     是 **UTF-8 无 BOM 含中文**，PS 5.1 `-File` 调用直接 ParserError
     （`Unexpected token '`n原因：…'`）——同一会话里两种文件并存，用字节检测区分。

## 三、AI 编辑工具（edit / write）编码坑（先检测后选路）

**背景（2026-08-30 实测 + 社区实证）**：AI agent 的 edit 工具在 Windows 上读已有文件时
按 ANSI 代码页（中文系统 = GBK）解码，再按 UTF-8 写回 → 整个文件中文变 mojibake（乱码）、
UTF-8 BOM 被丢弃、脚本语法全挂。这是业界已知 bug（claude-code #60174「Edit tool corrupts
UTF-8 BOM files on Windows」、#34695 / #62723 同类，qwen-code #1680 专门 PR 修复 BOM 丢失；
根因见 codex #23044：Windows 非英语区域下 Get-Content 默认按 ANSI 代码页读）。write 工具是
全新写文件（不做「读旧写新」转换），无此问题。

**铁律：编辑已有文件前，先检测编码，再动态选路：**
1. **检测**（一次命令，毫秒级）：读前 3 字节看 BOM（`EF BB BF` = UTF-8 BOM）；
   扫描全文是否有 `>0x7F` 字节（有 = 非 ASCII / 含中文）。
2. **选路**：
   - **纯 ASCII 文件**（无 BOM、无 >0x7F 字节）→ 可用 edit 工具（任何编码读同样字节，
     写回不变，安全）。
   - **含中文 / 带 BOM / 其他编码** → **禁止 edit**；改用「补丁脚本 + 显式编码」：
     ① write 工具写补丁脚本（可含中文：write 输出是干净 UTF-8 无 BOM，不转换不乱码）；
     ② 一条命令给脚本补 UTF-8 BOM（PS 5.1 解析中文必需）再执行；③ 脚本内
     `[IO.File]::ReadAllText(路径, UTF8)` 读 → 归一化行尾 `\r\n`→`\n` → 字面
     `.Replace()` 替换 → 还原行尾 → `UTF8Encoding($true)`（源文件原本 BOM）/
     `($false)`（原本无 BOM）写回。
3. **改完必验三件事**：BOM 字节 / 语法解析（`[scriptblock]::Create`）/ 中文完整性
   （`Contains` 检查关键中文字符串，防 mojibake 漏网）。
4. **效率结论**：检测成本毫秒级；「先检测后选路」把保护只花在需要的文件上，
   避免 edit 破坏后的「恢复 + 重做」返工（2026-08-30 实测返工 4~5 步 ≫ 检测 1 步）。
   纯 ASCII 文件走 edit 零额外开销；含中文文件一次写对。
## 四、批处理 / cmd / 控制台坑

1. **`.bat/.cmd` 含中文必须 GBK 编码文件**（UTF-8 无 BOM 会被按 ANSI 读 → 乱码）。
   写文件用 `[System.Text.Encoding]::GetEncoding(936)`。
2. **cmd 子进程输出捕获**：控制台代码页 936(GBK) 下，中文输出按
   `[System.Text.Encoding]::GetEncoding(936)` 解码读取，别按 UTF-8 读。
3. **`cmd /c "powershell -Command \"中文\""` 双重编码风险**：命令行传中文极易被
   中间层转码破坏。稳妥做法是 `powershell -File <带 BOM 脚本>`，不内联中文。
4. **`findstr` 校验**：findstr 按 ANSI 处理，且正斜杠/反斜杠有差异（zip 条目名
   bsdtar 为正斜杠），校验时注意。
5. **控制台编码**：Windows PowerShell 5.1 默认 ANSI(GBK)，pwsh 7 默认 UTF-8。
   需要中文正常输出可 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`。

## 五、HTTP / RPC 中文传输坑（如 DSH RPC、Web API）

1. **请求体必须 UTF-8 字节**：`Invoke-WebRequest -Body ([Text.Encoding]::UTF8.GetBytes($json))`；
   直接传字符串 body → 中文变 `??`。
2. **响应必须按字节读 + UTF-8 解码**：
   `$resp.RawContentStream.ToArray()` → `[Text.Encoding]::UTF8.GetString($bytes)`；
   按字符串/默认编码读 → 中文乱码。
3. JSON 中的中文经 `ConvertTo-Json` 会 `\uXXXX` 转义，解析端正常还原即可，别手动
   二次转义。

## 六、zip / 压缩包编码坑

1. **条目名分隔符**：.NET Framework `CreateFromDirectory` 写**反斜杠**条目名；
   `C:\Windows\System32\tar.exe`（bsdtar）写**正斜杠**（推荐，跨平台兼容）。
2. 条目名本身 UTF-8 编码；用 `ZipFile.OpenRead` 校验条目名与内容。
3. 详见 `zip-archive-ops` 技能（打包/校验/修复完整流程）。

## 七、常见症状 → 根因 速查

| 症状 | 根因 |
|---|---|
| 脚本报"表达式或语句中包含意外的标记" | .ps1 无 BOM，中文被 GBK 误解 |
| 中文显示成 `??` | HTTP body 传了字符串而非 UTF-8 字节 |
| 中文显示成 `�`/乱码 | 响应/文件按错误编码读取 |
| `找不到路径 ...目录不存在` 但路径明明在 | 脚本文件无 BOM，中文路径字面量被 GBK 误解成乱码 |
| .bat 中文乱码/命令错乱 | .bat 用了 UTF-8 而非 GBK |
| 子进程中文输出乱码 | 输出按 UTF-8 读，实际控制台是 GBK(936) |
| edit 工具改后中文全变乱码/语法挂 | edit 按 ANSI 读入再按 UTF-8 写回（mojibake + 丢 BOM）；改用补丁脚本+显式编码 |

## 八、本机长期实例（已踩过）

- **dsh-launcher 技能**：其生成物/模板统一 **UTF-8 带 BOM**（团队约定，跨机器安全，
  setup.ps1 已按此写出生成物）；`_meta.json` 等用 UTF-8 无 BOM。这属于「新写文件统一
  UTF-8 带 BOM」的约定；**ISE/GBK 无 BOM 同为合法格式**（见一/二节），他人机器上的
  ISE 保存脚本不必强行转码。
- **DSH RPC**（托盘脚本 `Invoke-DshRpc`）：UTF-8 字节发请求、RawContentStream 字节
  收响应，中文工作区名/标题不乱码。
- **踩坑实例 2026-08-21**：write 工具写的中文测试脚本无 BOM → PS 5.1 GBK 误读 →
  `Set-Content` 中文路径 DirectoryNotFound。教训：测试脚本纯 ASCII + `$env:TEMP`。
- **踩坑实例 2026-08-21（RPC）**：请求体字符串 → 中文 `??`；响应按默认编码读 → 乱码。
- **实测 2026-08-29（ISE 保存格式 vs UTF-8 无 BOM）**：D:\Download\
  configure-git-credentials.ps1（PowerShell ISE 保存）为 **ANSI/GBK 无 BOM**，PS 5.1
  按 ANSI 解析中文正常、可顺利运行；同批 GitHub 66 分支 dsh-sync.ps1 为 **UTF-8 无
  BOM 含中文**，PS 5.1 直接 ParserError。字节检测（GBK vs UTF-8 解码比对）见「二、6」。
  结论：**「别人给的 .ps1 能跑」≠「编码符合约定」**，改动前先字节检测；ISE 老文件
  保持 GBK 即可，新写文件一律 UTF-8 带 BOM。

## 九、动手前 Checklist

**闸门前置检查（GATE-0，先于以下各项；未过闸门则以下各项均无意义）**

0. **本次是否要写文件？** 是 → 已按 G0 走到 G2 取到事实（是否新建 / 编码六类判定 / 行尾），路由由 G3 直接决定，
   并在回复写出 G4 落痕行 **加 G2 命令的原始输出**。否（纯只读）→ 本项不适用，**不要**为格式好看强插落痕行。

1. 要写的脚本/模板是什么类型 → 查第一节编码表 + G2 第二步目标编码。
2. 工具写的 `.ps1` 是否转成了合法格式（UTF-8 带 BOM 或 ANSI/GBK 无 BOM，**禁 UTF-8 无 BOM**）？补丁/测试脚本是否纯 ASCII、是否落在 ASCII 路径？
3. 涉及中文路径/文本的读写是否**显式指定了与源文件相同的编码**？**GBK 文件有没有被误按 UTF-8 读写？**
4. 若目标已存在：G2 判定是六类里的哪一类？**改后编码与行尾是否与改前一致**（G5 第 1、4 条）？
5. HTTP/RPC 中文是否走了 UTF-8 字节收发？
6. 子进程/控制台输出按什么代码页解码？
7. 写入含中文的 `.bat` / `.cmd` 时：编码是否为 GBK、行尾是否 CRLF？

