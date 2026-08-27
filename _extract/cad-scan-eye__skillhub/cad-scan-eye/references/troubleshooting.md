# 故障排查与常见问题

## 1. 「AutoCAD 未运行」提示

- A 路（COM）与转 T3 依赖运行中的 AutoCAD。离线提取（B/C 路）不需要。
- 需要 COM 时：提醒用户打开 AutoCAD 并打开目标 DWG，**不要自行启动 CAD**。
- 目标图未打开：A 路跳过并记入 `errors[]`，B/C 路兜底继续。

## 2. 天正图转 T3 流程卡住

症状：`verdict=convert_t3` 但一直没有 `_AiT3` 文件。

| 情况 | 处理 |
|------|------|
| 插件从未注册 | `python tz3_install.py --register` → **重启 AutoCAD**（注册表 demand-load 启动时读） |
| 当次会话不想重启 | CAD 内 `APPLOAD` 加载 `tz3_register.lsp` → 输 `REGDLL`；或 `NETLOAD` 对应 dll（≤2024 用 fx48，≥2025 用 net8）→ 输 `TZ3` |
| 已注册但重启后未加载 | `python tz3_install.py --status` 核对 LOADER 指向的 dll 与 CAD 版本匹配（2025 起必须 net8 产物） |
| NETLOAD 被静默拦截 | SECURELOAD=1 且 dll 不在信任路径 → 运行 `--register`（会追加 TRUSTEDPATHS）后重启 CAD 再试 |
| dll 哈希校验不过 | 重新运行 `compile.bat` 生成双产物与 `TZ3Converter.sha256` |

转换成功后源目录出现 `原名_AiT3.dwg` + `原名_AiT3.meta.json`（sidecar，三重增量判定用）。发现 `原名_AiT3.dwg.tmp` 残留 = 上次转换失败，自动重转。

## 3. B 路（LibreDWG）提取结果少/报「截断」

- LibreDWG 0.14 对超大图（数十万对象）输出不完整是已知限制（BLOCKS 段截断、块名编码错误）。skill 已做三级缓解：
  1. BINARY 组码畸形行修复（奇长补 0 / 非 hex 替换）；
  2. 未闭合段截断修复（保留完整块，丢弃截断尾部）；
  3. 块名规则提取（*MODEL_SPACE 大小写兼容、乱码块经 INSERT 展开、孤儿布局块直接提取）。
- 结果仍不完整时：`errors[]` 会标注，优先改用 A 路（CAD 打开图）或 C 路兜底。
- ODA File Converter 是 LibreDWG 的上位替代（商业级转换，兼容性更好），本机未装，后续可按需接入（ezdxf `odafc.readfile()` 一行接入）。

## 4. 提取的文字里出现乱码/噪音

- C 路二进制扫描是启发式降噪（三级过滤），偶尔出现「栖凄畦旗」类伪中文片段（GBK 解码二进制字节的一级区汉字串）——这是设计内可接受的兜底噪音，B 路/A 路数据优先。
- 「足轩\u000b照明配电箱」类片段含控制字符：C 路噪音尾部，忽略即可。
- B 路文字乱码：确认图纸编码（$DWGCODEPAGE），LibreDWG 输出为 GBK，skill 已按 GBK 解码。

## 5. 转 T3 后文字仍读不到

- 确认 `proxy_detect.py` 输出 `verdict=none` 且 `proxy_count=0`（数实例才是判据，类名残留不报）。
- 若 proxy 为 0 但仍缺文字：可能是 XREF 内容（文字在被参照图里）→ 用 `--xref` 递归解析，看 `xrefs[]` 清单里的 unresolved 项。

## 6. 输出目录写不进（SMB 映射盘盘符只读）

所有脚本内置动态输出目录探测（`path_util.ensure_writable_dir`），三级降级：

1. **图纸同目录**（盘符路径）；
2. **同目录 UNC 形式**：SMB 映射盘盘符只读时自动转 `//server/share/...`（如 `X:` → `//192.18.20.69/Moosync/...`）；
3. **系统临时目录**：仍失败才降级。

结果 JSON 的 `output_dir`/打印信息标注实际落盘路径与降级模式（`direct`/`unc`/`temp`）。可用 `--out <目录>` 显式指定。盘符→UNC 映射读自注册表 `HKCU\Network\<盘符>\RemotePath`（`path_util.to_unc`，带缓存）。

## 7. COM 提取慢 / 挂起

- 大图默认快模式（TEXT/MTEXT/INSERT/MULTILEADER/ACAD_TABLE），全量加 `--full`；
- 看门狗 5 分钟硬超时，超时降级并标注「COM 不完整」；
- 提取期间 AutoCAD 内不要操作、不要留弹窗；
- **extract.py 为纯读取，不修改任何系统变量**（2026-08-18 优化）；
- tz3_convert.py 仅在 `SendCommand("TZ3")` 时临时设 `CMDDIA=0`，用完立即恢复 + 30s 主动兜底（超时强制恢复）。

## 8. Ctrl+O 等不弹对话框（命令行模式）——崩溃兜底

**症状**：提取后 AutoCAD 的 `Ctrl+O`、`Ctrl+S` 等不再弹文件对话框，变成命令行提示。

**原因**：tz3_convert.py 为防命令对话框挂起，临时设 `CMDDIA=0`，正常会恢复；但 Python 进程崩溃/被 kill 时未恢复。**extract.py 为纯读取，不修改任何系统变量**，不会导致此问题。

**恢复**（一键）：
```
python "<skill目录>/tz3_convert.py" --restore-guards
```
（需先打开 AutoCAD）。orchestrator 下次启动会自动检测残留快照并打印此恢复命令。

**主动兜底**（30 秒内自动恢复）：tz3_convert 设变量后启动 30s 看门狗线程，超时未恢复则强制恢复，无需人工干预。

**手动恢复**（若一键恢复失败）：在 AutoCAD 命令行输 `CMDDIA` 回车 `1`。

**预防**：转 T3 期间不要强制关闭终端/杀 Python 进程；崩溃后 30s 内看门狗会自动恢复，或尽快运行 `--restore-guards`。

## 9. 注册表改动回滚

- `python tz3_install.py --unregister`：删除 Applications\TZ3Converter 键 + 按 `tz3_install.log.json` 回滚 TRUSTEDPATHS 追加项；
- 手动核对：注册表 `HKCU\Software\Autodesk\AutoCAD\R2x.x\<产品键>\Applications\` 下无 TZ3Converter；TRUSTEDPATHS 中无本 skill 目录。

## 10. 环境重建

- Python（本机无 venv，用 WorkBuddy 自带解释器）：`C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\`（comtypes/ezdxf/pyautocad/numpy/pywin32 已装）；失效时重装：
  `python -m pip install comtypes ezdxf pyautocad numpy --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple`
- LibreDWG 0.14：`~/.workbuddy/bin/libredwg/`（dwgread.exe/dwg2dxf.exe）；可用环境变量 `LIBREDWG_DIR` 指向其他安装位置。
- TZ3 双产物：由用户手动运行 `compile.bat`（csc.exe 被安全策略拦截，编译不能由 agent 代跑）。无 .NET 8 环境时只产 fx48 并在日志明示。

## 11. DWG 修复失败

**症状**：`--repair` 模式执行后未生成 `原名_fix.dwg`，或修复步骤报错。

**排查**：

| 情况 | 处理 |
|------|------|
| AUDIT 失败 | 检查图纸是否严重损坏 → 尝试 `--repair --recover-only` 仅执行 RECOVER |
| PURGE 卡住 | 图纸过大（>100MB）时 PURGE 可能耗时较长，等待或按 ESC 中断 |
| 字典清理报错 | 部分字典不存在属正常（`[无数据]`），非错误 |
| RECOVER 失败 | 图纸损坏严重，尝试用 ODA File Converter 或 AutoCAD 内置 `RECOVER` 命令手动修复 |
| 修复后转 T3 失败 | 检查天正环境是否正常（`tch_kernal.arx` 已加载） |

**修复级别**：`--repair` 默认执行全部 7 级修复；可用 `dwg_repair.py --level 1-7` 单独调整（1=仅 AUDIT，7=全部）。
