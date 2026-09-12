#!/usr/bin/env python3
"""l0_doc_patch_v2.py

作用: 把离线用例脚本 l0_token_parse_cases.ps1 的实测结论回写进 v2 设计文档
      （探测必须 $req.Proxy=$null；新增 V3b 行；自证声明补 C 组实测与 stub 进程的坑）。幂等。
输入: --doc <设计文档路径>（默认 D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v2.md）
输出: stdout 每条替换命中数 + 末行 JSON 摘要
复跑: python l0_doc_patch_v2.py
依赖: 标准库
"""
import argparse
import json
import re
import sys

DEFAULT_DOC = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v2.md"

F3_OLD = "- **F3** 令牌有效性以**探测**为准（v2 新增）：对候选令牌地址发一次不跟随重定向的 GET，`303` 视为有效、`401` 视为无效（依据上游 `packages/client/connection/src/browser-auth.ts:244-276`）。探测不消费令牌（同文件 `:244-247` 无消费/失效逻辑），仅在托盘自身 HTTP 会话里铸一次 cookie，对浏览器无影响。"
F3_NEW = F3_OLD + " 探测实现必须显式设 `$req.Proxy = $null`：loopback 请求不得走系统代理（本机存在系统代理配置习惯，见 `assets/tmpl/parts/10-utils.ps1:31-43` 的 `Get-SystemProxy`）；该要求由离线用例实测得出（见 §九.7 C 组）。"

D2_OLD = "- **首选判据 = 探测**（§F3）：`Test-DshTokenUrl` 用 `System.Net.HttpWebRequest` 配 `AllowAutoRedirect = $false`、`Timeout = 3000` 发 GET；`303` → 有效，`401` → 无效，异常 → 视为无效/服务未就绪。"
D2_NEW = "- **首选判据 = 探测**（§F3）：`Test-DshTokenUrl` 用 `System.Net.HttpWebRequest` 配 `AllowAutoRedirect = $false`、`Proxy = $null`、`Timeout = 3000` 发 GET；`303` → 有效，`401` → 无效，异常 → 视为无效/服务未就绪。离线实测（§九.7 C 组）：303 stub → True、401 stub → False、端口关闭 → False。"

V3B_ROW = "| V3b | 探测判据（离线，原始 TCP stub 进程）：stub 返回 303 → 有效；stub 返回 401 → 无效；端口关闭 → 无效 | 是（`l0_token_parse_cases.ps1` C 组） |\n"

SELF_OLD_MARK = "  8. V4 检查器双向验证："
SELF_EXTRA = """  8. 离线用例脚本 `l0_token_parse_cases.ps1` 的 PS 5.1 实测（2026-09-10）：A 组 12 例与 B 组 5 例输出与 §六 期望值逐条一致（A4 令牌 20 字符 → 返回；A7/A8 CRLF/LF 两行 → 末行；A12 70 字符 → 完整返回；B1 早 3600 秒 → null；B2 早 1 秒 → 返回；B3/B4 → null；B5 `-ListenerPid 0` → 候选）；C 组用**独立进程**的原始 TCP stub：303 → True、401 → False、关闭端口 → False（首次实现用 `Start-Job` 传递 `TcpListener` 失败——作业参数会被序列化，收不到连接，据此改为独立 `powershell.exe` 进程；该坑记录在此，避免复审重踩）。同组实测暴露生产实现必须显式 `$req.Proxy = $null`。
"""
SELF_NEW_MARK = "  9. V4 检查器双向验证："

CONTRACT_OLD = "- **期望值归属**：脚本**只输出观测值**（不内置断言、不内置预期）；每条用例的期望结论由本表给出，由独立审查者按表核对脚本输出。"
CONTRACT_NEW = "- **用例分组**：A 组＝解析（A1–A12）、B 组＝新鲜度预筛（B1–B5）、C 组＝探测判据（C1–C3，用独立 `powershell.exe` 进程跑一个只回一帧响应的原始 TCP stub；**不可**用 `Start-Job` 传 `TcpListener`——作业参数会被序列化，监听对象失效）。\n" + CONTRACT_OLD


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()

    with open(args.doc, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    bom = raw[:3] == b"\xef\xbb\xbf"
    counts = {}

    for label, old, new in (("F3-proxy", F3_OLD, F3_NEW), ("D2-proxy", D2_OLD, D2_NEW),
                            ("contract-groups", CONTRACT_OLD, CONTRACT_NEW)):
        n = text.count(old)
        counts[label] = n
        if n:
            text = text.replace(old, new)

    text, n = re.subn(r'(\| V3 \|.*\n)', lambda m: m.group(1) + V3B_ROW, text)
    counts["V3b-row"] = n

    text, n = re.subn(re.escape(SELF_OLD_MARK), SELF_NEW_MARK, text)
    counts["self-renumber"] = n
    text, n = re.subn(re.escape(SELF_NEW_MARK), SELF_EXTRA + SELF_NEW_MARK, text, count=1)
    counts["self-insert"] = n

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
