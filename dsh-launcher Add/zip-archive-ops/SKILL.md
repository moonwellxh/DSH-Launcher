---
name: zip-archive-ops
description: >
  通用 zip 压缩包 创建/校验/修复 技能。适用于任何涉及 zip 打包、上传到网络盘/NAS
  （RaiDrive/Synology/SMB 等）后校验、压缩包打不开/损坏的排查与修复任务。涵盖 zip
  格式结构（本地文件头 + 中央目录 + 末尾 EOCD）、截断损坏判定（EOCD 缺失）、上传后
  必验（ZipFile.OpenRead）、bsdtar 兜底抢救（C:\Windows\System32\tar.exe）、重新打包
  与替换分发。遇到 "End of Central Directory record could not be found" 等 zip 错误
  时使用本技能。
---

# zip 压缩包 创建 / 校验 / 修复（通用）

任何任务中涉及压缩包（zip）的创建、复制到网络盘、打开失败、修复时，遵循本技能。

## 配套维护提醒（dsh-launcher 一键启动技能）

本技能是 `dsh-launcher`（DSH 一键启动）的**配套技能**，已打包进其
`assets\配套技能\`，安装一键启动时会自动装上本技能。

**修改本技能后，同步分发（缺一不可；Z: 网络盘归档已废弃，分发一律走 GitHub 私有仓库）**：
1. 打包 `zip-archive-ops__skillhub.zip`（根目录=技能名），归档到 GitHub 仓库
   `releases\<当前版本>\`（与主包同目录归档）＋ 更新仓库内配套源树 `dsh-launcher Add\zip-archive-ops\`；
2. 把新 zip 复制进 `dsh-launcher\assets\配套技能\`（覆盖旧包）；
3. 重打包 `dsh-launcher__skillhub.zip` 到 `releases\<当前版本>\`，git commit + push
   （setup.ps1 按版本/时间戳自动分发新版）。

## 何时使用

- 打包 zip（.NET ZipFile / Compress-Archive / tar）
- 把 zip 上传/复制到网络盘、NAS（RaiDrive、Synology、SMB 等）
- zip 打开失败：报 "End of Central Directory record could not be found" 等
- 任何任务产出 zip 后需要验证可解压

## 一、zip 格式关键认知

- zip 是「头在开头、目录在末尾」：条目数据在开头（本地文件头 PK0304），全部条目之后
  是**中央目录（PK0102）**，文件末尾是**中央目录结尾记录 EOCD（PK0506）**。
- **只查开头 PK 头会误判"正常"**；打开 zip 靠末尾的中央目录 + EOCD。
- 网络盘（RaiDrive/Synology）上传/同步连接抖动时，文件常被**截断**——开头还在、
  末尾目录被切掉 → .NET/Expand-Archive 拒绝打开。

## 二、创建 zip（规范做法）

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
# includeBaseDirectory=$true 时根目录=源目录名（打包技能/目录时用）
[System.IO.Compression.ZipFile]::CreateFromDirectory(
  "<源目录>", "<输出.zip>",
  [System.IO.Compression.CompressionLevel]::Optimal, $true)
```

## 三、校验（创建/复制到网络盘后必做）

```powershell
$z = [System.IO.Compression.ZipFile]::OpenRead("<路径.zip>")
$z.Entries.Count   # 不抛异常 = 结构完整
$z.Dispose()
```

- **任何 zip 写到网络盘/NAS 之后，必须先验证再分发/使用。**
- 快速截断判定：读文件末尾找 EOCD（PK0506）；缺失 = 截断。

## 四、修复损坏 zip（bsdtar 兜底）

- .NET / Expand-Archive 要求完整中央目录 + EOCD，遇截断 zip 直接拒绝；
- **Windows 自带 bsdtar（C:\Windows\System32\tar.exe）更宽容**，可按本地文件头直接读。

```powershell
# 1) 列出内容（能列出 = 数据还在，可修复）
C:\Windows\System32\tar.exe -tf "<损坏.zip>"
# 2) 解压抢救
C:\Windows\System32\tar.exe -xf "<损坏.zip>" -C "<目标目录>"
# 3) 核对内容后重新打包为干净 zip（见「二、创建」）
# 4) 校验新包（见「三、校验」）
# 5) 用干净包替换所有分发位置
```

> ⚠️ 用 `C:\Windows\System32\tar.exe`，**不要用 Git 的 `/usr/bin/tar`（MSYS2）**——
> 后者不识别 Windows 盘符（报 "Cannot connect to Z:" 之类）。

## 五、经验清单

1. 上传/拷贝 zip 到网络盘后，先 `ZipFile.OpenRead` 验证再使用。
2. 排障顺序：开头 PK 头 → 数本地文件头 → 找末尾 EOCD（PK0506）；EOCD 缺失 = 截断。
3. 打不开且无原始文件时，优先 bsdtar 兜底。
4. 修复后务必重新打包替换损坏副本，避免损坏包继续传播。
5. 区分两个 tar：`C:\Windows\System32\tar.exe` vs Git 的 `/usr/bin/tar`。
6. 网络盘/NAS（RaiDrive、Synology）连接不稳时，先在本地打包校验，再一次性复制。
7. **同步守卫（覆盖网络盘归档前）**：必须**内容级比对**（解包远端、比对条目列表与逐文件哈希），**不能只比版本号**——远端版本号可能低于本地但内容更丰富。**远端与本机内容不一致即停止并提示「需人工确认合并方向」，绝不盲目覆盖**；确认为同内容后才写入。

## 分发规则

本技能更新后，打包 zip（根目录 = 技能名）归档到 GitHub 仓库
`releases\<当前版本>\zip-archive-ops__skillhub.zip`（与 dsh-launcher 主包同目录归档，
git commit + push）。**Z: 网络盘归档已废弃，不再同步 Z:**；与 launcher 无关的技能包独立管理，不进本仓库。