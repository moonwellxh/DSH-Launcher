#!/usr/bin/env python3
"""l0_repair_v2.py

作用: 修复两处问题（幂等）——
      1) l0_doc_patch_v2.py 非幂等造成的重复：F3 附加句、测试契约"用例分组"句、V3b 表行、
         自证声明第 8 项（各去重后只保留一份，位置固定）；
      2) l0_anchor_check.py 对 `$DSH_HOME/...` 这类环境变量路径误报 fail：为其加跳过守卫。
输入: 无参数（路径内嵌）
输出: stdout 每条操作的命中数 + 末行 JSON；exit 0
复跑: python l0_repair_v2.py   （再跑一次应全为 0/已存在）
依赖: 标准库
"""
import json
import os
import re
import sys

DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v2.md"
CRAWLER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "l0_anchor_check.py")

F3_EXTRA = " 探测实现必须显式设 `$req.Proxy = $null`：loopback 请求不得走系统代理（本机存在系统代理配置习惯，见 `assets/tmpl/parts/10-utils.ps1:31-43` 的 `Get-SystemProxy`）；该要求由离线用例实测得出（见 §九.7 C 组）。"
F3_BASE_TAIL = "仅在托盘自身 HTTP 会话里铸一次 cookie，对浏览器无影响。"

CONTRACT_EXTRA = "- **用例分组**：A 组＝解析（A1–A12）、B 组＝新鲜度预筛（B1–B5）、C 组＝探测判据（C1–C3，用独立 `powershell.exe` 进程跑一个只回一帧响应的原始 TCP stub；**不可**用 `Start-Job` 传 `TcpListener`——作业参数会被序列化，监听对象失效）。"
CONTRACT_ANCHOR = "- **期望值归属**："

V3B_ROW = "| V3b | 探测判据（离线，原始 TCP stub 进程）：stub 返回 303 → 有效；stub 返回 401 → 无效；端口关闭 → 无效 | 是（`l0_token_parse_cases.ps1` C 组） |"
SELF8_PREFIX = "  8. 离线用例脚本 `l0_token_parse_cases.ps1` 的 PS 5.1 实测"

GUARD_ANCHOR = '    if path.endswith("dsh-web.log"):'
GUARD = '    if path.startswith(("$", "~", "%")):\n        return ("skip", "env-var or home-relative path")\n'


def main():
    counts = {}

    # --- 1) crawler guard ---
    with open(CRAWLER, "rb") as fh:
        crawler = fh.read().decode("utf-8")
    if GUARD in crawler:
        counts["crawler-guard"] = 0
    else:
        n = crawler.count(GUARD_ANCHOR)
        counts["crawler-guard"] = n
        if n:
            crawler = crawler.replace(GUARD_ANCHOR, GUARD + GUARD_ANCHOR, 1)
            with open(CRAWLER, "wb") as fh:
                fh.write(crawler.encode("utf-8"))

    # --- 2) doc dedupe / normalize ---
    with open(DOC, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"

    # F3: drop every copy of the extra sentence, then re-append exactly one after the base tail
    n = text.count(F3_EXTRA)
    counts["F3-extra-removed"] = n
    text = text.replace(F3_EXTRA, "")
    if text.count(F3_BASE_TAIL) == 1:
        text = text.replace(F3_BASE_TAIL, F3_BASE_TAIL + F3_EXTRA, 1)
        counts["F3-extra-readded"] = 1
    else:
        counts["F3-extra-readded"] = 0

    # contract: drop every copy, insert exactly one before the "期望值归属" bullet
    n = text.count(CONTRACT_EXTRA + "\n")
    counts["contract-removed"] = n
    text = text.replace(CONTRACT_EXTRA + "\n", "").replace(CONTRACT_EXTRA, "")
    if text.count(CONTRACT_ANCHOR) == 1:
        text = text.replace(CONTRACT_ANCHOR, CONTRACT_EXTRA + "\n" + CONTRACT_ANCHOR, 1)
        counts["contract-readded"] = 1
    else:
        counts["contract-readded"] = 0

    # V3b rows: keep exactly one, placed right after the V3 row
    n = len(re.findall(r'^\| V3b \|.*$', text, flags=re.M))
    counts["v3b-removed"] = n
    text = re.sub(r'^\| V3b \|.*\n?', '', text, flags=re.M)
    text, k = re.subn(r'(\| V3 \|.*\n)', lambda m: m.group(1) + V3B_ROW + "\n", text)
    counts["v3b-readded"] = k

    # self-proof item 8: keep exactly one (the first)
    lines = text.split("\n")
    kept, removed = [], 0
    seen8 = False
    for line in lines:
        if line.startswith(SELF8_PREFIX):
            if seen8:
                removed += 1
                continue
            seen8 = True
        kept.append(line)
    counts["self8-removed"] = removed
    text = "\n".join(kept)

    with open(DOC, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(text.encode("utf-8"))

    for k, v in counts.items():
        print("%-22s %d" % (k, v))
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
