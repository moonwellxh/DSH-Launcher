# dsh-launcher 交接与维护手册（TRAE Solo）

> **一份文档 = 资产交接清单 + 可执行维护操作手册（已合并去重）。**
> 权威原理/流程：`C:\Users\雍远\.agents\skills\dsh-launcher\SKILL.md`（**动手前先读**）。
> 本文为 2026-08-28 实测快照（1.1.65，GitHub 同步版）+ 可复制命令；执行前先核对第 2、3 节实测值，不凭记忆。

---

## 0. 一句话定位

`dsh-launcher` 是「DSH 一键启动 + 系统托盘」技能：给任意机器安装**启动脚本生成器**（`setup.ps1`），
生成 `启动DSH.bat` / `启动DSH-托盘.vbs/.cmd` / `DSH-tray.ps1` / `dsh.cmd` 等产物，实现托盘常驻、
右键关闭、浏览器就绪后自动打开、补丁自动载入。**它是启动器生成器，不是 DSH 安装器**（从不装/升/卸 DSH 本体）。

---

## 1. 关键路径总表（接收方必存）

| 项 | 值 |
|---|---|
| 本机真实用户名 | `C:\Users\雍远`（**不是** moonw；禁止硬编码 moonw） |
| 启动器安装目录 / 本机工作区 | `D:\DSHS` |
| 技能本体（改这里的源） | `C:\Users\雍远\.agents\skills\dsh-launcher\` |
| 技能副本（就地安装，应保持与本体一致） | `D:\DSHS\`（含 `assets\` 副本） |
| DSH 源码树 | `C:\Users\雍远\deepseek-harness`（源码树模式；`dsh` 不在 PATH 是正常现象） |
| DSH 数据目录 | `C:\Users\雍远\.dsh`（sessions / profiles / patches-backup / .credentials.yaml / settings.yaml） |
| Node.js | `C:\Users\雍远\.workbuddy\binaries\node\versions\22.22.2\node.exe`（v22.22.2） |
| Python | `C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe` |
| 系统代理 | `127.0.0.1:7897`（Clash Verge mixed-port） |
| Web GUI | `http://127.0.0.1:3080` |
| Z 盘 skills 目录 | ~~`Z:\Date_Home\【MoonwelL】\【AI】\My skills`~~（**已弃用**，不再作为同步存档） |
| GitHub 同步仓库 | `https://github.com/moonwellxh/DSH-Launcher`（main 分支，**现同步目标**） |
| GitHub 工作副本（本机缓存） | `C:\Users\雍远\.dsh\gh-sync\DSH-Launcher` |
| GitHub 发布包归档 | 仓库 `releases\v<版本>\`（zip 集中目录，历史版本按目录留档） |
| 补丁备份根 | `C:\Users\雍远\.dsh\patches-backup\<补丁id>\` |
| 本机跨任务记忆 | `D:\DSHS\_记忆\通用记忆.md`（主）+ `路径速查.md`（别名） |

---

## 2. 资产与版本速览

| 资产 | 位置 | 版本 |
|---|---|---|
| 技能本体（AI 会话加载） | `C:\Users\雍远\.agents\skills\dsh-launcher\` | **1.1.65** |
| 技能副本（就地安装工作区） | `D:\DSHS\`（同时是启动器安装目录） | **1.1.65** |
| GitHub 发布包 | 仓库 `releases\v1.1.65\dsh-launcher__skillhub.zip` | **1.1.65** |
| GitHub 历史归档 | 仓库 `releases\v<旧版本>\`（按版本目录留档） | 1.1.64 及更早（git 历史亦保留） |
| 配套技能（4 个，内嵌于主包 `assets\配套技能\`） | 见第 8 节 | 见第 8 节 |
| DSH 本体 | 源码树 `C:\Users\雍远\deepseek-harness\` | **0.1.1-rc.2** |

**同步状态（2026-08-28 实测）**：技能本体 ↔ D:\DSHS 副本关键文件 SHA256 一致；GitHub 仓库
源树/`releases\v1.1.65\` 与本机一致 = 1.1.65。**同步存档已从 Z: 盘全面切换为 GitHub**。

---

## 3. 当前状态快照（覆盖 `_记忆` 的过期快照）

> ⚠️ `D:\DSHS\_记忆\通用记忆.md` 第 10 节「本机状态快照」仍写 **1.1.60**，已过期，以本节实测为准，建议更新该文件。

| 位置 | 版本 |
|---|---|
| 技能本体 `_meta.json` | **1.1.65**（publishedAt 1787854252769） |
| 安装目录 `D:\DSHS\launcher.version` | **1.1.65** |
| GitHub 仓库（源树 + `releases\v1.1.65\`） | **1.1.65** |
| DSH 本体 | **0.1.1-rc.2**（源码树模式） |
| 补丁 `dsh-recycle-bin-v1` | `enabled=true`，兼容 0.1.1-rc.2 ✅，**已应用** |
| 生成产物 | `dsh.cmd`（GBK+chcp936）、`DSH-tray.ps1`（UTF-8 BOM）、`启动DSH.bat`、`启动DSH-托盘.vbs/.cmd`、`run-hidden.vbs` |
| 运行状态 | 托盘与 web(3080) 正常；`dsh-web.log` / `dsh-web.err.log` 在 `D:\DSHS\` |

**1.1.60 → 1.1.65 之间发生了什么**（D:\DSHS 留有 `DSH-tray.ps1.bak-20260827-*` 备份）：

- **1.1.61**：一键托盘入口全面去闪烁——`启动DSH-托盘.cmd` 顶部自隐藏包装（`run-hidden.vbs` 隐藏重入，`__DSH_HIDDEN` 防重入）；新增零窗口双击入口 `启动DSH-托盘.vbs`。
- **1.1.62**：托盘右键第三行文案「一键启动脚本版本」→「一键同步启动脚本」。
- **1.1.64**：同步冲突处理（用户确认制）——时间戳相同但内容不同时，按文件修改时间分析并弹窗展示分析/建议，由用户确认方向（上传/拉取/取消）后才执行；上传前先备份服务器旧包，绝不自动覆盖良包。测试脚本 `D:\DSHS\_tools\dsh-sync-confirm-test.ps1`。
- **1.1.65**：**同步存档全面切换 GitHub**——弃用 Z: 网络盘（NAS）存档；托盘「一键同步」改为 git 双向同步 `moonwellxh/DSH-Launcher`（工作副本 `~\.dsh\gh-sync\DSH-Launcher`）：拉取=与仓库源树 `dsh-launcher/` SHA256 比对后应用并重跑 setup；上传=更新源树 + 重打包 zip 到 `releases\<版本>\` + git add/commit/push（git 历史天然备份旧版，不再手工备份旧包）。git 全程非交互（`GIT_TERMINAL_PROMPT=0`），缺凭据立即报错。

---

## 4. 文件地图：改哪里 / 不要改哪里

### 4.1 ✅ 可改（源，setup.ps1 据此生成）

`C:\Users\雍远\.agents\skills\dsh-launcher\` 下的：

| 文件 | 作用 |
|---|---|
| `assets\setup.ps1` | **核心安装/生成器**：探测 DSH → 生成启动脚本/快捷方式 → 按补丁清单打补丁 |
| `assets\tmpl\parts\*.ps1` + `mode-*.json` | 托盘本体模板片段（setup.ps1 按模式拼装成 DSH-tray.ps1） |
| `assets\tmpl\dsh.cmd.tmpl` / `dsh.cmd.path.tmpl` | CLI 包装模板（两种模式） |
| `assets\启动DSH.bat` | 菜单启动器源 |
| `assets\启动DSH-托盘.vbs` | 零窗口一键托盘入口源 |
| `assets\启动DSH-托盘.cmd` | 自隐藏一键托盘入口源 |
| `assets\run-hidden.vbs` | .cmd 自隐藏重入辅助 |
| `assets\更新安装.cmd` | 一键更新：覆盖技能 + 重跑 setup + 刷新快捷方式 + 启动托盘 |
| `_meta.json` / `SKILL.md` / `_icon.png` | 版本元数据 / 主文档 / 图标 |
| `assets\配套技能\*.zip` | 4 个配套技能安装包 |
| `assets\补丁管理\*` | 补丁自动载入清单全套 |

### 4.2 ⛔ 不要直接改（生成物，改了也会被 setup.ps1 覆盖，且运行中的是它们）

`D:\DSHS\` 下的 `DSH-tray.ps1`、`dsh.cmd`、`启动DSH.bat`、`启动DSH-托盘.vbs/.cmd`、`run-hidden.vbs`、`launcher.version`。

> 改完技能本体的源后，`D:\DSHS\assets\` 副本要同步一致（关键文件 SHA256 一致），否则从 D:\DSHS 跑 setup 会用旧源。

### 4.3 本机扩展文件（仅 D:\DSHS，不在技能包内，交接时勿丢）

`README.md`（日常使用说明）、`_记忆\通用记忆.md`（跨任务记忆主文件）、`_记忆\路径速查.md`、
`_tools\dsh-session-decompress.js` / `dsh-session-extract.js`（会话解压/抽取）、
`_tools\dsh-sync-confirm-test.ps1`（1.1.64 同步确认制回归测试）、
`升级\升级DSH后重新渲染-标准说法.md`、`升级\智谱AI开放平台费用明细2026-08_*.xlsx`。

---

## 5. 铁律（违反任何一条都可能出事故）

1. **只改模板/源 → setup.ps1 重新生成 → 语法验证 → 备份 → 重启托盘**。绝不直接编辑运行中的生成物（08-25 事故：差点全盘瘫痪）。
2. **编码**：`.cmd/.bat` = GBK + CRLF、无 BOM；`.ps1` 含中文 = **UTF-8 带 BOM**；`.md/.json/.txt` = UTF-8 无 BOM。
3. **改内容必升版本**：`_meta.json` 的 `version` + `publishedAt` 一起动；禁止只改内容不升版本（同步误判"时间戳相同内容不同"→人工复核，多机合并无法辨新旧）。
4. **绝不自动覆盖远端良包**：覆盖前内容级比对；时间戳相同但内容不同时，托盘弹窗由用户拍板（1.1.64 起；1.1.65 起远端=GitHub，git 历史保留旧版）。
5. **脚本内部调用一律绝对路径**，禁止裸命令名（cmd 当前目录优先于 PATH 的劫持陷阱，08-23 托盘 15s 循环事故）。
6. **补丁绑定 DSH 版本**：DSH 升级前必须先挂起所有补丁（manifest `enabled=false`），否则旧载荷覆盖新版包 → 前端渲染故障（08-23 事故）。

---

## 6. 标准操作流程（命令可复制）

### 6.1 日常使用

- 启动 Web：双击桌面「启动DSH」快捷方式 或 `启动DSH-托盘.vbs`（推荐，零窗口）。
- 关闭：托盘右键 →「退出并停止 DSH」（`taskkill /PID <3080监听PID> /T /F` 停整棵进程树）。
- 菜单：`启动DSH.bat`（1 托盘+Web / 2 TUI / 3 Headless / 0 退出）。
- 托盘右键顶部三行：DSH 版本（点开 deepseekdocs.com）/ 最新版本（可更新时点升级）/
  「启动托盘 x.x.x 版（点击可更新/已是最新）」（点击与 GitHub 双向同步，SHA256 内容级比对，冲突时用户确认制）。

### 6.2 改托盘 / 启动器 → 重新生成 → 重启托盘（最常用）

```powershell
# ① 改源：只改 assets\tmpl\parts\*.ps1 / mode-*.json 或 assets\*.cmd/.vbs（按第 9 节编码方式写）
# ② 语法验证（可用仓库根目录 verify_parts.py 检查无残留占位符）
python verify_parts.py   # 无报错=OK

# ③ 备份当前良版生成物
Copy-Item D:\DSHS\DSH-tray.ps1 "D:\DSHS\DSH-tray.ps1.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# ④ 重新生成（幂等；自动按清单打补丁——已应用会跳过）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\雍远\.agents\skills\dsh-launcher\assets\setup.ps1" -InstallDir D:\DSHS -NoShortcut

# ⑤ 验证生成物语法 + 版本
$null=[scriptblock]::Create((Get-Content -Raw -LiteralPath D:\DSHS\DSH-tray.ps1 -Encoding UTF8))
Get-Content D:\DSHS\launcher.version
```

**重启托盘（安全命令，含"命令自伤"坑）**：

> **坑（实测）**：若用宽泛正则 `-match 'DSH-tray\.ps1'` 筛进程，而运行命令的 powershell 本身命令行里含
> `DSH-tray.ps1` 字样，会把**自己**也匹配进去杀掉（命令无输出、退出码 -1/4294967295）。因此必须：
> ① 用精确 `-File` 模式；② 排除 `$PID`。

```powershell
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -match '-File\s+[^\s]*DSH-tray\.ps1' -and $_.ProcessId -ne $PID } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1
Start-Process -FilePath "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','D:\DSHS\DSH-tray.ps1' `
  -WindowStyle Hidden
```

> 托盘菜单「重启 DSH」会杀 web 再重启（中断会话）——**日常改脚本用上面的手动重启，别点菜单重启**。

### 6.3 只改文档 / 图标（不涉及生成）

改 `SKILL.md` / `_meta.json` / `_icon.png` → 重装技能即可（解压 zip 覆盖 `~/.agents/skills\dsh-launcher`），无需重跑 setup。
改 `_meta.json` 版本时同时更新 `publishedAt`：`[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()`。

### 6.4 同步 GitHub 仓库（源树 + releases 归档 + git 推送）

> 同步存档已从 Z: 盘切换为 GitHub，托盘右键第三行可自动完成（见 6.1）；
> 以下为 AI/手动侧的对齐命令（git 历史 = 旧版本天然备份，无需手工备份旧包）。

```powershell
$repo  = 'https://github.com/moonwellxh/DSH-Launcher.git'
$cache = "$env:USERPROFILE\.dsh\gh-sync\DSH-Launcher"
if (-not (Test-Path "$cache\.git")) { git clone -b main --depth 1 $repo $cache }   # 首次
git -C $cache fetch origin main; git -C $cache reset --hard origin/main            # 对齐最新
# ① 更新源树：本机技能目录复制进 $cache\dsh-launcher（或反向应用回本机）
# ② 重打包 zip 到 releases\<版本>\：
#   & 'C:\Windows\System32\tar.exe' -a -cf "$cache\releases\v<版本>\dsh-launcher__skillhub.zip" -C $cache 'dsh-launcher'
# ③ 提交推送：
git -C $cache add -A
git -C $cache commit -m "dsh-launcher v<版本> 同步"
git -C $cache push origin main
# ④ 写盘后校验 zip：按 zip-archive-ops 技能
```

> **GitHub 网络与凭据**：国内环境需 git 已配置代理（`http.proxy`）；托盘同步在隐藏窗口
> 非交互运行（`GIT_TERMINAL_PROMPT=0`），push 缺凭据会立即报错——提前用 credential
> manager / SSH key 配好凭据。

### 6.5 打补丁 / 还原补丁

```powershell
$pe = 'C:\Users\雍远\.agents\skills\dsh-launcher\assets\补丁管理\补丁引擎-应用还原检查.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File $pe -CheckOnly   # 检查（列计划=已应用）
powershell -NoProfile -ExecutionPolicy Bypass -File $pe              # 应用（幂等，已应用跳过）
powershell -NoProfile -ExecutionPolicy Bypass -File $pe -Restore     # 还原官方原状
```

### 6.6 DSH 升级 + 补丁安全顺序（用户规定，固定执行）

1. 更新 DSH：源码树 `git pull` → `pnpm install` → `pnpm build`；npm 则 `npm update -g @deepseek-ai/dsh`。
2. 挂起补丁：manifest 全部 `enabled=false`。
3. 分析兼容性（dsh-launcher 本体 + setup.ps1 + 模板 + 配套技能 + 补丁清单）；兼容的先装，不兼容的给报告。
4. **用户决策**：修改/重写/搁置由用户定，未经同意不得启用不兼容项。
5. 重启 dsh web，验证版本号、会话历史可加载、消息有反馈；**浏览器 Ctrl+F5 硬刷新**。

---

## 7. 补丁专章（信息最易丢的部分）

### 7.1 补丁登记（`assets\补丁管理\自动载入清单-manifest.json`）

| 字段 | 值 |
|---|---|
| id | `dsh-recycle-bin-v1` |
| 目录 | `补丁01-档案柜v1-归档升级版` |
| 名称 | 档案柜 v1（归档升级版：移入档案柜 + 底部档案柜分区 + 恢复） |
| 版本 | 0.1.1 |
| **compatibleDsh** | **仅 0.1.1-rc.2**（载荷绑定版本！） |
| enabled | **true** |
| requiresRestart | true（应用后需重启 dsh web） |

**功能**：会话 ⋯ 菜单「移入档案柜」+ 侧边栏底部「档案柜」分区（默认折叠）+ 恢复；新增 RPC `workspace.restoreSession`。
**载荷**（5 个，覆盖 profile 的 @deepseek-ai 包）：`dsh-client-connection\lib\client.js`、
`dsh-client-runtime\lib\client.js`、`dsh-client-ui-workspace\lib\client.js`、
`dsh-host-apiproxy\lib\index.js`、`dsh-workspace\lib\index.js`。

### 7.2 应用状态

已应用 ✅：`C:\Users\雍远\.dsh\patches-backup\dsh-recycle-bin-v1\` 含 `backup-manifest.json` + 5 个 `orig__*`。
校验：`补丁引擎-应用还原检查.ps1 -CheckOnly`。注意还原成功后备份目录被删，以「备份 manifest 非空」为准。

### 7.3 补丁红线（08-23 事故）

> 载荷绑定 DSH 版本。DSH 升级后**绝不能直接重跑 setup 应用旧补丁**——profile 的 @deepseek-ai 包是
> junction 指向源树 `apps/cli/node_modules`，覆盖即改坏新版构建产物。安全做法：升级前挂起补丁 →
> 升级 → 分析兼容（`compatibleDsh` 自动校验，不匹配跳过+提醒）→ 用户决策 → 重启验证。
> 已误覆盖则从 npm 拉对应版本纯净包恢复，或 `pnpm build` 全量重建。

### 7.4 新增/修改补丁三步

① 写载荷与安装/还原脚本到 `assets\补丁管理\补丁NN-功能名\`（id 决定备份目录名，dir 决定源码子目录名）
→ ② manifest 登记（`enabled:true` + 填 `compatibleDsh`）→ ③ 同步 `assets\补丁管理\` 并重打包 zip。临时停用置 `enabled=false` 即可。

---

## 8. 配套技能交接（主包内嵌，setup.ps1 自动安装）

| 技能 | GitHub 位置 | 版本 |
|---|---|---|
| `zip-archive-ops` | 仓库 `releases\<当前版本>\` + 源树 `dsh-launcher Add\` + 主包内嵌 | 1.0.4 |
| `charset-pitfalls` | 仓库 `releases\<当前版本>\` + 源树 `dsh-launcher Add\` + 主包内嵌 | 1.1.3 |
| `batch-files` | 仓库 `releases\<当前版本>\` + 源树 `dsh-launcher Add\` + 主包内嵌 | 1.1.3 |
| `skill-install-ops` | 仓库 `releases\<当前版本>\` + 源树 `dsh-launcher Add\` + 主包内嵌 | 1.1.2 |

- 分发只需一个包 `dsh-launcher__skillhub.zip`；配套技能变更后**三连同步**：① 打包 `xxx__skillhub.zip` 归档到 GitHub `releases\<当前版本>\`＋更新仓库源树 `dsh-launcher Add\<技能名>\`；② 复制进 `assets\配套技能\` 覆盖旧包；③ 重打包主包到 `releases\<当前版本>\` 并 git commit + push。并递增该技能 `_meta.json` version/publishedAt。
- **归档定位铁律（用户明确）**：技能是否进 launcher 配套，**最终由用户拍板**；AI 只能预判（通用运维→配套，个性化生产力→根目录独立），判断后必须先征得用户同意。当前 4 个是历史决定；`cad-scan-eye` 为根目录独立能力。

---

## 9. 编码自检与安全写入（最高频踩坑）

| 要写/读 | 命令 |
|---|---|
| 读 GBK `.cmd` | `[System.IO.File]::ReadAllText($p, [System.Text.Encoding]::GetEncoding(936))` |
| 写 GBK `.cmd`（CRLF、无 BOM） | `$gbk=[Text.Encoding]::GetEncoding(936); [IO.File]::WriteAllBytes($p, $gbk.GetBytes(($c -replace "`r?`n","`r`n")+"`r`n"))` |
| 写 `.ps1`（含中文，UTF-8 **带 BOM**） | `$u8=New-Object Text.UTF8Encoding($false); [IO.File]::WriteAllBytes($p, ([byte[]](0xEF,0xBB,0xBF))+$u8.GetBytes($c))` |
| 查 BOM | `[System.IO.File]::ReadAllBytes($p)[0..2] -join ','`（`239,187,191` = UTF-8 BOM） |
| 语法验证 `.ps1`（不改文件） | `$null=[scriptblock]::Create((Get-Content -Raw -LiteralPath $p -Encoding UTF8))` |

> AI 工具（含 TRAE）默认写 UTF-8 **无 BOM**：写含中文 `.ps1` 后必须补 BOM，否则 PS 5.1 按 GBK 误读 → 中文路径 DirectoryNotFound / 语法报错。

---

## 10. 排障速查

| 症状 | 处理 |
|---|---|
| 托盘图标不出现 | 结束残留 DSH-tray 进程 → 重新启动（第 6.2 节） |
| 双击 .cmd 闪命令行窗口 | 用 `启动DSH-托盘.vbs`（零窗口）或桌面「启动DSH」快捷方式；.cmd 已自隐藏 |
| 浏览器 `Failed to load plugins ... pending` | 服务未就绪就打开；等 `dsh-web.log` 出现 `dsh web: http://...` 再刷新 |
| 端口 3080 被占用 | 视为 DSH 已在运行，只开浏览器不重复启动 |
| 启动失败 | 先看 `D:\DSHS\dsh-web.err.log`；就绪与否看 `dsh-web.log` |
| 托盘图标未变 | 图标启动时读取，改 `tray.ico` 后需退出托盘再启动 |
| 托盘 15s 循环/鬼影图标 | 旧 buggy 托盘未清：结束所有 DSH-tray 进程，重跑 setup 重新生成后重启 |
| 补丁未生效 | `补丁引擎-应用还原检查.ps1 -CheckOnly`；`~\.dsh\patches-backup\<id>\` 有备份=已应用 |
| 升级后界面旧内容/"DSH Local Build" | **Ctrl+F5 硬刷新** 3080（插件 rev 哈希缓存） |
| 同步弹"时间戳相同/人工复核" | 内容改了但没升版本 → 升版本 + 重新同步（或托盘弹窗按分析选方向） |
| 快捷方式图标不更新 | `ie4uinit.exe -show`；仍不行杀 Explorer 删 iconcache 重启 |
| 0xc0000142 偶发 | 密集拉进程触发，避免连拉；非持续故障 |
| New-Object 括号参数报错 | 含算术用 `New-Object ... -ArgumentList @(…)`，别用 `New-Object X(a, b-1)` |

---

## 11. 改完必测 + 交付 + 验证清单

### 11.1 改完必测

```powershell
# 同步冲突用户确认制回归测试（期望末尾 PASS=19 FAIL=0）
powershell -NoProfile -ExecutionPolicy Bypass -File D:\DSHS\_tools\dsh-sync-confirm-test.ps1
```

改同步相关逻辑后必须重跑；改其它部分至少做第 9 节语法验证。

### 11.2 交付前核对

- `_meta.json` version/publishedAt 已升（改了内容就升）
- `D:\DSHS\assets\` 与技能本体关键文件一致
- 托盘已用新脚本重启、web 正常
- **GitHub 推送等用户测试满意后再做**（改完不自动推；用户点托盘第三行「启动托盘版本」或按 6.4 手动提交推送）

### 11.3 首日验证清单

- [ ] `SKILL.md` / `_meta.json` / `launcher.version` / GitHub `releases\v1.1.65\` zip 内版本一致（1.1.65）
- [ ] 生成物正常：`dsh.cmd`、`DSH-tray.ps1`（UTF-8 BOM）、`启动DSH-托盘.vbs` 存在
- [ ] 补丁已应用：`~\.dsh\patches-backup\dsh-recycle-bin-v1\` 含 backup-manifest.json + 5 个 orig 文件
- [ ] `补丁引擎-应用还原检查.ps1 -CheckOnly` 可跑
- [ ] 托盘右键三行正常（版本 / 最新版本 / 启动托盘版本）
- [ ] web(3080) 可访问、会话历史可加载、消息有反馈
- [ ] GitHub 仓库源树 + `releases\` 归档可读；托盘「启动托盘版本」行可连通 GitHub（clone/fetch 正常）
- [ ] 已更新 `_记忆\通用记忆.md` 第 10 节过期快照（1.1.60 → 1.1.65）
- [ ] 通读本文第 5 节铁律 + 7.3 补丁红线

---

## 12. 版本历史摘要（1.1.48 → 1.1.65，详见 SKILL.md 兼容性列表）

| 版本 | 变更要点 |
|---|---|
| 1.1.48 | 配套技能版本比较改为「版本号优先、时间戳兜底」 |
| 1.1.51 | P0-P2 全面修复（补丁引擎 $LASTEXITCODE 陷阱/还原 enabled、托盘重启链编码、更新安装.cmd 降级等） |
| 1.1.52 | 修复还原失败时 manifest 丢失成功项的回归 + 文档验证口径同步 |
| 1.1.53-57 | 托盘双击/「打开 Web UI」优先打开已装 PWA 主应用（SC_RESTORE 聚焦 + IsZoomed 保护 + 未装引导式安装） |
| 1.1.58 | 固化调试纪律铁律（绝不在运行中生成物上直接编辑） |
| 1.1.59 | 「重启 DSH」改版：杀 web + 按标题关闭 DSH 浏览器窗口（WM_CLOSE）+ helper 接力重启；所有 Start-Process powershell 加 `-WindowStyle Hidden` |
| 1.1.60 | 修复托盘右键「最新版本」查询失败：强制 TLS1.2 + 优先直连（Clash 7897 环境实测需要）、失败回退系统代理 |
| 1.1.61 | 一键托盘入口全面去闪烁：`.cmd` 自隐藏包装（run-hidden.vbs）+ 新增零窗口 `.vbs` 入口 |
| 1.1.62 | 托盘右键第三行文案：「一键启动脚本版本」→「一键同步启动脚本」 |
| 1.1.64 | 同步冲突处理（用户确认制）：时间戳相同内容不同 → 分析展示 → 用户确认方向；绝不自动覆盖良包 |
| 1.1.65 | **同步存档全面切换 GitHub**：弃用 Z: 盘（NAS）存档；托盘「一键同步」改为 git 双向同步 `moonwellxh/DSH-Launcher`（源树 SHA256 比对 + 上传重打包 zip 到 `releases\<版本>\` + git add/commit/push；git 历史天然备份旧版，不再手工备份旧包） |

**补丁历史**：档案柜 v1 最初基于 0.1.0-rc.7，2026-08-23 重新适配 0.1.1-rc.2（对每个目标文件 diff 旧原始 vs 旧补丁提取增量，再按新版上下文套用）。当前 `compatibleDsh="0.1.1-rc.2"`。

---

## 13. 风险与未决事项

1. **`_记忆\通用记忆.md` 状态快照过期**（写 1.1.60，实际 1.1.65）——需更新，本文第 3 节可作依据。
2. **补丁与 DSH 版本强绑定**：档案柜 v1 仅适配 0.1.1-rc.2。下次 DSH 升级必须先挂起补丁（6.6 流程），否则可能重演 08-23 前端渲染故障。
3. **GitHub 网络与凭据**：国内环境需 git 已配置代理；托盘同步非交互运行（`GIT_TERMINAL_PROMPT=0`），push 缺凭据会立即报错——须提前用 credential manager / SSH key 配好凭据；多机并发 push 罕见，冲突时以 git 提示为准人工合并。
4. **PWA 主应用依赖 Edge 手动安装**：Edge 无静默安装命令行，新机器需引导用户手动「安装为应用」一次。
5. **本文为快照文档**：后续版本变更、补丁增删、路径变化，应在 `SKILL.md` 兼容性列表与 `_记忆\通用记忆.md` 同步更新。

---

*交接完成标志：接收方（TRAE Solo）能独立回答「技能版本是多少 / 补丁状态如何 / 升级 DSH 该按什么顺序 / 出问题先查什么」四个问题，且能复现第 11.3 节验证清单全部条目。*
