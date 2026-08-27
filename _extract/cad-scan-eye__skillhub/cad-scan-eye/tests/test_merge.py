# -*- coding: utf-8 -*-
"""
test_merge.py — merge_normalize 归并模块单元测试

依据：任务书 T3 验收（双路重复数据合并位置数正确、坐标矩阵误差 <0.01）。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_normalize import (merge_records, transform_point,
                             transform_block_records, normalize_layer_state)

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


def check_close(no, desc, got, expect, tol=0.01):
    global PASS, FAIL
    if all(abs(g - e) <= tol for g, e in zip(got, expect)):
        PASS += 1
    else:
        FAIL += 1
        FAILED.append((no, desc, got, expect))


# ---------------------------------------------------------------- 坐标变换
check_close(1, "恒等变换", transform_point(10, 20), (10, 20))
check_close(2, "平移", transform_point(10, 20, insert=(100, 50)), (110, 70))
check_close(3, "等比缩放", transform_point(10, 0, scale=(2, 2)), (20, 0))
check_close(4, "旋转90°", transform_point(10, 0, rotation_deg=90), (0, 10), tol=1e-9)
check_close(5, "平移+缩放+旋转90°",
            transform_point(10, 0, (100, 50), (2, 2), 90), (100, 70), tol=1e-9)
check_close(6, "旋转45°", transform_point(10, 0, rotation_deg=45),
            (10 * math.sqrt(2) / 2, 10 * math.sqrt(2) / 2))
check_close(7, "X镜像（负缩放）", transform_point(5, 3, scale=(-1, 1)), (-5, 3))
check_close(8, "X/Y不等比缩放", transform_point(10, 10, scale=(2, 0.5)), (20, 5))
check_close(9, "负坐标点", transform_point(-10, -5, scale=(2, 2)), (-20, -10))

# ---------------------------------------------------------------- 归并去重
def test_merge_dual():
    ra = [{"content": "梁下净高4.5m", "source": "A", "x": 1.0, "y": 2.0,
           "layer": "F-TEXT", "height": 350.0, "handle": "3A7F"}]
    rb = [{"content": "梁下净高4.5m", "source": "B", "x": 100.0, "y": 200.0,
           "layer": "0", "height": 300.0, "handle": "2B1"}]
    m = merge_records(ra + rb)
    return m


m = test_merge_dual()
check(10, "双路同内容合并为一条", len(m), 1)
check(11, "occurrences 保留全部位置", len(m[0]["occurrences"]), 2)
check(12, "source 取最高优先级 A", m[0]["source"], "A")
check(13, "height 冲突取 A 路值", m[0]["height"], 350.0)
check(14, "layer 冲突取 A 路值", m[0]["layer"], "F-TEXT")
check(15, "handle 取 A 路值", m[0]["handle"], "3A7F")

# 同位置去重：A/B 都报 (1,2) 同一位置 → occurrences 只留 1 条
def test_dedup_same_pos():
    ra = [{"content": "X", "source": "A", "x": 1.0, "y": 2.0, "layer": "L1"}]
    rb = [{"content": "X", "source": "B", "x": 1.0, "y": 2.0, "layer": "L1"}]
    return merge_records(ra + rb)

m2 = test_dedup_same_pos()
check(16, "同位置去重", len(m2[0]["occurrences"]), 1)

# 空内容过滤 + 不同内容不合并
m3 = merge_records([
    {"content": "A", "source": "A", "x": 1, "y": 1},
    {"content": "B", "source": "B", "x": 2, "y": 2},
    {"content": "", "source": "A", "x": 3, "y": 3},
    {"content": None, "source": "A", "x": 4, "y": 4},
])
check(17, "空内容被过滤", len(m3), 2)

# source 优先级 C 最低
m4 = merge_records([
    {"content": "A", "source": "C", "x": 1, "y": 1, "height": 100},
    {"content": "A", "source": "D", "x": 2, "y": 2, "height": 200},
])
check(18, "D 优先于 C", m4[0]["source"], "D")
check(19, "height 取 D 路", m4[0]["height"], 200)

# ---------------------------------------------------------------- 块内变换
bt = [{"content": "门窗M1025", "x": 100.0, "y": 0.0, "height": 250.0,
       "layer": "WINDOW", "handle": "AA1"}]
out = transform_block_records(bt, insert=(1000, 500), scale=(1, 2),
                              rotation_deg=0, block_name="W-1025")
o0 = out[0]
check_close(20, "块内点→世界坐标", (o0["x"], o0["y"]), (1100, 500))
check(21, "block_name 保留", o0["block_name"], "W-1025")
check(22, "原始块内坐标保留", (o0["block_x"], o0["block_y"]), (100.0, 0.0))
check(23, "字高 ×Y缩放 修正", o0["height"], 500.0)

# 镜像（负X缩放）+旋转组合
out2 = transform_block_records([{"content": "M", "x": 5.0, "y": 3.0, "height": 300}],
                               insert=(0, 0), scale=(-1, 1),
                               rotation_deg=90, block_name="B2")
check_close(24, "镜像+旋转变换", (out2[0]["x"], out2[0]["y"]), (-3.0, -5.0), tol=1e-9)

# ---------------------------------------------------------------- 归一化
check(25, "layer_state None→on", normalize_layer_state(None), "on")
check(26, "layer_state 空串→on", normalize_layer_state(""), "on")
check(27, "layer_state frozen 保留", normalize_layer_state("frozen"), "frozen")

# ---------------------------------------------------------------- 汇总
print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_merge.py 全部通过 ✓")
