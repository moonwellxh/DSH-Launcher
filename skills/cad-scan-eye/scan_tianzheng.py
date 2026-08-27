# -*- coding: utf-8 -*-
"""
scan_tianzheng.py — 天正门窗「编号 ↔ 尺寸」兜底工具（启发式，带警告）

依据：《最终设计 rev2》§3 第 4 路说明 + 任务书 §2.1④（保留为兜底，
标注启发式局限）。

⚠️ 已知局限（红线 8）：
  编号与门窗按顺序配对是启发式——二进制扫描的出现顺序与 COM 遍历顺序
  无一致性保证，pairs 可能错位。输出强制带 pairing:"heuristic-order"
  警告。正路是转 T3 后编号变 TEXT 可精确关联（orchestrator 自动处理）。

流程：
  1) 连 AutoCAD 拿目标文档的磁盘路径 FullName
  2) 读 DWG 文件二进制，GBK 解码，正则扫描编号（M/C+数字+可选字母）
  3) 同时 COM 遍历模型空间读 TDbOpening 的尺寸(Width/Height)

用法：
    python scan_tianzheng.py "关键词" ...    # 按文档名关键词匹配（可多个）

输出：JSON（编号清单 + 门窗尺寸 + 启发式配对警告）+ stdout
"""
import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import comtypes
import comtypes.client

RPC_E_CALL_REJECTED = -2147418111


def pick_output_dir(preferred=None):
    """动态输出目录（§8.3）：图纸同目录 → 同目录 UNC 形式（SMB 盘符只读兜底）→ 临时目录。"""
    from path_util import ensure_writable_dir
    d, _mode = ensure_writable_dir(preferred)
    return d


def com_retry(fn, retries=120, delay=0.5):
    for _ in range(retries):
        try:
            return fn()
        except comtypes.COMError as e:
            if e.args and e.args[0] == RPC_E_CALL_REJECTED:
                time.sleep(delay)
                continue
            raise
    raise TimeoutError("COM 调用持续被拒绝")


def scan_numbers(path):
    """扫描 DWG 二进制，提取天正门窗编号（GBK）。"""
    data = open(path, "rb").read()
    txt = data.decode("gbk", errors="ignore")
    pat = re.compile(r"[MC]\d{3,4}[a-z]?\x00")
    nums = []
    for m in pat.finditer(txt):
        num = m.group().rstrip("\x00")
        if txt[m.start() - 1:m.start()] == "A":  # 排除文件头 AC1018 里的 C1018
            continue
        if num not in nums:
            nums.append(num)
    return nums


def main():
    args = sys.argv[1:]
    out_dir = None
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        args = args[:i] + args[i + 2:]
    keywords = args

    try:
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
    except Exception:
        print("[未连接] AutoCAD 未运行。请先打开 AutoCAD 并打开目标 DWG。")
        sys.exit(2)

    docs = app.Documents
    if not keywords:
        matched = [docs.Item(0)]
    else:
        matched = [docs.Item(i) for i in range(docs.Count)
                   if any(k in docs.Item(i).Name for k in keywords)]

    for d in matched:
        dwg_name = com_retry(lambda: d.Name)
        dwg_path = com_retry(lambda: d.FullName)
        saved = com_retry(lambda: d.Saved)
        print(f"\n[文档] {dwg_name}\n[路径] {dwg_path}\n[已保存] {saved}",
              flush=True)

        # 1) COM 读天正门窗尺寸
        openings = []
        ms = com_retry(lambda: d.ModelSpace)
        total = com_retry(lambda: ms.Count)
        for i in range(total):
            obj = com_retry(lambda i=i: ms.Item(i))
            if obj.ObjectName == "TDbOpening":
                try:
                    openings.append({"width": round(float(obj.Width), 1),
                                     "height": round(float(obj.Height), 1),
                                     "layer": str(obj.Layer)})
                except Exception:
                    pass

        # 2) 二进制扫描编号
        numbers = []
        if saved and Path(dwg_path).exists():
            numbers = scan_numbers(dwg_path)
        else:
            print("  ⚠️ 文档未保存或磁盘文件不存在，无法二进制扫描编号"
                  "（请先保存）", flush=True)

        # 按顺序对应（启发式——顺序无一致性保证，输出带警告）
        pairs = []
        for idx, o in enumerate(openings):
            num = numbers[idx] if idx < len(numbers) else ""
            pairs.append({"number": num, "width": o["width"],
                          "height": o["height"], "layer": o["layer"]})

        payload = {
            "dwg": dwg_name, "path": dwg_path, "saved": saved,
            "numbers": numbers, "openings": openings, "pairs": pairs,
            # 红线 8：启发式配对必须带警告
            "pairing": "heuristic-order",
            "warning": ("编号与门窗按顺序配对为启发式，顺序无一致性保证，"
                        "pairs 可能错位。正路：转 T3 后编号变 TEXT 可精确"
                        "关联（orchestrator 自动处理）。"),
        }
        out = pick_output_dir(out_dir or Path(dwg_path).parent) \
            / f"{Path(dwg_name).stem}_天正门窗.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print(f"  [门窗实体] {len(openings)} 个 / [编号] {len(numbers)} 个",
              flush=True)
        print(f"  [输出JSON] {out}", flush=True)
        print(f"  ⚠️ {payload['warning']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[失败] {type(e).__name__}: {e}")
        sys.exit(1)
