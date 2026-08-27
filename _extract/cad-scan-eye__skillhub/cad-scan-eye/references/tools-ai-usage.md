# 配套工具 AI 使用方法（cad-scan-eye 配套环境速查）

> 本文件记录本技能依赖的各配套工具：**路径 / AI 怎么调用 / 常见坑**。
> 按 skill-install-ops 规范安装后，本机真实路径已写入「环境」表，这里给出 AI 可直接
> 执行的调用模板。**所有路径用 %USERPROFILE% 展开，禁止硬编码用户名。**

## 1. Python 解释器（WorkBuddy 自带，无 venv）

| 项 | 值 |
|----|----|
| 路径 | `%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe` |
| 版本 | 3.13.x（实测 3.13.14） |
| 已装包 | comtypes 1.4.16 / ezdxf 1.4.4 / numpy 2.5.2 / pyautocad 0.2.0 / pywin32 312 |

AI 调用模板（PowerShell）：
```powershell
$py = "$env:USERPROFILE\.workbuddy\binaries\python\versions\3.13.12\python.exe"
& $py "<技能目录>\orchestrator.py" "D:\xx.dwg"
```
**坑**：
- 本机**没有** `envs\default` venv（WorkBuddy 直接装 base 解释器）；技能文档里的
  `envs\default\Scripts\python.exe` 是示例，本机用 `versions\3.13.12\python.exe`。
- 内联 `python -c "..."` 传多行/含引号代码会被 PowerShell 转义破坏 → 用
  `$code = @'...'@; $code | & $py -` 或写临时 .py 文件执行。
- 控制台 GBK 乱码：设 `$env:PYTHONIOENCODING='utf-8'`；子进程捕获输出用
  `errors="replace"`，否则中文输出按 GBK 解码会炸 `UnicodeDecodeError`。

## 2. Python 依赖包（pip 安装）

```powershell
$py = "$env:USERPROFILE\.workbuddy\binaries\python\versions\3.13.12\python.exe"
& $py -m pip install --no-input -i https://pypi.tuna.tsinghua.edu.cn/simple <包...>
```
**坑**：本机系统代理注册表常设 `127.0.0.1:7897`（Clash Verge），**代理未开时 pip 全挂**
（`NewConnectionError ... 10061`）。处理：`$env:NO_PROXY='*'; $env:no_proxy='*'` 绕过代理
直连清华镜像。**依赖包角色**：comtypes=COM 调 AutoCAD（A 路）、ezdxf=离线 DXF 读写
（B 路后处理）、pyautocad=COM 便捷封装、numpy=坐标矩阵、pywin32=COM 底层。

## 3. LibreDWG 0.14（离线解析 + 代理检测）

| 项 | 值 |
|----|----|
| 探测路径 | `~/.workbuddy/bin/libredwg/`（`find_libredwg_dir()`：LIBREDWG_DIR → 用户目录 → PATH） |
| 关键 exe | `dwgread.exe` / `dwg2dxf.exe` / `dxf2dwg.exe` |
| 来源 | GitHub 官方 release `libredwg-0.14-win64.zip`（SHA256 `1ad7e153...`） |

AI 调用模板：
```powershell
$d = "$env:USERPROFILE\.workbuddy\bin\libredwg"
& "$d\dwgread.exe" --version          # → dwgread 0.14
& "$d\dwg2dxf.exe" -o out.dxf in.dwg  # 离线转 DXF（B 路）
& "$d\dxf2dwg.exe" -o out.dwg in.dxf  # 造测试样本（注意 -o 指定输出！）
```
**坑**：
- `dxf2dwg` **必须用 `-o outfile`** 指定输出，第二个位置参数会被当成另一个输入文件。
- `dwgread`/`dwg2dxf` 输出含中文时按 GBK 打印，脚本捕获需 `errors="replace"`。
- 大图 dwg2dxf 会在 BLOCKS 段截断（30 万对象），技能已内置 BINARY 修复+段截断修复。
- 该目录含 exe + 依赖 dll（libredwg-0.dll 等），**必须整目录存在**，不能只拷 exe。

## 4. TZ3 插件（天正→T3 静默转换）

| 项 | 值 |
|----|----|
| dll | 技能目录 `TZ3Converter.fx48.dll` / `.net8.dll`（双运行时） |
| 注册 | `& $py "<技能目录>\tz3_install.py" --register`（哈希校验，需重启 CAD 生效） |
| 免重启 | APPLOAD `tz3_register.lsp`（REGDLL）或直接 NETLOAD |
| 转换 | `orchestrator.py xxx.dwg` 自动检测天正代理 → 自动转 `原名_AiT3.dwg` |

**AI 使用要点**：
- 转 T3 依赖**运行中的 AutoCAD + 天正**（`tch_kernal.arx`）；CAD 未运行且需要转时，
  orchestrator 会自动启动 CAD（`--no-auto-t3` 禁用）。
- 产物 `原名_AiT3.dwg` + `.meta.json` sidecar 原子写，源文件永不修改；mtime/size/快哈希
  三重增量判定避免重复转。
- 注册表 `HKCU\Software\Autodesk\AutoCAD\R2x.x\<产品键>\Applications\TZ3Converter`，
  注销 `--unregister` 可回滚（含 TRUSTEDPATHS 追加项）。

## 5. AutoCAD COM（A 路在线提取）

```python
import comtypes.client
app = comtypes.client.GetActiveObject("AutoCAD.Application", dynamic=True)  # 失败=未运行
```
**AI 使用要点**：
- 只读提取**不修改系统变量**；仅 tz3_convert 发 `TZ3` 时临时设 `CMDDIA=0` 并 30s 看门狗
  恢复，快照存 `%TEMP%/cad-scan-eye/guards_snapshot.json`，残留用
  `extract.py --restore-guards` 恢复。
- COM 必须用 comtypes（PowerShell `New-Object -ComObject` 被安全策略拦截）。
- 弹窗防护：`FILEDIA/CMDDIA` 卡 0 会导致 Ctrl+O 不弹框；orchestrator 启动自动检测残留。

## 6. 天正环境（T3 转换前提）

| 项 | 值 |
|----|----|
| 判定 | AutoCAD 内已装天正（`tch_kernal.arx` 存在） |
| 转换命令 | 静默靠 `SaveAsTArch3` 直调（TZ3 插件）；`TSAVEAS`/`TXDC` 等无效 |

**AI 使用要点**：`SaveAsTArch3` 动态解析跨天正版本；天正代理实体未转 T3 时 B/C 路读不到
文字内容，此时应引导转 T3（或报告「相关文字可能缺失」）。

## 7. 快速环境自检（一键）

```powershell
$py = "$env:USERPROFILE\.workbuddy\binaries\python\versions\3.13.12\python.exe"
& $py "<技能目录>\verify_install.py"   # 四层自检：导入/探测/测试/端到端冒烟
```

## 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-08-24 | 初版：按 skill-install-ops 规范记录本机配套工具路径、AI 调用模板与踩坑 |
