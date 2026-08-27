# -*- coding: utf-8 -*-
"""
test_structured.py — scan_dwg_structured 修复函数单元测试（合成 DXF 片段）

依据：任务书 T5 验收（组码 3/1 顺序、布局 space 标志、BINARY/截断修复）。
真实图端到端已在开发中实测（_t3 图 359 条、30 万对象图 227 条+截断警告）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scan_dwg_structured import (fix_dxf, _entity_xy, _round, _layer_states)

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


def make_dxf(extra_lines, tail=True):
    """构造最小合法 DXF 文本（GBK），尾部可注入测试内容。"""
    head = ("999\r\nLibreDWG 0.14\r\n  0\r\nSECTION\r\n  2\r\nHEADER\r\n"
            "  9\r\n$ACADVER\r\n  1\r\nAC1018\r\n  0\r\nENDSEC\r\n")
    body = "".join(extra_lines)
    foot = ("  0\r\nEOF\r\n" if tail else "")
    return head + body + foot


tmpdir = tempfile.mkdtemp(prefix="cadscan_test_")
src = os.path.join(tmpdir, "t.dxf")
dst = os.path.join(tmpdir, "t_fixed.dxf")


def run_fix(text):
    with open(src, "wb") as f:
        f.write(text.encode("gbk"))
    return fix_dxf(src, dst)


# ---------------------------------------------------------------- BINARY 修复
# 用例 1：奇长纯 hex "0" → 右侧补 0 成 "00"
t1 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n310\r\n0\r\n"
               "  0\r\nENDBLK\r\n  0\r\nENDSEC\r\n"])
fixed, trunc = run_fix(t1)
check(1, "奇长 hex 补 0 修复计数", fixed, 1)
check(2, "无段截断", trunc, [])
out = open(dst, "rb").read().decode("gbk")
lines = out.split("\n")
i = [k for k, l in enumerate(lines) if l.strip() == "310"][0]
check(3, "修复后值为偶长 00", lines[i + 1].strip(), "00")

# 用例 2：非 hex（GBK 字节串）→ 替换 00
t2 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n310\r\n汉字串\r\n"
               "  0\r\nENDBLK\r\n  0\r\nENDSEC\r\n"])
fixed, trunc = run_fix(t2)
check(4, "非 hex 修复计数", fixed, 1)
out = open(dst, "rb").read().decode("gbk")
lines = out.split("\n")
i = [k for k, l in enumerate(lines) if l.strip() == "310"][0]
check(5, "非 hex 替换为 00", lines[i + 1].strip(), "00")

# 用例 3：合法偶长 hex 不动 + 空值不动
t3 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n310\r\nA040BD\r\n310\r\n\r\n"
               "  0\r\nENDBLK\r\n  0\r\nENDSEC\r\n"])
fixed, trunc = run_fix(t3)
check(6, "合法值不修复", fixed, 0)

# 用例 4：奇长多字符 hex "331" → "3310"
t4 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n311\r\n331\r\n"
               "  0\r\nENDBLK\r\n  0\r\nENDSEC\r\n"])
fixed, trunc = run_fix(t4)
out = open(dst, "rb").read().decode("gbk")
lines = out.split("\n")
i = [k for k, l in enumerate(lines) if l.strip() == "311"][0]
check(7, "奇长多字符右补 0", lines[i + 1].strip(), "3310")

# ---------------------------------------------------------------- 段截断修复
# 用例 5：BLOCKS 段中间截断（无 ENDSEC/EOF）→ 保留完整块 + 补 ENDSEC/EOF
t5 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n  0\r\nTEXT\r\n  8\r\n0\r\n"
               "  1\r\nABC\r\n  0\r\nENDBLK\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\nXREF1\r\n 70\r\n4\r\n  1\r\n..\\\\底图.dwg\r\n"],
              tail=False)   # 无 ENDSEC/EOF
fixed, trunc = run_fix(t5)
check(8, "截断段检测", trunc, ["BLOCKS"])
out = open(dst, "rb").read().decode("gbk")
lines = out.split("\n")
stripped = [l.strip() for l in lines]
check(9, "保留完整块(ENDBLK 在)", "ENDBLK" in stripped, True)
check(10, "截断后补 ENDSEC", "ENDSEC" in stripped, True)
check(11, "截断后补 EOF", "EOF" in stripped, True)
check(12, "截断点后内容丢弃(XREF1 不在)", "XREF1" not in stripped, True)

# 用例 6：完整 DXF（有 EOF）→ 不截断
t6 = make_dxf(["  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n  0\r\nENDBLK\r\n  0\r\n"
               "ENDSEC\r\n"], tail=True)
fixed, trunc = run_fix(t6)
check(13, "完整 DXF 不截断", trunc, [])

# 用例 7：ENTITIES 段后 BLOCKS 截断（尾部已 ENDSEC）→ 只补 EOF 无孤立 ENDSEC
t7 = make_dxf(["  0\r\nSECTION\r\n  2\r\nENTITIES\r\n  0\r\nENDSEC\r\n"
               "  0\r\nSECTION\r\n  2\r\nBLOCKS\r\n  0\r\nBLOCK\r\n  8\r\n0\r\n"
               "  2\r\n*Model_Space\r\n 70\r\n0\r\n310\r\n0\r\n"],
              tail=False)
fixed, trunc = run_fix(t7)
check(14, "ENTITIES+截断 BLOCKS", trunc, ["BLOCKS"])
out = open(dst, "rb").read().decode("gbk")
ends = [l.strip() for l in out.split("\n") if l.strip() in ("ENDSEC", "EOF")]
check(15, "ENDSEC/EOF 序列正确", ends[-2:], ["ENDSEC", "EOF"])

# ---------------------------------------------------------------- 辅助函数
check(16, "_round 正常", _round(3.14159, 2), 3.14)
check(17, "_round None 安全", _round(None), None)
check(18, "_round 字符串安全", _round("abc"), None)

# _entity_xy 用假实体
class _FakeDxf:
    def __init__(self, insert):
        self.insert = insert

class _FakeE:
    def __init__(self, insert):
        self.dxf = _FakeDxf(insert)

import ezdxf.math
check(19, "_entity_xy Vec3", _entity_xy(_FakeE(ezdxf.math.Vec3(1.5, 2.5, 0))),
      (1.5, 2.5))
check(20, "_entity_xy 无 insert 安全", _entity_xy(_FakeE(None)), (None, None))

# ---------------------------------------------------------------- 汇总
print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_structured.py 全部通过 ✓")
