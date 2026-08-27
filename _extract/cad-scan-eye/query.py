# -*- coding: utf-8 -*-
"""
query.py — 提取结果投影接口（纯标准库，零依赖）

依据：《最终设计 rev2》§7 第③层投影接口 + 任务书 T4。

默认不改原始 JSON，只做服务端筛选投影，避免 4 万条原始数据灌入 LLM 上下文：

  --summary              图层×类型计数矩阵 + 图幅范围 + 抽样（紧凑输出）
  --filter "<正则>"      内容正则筛选（可用 --layers 白名单叠加）
  --layers <逗号列表>    图层白名单
  --bbox x1,y1,x2,y2     空间范围筛选（世界坐标）
  --handle <id>          按实体句柄取单条完整记录

用法：
    python query.py <结果JSON路径> --summary
    python query.py <结果JSON路径> --filter "消防" --layers 暖通-风管,电气-照明
    python query.py <结果JSON路径> --bbox 0,0,50000,50000
    python query.py <结果JSON路径> --handle 3A7F
"""
import json
import re
import sys
from collections import Counter, OrderedDict


def load_result(path):
    """读取提取结果 JSON。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 各投影函数（可被 orchestrator / SKILL 工作流直接 import 调用）
# ---------------------------------------------------------------------------

def summary(data):
    """图层×类型计数矩阵 + 图幅范围 + 抽样。

    返回紧凑 dict（可 JSON dump < 2KB），供 LLM 判断「钻取什么」。
    """
    texts = data.get("texts", [])
    matrix = OrderedDict()
    xs, ys = [], []
    samples = OrderedDict()
    for t in texts:
        layer = t.get("layer") or "(无图层)"
        typ = t.get("type") or "?"
        matrix.setdefault(layer, Counter())
        matrix[layer][typ] += 1
        for o in t.get("occurrences", []):
            if o.get("x") is not None:
                xs.append(o["x"])
            if o.get("y") is not None:
                ys.append(o["y"])
        # 每图层采样 1 条（内容截断）
        if layer not in samples:
            samples[layer] = (t.get("content") or "")[:60]

    dims = data.get("dims", [])
    attrs = data.get("attrs", [])
    return {
        "dwg": data.get("dwg"),
        "counts": {"texts": len(texts), "dims": len(dims),
                   "attrs": len(attrs),
                   "xrefs": len(data.get("xrefs", []))},
        "bbox": {"xmin": round(min(xs), 1) if xs else None,
                 "xmax": round(max(xs), 1) if xs else None,
                 "ymin": round(min(ys), 1) if ys else None,
                 "ymax": round(max(ys), 1) if ys else None},
        "layers": {layer: dict(c) for layer, c in
                   list(matrix.items())[:60]},   # 前 60 个图层防膨胀
        "layer_total": len(matrix),
        "samples": dict(list(samples.items())[:20]),
    }


def filter_texts(data, pattern=None, layers=None, bbox=None, limit=2000):
    """按正则/图层白名单/空间范围筛选文字记录。

    pattern: 正则字符串（内容匹配）
    layers:  [str] 图层白名单（None=全部）
    bbox:    (x1, y1, x2, y2)（None=全部；按 occurrence 是否落入范围）
    limit:   返回条数上限（防上下文爆炸）
    返回: 筛选后的 texts 子集。
    """
    try:
        pat = re.compile(pattern) if pattern else None
    except re.error as e:
        raise ValueError(f"正则无效: {e}")

    out = []
    for t in data.get("texts", []):
        if pat and not pat.search(t.get("content") or ""):
            continue
        if layers:
            occ_layers = {o.get("layer") for o in t.get("occurrences", [])}
            occ_layers.add(t.get("layer"))
            if not (occ_layers & set(layers)):
                continue
        if bbox:
            x1, y1, x2, y2 = bbox
            if not any(o.get("x") is not None and o.get("y") is not None and
                       x1 <= o["x"] <= x2 and y1 <= o["y"] <= y2
                       for o in t.get("occurrences", [])):
                continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def get_by_handle(data, handle):
    """按实体句柄精确取单条完整记录（含 occurrences 内嵌 handle）。"""
    for t in data.get("texts", []):
        if t.get("handle") == handle:
            return t
        for o in t.get("occurrences", []):
            if o.get("handle") == handle:
                return t
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_bbox(s):
    try:
        x1, y1, x2, y2 = (float(v) for v in s.split(","))
    except (ValueError, TypeError):
        raise ValueError(f"bbox 格式错误（应为 x1,y1,x2,y2）: {s!r}")
    return (x1, y1, x2, y2)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = argv[0]
    data = load_result(path)

    i = 1
    if i < len(argv) and argv[i] == "--summary":
        print(json.dumps(summary(data), ensure_ascii=False, separators=(",", ":")))
        return
    if i < len(argv) and argv[i] == "--handle":
        rec = get_by_handle(data, argv[i + 1])
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        return

    pattern, layers, bbox = None, None, None
    while i < len(argv):
        a = argv[i]
        if a == "--filter":
            pattern = argv[i + 1]
            i += 2
        elif a == "--layers":
            layers = [s.strip() for s in argv[i + 1].split(",") if s.strip()]
            i += 2
        elif a == "--bbox":
            bbox = _parse_bbox(argv[i + 1])
            i += 2
        elif a == "--xref":
            # 递归解析参照由 orchestrator 处理，此处透传 xref 清单
            print(json.dumps(data.get("xrefs", []), ensure_ascii=False,
                             indent=1))
            return
        else:
            i += 1

    sub = filter_texts(data, pattern, layers, bbox)
    print(json.dumps({
        "dwg": data.get("dwg"),
        "filter_criteria": {
            "pattern": pattern, "layers": layers, "bbox": list(bbox) if bbox else None,
        },
        "matched": len(sub),
        "texts": sub,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
