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
> 它会重新生成启动脚本并**自动按清单应用补丁**（见「补丁自动载入清单」）；**跳过此步 = 技能更新不完整（补丁未打）**。

## 到新机器怎么用（二选一）

### 方式 A：作为 DSH 技能使用（有 AI 协助时，推荐）

1. 把本技能装到 DSH 技能目录 `~/.agents/skills/dsh-launcher`（或从
   `dsh-launcher__skillhub.zip` 解压，zip 根目录=技能名）。
2. 运行安装脚本（AI 或用户手动执行均可）：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1"
   ```

   脚本会自动探测本机 DSH、生成适配脚本、默认建桌面快捷方式。
3. **配套技能自动安装**：本技能 `assets\配套技能\` 内打包了四个配套技能
   （`zip-archive-ops` / `batch-files` / `charset-pitfalls` / `skill-install-ops`
   的 `__skillhub.zip`），
   setup.ps1 安装时会自动把它们装进 `~/.agents/skills\`（已装且包内不更新则跳过）。
   **只需分发 `dsh-launcher__skillhub.zip` 一个包即可带全五个技能**。
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
3. **以后更新**：把新 `dsh-launcher__skillhub.zip` 放到 `assets\` 目录（或直接拖到脚本上），双击 `assets\更新安装.cmd`——它自动完成「解压覆盖技能 + 重跑 setup.ps1（自动应用补丁）+ **刷新桌面快捷方式**（指向当前安装目录）+ **自动启动托盘**（就绪后自动开浏览器一次）」。若托盘图标未出现，先结束残留的 DSH-tray powershell 进程再启动；若 setup 失败会明确报错并提示原因。

## setup.ps1 参数

```powershell
setup.ps1                          # 自动探测并安装到 %USERPROFILE%\DSH
setup.ps1 -InstallDir D:\DSHS      # 指定安装目录
setup.ps1 -NoShortcut              # 不建桌面快捷方式
setup.ps1 -CheckOnly               # 只探测、打印结果，不安装
```

## 探测逻辑（AI 需知）

> **边界声明（必读）**：`setup.ps1` 是**启动器生成器，不是 DSH 安装器**。它从不安装、
> 升级、卸载 DSH 本体；不运行 npm/pnpm；不改 PATH。DSH 怎么装由**用户指定**：
> 源码树 = `git pull` + `pnpm install` + `pnpm build --profile official`（产物
> `apps\cli\lib\bin.js`，缺它源码树识别不到）；npm 全局 = `npm update -g @deepseek-ai/dsh`。
> setup.ps1 只做三件事：① 探测**已装好**什么；② 生成启动脚本/快捷方式；③ 按补丁清单
> 打补丁（可挂起）。它的 `mode=path/source` 只是"从已装好的里面挑一个来启动"，
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
| `DSH-tray.ps1` | 系统托盘：右键菜单**顶部分隔线上方三行**——第一行「DSH 版本 x.x.x」**加粗**（点击打开 DeepSeek 文档 deepseekdocs.com）、第二行「最新版本 x.x.x（点击升级）」（可更新时可点，弹窗确认：可编辑提示词 + 选模型/推理等级后 `selectModel`+`prompt` 提交，无需粘贴）、第三行「启动托盘 x.x.x 版（点击可更新/已是最新）」（点击**与 GitHub 双向同步**（发布级）：配置优先环境变量 `DSH_SYNC_REPO` / `DSH_SYNC_BRANCH` / `DSH_SYNC_TOKEN` > `~\.dsh\gh-sync\config.json` > 内置默认（repo=`moonwellxh/DSH-Launcher`、branch=`feature/github-sync-v1.1.65`）；网络自动探测系统代理、直连↔代理双路回退（命令级 `-c` 注入，不改全局 git 配置）；git 全程非交互（禁终端提示 + 禁 GCM 弹窗），失败按类给出可操作提示（未装 git / 认证缺失或失效 / 仓库分支 404 / 网络不通 / 非快进）；以仓库源树 `dsh-launcher/` 为比对对象逐文件内容比对（文本先归一化 CRLF→LF 再哈希，避免 autocrlf 造成"同内容不同哈希"；跳过机器特定文件 install-dir.txt），方向按双方实际 `_meta.json` 时间戳判定——GitHub 新则更新本地并重跑 setup 后自动重启托盘，本地新则更新源树 + 发布 **5 个 zip（主包+4 配套）** 到 `releases\<版本>\` + git 提交推送（`HEAD:<branch>`，token 经 http.extraheader 仅内存注入、不落盘不打印）并校验，一致则跳过，时间戳相同但内容不同则按 **git 提交时间 vs 本地修改时间**分析并弹窗展示分析/建议，由用户确认方向（上传到 GitHub/拉取 GitHub 版本/取消）后才执行（绝不自动覆盖；git 历史保留旧版；同步带互斥锁防并发；缓存损坏自动重建）；不信任缓存/版本号）；其余菜单项：打开 Web UI / TUI / Headless / DS 开放平台（platform.deepseek.com）/ 重启 / 退出并停止；单击无动作、双击开浏览器；状态气泡保留 |
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
- **打开主应用优先（2026-08-25 新增，1.1.54 实测定型）**：托盘双击 / 「打开 Web UI」优先
  打开用户已手动「安装为应用」的 PWA 主应用（独立窗口、聚焦不开多个、界面与主应用一致），
  而非普通浏览器标签页。机制：`Open-DshApp` 读 Edge `Preferences.web_apps.daily_metrics[
  "http://127.0.0.1:3080/"].installed` 判断是否已装 → 已装则用 Win32 枚举找已有 PWA 窗口，
  发 `PostMessage(WM_SYSCOMMAND, SC_RESTORE)` 恢复最小化 + `SetForegroundWindow` 置顶
  （实测 `--app-id` 会开新窗口不可靠，SC_RESTORE 对 Edge PWA 有效）；窗口不存在才
  `msedge --app-id=hgiemfgfjhalibdoboikeiepnnjapnpc` 启动；未装/无 Edge 则回退普通浏览器。
  PWA 需用户在 Edge 地址栏手动「安装为应用」一次（Edge 无静默安装命令行）；setup.ps1
  检测到 Edge 会附加建 `DSH应用.lnk` 桌面快捷方式（指向 `msedge --app-id=...`，装了 PWA
  后双击即开主应用）。**引导式安装**：未装 PWA 时双击托盘不默默开普通网页，而是打开 Edge
  访问 3080（地址栏出现安装图标）+ 气泡提示「点安装图标安装为独立应用」，用户点一下即完成；
  同一次托盘生命周期只提示一次（`$script:pwaGuideShown` 标记），装好后下次双击即走聚焦逻辑。
- **Web 看护重启上限**：自动重启连续失败 3 次 → 停止自动重启并气泡提示
  「DSH Web 反复启动失败（可能 DSH 版本过旧或安装异常），请升级 DSH」。服务恢复后计数
  归零。**老 DSH + 新启动器**场景：补丁被兼容检查跳过（正常），若 web 起不来即升级 DSH。
- **托盘手动关闭**：托盘脚本记录 3080 端口的监听 PID，右键「退出并停止 DSH」时
  `taskkill /PID <pid> /T /F` 停止整棵进程树。
- **编码约定**：`.bat/.cmd` 用 GBK + CRLF（含中文时）、无 BOM；`.ps1` **含中文必须 UTF-8 带 BOM**（否则 Windows PowerShell 5.1 按 ANSI 解析中文会报语法错误），纯 ASCII 的 .ps1 任意编码均可（推荐仍带 BOM）。`setup.ps1` 已按此约定写出生成物，不要手工改写生成后的脚本。
- **写 .ps1/.bat/.cmd 前先载入 `charset-pitfalls` 技能**（全局中文编码避坑汇总，
  含本技能全部编码约定与踩坑记录），动手前对照编码表，不要等出乱码再查。
- **冷启动**：源码树模式优先用已构建的 `apps\cli\lib\bin.js`（免 tsx，约 4s），
- **0xc0000142（cmd/node 偶发"应用程序无法正常启动"）**：DLL 初始化失败的瞬时现象，多为**快速连续拉起多个进程**（或系统瞬时状态/其他安全软件扫描）触发，非持续故障。处理：避免密集拉进程；托盘版本读取已改为直接读 package.json（免 node 进程）；如频繁出现再排查系统 DLL/安全软件。- **快捷方式图标不更新**：`.lnk` 指向的 `.ico` 文件本身没问题时，是 Windows 图标缓存未刷新。解决顺序：先 `ie4uinit.exe -show`；仍不更新则结束 Explorer（`taskkill /f /im explorer.exe`）→ 删除 `%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db` → 重启 Explorer（`start explorer.exe`）。
- **GitHub 同步（同步守卫，1.1.66 发布级重写）**：同步逻辑**唯一实现为 `assets\dsh-sync.ps1`**，托盘「一键同步」菜单调用它执行
  （托盘生成物内不再内嵌同步实现，原 `tmpl\parts\70-sync-*.ps1` 内嵌副本已删除）。同步以仓库源树 `dsh-launcher/` 为比对对象，逐文件
  **内容级比对（不信任缓存/版本号）**——文本文件先归一化 CRLF→LF 再 SHA256（git `core.autocrlf` 会把检出文件
  变成 CRLF，与 zip 内 LF"同内容不同哈希"，必须归一化；二进制如 zip/ico/png 保持原始字节）；**跳过机器特定文件**
  （`assets/install-dir.txt`）；方向按双方实际 `_meta.json` 时间戳判定；时间戳相同但内容不同时按 **git 提交时间 vs
  本地修改时间**分析并弹窗由用户确认方向（上传/拉取/取消），**绝不自动覆盖远端良包**。配置/健壮性：repo/branch/token
  可配置（环境变量 `DSH_SYNC_REPO/DSH_SYNC_BRANCH/DSH_SYNC_TOKEN` > `~\.dsh\gh-sync\config.json` > 默认）；
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

## 补丁自动载入清单（assets\补丁管理\）
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
- 补丁备份默认在 `~\.dsh\patches-backup\<补丁id>\`（可用 `-BackupRoot` 覆盖）；
- **幂等与验证**：`setup.ps1` / `重打全部补丁.bat` 均可重复运行，不会重复打或损坏（已应用自动跳过）；验证补丁是否生效：跑 `补丁引擎-应用还原检查.ps1 -CheckOnly`（列计划即已应用清单）；还原用 `补丁引擎-应用还原检查.ps1 -Restore`。注意：还原成功后备份清单会被清空为 `{}` 且备份目录会被删除，故「目录存在=已应用」不再可靠；引擎的「是否已应用」判断以三条件齐备为准——**备份目录存在 + `backup-manifest.json` 存在 + 清单解析后非空（含备份条目）**。
- 每个补丁一个独立子目录 `补丁管理\补丁NN-功能名\`，含安装脚本 / 还原脚本 / `载荷文件\`
  （`id` 决定备份目录名保持稳定，`dir` 决定源码子目录名可随意起名，详见目录内 README）；
- **清单控制安装**：`自动载入清单-manifest.json` 里每个补丁的 `enabled` 字段决定是否随 `setup.ps1` / `重打全部补丁.bat` 自动安装：`true` = 安装；`false` = **挂起（跳过不装）**。需要临时停用某补丁（如与新版本冲突）时置 `false` 即可，改回 `true` 再跑一次即恢复；不必删除补丁目录。
- **新增补丁三步**：① 写载荷与安装/还原脚本 → ② 在 `自动载入清单-manifest.json` 登记（`enabled: true`）→ ③ 同步 `assets\补丁管理\` 并重打包 zip（见下）。
- 已知补丁登记：
  - `补丁01-档案柜v1-归档升级版`（id: dsh-recycle-bin-v1，**已适配 0.1.1-rc.2**，2026-08-23）：会话 ⋯ 菜单「移入档案柜」+ 侧边栏底部「档案柜」分区（默认折叠）+ 恢复；新增服务端 RPC `workspace.restoreSession`，应用后需重启 dsh web。**适配方法**：对每个目标文件 diff「旧原始 vs 旧补丁」提取增量，再按新版上下文套用（dsh-workspace 新旧一致可直接套用；其余 4 个按锚点插入：RPC handler/schema/路由、客户端 schema/方法、运行时 manager/facade、UI RecycleSection 组件+属性穿透+i18n+actions）。

## DSH 升级 + 补丁安全流程（用户规定的固定流程，2026-08-23 起执行）

**任何 DSH 版本升级（含托盘升级按钮触发的 AI 升级），严格按以下顺序执行；未经用户
明确确认，不得应用不兼容补丁：**

1. **更新 DSH**：源码树安装 → 进入源树 `git pull` → `pnpm install` → `pnpm build`；
   PATH/npm 安装 → `npm update -g @deepseek-ai/dsh`。
2. **更新一键启动**：重跑 setup.ps1 —— 但**执行前**先把本技能
   `assets\补丁管理\自动载入清单-manifest.json` 中**所有补丁 `enabled` 置 `false`
   （全部挂起）**，确保 setup.ps1 不应用任何补丁。
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

**铁律**：setup（生成 + 检查）与同步（分发）是两个独立步骤，**绝不能跳过 setup/检查直接上传**
（2026-08-30 教训：bump 后漏跑 setup 导致安装目录 `launcher.version` 滞后、托盘版本显示旧值）。
## 已装机器如何升级

**更新后的必做步骤（不重跑 = 补丁未打、安装不完整）：**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1" -InstallDir "<安装目录>" -NoShortcut
```

`setup.ps1` 一次完成：① 重新生成启动脚本；② **自动按 `assets\补丁管理\` 清单应用补丁**（幂等，已应用会跳过）。补丁仅在 DSH 重装/升级导致失效时才需要重打；验证方式：`~\.dsh\patches-backup\<补丁id>\` 目录存在且 `backup-manifest.json` 非空（含备份条目）即已应用，或跑 `assets\补丁管理\补丁引擎-应用还原检查.ps1 -CheckOnly`。

**升级/打补丁/换前端插件后必须硬刷新浏览器（Ctrl+F5）重新加载 http://127.0.0.1:3080**：
DSH 前端是 client-plugin 图（index.html 的 `__DSH_BOOT__` 指向带 rev 哈希的插件 JS），
服务端重启只是第一步；浏览器缓存旧页面 = 继续跑旧插件，界面（如侧边栏左上角品牌名
`sidebar.brand.name` 槽位）显示旧内容或兜底文字 "DSH Local Build"（官方字标由
`dsh-client-ui-brand-official` 插件提供，仅 official 构建注册）。刷新后插件按新 rev
重载才正确。给其他机器升级时的标准说法与同类情况清单见
`assets\升级后重新渲染-标准说法.md`。

GitHub 仓库（`moonwellxh/DSH-Launcher`，`feature/github-sync-v1.1.65` 分支）是各台机器修改的合集；仓库内**解压源树 `dsh-launcher/` 为维护对象**，
zip 安装包**集中归档在 `releases\<版本>\` 目录**（历史版本按目录留档）。已在用的机器按下面规则对齐：

| 本次改了什么 | 已装机器要做的 |
|---|---|
| 只改 `SKILL.md` / `_meta.json` / `_icon.png` | 重装技能：解压 zip 覆盖 `~/.agents/skills\dsh-launcher` 即可 |
| 改了 setup.ps1 或 `assets\tmpl\` 模板（`parts\*.ps1` / `mode-*.json`） | 重装技能 + 重跑一次 setup.ps1（重新生成安装目录里的启动脚本） |
| 改了 `assets\补丁管理\*`（补丁载荷 / 清单 / 引擎） | 重装技能 + 重跑一次 `setup.ps1`（或直接跑 `assets\补丁管理\补丁引擎-应用还原检查.ps1`） |
| 想一键完成上面任意一项 | 双击 `assets\更新安装.cmd`（新 zip 放 assets 目录或拖入），自动「覆盖技能 + 重跑 setup.ps1（自动应用补丁）」 |

原因：真正运行的是 `setup.ps1` 生成的脚本（`dsh.cmd`、`DSH-tray.ps1`、`启动DSH.bat` 等），
光更新技能不会刷新这些生成物；`setup.ps1` 幂等，可安全重复执行。

合并多台机器的修改时：以 GitHub 仓库为准逐文件比对，凡「GitHub 有而本地无」或「两边不同」的文件，
以 GitHub 为准并入本地，再 git commit + push 回 GitHub（托盘右键第三行「启动托盘版本」可自动完成双向同步）。

## 兼容性列表（适配关系，修改技能/补丁时必须同步维护）

| 组件 | 版本 | 兼容 DSH 版本 | 说明 |
|---|---|---|---|
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
- **补丁引擎**：应用每个补丁前，读取清单 `compatibleDsh`，与本机当前 DSH 版本（读
  profile `@deepseek-ai/dsh/package.json`）比对；**不匹配 → 跳过 + 提醒**（"请先升级
  DSH 到 X，或将补丁适配到当前版本"），绝不硬装。
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
- 后续优化项（暂不实施）：托盘启动时对渲染出的 node/DSH 路径做存在性校验，失效则重探测并
  重写自身配置；Find-Node 增加 nvm/官方安装目录探测；无可用 node 时给出「请安装 Node.js」的
  明确指引而非静默用私有运行时。

### 配套技能清单与维护（必须同步，缺一不可）

本技能是**主安装包**，`assets\配套技能\` 内置配套脚本技能，setup.ps1 安装时会自动
安装它们。当前配套清单：`zip-archive-ops` / `batch-files` / `charset-pitfalls` /
`skill-install-ops`（安装运维规范，自带版本号与自动进化机制，见其 SKILL.md）。

**每次修改任一配套技能，三连同步**：
1. 打包 `xxx__skillhub.zip`（根目录=技能名）同步到 GitHub 仓库
   `releases\<当前版本>\`（与主包同目录归档）＋ 仓库内配套源树 `dsh-launcher Add\<技能名>\`；
2. 把新 zip 复制进本技能 `assets\配套技能\`（覆盖旧包）；
3. 重打包 `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\`，git commit + push
   （setup.ps1 按时间戳自动分发新版）。

**以后新增脚本技能**（成为一键启动配套的通用规则）：
1. 建好技能（SKILL.md + _meta.json，编码/结构遵守 charset-pitfalls 技能）；
2. 打包 `xxx__skillhub.zip`（根目录=技能名），归档到 GitHub `releases\<当前版本>\`，
   并把源树放进 `dsh-launcher Add\<技能名>\`；
3. 把该 zip 复制进 `dsh-launcher\assets\配套技能\`（setup.ps1 自动扫描该目录下所有
   `*__skillhub.zip`，无需改 setup.ps1）；
4. 重打包并同步 `dsh-launcher__skillhub.zip`（`releases\<当前版本>\`），并把新技能名登记进本清单。

**与 launcher 无关的技能**：zip 不进入本仓库的 releases 配套归档，独立管理。

**归档定位铁律（2026-08-24 用户明确，2026-08-24 修订：用户最终拍板）**：技能是否进
launcher 配套，**最终由用户定义**。AI 只能做预判断（一键启动相关通用运维技能 vs
个性化生产力技能），**判断后必须先征得用户同意，才能执行配套/独立的归档操作**
（进 `assets\配套技能\`、进 `dsh-launcher Add\`、进主包内嵌，或仅放根目录）。
未经用户确认，AI 不得自行决定技能归属并执行归档。当前配套
（`zip-archive-ops` / `batch-files` / `charset-pitfalls` / `skill-install-ops`）
是已获用户认可的历史决定；`cad-scan-eye` 扫描之眼已明确为根目录独立能力。