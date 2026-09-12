#!/usr/bin/env python3
"""l0_doc_patch_d1.py

作用: 按 2026-09-10 PS 5.1 原型实测结果修订设计文档（D1 解析式 / D1 约束段 / D2 证据 /
      V2 判据 / 自证声明 7），采用"锚点区间替换"，幂等（已修订后再跑命中数为 0）。
输入: --doc <设计文档路径>（默认 D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md）
输出: stdout 每条替换的命中数 + 末行 JSON 摘要
复跑: python l0_doc_patch_d1.py
依赖: 标准库
"""
import argparse
import json
import re
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md"

NEW_CODE = '''    $ms = [regex]::Matches($text, "http://127\\.0\\.0\\.1:$port/\\?token=([A-Za-z0-9_-]+)")
    if ($ms.Count -eq 0) { return $null }
    $cand = $null
    # 从最后一次启动的行往前取第一个长度合法的令牌（无界捕获 + 代码内区间校验，避免有界量词静默截断）
    for ($i = $ms.Count - 1; $i -ge 0; $i--) {
        if ($ms[$i].Groups[1].Value.Length -ge 20 -and $ms[$i].Groups[1].Value.Length -le 128) {
            $cand = $ms[$i].Value; break
        }
    }
    if (-not $cand) { return $null }
'''

NEW_CONSTRAINT = '''实现约束（5 条）：

1. 字符集限定 `[A-Za-z0-9_-]`，与上游 base64url 判据一致（`packages/client/connection/src/browser-auth.ts:19`）；上游令牌为 32 随机字节 → 43 字符（`packages/client/connection/src/browser-auth.ts:14,52-57`）。
2. 用**无界**量词 `+` 捕获、再在代码内校验长度 20~128，而不是用有界量词：PS 5.1 原型实测（见 §九.7）中 `{20,64}` 对 70 字符令牌返回**被截断**的地址（截断值必然 401 且用户看不出原因）；"无界捕获 + 区间校验"要么返回完整地址，要么判为不可得并走 F4 回退，不会产生静默无效地址。43 是上游当前值，区间刻意放宽以容忍上游长度变化。
3. 多余查询参数不进入匹配（正则不含 `&`）：即便日志行的 URL 带附加参数，取到的 `?token=…` 仍是**单** token 参数，满足上游交换条件 `tokens.length===1`（`packages/client/connection/src/browser-auth.ts:243-247`）。
4. **只接受 `127.0.0.1`**：cookie 与其 authority（规范化后的 `host:port`）绑定（`packages/client/connection/src/browser-auth.ts:69-78,106-108,296`），用 `localhost` 打开会与按 `127.0.0.1` 铸出的 cookie 不匹配；且 `dsh web` 打印的本地地址本来就是 `127.0.0.1`（上游 `packages/bundle/web-app/src/index.ts:261-262` 取 `localWebUrl()`）。因此形如 `http://localhost:3080/?token=…` 的行按"不可得"处理。
5. "取最后一次启动的行"成立的前提是每次启动前日志被删除：`assets/tmpl/parts/mode-source.json` 与 `assets/tmpl/parts/mode-path.json` 的 `__MODE_START_DSH_SERVER__` 段均先 `Remove-Item -LiteralPath $logOut, $logErr`。
'''

D2_EXTRA = '''- 该判据已在 Windows PowerShell 5.1（5.1.19041.6093）原型实测：日志写入时间 16:19:29.672 晚于同进程启动时间 16:19:29.343 → 判定可信 True；把日志时间改为 1 小时前 → 判定可信 False；改为 1 秒前（落在 2 秒容差内）→ 仍判可信 True（容差按设计生效）。
'''

NEW_V2 = '''| V2 | 反例（PS 5.1 函数级原型已跑通，见 §九.7）：无令牌行 → $null；令牌长度 19 → $null；令牌长度 20 → 匹配（区间下界含 20）；端口非 3080 → $null；`localhost` 形式 → $null；多行 → 取最后一行；令牌后带 `&v=1` → 前缀地址（仅 token 参数）；`(LAN: …)` 后缀 → 不受影响；令牌长度 70 → 在合法区间 20~128 内，按设计完整接受（非截断） | 是（离线脚本） |'''

SELF_EXTRA = '''  7. D1 解析式与 D2 可信判据的 PS 5.1 实测（2026-09-10，`powershell.exe -NoProfile -File` 跑 ASCII 原型脚本，PS 5.1.19041.6093；函数级原型含长度校验与新鲜度门）：正例 43 字符令牌行 + 新鲜日志 + 同进程监听 PID → 完整地址；旧版本行 → null；19 字符 → null；20 字符 → 匹配；端口 9999 → null；`localhost` → null；多行 → 末行；`&v=1` → 仅取到 token；`(LAN: …)` 后缀 → 不受影响；日志缺失/空 → null；监听 PID=0 → 返回候选地址；日志早 1 小时 → null、早 1 秒 → 返回地址（2 秒容差生效）；70 字符令牌 → 有界量词 `{20,64}` 返回被截断地址（据此改为无界捕获 + 区间校验，函数级原型下完整返回）。'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()

    with open(args.doc, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"
    counts = {}

    # 1) D1 code: replace the regex + candidate-selection block between two stable anchors
    text, n1 = re.subn(
        r'(    \$text = Read-TextFile \$logOut\n    if \(-not \$text\) \{ return \$null \}\n).*?(    \$pid0 = Get-DshListenerPid\n)',
        lambda m: m.group(1) + NEW_CODE + m.group(2), text, flags=re.S)
    counts["D1-code"] = n1

    # 2) D1 constraint paragraph: replace from its lead-in to the blank line before the next heading
    text, n2 = re.subn(r'实现约束：.*?(?=\n\n### D2)', NEW_CONSTRAINT.rstrip("\n"), text, flags=re.S)
    counts["D1-constraint"] = n2

    # 3) D2: append the empirical bullet before the D3 heading
    text, n3 = re.subn(r'(?=\n\n### D3 菜单项与点击处理)', "\n" + D2_EXTRA.rstrip("\n"), text)
    counts["D2-evidence"] = n3

    # 4) V2 row
    text, n4 = re.subn(r'^\| V2 \|.*$', NEW_V2, text, flags=re.M)
    counts["V2-row"] = n4

    # 5) self-proof item 7
    text, n5 = re.subn(r'(  6\. 编码约束 → .*$)', lambda m: m.group(1) + "\n" + SELF_EXTRA.rstrip("\n"),
                       text, flags=re.M)
    counts["self-proof-7"] = n5

    with open(args.doc, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))
    for k, v in counts.items():
        print("%-18s %d" % (k, v))
    print(json.dumps({"applied": sum(1 for v in counts.values() if v)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
