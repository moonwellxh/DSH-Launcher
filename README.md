# dsh-launcher — DSH魔偶助手 一键启动 + 系统托盘

> **当前版本：1.1.80** · 适配 DSH：`0.1.0-rc.7` / `0.1.1-rc.2` · 平台：Windows（PowerShell 5.1+）

`dsh-launcher` 是 DeepSeek Harness（DSH）的**一键启动器生成器**：给任意一台已装 DSH 的
Windows 机器安装「一键启动 + 系统托盘手动关闭」方案。它生成 `启动DSH.bat` 菜单启动器、
`DSH-tray.ps1` 系统托盘（托盘常驻、右键关闭服务、浏览器就绪后自动打开、PWA 主应用优先）、
`dsh.cmd` CLI 包装，并自动按清单加载补丁。

> ⚠️ **边界声明**：它是**启动器生成器，不是 DSH 安装器**。从不安装 / 升级 / 卸载 DSH 本体，
> 不运行 npm/pnpm，不改 PATH。DSH 的安装与升级由用户负责。

---

## 💡 强烈推荐：把 DSH 安装为 PWA 应用（外观与原生应用无差别）

DSH 的 Web UI（http://127.0.0.1:3080）本质是网页，但**只需在 Edge 里点一次「安装为应用」**，
即可获得与正常桌面应用无差别的体验：

- **独立应用窗口**：不再有浏览器标签页 / 地址栏，像原生应用一样独立成窗、可最小化/最大化/贴靠。
- **任务栏常驻**：拥有独立图标，可固定到任务栏，一键唤起，与普通软件无异。
- **托盘双击直达**：安装后，托盘双击 / 「打开 Web UI」**自动优先打开 PWA 主应用**
  （独立窗口、聚焦不重复开多个），而非普通浏览器标签页。

**安装方法（一次性，约 10 秒）：**

1. 启动 DSH，浏览器自动打开 `http://127.0.0.1:3080`（或托盘双击）。
2. 在 Edge 地址栏右侧点击**安装图标**（显示器 + 加号），选择「**安装**」/「**安装为应用**」→ 确认。
3. 完成。此后：
   - 托盘双击、「打开 Web UI」、桌面 **`DSH应用.lnk`**（setup.ps1 检测到 Edge 时自动创建）
     都会直接唤起 PWA 应用窗口；
   - 最小化时再双击托盘，会自动**恢复并置顶**已有的 PWA 窗口（不会新开一堆窗口）。

> 未安装 PWA 时，托盘双击不会默默开普通网页，而是打开 Edge 并气泡提示
> 「点安装图标安装为独立应用」，点一下即完成。Edge 不支持命令行静默安装，这步需手动点一次；
> 安装后如需卸载，可在 Edge `edge://apps` 或系统「应用」中管理。

## ✨ 特性

- **自适应探测**：自动识别 DSH 安装方式（PATH 全局安装 / `deepseek-harness` 源码树 + node），
  生成适配的启动脚本与托盘。
- **系统托盘常驻**：右键菜单一键关闭 DSH（杀整棵进程树）、硬重启托盘、打开 Web UI / TUI / Headless。
- **浏览器就绪后自动打开**：等待 `dsh web` 打印就绪信号，避免过早打开导致前端报错；
  优先打开已「安装为应用」的 PWA 主应用（无则引导安装）。
- **零窗口入口**：`启动DSH-托盘.vbs`（wscript 直启，零命令行窗口）与自隐藏 `.cmd` 入口，双击不闪屏。
- **补丁自动载入**：`assets\补丁管理\` 内置补丁引擎，随安装自动按清单打补丁（幂等、可挂起、可一键还原）。
- **配套技能一体分发**：只需分发一个 `dsh-launcher__skillhub.zip`，安装时自动携带 4 个配套技能。
- **单一来源配置**：同步仓库 / 分支 / 候选分支收敛到 `assets\sync-defaults.json` 一处定义，
  setup.ps1 渲染时注入所有生成物（dsh-sync.ps1 / 凭证脚本 / 托盘模板），**改一处全局生效**。
- **一键同步（GitHub）**：托盘右键「DSH魔偶助手」行与 GitHub 仓库 `moonwellxh/DSH-Launcher`
  做 git 双向同步（源树逐文件 SHA256 比对，方向按版本号优先、时间戳兜底；冲突时用户确认制；
  上传自动更新源树 + 重打包 5 个 zip 归档到 `releases\<版本>\` + 提交推送）。
- **同步分支切换**：托盘右键「切换同步分支」对话框——下拉列出 `sync-defaults.json` 的固定候选，
  可点「获取已有分支」动态拉取 GitHub 现有分支补入列表，也可手动输入任意分支；选择后写入
  `~\.dsh\gh-sync\config.json` 并重启托盘生效。

---

## 📦 仓库结构

```
DSH-Launcher/
├── README.md                        ← 本文件（仓库说明）
├── dsh-launcher-交接与维护手册-TRAESolo.md  ← 资产交接清单 + 可执行维护操作手册（先读它）
├── dsh-launcher/                    ← 主技能源树（**维护对象**）
│   ├── SKILL.md                     ← 技能主文档（安装/用法/排障/兼容性）
│   ├── _meta.json                   ← 版本元数据（version / publishedAt / compatibleDsh）
│   ├── 就地安装.bat                 ← 绿色安装：注册技能 + 就地生成启动器
│   └── assets/
│       ├── setup.ps1                ← 核心安装/生成器（探测 DSH → 渲染模板 → 按清单打补丁）
│       ├── sync-defaults.json       ← 单一来源：同步 repo / branch / branches 候选（改这一处即可）
│       ├── dsh-sync.ps1             ← 同步 CLI（托盘「一键同步」调用；setup 渲染占位符后部署）
│       ├── configure-git-credentials.vbs ← 托盘 5 连击打开的 token 配置脚本（写 gh-sync config.json）
│       ├── tmpl/                    ← 托盘与 CLI 包装模板（parts/ 片段 + mode-*.json + setup.ps1 拼装生成）
│       ├── 启动DSH.bat / 启动DSH-托盘.cmd / 启动DSH-托盘.vbs / run-hidden.vbs / 更新安装.cmd
│       ├── 配套技能/                ← 内嵌 4 个配套技能 zip（setup.ps1 自动安装）
│       ├── 补丁管理/                ← 补丁引擎 + 自动载入清单 + 补丁01-档案柜v1
│       └── 图标（tray.ico / whale*.ico / whale-white.png）
├── dsh-launcher Add/                ← 4 个配套技能的**源树**
│   ├── batch-files/  charset-pitfalls/  skill-install-ops/  zip-archive-ops/
└── releases/                        ← **zip 集中归档目录（历史版本按目录留档）**
    ├── v1.1.66 … v1.1.78 …          ← 历史版本（主包 + 配套包）
    └── v1.1.80/                     ← 当前版本（dsh-launcher__skillhub.zip 等 5 个 zip）
```

---

## 🚀 快速开始（Windows）

### 方式 A：作为 DSH 技能使用（有 AI 协助时，推荐）

1. 解压 `dsh-launcher__skillhub.zip` 到 DSH 技能目录 `~/.agents/skills/dsh-launcher`
   （zip 根目录 = 技能名；可从仓库 `releases\v1.1.80\dsh-launcher__skillhub.zip` 下载）。
2. 运行安装脚本（AI 或手动均可）：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "<技能目录>\assets\setup.ps1"
   ```

   脚本自动探测 DSH、生成适配脚本、默认创建桌面快捷方式，并**自动安装 4 个配套技能**。

### 方式 B：作为绿色软件使用（无 AI 时，纯复制）

1. 解压 zip 到任意位置（如 `F:\DSH\dsh-launcher\`）。
2. 双击解压目录里的 **`就地安装.bat`** ——自动完成：① 注册技能到 `~/.agents/skills\dsh-launcher`；
   ② 以自身所在目录为安装目录，就地生成托盘 / 启动脚本 / 桌面快捷方式。

### setup.ps1 参数

```powershell
setup.ps1                          # 自动探测并安装到 %USERPROFILE%\DSH
setup.ps1 -InstallDir D:\DSHS      # 指定安装目录
setup.ps1 -NoShortcut              # 不建桌面快捷方式
setup.ps1 -CheckOnly               # 只探测、打印结果，不安装
```

> ⚠️ **安装/更新本技能后的强制步骤**：必须重跑一次 `setup.ps1`（它会重新生成启动脚本并自动
> 按清单应用补丁）。跳过此步 = 技能更新不完整（补丁未打）。

### 更新已装机器

把新 zip 放到 `assets\` 目录（或直接拖到脚本上），双击 **`assets\更新安装.cmd`** ——自动完成
「解压覆盖技能 + 重跑 setup.ps1（自动应用补丁）+ 刷新桌面快捷方式 + 自动启动托盘」。

---

## 📄 生成产物（写入安装目录）

| 文件 | 作用 |
|---|---|
| `启动DSH.bat` | 菜单启动器（1 托盘+Web / 2 TUI / 3 Headless / 0 退出） |
| `启动DSH-托盘.cmd` | 一键托盘（自隐藏窗口，双击不闪命令行窗口） |
| `启动DSH-托盘.vbs` | 一键托盘（零命令行窗口，推荐双击入口） |
| `DSH-tray.ps1` | 系统托盘本体（右键菜单：DSH 版本 / 最新版本 / 魔偶助手 / 魔偶Git版本 / **切换同步分支** / 打开 Web UI / TUI / Headless / 硬重启托盘 / 退出并停止） |
| `dsh-sync.ps1` | 同步 CLI（托盘「一键同步」调用；由 setup.ps1 渲染占位符后部署） |
| `configure-git-credentials.vbs` | token 配置脚本（托盘魔偶助手行 5 连击打开） |
| `dsh.cmd` | CLI 入口包装（`--version` / TUI / Headless） |
| `launcher.version` | 启动器版本号 |

---

## 🔄 同步与分支切换

### 一键同步（托盘「魔偶Git版本」行）

- 配置优先级：环境变量 `DSH_SYNC_REPO` / `DSH_SYNC_BRANCH` / `DSH_SYNC_TOKEN` >
  `~\.dsh\gh-sync\config.json` > 内置默认（来自 `sync-defaults.json`）。
- 方向判定：**版本号优先、时间戳兜底**；时间戳相同但内容不同时弹窗展示分析，由用户确认
  （上传 / 拉取 / 取消），**绝不自动覆盖良包**。
- 网络：自动探测系统代理，直连 ↔ 代理双路回退（命令级 `-c` 注入，不改全局 git 配置）；
  git 全程非交互（禁终端提示 + 禁 GCM 弹窗）。
- 上传 = 更新源树 + 重打包 5 个 zip（主包 + 4 配套）到 `releases\<版本>\` + git 提交推送
  （`HEAD:<branch>`，token 经 http.extraheader 仅内存注入，不落盘不打印）。

### 切换同步分支（托盘「切换同步分支」行）

- 下拉候选 = `sync-defaults.json` 的 `branches` 数组（固定列表）。
- **「获取已有分支」按钮**：`git ls-remote --heads` 动态拉取 GitHub 现有分支，去重后追加到
  下拉列表（与固定候选并存，不覆盖）；git 自动探测常见安装路径 / GitHub Desktop / PATH 兜底。
- 也支持**手动输入**任意分支名。
- 选择后写入 `~\.dsh\gh-sync\config.json` 的 `branch` 字段（保留 repo/token），并自动重启托盘生效。

### token 配置

私有仓库读写需配置 PAT：托盘右键「DSH魔偶助手」行 **3 秒内左键连点 5 次** → 打开
`configure-git-credentials.vbs`（Windows 原生 InputBox，零控制台闪现）→ 输入 token →
写入 `~\.dsh\gh-sync\config.json`（UTF-8）。

---

## 🩹 补丁机制（`assets\补丁管理\`）

- **自动载入清单** `自动载入清单-manifest.json`：登记补丁（`enabled` 标记挂起/启用，
  `compatibleDsh` 校验适配的 DSH 版本）。
- **补丁引擎** `补丁引擎-应用还原检查.ps1`：应用 / 还原 / 检查（`-Restore` / `-CheckOnly`），
  幂等，已应用自动跳过；**不匹配 DSH 版本会跳过并提醒，绝不硬装**。
- **已登记补丁**：`补丁01-档案柜v1-归档升级版`（id `dsh-recycle-bin-v1`，适配 **仅 0.1.1-rc.2**，
  已启用）——会话「移入档案柜」+ 侧边栏「档案柜」分区 + 恢复，新增 RPC `workspace.restoreSession`。
- **升级安全红线**：DSH 升级前必须先将清单中所有补丁 `enabled=false`（全部挂起），升级并分析
  兼容性后再由用户拍板是否启用，防止旧载荷覆盖新版构建产物（曾引发前端渲染故障事故）。

---

## 🧩 配套技能（随主包自动安装）

| 技能 | 版本（zip 内） | 用途 |
|---|---|---|
| `zip-archive-ops` | 1.0.5 | zip 归档打包/校验/修复 |
| `charset-pitfalls` | 1.1.6 | Windows 中文编码避坑汇总（GBK/UTF-8/BOM） |
| `batch-files` | 1.1.4 | Windows 批处理专家级写作/调试 |
| `skill-install-ops` | 1.1.4 | 技能安装运维规范（自带版本号与自动进化机制） |

> 分发只需 `dsh-launcher__skillhub.zip` 一个包。任一配套技能变更后需**三连同步**：
> ① 打包 `xxx__skillhub.zip` 归档到 GitHub `releases\<当前版本>\`＋更新源树 `dsh-launcher Add\<技能名>\`；
> ② 复制进 `assets\配套技能\` 覆盖旧包；③ 重打包主包并 git commit + push，且递增该技能
> `_meta.json` 的 version / publishedAt。

---

## 🧰 版本与兼容性

| 组件 | 版本 | 兼容 DSH |
|---|---|---|
| dsh-launcher | 1.1.80 | 0.1.0-rc.7、0.1.1-rc.2 |
| 档案柜 v1 补丁 | 0.1.1 | **仅 0.1.1-rc.2**（载荷绑定版本） |

版本历史（1.1.66 → 1.1.80）要点：

- **1.1.66** 一键同步发布级重写：配置化 repo/branch/token（env > config.json > 默认），代理自动探测双路回退，错误分类引导，文本归一化比对，5 zip 发布
- **1.1.67** 代码审查 bug 修复批次（B1–B24）：补丁引擎改子进程调用、就地安装.bat 守卫、更新安装.cmd 降级改 .NET、删除死代码（70-sync-*.ps1、废弃 .tmpl）
- **1.1.68** 双击 PWA 打开链路易损性修复（Edge 检测 / `--app` 兜底 / Find-Node 排除 agent 环境 node.cmd）
- **1.1.69** DSH 改用通用 Node.js 运行（启动 web 前清理宿主 agent kimi daimon 注入的环境变量）
- **1.1.70** 同步方向判定升级为「版本号优先、时间戳兜底」；配套 charset-pitfalls 升 1.1.6
- **1.1.71** 环境清理匹配扩展 kimi-work
- **1.1.72** 托盘第三行文案「启动器版本 xx 版」；Get-GhLauncherVersion 带 token 检测；dsh-sync 凭证类通配排除；收编 configure-git-credentials.ps1
- **1.1.73** 托盘右键菜单拆行：第三行「DSH魔偶助手」（5 连击配置 token）、第四行 Git 版本/同步
- **1.1.74** 第三行「DSH魔偶助手」加粗
- **1.1.75** 第三行单击保持菜单打开；5 连击改 wscript 启动 configure-git-credentials.vbs（原生 InputBox 无控制台闪现）
- **1.1.76** 新增「发布前检查清单」章节（改动 → setup 生成 → 人工检查 → 确认 OK 才 bump + 同步）
- **1.1.77** 发布前检查清单补第 5 步（同步完成后重启服务 + web 界面）
- **1.1.78** 托盘「重启 DSH」改名「硬重启托盘」，点击先跑 setup.ps1 再重启托盘
- **1.1.79** **同步配置收敛为单一来源 `sync-defaults.json`**（repo/branch/branches 一处定义，占位符 `__GH_REPO__`/`__GH_BRANCH__`/`__GH_BRANCHES__` 由 setup.ps1 渲染注入所有生成物）；托盘新增「切换同步分支」菜单（候选 + 手动输入，写 config.json 并重启托盘）；同步目标改 main 主分支
- **1.1.80** 「切换同步分支」对话框新增**「获取已有分支」按钮**：git ls-remote 动态拉取 GitHub 现有分支补入下拉（与固定候选并存），git 自动探测 + 直连↔代理双路回退

---

## ⚠️ 编码约定（最高频踩坑）

- `.cmd / .bat` 含中文：**GBK + CRLF、无 BOM**
- `.ps1` 含中文：**UTF-8 带 BOM**（否则 Windows PowerShell 5.1 按 ANSI 解析中文报语法错误）
- `.md / .json / .txt`：UTF-8 无 BOM

> 写 `.ps1/.bat/.cmd` 前先载入 `charset-pitfalls` 技能对照编码表。

---

## 📚 文档

- [dsh-launcher-交接与维护手册-TRAESolo.md](dsh-launcher-交接与维护手册-TRAESolo.md)
  —— 资产交接清单 + 可执行维护操作手册（关键路径、铁律、标准操作流程、补丁专章、排障速查、验证清单）。
- `dsh-launcher/SKILL.md` —— 技能主文档（安装/用法/关键原理/补丁/兼容性/分发规则）。
- `dsh-launcher/环境要求-安装指南.md` —— 新机器装环境前必读（Node.js / Git 安装、验证清单与常见问题）。
- `dsh-launcher/assets/升级后重新渲染-标准说法.md` —— 升级后浏览器硬刷新的标准说明。
- `dsh-launcher/assets/补丁管理/补丁管理说明-README.md` —— 补丁清单与格式说明。

---

*本仓库为技能与维护文档的公开归档。同步目标为 GitHub 仓库 `moonwellxh/DSH-Launcher`（main 分支）；
本机路径等个人环境信息见交接手册第 1 节。*
