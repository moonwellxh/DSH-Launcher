#!/usr/bin/env python3
"""l0_registry.py

作用: 生成任务级 registry.json（可执行事实源）——登记本任务全部确定性脚本的 code_path/run/hash。
输入: 无参数（路径内嵌）
输出: var/task-scripts/tray-token-open/registry.json（UTF-8 无 BOM）
复跑: python l0_registry.py
依赖: 标准库
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_V2 = "D:\\\\DSHS\\\\升级\\\\托盘带令牌恢复入口-需求与设计-v6.md"
DOC_V1 = "D:\\DSHS\\升级\\托盘带令牌恢复入口-需求与设计-v1.md"

ENTRIES = [
    {
        "name": "l0_anchor_check",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_anchor_check.py"),
        "entrypoint": "main",
        "run": 'python l0_anchor_check.py --doc "%s"' % DOC_V2,
        "purpose": "校验文档中每条 `文件:行` 引用锚点真实存在（模板 / 生成物 / 上游 tag 三类），并独立重算版本号、日志行数、生成物 BOM、parts 编码等事实；skip 仅限环境变量路径",
    },
    {
        "name": "l0_citation_normalize",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_citation_normalize.py"),
        "entrypoint": "main",
        "run": 'python l0_citation_normalize.py --doc "%s"' % DOC_V1,
        "purpose": "幂等规范化 v1 文档的引用写法（去 ~ 前缀、补全 parts/setup/mode 相对路径、补全上游全路径），使锚点可被 l0_anchor_check 无歧义解析",
    },
    {
        "name": "l0_doc_patch_d1",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_doc_patch_d1.py"),
        "entrypoint": "main",
        "run": 'python l0_doc_patch_d1.py --doc "%s"' % DOC_V1,
        "purpose": "按 PS 5.1 原型实测结果修订 v1 的 D1/D2/V2/自证声明（锚点区间替换）",
    },
    {
        "name": "l0_doc_patch_v2",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_doc_patch_v2.py"),
        "entrypoint": "main",
        "run": "python l0_doc_patch_v2.py",
        "purpose": "把离线用例实测结论回写 v2（探测必须 $req.Proxy=$null、新增 V3b 行、自证声明补 C 组实测与 stub 进程坑）",
    },
    {
        "name": "l0_repair_v2",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_repair_v2.py"),
        "entrypoint": "main",
        "run": "python l0_repair_v2.py",
        "purpose": "修复 l0_doc_patch_v2 非幂等造成的重复段（F3/契约/V3b/自证项各留一份）并为锚点脚本加环境变量路径守卫",
    },
    {
        "name": "l0_repair_v2b",
        "ns": "document",
        "code_path": os.path.join(HERE, "l0_repair_v2b.py"),
        "entrypoint": "main",
        "run": "python l0_repair_v2b.py",
        "purpose": "让锚点脚本的裸文件名解析覆盖本任务目录（任务脚本被文档以裸名引用时不再记为无法解析）",
    },
    {
        "name": "l0_token_parse_cases",
        "ns": "code",
        "code_path": os.path.join(HERE, "l0_token_parse_cases.ps1"),
        "entrypoint": "script",
        "run": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File l0_token_parse_cases.ps1",
        "purpose": "V1/V2/V3/V3b 离线用例：A 组解析 12 例、B 组新鲜度预筛 5 例、C 组探测判据 3 例（原始 TCP stub 独立进程）；只输出观测值，不内置期望",
    },
    {
        "name": "l0_tray_artifact_check",
        "ns": "code",
        "code_path": os.path.join(HERE, "l0_tray_artifact_check.ps1"),
        "entrypoint": "script",
        "run": 'powershell.exe -NoProfile -File l0_tray_artifact_check.ps1 -Path "D:\\DSHS\\DSH-tray.ps1" -MarkersCsv "打开 Web UI,退出并停止 DSH" -MinMenuItems 13',
        "purpose": "V4 生成物校验：UTF-8 BOM / 仅 CRLF / 语法解析 0 错 / 中文标记存在 / 无 U+FFFD / 菜单项数下限；基线 exit=0、故障样本 exit=1",
    },
]


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    for e in ENTRIES:
        e["hash"] = sha256(e["code_path"]) if os.path.exists(e["code_path"]) else "MISSING"
    doc = {"task_id": "tray-token-open", "created_at": "2026-09-10", "object": DOC_V2, "entries": ENTRIES}
    out = os.path.join(HERE, "registry.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"registry": out, "entries": len(ENTRIES), "missing": [e["name"] for e in ENTRIES if e["hash"] == "MISSING"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
