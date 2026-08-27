# -*- coding: utf-8 -*-
"""
test_xref.py — XREF 检测单元测试（合成 DXF）

依据：任务书 T7 验收（含 2 Attach + 1 Overlay + 1 丢失参照的测试图，
清单四项状态全对）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scan_dwg_structured import _extract_xrefs

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


def make_dxf_with_xrefs(blocks):
    """构造含 XREF 块记录的 DXF（BLOCKS 段）。"""
    head = ("999\r\nLibreDWG 0.14\r\n  0\r\nSECTION\r\n  2\r\nHEADER\r\n"
            "  9\r\n$ACADVER\r\n  1\r\nAC1018\r\n"
            "  9\r\n$DWGCODEPAGE\r\n  3\r\nANSI_936\r\n"
            "  0\r\nENDSEC\r\n"
            "  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n")
    body = ""
    for name, flags, path in blocks:
        body += ("  0\r\nBLOCK\r\n  8\r\n0\r\n  2\r\n{0}\r\n 70\r\n{1}\r\n"
                 "  1\r\n{2}\r\n 10\r\n0.0\r\n 20\r\n0.0\r\n 30\r\n0.0\r\n"
                 "  0\r\nENDBLK\r\n").format(name, flags, path)
    foot = "  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
    text = head + body + foot
    p = os.path.join(tempfile.mkdtemp(prefix="xr_"), "x.dxf")
    with open(p, "wb") as f:
        f.write(text.encode("gbk"))
    return p


import ezdxf

# 2 Attach + 1 Overlay + 1 丢失参照（flags: 4=attach xref, 12=overlay xref）
path = make_dxf_with_xrefs([
    ("AXIS", 4, r"..\\底图\\轴网.dwg"),
    ("GRID", 4, r"D:\\refs\\网格.dwg"),
    ("PLAN_OV", 12, r"C:\\refs\\平面_overlay.dwg"),
    ("LOST", 4, r"Z:\\不存在\\丢失参照.dwg"),
])
doc = ezdxf.readfile(path)
xrefs = _extract_xrefs(doc)
check(1, "检测到 4 个 XREF", len(xrefs), 4)

by_name = {x["name"]: x for x in xrefs}
check(2, "Attach 类型正确", by_name["AXIS"]["type"], "attach")
check(3, "Overlay 类型正确", by_name["PLAN_OV"]["type"], "overlay")
check(4, "路径保留", by_name["AXIS"]["path"], r"..\\底图\\轴网.dwg")
check(5, "丢失参照也在清单（状态由调用方判）",
      by_name["LOST"]["path"], r"Z:\\不存在\\丢失参照.dwg")

# 无 XREF 的图 → 空清单
path2 = make_dxf_with_xrefs([("*Model_Space", 0, ""), ("LEB", 0, "")])
doc2 = ezdxf.readfile(path2)
check(6, "无 XREF 图为空", _extract_xrefs(doc2), [])

print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_xref.py 全部通过 ✓")
