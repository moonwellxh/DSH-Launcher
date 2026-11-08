---
name: dsh-launcher
description: >
  DeepSeek Harness（DSH）一键启动 + 系统托盘 安装/迁移技能。提供自适应安装脚本
  setup.ps1：自动探测本机 DSH 安装方式（PATH 上的 dsh 全局安装，或 deepseek-harness
  源码树 + node），生成启动DSH.bat 菜单启动器、DSH-tray.ps1 系统托盘（右键「退出并
  停止 DSH」可关闭服务）、dsh.cmd CLI 包装，并可创建桌面快捷方式。适用于：为任意一台
  机器安装或迁移 DSH 的一键启动与托盘关闭方案。
---

# DSH 一键启动 + 系统托盘

给任意一台机器安装「一键启动 + 托盘手动关闭」的 DSH 启动方案。
> ⚠️ **安装/更新本技能后的第一条强制步骤**：必须重跑 `assets\setup.ps1`
> （`powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1" -InstallDir "<启动器目录>" -NoShortcut`）。
> 它会重新生成启动脚本（补丁体系已于 2026-11-06 退役，不再应用补丁）；**跳过此步 = 启动脚本未刷新**。

## 到新机器怎么用（二选一）

### 方式 A：作为 DSH 技能使用（有 AI 协助时，推荐）

1. 把本技能装到 DSH 技能目录 `~/.agents/skills/dsh-launcher`（或从
   `dsh-launcher__skillhub.zip` 解压，zip 根目录=技能名）。
2. 运行安装脚本（AI 或用户手动执行均可）：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1"
   ```

   脚本会自动探测本机 DSH、生成适配脚本、默认建桌面快捷方式。
3. **配套技能自动安装**：`assets\配套技能\` 目录内所有 `*__skillhub.zip` 即配套技能
   （**目录即事实源**：setup.ps1 与同步引擎均扫描该目录，增删配套只需放/删 zip，
   无需改任何清单），setup.ps1 安装时会自动把它们装进 `~/.agents/skills\`
   （已装且包内不更新则跳过）。
   **只需分发 `dsh-launcher__skillhub.zip` 一个包即可带全配套技能**。
   配套技能内容变更后，需把新 zip 同步进 `assets\配套技能\` 再分发。

### 方式 B：作为绿色软件使用（无 AI 时，纯复制）

**最简方式（就地安装）**：把 `dsh-launcher__skillhub.zip` 解压到任意位置（如
`F:\DSH\dsh-launcher\`），双击解压目录里的 **`就地安装.bat`**——它自动完成：
① 把技能注册到 `%USERPROFILE%\.agents\skills\dsh-launcher`（AI 会话可加载本技能及
配套技能）；② 以**自身所在目录为安装目录**就地生成托盘/启动脚本/桌面快捷方式。
无需提供压缩包地址，本机已装 DSH（源码树或 PATH 均可）即可直接使用。

1. 把 `assets\` 目录（含 `setup.ps1` 及其 `tmpl\` 模板、便携文件、图标）
   整个复制到目标机器。
2. 运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -InstallDir D:\DSHS
   ```

   无需 agent 参与，双击或命令行执行即可完成安装。
3. **以后更新**：把新 `dsh-launcher__skillhub.zip` 放到 `assets\` 目录（或直接拖到脚本上），双击 `assets\更新安装.cmd`——它自动完成「解压覆盖技能 + 重跑 setup.ps1 + **刷新桌面快捷方式**（指向当前安装目录）+ **自动启动托盘**（就绪后自动开浏览器一次）」。若托盘图标未出现，先结束残留的 DSH-tray powershell 进程再启动；若 setup 失败会明确报错并提示原因。

## setup.ps1 参数

```powershell
setup.ps1                          # 自动探测并安装到 %USERPROFILE%\DSH
setup.ps1 -InstallDir D:\DSHS      # 指定安装目录
setup.ps1 -NoShortcut              # 不建桌面快捷方式
setup.ps1 -CheckOnly               # 只探测、打印结果，不安装
```

## 安装即写入通用记忆规则 0（2026-09-05 起：只装一次启动器 = 规则永久生效，无需运行本技能）

`setup.ps1` 在安装流程中自动调用 `Install-GeneralMemoryRule0`，把「通用记忆规则 0」
（实事求是 / 独立认真判断 / 禁止讨好、用户画像与附和；正文见 setup.ps1 内实现）幂等
写入 DSH 用户全局指令文件 `$DSH_HOME\AGENTS.md`（`$DSH_HOME` 未设时 = `$DSH_HOME\AGENTS.md`）：

- **只装一次 = 永久生效**：只要跑过一次 setup.ps1（含 `就地安装.bat` / `更新安装.cmd`
  触发），规则 0 即进入该机通用记忆；DSH 每次会话自动加载 AGENTS.md（先于任何项目级
  AGENTS.md），因此**不加载、不运行本技能也持续生效**；以后卸载本技能同样不影响
  （规则已固化在 AGENTS.md，不依赖本技能文件）。
- **幂等合并**：目标文件已含规则标记 → 跳过；已有用户其他内容 → 在其后追加合并，
  绝不覆盖既有指令；重复运行 setup.ps1 不产生重复条目。
- **更新规则正文**：改 `assets\setup.ps1` 内 `Install-GeneralMemoryRule0` 的规则文本后，
  对已写入过的机器需删除 AGENTS.md 中旧规则块再重跑 setup.ps1（或手工同步 AGENTS.md）。
- **内嵌文本与 AGENTS.md 的关系（2026-09-22 已同步）**：`setup.ps1` 内嵌的 `$ruleBlock` 已同步为现行规则 0（含节号 `## 1 ` 与末句括注「（平台系统约束除外，见第 5 节）」），与已写入的 `AGENTS.md` 的规则 0 段逐字一致（块内容口径：不含 here-string 结构性首尾空行）；权威仍以 `AGENTS.md` 为准（每次会话注入的生效文件）。注意：该内嵌块用于**新建** AGENTS.md 的机器，末句括注中的「见第 5 节」在仅有规则 0 的新文件里暂无指向，随通用记忆扩充后自然成立。

## 探测逻辑（AI 需知）

> **边界声明（必读）**：`setup.ps1` 是**启动器生成器，不是 DSH 安装器**。它从不安装、
> 升级、卸载 DSH 本体；不运行 npm/pnpm；不改 PATH。DSH 怎么装由**用户指定**：
> 源码树 = `git pull` + `pnpm install` + `pnpm build --profile official`（产物
> `apps\cli\lib\bin.js`，缺它源码树识别不到）；npm 全局 = `npm update -g @deepseek-ai/dsh`。
> setup.ps1 只做三件事：① 探测**已装好**什么；② 生成启动脚本/快捷方式；③ 安装配套技能（补丁体系已于 2026-11-06 退役）。它的 `mode=path/source` 只是"从已装好的里面挑一个来启动"，
> **不影响也不修改任何安装**。若 PATH 有 dsh 且源码树也存在，会打黄色警告并说明
> 如何切到源码树运行。

`setup.ps1` 按以下顺序判定本机 DSH 安装方式：

1. **PATH 模式**：`dsh` 已在 PATH（npm 全局安装，例如
   `F:\DeepSeekS\npm-global\dsh.cmd`）。
2. **源码树模式**：存在 `deepseek-harness` 源码树（含 `apps\cli\lib\bin.js`）且有
   node（优先 PATH 上的 `node`，其次 `~\.workbuddy\binaries\node\versions\*\node.exe`）。

生成产物（写入安装目录）：

| 文件 | 作用 |
|---|---|
| `启动DSH.bat` | 菜单启动器（1 托盘+Web / 2 TUI / 3 Headless / 0 退出） |
| `启动DSH-托盘.cmd` | 一键托盘（跳过菜单，直接启动 + 开浏览器；**已自隐藏窗口**：首次进入经 `run-hidden.vbs` 隐藏重入，双击不再闪命令行窗口） |
| `启动DSH-托盘.vbs` | 一键托盘（**零命令行窗口**，wscript 直启 DSH-tray.ps1，推荐双击入口；配套 `run-hidden.vbs` 供 .cmd 自隐藏重入） |
| `DSH-tray.ps1` | 系统托盘：右键菜单**顶部分隔线上方三行**——第一行「DSH 版本 x.x.x」**加粗**（点击打开 DeepSeek 文档 deepseekdocs.com）、第二行「最新版本 x.x.x（点击升级）」（可更新时可点，弹窗确认：可编辑提示词 + 选模型/推理等级后 `selectModel`+`prompt` 提交，无需粘贴）、第三行「启动托盘 x.x.x 版（点击可更新/已是最新）」（点击**与 GitHub 双向同步**（发布级）：配置优先环境变量 `DSH_SYNC_REPO` / `DSH_SYNC_BRANCH` / `DSH_SYNC_TOKEN` > `$DSH_HOME\gh-sync\config.json` > 内置默认（repo=`moonwellxh/DSH-Launcher`、branch=`main`）；网络自动探测系统代理、直连↔代理双路回退（命令级 `-c` 注入，不改全局 git 配置）；git 全程非交互（禁终端提示 + 禁 GCM 弹窗），失败按类给出可操作提示（未装 git / 认证缺失或失效 / 仓库分支 404 / 网络不通 / 非快进）；以仓库源树 `dsh-launcher/` 为比对对象逐文件内容比对（文本先归一化 CRLF→LF 再哈希，避免 autocrlf 造成"同内容不同哈希"；跳过机器特定文件 install-dir.txt），方向**永不自动判定**：引擎只按版本号/时间戳/内容差异给出**建议**，由用户在弹出的方向选择框自行决定 上传到 GitHub / 拉取 GitHub 版本 / 取消，确认后才执行（绝不自动执行方向；2026-09-05 规则）。上传方向 = 更新源树 + 发布 **主包+全部配套** 到 `releases\<版本>\` + git 提交推送（`HEAD:<branch>`，token 经 http.extraheader 仅内存注入、不落盘不打印）并校验，一致则跳过，时间戳相同但内容不同则按 **git 提交时间 vs 本地修改时间**分析并弹窗展示分析/建议，由用户确认方向（上传到 GitHub/拉取 GitHub 版本/取消）后才执行（绝不自动覆盖；git 历史保留旧版；同步带互斥锁防并发；缓存损坏自动重建）；不信任缓存/版本号）；其余菜单项：打开 superagent 面板 (3082) / 打开 Web UI / TUI / Headless / DS 开放平台（platform.deepseek.com）/ 重启 / 退出并停止；单击无动作、双击开浏览器；状态气泡保留 |
| `dsh-toast.ps1` | 右下角自绘提示窗（2026-10-26）：`-InstallDir <目录> [-Title .. -Text .. -Seconds 5]`；「硬重启托盘」起点用它提示，不依赖系统通知设置 |
| `dsh-tray.log` | 托盘提示留痕（运行期生成，非分发产物）：每张卡片一行 + 硬重启开始/结果；超 1 MB 轮转 `dsh-tray.log.1` |
| `dsh-log.ps1` | 托盘日志查看器（2026-10-26）：`-Tail N` / `-Level WARN,ERROR` / `-Event restart.start,restart.setup` / `-Summary` / `-Raw`；解析规则唯一实现 |
| `dsh.cmd` | CLI 入口包装（`--version` / TUI / Headless） |
| `whale-white.ico` / `whale-white.png` | 托盘图标（默认，白色描边鲸鱼版，镂空填白/下半白底） |
| `tray.ico` / `whale.ico` | 备用图标（自动回退） |

> **新机器装环境前必读**：`环境要求-安装指南.md`（本技能根目录）——通用 Node.js / Git 的安装步骤、为什么禁止用宿主内嵌运行时、干净启动方式、验证清单与常见问题（2026-08-30 沉淀）。

## 关键原理（排障必读）

- **就绪信号**：`dsh web` 完整启动后才会打印 `dsh web: http://127.0.0.1:3080`；
  托盘脚本等到该信号出现在日志（`dsh-web.log`）后才自动打开浏览器，避免过早打开
  导致前端报 `Failed to load plugins ... pending`。
- **浏览器只开一次（--no-open）**：`dsh web` 服务端默认启动即自动开浏览器——托盘启动
  服务一律加 `--no-open`（源码树 `web --no-open`；PATH 模式 `dsh web --no-open`），
  浏览器**只由托盘就绪后开一次**（`browserOpened` 守卫）。避免老 DSH/坏安装下服务反复
  重启导致浏览器疯狂弹出。
- **打开 DSH 主窗口（2026-10-25 修正，1.1.95 待发布）**：托盘双击 / 「打开 Web UI」/ 就绪后自动开浏览器
  都走 `Open-Url` → `Open-DshApp`：已有 DSH 窗口 → Win32 枚举找窗口 + `PostMessage(WM_SYSCOMMAND,
  SC_RESTORE)` 恢复 + `SetForegroundWindow` 置顶（不开多个、不重复加载页面）；没有窗口 →
  **默认模式** = `msedge --app-id=<已装 PWA>`（无标题栏的独立应用窗口），每 250ms 轮询窗口、最多 12 秒，
  窗口一出现就置顶返回（用户随后关掉也不会补开）。**降级模式** = 12 秒内一个窗口都没枚举到
  （PWA 起不来，或标题一直不就位——例如 cookie 过期后的 401 页）时，再发一次 `msedge --app=<带令牌 URL>`
  （带标题栏的应用窗口，页面能用、观感差一档），再轮询 6 秒。两条都没窗口才回退默认浏览器。
  - **为什么只发一次**：旧实现先 `--app=URL` 睡 4 秒、找不到窗口再发 `--app-id` 重试一次。用户在
    这 4 秒内关掉刚弹出的窗口时第二次启动照发——表现就是「关掉以后它自己又弹一个」；而且两次入口
    不是同一个东西：`--app=<URL>` 在本机被 Edge 当成普通导航，开出来的是**浏览器网页版**（有标签栏
    + 地址栏），`--app-id` 才是已装 PWA 的**应用窗口**（无标签栏/地址栏）。同一个按钮弹出两种 UI
    （2026-10-25 用户两次报障）。
  - **入口取舍（用户 2026-10-25 指定）**：无标题栏的已装 PWA 窗口是默认，带标题栏的应用窗口只作兜底
    降级。托盘与桌面 `DSH应用.lnk` 都以 `--app-id` 为主，外观一致；
    令牌用 Chromium 的 `--app-launch-url-for-shortcuts-menu-item=<带令牌 URL>` 捎进去：Edge 认就
    按带令牌入口打开、顺带刷新 30 天认证 cookie；不认就退回 app 自己的 `start_url`（等于旧版
    `--app-id` 行为）。2026-10-25 本机实测（Edge 156）：带该开关启动得到的确实是应用窗口（不是浏览器
    网页版）、页面正常加载；至于它是否真把令牌 URL 带进去了，cookie 有效时分不出来，属"认了更好、
    不认不更差"。
  - **兜底语义**：默认入口里只要「窗口出现并置顶」就返回成功——用户在轮询期内关掉也不会补开。
    只有默认入口 12 秒内**一个窗口都没枚举到**才降级；降级也拿不到窗口才返回 `$false`，交
    `Open-Url` 用默认浏览器做最后一次兜底（保证一定有页面）。已知残留：若在窗口标题就位前
    （通常 <1 秒）就把它关掉，可能仍会出现降级窗口——这是"必须保留兜底"的代价，概率很低。
  - **未装 PWA 时**：双击托盘 /「打开 Web UI」不默默开普通网页，而是打开 Edge 访问 3080 +
    气泡提示「点安装图标安装为独立应用」，`$script:pwaGuideShown` 保证同一次托盘生命周期只提示一次。
- **Web 看护重启上限**：自动重启连续失败 3 次 → 停止自动重启并气泡提示
  「DSH Web 反复启动失败（可能 DSH 版本过旧或安装异常），请升级 DSH」。服务恢复后计数
  归零。**老 DSH + 新启动器**场景：若 web 起不来即升级 DSH。
- **托盘手动关闭**：托盘脚本记录 3080 端口的监听 PID，右键「退出并停止 DSH」时
  `taskkill /PID <pid> /T /F` 停止整棵进程树。
- **硬重启托盘（2026-10-26 对抗性审查后重做，1.1.96）**：点击先弹确认框，写明四步副作用
  （结束 dsh web 进程树＝当前 AI 回合中断 / 只关 DSH 应用窗口 / 重跑安装脚本并可能改写
  `$DSH_HOME/AGENTS.md` 与配套技能 / 重启托盘）。执行链：① `Test-DshListenerIdentity` 先验 3080
  属主（进程名 `node|dsh` → 命令行含 `bin.js|dsh|deepseek-harness` → 父进程是托盘），判不准就
  **不杀**并在气泡里说明；② `CloseDshWindows` 只关 Edge 进程承载、且标题不以 `- Microsoft Edge`
  结尾的应用窗口（普通浏览器窗口与记事本/Word 等一律不碰）；③ setup.ps1 先 `Test-Path`，缺失则
  只重启托盘不重渲染；④ helper 用 `-PassThru` + `Wait-Process -Timeout 300` 跑 setup，回收退出码，
  结果写 `dsh-restart-status.txt`（`setup=done|failed|timeout|missing`）；⑤ 新托盘启动时读该文件，
  非 done 或带 notes 才弹气泡（成功静默），读完即删。⑥ **起点提示（自绘弹窗）**：helper 在结束托盘之前启动安装目录里的 `dsh-toast.ps1` —— 右下角
  无边框卡片（鲸鱼图标 +「DSH 正在重启」+ 说明，5 秒自动消失，`WS_EX_NOACTIVATE` 不抢焦点）。
  **为什么不用系统通知**：本机 `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\
  EnableBalloonTips = 0`，`ShowBalloonTip` 一律不显示；WinRT Toast 在本机也不落地。故改为自绘窗口，
  不依赖通知设置。
  **全部托盘提示统一走它**（2026-10-26 用户确认）：新增 `Show-DshNotice(超时, 标题, 正文, 图标)`，
  参数顺序与原 `ShowBalloonTip` 一致，模板里 39 处调用点已全部替换（就绪/启动失败/看护反复失败/
  已恢复/硬重启结果/升级与同步/CodeBuddy 网关/PWA 引导/打开失败等）。卡片**单实例**（按安装目录
  的 pid 文件，新消息顶掉旧的，不叠加）、按级别着色（Info 白 / Warning 黄 / Error 红）、正文超长
  自动加高。`dsh-toast.ps1` 缺失时才退回 `ShowBalloonTip`（其它机器气泡是好的）。
  - **留痕（2026-10-26 用户要求）**：卡片是瞬时弹窗、不进通知中心，故每张卡片都往安装目录的
    `dsh-tray.log` 追加一行 `yyyy-MM-dd HH:mm:ss [Info|Warning|Error] 标题 | 正文`（UTF-8 无 BOM；
    正文换行折成空格；超 1 MB 轮转 `dsh-tray.log.1`）。硬重启的 helper 另记两行：
    `[Info] 硬重启托盘：开始（旧托盘 PID …；setup=…）` 与 `[Info|Warning] 硬重启托盘：setup=done|failed|timeout|missing（exit=…）notes=…`。
  已知残留：托盘仍把「3080 有监听」当作
  「DSH 已在跑」，港口被第三方占用时不会自起 dsh web（属既有设计，另行评估）。
- **日志与留痕（后续维修必读）**：托盘所有提示是自绘卡片（不进通知中心），**每张卡片自动写一行**
  到 `<安装目录>\dsh-tray.log`，格式 `[dsh-tray] ts=<ISO8601+时区> level=<INFO|WARN|ERROR>
  event=<notify|restart.start|restart.setup> …`（固定前缀、`key=value`、超 1 MB 轮转 `.1`）；
  硬重启另记 `restart.start`/`restart.setup` 两行并用 `run` 关联、带 `duration_ms`。
  读日志用 `<安装目录>\dsh-log.ps1`（`-Tail/-Level/-Event/-Summary/-Raw`），不要自造解析；
  改提示必须走 `Show-DshNotice`，否则"有卡片无留痕"。完整字段表、级别语义、偏离声明与改动点位见
  `docs\日志与留痕-维护说明.md`（本技能目录内）。
- **编码约定**：`.bat/.cmd` 用 GBK + CRLF（含中文时）、无 BOM；`.ps1` **含中文必须 UTF-8 带 BOM**（否则 Windows PowerShell 5.1 按 ANSI 解析中文会报语法错误），纯 ASCII 的 .ps1 任意编码均可（推荐仍带 BOM）。`setup.ps1` 已按此约定写出生成物，不要手工改写生成后的脚本。
- **写 .ps1/.bat/.cmd 前先载入 `charset-pitfalls` 技能**（全局中文编码避坑汇总，
  含本技能全部编码约定与踩坑记录），动手前对照编码表，不要等出乱码再查。
- **冷启动**：源码树模式优先用已构建的 `apps\cli\lib\bin.js`（免 tsx，约 4s），
- **0xc0000142（cmd/node 偶发"应用程序无法正常启动"）**：DLL 初始化失败的瞬时现象，多为**快速连续拉起多个进程**（或系统瞬时状态/其他安全软件扫描）触发，非持续故障。处理：避免密集拉进程；托盘版本读取已改为直接读 package.json（免 node 进程）；如频繁出现再排查系统 DLL/安全软件。- **快捷方式图标不更新**：`.lnk` 指向的 `.ico` 文件本身没问题时，是 Windows 图标缓存未刷新。解决顺序：先 `ie4uinit.exe -show`；仍不更新则结束 Explorer（`taskkill /f /im explorer.exe`）→ 删除 `%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db` → 重启 Explorer（`start explorer.exe`）。
- **GitHub 同步（同步守卫，1.1.66 发布级重写）**：同步逻辑**唯一实现为 `assets\dsh-sync.ps1`**，托盘「一键同步」菜单调用它执行
  （托盘生成物内不再内嵌同步实现，原 `tmpl\parts\70-sync-*.ps1` 内嵌副本已删除）。同步以仓库源树 `dsh-launcher/` 为比对对象，逐文件
  **内容级比对（不信任缓存/版本号）**——文本文件先归一化 CRLF→LF 再 SHA256（git `core.autocrlf` 会把检出文件
  变成 CRLF，与 zip 内 LF"同内容不同哈希"，必须归一化；二进制如 zip/ico/png 保持原始字节）；**跳过机器特定文件**
  （`assets/install-dir.txt`）；方向**永不自动判定**：引擎只给出建议（版本号/时间戳/内容差异信号），由用户在弹出的方向选择框自行决定 上传/拉取/取消——绝不自动执行方向（2026-09-05 规则）；时间戳相同但内容不同时按 **git 提交时间 vs
  本地修改时间**分析并弹窗由用户确认方向（上传/拉取/取消），**绝不自动覆盖远端良包**。配置/健壮性：repo/branch/token
  可配置（环境变量 `DSH_SYNC_REPO/DSH_SYNC_BRANCH/DSH_SYNC_TOKEN` > `$DSH_HOME\gh-sync\config.json` > 默认）；
  网络自动探测系统代理（注册表）直连↔代理双路回退；git 非交互（`GIT_TERMINAL_PROMPT=0` + `GCM_INTERACTIVE=Never`
  防弹窗挂起）；失败分类为可操作提示（未装 git / 认证缺失或失效 / 仓库或分支 404 / 网络不通 / 非快进）；
  上传 = 更新源树 + 发布 5 个 zip（主包+4 配套，.NET ZipFile 正斜杠条目名、排除 install-dir.txt）到
  `releases\<版本>\` + git 提交推送（`HEAD:<branch>`，token 经 http.extraheader 仅内存注入）；同步带互斥锁防并发、
  缓存损坏自动重建、结构契约校验（缺 `dsh-launcher/` 源树即报错并提示检查 branch）。写 zip 后按 `zip-archive-ops`
  校验。打包/修复流程见 `zip-archive-ops` 技能。
  避免 `--import tsx/esm apps/cli/src/bin.ts` 的约 20s 现场编译。

## 关键原理（排障补记 2026-08-21）

- **PATH 模式陷阱**：`Get-Command dsh` 在 PowerShell 中会优先解析到 `dsh.ps1`（ExternalScript），而非 `dsh.cmd`；若把它写进 .cmd 包装器会得到空输出（cmd 无法执行 .ps1）。故 setup.ps1 的 path 模式改用 `Get-Command dsh.cmd` 解析真实 CLI 入口。
- **递归陷阱**：本地 `dsh.cmd` 若用裸 `dsh %*` 转发，当工作目录含同名 `dsh.cmd`（桌面快捷方式 WorkingDirectory 即安装目录）时会解析到自身、无限递归卡死。故包装器/托盘一律用解析出的**绝对路径** `call "<dsh.cmd 绝对路径>" %*` 与 `cmd /c "<绝对路径>" web`。
- **New-Object 括号参数陷阱（对话框不弹出的元凶）**：`New-Object System.Drawing.Point(160, $y - 1)` 的括号**不是方法调用语法**，`160, $y - 1` 按逗号优先级解析成 `(160, $y) - 1`，对数组做减法直接抛 `op_Subtraction` 异常（被 `catch {}` 吞掉后表现为"点了没反应"）。凡括号参数里含算术一律改用显式写法：`New-Object System.Drawing.Point -ArgumentList @(160, ($y - 1))`。已按此修正模板全部 4 处。
- 本技能模板已按上述几点修正；重新 `setup.ps1` 即可生成正确产物。

## 关键原理（排障补记 2026-08-23：PATH 模式托盘循环 Bug 修复）

> **红线（防复发）**：脚本**内部**调用入口/服务/命令一律用**绝对路径**，禁止裸命令名——
> cmd 解析命令是【当前目录优先于 PATH】，工作目录里只要有同名 `.cmd/.bat/.exe` 就会劫持调用
> （安装目录里就有本地 `dsh.cmd` 包装器，裸 `dsh` 必然命中它）。

- **PATH 模式服务启动劫持（托盘 15s 循环 Bug 根因）**：托盘 `Start-DshServer` 若用裸
  `cmd /c dsh web`，cmd 解析命令时【当前目录优先于 PATH】——而安装目录里正好有本地
  `dsh.cmd` 包装器，其 `web` 分支是 `start powershell -File DSH-tray.ps1 -OpenBrowser`
  （拉起**托盘**而非 web 服务）→ 新托盘发现互斥锁被占 → 强杀旧托盘 → 15s 后看护再判定
  "服务未运行" → 再次劫持 → **每 15s 一个新托盘、旧托盘被杀（鬼影图标）、服务永远起不来**。
  修复：PATH 模板 `Start-DshServer` 改用解析出的全局 dsh **绝对路径**
  `$arg = '/c "__DSH_CMD__" web'`（setup.ps1 的 PATH 模式已注入 `__DSH_CMD__`），绕过本地包装器。
  源码树模式用绝对 node 路径，无此问题。**已装机器需重跑 setup.ps1 重新生成 DSH-tray.ps1，
  并先结束旧 buggy 托盘进程再验证（旧进程的看护仍会触发循环）。**
- **接管误杀收窄**：互斥锁接管原按 `'DSH-tray\.ps1'` 匹配命令行，会误杀**任何**命令行里
  含该字样的 powershell（排查脚本等无关进程）。现行为 `-File\s+.*DSH-tray\.ps1`
  （只杀真正以 `-File` 方式运行托盘脚本的进程；`.*` 版同时支持带空格的脚本路径）。

## 补丁自动载入清单（assets\补丁管理\）— 已于 2026-11-06 退役

> **本体系已停用。** 补丁引擎、自动载入清单、重打/还原 bat 已移入
> `D:\DSHS\_bak\补丁管理-退役-20261106-174104\`；`setup.ps1` 里的「应用补丁」段已整段删除，
> 不再自动装补丁。唯一在用的补丁已独立到 `assets\独立补丁\前端缓存no-store\`
> （含操作指南与给 agent 的提示词）。下面内容保留作历史参考，**不要再按它操作**。
`assets\补丁管理\` 是本技能携带的 **DSH 补丁自动载入清单**：
| 文件 | 作用 |
|---|---|
| `自动载入清单-manifest.json` | 自动载入清单：登记所有需要打进 DSH 的补丁（`enabled` 标记挂起/启用） |
| `补丁引擎-应用还原检查.ps1` | 补丁引擎：应用 / 还原 / 检查（`-Restore` / `-CheckOnly`） |
| `补丁引擎-公共库.ps1` | 公共库：带备份的文件安装、按清单还原 |

**⚠ 重要教训（2026-08-23 事故）**：补丁载荷是**绑定 DSH 版本的**（档案柜 v1 基于
0.1.0-rc.7）。DSH 升级后**绝不能直接重跑 setup.ps1 应用旧补丁**——会把旧版载荷覆盖到
新版包上（profile 的 @deepseek-ai 包是 junction 指向源树 apps/cli/node_modules，
覆盖即改坏源树构建产物），造成前端渲染故障（其他会话历史加载失败、消息无反馈）但
RPC 直连正常，极难排查。
**处理**：升级 DSH 后，若补丁与新版不兼容 → 在 manifest 里置 `enabled=false` 挂起，
并从 npm 官方源拉取对应版本纯净包恢复被覆盖文件（或 pnpm build 全量重建），再重启
dsh web。**补丁引擎已实现兼容性校验**（`补丁引擎-应用还原检查.ps1` 读取当前 DSH
package.json 版本，与清单 `compatibleDsh` 字段比对，不在列表即跳过并提醒先升级 DSH）——
补丁的 `version` 字段仅作显示，不参与校验。还原模式按「是否已应用」（备份清单存在）
判断，不受 `enabled` 影响，挂起后仍可一键还原。
| `补丁管理说明-README.md` | 清单与补丁格式说明 |
| `重打全部补丁.bat` / `还原全部补丁.bat` | 一键应用 / 一键还原清单中全部补丁 |
`setup.ps1` 在安装末尾自动按清单应用补丁。**DSH 重装 / 升级导致补丁失效后，重跑
`setup.ps1`（或 `补丁引擎-应用还原检查.ps1`）即可恢复**；
`补丁引擎-应用还原检查.ps1 -Restore` 可一键还原官方原状。
- 补丁备份默认在 `$DSH_HOME\patches-backup\<补丁id>\`（可用 `-BackupRoot` 覆盖）；
- **幂等与验证**：`setup.ps1` / `重打全部补丁.bat` 均可重复运行，不会重复打或损坏（已应用自动跳过）；验证补丁是否生效：跑 `补丁引擎-应用还原检查.ps1 -CheckOnly`（列计划即已应用清单）；还原用 `补丁引擎-应用还原检查.ps1 -Restore`。注意：还原成功后备份清单会被清空为 `{}` 且备份目录会被删除，故「目录存在=已应用」不再可靠；引擎的「是否已应用」判断以三条件齐备为准——**备份目录存在 + `backup-manifest.json` 存在 + 清单解析后非空（含备份条目）**。
- 每个补丁一个独立子目录 `补丁管理\补丁NN-功能名\`，含安装脚本 / 还原脚本 / `载荷文件\`
  （`id` 决定备份目录名保持稳定，`dir` 决定源码子目录名可随意起名，详见目录内 README）；
- **清单控制安装**：`自动载入清单-manifest.json` 里每个补丁的 `enabled` 字段决定是否随 `setup.ps1` / `重打全部补丁.bat` 自动安装：`true` = 安装；`false` = **挂起（跳过不装）**。需要临时停用某补丁（如与新版本冲突）时置 `false` 即可，改回 `true` 再跑一次即恢复；不必删除补丁目录。
- **新增补丁三步**：① 写载荷与安装/还原脚本 → ② 在 `自动载入清单-manifest.json` 登记（`enabled: true`）→ ③ 同步 `assets\补丁管理\` 并重打包 zip（见下）。
- 已知补丁登记（历史台账，**已全部退役**：补丁01/03 于 2026-10-31 移除，补丁02 于 2026-11-06 独立到 `assets\独立补丁\前端缓存no-store\`）：
  - `补丁02-前端缓存no-store`（id: `dsh-frontend-static-no-store`，适配 **0.2.1-rc.2**；**2026-11-06 已独立到 `assets\独立补丁\前端缓存no-store\`，不再由任何自动流程安装**；历史上在 0.2.1-rc.5 上未生效——升级换包已覆盖 install 载荷（实测 `lib\index.js` 3899 B 与备份原版 SHA256 相同、不含 no-store/immutable），且 `compatibleDsh` 不含 rc.5，引擎会跳过；属待适配项）：
    `packages/host/frontend-static` 的静态资源缓存策略——渲染的 index `no-store`、文件名带内容哈希的资源
    `public, max-age=31536000, immutable`、其余文件 `no-cache` + ETag（命中 `if-none-match` 回 304）。
    根治「升级/前端重建后浏览器复用旧 index.html → 白屏 / `client-modules: boot manifest batches must be an array`」。
    载荷只覆盖真正运行的构建产物 `@deepseek-ai\dsh-host-frontend-static\lib\index.js`
    （不覆盖 tracked 的 TS 源码，避免占用 git 工作树、阻碍升级第一步 `git pull`）。
  - `补丁01-档案柜v1-归档升级版`（id: `dsh-recycle-bin-v1`，适配 0.1.1-rc.2，2026-08-23，**已废弃：2026-10-31 从清单与目录移除，仅 patches-backup 留 stale 副本**）：
    会话 ⋯ 菜单「移入档案柜」+ 侧边栏底部「档案柜」分区 + 恢复。**与 0.1.5-rc.1 不兼容**：5 个目标包中
    `dsh-client-runtime` / `dsh-host-apiproxy` 已被上游删除（profile 里是悬空 junction，引擎会直接抛错）；
    载荷是旧构建整文件覆盖；「归档」半边已由上游原生实现。**不要启用**。
  - `补丁03-档案柜v2-恢复半边`（id: `dsh-recycle-bin-restore-v2`，适配 **0.1.5-rc.1**，2026-09-12，**已废弃：2026-10-31 从清单与目录移除，仅 patches-backup 留 stale 副本**）：
    上游已原生提供「归档」（⋯ 菜单「归档会话」+ RPC `workspace/archiveSession` + `archivedSessionIds`），本补丁只补缺失的另一半——
    侧边栏底部「档案柜」入口（`sidebar.footer.action` 列表槽）+ 已归档会话列表 + 一键恢复；新增服务端 Remote
    `workspace/restoreSession`（幂等，复用既有 `{type:'archived'}` 增量广播）。需求与设计见
    `docs\补丁-档案柜v2-需求与设计-0.1.5-rc.1.md`；源码增量留档原本在补丁目录内，已于 2026-10-31 随目录一同删除
    （该补丁已废弃，不再需要重适配）。

  - 适配方法（新增/改造补丁时复用）：对每个目标文件 diff「上游原状 vs 打补丁后」提取增量，再按新版上下文套用；
    或（更稳）在源树改 TS → `pnpm run build:lib:host` / `build:lib:client` → 取构建产物做载荷；
    **首次安装前先 `git checkout` 回上游源码并重建**，使引擎备份里存的是真正的原版文件；
    装好后再把源树恢复干净（源码增量留档到补丁目录），避免阻挡下次 `git pull`。

## DSH 升级 + 补丁安全流程（用户规定的固定流程，2026-08-23 起执行）

**任何 DSH 版本升级（含托盘升级按钮触发的 AI 升级），严格按以下顺序执行；未经用户
明确确认，不得应用不兼容补丁：**

1. **更新 DSH**：源码树安装 → 进入源树 `git pull` → `pnpm install` → `pnpm build`；
   PATH/npm 安装 → `npm update -g @deepseek-ai/dsh`。
2. **更新一键启动**：重跑 setup.ps1。补丁体系已于 2026-11-06 退役，`setup.ps1` 不再应用任何补丁，
   无需再改 manifest。若确实要装 `assets\独立补丁\` 里的补丁，另行按该目录的 `操作指南.md` 处理。
3. **分析一键启动技能及其自带脚本**（分析对象：dsh-launcher 本体 + setup.ps1 +
   模板 + `assets\配套技能\` 内全部脚本技能 zip-archive-ops / batch-files /
   charset-pitfalls / skill-install-ops + 补丁清单；对照新版本实际内容逐个分析）：
   - **先安装兼容的**：与新版兼容、可直接安装且不破坏新版本的 → 安装（应用后重启
     dsh web 验证）；
   - **不兼容的挂起并给分析报告**：保持挂起，输出分析报告（目的 / 不兼容原因 /
     影响范围 / 建议：修改 / 按原功能彻底重写 / 暂时搁置）；
   - **铁律：若一键启动本身（dsh-launcher / setup.ps1）不兼容**，则其他自带脚本
     **无论是否兼容一律不安装**，直接给分析报告。
4. **用户决策**：由用户选择修改、重写或搁置；未经用户同意不得启用不兼容项。
5. 重启 dsh web，验证：版本号、各会话历史可加载、消息有反馈。

**前车之鉴（2026-08-23）**：旧补丁载荷直接覆盖新版包（profile 的 @deepseek-ai 包是
junction 指向源树构建产物），导致前端渲染故障且 RPC 直连正常，极难排查。详见
「补丁自动载入清单」一节的教训。

## 启动链铁律（2026-11-01 用户规定，优先级高于本文件其余流程约束）

任何**启动链**改动——`DSH-tray.ps1` 及其模板片段 / `setup.ps1` / 计划任务与自启动项 /
客户端插件注册（profile 的 `package.json`、`cordis.patch.yml`）/ 生成器里的 here-string /
一键入口脚本——**合入前必须过独立对抗性审查**（载入 `adversarial-review`，用独立子审查者，
只喂对象与事实、不喂作者推理；禁止用作者上下文自审），且**必须同时留下「故障时不需要 AI 在场」
的自救手段**。

理由（用户原话的意思）：用户只有 DSH 界面这一个沟通渠道；启动链一坏，用户就没法把故障告诉
维护者，只能找外部手段救。所以「能不能启动」与「坏了能不能自己救」两条都要过。

通过判据沿用默认：**阻断清零 ∧ 严重清零**。交付时三件事缺一不可：
① 审查结论（阻断/严重各几条、谁审的）；② 自救入口（当前为 `D:\DSHS\DSH-rescue.cmd`，
桌面快捷方式「DSH 紧急恢复」；功能：清残留 → 直启 dsh web → 失败则 `dsh rescue --from-default-profile web`）；
③ 回滚点（秒级时间戳备份路径 + 还原命令）。

已知两次真实事故（写进铁律的原因，勿重犯）：helper 生成时 `$Rec` 未转义 → 语法错误使硬重启
后无人拉起托盘；客户端插件写成裸 ESM 而非 `window.__ModuleLoader__.load({id,factory})` →
界面报 `Failed to load plugins`。
**必须按用户的编程范式落地（2026-11-01 用户追加）**：修改启动器（本技能中任何会进入启动路径的
文件——`setup.ps1`、`assets\tmpl\` 模板片段、`DSH-tray.ps1` 生成物、计划任务与入口脚本、
profile 的 `package.json` / `cordis.patch.yml`）时，**无论是否当次对话**，一律按 `guide-dev`
的编程范式执行（判档 → 设计先落纸 → 实现 → 独立对抗审查 → 验证），并且**必须"修复无误后再运行"**：
语法解析、临时目录生成、`-CheckOnly` 冒烟这些验证通过之前，不得把改动生成到真实安装目录，
不得重启托盘或服务。

**可逆留痕（同一规定）**：每次改动都要留下可回滚的痕迹——改前用秒级时间戳备份（放对象同级的
`_bak\` 或 `_backup\`，格式 `原名.bak-yyyyMMdd-HHmmss`）、写明回滚命令、并在
`$DSH_HOME/AGENTS-changelog.md` 记一条变更记录。三样缺一视同未完成，不得上机。
### PowerShell 运行时分工（2026-11-06 用户规定，硬约束）

> **Windows PowerShell 5.1 只允许出现在启动链**；其他任何脚本一律用 PowerShell 7。

- **按 5.1 写、按 5.1 验**的对象：`DSH-tray.ps1` 及模板片段、`setup.ps1`、启动器生成的 `.bat/.cmd` 里调起的脚本、计划任务与自启动项。
- **按 7 写**的对象：agent 调用的命令行、分析/临时脚本、非启动链工具。
- **验收口径**：启动链脚本改完，`powershell.exe`（5.1）与 `pwsh`（7）**两边都做语法解析**；行为验证优先在 5.1 上跑（那才是真实宿主）。
- **理由**：5.1 由操作系统保证存在；PS7 是自己装的，升级/卸载 PS7 不能影响"能否启动"。
- **已知 5.1 专有坑**：`Start-Process -PassThru -RedirectStandard*` 后 `Wait-Process` 再读 `$p.ExitCode` 恒为空串（PS7 正常）；先摸 `$p.Handle` 可读回。
- **落点说明**：本条是执行层硬约束，**权威副本在本文件**；`U:\AImd\【我的系统环境】\7.智能体工具与环境指南.md` §13 仅为冷归档（只读参考，不参与执行）。
## 调试纪律（铁律，2026-08-25 事故教训）

**托盘/启动器脚本调试，绝不在运行中的生成物上直接编辑。** 事故复盘：调试双击引导时，
AI 直接往 `D:\DSHS\DSH-tray.ps1`（正在运行的生成物）注入诊断代码 + 反复 Stop-Process
重启托盘，某次生成版本启动即异常 → 托盘起不来，快捷方式也指向同一坏文件 → 「托盘没了、
双击快捷方式也启动不了」差点全盘瘫痪。恢复靠 Z 盘已知良包覆盖 + 就地安装。

**正确流程（必须遵守）**：
1. **只改模板片段**（`assets\tmpl\parts\*.ps1` / `mode-*.json`），不改生成物；setup.ps1 会按模式拼装生成最终托盘脚本；
2. 用 setup.ps1 或按渲染逻辑**重新生成** DSH-tray.ps1；
3. 重新生成后**先做语法验证**（`[scriptblock]::Create((Get-Content -Raw))`）再重启托盘；
4. 重启托盘前**先备份当前良版生成物**（如复制 DSH-tray.ps1.bak）；
5. 托盘进程用托盘右键「重启 DSH」或结束进程后重新 `Start-Process`，避免注入式修改运行中脚本；
6. 修改前**先备份当前版本良包**（git 历史与 `releases\<版本>\` 目录即天然留档；本地改动未提交前先单独复制一份 zip/源树备份），防止覆盖坏包；
7. 临时诊断代码**只能放模板或单独测试脚本**，绝不写进生成物后长期残留。

**判断良包标准**：归档包（`releases\<版本>\` 内的 zip）`testzip()` 无损坏、模板含完整功能（Open-DshApp/pwaGuideShown/
IsZoomed/双击 Open-Url）、setup.ps1 BOM 合规、内嵌配套版本与配套目录一致。

## 发布前检查清单（本地改动 → 上传，用户规定 2026-08-30）

任何对技能（模板 / assets 脚本 / 文档 / 版本号）的改动，**上传 GitHub 之前**严格按此顺序，缺一不可：

1. **改动**：只改模板片段 / assets 脚本 / 文档（遵守「调试纪律」：只改模板，不直接改运行中的生成物）。
2. **跑 setup.ps1 生成**（干净 PATH 下）：
   `powershell -NoProfile -ExecutionPolicy Bypass -File "<技能>\assets\setup.ps1" -InstallDir <安装目录>`
   它会重新生成安装目录脚本，并更新 `launcher.version`。
3. **实际检查（人工确认）**：
   - 安装目录生成物确实含新改动（`DSH-tray.ps1` / `dsh-sync.ps1` / `launcher.version`）；
   - 语法解析 OK（`[scriptblock]::Create`）；
   - 重启托盘，右键菜单 / 功能实际验证 OK。
4. **确认 OK 后才 bump + 同步**：
   - bump `_meta.json` 的 `version` + `publishedAt`；
   - SKILL.md 兼容性表登记一行；
   - 点托盘第四行「双向同步」（或 CLI 跑 dsh-sync.ps1）上传。
5. **同步完成后重启服务 + web 界面**（让新脚本 / 新版本号在运行中生效）：
   - 托盘右键「重启 DSH」，或「退出并停止 DSH」后双击桌面「启动DSH」；
   - 验证托盘版本号、菜单功能与最新版一致。

**铁律**：setup（生成 + 检查）与同步（分发）是两个独立步骤，**绝不能跳过 setup/检查直接上传**
（2026-08-30 教训：bump 后漏跑 setup 导致安装目录 `launcher.version` 滞后、托盘版本显示旧值）。
## 已装机器如何升级

**更新后的必做步骤（不重跑 = 启动脚本未刷新）：**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1" -InstallDir "<安装目录>" -NoShortcut
```

`setup.ps1` 一次完成：① 重新生成启动脚本；② 安装 `assets\配套技能\` 内的配套技能。补丁体系已于 2026-11-06 退役，不再应用补丁；唯一的补丁在 `assets\独立补丁\前端缓存no-store\`，按需人工处理。

**升级/打补丁/换前端插件后必须硬刷新浏览器（Ctrl+F5）重新加载 http://127.0.0.1:3080**：
DSH 前端是 client-plugin 图（index.html 的 `__DSH_BOOT__` 指向带 rev 哈希的插件 JS），
服务端重启只是第一步；浏览器缓存旧页面 = 继续跑旧插件，界面（如侧边栏左上角品牌名
`sidebar.brand.name` 槽位）显示旧内容或兜底文字 "DSH Local Build"（官方字标由
`dsh-client-ui-brand-official` 插件提供，仅 official 构建注册）。刷新后插件按新 rev
重载才正确。给其他机器升级时的标准说法与同类情况清单见
`assets\升级后重新渲染-标准说法.md`。

GitHub 仓库（`moonwellxh/DSH-Launcher`，main 分支）是各台机器修改的合集；仓库内**解压源树 `dsh-launcher/` 为维护对象**，
zip 安装包**集中归档在 `releases\<版本>\` 目录**（历史版本按目录留档）。已在用的机器按下面规则对齐：

| 本次改了什么 | 已装机器要做的 |
|---|---|
| 只改 `SKILL.md` / `_meta.json` / `_icon.png` | 重装技能：解压 zip 覆盖 `~/.agents/skills\dsh-launcher` 即可 |
| 改了 setup.ps1 或 `assets\tmpl\` 模板（`parts\*.ps1` / `mode-*.json`） | 重装技能 + 重跑一次 setup.ps1（重新生成安装目录里的启动脚本） |
| 改了 `assets\独立补丁\*` | 重装技能即可（独立补丁不参与任何自动流程） |
| 想一键完成上面任意一项 | 双击 `assets\更新安装.cmd`（新 zip 放 assets 目录或拖入），自动「覆盖技能 + 重跑 setup.ps1」 |

原因：真正运行的是 `setup.ps1` 生成的脚本（`dsh.cmd`、`DSH-tray.ps1`、`启动DSH.bat` 等），
光更新技能不会刷新这些生成物；`setup.ps1` 幂等，可安全重复执行。

合并多台机器的修改时：以 GitHub 仓库为准逐文件比对，凡「GitHub 有而本地无」或「两边不同」的文件，
以 GitHub 为准并入本地，再 git commit + push 回 GitHub（托盘右键第三行「启动托盘版本」可自动完成双向同步）。

## 兼容性列表（适配关系，修改技能/补丁时必须同步维护）

| 组件 | 版本 | 兼容 DSH 版本 | 说明 |
|---|---|---|---|
| dsh-launcher（一键启动本体） | 1.2.13 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **双向同步不再抹本地提交**（2026-11-08 实测事故 + 十轮审查）：事故经过——点托盘「双向同步」，脚本在弹方向确认框**之前**就执行 `git reset --hard origin/main`，把 3 个未推送的本地提交抹掉；用户随后点"取消"，提示还写"未做任何更改"。修复：① 对齐前先 `Save-SyncLocalCommits`：数 `origin/<branch>..HEAD`，非 0（含取不到，按 -1）就先 `git branch local-backup-<秒级时间戳> HEAD` 并**校验退出码**，失败即 `throw` 中止，绝不"先 reset 再说"；② `reset --hard` 之后补 `git clean -fd`（不带 `-x`，保留 `.gitignore` 忽略项）清上一轮未跟踪残留，失败时界面告警（不再只写 TEMP 日志）；③ 目录层保护：需要删/重建缓存时改为 `Move-Item` 到 `<cache>.bak-<秒级时间戳>`，备份失败一律 `throw`，**取消**了原来"备份失败就 `Remove-Item -Recurse`"的回退删除；④ 备份提示写 `%TEMP%\dsh-sync.log`，取消提示如实点名备份分支；⑤ 修两处**能解析但运行期必炸**的写法：`(if …)` 当表达式（两引擎都报 CommandNotFoundException）、PS7 下 `$PSHome\powershell.exe` 不存在（回退到系统 Windows PowerShell）；⑥ `git branch` 包 try/catch、setup 调用局部降级 `ErrorActionPreference`（5.1 下 stderr 会误报"同步失败"）。审查：本地 GLM + 外包 CodeBuddy/CodeBuddy-CN 共十轮，R10 双通道均「可执行，0 阻断/0 严重」。遗留（不阻断）：`Get-CurrentDshVersion` 里两处 `--version 2>&1` 未局部降级（会静默丢版本、跳过兼容性守卫）；`.bak` 目录与备份分支无清理策略；clean 失败告警文案只提"上传"。回滚：`assets\_bak\dsh-sync.ps1.bak5-*`。 |
| dsh-launcher（一键启动本体） | 1.2.12 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **裸版本按 npm x-range 语义**（2026-11-08，第 5 轮审查）：`engines.node` 里不带运算符的裸版本，原来一律当精确版本（`"24"` → 仅 `24.0.0`），npm 语义应是 `"24"` = `>=24.0.0 <25.0.0`、`"24.9"` = `>=24.9.0 <24.10.0`、`"24.9.0"` 才是精确。后果：装了 24.20.0 的机器会被 `"24"` 误判为不满足而拒绝启动。已按正则捕获分组分三档生成上界；与既有 `24.x`/`24.*` 通配分支语义一致且互斥触发，AND 求交与 `\|\|` 分支不受影响。验证：双引擎 `PARSE-OK tokens=7222`；单测 9/9（`24` 收 24.20.0 拒 25.0.0；`24.9` 收 24.9.5 拒 24.10.0；`24.9.0` 收 24.9.0 拒 24.9.1）。审查：本地 GLM + 外包 CodeBuddy 均判「可执行，0 阻断/0 严重」（GLM 另做 27 组内存模拟、CodeBuddy 补测边界）。遗留（不阻断）：`>`/`<=` 对部分版本仍非 npm 语义（`>24` 应为 `>=25.0.0`）、通配分支与 default 算法重复、提示文案只报下界。回滚：`assets\_bak\setup.ps1.bak-*`。 |
| dsh-launcher（一键启动本体） | 1.2.11 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **动态就绪等待 + 开早问题闭环**（2026-11-08，四轮审查）：① 新增 `Get-DshReadyTimeoutSec` / `Add-DshReadySample`：每次真实冷启记"启动→就绪"耗时（最近 20 条），去首尾各 10% 极端值取 P80、乘 1.3，夹在 `[90,300]`；样本 <3 条取 `max(120, 已有样本 P80×1.3)`；默认 120 秒（实测冷启动 79 秒）。② 超时判定由固定 30 秒改为上面的动态值。③ **采样双重门**：只有"本进程真拉起服务"（`startedByMe`）且"非超时分支"（`readyFromTimeout`）才记样本，避免附着启动的 1-2 秒假样本与"把阈值当样本"的棘轮下压。④ 看护重启复位 `readyTicks` / `readyFromTimeout` / `startedByMe`（此前重启后第一个 tick 就满足超时→1.4 秒开页面）。⑤ 提权交接路径由"端口有监听即开"改为"等令牌被服务接受"，**墙钟**截止、上限 `max(120, 动态阈值)`，超时先留 WARN + 提示再开（原为 240 次×250ms≈按次数计时，实测会拖到 200 秒以上）。⑥ 样本文件原子写（临时文件 + 替换），失败记 WARN。回归项：打开页面回退为 `Open-Url $webUrl`（其内部已有 `Get-DshOpenUrl` 令牌探测 + `Open-DshApp` PWA 优先）；修 `Find-DshSourceTree` 递归回退返回数组/尾随空格。审查：本地 GLM + 外包 CodeBuddy 四轮，R4 双通道均判「可执行，0 阻断/0 严重」。遗留（不阻断）：单条 <30 秒的极短样本未过滤（可选一行加固）、自适应采样只在带 `-OpenBrowser` 的入口产生。回滚：`assets\_bak\setup.ps1.bak-*`、`assets\tmpl\parts\_bak\*.bak5-*`。 |
| dsh-launcher（一键启动本体） | 1.2.10 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **修既有严重 + 解析器收尾**（2026-11-08，第三/四轮审查）：① `Find-DshSourceTree` 递归回退里 `return $_.FullName` 写在 `ForEach-Object` 中——只结束当次迭代、路径混进输出流，函数返回 `Object[]`，下游 `[string]` 化后成"路径 + 尾随空格"，导致门槛读不到 `package.json`（静默回落）且 `__DSH_ROOT__` 渲染成无效路径；改为"命中存 `$hit`、两层 `break`、循环后返回"，实测返回单值且无尾随空格。② `X.Y.x` 通配改为与其它条件求交（原先覆盖，`>=24.9.0 24.x` 与 `24.x >=24.9.0` 结果不同）。③ 运算符后空格（`>= 24.9.0`）先归一。④ 非 `.exe` 包装器（`.cmd/.bat/.ps1`）统一进拒绝清单。⑤ `$found` 按路径去重。验证：双引擎 `PARSE-OK tokens=7133`；解析器单测 15/15；`Find-DshSourceTree` 伪造用户目录实测单值。审查：GLM-5.3-Flash 复审判「可执行，0 阻断/0 严重」，并确认上一轮 S1/S2/S3 与既有严重全部闭合；另留两条**既有的建议级**问题（递归根列表过滤、裸主版本解析），不构成放行障碍，留待后续。回滚：`assets\_bak\setup.ps1.bak-*`。 |
| dsh-launcher（一键启动本体） | 1.2.9 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **第三轮审查 3 条严重收口**（2026-11-08）：① S1 只有上界的条件（`<=22.0.0` / `<24.0.0`）此前因 `if ($ok -and $lo)` 被整条丢弃 → 变成"无区间"反判 24.9.0 通过；改为下界缺省 `0.0.0`，`*` 不再覆盖已有上界。② S2 `.exe` 硬判据原来只在"版本不达标"分支里，达标但为 `.cmd` 的候选（唯一入口 `KIMI_DESKTOP_RUNTIME_NODE`）会被写进启动器；改为在候选收集阶段前置拒绝非 `.exe` 并记拒绝原因，版本号解析异常也不再静默丢弃。③ S3 path 模式告警原来用"全部候选里最高版本"判定，而 `dsh.cmd` 实际用 PATH 上第一个合格 `.exe`，会漏报/报错文件名；抽出 `Get-PathNodeExe`（与 `Find-Node` ① 同一套过滤）供告警使用。另：单分支来源标签区分 `>=`/`<=`/`^~`/`||`；全文件行尾统一 CRLF（原来混有 18 处 LF-only）。验证：双引擎 `PARSE-OK tokens=7028`；单测 18/18（含 `<=22.0.0` 拒 24.9、`<24.0.0` 拒 24.0、`>=24.9.0 *` 与 `* >=24.9.0` 顺序无关、`^22.19.0 \|\| >=24` 拒 23.11）；真机 `-CheckOnly` exit 0、门槛文件打印正常。回滚：`assets\_bak\setup.ps1.bak-*`。 |
| dsh-launcher（一键启动本体） | 1.2.8 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **审查遗留项收口**（2026-11-08，按独立审查的 M1–M5）：① 解析器重写为「按条件求交 + 分支并集」：支持 `>=`/`>`/`<=`/`<`/`^`/`~`/裸版本、空格 AND、`\|\|` OR、`X.Y.x`/`*` 通配；`^0.x` 上界按 0.(Y+1).0 处理；无法识别的条件记入 `Unparsed` 并在 `-CheckOnly` 与来源里标注，不静默放过。② 老版 npm 包**没有 `engines` 字段**时，按已装版本给默认要求（`<0.2.2` 用 `^22.19.0 \|\| >=24`，否则 `>=24.9.0`），不再一律 24.9.0 误拒。③ 门槛来源记录命中的 `package.json` 路径并在 `-CheckOnly` 打出；path 模式告警改用 `Find-Node` 同一候选，不再另起一次 `Get-Command`。④ 托盘自动修复 helper 改为 `-PassThru` 并落 `<helper>.exit.txt` 记录 setup 退出码（此前 `-Wait` 丢弃退出码，新增的 exit 1 在该链路不可见）；模板改动**需下次跑 setup 才生成到托盘**。⑤ `-Force` 的「命令行可解析」改为硬判据：非 `.exe` 即便 `-Force` 也拒绝。验证：双引擎 `PARSE-OK tokens=6874`（setup）/`7089`（模板）；函数级单测 15/15（含 `>=24.9.0 <26` 拒 26、`^0.2.3` 拒 0.3、`~22.19` 拒 22.20、`24.x`/`*`、旧包默认拒 23.11）；真机 `-CheckOnly` 输出「找到 3 个可用 node，选用版本最高的 24.20.0」+ 门槛文件路径。回滚：`assets\_bak\setup.ps1.bak-*`、`assets\tmpl\parts\_bak\90-main.ps1.bak-*`。 |
| dsh-launcher（一键启动本体） | 1.2.7 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **版本判定移出 Find-Node + 门槛候选按模式隔离**（2026-11-08，独立审查第二轮 2 条严重）：① 原实现里 `Find-Node` 已用同一区间谓词筛过候选，导致后面"源码树提前报错"分支恒不成立、`-Force` 永远不可达（死代码）；改法：`Find-Node` 只判「可运行的 .exe + 版本号可解析」，收集全部候选并返回**版本最高**者，是否达标交给守卫判定——守卫因此可达，默认 `exit 1`、`-Force` 时打印 5 项校验与风险后继续。② 门槛候选改为**按模式隔离**：`$dshPath` 非空时只认它旁边的 npm 包，绝不回退读源码树 engines（两者版本可能不同，会让 path 模式判错门槛）；命中文件记入 `Source` 对应字段，便于归因。验证：双引擎 `PARSE-OK tokens=6016`；真机 `-CheckOnly` 输出「找到 3 个可用 node，选用版本最高的 24.20.0」、mode=path、要求来源 package.json(>=)。回滚：`assets\_bak\setup.ps1.bak-20261108-110*`。 |
| dsh-launcher（一键启动本体） | 1.2.6 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **Node 门槛：源码树模式提前校验 + 区间判定**（2026-11-08，独立审查指出 2 条严重后修复）：① 门槛改为**逐分支区间**判定——`>=X` → `[X,∞)`、`^X.Y.Z` → `[X.Y.Z,(X+1).0.0)`、`~X.Y.Z` → `[X.Y.Z,X.(Y+1).0)`，版本落在**任一**分支内才通过；旧实现只取最低下界，会把 Node 23.x 在旧 DSH（`^22.19.0 \|\| >=24`）上误放行（23.x 两分支都不属于）；② 门槛来源按模式取：path 模式读 PATH 上 dsh 旁的 `@deepseek-ai/dsh/package.json`，源码树模式读 `<tree>\apps\cli\package.json`（再退 `<tree>\package.json`），某候选无 `engines` 则继续下一个，全无才回落 24.9.0（旧实现只传 `$dshPath`，源码树模式恒回落 → 在唯一"按门槛挑 node"的模式里失效）；③ **源码树模式提前报错**：选中的 node 不落在区间内 → 报错 + 建议退出 + `exit 1`，**不做任何写入**；加 `-Force` 则先重新校验（打印 5 项校验与风险）再继续；④ 拒绝清单不再记录"标准目录本来就不存在"的路径（只记存在但不可用），path 模式找不到 node 也会提示；⑤ 退出码文档化：0=可安装 / 1=装不了 / 2=`-CheckOnly` 探测不到 mode。验证：双引擎 `PARSE-OK tokens=5990`；单元测试 10/10 PASS（含 23.11.1 在 `^22.19 \|\| >=24` 下拒绝、`~22.19.0` 下 22.20.0 拒绝）；真机 `-CheckOnly` 要求来源正确。审查：本地 deepseek-flash 判"需修订"（0 阻断/2 严重，即上述①②），已修。回滚：`assets\_bak\setup.ps1.bak-20261108-104529`（`C502CB79`）。 |
| dsh-launcher（一键启动本体） | 1.2.5 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **不再接受 node.cmd 作为 Node 来源**（2026-11-08，启动链审查发现）：托盘用 `Start-Process -RedirectStandardOutput/-RedirectStandardError` 启动 web，该 API 只能启动可执行映像，`.cmd` 必抛"不是有效的 Win32 应用程序"；而安装期验证走 `cmd /c`，`.tmpl` 里没有 `call`，批处理间转移控制 + 退出码照常 →「验证通过、托盘起不来」（历史"反复启动失败"同源）。改法：删掉 ④ `.cmd` 兜底，凡 `.cmd` 候选一律记入拒绝清单；`Test-UsableNode` 的每类失败（不存在／版本低／输出不可解析／执行异常）都记原因并去重，错误文案穷尽列出「以下候选被跳过（含原因）」；`-CheckOnly` 输出同一清单，`mode` 为空时退出码改 **2**。验证：双引擎 `PARSE-OK tokens=4826`；真机 `-CheckOnly` exit 0 / mode=path；隔离环境（唯一候选为伪造 `node.cmd`）实跑 → 输出含 `.cmd 包装器（…）` 且 exit 1；顺带暴露本机 `.workbuddy` 下 node 22.22.2 会被明确标"版本低于 24.9.0"。审查：deepseek-flash（0 阻断 / 3 严重，均已按此修）；CodeBuddy 通道当日要求 provider+model 成对、未能送审。回滚：`assets\_bak\setup.ps1.bak-20261108-100558`（`FD35D71C`）。 |
| dsh-launcher（一键启动本体） | 1.2.4 | 0.2.2-rc.1（并保留 0.2.1-rc.2、0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **Node 门槛对齐 DSH 0.2.2-rc.1**（2026-11-08）：`engines.node` 改为 `>=24.9.0`（旧版 `^22.19.0 || >=24`），`Find-Node` 的 `$minVer` 22.19.0→24.9.0、判定简化为 `$ver -ge $minVer`，④ `node.cmd` 兜底也纳入版本校验（不达标返回 `$null`）；错误提示与 `环境要求-安装指南.md` 同步改为「Node.js 24.9 及以上」（原「LTS」在 22.x 仍是 LTS 时会误导）。审查：本地 GLM 子代理通道当日不可用，改 deepseek-flash 补位 + 外包 CodeBuddy 双轨；CodeBuddy 三条严重（LTS 文案、分发副本未同步、④ 无版本校验）已全修。验证：双引擎 `PARSE-OK tokens=4721`、`-CheckOnly` exit 0 mode=path、判定表 22.19/22.20.5/23.11.1/24.0.0/24.8.9 拒绝、24.9.0/24.20.0/25.0.0 接受；两份分发副本已同步 40,613 B / `FD35D71C6665A067`，**尚未 git commit/push**。回滚：`assets\_bak\setup.ps1.bak-20261108-091900`（`EF422A23`）。 |
| dsh-launcher（一键启动本体） | 1.2.3 | 0.2.1-rc.2（并保留 0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **托盘取令牌加固**（2026-11-06，用户报障「托盘右键打不开 superagent」，提示「读不到启动令牌」）：`Get-SuperagentUrl` 原来按 mtime 扫「最新 5 个」`dsh-superagent-superagent-*.log`，任何更新的 0 字节日志（中断的启动、名字相近的别的 profile）都会把真正的启动日志挤出窗口。改为：① 整名匹配 `^dsh-superagent-superagent-\d{8}-\d{6}-\d+\.log$`；② 按文件名（内嵌启动时刻）倒序，而不是 mtime（实测 `…-163641-…log` 的 mtime 是 17:06）；③ 只看最近一次启动，读不到或没有令牌一律返回空串，不拿上一次启动的旧令牌去撞 401。审查：本地 GLM-5.3-Flash + 外包 CodeBuddy 双轨；CodeBuddy 指出首版 `catch { continue }` 会退回过期令牌，已据此改为只读最近一次。验证：函数级 8 项在 PowerShell 7 与托盘宿主 PS 5.1 双跑全过（含「同一合成目录下旧实现返回空、新实现取到 token」的对照）；真实 `.artifacts` 取到的 URL 返回 303；重新生成的 `DSH-tray.ps1` 与现场只差 `Get-SuperagentUrl` 一个 hunk；切换后托盘 pid 20164 ELEVATED、dsh web 未动。回滚：`D:\DSHS\_bak\DSH-tray.ps1.bak-20261106-012652`（还原后重启托盘）。 |
| dsh-launcher（一键启动本体） | 1.2.2 | 0.2.1-rc.2（并保留 0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **托盘右键新增「打开 superagent 面板 (3082)」**（2026-11-05，用户要求只加这一项）：① `parts\00-header.ps1` 加 `$saUrl` / `$saLogDir`；② `parts\10-utils.ps1` 加 `Get-SuperagentUrl`（取最新 5 个 `.artifacts\dsh-superagent-superagent-*.log`、共享读打开、取文件内最后一个令牌；取不到返回空串，不静默回退裸 URL——3082 裸 URL 无令牌实测 401）；③ `parts\90-main.ps1` 菜单项排在「打开 Web UI」之后，handler 先探 3082 监听、再取令牌才 Open-Url。审查：本地 GLM-5.3-Flash + 外包 CodeBuddy 双送对拍；首轮生成的「回退裸 URL 静默 401」已修。验证：三片段回退原件→重生成 108,499 B 与改前生成物逐字节相等；改后→110,613 B 与候选逐字节相等；source 模式产物 PARSE-OK。**待推送 GitHub**（本地提交 ec8c7dd，`_meta` 1.2.1→1.2.2） |
| dsh-launcher（一键启动本体） | 1.1.99 | 0.2.1-rc.2（并保留 0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **启动链两轮对抗审查后的加固**（2026-11-01，本地 GLM-5.3-Flash + 外包 CodeBuddy 双份审查）：① 互斥锁：首次 `WaitOne` 加 try/catch，`AbandonedMutexException` 按「已拿到锁」处理（上一版误判为忙，导致"已有托盘时再双击"杀掉旧托盘后自己退出）；② 交接判据重做：等待者写 `.dsh-handoff.<PID>.lock`，被任务拉起且已提权的托盘在 `$notify.Visible=$true` 之后写 `dsh-tray.ready`（内含 pid），等待者只在「自己标记消失 ∧ ready 新鲜 ∧ ready 里的 pid 存活」时 exit 0，超时 20 秒清理后降级启动；清理动作移到抢到锁之后，写完 ready 再清一次迟到标记；③ `schtasks` 加 `Wait-Process -Timeout 20` 并在超时/抛错时回收进程；④ 锁到手后统一重探 `$listener`（覆盖三条拿锁路径）；⑤ 看护里的 `Start-DshServer` 也包 try/catch；⑥ 「退出并停止 DSH」先 `Test-DshListenerIdentity` 再 `taskkill`；⑦ 属主判定补 `bin.ts`、去掉裸 `dsh`，判不准时用启动令牌兜底（只认 302/303 且要求 `Set-Cookie` 含 `dsh-auth-`，禁用系统代理）；⑧ 启动失败文案区分「找不到 Node」与「启动抛异常」，文案压到 41 字避免被卡片裁切；⑨ 外来端口/启动失败时不再叠第二张气泡。补丁02 三档缓存头已在活服务验证（index `no-store`、内容寻址 `immutable`、普通静态 `no-cache`+ETag 且条件请求 304）。 |
| dsh-launcher（一键启动本体） | 1.1.98 | 0.2.1-rc.2（并保留 0.1.5-rc.1、0.1.1-rc.2、0.1.0-rc.7） | **补丁链适配 DSH 0.2.x 源码树布局**（2026-10-31，用户要求「都适配到现有版本」）：① 目标定位重写——0.2.x 的 profile 不再携带 `@deepseek-ai` 包（bundles 改由源码树提供），引擎原先只认 `~\.dsh\profiles\node_modules`，于是 setup 报「未找到 DSH web profile 的 node_modules」直接跳过。现改为：先试旧 profile 布局，再按 `@deepseek-ai\<包>\<剩余路径>` 到 `<DSH 根>\packages` 下按 package.json 的 `name` 反查包目录（本机扫到 342 个包）；根定位链 `-DshRoot` → `$env:DSH_ROOT` → `%USERPROFILE%\deepseek-harness` → `assets\install-dir.txt` → 托盘 `$dsRoot`；版本改读 `<根>\apps\cli\package.json`。② 修两处实现缺陷：`Split-Path -LiteralPath ... -Parent` 在 PS7 参数集不成立，异常被逐项 catch 吞掉导致包映射恒为空（改用 `[IO.Path]::GetDirectoryName`）；junction 检查里用 `return` 在脚本作用域直接退出整个引擎（改为条件表达式）。③ 补丁02（前端缓存 no-store）按 0.2.1-rc.2 重做：改 `packages\host\frontend-static\src\index.ts` → tsc → tsdown 取真实构建产物做载荷（5938 B，base 保持 0.2.x 的 `./`），源码增量留档 `源码增量-前端缓存no-store-0.2.1-rc.2.patch`，随后 `git checkout` 还原源码保持工作树干净；行为验证 7/7（index no-store / 内容寻址 immutable / 普通资源 no-cache+ETag / 命中 304 / 旧 ETag 仍 200 / 越界 403 / 缺失 404）。④ 档案柜补丁全部废弃：上游 0.2.x 已原生提供 `workspace/archiveSession` + `workspace/unarchiveSession` 与侧边栏功能，`补丁03` 置 `enabled=false` 并注明载荷是 0.1.5-rc.1 构建产物、禁止在 0.2.x 启用（用户 2026-10-31 确认放弃）。⑤ 引擎实际应用验证：备份目录存上游原件（无缓存逻辑）、`lib/index.js` 被换成载荷、`-CheckOnly` 与 setup.ps1 集成均正常。**待推送 GitHub**（本地已 bump `_meta.json` 至 1.1.98） |
| dsh-launcher（一键启动本体） | 1.1.97 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **修「托盘一显示就退出」+ 新增入口自动提权**（2026-10-31，用户报障）：① 根因：2026-10-26 把 `$notify.ShowBalloonTip(...)`（.NET 方法，括号式正确）换成 PowerShell 函数 `Show-DshNotice(...)` 时没改调用语法——PowerShell 把整张参数表当成**一个 Object[]** 交给第一个参数 `[int]$Timeout`，绑定失败抛终止性错误 → runspace 结束，托盘图标刚出现就消失、dsh web 留在后台。**34 处调用点全部踩中**，第一次弹卡片必死（就绪卡/「已在运行」卡）。修法在 `parts\10-utils.ps1`：第一个参数改收 `[object]`，体内按数组拆回四参并解析成整数 `$tms`（命名式调用仍兼容），气泡回退路径同步改用 `$tms`。② 新增入口提权守卫（`parts\90-main.ps1`，`$CheckOnly` 除外）：非管理员启动时改投「最高权限」计划任务 `DSH-Tray-Elevated` 后立即退出，使所有入口（桌面快捷方式 / 启动DSH-托盘.vbs / .cmd / 启动DSH.bat / 直接 `-File`）最终都落到提权托盘；`-OpenBrowser` 由**未提权 stub** 打开浏览器（避免管理员 Edge 与用户浏览器会话分家）；**任务未登记时照常以当前权限运行，不阻断启动**（新机器需手工登记或后续让 setup.ps1 自动建）。③ 本机配套：计划任务 `DSH-Tray-Elevated`（登录触发 / Highest / Interactive / IgnoreNew / 执行时限无 / 失败重启 3 次），并把 Startup 里的普通权限 `DSH-Tray-Autostart.lnk` 移走备份到 `_bak\`，避免两套自启动互抢。验证：`D:\DSHS` 前台跑 25 s 仍存活、stderr 空、`dsh-tray.log` 写出卡片行；`_tools\probe-elevated.ps1` 读令牌 TokenIsElevation 实测 `DSH-TRAY`/`DSH-WEB`=ELEVATED、`explorer`=NOT-elevated（对照有效性）；**用 Limited 计划任务模拟普通权限入口**：stub 退出码 0、最终托盘 ELEVATED、日志有对应记录；生成物 PARSE-OK、BOM 与 CRLF 保持、模板改动后 `fffd=0`。**待推送 GitHub**（本地已 bump `_meta.json` 至 1.1.97） |
| dsh-launcher（一键启动本体） | 1.1.96 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **「硬重启托盘」按对抗性审查结论重做**（2026-10-26，独立子审查者 DeepSeek/deepseek-flash 判阻断 0／严重 7）：① 加确认框（写明会中断当前 AI 回合、会重跑安装器）；② 结束前用 `Test-DshListenerIdentity` 校验 3080 属主（实测源码树模式命令行是 `node.exe apps/cli/lib/bin.js web --no-open`，不含 dsh 字样，故判定链加了 `bin.js` 与父进程托盘两条），判不准不杀；③ `CloseDshWindows` 只关 Edge 进程且标题不以 `- Microsoft Edge` 结尾的窗口（原来按标题 Contains 会关掉用户整个浏览器窗口、甚至记事本）；④ setup.ps1 先 `Test-Path`，技能被移动时只重启托盘不重渲染；⑤ helper 加 `-PassThru`+`Wait-Process -Timeout 300` 并回收退出码，结果写 `dsh-restart-status.txt`，新托盘启动时读并如实气泡（成功静默）；⑥ 外层 `catch {}` 改为弹气泡。验证：C# 类独立编译通过、身份判定 4 例（dsh web→True／msedge、不存在、0→False）、helper 三态（exit 3→failed／exit 0→done／缺失→missing）均写 4 行状态并成功拉起托盘、回执块三态（failed 弹、done 静默、missing 弹）、生成物 PARSE-OK + 产物校验 exit=0。⑦ 起点提示与全部托盘提示统一改为自绘弹窗 `dsh-toast.ps1`（新增 `Show-DshNotice`，模板 39 处调用点全部替换；单实例、按级别着色、长文自动加高）（本机 EnableBalloonTips=0，系统气泡与 Toast 都不显示；自绘卡片右下角 5 秒、不抢焦点），helper 在杀托盘前启动它；setup.ps1 新增部署该产物。已 DPI 感知截图与进程侧双重验证（helper 确实拉起 toast 进程）。**待推送 GitHub**（未 bump `_meta.json`） |
| dsh-launcher（一键启动本体） | 1.1.95 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **修「打开 Web UI 关掉后自己又弹一个窗口」**（2026-10-25，用户报障）：`Open-DshApp` 冷启动原为「`--app=<令牌 URL>` 睡 4 秒 → 找不到窗口再发 `--app-id` 重试一次」两段逻辑——用户在这 4 秒内关掉刚弹出的窗口时第二次启动照发，且两次入口画出的窗口外观不同（前者普通应用窗口带标题栏、后者已装 PWA 窗口无标题栏）。现改为**两级**：默认 `--app-id=<已装 PWA>`（无标题栏 PWA 窗口，250ms×48≈12 秒轮询）+ 降级 `--app=<令牌 URL>`（带标题栏应用窗口，250ms×24≈6 秒）：见到窗口即置顶返回（用户随后关掉也不补开）；默认入口 12 秒内一个窗口都没枚举到才降级，降级 6 秒也无窗口才返回 `$false`，由 `Open-Url` 用默认浏览器做最后兜底。删除 `$tryArgs` 两段重试；入口固定 `--app-id`（与桌面 `DSH应用.lnk` 同源，两个入口外观一致），令牌经 `--app-launch-url-for-shortcuts-menu-item` 捎入（认则刷新 30 天 cookie，不认退回 start_url）。另修：`--app=URL` 在本机被 Edge 当普通导航开成浏览器网页版，托盘一度只出网页版。验证：stub 掉 `Start-Process`/窗口枚举的新旧对比——旧实现关窗场景 2 次启动（bug）；新实现关窗场景 1 次、两轮都无窗口场景 2 次（默认+降级）、此后才回退浏览器；生成物 PARSE-OK，模板仍 UTF-8 无 BOM 纯 CRLF。**待推送 GitHub**（未 bump `_meta.json`） |
| dsh-launcher（一键启动本体） | 1.1.94 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **启动器环境清理扩展**（2026-10-14）：WorkBuddy/CodeBuddy 经 NODE_OPTIONS 注入 node「安全删除」护栏（实为回收站转移 + 每轮 50 次删除额度），DSH 贴图落盘路径必须 unlink 暂存文件，额度用满后删除被拒、裸异常被 commands.ts 兜底成 session/agent-busy，表现为「贴图发不出去」；模板 mode-source.json / mode-path.json 的 __MODE_START_DSH_SERVER__ 新增 Remove-InjectedDeleteGuard + Start-DshProcess（置空 NODE_OPTIONS、置 CODEBUDDY_SAFE_DELETE_ENABLED=0，生效后还原宿主环境）；本机 D:\DSHS 启动器已按同一方式手工打补丁；验证：同一 unlink 在原环境报 SAFE_DELETE_BULK_CONFIRM_REQUIRED、清洁后 ok，子进程 safeDeleteShimLoaded=false；备份 .bak-deleteguard-20261014-180312；**待推送 GitHub**（本次未执行上传） |
| dsh-launcher（一键启动本体） | 1.1.93 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **配套技能 skill-craft-charter 升至 1.7.0**（references 按【构建期】/【维护期】重划去噪：新增 `references/自维护留痕.md` 收原 `方法论.md` §六 全块，`方法论.md` 21,722→9,841 B；台账只留机器数据、两条规范（留痕存放/标注、专章计量口径）上移构建期文件；`SKILL.md` §7 加「读法分工」；§0 仍四条铁律、§6 仍 16 项）。主包按官方 `Is-SyncIgnored` 规则重建（71 条目），本轮发布到 `releases\v1.1.93\`（不再原地重写旧版本目录）。 |
| dsh-launcher（一键启动本体） | 1.1.92 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **规则 0 payload 同步为现行形态**（2026-09-22，AGENTS.md 合并收口）：① `setup.ps1` 内嵌 `$ruleBlock` 由「旧标题 + 全项加粗 + 无末句括注」同步为**现行规则 0**（`## 1 规则 0（最高优先强制项）…`，末句含「（平台系统约束除外，见第 5 节）」），`$ruleMarker` 同步更新——新机写入的 AGENTS.md 与主文件规则 0 段逐字一致（块内容口径：不含 here-string 结构性首尾空行）；② `SKILL.md` 的「本机两处同源…以本技能为准」改为止于事实的「已同步…权威仍以 AGENTS.md 为准」，并注明新建机器上「见第 5 节」暂无指向；③ 行为三态实测（新建写入／已同步跳过／缺规则 0 追加）＋ PS 5.1 语法检查通过。本轮发布到 `releases\v1.1.92\`。 |
| dsh-launcher（一键启动本体） | 1.1.91 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **修复内嵌配套包长期发旧件**（2026-09-19，审查 S1/S2）：① `dsh-sync.ps1` 的内嵌刷新由「本机版本 ≠ 内嵌版本」门控改为**对全部配套无条件重建**——原先「只改内容、未 bump 版本」的配套（pdf-parse-v3 去本机路径、adversarial-review 内容增长）内嵌包永不刷新，成品包长期发旧件，且旧件与新件 `_meta` 版本相同时引擎连分叉都检测不到；② 新增发布后一致性守卫（内嵌包 vs releases 包的条目名+大小，不一致即 warning）；③ 配套版本：pdf-parse-v3 **1.2.4**（去本机绝对路径 20 处）、adversarial-review `_meta` **0.1.0→0.1.2**（与其 SKILL.md frontmatter 对齐，消除自相矛盾）。本轮发布到 `releases\v1.1.91\`。 |
| dsh-launcher（一键启动本体） | 1.1.90 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **运行期留痕不再随包分发 + 发布物去本机路径**（2026-09-19）：① `dsh-sync.ps1` 的 `Is-SyncIgnored` 与 `Test-SyncPurgePath` 新增 `var/` 规则——各技能 `var/`（审查快照/台账/任务脚本）属每台机器各自的运行期产物，不进包/不进源树，并从仓库源树清除历史遗留；技能脚本按三级回落自建目录，新机器缺 `var/` 不影响可用（备案：`var/registry/guide-clauses.json` 沉淀条款也因此不再跨机传播）。② 清理 `pdf-parse-v3` 发布物内的本机绝对路径（`C:\Users\<用户名>` 等 20 处，均在文档/prompt 中）。③ 本轮起发布到新版本目录 `releases\v1.1.90\`（不再原地重写旧版本目录）。 |
| dsh-launcher（一键启动本体） | 1.1.89 | 0.1.5-rc.1（并保留 0.1.0-rc.7、0.1.1-rc.2） | **托盘全面适配 DSH 0.1.5-rc.1**（2026-09-12，本机实测）：① `Invoke-DshRpc` 改用斜杠端点（`session/list` 等）+ `{args:{<形参名>}}` 信封 + 启动令牌换浏览器认证 cookie（401 自动重登一次；令牌变化=服务重启过则自动重登）；② `session.models` → `session/modelCatalog`，并按新目录形状取值（`default` / `groups[].models[].reasoning?`）；③ `session/prompt` 补必填 `requestId`；④ 「打开 Web UI」/托盘双击/就绪后自动开浏览器一律走带令牌入口 `?token=…`（0.1.5 起裸 URL 无 cookie 直接 401），PWA 冷启动在带令牌时优先 `--app=URL`；⑤ 就绪探测统一为「端口在监听 + 日志已打印启动行 + 带认证 cookie 的 GET / 恰好 200」，两条分支同口径，不再把 401 当已就绪（读不到令牌时一次性气泡提示 + 30 秒兜底）；⑥ `setup.ps1` 的规则 0 幂等判据改为兼容两种标题形态的正则（`## 1 规则 0（…）` 与 `## 规则 0 —— …`），否则每次跑 setup 都重复追加 `~/.dsh/AGENTS.md`；⑦ 新增补丁 `dsh-frontend-static-no-store`（no-store/immutable/no-cache+ETag，注册进清单并已应用）与 `dsh-recycle-bin-restore-v2`（档案柜恢复半边）。实测：扩展冒烟 14/14 PASS + 令牌/就绪 8/8 PASS |
| dsh-launcher（一键启动本体） | 1.1.88 | 0.1.0-rc.7、0.1.1-rc.2 | 新增配套技能 adversarial-review（对抗性审查与沉淀迭代 v0.1.0，2026-09-06）：打包 adversarial-review__skillhub.zip 纳入 assets\配套技能\（目录即事实源），随启动器分发、setup.ps1 自动装到各机 ~/.agents/skills；配套数 6 → 7 |
| dsh-launcher（一键启动本体） | 1.1.87 | 0.1.0-rc.7、0.1.1-rc.2 | 多机分发健壮性（2026-09-05）：① setup.ps1 Find-Node 通用化：探测顺序改为 PATH → 官方/nvm 通用目录（Program Files\nodejs、%LOCALAPPDATA%\Programs\nodejs、NVM_HOME/NVM_SYMLINK）→ 宿主私有运行时→ node.cmd；② 托盘 Web 看护达重启上限时自动重跑 setup.ps1 自愈（30 分钟熔断防循环），仍失败才禁用+人工提示；③ 无 node 时明确指引安装 Node.js（setup 与托盘失败提示均补入 https://nodejs.org） ；含抗对审查修复（M1）helper 均 UTF-8 BOM+路径单引号转义（中文用户名机器）；M2 setup 路径渲染期注入 __SETUP_PS1__ + Test-Path 前置；M3 熔断 fail-closed；M4 Find-Node 可运行性/版本门槛（≥22.19）+排除 kimi-work；另修 re-arm 死代码、挂死进程清理、菜单名统一。 |
| dsh-launcher（一键启动本体） | 1.1.86 | 0.1.0-rc.7、0.1.1-rc.2 | 配套清单归一为「目录即事实源」（2026-09-05）：dsh-sync.ps1 清单由硬编码改为扫描 `assets\配套技能\` 目录内全部 `*__skillhub.zip`，与 setup.ps1 安装同源——增删配套只需放/删 zip，引擎零改动；配套描述/注释不再逐名列举 |
| dsh-launcher（一键启动本体） | 1.1.85 | 0.1.0-rc.7、0.1.1-rc.2 | 配套模型补齐（2026-09-05）：dsh-sync.ps1 的 `$script:CompanionSkills` 由 4 项扩为 6 项（纳入 pdf-parse-v3 / std-official-search），releases 发布循环与 Add 源树同步改引用统一清单——修复「两技能从不发布 releases 归档 / Add 源树」的遗漏；配套清单三处（引擎/文档/setup.ps1 注释）同步为 6 项 |
| dsh-launcher（一键启动本体） | 1.1.84 | 0.1.0-rc.7、0.1.1-rc.2 | 同步方向建议=真实文件 diff 分析+措辞与按钮一致（上传到 GitHub/拉取 GitHub 版本/取消）；第四行待更新同样经引擎弹窗，方向永不自动判定 |
| dsh-launcher（一键启动本体） | 1.1.83 | 0.1.0-rc.7、0.1.1-rc.2 | SKILL L92 同步规则表述修正（永不自动判定；主包+全部配套）；发布 v1.1.83 |
| dsh-launcher（一键启动本体） | 1.1.82 | 0.1.0-rc.7、0.1.1-rc.2 | 同步方向永不自动判定——只给建议，方向由用户选择（第四行待更新/双向同步均经引擎弹窗） |
| dsh-launcher（一键启动本体） | 1.1.81 | 0.1.0-rc.7、0.1.1-rc.2 | 同步纳入配套目录比对：配套技能版本变化自动检测推送（无需手动 bump 主包时间戳）；上传时自动刷新主树内嵌配套 zip、同步仓库 `dsh-launcher Add\` 配套源树 |
| dsh-launcher（一键启动本体） | 1.1.80 | 0.1.0-rc.7、0.1.1-rc.2 | 「切换同步分支」对话框新增「获取已有分支」按钮：点击后 git ls-remote --heads 动态拉取 GitHub 现有分支，去重后追加到下拉列表（与固定候选并存，不覆盖）；git 自动探测常见安装路径/GitHub Desktop/PATH 兜底，直连↔系统代理双路回退（读注册表 ProxyServer），失败弹窗给出可操作提示；按钮获取中变灰显示「获取中…」 |
| dsh-launcher（一键启动本体） | 1.1.79 | 0.1.0-rc.7、0.1.1-rc.2 | 同步 repo/branch/候选分支收敛为单一来源 `assets\sync-defaults.json`（改一处全局生效）：dsh-sync.ps1 / configure-git-credentials.vbs / mode-*.json 的分支值改为占位符 `__GH_REPO__` / `__GH_BRANCH__` / `__GH_BRANCHES__`，setup.ps1 渲染时从 sync-defaults.json 注入（dsh-sync.ps1 与 vbs 由 Copy-Item 改为渲染写）；托盘右键菜单新增「切换同步分支」项（下拉候选来自 sync-defaults.json 的 branches + 手动输入，选择后写 `~\.dsh\gh-sync\config.json` 的 branch 并重启托盘生效）；同步目标改 main 主分支 |
| dsh-launcher（一键启动本体） | 1.1.78 | 0.1.0-rc.7、0.1.1-rc.2 | 托盘「重启 DSH」改名为「硬重启托盘」，点击后先运行 setup.ps1（重新生成脚本/更新版本/应用补丁，-Wait 等待完成）再重启托盘 |
| dsh-launcher（一键启动本体） | 1.1.77 | 0.1.0-rc.7、0.1.1-rc.2 | 「发布前检查清单」补第 5 步：同步完成后重启服务 + web 界面（让新脚本/版本号在运行中生效） |
| dsh-launcher（一键启动本体） | 1.1.76 | 0.1.0-rc.7、0.1.1-rc.2 | 新增「发布前检查清单」章节：本地改动 → setup 生成 → 人工检查 → 确认 OK 才 bump + 同步（setup 与同步分离，禁止跳过检查直接上传） |
| dsh-launcher（一键启动本体） | 1.1.75 | 0.1.0-rc.7、0.1.1-rc.2 | 第三行单击保持菜单打开（菜单级 ItemClicked 精确判断：点第三行不关闭菜单、便于连点 5 次，点其它项/别处照常关闭）；5 连击改为 wscript 启动 configure-git-credentials.vbs（Windows 原生 InputBox，无控制台闪现——powershell -WindowStyle Hidden 会隐藏 InputBox/Form 导致不弹窗，改用 GUI 型 wscript 彻底规避；vbs：InputBox 输入 token → ADODB.Stream 写 UTF-8 config.json → MsgBox 提示）；旧 configure-git-credentials.ps1 移除 |
| dsh-launcher（一键启动本体） | 1.1.74 | 0.1.0-rc.7、0.1.1-rc.2 | 托盘第三行「DSH魔偶助手」加粗（与第一行同款 Microsoft YaHei UI 9pt Bold） |
| dsh-launcher（一键启动本体） | 1.1.73 | 0.1.0-rc.7、0.1.1-rc.2 | 托盘右键菜单拆行为四行：第三行「DSH魔偶助手 <本地版本>」（3 秒内左键连点 5 次 → 打开 configure-git-credentials.ps1 配置 token）；第四行无 token 时「魔偶最新版本 <远程>（待更新/无需更新）」——待更新点击即拉取更新本地，无需更新点击做状态刷新（查询中…显示 ≥1s）；配置 token 后第四行变「魔偶Git版本 <远程>（单击双向同步）」——点击弹确认框，确定后双向同步；setup.ps1 部署 configure-git-credentials.ps1 到安装目录 |
| dsh-launcher（一键启动本体） | 1.1.72 | 0.1.0-rc.7、0.1.1-rc.2 | 托盘第三行文案改为「启动器版本 xx 版（有新版/无新版/无法检测）」；Get-GhLauncherVersion 带 token 检测（私有仓库也能检测版本，$ghToken 为空时匿名访问公开仓库）；dsh-sync 新增 Is-SyncIgnored 凭证类通配排除（config.json / credentials / .dsh / *.token 绝不进打包/上传，分发安全红线）；收编 configure-git-credentials.ps1 一键 token 配置脚本（转 UTF-8 BOM、分支修正为 feature/github-sync-v1.1.66）；环境要求-安装指南.md 新增「配置 GitHub token」章节 |
| dsh-launcher（一键启动本体） | 1.1.71 | 0.1.0-rc.7、0.1.1-rc.2 | 环境清理匹配扩展 kimi-work（2026-08-30）：Start-DshServer 的 PATH 清理由 kimi-desktop|daimon 扩展为 kimi-desktop|daimon|kimi-work，覆盖 kimi 生态的 .kimi-work\bin 注入段，确保从任何宿主启动 DSH 时 web/GUI 环境均无 kimi 残留 |
| dsh-launcher（一键启动本体） | 1.1.70 | 0.1.0-rc.7、0.1.1-rc.2 | 同步方向判定升级为「版本号优先、时间戳兜底」（2026-08-30，与配套技能一致）：auto 模式先比 _meta.json 的 version（新增 Compare-SyncVersion 语义比较，1.1.9 < 1.1.10），版本高者胜；版本相同再比 publishedAt；两者都相同才按内容修改时间分析并弹窗人工确认；配套 charset-pitfalls 升至 1.1.6（新增「AI 编辑工具编码坑·先检测后选路」章节） |
| dsh-launcher（一键启动本体） | 1.1.69 | 0.1.0-rc.7、0.1.1-rc.2 | DSH 改用通用 Node.js 运行（2026-08-30）：Start-DshServer 启动 web 前清理宿主 agent（kimi daimon）注入的环境变量——移除 PATH 中的 kimi-desktop/daimon 段、删除 npm_config_prefix，source 模式再把通用 node 目录前置，确保 DSH 服务与 GUI 命令均使用用户安装的 Node；setup.ps1 Find-Node 在干净 PATH 下选中通用 node.exe |
| dsh-launcher（一键启动本体） | 1.1.68 | 0.1.0-rc.7、0.1.1-rc.2 | 双击托盘 PWA 打开链路易损性修复（2026-08-30 实测案例驱动）：① **Edge 检测改用 `[Environment]::GetFolderPath`**——托盘/安装若从 PATH 被精简的宿主进程（自动化 agent shell）启动，`$env:ProgramFiles` 为 null 会让 Open-DshApp 抛异常静默退化成开标签页（本次"100% 开标签"主根因）；② **Edge 152 起 `--app-id` 在已有浏览器会话时会被转发成普通标签页**——冷启动改为先试 `--app-id`、失败用 `--app=URL` 兜底（应用模式窗口，无需注册）；③ 窗口匹配只认 PWA/应用模式窗口（排除 `- Microsoft Edge` 结尾的普通浏览器窗口，防标签页抢焦点）；④ 两次尝试仍无应用窗口则认输回退开普通标签页（保证双击一定有页面出来）；⑤ 桌面 DSH应用.lnk 同步改 `--app=URL`；⑥ **setup.ps1 的 Find-Node 排除 agent 环境 node.cmd 包装器**——若在 PATH 被注入的宿主（kimi-desktop command-process-owner\bin\node.cmd）里跑安装，渲染进托盘的 node.cmd 依赖宿主私有环境变量，经 Explorer/启动文件夹启动时变量缺失导致 web 起不来（「反复启动失败」）；现过滤为只选真 node.exe（排除 command-process-owner/daimon-share 路径），回退 `$env:KIMI_DESKTOP_RUNTIME_NODE` 真 node.exe，最后才用 node.cmd 并打警告 |
| dsh-launcher（一键启动本体） | 1.1.67 | 0.1.0-rc.7、0.1.1-rc.2 | 代码审查 bug 修复批次（B1–B24）：补丁引擎改子进程调用（exit 不再中止 setup）；默认分支三处收敛 `feature/github-sync-v1.1.65`；显式同步方向不再被时间戳翻转、时区基准统一 UTC；就地安装.bat 加技能目录守卫防自毁；更新安装.cmd zip 校验降级改 .NET 实现、覆盖改 robocopy /MIR；托盘网络查询超时生效、readyTimer 不再永久放弃；删除死代码（70-sync-*.ps1、两个废弃 .tmpl）；补丁引擎 $LASTEXITCODE 清零 +「已应用」口径收紧；文档口径五处对齐。配套技能 zip 文档同步为 GitHub-first（batch-files 1.1.4 / charset-pitfalls 1.1.5 / zip-archive-ops 1.0.5） |
| dsh-launcher（一键启动本体） | 1.1.66 | 0.1.0-rc.7、0.1.1-rc.2 | 1.1.66 「一键同步」发布级重写：repo/branch/token 可配置（env > `~\.dsh\gh-sync\config.json` > 默认，同步分支改 `feature/github-sync-v1.1.65`）；系统代理自动探测 + 直连↔代理双路回退（命令级 -c 注入不改全局 git）；git 非交互防弹窗（GIT_TERMINAL_PROMPT=0 + GCM_INTERACTIVE=Never），失败分类为可操作提示（未装 git/认证缺失失效/仓库分支 404/网络不通/非快进）；文本比对归一化 CRLF→LF（修 autocrlf 同内容不同哈希 bug）、跳过机器特定文件、时间戳相同按 git 提交时间分析（修 clone 后 mtime 误判）；上传发布 5 个 zip（主包+4 配套）到 `releases\<版本>\`、`HEAD:<branch>` push、token 经 http.extraheader 仅内存注入；互斥锁防并发、缓存损坏自愈、结构契约校验； |
| dsh-launcher（一键启动本体） | 1.1.65 | 0.1.0-rc.7、0.1.1-rc.2 | 托盘所用 RPC 在两版均存在；`_meta.json` 的 `compatibleDsh` 字段同步维护；1.1.48 起配套技能版本比较改为「版本号优先、时间戳兜底」；1.1.51 完成 P0-P2 全面修复（补丁引擎 $LASTEXITCODE 陷阱/还原 enabled、托盘重启链编码、更新安装.cmd 降级等）；1.1.52 修复还原失败时 manifest 丢失成功项的回归 + 文档验证口径同步；1.1.53-57 托盘双击/「打开 Web UI」优先打开已装 PWA 主应用（SC_RESTORE 聚焦 + IsZoomed 最大化保护 + 未装引导式安装）；1.1.58 固化调试纪律铁律（绝不在运行中生成物上直接编辑，改模板→重新生成→验证→重启，先备份良包）；1.1.59 「重启 DSH」改版：杀 web + 按标题关闭 DSH 浏览器窗口（CloseDshWindows，WM_CLOSE 优雅关闭，不碰其他窗口）+ helper 接力重启托盘（-OpenBrowser 就绪后自动重开 PWA），所有 Start-Process powershell 统一加结尾 -WindowStyle Hidden 消除命令行窗口闪现；1.1.60 修复托盘右键「最新版本」查询失败：PS5.1 默认 TLS 非 1.2 + 系统代理（Clash 7897）对 npm HTTPS 转发不可靠 → Get-LatestDshInfo 强制 TLS1.2 + 优先直连（WebClient.Proxy=$null）、失败回退系统代理；1.1.61 一键托盘入口全面去闪烁：`启动DSH-托盘.cmd` 顶部加自隐藏包装（`run-hidden.vbs` 经 wscript 以隐藏窗口重入，`__DSH_HIDDEN` 标记防重入），新增零窗口双击入口 `启动DSH-托盘.vbs`（wscript 直启隐藏 powershell），setup.ps1 部署新 vbs 并更新产物清单；1.1.62 托盘右键第三行文案优化：「一键启动脚本版本」→「一键同步启动脚本」（模板/文档/生成物同步；内容变更同步 bump _meta 版本时间戳，避免同步误判人工复核）；1.1.64 同步冲突处理（用户确认制）：时间戳相同但内容不同时，按实际文件修改时间分析并弹窗展示分析/建议，由用户确认方向（上传/拉取/取消）后才执行，绝不自动覆盖良包；1.1.65 同步存档全面切换 GitHub：弃用 Z: 网络盘（NAS）存档，托盘「一键同步」改为 git 双向同步 `moonwellxh/DSH-Launcher`（clone/fetch 工作副本 `~\.dsh\gh-sync\DSH-Launcher`，逐文件 SHA256 比对逻辑不变；上传=更新源树 + 重打包 zip 到 `releases\<版本>\` + git add/commit/push，git 历史天然备份旧版，不再手工备份旧包；拉取=与仓库源树比对后应用并重跑 setup；git 全程非交互 GIT_TERMINAL_PROMPT=0，缺凭据立即报错） |
| 档案柜 v1 补丁 | 0.1.1 | **仅 0.1.1-rc.2** | 载荷绑定版本；清单 `compatibleDsh` 字段校验 |

**兼容性检查规则（防冲突）**：
- **补丁引擎**（已退役，2026-11-06）：原规则为「应用每个补丁前按清单 `compatibleDsh` 比对版本，不匹配即跳过、绝不硬装」。引擎与清单已移入 `D:\DSHS\_bak\补丁管理-退役-20261106-174104\`，不再参与任何自动流程。
- **托盘同步**（右键第三行）：GitHub 上的启动器若声明了 `compatibleDsh` 且本机 DSH
  不在其列 → **提醒先升级 DSH，不更新本地**。
- **修改适配规则**：技能/补丁适配了新 DSH 版本后，必须同时更新：本表、
  `_meta.json`（启动器）或清单（补丁）的 `compatibleDsh` 字段。
- **旧 DSH 上不要手动强装**新适配的补丁/脚本（2026-08-23 事故教训）。

## 修改与分发规则（同步目标：GitHub，已弃用 Z: 网络盘存档）

安装/修改/更新本技能后，维护仓库内**解压源树 `dsh-launcher/`**（本技能目录），并把新 zip
（根目录 = 技能名 `dsh-launcher`）归档到 GitHub 仓库 `releases\<版本>\dsh-launcher__skillhub.zip`
（如 `releases/v1.1.66/`），随后 git commit + push。托盘右键第三行「启动托盘版本」可自动完成
「源树更新 + 重打包 zip 到 releases\<版本>\ + 提交推送」；**大版本更新前，当前版本的内容已按
版本目录留档在 `releases\v<旧版本>\`**（git 历史也是天然备份）。

### 编程规范：泛化性与发布就绪（用户规定，2026-08-30 起执行，优化项记入待办、本次不改）

- **任何写进成品的具体取值都必须能泛化**：路径、用户名、盘符、应用私有运行时路径等，一律
  在目标机器上探测/渲染，或提供可配置的兜底，**禁止把本机才有的取值当作通用解**。
  反例（2026-08-30）：Find-Node 在无真 node.exe 时回退到
  `%LocalAppData%\Programs\kimi-desktop\...\runtime\node.exe`——那是 kimi-desktop 的私有运行时，
  其他机器/卸载后即失效；虽属安装期按机渲染（非源码写死），仍不符合发布要求。
- **按"以后要发布给任意用户"的标准写代码**：优先级应为「用户正式安装的 Node.js（PATH）＞
  常见版本管理器（nvm 等）＞明确提示用户安装 Node.js」，应用私有运行时最多作为带警告的
  最后兜底，且托盘启动失败时应能自愈重探测而不是直接放弃。
- 后续优化项（2026-09-05 多机分发视角重评：本机「罕见」≠ 多机「罕见」，三项均实施于 1.1.87）：
  ① Find-Node 通用化——探测链改为 PATH → 官方/nvm 通用目录（Program Files\nodejs /
     %LOCALAPPDATA%\Programs\nodejs / NVM_HOME / NVM_SYMLINK）→ 宿主私有运行时（kimi/workbuddy，
     仅宿主机兜底并带警告）→ node.cmd；② 托盘 Web 看护达重启上限时自动重跑 setup.ps1 自愈
     （重探测 node/DSH 并重渲染托盘；30 分钟熔断标记防死循环），仍失败才禁用并提示人工；
  ③ 无可用 node 时 setup 与托盘失败文案均明确指引安装 Node.js（https://nodejs.org），
     不再静默回退私有运行时。

### 配套技能清单与维护（必须同步，缺一不可）

本技能是**主安装包**，`assets\配套技能\` 目录内全部 `*__skillhub.zip` 即配套技能
（**目录即事实源**，2026-09-05 归一）：setup.ps1 安装与 dsh-sync.ps1 同步引擎
（比对/刷新内嵌/Add 源树/发布 releases）**统一扫描该目录**推导清单，不再有任何散落的
硬编码名单——新增/移除配套只需放/删 zip，引擎零改动。
（历史教训：曾硬编码 4 项遗漏 pdf-parse-v3 / std-official-search，导致其 releases
归档与 Add 源树从不发布；故归一为目录扫描。）

**每次修改任一配套技能，三连同步**：
1. 打包 `xxx__skillhub.zip`（根目录=技能名）同步到 GitHub 仓库
   `releases\<当前版本>\`（与主包同目录归档）＋ 仓库内配套源树 `dsh-launcher Add\<技能名>\`；
2. 把新 zip 复制进本技能 `assets\配套技能\`（覆盖旧包）；
3. 重打包 `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\`，git commit + push
   （setup.ps1 按时间戳自动分发新版）。
> **自 1.1.81 起自动化**：一键同步已把配套目录纳入比对，配套版本变化自动检测推送（自动刷新主树内嵌 zip、发布 releases zip、同步 `dsh-launcher Add\` 源树）；第 2、3 步无需手动执行，主包版本不变也无需手动 bump 时间戳。

**以后新增脚本技能**（成为一键启动配套的通用规则）：
1. 建好技能（SKILL.md + _meta.json，编码/结构遵守 charset-pitfalls 技能）；
2. 打包 `xxx__skillhub.zip`（根目录=技能名），归档到 GitHub `releases\<当前版本>\`，
   并把源树放进 `dsh-launcher Add\<技能名>\`；
3. 把该 zip 复制进 `dsh-launcher\assets\配套技能\`（**目录即事实源**：setup.ps1 与
   同步引擎自动扫描该目录下所有 `*__skillhub.zip`，无需改引擎/清单）；
4. 重打包并同步 `dsh-launcher__skillhub.zip`（`releases\<当前版本>\`）。

**与 launcher 无关的技能**：zip 不进入本仓库的 releases 配套归档，独立管理。

**归档定位铁律（2026-08-24 用户明确，2026-08-24 修订：用户最终拍板）**：技能是否进
launcher 配套，**最终由用户定义**。AI 只能做预判断（一键启动相关通用运维技能 vs
个性化生产力技能），**判断后必须先征得用户同意，才能执行配套/独立的归档操作**
（进 `assets\配套技能\`、进 `dsh-launcher Add\`、进主包内嵌，或仅放根目录）。
未经用户确认，AI 不得自行决定技能归属并执行归档。当前 `assets\配套技能\` 目录内的配套
是已获用户认可的历史决定（**目录即事实源**，增删由用户拍板后放/删 zip 即生效）；
`cad-scan-eye` 扫描之眼已明确为根目录独立能力。

## 本机工具索引（2026-11-01）

`assets\tools\` 下是可直接复用的本机工具，调用时用绝对路径 `%USERPROFILE%\.agents\skills\dsh-launcher\assets\tools\<名>`：

- `probe-elevated.ps1`：读进程令牌，报 `DSH-TRAY` / `DSH-WEB` / 本 shell / explorer 是否为 ELEVATED（判托盘与服务权限，最常用）。
- `switch-dsh-home3.ps1` + `run-switch3.ps1`：切换 DSH 家目录（改 `dsh-home.txt`，托盘 `Start-DshServer` 读取）。必须用 `run-switch3.ps1 -NewHome <路径> -Now` 经计划任务执行，否则脚本会自检拒绝（避免像 v1 那样把自己杀掉）。
- `test-frontend-cache.mjs`：验前端三档缓存头（index `no-store`、内容寻址 `immutable`、普通静态 `no-cache`+ETag+304）。
- `test-model-menu-plugin.mjs`：验 client 插件注册格式（`window.__ModuleLoader__.load`）。

### dsh-home.txt 约定（2026-11-02）

- 文件放在安装目录（如 `D:\DSHS\dsh-home.txt`），内容为**单行纯 ASCII 绝对路径**，无 BOM、无引号、无尾随空格。
- 读者：托盘 `Start-DshServer`、`dsh.cmd`、`DSH-rescue.ps1`、备份引擎、会话索引任务。
- 差异提示：托盘与备份用 `Trim()` 去首尾空白；`dsh.cmd` 用 `for /f` **不去尾随空格**。手工编辑该文件时别留空格，否则只有命令行那条链会带上空格。
- 备份引擎的解析顺序：`dsh-home.txt` → `~\.dsh`（`$env:DSH_HOME` 分支已删除，因为计划任务环境里不存在该变量）。