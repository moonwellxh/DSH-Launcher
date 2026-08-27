---
name: skill-install-ops
description: |
  技能/程序插件安装运维规范（本机长期经验沉淀）。适用于任何「把 zip 技能包或程序插件装到本机并使其可用」的任务：安装前先列清全部环境依赖，环境与主体一起装好（Python 依赖包 / LibreDWG 等二进制 / 注册表项 / 运行时）；目录一律自适应（用 %USERPROFILE%、Path.home()、环境变量探测，禁止硬编码 moonw 等他人用户名）；安装后用「导入验证 + 探测验证 + 自带测试 + 真实冒烟」四层检测确认完全安装好；发现问题当场调试到可用状态，并把文档里的示例路径同步改成本机真实值。
  触发词：「安装 skill」「安装技能」「安装插件」「装环境」「环境适配」「首次使用配置」「装好没」「自检」「调试到可用」「skillhub.zip 安装」「My skills 里的技能」。
---

# 技能/插件安装运维规范（skill-install-ops）

把 `__skillhub.zip` 技能包（或任何程序插件）安装到本机并**调试到可用**的完整流程。
本技能由 2026-08-24 安装 cad-scan-eye 的实战教训沉淀而成。

## 铁律（四条）

1. **环境与主体一起装**：技能包只是代码，跑不起来等于没装。装包时必须同时把它的全部运行环境装好（Python 依赖 / 二进制工具 / 注册表项 / 运行时 / 插件），**不许装完包就交差**。
2. **目录必须自适应**：安装目标、脚本内路径、文档示例路径一律用 `%USERPROFILE%`、`Path.home()`、环境变量探测；**禁止硬编码他人用户名**（如 `C:\Users\moonw\...`，本机真实用户是 `C:\Users\雍远`）。
3. **装完必须四层检测**：导入验证 → 探测验证 → 自带测试 → 真实冒烟。任何一层不过，当场调试到通过，才算「安装完成」。
4. **文档示例路径同步改**：SKILL.md / troubleshooting.md / 测试脚本里的示例路径，只要与本机不符，全部改成本机真实值，防止下次使用照抄失败。

## 一、安装前（三步）

1. **列依赖清单**：读 SKILL.md 的「环境」表、requirements、README，把依赖分类：
   | 类别 | 例子 | 检查方法 |
   |------|------|----------|
   | Python 包 | comtypes/ezdxf/pyautocad/numpy | `python -c "import importlib.util as u; print(u.find_spec('xxx'))"` |
   | 二进制工具 | LibreDWG（dwgread/dwg2dxf） | `where dwgread` / 探测脚本 |
   | 运行时 | .NET 8 / AutoCAD / 天正 | 注册表 / 进程 / `Get-Command` |
   | 注册表项 | AutoCAD Applications 注册、TRUSTEDPATHS | `reg query` |
2. **找可用的 Python 解释器**：先查 `%USERPROFILE%\.workbuddy\binaries\python\versions\*\python.exe`（WorkBuddy 自带）、`py -0p`、`Get-Command python`。**不要假设技能文档写的 venv 存在**。
3. **确认网络**：本机系统代理注册表常设 `127.0.0.1:7897`（Clash Verge mixed-port），代理未开时 pip/下载全挂。**代理没开时**：pip 用 `-i https://pypi.tuna.tsinghua.edu.cn/simple` + `$env:NO_PROXY='*'`；二进制下载用 `curl -x http://127.0.0.1:7897`（代理开着时）。先 `Test-NetConnection 127.0.0.1 -Port 7897` 判断。

## 二、安装中（环境与主体一起装）

1. **装 Python 依赖**（选定的解释器）：
   ```
   & $py -m pip install --no-input -i https://pypi.tuna.tsinghua.edu.cn/simple <包...>
   ```
   装完立即验证导入，**别信 pip 的 Successfully installed 就完事**（见检测层 1）。
2. **装二进制工具**：优先官方 release 的 win64 包（如 [LibreDWG 0.14 win64](https://github.com/LibreDWG/libredwg/releases/tag/0.14)），下载后**必须校验 SHA256**（release 正文或 `.sha256` 文件里有官方值），不一致拒绝使用。解压到技能脚本的探测路径（如 `~/.workbuddy/bin/libredwg/`）。
3. **解压技能包**：目标 `%USERPROFILE%\.agents\skills\<技能名>\`（zip 根目录=技能名）。**中文用户名坑**：bsdtar（`C:\Windows\System32\tar.exe`）会把中文用户名按 GBK 误解成乱码导致解压失败，改用 .NET `[System.IO.Compression.ZipFile]::ExtractToDirectory()`。
4. **注册表/运行时类**：按技能 SKILL.md 的「系统级改动清单」执行，并记录回滚方法。

## 三、安装后四层检测（缺一不可）

> 每层用独立的可执行检查，输出 PASS/FAIL 清单；FAIL 必须当场修。

1. **导入验证**：全部 Python 依赖能 import：
   ```
   & $py -c "import comtypes, ezdxf, pyautocad, numpy; print('IMPORTS OK')"
   ```
2. **探测验证**：技能自带的路径/工具探测函数能命中本机安装：
   ```
   & $py -c "import sys; sys.path.insert(0, r'<技能目录>'); from <探测模块> import <探测函数>; print(<探测函数>())"
   ```
   以及二进制自检：`& <exe> --version`。
3. **自带测试**：跑技能 tests/ 下的回归/单测（如 `test_proxy.py`、`test_path_util.py`），要求全部通过。**控制台 GBK 乱码/`\u2713` 报错是显示问题**：设 `$env:PYTHONIOENCODING='utf-8'` 重跑确认，功能不受影响。
4. **真实冒烟**：用真实输入跑主入口（如 `orchestrator.py`），验证「正常路径」和「错误路径」都不崩（错误路径应报友好错误如「文件不存在」而非 Traceback）。

## 四、目录自适应规则（写进技能时遵循）

- 探测顺序：**环境变量 → 用户目录（Path.home()）→ PATH**，如 `LIBREDWG_DIR → ~/.workbuddy/bin/libredwg → PATH 中的 dwgread`。
- 技能文档里的解释器示例路径不要写死他人用户名；本机适配后统一写成：
  ```
  C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe
  ```
  （WorkBuddy 自带解释器；无 venv 时直接用这个）。
- SKILL.md / troubleshooting.md / tests 里的示例路径与本机不符时，**全部同步改**（grep 技能目录内 `moonw` 等旧用户名逐一清理，测试数据路径除外）。

## 五、装完收尾

1. 把安装中踩的坑和最终路径**写回技能文档**（环境表、troubleshooting），让下次安装有据可查。
2. 向用户报告：装了哪些环境、检测四层各几条 PASS、文档改了哪里、还剩什么条件才能用（如 AutoCAD/天正需运行）。
3. 涉及 `__skillhub.zip` 分发的：重打包归档到 GitHub 仓库
   `releases\<当前版本>\`（zip 集中归档目录；已弃用 Z: 盘存档）。

**归档定位铁律（2026-08-24 用户明确，2026-08-24 修订：用户最终拍板）**：技能是否进
`dsh-launcher` 配套（`assets\配套技能\` + `dsh-launcher Add\` + 主包内嵌三处同步），
**最终由用户定义，AI 不得自行决定**。流程：
1. **AI 预判断**：通用运维技能（如 zip-archive-ops / batch-files / charset-pitfalls /
   本技能）→ 倾向配套；个性化生产力技能（如 cad-scan-eye 扫描之眼）→ 倾向根目录独立；
2. **必须询问用户**：明确告知预判断结果与理由，**取得用户同意后才能执行**配套或独立
   归档操作（复制/打包/同步）；用户未确认前，**不得进行任何归档动作**。
历史已定：当前配套 4 个（zip-archive-ops / batch-files / charset-pitfalls / 本技能）；
`cad-scan-eye` 为根目录独立生产力技能。

## 本技能自身：版本与自动进化（必读）

**本技能是 `dsh-launcher` 的配套技能（一键启动补丁）**，随 `dsh-launcher__skillhub.zip`
分发（放 `assets\配套技能\`，setup.ps1 自动安装，同时同步一份到 `dsh-launcher Add\`）。

**自动进化规则（铁律）**：以后每次实际安装任何 skill/插件后，把**新踩的坑、新学到的
适配方法**追加进本 SKILL.md（新增小节或速查表行），然后**三连同步**：
1. `_meta.json` 的 `version` **递增**（如 1.1.0 → 1.1.1）+ `publishedAt` 更新为当前
   毫秒时间戳（setup.ps1 靠它判定"包内更新则重装"，时间戳不更新 = 已装机器不会收到
   新内容）；
2. 打包 `skill-install-ops__skillhub.zip` 归档到 GitHub 仓库
   `releases\<当前版本>\`（zip 集中归档目录）＋更新配套源树 `dsh-launcher Add\skill-install-ops\`；
3. 复制进 `dsh-launcher\assets\配套技能\` 覆盖旧包，重打包
   `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\` 并 git commit + push。

**版本号防误覆盖**：任何一次进化都**必须升 `_meta.json` 的 `version`**（语义化：
主.次.补丁），并在下方「版本历史」追加一行（版本 / 日期 / 变更内容）。**禁止**只改
内容不升版本——否则多台机器合并时无法区分新旧，可能旧包覆盖新内容。

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.1.2 | 2026-08-24 | 归档定位铁律修订：AI 只做预判断，是否进 launcher 配套由用户最终拍板，未经用户同意不得执行任何归档操作 |
| 1.1.1 | 2026-08-24 | 归档定位铁律：仅一键启动相关通用运维技能进配套；个性化生产力技能（cad-scan-eye）只放根目录独立，绝不混入配套 |
| 1.1.0 | 2026-08-24 | 新增「本技能自身：版本与自动进化」章节；明确为 dsh-launcher 配套技能；四层检测加入端到端产出验证（orchestrator JSON）；记录 dxf2dwg 用 `-o` 指定输出、子进程输出按 GBK 解码会炸需 `errors="replace"` |
| 1.0.0 | 2026-08-24 | 初版：从安装 cad-scan-eye 的实战沉淀（环境同装 / 目录自适应 / 四层检测 / 文档路径同步） |

## 本机关键事实速查

| 项 | 值 |
|----|----|
| 真实用户名 | `C:\Users\雍远`（**不是** moonw） |
| WorkBuddy Python | `C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe`（3.13.x） |
| 系统代理 | 注册表 `127.0.0.1:7897`（Clash Verge）；未开时 pip 走清华镜像+NO_PROXY |
| 技能安装目录 | `C:\Users\雍远\.agents\skills\<技能名>\` |
| LibreDWG 探测路径 | `~/.workbuddy/bin/libredwg/`（dwgread.exe/dwg2dxf.exe，0.14 已装） |
| 中文路径解压 | 用 .NET ZipFile，不用 bsdtar |
