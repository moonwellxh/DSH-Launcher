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

1. 要写的脚本/模板是什么类型 → 查第一节编码表。
2. 工具写的 .ps1 是否转成了合法格式（UTF-8 带 BOM 或 ANSI/GBK，**禁 UTF-8 无 BOM**）？测试脚本是否纯 ASCII？
3. 涉及中文路径/文本的读写是否显式指定编码？
4. HTTP/RPC 中文是否走了 UTF-8 字节收发？
5. 子进程/控制台输出按什么代码页解码？
6. 编辑已有文件前先检测编码（BOM + 非 ASCII 字节）：纯 ASCII 才用 edit，含中文/带 BOM 走「补丁脚本 + 显式编码」（见第三节）。
