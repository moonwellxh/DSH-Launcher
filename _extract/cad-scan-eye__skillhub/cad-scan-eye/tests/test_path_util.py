# -*- coding: utf-8 -*-
"""path_util 单元测试：SMB 盘符→UNC 转换 + 可写目录探测降级链。

背景：SMB 映射盘（如 X:）在受限环境对盘符路径只读、UNC 形式可写。
本测试用 mock 验证 to_unc 转换与 ensure_writable_dir 的 direct→unc→temp 降级顺序。
"""
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import path_util as P  # noqa: E402

PASS = 0
FAIL = 0


def check(no, desc, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {no} {desc}")
    else:
        FAIL += 1
        print(f"  [FAIL] {no} {desc}  {detail}")


MAP = {"X": r"\\192.18.20.69\Moosync"}

# ---------------------------------------------------------------- to_unc
with mock.patch.object(P, "_network_drive_map", return_value=MAP):
    P.reset_cache()
    check(1, "盘符正斜杠转 UNC",
          P.to_unc("X:/a/b.dwg") == "//192.18.20.69/Moosync/a/b.dwg",
          P.to_unc("X:/a/b.dwg"))
    check(2, "盘符反斜杠转 UNC",
          P.to_unc("X:\\a\\b.dwg") == "//192.18.20.69/Moosync/a/b.dwg",
          P.to_unc("X:\\a\\b.dwg"))
    check(3, "无映射盘符返回 None", P.to_unc("C:/a.dwg") is None)
    check(4, "相对路径返回 None", P.to_unc("a.dwg") is None)
    check(5, "已是 UNC 返回 None", P.to_unc("//srv/share/a.dwg") is None)
P.reset_cache()

# ---------------------------------------------------------------- ensure_writable_dir
with mock.patch.object(P, "_network_drive_map", return_value=MAP):
    P.reset_cache()

    # direct：盘符可写
    with mock.patch.object(P, "_is_writable", return_value=True):
        d, mode = P.ensure_writable_dir("X:/a")
        check(6, "盘符可写 → direct",
              mode == "direct" and d.as_posix() == "X:/a",
              f"mode={mode} dir={d}")

    # unc：盘符只读、UNC 可写
    def fake_writable(p):
        return p.as_posix().startswith("//")
    with mock.patch.object(P, "_is_writable", side_effect=fake_writable):
        d, mode = P.ensure_writable_dir("X:/a")
        check(7, "盘符只读+UNC 可写 → unc",
              mode == "unc" and d.as_posix() == "//192.18.20.69/Moosync/a",
              f"mode={mode} dir={d}")

    # temp：都不可写
    with mock.patch.object(P, "_is_writable", return_value=False):
        d, mode = P.ensure_writable_dir("X:/a")
        check(8, "都不可写 → temp", mode == "temp", f"mode={mode}")

    # 无 preferred → temp
    with mock.patch.object(P, "_is_writable", return_value=True):
        d, mode = P.ensure_writable_dir(None)
        check(9, "无 preferred → temp", mode == "temp", f"mode={mode}")
P.reset_cache()

print(f"path_util 单测：{PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
