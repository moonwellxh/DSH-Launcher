#!/usr/bin/env python3
"""l0_sop_v4_patch.py

作用: 把第三轮窄范围核验的 5 轻微 + 2 建议落到 SOP v4（含订正 v3 的两处事实错误）。幂等。
输入: --doc <v4 文档路径>（应已从 v3 复制）
输出: 每条规则命中数 + JSON
复跑: python l0_sop_v4_patch.py   （再跑应全 0）
依赖: 标准库（自动处理 LF/CRLF）
"""
import argparse
import json
import sys

DEFAULT = "D:\\DSHS\\升级\\DSH-Web-打不开-人工恢复SOP-v4.md"

RULES = [
    ("ver", "- 版本：**v3**（2026-09-10）", "- 版本：**v4**（2026-09-10）"),

    ("trail",
     "→ **v3（第二轮窄范围复审 1 阻断 D1 + 3 严重 D2/D3/D4 + 5 轻微 D5–D9 + 2 建议 D10/D11）**；逐条对照见 §十二",
     "→ **v3（第二轮窄范围复审 1 阻断 D1 + 3 严重 D2/D3/D4 + 5 轻微 D5–D9 + 2 建议 D10/D11）** "
     "→ **v4（第三轮窄范围核验：阻断 0 / 严重 0，采纳其 5 轻微 + 2 建议，并订正 v3 两处事实错误）**；逐条对照见 §十二"),

    ("no-incognito-attribution",
     "- 无痕窗口**仍报同一个错** → 说明服务端当时提供的产物与客户端不一致 → **R5′**（完整构建后重启）。",
     "- 无痕窗口**仍报同一个错** → 说明问题**不在（或不只在）**原浏览器的缓存 → 走 **R5′**（检查服务端构建完整性）。\n"
     "  **归因边界**：按上游实现，服务端**不可能**注入“缺少 `batches` 的 BOOT”（见上），所以这一支更可能是“构建期间产物不完整、或 dist 与 boot 数据不一致”，"
     "而不是 §一 那条缓存成因。"),

    ("git-bash-header",
     "**Git Bash（备用；仅当该机装了 Git Bash。本机未装，故此形式未在本机验证）**",
     "**Git Bash（备用；本机实测可用：`D:\\Git\\bin\\bash.exe`，GNU bash 5.2.26 msys）**"),

    ("node-auto-headers",
     "HTTP 头部名大小写不敏感，看到大写形式也正常；关键是这三样：`303`、`location: /`、`set-cookie: dsh-auth-`。",
     "HTTP 头部名大小写不敏感，看到大写形式也正常；关键是这三样：`303`、`location: /`、`set-cookie: dsh-auth-`。\n"
     "另：Node 还会自动加 `Date`、`Connection`、`Keep-Alive`、`Transfer-Encoding` 等头（驼峰大小写），逐行比对时会“多出内容”，不影响判定。"),

    ("r5-rehandshake",
     "3. 重新启动（双击桌面「启动DSH」），再重跑 R0 → 按 §一 重新定位；**之后仍需清一次该站点的浏览器缓存**（新产物需要新的 index.html）。",
     "3. 重新启动（双击桌面「启动DSH」），再重跑 R0 → 按 §一 重新定位；**之后仍需清一次该站点的浏览器缓存**（新产物需要新的 index.html）。\n"
     "   **注意**：清站点数据等于删掉 cookie，所以清完**必须重跑 R1 取一次令牌地址再打开**——0.1.5+ 上裸地址此时必然 401。"),

    ("myth5",
     "5. **不要**在构建期间让看护狗把 Web 拉起来：半构建产物会让客户端拿到不一致的启动数据（§一）。",
     "5. **不要**在构建期间让看护狗把 Web 拉起来：构建中被拉起的 Web 会提供不完整的产物。"
     "**注意**：这与 §一 那条“缓存导致 `batches` 报错”是**两回事**，不要把两者的结论混用。"),

    ("batches-row",
     "| `batches` 报错的成因 | 依据上游 `packages/client/modules/src/client/manifest.ts:178-179`（抛错点）与 "
     "`packages/client/modules/src/index.ts:727-728,498-499`（恒产出并在注入前解引用）；本机 0.1.1-rc.2 树内 `batches` 零命中，"
     "故\"升级前缓存的旧 shell 直接抛该错\"不成立 |",
     "| `batches` 报错的成因 | 依据上游 `packages/client/modules/src/client/manifest.ts:178-179`（唯一抛错点）与 "
     "`packages/client/modules/src/index.ts:727-728,498-499`（恒产出 `batches`，且在注入前解引用）；本机 0.1.1-rc.2 的 "
     "**client-modules 引导路径不含** `batches`（其 BOOT 形态为 `{rev, entries}`），故\"升级前缓存的旧 shell 直接抛该错\"不成立。"
     "**v4 订正**：v3 写\"树内 `batches` 零命中\"字面不成立——全文检索该词在树内有大量**同名不同义**命中"
     "（如 `sessions/projection-store.ts`），正确表述即本行前述 |"),

    ("git-bash-row",
     "| Git Bash 形式 | 本机未装 Git Bash；命令形态依据他机问题报告 §5.1 的同类做法 |",
     "| Git Bash 形式 | **本机实测（v4 订正）**：本机装有 Git Bash（`D:\\Git\\bin\\bash.exe`，GNU bash 5.2.26 msys）；"
     "§三 的单行形式与多行 `${PORT}`/`$LOG` 形式均实跑通过（合成日志取到末条令牌、真实日志空输出）。v3 写\"本机未装\"有误 |"),

    ("d3-row",
     "| D3 \"服务端半构建\"根因不成立 | 严重 | 删除该根因并写明推翻依据（上游恒产出 `batches` 且在注入前解引用；0.1.1-rc.2 树内无该字符串） |",
     "| D3 \"服务端半构建\"根因不成立 | 严重 | 删除该根因并写明推翻依据（上游恒产出 `batches` 且在注入前解引用；"
     "本机 0.1.1-rc.2 的 client-modules 引导路径不含 `batches`，其 BOOT 形态为 `{rev, entries}`） |"),

    ("codeblock-note",
     "## 二、R0 取证（30 秒，三条命令）\n\n```powershell",
     "## 二、R0 取证（30 秒，三条命令）\n\n"
     "> **怎么用这些代码块**：直接**复制粘贴到 PowerShell 控制台**执行（本 SOP 就是按这个用法验证的）。\n"
     "> 若要把它们**存成 .ps1 文件**再运行，必须存为 **UTF-8 带 BOM**（或 ANSI/GBK）：含中文的 .ps1 若是 UTF-8 **无 BOM**，"
     "PowerShell 5.1 会按 GBK 误读并直接报 `ParserError`（本机 5.1.19041.6093 实测；编写本 SOP 的验证脚本时也踩过一次）。\n\n"
     "```powershell"),

    ("appendix", "## 附：一键复制区（v3）", "## 附：一键复制区（v4）"),
]

V34_TABLE = """
**v3 → v4 修订对照（第三轮窄范围核验：阻断 0 / 严重 0，以下为其 5 轻微 + 2 建议，另订正 v3 两处事实错误）**

| 复审意见 | 级别 | v4 处理 |
|---|---|---|
| 1 §一“无痕仍报同错”的归因缺支撑 | 轻微 | §一 改为“问题**不在（或不只在）**原浏览器缓存”，并写明归因边界（服务端不可能注入缺 `batches` 的 BOOT） |
| 2 §九 仍沿用已被推翻的“半构建”说法 | 轻微 | §九 第 5 条改写，并显式声明它与 §一 那条成因是两回事 |
| 3 “树内 `batches` 零命中”字面不成立 | 轻微 | §十二 订正为“client-modules 引导路径不含 `batches`”，并记明全文检索有大量同名不同义命中 |
| 4 本机其实装有 Git Bash | 轻微 | §三 与 §十二 改列**本机实测**（`D:\\Git\\bin\\bash.exe`，bash 5.2.26），单行与多行形式均实跑通过 |
| 5 含中文代码块存成 .ps1 会 `ParserError` | 轻微 | §二 增“怎么用这些代码块”提示（粘贴到控制台；存文件须 UTF-8 带 BOM 或 ANSI/GBK） |
| 6 R5′ 清缓存后未提醒重取令牌地址 | 建议 | §六 第 3 步补上“清完必须重跑 R1” |
| 7 R3 期望块未说明 Node 自动头 | 建议 | §四 期望块下补注 `Date`/`Connection`/`Keep-Alive`/`Transfer-Encoding` |
"""

MARKER = "| D11 R4 未说明\"手上还没有地址时先跑 R1\" | 建议 | §五 第 2 步补上 |\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT)
    args = ap.parse_args()

    with open(args.doc, "rb") as fh:
        raw = fh.read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")

    counts = {}
    for label, old, new in RULES:
        n = text.count(old)
        counts[label] = n
        if n:
            text = text.replace(old, new, 1)

    if "v3 → v4 修订对照" in text:
        counts["v34-table"] = 0
    else:
        n = text.count(MARKER)
        counts["v34-table"] = n
        if n:
            text = text.replace(MARKER, MARKER + V34_TABLE, 1)

    out = text.replace("\n", "\r\n") if crlf else text
    with open(args.doc, "wb") as fh:
        if bom:
            fh.write(b"\xef\xbb\xbf")
        fh.write(out.encode("utf-8"))
    for k, v in counts.items():
        print("%-26s %d" % (k, v))
    print(json.dumps({"applied": sum(1 for v in counts.values() if v)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
