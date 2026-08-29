# dsh-launcher — DSH 一键启动 + 系统托盘

> **当前版本：1.1.66** · 适配 DSH：`0.1.0-rc.7` / `0.1.1-rc.2` · 平台：Windows（PowerShell 5.1+）

`dsh-launcher` 是 DeepSeek Harness（DSH）的**一键启动器生成器**：给任意一台已装 DSH 的
Windows 机器安装「一键启动 + 系统托盘手动关闭」方案。它生成 `启动DSH.bat` 菜单启动器、
`DSH-tray.ps1` 系统托盘（托盘常驻、右键关闭服务、浏览器就绪后自动打开、PWA 主应用优先）、
`dsh.cmd` CLI 包装，并自动按清单加载补丁。

> ⚠️ **边界声明**：它是**启动器生成器，不是 DSH 安装器**。从不安装 / 升级 / 卸载 DSH 本体，
> 不运行 npm/pnpm，不改 PATH。DSH 的安装与升级由用户负责。

---

## ✨ 特性

- **自适应探测**：自动识别 DSH 安装方式（PATH 全局安装 / `deepseek-harness` 源码树 + node），
  生成适配的启动脚本与托盘。
- **系统托盘常驻**：右键菜单一键关闭 DSH（杀整棵进程树）、重启、打开 Web UI / TUI / Headless。
- **浏览器就绪后自动打开**：等待 `dsh web` 打印就绪信号，避免过早打开导致前端报错；
  优先打开已「安装为应用」的 PWA 主应用（无则引导安装）。
- **零窗口入口**：`启动DSH-托盘.vbs`（wscript 直启，零命令行窗口）与自隐藏 `.cmd` 入口，双击不闪屏。
- **补丁自动载入**：`assets\补丁管理\` 内置补丁引擎，随安装自动按清单打补丁（幂等、可挂起、可一键还原）。
- **配套技能一体分发**：只需分发一个 `dsh-launcher__skillhub.zip`，安装时自动携带 4 个配套技能。
- **一键同步（GitHub）**：托盘右键第三行「启动托盘 x.x.x 版（点击可更新/已是最新）」与 GitHub 仓库 `moonwellxh/DSH-Launcher`
  做 git 双向同步（源树逐文件 SHA256 比对，冲突时用户确认制；上传自动更新源树 + 重打包 zip 归档）。

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
│       ├── setup.ps1                ← 核心安装/生成器（探测 DSH → 生成脚本 → 按清单打补丁）
│       ├── tmpl/                    ← 托盘与 CLI 包装模板（parts/ 片段 + mode-*.json + setup.ps1 拼装生成）
│       ├── 启动DSH.bat / 启动DSH-托盘.cmd / 启动DSH-托盘.vbs / run-hidden.vbs / 更新安装.cmd
│       ├── 配套技能/                ← 内嵌 4 个配套技能 zip（setup.ps1 自动安装）
│       ├── 补丁管理/                ← 补丁引擎 + 自动载入清单 + 补丁01-档案柜v1
│       └── 图标（tray.ico / whale*.ico / whale-white.png）
├── dsh-launcher Add/                ← 4 个配套技能的**源树**（zip 已集中到 releases/）
│   ├── batch-files/ （1.1.3）  charset-pitfalls/ （1.1.3）
│   └── skill-install-ops/ （1.1.2）  zip-archive-ops/ （1.0.4）
└── releases/                        ← **zip 集中归档目录（历史版本按目录留档）**
    ├── v1.1.64/ ← 历史版本（主包 + 配套包）   v1.1.65/ ← 历史版本
    └── v1.1.66/                     ← 当前版本（dsh-launcher__skillhub.zip 等）
```

---

## 🚀 快速开始（Windows）

### 方式 A：作为 DSH 技能使用（有 AI 协助时，推荐）

1. 解压 `dsh-launcher__skillhub.zip` 到 DSH 技能目录 `~/.agents/skills/dsh-launcher`
   （zip 根目录 = 技能名；可从仓库 `releases\v1.1.66\dsh-launcher__skillhub.zip` 下载）。
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
| `DSH-tray.ps1` | 系统托盘本体（右键菜单：版本 / 最新版本 / 一键同步 / 打开 Web UI / TUI / Headless / 重启 / 退出并停止） |
| `dsh.cmd` | CLI 入口包装（`--version` / TUI / Headless） |
| `launcher.version` | 启动器版本号 |

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

| 技能 | 版本 | 用途 |
|---|---|---|
| `zip-archive-ops` | 1.0.4 | zip 归档打包/校验/修复 |
| `charset-pitfalls` | 1.1.3 | Windows 中文编码避坑汇总（GBK/UTF-8/BOM） |
| `batch-files` | 1.1.3 | Windows 批处理专家级写作/调试 |
| `skill-install-ops` | 1.1.2 | 技能安装运维规范（自带版本号与自动进化机制） |

> 分发只需 `dsh-launcher__skillhub.zip` 一个包。任一配套技能变更后需**三连同步**：
> ① 打包 `xxx__skillhub.zip` 归档到 GitHub `releases\<当前版本>\`＋更新源树 `dsh-launcher Add\<技能名>\`；
> ② 复制进 `assets\配套技能\` 覆盖旧包；③ 重打包主包并 git commit + push，且递增该技能
> `_meta.json` 的 version / publishedAt。

---

## 🧰 版本与兼容性

| 组件 | 版本 | 兼容 DSH |
|---|---|---|
| dsh-launcher | 1.1.66 | 0.1.0-rc.7、0.1.1-rc.2 |
| 档案柜 v1 补丁 | 0.1.1 | **仅 0.1.1-rc.2**（载荷绑定版本） |

版本历史（1.1.48 → 1.1.66）要点：

- **1.1.51** P0-P2 全面修复（补丁引擎陷阱 / 托盘重启链编码等）
- **1.1.53-57** 双击 / 「打开 Web UI」优先打开已装 PWA 主应用（SC_RESTORE 聚焦 + 引导式安装）
- **1.1.58** 固化调试纪律铁律（绝不在运行中生成物上直接编辑）
- **1.1.59** 「重启 DSH」改版：杀 web + WM_CLOSE 优雅关窗 + helper 接力重启
- **1.1.60** 修复「最新版本」查询：强制 TLS1.2 + 优先直连、失败回退代理
- **1.1.61** 一键托盘入口全面去闪烁（自隐藏 .cmd + 零窗口 .vbs）
- **1.1.62** 托盘右键第三行文案 →「一键同步启动脚本」
- **1.1.64** 同步冲突处理（用户确认制）：时间戳相同但内容不同时，弹窗展示分析，用户确认方向（上传/拉取/取消）后才执行，绝不自动覆盖良包
- **1.1.65** **同步存档全面切换 GitHub**：弃用 Z: 盘（NAS）存档；托盘「一键同步」改为 git 双向同步 `moonwellxh/DSH-Launcher`（上传=更新源树 + 重打包 zip 到 `releases\<版本>\` + git add/commit/push；git 历史天然备份旧版）
- **1.1.66** **一键同步发布级重写**：配置化 repo/branch/token（环境变量 > config.json > 默认），代理自动探测双路回退，错误分类引导，文本归一化比对，5 zip 发布；托盘右键第三行改为「启动托盘 x.x.x 版（点击可更新/已是最新）」

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
- `dsh-launcher/assets/升级后重新渲染-标准说法.md` —— 升级后浏览器硬刷新的标准说明。
- `dsh-launcher/assets/补丁管理/补丁管理说明-README.md` —— 补丁清单与格式说明。

---

*本仓库为技能与维护文档的公开归档。同步目标为 GitHub 仓库 `moonwellxh/DSH-Launcher`；
本机路径等个人环境信息见交接手册第 1 节。*
