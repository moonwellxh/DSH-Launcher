# -*- coding: utf-8 -*-
"""
test_query.py — query 投影接口单元测试

依据：任务书 T4 验收：
  - 对 4 万条测试 JSON，summary 输出 <2KB；
  - filter/bbox 结果与全量手工核对一致；
  - handle 精确命中。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from query import summary, filter_texts, get_by_handle, load_result, _parse_bbox

PASS = 0
FAIL = 0
FAILED = []


def check(no, desc, got, expect):
    global PASS, FAIL
    if got == expect:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append((no, desc, got, expect))


# ---------------------------------------------------------------- 构造 4 万条数据
def make_big_data(n=40000):
    texts = []
    for i in range(n):
        layer = f"L{i % 40}"
        texts.append({
            "handle": f"{i:X}",
            "content": f"测试文字{i}" if i % 100 != 0 else f"消防控制室面积{i}",
            "type": "单行" if i % 2 == 0 else "多行",
            "layer": layer,
            "occurrences": [{"x": float(i % 1000), "y": float(i // 1000),
                             "layer": layer, "handle": f"{i:X}"}],
        })
    return {"dwg": "big.dwg", "texts": texts, "dims": [], "attrs": [],
            "xrefs": []}


BIG = make_big_data()

# ---------------------------------------------------------------- summary
s = summary(BIG)
size = len(json.dumps(s, ensure_ascii=False, separators=(",", ":")))
check(1, "4万条 summary 输出 <2KB", size < 2048, True)
check(2, "文字计数正确", s["counts"]["texts"], 40000)
check(3, "图层计数", s["layer_total"], 40)
check(4, "图幅范围", s["bbox"], {"xmin": 0.0, "xmax": 999.0, "ymin": 0.0, "ymax": 39.0})

# ---------------------------------------------------------------- filter
f1 = filter_texts(BIG, pattern="消防控制室")
check(5, "正则筛选命中数", len(f1), 400)
check(6, "正则筛选内容正确", f1[0]["content"], "消防控制室面积0")

f2 = filter_texts(BIG, layers=["L0"])
check(7, "图层白名单命中数", len(f2), 1000)
check(8, "图层白名单内容正确",
      all(t["layer"] == "L0" for t in f2[:10]), True)

f3 = filter_texts(BIG, pattern="消防", layers=["L0"])
# 消防条 i%100==0 且 L0 层 i%40==0 → i%200==0，共 200 条
check(9, "正则+图层叠加", len(f3), 200)

f4 = filter_texts(BIG, bbox=(0, 0, 100, 100), limit=100000)
# x = i%1000, y = i//1000；y ≤ 39 ≤ 100 恒成立；x ≤ 100 每千块 101 个 × 40 块
expect4 = 40 * 101
check(10, "bbox 筛选与手工核对一致", len(f4), expect4)

f5 = filter_texts(BIG, pattern="测试文字", limit=50)
check(11, "limit 上限生效", len(f5), 50)

# ---------------------------------------------------------------- handle
h = get_by_handle(BIG, "1234")
check(12, "handle 精确命中", h is not None and h["content"] == "测试文字4660", True)
check(13, "handle 不存在返回 None", get_by_handle(BIG, "NOPE"), None)

# ---------------------------------------------------------------- bbox 解析
check(14, "bbox 参数解析", _parse_bbox("0,0,100,200"), (0.0, 0.0, 100.0, 200.0))
try:
    _parse_bbox("abc")
    check(15, "非法 bbox 抛错", False, True)
except ValueError:
    check(15, "非法 bbox 抛错", True, True)

# ---------------------------------------------------------------- 汇总
print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_query.py 全部通过 ✓")
