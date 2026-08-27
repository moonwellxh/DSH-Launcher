# -*- coding: utf-8 -*-
"""
proxy_detect.py — 代理实体双轨检测（纯标准库，零依赖）

依据：《最终设计 rev2》§4.1 + 任务书 T2。

双轨：
  离线轨（默认）  LibreDWG `dwgread -O JSON` → CLASSES 段按 num_instances
                 「数实例」判代理实体（类名残留但实例为 0 不报——实测
                 原图与 _t3 都含 TDb 类名，只有实例数才是正确判据）；
  在线轨（可选）  AutoCAD COM 枚举 ObjectName="AcDbProxyEntity"，
                 读 OriginalClassName / ApplicationDescription。

泛化代理报告：检测不限于天正——浩辰/中望/Civil3D/Revit 等代理同样输出
  classes 清单并警告「相关文字可能缺失」。

输出结构：
  {
    "proxy_count": 256,          # 代理实体实例总数
    "is_tianzheng": true,        # 是否含天正代理实例
    "classes": [{"name": "TCH_DBCONFIG", "app": "TCH_KERNAL", "count": 255}, ...],
    "verdict": "convert_t3"      # convert_t3 | report_only | none
  }

用法：
    from proxy_detect import detect_offline, detect_online
    r = detect_offline("D:/xx.dwg")            # 离线（无需 CAD）
    r = detect_online(acad_doc)                # 在线（CAD 已打开时）
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# 天正来源标志（appname / cppname 关键字）
TIANZHENG_MARKS = ("TCH_KERNAL", "TANGENT", "TARCH", "TSSD", "TCH_", "TCH")
TIANZHENG_CPP = "TDb"
# AutoCAD 原生类（不算代理；WipeOut 为 Autodesk 官方区域覆盖，转 T3 不消除）
NATIVE_APPS = ("ObjectDBX Classes", "ACDB_", "AcDb", "WipeOut")

_LIBREDWG_CANDIDATES = []


def find_libredwg_dir():
    """定位 LibreDWG 目录（动态探测，不硬编码用户目录）。

    顺序：LIBREDWG_DIR 环境变量 → ~/.workbuddy/bin/libredwg → PATH 中的 dwgread。
    """
    if _LIBREDWG_CANDIDATES:
        return _LIBREDWG_CANDIDATES[0]
    cands = []
    env = os.environ.get("LIBREDWG_DIR")
    if env and (Path(env) / "dwgread.exe").exists():
        cands.append(Path(env))
    home_cand = Path.home() / ".workbuddy" / "bin" / "libredwg"
    if (home_cand / "dwgread.exe").exists():
        cands.append(home_cand)
    _LIBREDWG_CANDIDATES.extend(cands)
    return cands[0] if cands else None


def _is_tianzheng_class(appname, cppname):
    app = (appname or "").upper()
    cpp = (cppname or "")
    if any(m in app for m in TIANZHENG_MARKS):
        return True
    return cpp.startswith(TIANZHENG_CPP)


def _is_native_class(appname):
    app = (appname or "")
    return any(m in app for m in NATIVE_APPS)


def _is_config_class(name, cppname):
    """天正配置类（非图形代理实体，转 T3 后仍残留，不作 convert_t3 判据）。

    实测：天正图转 T3 后 TCH_DBCONFIG（TDbConfig）配置类仍保留 256 个实例，
    若把它计入「天正代理」会导致已转好的 _AiT3 图被误判 convert_t3、陷入
    反复转 T3 的死循环。故单独排除，只统计真正的图形代理（TCH_WALL/
    TCH_OPENING/TCH_AXIS_LABEL 等）。
    """
    n = (name or "").upper()
    c = (cppname or "").upper()
    return n == "TCH_DBCONFIG" or c == "TDBCONFIG"


def detect_offline(dwg_path):
    """离线轨：LibreDWG dwgread 解析 CLASSES 段，按实例数判定代理实体。

    返回 dict（见模块 docstring）。解析失败时返回 verdict="unknown" 并带 error。
    """
    base = {"proxy_count": 0, "is_tianzheng": False, "classes": [],
            "verdict": "none", "errors": []}
    d = find_libredwg_dir()
    if d is None:
        base["errors"].append("LibreDWG 未找到（探测 ~/.workbuddy/bin/libredwg 失败）")
        base["verdict"] = "unknown"
        return base

    exe = d / "dwgread.exe"
    try:
        r = subprocess.run(
            [str(exe), "-O", "JSON", str(dwg_path)],
            capture_output=True, timeout=180, encoding="utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError) as e:
        base["errors"].append(f"dwgread 执行失败: {e}")
        base["verdict"] = "unknown"
        return base
    if r.returncode != 0 or not r.stdout.strip():
        base["errors"].append(f"dwgread 返回码 {r.returncode}: "
                              f"{(r.stderr or '')[:200]}")
        base["verdict"] = "unknown"
        return base

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        # dwgread JSON 对部分图损坏（实测 203KB 天正图 char 损坏）→ 降级
        base["errors"].append(f"dwgread JSON 损坏，降级 dwg2dxf 解析: {e}")
        fb = _detect_offline_fallback(dwg_path)
        fb["errors"] = base["errors"] + fb.get("errors", [])
        return fb

    classes = data.get("CLASSES", [])
    tz_count = 0
    other_count = 0
    for x in classes:
        ni = x.get("num_instances") or 0
        if ni <= 0:
            continue  # 类定义残留（实例 0）不报——rev2 §4.1 判据
        app = x.get("appname") or ""
        cpp = x.get("cppname") or ""
        name = x.get("dxfname") or cpp or "?"
        if _is_native_class(app):
            continue  # AutoCAD 原生类
        if _is_config_class(name, cpp):
            continue  # 天正配置类（非图形代理，不作判据）
        if _is_tianzheng_class(app, cpp):
            base["classes"].append({"name": name, "app": app.strip('"'),
                                    "count": ni, "kind": "tianzheng"})
            tz_count += ni
        else:
            base["classes"].append({"name": name, "app": app.strip('"'),
                                    "count": ni, "kind": "other"})
            other_count += ni

    base["proxy_count"] = tz_count + other_count
    base["is_tianzheng"] = tz_count > 0
    if tz_count > 0:
        base["verdict"] = "convert_t3"
    elif other_count > 0:
        base["verdict"] = "report_only"
    else:
        base["verdict"] = "none"
    return base


def _detect_offline_fallback(dwg_path):
    """降级轨：dwgread JSON 损坏时，用 dwg2dxf → ezdxf 统计 CLASS instance_count。

    与 dwgread JSON 的 num_instances 等价（ezdxf CLASS 实体 instance_count）。
    返回结构同 detect_offline。
    """
    import tempfile
    base = {"proxy_count": 0, "is_tianzheng": False, "classes": [],
            "verdict": "none", "errors": []}
    d = find_libredwg_dir()
    if d is None:
        base["errors"].append("LibreDWG 未找到")
        base["verdict"] = "unknown"
        return base
    exe = d / "dwg2dxf.exe"
    if not exe.exists():
        base["errors"].append("dwg2dxf.exe 未找到")
        base["verdict"] = "unknown"
        return base
    work = Path(tempfile.gettempdir())
    dxf_path = work / (Path(dwg_path).stem + "_probe.dxf")
    try:
        r = subprocess.run([str(exe), "-o", str(dxf_path), str(dwg_path)],
                           capture_output=True, timeout=600,
                           encoding="utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError) as e:
        base["errors"].append(f"dwg2dxf 失败: {e}")
        base["verdict"] = "unknown"
        return base
    if not dxf_path.exists() or dxf_path.stat().st_size == 0:
        base["errors"].append("dwg2dxf 无输出")
        base["verdict"] = "unknown"
        return base
    try:
        from scan_dwg_structured import _read_fixed_dxf  # 延迟 import 防循环
        doc, _, _ = _read_fixed_dxf(dxf_path, work)
    except Exception as e:
        base["errors"].append(f"ezdxf 读取失败: {type(e).__name__}: {str(e)[:120]}")
        base["verdict"] = "unknown"
        return base

    tz_count = 0
    other_count = 0
    try:
        for e in doc.classes:
            ic = e.dxf.get("instance_count", 0) or 0
            if ic <= 0:
                continue
            cpp = e.dxf.get("cpp_class_name", "") or ""
            app = e.dxf.get("app_name", "") or ""
            name = e.dxf.get("name", "") or ""
            if _is_native_class(app):
                continue
            if _is_config_class(name, cpp):
                continue
            if _is_tianzheng_class(app, cpp):
                base["classes"].append({"name": name, "app": app,
                                        "count": ic, "kind": "tianzheng"})
                tz_count += ic
            else:
                base["classes"].append({"name": name, "app": app,
                                        "count": ic, "kind": "other"})
                other_count += ic
    except Exception as e:
        base["errors"].append(f"CLASS 统计失败: {e}")
        base["verdict"] = "unknown"
        return base

    base["proxy_count"] = tz_count + other_count
    base["is_tianzheng"] = tz_count > 0
    if tz_count > 0:
        base["verdict"] = "convert_t3"
    elif other_count > 0:
        base["verdict"] = "report_only"
    else:
        base["verdict"] = "none"
    return base


def detect_online(doc, max_scan=100000):
    """在线轨：COM 枚举代理实体（AutoCAD 已打开时优先，零猜测）。

    doc: pyautocad/comtypes Document 对象。
    max_scan: 遍历实体上限（防止超大图长时间遍历；超限标注 truncated）。
    返回 dict（同 detect_offline 结构）。
    """
    from comtypes import COMError  # comtypes 仅在线轨需要
    base = {"proxy_count": 0, "is_tianzheng": False, "classes": [],
            "verdict": "none", "errors": [], "truncated": False}

    def _retry(fn, retries=60, delay=0.3):
        for _ in range(retries):
            try:
                return fn()
            except COMError as e:
                if e.args and e.args[0] == -2147418111:  # RPC_E_CALL_REJECTED
                    import time
                    time.sleep(delay)
                    continue
                raise
        raise TimeoutError("COM 调用持续被拒绝")

    try:
        ms = _retry(lambda: doc.ModelSpace)
        total = _retry(lambda: ms.Count)
        scan = min(total, max_scan)
        counts = {}
        for i in range(scan):
            obj = _retry(lambda i=i: ms.Item(i))
            try:
                oname = obj.ObjectName
            except Exception:
                continue
            if oname == "AcDbProxyEntity":
                try:
                    cls = str(obj.OriginalClassName or "")
                except Exception:
                    cls = ""
                try:
                    app = str(obj.ApplicationDescription or "")
                except Exception:
                    app = ""
                key = (cls, app)
                counts[key] = counts.get(key, 0) + 1
        tz = 0
        other = 0
        for (cls, app), n in counts.items():
            kind = "tianzheng" if _is_tianzheng_class(app, cls) else "other"
            base["classes"].append(
                {"name": cls or "(unknown)", "app": app, "count": n, "kind": kind})
            if kind == "tianzheng":
                tz += n
            else:
                other += n
        base["proxy_count"] = tz + other
        base["is_tianzheng"] = tz > 0
        base["truncated"] = scan < total
        if tz > 0:
            base["verdict"] = "convert_t3"
        elif other > 0:
            base["verdict"] = "report_only"
        else:
            base["verdict"] = "none"
    except Exception as e:
        base["errors"].append(f"COM 枚举失败: {e}")
        base["verdict"] = "unknown"
    return base


def format_report(r):
    """把检测结果格式化为面向 LLM 的短文本（供 SKILL 工作流直接引用）。"""
    v = r.get("verdict")
    if v == "convert_t3":
        tz = [c for c in r.get("classes", []) if c.get("kind") == "tianzheng"]
        names = ", ".join(f"{c['name']}×{c['count']}" for c in tz[:5])
        more = f" 等 {len(tz)} 类" if len(tz) > 5 else ""
        return (f"[代理检测] 天正代理实体 {r['proxy_count']} 个（{names}{more}）"
                f" → 建议转 T3 后读取（verdict=convert_t3）")
    if v == "report_only":
        names = ", ".join(f"{c['name']}×{c['count']}"
                          for c in r.get("classes", [])[:5])
        return (f"[代理检测] 含 {r['proxy_count']} 个非天正代理实体（{names}）"
                f" → 不转 T3，相关文字可能缺失（verdict=report_only）")
    if v == "unknown":
        return f"[代理检测] 无法判定：{'；'.join(r.get('errors', [])[:2])}"
    return "[代理检测] 无代理实体（verdict=none）"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python proxy_detect.py <dwg路径>")
        sys.exit(1)
    res = detect_offline(sys.argv[1])
    print(format_report(res))
    print(json.dumps(res, ensure_ascii=False, indent=1))
