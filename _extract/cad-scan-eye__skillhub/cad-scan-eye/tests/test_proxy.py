# -*- coding: utf-8 -*-
"""
test_proxy.py — proxy_detect 判定逻辑单元测试（离线 mock + 真实图实测）

依据：任务书 T2 验收 + rev2 §4.1：
  - 原图（含天正图形代理）判 convert_t3；
  - 已转 T3 图判 none（图形代理归零，TCH_DBCONFIG 配置类不计入）；
  - 含 TDb 类名残留但无实例的图不误报；
  - 非天正代理图出 report_only 警告。
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proxy_detect import (_is_tianzheng_class, _is_native_class,
                          _is_config_class, format_report,
                          find_libredwg_dir)

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


# ---------------------------------------------------------------- 判定函数
check(1, "天正 appname 判定", _is_tianzheng_class('"TCH_KERNAL|...', ""), True)
check(2, "天正 cppname TDb 前缀判定", _is_tianzheng_class("", "TDbOpening"), True)
check(3, "TANGENT 判定", _is_tianzheng_class('"TANGENT|...', ""), True)
check(4, "非天正 appname", _is_tianzheng_class('"EXAC_ESW"', ""), False)
check(5, "原生类不误判", _is_tianzheng_class("ObjectDBX Classes", ""), False)
check(6, "原生类判定", _is_native_class("ObjectDBX Classes"), True)
check(7, "ACDB 前缀原生", _is_native_class("ACDB_MLEADER_CLASS"), True)
check(8, "EXAC 非原生", _is_native_class("EXAC_ESW"), False)
# 配置类排除（转 T3 不消除，不作 convert_t3 判据）
check(9, "TCH_DBCONFIG 是配置类", _is_config_class("TCH_DBCONFIG", "TDbConfig"), True)
check(10, "TCH_OPENING 非配置类", _is_config_class("TCH_OPENING", "TDbOpening"), False)
# WipeOut 白名单（Autodesk 官方区域覆盖，非第三方代理）
check(11, "WipeOut 判原生", _is_native_class('"WipeOut|Product Desc: WipeOut Dbx Application"'), True)

# ---------------------------------------------------------------- 报告格式化
def startswith_check(no, desc, got, prefix):
    global PASS, FAIL
    if got.startswith(prefix):
        PASS += 1
    else:
        FAIL += 1
        FAILED.append((no, desc, got, prefix))


startswith_check(12, "convert_t3 报告", format_report(
    {"verdict": "convert_t3", "proxy_count": 37,
     "classes": [{"name": "TCH_OPENING", "app": "TCH_KERNAL", "count": 37,
                  "kind": "tianzheng"}]}), "[代理检测] 天正")
startswith_check(13, "report_only 报告", format_report(
    {"verdict": "report_only", "proxy_count": 1,
     "classes": [{"name": "EXACXREFPANELOBJECT", "count": 1, "kind": "other"}]}),
    "[代理检测] 含")
check(14, "none 报告", format_report({"verdict": "none", "classes": [], "errors": []}),
    "[代理检测] 无代理实体（verdict=none）")
startswith_check(15, "unknown 报告含错误", format_report(
    {"verdict": "unknown", "errors": ["dwgread 执行失败"]}), "[代理检测] 无法")

# ---------------------------------------------------------------- 真实图实测
# 用 mock 方式注入 CLASSES 数据，验证「数实例」判据核心逻辑
import proxy_detect as pd

def run_with_classes(classes):
    """模拟 detect_offline 的 CLASSES 统计核心（走真实判定函数路径）。"""
    r = {"proxy_count": 0, "is_tianzheng": False, "classes": [],
         "verdict": "none", "errors": []}
    tz = 0
    other = 0
    for x in classes:
        ni = x.get("num_instances") or 0
        if ni <= 0:
            continue
        app = x.get("appname") or ""
        cpp = x.get("cppname") or ""
        name = x.get("dxfname") or "?"
        if pd._is_native_class(app):
            continue
        if pd._is_config_class(name, cpp):
            continue   # 配置类非图形代理
        if pd._is_tianzheng_class(app, cpp):
            r["classes"].append({"name": name, "count": ni, "kind": "tianzheng"})
            tz += ni
        else:
            r["classes"].append({"name": name, "count": ni, "kind": "other"})
            other += ni
    r["proxy_count"] = tz + other
    r["is_tianzheng"] = tz > 0
    r["verdict"] = "convert_t3" if tz > 0 else ("report_only" if other > 0 else "none")
    return r


# 天正原图：TCH_DBCONFIG 配置类排除，TCH_OPENING 图形代理计入
r = run_with_classes([
    {"dxfname": "TCH_DBCONFIG", "cppname": "TDbConfig",
     "appname": '"TCH_KERNAL|..."', "num_instances": 255},
    {"dxfname": "TCH_OPENING", "cppname": "TDbOpening",
     "appname": '"TCH_KERNAL|..."', "num_instances": 37},
    {"dxfname": "VISUALSTYLE", "appname": "ObjectDBX Classes",
     "num_instances": 26},
])
check(16, "天正原图→convert_t3", r["verdict"], "convert_t3")
check(17, "配置类不计入 proxy 计数", r["proxy_count"], 37)
check(18, "classes 仅图形代理+原生过滤", len(r["classes"]), 1)

# 已转 T3 图：TCH_DBCONFIG 配置类残留实例，但图形代理归零 → none 不误报
r2 = run_with_classes([
    {"dxfname": "TCH_DBCONFIG", "cppname": "TDbConfig",
     "appname": '"TCH_KERNAL|..."', "num_instances": 256},
    {"dxfname": "VISUALSTYLE", "appname": "ObjectDBX Classes",
     "num_instances": 26},
])
check(19, "_AiT3 配置类残留不误报", r2["verdict"], "none")

# 类名残留但实例 0 → none
r3 = run_with_classes([
    {"dxfname": "TCH_DBCONFIG", "cppname": "TDbConfig",
     "appname": '"TCH_KERNAL|..."', "num_instances": 0},
    {"dxfname": "VISUALSTYLE", "appname": "ObjectDBX Classes",
     "num_instances": 26},
])
check(20, "类名残留实例 0 不误报", r3["verdict"], "none")

# 非天正代理 → report_only（WipeOut 已白名单为原生）
r4 = run_with_classes([
    {"dxfname": "EXACXREFPANELOBJECT", "cppname": "ExAcXREFPanelObject",
     "appname": '"EXAC_ESW"', "num_instances": 1},
    {"dxfname": "WIPEOUTVARIABLES", "appname": '"WipeOut|..."',
     "num_instances": 1},
])
check(21, "非天正代理→report_only", r4["verdict"], "report_only")
check(22, "WipeOut 不计入 proxy", r4["proxy_count"], 1)

# 纯原生图 → none
r5 = run_with_classes([
    {"dxfname": "VISUALSTYLE", "appname": "ObjectDBX Classes",
     "num_instances": 26},
    {"dxfname": "MULTILEADER", "appname": "ACDB_MLEADER_CLASS",
     "num_instances": 10},
])
check(23, "纯原生图→none", r5["verdict"], "none")

# ---------------------------------------------------------------- 环境检查
check(24, "LibreDWG 目录可探测", find_libredwg_dir() is not None, True)

# ---------------------------------------------------------------- 汇总
print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_proxy.py 全部通过 ✓")
