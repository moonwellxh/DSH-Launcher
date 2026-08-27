# -*- coding: utf-8 -*-
"""cad_guard 单元测试：快照持久化 + 残留检测 + 恢复逻辑（mock CAD，不依赖真实环境）。"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cad_guard as G  # noqa: E402

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


class FakeDoc:
    Name = "测试图.dwg"
    FullName = r"D:\test\测试图.dwg"

    def __init__(self):
        self._vars = {}

    def GetVariable(self, k):
        return self._vars.get(k, 1)

    def SetVariable(self, k, v):
        self._vars[k] = v


def _reset_env():
    G.SNAP_DIR = Path(tempfile.mkdtemp(prefix="cadguard_test_"))
    G.SNAP_FILE = G.SNAP_DIR / "guards_snapshot.json"
    G.STALE_FILE = G.SNAP_DIR / "guards_snapshot_stale.json"


# 1. save_snapshot 写入 + has_stale 检测
_reset_env()
doc = FakeDoc()
G.save_snapshot(doc, {"FILEDIA": 1, "CMDDIA": 1, "FONTALT": "simplex.shx"})
check(1, "save_snapshot 后 has_stale=True", G.has_stale_snapshot() is True)
snap = G.load_snapshot()
check(2, "快照内容含变量与文档信息",
      snap is not None and snap["vars"]["FILEDIA"] == 1
      and snap["doc_name"] == "测试图.dwg")

# 2. clear_snapshot 删除
G.clear_snapshot()
check(3, "clear_snapshot 后 has_stale=False", G.has_stale_snapshot() is False)

# 3. 残留快照备份（再次 save 时旧档转 _stale）
_reset_env()
G.save_snapshot(doc, {"FILEDIA": 0})
G.save_snapshot(doc, {"FILEDIA": 1})
check(4, "重复 save 时旧档转 stale", G.STALE_FILE.exists())

# 4. restore_from_snapshot：mock comtypes
_reset_env()
G.save_snapshot(doc, {"FILEDIA": 1, "CMDDIA": 1})
fake_doc = FakeDoc()
fake_doc._vars = {"FILEDIA": 0, "CMDDIA": 0}   # 模拟崩溃残留
fake_app = mock.MagicMock()
fake_app.ActiveDocument = fake_doc
with mock.patch("comtypes.client.GetActiveObject", return_value=fake_app):
    ok, lines = G.restore_from_snapshot(verbose=False)
    check(5, "restore 返回 ok", ok is True, str(lines))
    check(6, "FILEDIA 恢复为 1", fake_doc._vars["FILEDIA"] == 1,
          str(fake_doc._vars))
    check(7, "CMDDIA 恢复为 1", fake_doc._vars["CMDDIA"] == 1)
    check(8, "恢复后快照已清理", not G.has_stale_snapshot())

# 5. 无快照时 restore 幂等
_reset_env()
ok, lines = G.restore_from_snapshot(verbose=False)
check(9, "无快照时 restore 返回 ok 且提示无需恢复",
      ok is True and any("无需恢复" in ln for ln in lines))

# 6. AutoCAD 未运行时 restore 失败但不崩溃
_reset_env()
G.save_snapshot(doc, {"FILEDIA": 1})
with mock.patch("comtypes.client.GetActiveObject",
                side_effect=Exception("not running")):
    ok, lines = G.restore_from_snapshot(verbose=False)
    check(10, "CAD 未运行时 restore 返回 False + 提示", ok is False
          and any("未运行" in ln for ln in lines))
    check(11, "失败时快照保留", G.has_stale_snapshot())

# 7. self_check_and_warn：干净时返回 True，脏时返回 False 且打印
_reset_env()
check(12, "干净时 self_check 返回 True", G.self_check_and_warn() is True)
G.save_snapshot(doc, {"FILEDIA": 1})
check(13, "脏时 self_check 返回 False", G.self_check_and_warn() is False)

print(f"cad_guard 单测：{PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
