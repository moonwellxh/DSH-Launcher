---
name: skill-install-ops
description: |
  技能/程序插件安装运维规范（本机长期经验沉淀）。适用于任何「把 zip 技能包或程序插件装到本机并使其可用」的任务：安装前先列清全部环境依赖，环境与主体一起装好（Python 依赖包 / LibreDWG 等二进制 / 注册表项 / 运行时）；目录一律自适应（用 %USERPROFILE%、Path.home()、环境变量探测，禁止硬编码 moonw 等他人用户名）；安装后用「导入验证 + 探测验证 + 自带测试 + 真实冒烟」四层检测确认完全安装好；发现问题当场调试到可用状态，并把文档里的示例路径同步改成本机真实值。
  触发词：「安装 skill」「安装技能」「安装插件」「装环境」「环境适配」「首次使用配置」「装好没」「自检」「调试到可用」「skillhub.zip 安装」「My skills 里的技能」。
---

# 技能/程序插件安装运维规范（skill-install-ops）

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

> **纯文档型 skill 适配**（无 scripts/、无 tests/、无 Python 依赖，如 skill-craft-charter）：L1-L3 三层标 N/A；L4 真实冒烟改为——安装目录与源**逐文件 SHA256 逐字节一致**（`Get-FileHash -Algorithm SHA256` 比对）＋文件清单一致＋frontmatter 合法（name/description/version）＋编码无 BOM/FFFD 污染。**禁止用「version 号字符串匹配」当验收**：它只看一行，文件错/乱码也可能通过，是假绿灯；SHA256 逐字节才是可失败的判据。

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
3. 涉及 `__skillhub.zip` 分发的：**Z: 归档已废弃（2026-08-28 用户明确，目录已改名 `My skills xxx` 标记，不再同步 Z:）**；分发改走 GitHub 私有仓库 `moonwellxh/DSH-Launcher`——配套包内嵌进主包 `assets\配套技能\`，主包经托盘右键「一键同步启动脚本」或 PAT 推送 GitHub（见第六节）。

**归档定位铁律（2026-08-24 用户明确，2026-08-24 修订：用户最终拍板）**：技能是否进
`dsh-launcher` 配套（`assets\配套技能\` 内嵌 + 主包内嵌 + GitHub 分发；Z: 的
`dsh-launcher Add\` 已随 Z: 归档废弃），**最终由用户定义，AI 不得自行决定**。流程：
1. **AI 预判断**：通用运维技能（如 zip-archive-ops / batch-files / charset-pitfalls /
   本技能）→ 倾向配套；个性化生产力技能（如 cad-scan-eye 扫描之眼）→ 倾向根目录独立；
2. **必须询问用户**：明确告知预判断结果与理由，**取得用户同意后才能执行**配套或独立
   归档操作（复制/打包/推送）；用户未确认前，**不得进行任何归档动作**。
历史已定：当前配套 4 个（zip-archive-ops / batch-files / charset-pitfalls / 本技能）；
`cad-scan-eye` 为根目录独立生产力技能。

## 六、私有 GitHub 仓库下载与工具环境经验（2026-08-28 实测）

### 私有仓库技能包下载（PAT 认证）
- `moonwellxh/DSH-Launcher` 是**私有仓库**：raw URL 对私有仓库一律 404（直连/代理都
  一样）；GitHub API 无凭据也 404（该账号显示 0 公开仓库）。**不能只试 raw URL 就断定
  包不存在**，先用 PAT 走 API 探路。
- 下载流程（2026-08-28 更新 dsh-launcher 1.1.64→1.1.65 实测）：
  1. 取分支 sha：`GET https://api.github.com/repos/moonwellxh/DSH-Launcher/branches/<分支名>`
     （带 `Authorization: Bearer <PAT>`）→ `commit.sha`；
  2. 列包路径：`GET .../git/trees/<sha>?recursive=1`，筛 `\.zip$`；
  3. **contents API 默认查 `main` 分支**，指定分支必须带 `?ref=<分支名>`，否则 404；
  4. `GET .../contents/<路径>?ref=<分支>` 取 `download_url`（带签名 token）再下载；
     **Accept 头必须 `application/json`**（`application/octet-stream` 会 415）；
  5. 下载后立即 `ZipFile.OpenRead` 校验 + 读包内 `_meta.json` 确认版本。
- PAT 只在命令行会话内使用，不写进脚本/文档/日志。

### 工具环境坑（本会话实测）
- **本工具执行环境是 Windows PowerShell 5.1**（`$PSVersionTable.PSVersion` = 5.1.x）：
  `Get-Content -Raw` 不带 `-Encoding UTF8` 会按 ANSI/GBK 读 UTF-8 无 BOM 文件（如
  manifest / _meta.json）→ 显示乱码，**文件本身没坏**（用
  `[IO.File]::ReadAllBytes` + `[Text.Encoding]::UTF8.GetString` 验证）。读任何文本文件
  显式 `-Encoding UTF8`。
- **受限 shell 下 HTTPS 失败**：curl / Invoke-WebRequest 报
  `schannel: SEC_E_NO_CREDENTIALS`（拿不到 TLS 凭据）→ 属沙箱限制，需提升权限后重试；
  代理（7897）开着时直连 GitHub 也可能失败——先试 `curl -x http://127.0.0.1:7897 -L`，
  再试直连，两路都不行再考虑权限问题。
- **Z: 归档已废弃（2026-08-28 用户明确）**：原归档目录被用户改名 `My skills xxx` 作
  废弃标记，**分发一律走 GitHub 私有仓库，不要再往 Z: 同步**。推 GitHub 前同样做
  内容级比对（条目列表 + 逐文件哈希，见 zip-archive-ops），版本升级方向明确（旧→新、
  文件集一致）才覆盖/推送。

## 本技能自身：版本与自动进化（必读）

**本技能是 `dsh-launcher` 的配套技能（一键启动补丁）**，随 `dsh-launcher__skillhub.zip`
分发（放 `assets\配套技能\`，setup.ps1 自动安装）。

**自动进化规则（铁律，2026-08-28 修订：Z: 废弃、GitHub-first）**：以后每次实际安装
任何 skill/插件后，把**新踩的坑、新学到的适配方法**追加进本 SKILL.md（新增小节或
速查表行），然后**三连同步**：
1. `_meta.json` 的 `version` **递增**（如 1.1.0 → 1.1.1）+ `publishedAt` 更新为当前
   毫秒时间戳（setup.ps1 靠它判定"包内更新则重装"，时间戳不更新 = 已装机器不会收到
   新内容）；
2. 打包 `skill-install-ops__skillhub.zip` 复制进
   `dsh-launcher\assets\配套技能\`（本机技能目录）覆盖旧包；
3. 重打包 `dsh-launcher__skillhub.zip`（内嵌新版配套），经托盘右键「一键同步启动脚本」
   推送到 GitHub 私有仓库 `moonwellxh/DSH-Launcher`（或 PAT 直推，需写权限）；
   **Z: 归档已废弃，不再同步 Z:**。   **自 dsh-launcher 1.1.81 起此步自动化**：同步已把配套目录纳入比对，配套版本变化
   自动检测推送（自动刷新主树内嵌 zip、发布 releases zip、同步 `dsh-launcher Add\`
   源树），无需手动 bump 主包时间戳。

**版本号防误覆盖**：任何一次进化都**必须升 `_meta.json` 的 `version`**（语义化：
主.次.补丁），并在下方「版本历史」追加一行（版本 / 日期 / 变更内容）。**禁止**只改
内容不升版本——否则多台机器合并时无法区分新旧，可能旧包覆盖新内容。

## 七、配套分发与同步实战（2026-09-04 拆分/打包沉淀）

1. **"模板 vs 渲染副本"认知**：dsh-launcher 技能源是**通用模板**（含 `__GH_REPO__/__GH_BRANCH__`
   占位符），运行副本（如 `D:\DSHS`）是安装/同步时渲染的**本机实例**（真实仓库名等）。
   做"源 vs 副本"比对时：① 先**行尾归一（CRLF→LF）**再哈希/比较（git autocrlf 会制造假差异）；
   ② 先确认文件**存在**再比（对比不存在文件会把"缺失"误报成"内容不同"）。
2. **托盘「一键同步」方向陷阱**：同步方向判定为**拉取**时会**覆盖本地镜像内未推送的提交/文件**，
   且可能把工作树 reset 掉 → 改完配套/源树**先 commit+push，再跑同步**；本地权威副本始终以
   `~\.agents\skills\<技能>\` 为准，镜像（`~\.dsh\gh-sync\DSH-Launcher`）只是仓库工作副本。
3. **git push 凭据**：Bearer 头会被 GitHub 拒；用 `~\.dsh\gh-sync\config.json` 里的 token，
   **Basic 认证**可推：`[Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$tok"))` +
   `git -c "http.extraheader=Authorization: Basic <b64>" push`；token 仅内存使用不落盘不打印；
   先 `Test-NetConnection 127.0.0.1 -Port 7897`（代理开）再推，代理关时用 `-c http.proxy= https.proxy=` 直连尝试。
4. **配套技能分发六位核对清单**（每次改配套必查，`git log origin/main..HEAD` 应为 0 且远端内容可 `git cat-file -e HEAD:路径` 命中）：
   ① 本机 `dsh-launcher\assets\配套技能\<slug>__skillhub.zip`；② 镜像主树 `dsh-launcher\assets\配套技能\`
   同 zip；③ 镜像 `releases\<版本>\`（主包+各配套）；④ `dsh-launcher Add\<slug>\` 源树（解包副本）；
   ⑤ 主包重建后须含新配套条目（.NET `ZipFile.OpenRead` 数条目 + 匹配 `__skillhub.zip` 条目）；
   ⑥ 远端推送成功（`ls-remote origin main` 前 7 位=本地 HEAD）。
5. **zip 条目名中文**：含中文文件名（如 `docs\PDF解析输出JSON规范.md`）打包用 **python zipfile**
   （自动 UTF-8 条目旗标），避免 .NET Framework 按 ANSI 写坏；建包后 `ZipFile.OpenRead`+`Expand-Archive`
   往返校验；不含 `__pycache__/.pyc`。
6. 新增配套技能后，新机器 setup.ps1 会从 `assets\配套技能\*.zip` 自动安装到技能目录；依赖多的技能
   应自带 `check-env.ps1 -Install`（如 pdf-parse-v3）实现"同步即装、装完即用"。

7. **受管凭据文件格式（2026-09-05 事故）**：`~/.dsh/.credentials.yaml` 顶层**只允许 `version` 与 `refs`**；密钥必须写在 `refs:` 区块下（缩进两空格），如：
```yaml
version: 1
refs:
  ANYSEARCH_API_KEY: "as_sk_..."
```
**插件 README 里的"顶层直接写 ANYSEARCH_API_KEY"示例已过时**——顶层追加会让 credentials 插件解析崩溃，dsh web 起不来（表现为"托盘反复崩溃/启动器坏了"的假象）。改凭据前先备份：`Copy-Item x.yaml x.yaml.bak-日期`；修复后用 `dsh web` 就绪信号验证。

8. **AnySearch（@anysearch/anysearch-dsh）DSH 插件安装实战（2026-09-06 实测）**：
   - 本机是源码树 DSH（`C:\Users\雍远\deepseek-harness`），**不要用 `npx -y @deepseek-ai/dsh ...`**（会另拉 npm 包），直接用源码树 CLI：
     ```
     node C:\Users\雍远\deepseek-harness\apps\cli\lib\bin.js plugin --profile web add @anysearch/anysearch-dsh
     ```
     Git Bash 里 node/npx/pnpm 不在 PATH，先 `export PATH="/c/Users/雍远/AppData/Local/Programs/nodejs:$PATH"`；pnpm 用 `corepack enable pnpm` 建 shim（corepack 下载 pnpm 12.3.4，可用）。
   - 装后验证（四层检测）：
     ① `node ...\bin.js plugin --profile web list` 有 `@anysearch/anysearch-dsh`；
     ② `node ...\bin.js --profile web --dump-config` 出现 `searchProvider: anysearch`、`fetchProvider: anysearch`、`web-search-anysearch` 条目（只回显凭据引用名，不回显 key）；
     ③ 重启 web：`powershell -File D:\DSHS\restart-web.ps1`（杀 tray+node web 再拉起，等 3080 返回 200）；
     ④ 冒烟：用插件自带 Client（`~/.dsh/profiles/web/node_modules/@anysearch/anysearch-dsh/lib/client.js`，方法名 `search/extract/listDomains/getSubDomains`，**没有 capabilities()**）带 `~/.dsh/.credentials.yaml` refs 里的 key 实测 search + listDomains。
   - **web-app surface 架构坑：host 层 `tool-web` 的 `disabled: true` + `fetch: false` 是 dsh-web-app bundle 有意设计**——agent 工具按会话由 agent preset 挂载（`apps/cli/config/agent-presets/*/agent.cordis.yml` 各自有 tool-web 行）。**不要**在 profile 的 `cordis.patch.yml` 开 host tool-web 的 fetch（本已 disabled，改了也是惰性配置）；插件自己在 web_fetch 缺失时会补注册（`applyWebFetchTool`）。插件安装文档里"确认 tool-web fetch: true"一步只适用于无 preset 架构的旧预览版。
   - 插件包安装位置：`~/.dsh/profiles/web/`（package.json dependencies + dsh.profile.bundles + pnpm-lock + node_modules）。
   - **端到端实测法（最强验证）**：DSH web 的 api-gateway 支持匿名 RPC（托盘同款）——`POST http://127.0.0.1:3080/api/<method>`，body `{"type":"client-request","rpcId":"...","method":"...","payload":{}}`。可用方法见 `apps/cli/.../api/rpc-map.ts`：`session.create` → `session.models`（新会话默认继承 agent-default-model，**不用 selectModel**）→ `session.prompt {sessionId, mode:'queue', content:[{type:'text',text}]}` → 轮询 `session.history {sessionId}`。历史事件里 `tool/call` 的 `data.name` 是真实工具调用名（比 blob 匹配可靠，目录schema也会产生字符串命中）；`turn/end` 表示回合收尾。脚本样例：任务工作区 `anysearch-e2e.mjs`（2026-09-06 审查时 2 次 tool/call 实证 anysearch_capabilities+web_search）。
   - **卸载（2026-09-06 实测）**：`node ...\bin.js plugin --profile web remove @anysearch/anysearch-dsh`——dependencies 与 bundles 自动移除，`--dump-config` 的 `searchProvider` 自动回退 `deepseek-official`，anysearch 命中归 0。注意：pnpm remove 会留下**空的** `node_modules/@anysearch` scope 目录，手动 `rm -rf` 清掉。凭据 key 留在 credentials.yaml 不动（插件没了不读取，重装直接可用）。卸载后同样要 `restart-web.ps1` 重启生效。
9. **dsh-thinking-effort（@hytime/dsh-thinking-effort@0.3.3）DSH 插件安装实战（2026-09-24 实测）**：
   - **同名包辨析（先问清再装）**：纯名 `dsh-thinking-effort` npm 404；实际有 3 个同名/近名候选——`@hytime/dsh-thinking-effort`（最新、对应官方 Discussion #1817，用户选定）、`@chengwd96/dsh-thinking-effort`（近名、可视化配置）、GitHub `DreamRift/dsh-thinking-efforts`（复数、未发 npm）。`npm search thinking-effort` 找候选，**多候选必须先问清，不得自行选定**。
   - 装：`node C:\Users\雍远\deepseek-harness\apps\cli\lib\bin.js plugin --profile web add "@hytime/dsh-thinking-effort@0.3.3"`。**pnpm 元数据缓存旧会把不带版本的 add 解析到旧版**（本次解析 0.3.1 而非 latest 0.3.3），显式 `@<version>` 钉住；刚发布未达 `minimumReleaseAge` 的版本会被供应链策略拦下，CLI 自动写入 `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude`，属正常放行记录而非错误。
   - 重启脚本坑：`restart-web.ps1` 内 `Start-Process` 全路径 powershell.exe 报「系统找不到指定的文件」（路径 Test-Path 却为真，原因未明）→ 外层改 `cmd /c start /b powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\DSHS\restart-web.ps1` 分离启动；**分离启动还保住当前回合不被「杀 web」中断**（脚本第 8 行强杀 `bin.js web` = 承载会话的进程，前台跑会丢交付）。脚本轮询只认 3080 返 200，**现匿名访问返回 401 会误判 TIMEOUT**——判断服务活着以「web 进程存活 + HTTP 有响应（401 也算）+ 会话可用」三证为准。
   - **宿主加载 marker 路径坑（官方 INSTALL 文档与本机不符）**：marker = `join(process.env.DSH_HOME || cwd, "thinking-effort-loaded.json")`；tray 拉起的 web 进程**不带 DSH_HOME**，marker 实际落在 web 进程 cwd（`C:\Users\雍远\deepseek-harness\thinking-effort-loaded.json`）而非文档写的 `~/.dsh/`。验证时两处都找；`event: filled-N` 且 `pid` 对齐活 web 进程 = Host 已 apply 并自动补齐 N 个模型档位（最强证据）。
   - 四层验证（本插件官方口径 INSTALL.zh.md §4）：① 导入 `node -e "require('C:/Users/雍远/.dsh/profiles/web/node_modules/@hytime/dsh-thinking-effort/lib/index.js')"`（ESM，Node≥22 的 require(esm) 可载，期望 keys 含 `apply`）；② `plugin --profile web list` 有依赖 + `--dump-default-config`（**官方命令名，与 --dump-config 不同**）出现 `- id: thinking-effort` 且无独立旧名 `dsh-thinking-effort` 条目；③ 宿主 marker 见上；④ 浏览器侧匿名 curl 3080 被 401 挡、拿不到页面清单 → 改为让用户在已登录浏览器刷新目视设置页「模型能力与档位」（发布包不附带测试文件，第 3 层自带测试按此跳过）。
   - 卸载（官方 INSTALL §7）：`node ...\bin.js plugin --profile web remove @hytime/dsh-thinking-effort` + 删 marker + 重启 web。

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.1.12 | 2026-10-12 | 「三」补纯文档型 skill 四层检测适配：L1-L3 标 N/A，L4 真实冒烟＝逐文件 SHA256 逐字节一致＋清单一致＋frontmatter＋编码校验；明令禁止 version 号字符串匹配当验收（假绿灯） |
| 1.1.11 | 2026-09-24 | 新增「七.9 dsh-thinking-effort 插件安装实战」：同名包 3 候选须问清；pnpm 缓存旧解析需显式 @version + minimumReleaseAgeExclude 放行；restart-web.ps1 的 Start-Process 坑改 `cmd /c start /b`、401 误判 TIMEOUT 改三证判定；marker 落 cwd 非 ~/.dsh（web 无 DSH_HOME）；官方验证口径 --dump-default-config + marker pid 对齐 |
| 1.1.10 | 2026-09-06 | 「七.8」补充端到端实测法（api-gateway RPC：session.create/models/prompt/history，tool/call 的 data.name 为真实调用名）与卸载流程（remove 自动回退 deepseek-official、清空 @anysearch 残留目录、凭据保留、重启生效） |
| 1.1.9 | 2026-09-06 | 新增「七.8 AnySearch DSH 插件安装实战」：源码树 CLI 直装（不用 npx 拉包）+ corepack pnpm shim + 四层检测命令（plugin list / dump-config / restart-web.ps1 / Client 冒烟）+ web-app host tool-web disabled 是 preset 架构设计、勿在 profile 补丁层开 fetch；Client 方法名 search/extract/listDomains/getSubDomains |
| 1.1.8 | 2026-09-05 | 凭据格式事故沉淀：credentials.yaml 顶层仅允许 version/refs，密钥须入 refs 区块（插件 README 顶层示例已过时）；AnySearch 配 key 正确写法；改前备份 |

| 1.1.7 | 2026-09-04 | 新增「七、配套分发与同步实战」：模板 vs 渲染副本/CRLF 归一与存在性先查；托盘一键同步拉取覆盖风险（先推后拉）；git push 用 gh-sync config token + Basic(x-access-token)（Bearer 被拒）；配套六位核对清单；中文 zip 条目用 python zipfile；check-env 一键依赖 |
| 1.1.6 | 2026-09-01 | 配套同步自动化（dsh-launcher 1.1.81 起）：同步纳入配套目录比对，配套版本变化自动检测推送，无需手动 bump 主包 publishedAt；主树内嵌 zip 自动刷新 |
| 1.1.5 | 2026-08-30 | 本机速查表新增 image-mask 图片打码技能位置（C:\Users\雍远\.agents\skills\image-mask\，脚本 assets\mask-image.ps1 零依赖纯本地、不耗 token） |
| 1.1.4 | 2026-08-28 | Z: 归档废弃、分发改 GitHub-first（用户明确）：移除 Z: 三连同步，改为配套包内嵌 + 主包重打包 + GitHub 推送；同步修正五/六节、归档定位铁律、本机速查表中的 Z: 说明 |
| 1.1.3 | 2026-08-28 | 新增「六、私有 GitHub 仓库下载与工具环境经验」：moonwellxh/DSH-Launcher 为私有仓库需 PAT 认证下载（API 探路 + ?ref 分支 + download_url）；工具环境为 Windows PowerShell 5.1，Get-Content 需显式 -Encoding UTF8 否则 UTF-8 无 BOM 文件显示乱码；受限 shell HTTPS 报 schannel SEC_E_NO_CREDENTIALS 需提权；Z: 归档实际目录名是 `My skills xxx`（带 xxx 后缀）并同步修正文档内路径 |
| 1.1.2 | 2026-08-24 | 归档定位铁律修订：AI 只做预判断，是否进 launcher 配套由用户最终拍板，未经用户同意不得执行任何归档操作 |
| 1.1.1 | 2026-08-24 | 归档定位铁律：仅一键启动相关通用运维技能进配套；个性化生产力技能（cad-scan-eye）只放根目录独立，绝不混入配套 |
| 1.1.0 | 2026-08-24 | 新增「本技能自身：版本与自动进化」章节；明确为 dsh-launcher 配套技能；四层检测加入端到端产出验证（orchestrator JSON）；记录 dxf2dwg 用 `-o` 指定输出、子进程输出按 GBK 解码会炸需 `errors="replace"` |
| 1.0.0 | 2026-08-24 | 初版：从安装 cad-scan-eye 的实战沉淀（环境同装 / 目录自适应 / 四层检测 / 文档路径同步） |

## 本机关键事实速查

| 项 | 值 |
|----|----|
| 真实用户名 | `C:\Users\雍远`（**不是** moonw） |
| WorkBuddy Python | `C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe`（3.13.x） |
| DSH 专用 Python（推荐） | 运行时由 `pdf-parse-v3\assets\check-env.ps1` 探测/一键补装（探测优先；安装到 %USERPROFILE% 下） |
| dsh-launcher 运行副本 | `D:\DSHS`（launcher.version 1.1.81；为技能源模板渲染出的本机实例，脚本差异多为占位符→真实值） |
| gh-sync token | `~\.dsh\gh-sync\config.json`（内存使用；push 用 Basic base64("x-access-token:"+token)） |
| AnySearch key 配置 | `~/.dsh/.credentials.yaml` 的 **refs 区块**下（缩进两格）：`ANYSEARCH_API_KEY: "as_sk_..."`；**禁止顶层追加**（会崩 credentials 插件）。匿名 10/窗口，带 key 20/窗口、日 1000 次 |
| AnySearch 插件（2026-09-06 已卸载） | 装/卸命令与检测见「七.8」（remove 后 searchProvider 回退 deepseek-official；key 仍留在 credentials.yaml，重装即生效） |
| dsh-thinking-effort 插件（2026-09-24 已装 @hytime@0.3.3） | 装卸与四层验证见「七.9」；宿主 marker 在 `C:\Users\雍远\deepseek-harness\thinking-effort-loaded.json`（web 进程无 DSH_HOME 落 cwd）；回滚：`plugin --profile web remove @hytime/dsh-thinking-effort` + 重启 + 删 marker |
| 系统代理 | 注册表 `127.0.0.1:7897`（Clash Verge）；未开时 pip 走清华镜像+NO_PROXY |
| 技能安装目录 | `C:\Users\雍远\.agents\skills\<技能名>\` |
| image-mask 打码技能 | `C:\Users\雍远\.agents\skills\image-mask\assets\mask-image.ps1`（零依赖，System.Drawing 纯本地；SKILL.md 同目录） |
| LibreDWG 探测路径 | `~/.workbuddy/bin/libredwg/`（dwgread.exe/dwg2dxf.exe，0.14 已装） |
| 中文路径解压 | 用 .NET ZipFile，不用 bsdtar |
| GitHub 技能仓库 | `moonwellxh/DSH-Launcher`（**私有**，需 PAT；分支 `feature/github-sync-v1.1.65`，包在 `releases/<版本>/`） |
| 执行工具 | Windows PowerShell 5.1（`$PSVersionTable` 确认）；读文件显式 `-Encoding UTF8` |
| Z: 归档 | **已废弃**（2026-08-28，目录改名 `My skills xxx` 仅留档），分发走 GitHub 私有仓库，不再同步 Z: |
