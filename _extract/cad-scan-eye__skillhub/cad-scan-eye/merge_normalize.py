# -*- coding: utf-8 -*-
"""
merge_normalize.py — 多路提取结果归并整合（纯标准库，零依赖）

依据：《最终设计 rev2》§6.1(b)(d) + §7 字段约定 + 任务书 T3。

职责：
  1. occurrences 去重：同内容文字合并为一条，保留全部出现位置
     （同内容在不同位置承载不同语义，空间聚类与回图定位按 occurrence 展开）；
  2. source 优先级：A(COM) > D(T3后读) > B(LibreDWG) > C(二进制扫描)，冲突字段取高优先；
  3. 块内坐标世界变换：插入点/旋转/缩放（含 X/Y 不等比与镜像负值）矩阵换算，
     不等比缩放块内字高 ×Y 缩放修正；
  4. layer_state / plot_height 归一（缺省补全）。

用法：
    from merge_normalize import merge_records, transform_point
    merged = merge_records(records_a + records_b + records_c)
"""
import math

# source 优先级（越靠前越高），可被调用方覆盖
SOURCE_PRIORITY = "ADBC"

# 主记录冲突字段：取最高优先级 source 的值
_CONFLICT_FIELDS = ("height", "plot_height", "layer", "layer_state",
                    "type", "rotation", "block_name")


def transform_point(x, y, insert=(0.0, 0.0), scale=(1.0, 1.0),
                    rotation_deg=0.0):
    """块定义空间坐标 → 世界坐标（2D 仿射：缩放 → 旋转 → 平移）。

    镜像以 X 缩放取负表达（与 ezdxf virtual_entities 语义一致）。
    z 坐标不受块 2D 变换影响，由调用方透传。
    """
    sx, sy = scale
    rad = math.radians(rotation_deg)
    wx = x * sx * math.cos(rad) - y * sy * math.sin(rad) + insert[0]
    wy = x * sx * math.sin(rad) + y * sy * math.cos(rad) + insert[1]
    return wx, wy


def _source_rank(source):
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)  # 未知来源排最后


def _pick(recs, field):
    """从同内容记录组中取冲突字段值：按 source 优先级，取第一个非空。"""
    ranked = sorted(recs, key=lambda r: _source_rank(r.get("source", "?")))
    for r in ranked:
        v = r.get(field)
        if v is not None and v != "":
            return v
    return None


def _expand_occurrences(rec):
    """把一条记录展开为 occurrence 列表。

    输入记录允许两种形态：
      - 已带 occurrences: [{x,y,layer,handle,...}]
      - 平铺字段: {x, y, layer, handle}
    """
    occs = rec.get("occurrences")
    if occs:
        return [dict(o) for o in occs]
    x, y = rec.get("x"), rec.get("y")
    if x is None and y is None:
        return []
    o = {"x": x, "y": y}
    for k in ("layer", "handle", "z", "height", "plot_height"):
        if rec.get(k) is not None:
            o[k] = rec[k]
    return [o]


def _dedup_occurrences(occs):
    """位置去重：同 (x,y) 且同 layer 的 occurrence 只留一条（保留 handle 优先者）。"""
    seen, out = {}, []
    for o in occs:
        key = (round(o.get("x") or 0, 2), round(o.get("y") or 0, 2), o.get("layer"))
        if key in seen:
            # 已有同位置：若新者有 handle 而旧者无，回填 handle
            if seen[key].get("handle") is None and o.get("handle"):
                seen[key]["handle"] = o["handle"]
            continue
        seen[key] = o
        out.append(o)
    return out


def merge_records(records, source_priority=None):
    """多路提取记录归并。

    records: 可迭代，每条含 content（清洗后文本）与 source（A/B/C/D）。
    返回: 合并后记录列表。同 content 合并为一条：
      - occurrences: 全部位置（按首现顺序，位置级去重）
      - height/layer/type 等冲突字段: 取 source 优先级最高者的值
      - source: 主来源标记（最高优先级）
    """
    global SOURCE_PRIORITY
    if source_priority:
        SOURCE_PRIORITY = source_priority

    groups = {}   # content -> [records]
    order = []    # 内容首现顺序
    for r in records:
        c = (r.get("content") or "").strip()
        if not c:
            continue
        if c not in groups:
            groups[c] = []
            order.append(c)
        groups[c].append(r)

    merged = []
    for c in order:
        recs = groups[c]
        occs = []
        for r in recs:
            occs.extend(_expand_occurrences(r))
        occs = _dedup_occurrences(occs)

        m = {"content": c, "occurrences": occs,
             "source": _pick(recs, "source")}
        for f in _CONFLICT_FIELDS:
            v = _pick(recs, f)
            if v is not None:
                m[f] = v
        # handle：取主来源记录自己的 handle（有则带）
        h = _pick(recs, "handle")
        if h:
            m["handle"] = h
        # is_field：任一来源含字段则标注
        if any(r.get("is_field") for r in recs):
            m["is_field"] = True
        merged.append(m)
    return merged


def transform_block_records(block_texts, insert, scale, rotation_deg,
                            block_name):
    """块内文字记录 → 世界坐标记录（含字高修正与原始坐标保留）。

    block_texts: [{"content","x","y","height","layer","handle"}, ...]（块定义空间）
    返回: 变换后记录，顶层字段为世界坐标，保留 block 原始坐标与块名。
    """
    sx, sy = scale[0], scale[1]
    out = []
    for t in block_texts:
        bx, by = t.get("x"), t.get("y")
        wx = wy = None
        if bx is not None and by is not None:
            wx, wy = transform_point(bx, by, insert, scale, rotation_deg)
        r = dict(t)
        r["x"], r["y"] = wx, wy
        r["block_name"] = block_name
        r["block_x"], r["block_y"] = bx, by
        r["block_scale"] = [sx, sy]
        r["block_rotation"] = rotation_deg
        # 不等比缩放块内字高修正（字高 × Y 缩放，rev2 §3 第 2 条）
        if t.get("height") is not None:
            r["height"] = round(t["height"] * abs(sy), 3)
        out.append(r)
    return out


def normalize_layer_state(state):
    """layer_state 归一：None/空 → "on"；其余原样。"""
    if state in (None, ""):
        return "on"
    return str(state)


if __name__ == "__main__":
    # 快速自检（完整用例见 tests/test_merge.py）
    ra = [{"content": "梁下净高4.5m", "source": "A", "x": 1.0, "y": 2.0,
           "layer": "F-TEXT", "height": 350.0, "handle": "3A7F"}]
    rb = [{"content": "梁下净高4.5m", "source": "B", "x": 100.0, "y": 200.0,
           "layer": "0", "height": 300.0, "handle": "2B1"}]
    m = merge_records(ra + rb)
    print(m[0]["source"], "occurrences=", len(m[0]["occurrences"]),
          "height=", m[0]["height"])
    print("变换(10,0) ins(100,50) s(2,2) r90° →",
          tuple(round(v, 2) for v in transform_point(10, 0, (100, 50), (2, 2), 90)))
