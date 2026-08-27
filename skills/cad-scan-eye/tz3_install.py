# -*- coding: utf-8 -*-
"""
tz3_install.py — TZ3 插件静默注册 / 注销（winreg，纯标准库）

依据：《最终设计 rev2》§4.3 + §8.11 + 任务书 T10。

安全边界（§8.11 / 优化意见 P1-2.6）：
  1. 注册前校验 dll SHA-256 与 skill 清单 TZ3Converter.sha256 一致，
     不匹配拒绝注册（防供应链替换）；
  2. 按 AutoCAD 大版本选 dll：R25+（AutoCAD 2025+）→ net8 产物，
     R24-（≤2024）→ fx48 产物；枚举 HKCU 全部版本键全写；
  3. TRUSTEDPATHS 只追加不覆盖，改动前后值记日志（JSON），可完整回滚；
  4. 注销 = 删 Applications 注册项 + 回滚 TRUSTEDPATHS + 保留日志。

用法：
    python tz3_install.py --register     # 静默注册（免打开 CAD）
    python tz3_install.py --unregister   # 注销并回滚
    python tz3_install.py --status       # 查看注册状态

注意：
  - 注册表 demand-load 项需重启 AutoCAD 才生效（启动时读）；
    当次会话立即使用请 APPLOAD tz3_register.lsp → REGDLL，或
    NETLOAD 对应 dll 后输 TZ3。
  - TRUSTEDPATHS 由 AutoCAD 退出时从内存写回注册表：追加操作请在
    AutoCAD 关闭时执行，否则会被覆盖；CAD 内等效命令 SETENV。
"""
import hashlib
import json
import os
import sys
import time
import winreg
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).resolve().parent
REG_BASE = r"Software\Autodesk\AutoCAD"
APP_KEY = "TZ3Converter"
LOG_FILE = SKILL_DIR / "tz3_install.log.json"

DLL_FX48 = SKILL_DIR / "TZ3Converter.fx48.dll"
DLL_NET8 = SKILL_DIR / "TZ3Converter.net8.dll"
MANIFEST = SKILL_DIR / "TZ3Converter.sha256"


# ---------------------------------------------------------------------------
# 哈希清单
# ---------------------------------------------------------------------------

def load_manifest():
    """解析 TZ3Converter.sha256 → {文件名: sha256hex}。"""
    m = {}
    if not MANIFEST.exists():
        return m
    for line in MANIFEST.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            m[parts[-1]] = parts[0].lower()
    return m


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dll(dll_path, manifest):
    """校验 dll 哈希。返回 (ok, reason)。"""
    name = dll_path.name
    if not dll_path.exists():
        return False, f"文件不存在: {dll_path}"
    if name not in manifest:
        return False, f"清单中无 {name} 条目（请先运行 compile.bat 生成清单）"
    actual = sha256_of(dll_path)
    if actual != manifest[name]:
        return False, (f"SHA-256 不匹配: {dll_path.name}\n"
                       f"  清单: {manifest[name]}\n"
                       f"  实际: {actual}\n"
                       f"  拒绝注册（防止供应链替换）")
    return True, "ok"


# ---------------------------------------------------------------------------
# 注册表枚举
# ---------------------------------------------------------------------------

def enum_acad_versions():
    """枚举 HKCU\\Software\\Autodesk\\AutoCAD 下所有版本键。

    返回 [{"ver": "R23.1", "products": ["ACAD-2001:804", ...]}]
    """
    versions = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_BASE) as base:
            i = 0
            while True:
                try:
                    ver = winreg.EnumKey(base, i)
                except OSError:
                    break
                if ver.startswith("R"):
                    products = []
                    try:
                        with winreg.OpenKey(base, ver) as vk:
                            j = 0
                            while True:
                                try:
                                    p = winreg.EnumKey(vk, j)
                                    # 只保留真产品键（如 ACAD-2001:804），
                                    # 跳过 Update 等维护键
                                    if "ACAD-" in p.upper():
                                        products.append(p)
                                except OSError:
                                    break
                                j += 1
                    except OSError:
                        pass
                    versions.append({"ver": ver, "products": products})
                i += 1
    except OSError:
        pass
    return versions


def major_of(ver):
    """R23.1 → 23；R25.0 → 25。"""
    try:
        return int(ver[1:].split(".")[0])
    except (ValueError, IndexError):
        return 0


def dll_for_major(major):
    """AutoCAD 大版本 → dll 路径（2025 起 R25 → net8；之前 → fx48）。"""
    return DLL_NET8 if major >= 25 else DLL_FX48


# ---------------------------------------------------------------------------
# Applications 注册项
# ---------------------------------------------------------------------------

def write_app_key(ver, product, loader_path):
    """写 Applications\\TZ3Converter 4 值（DESCRIPTION/LOADER/LOADCTRLS/MANAGED）。"""
    key_path = f"{REG_BASE}\\{ver}\\{product}\\Applications\\{APP_KEY}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "DESCRIPTION", 0, winreg.REG_SZ,
                              "TZ3Converter - Tianzheng T3 silent converter")
            winreg.SetValueEx(k, "LOADER", 0, winreg.REG_SZ, str(loader_path))
            winreg.SetValueEx(k, "LOADCTRLS", 0, winreg.REG_DWORD, 2)
            winreg.SetValueEx(k, "MANAGED", 0, winreg.REG_DWORD, 1)
        return True, key_path
    except OSError as e:
        return False, f"{key_path}: {e}"


def delete_app_key(ver, product):
    """删除 Applications\\TZ3Converter 键。"""
    key_path = f"{REG_BASE}\\{ver}\\{product}\\Applications"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteKey(k, APP_KEY)
        return True, f"{key_path}\\{APP_KEY}"
    except FileNotFoundError:
        return True, f"{key_path}\\{APP_KEY} (不存在，跳过)"
    except OSError as e:
        return False, f"{key_path}\\{APP_KEY}: {e}"


# ---------------------------------------------------------------------------
# TRUSTEDPATHS（追加不覆盖 + 回滚）
# ---------------------------------------------------------------------------

def _trusted_variables_path(ver, product):
    return (f"{REG_BASE}\\{ver}\\{product}\\Profiles\\"
            f"<<Unnamed Profile>>\\Variables")


def read_trustedpaths(ver, product):
    path = _trusted_variables_path(ver, product)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            v, _ = winreg.QueryValueEx(k, "TRUSTEDPATHS")
            return str(v)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def write_trustedpaths(ver, product, value):
    path = _trusted_variables_path(ver, product)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
            winreg.SetValueEx(k, "TRUSTEDPATHS", 0, winreg.REG_SZ, value)
        return True
    except OSError:
        return False


def append_trusted(ver, product, add_path, log_entry):
    """TRUSTEDPATHS 追加（不覆盖既有值）；记录改动前后值。"""
    before = read_trustedpaths(ver, product)
    entry = {"action": "trustedpaths", "ver": ver, "product": product,
             "path": add_path, "before": before, "after": None, "status": ""}
    if before is None:
        # 无既有值：直接设（等于新建）
        ok = write_trustedpaths(ver, product, add_path)
        entry["after"] = add_path
        entry["status"] = "created" if ok else "write_failed"
    elif add_path in before.split(";"):
        entry["after"] = before
        entry["status"] = "already_present"
    else:
        new_val = before.rstrip(";") + ";" + add_path
        ok = write_trustedpaths(ver, product, new_val)
        entry["after"] = new_val if ok else None
        entry["status"] = "appended" if ok else "write_failed"
    log_entry.append(entry)
    return entry["status"] in ("created", "appended", "already_present")


def rollback_trusted(ver, product, log_entry):
    """按日志回滚 TRUSTEDPATHS 到改动前值。"""
    before = log_entry.get("before")
    cur = read_trustedpaths(ver, product)
    if before is None:
        # 改动前无值：尝试删除该值
        path = _trusted_variables_path(ver, product)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "TRUSTEDPATHS")
            return True, "deleted"
        except FileNotFoundError:
            return True, "absent"
        except OSError as e:
            return False, str(e)
    if cur != before:
        ok = write_trustedpaths(ver, product, before)
        return ok, "restored" if ok else "restore_failed"
    return True, "unchanged"


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def load_log():
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"entries": []}


def save_log(log):
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                        encoding="utf-8")


def append_log(action, detail):
    log = load_log()
    log["entries"].append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": action, "detail": detail,
    })
    save_log(log)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def register():
    """静默注册。返回 (ok, report_lines)。"""
    report = []
    versions = enum_acad_versions()
    if not versions:
        return False, ["未找到任何已安装的 AutoCAD 版本键（HKCU\\"
                       "Software\\Autodesk\\AutoCAD\\R2x.x 为空）"]

    manifest = load_manifest()
    log = load_log()
    trusted_entries = []
    registered = []

    # 按版本选 dll 并校验哈希
    dll_choices = {}
    for v in versions:
        dll = dll_for_major(major_of(v["ver"]))
        dll_choices[dll.name] = dll
    for dll in dll_choices.values():
        ok, reason = verify_dll(dll, manifest)
        if not ok:
            return False, [reason]
        report.append(f"[哈希校验通过] {dll.name}")

    for v in versions:
        major = major_of(v["ver"])
        dll = dll_for_major(major)
        for product in v["products"]:
            ok, info = write_app_key(v["ver"], product, dll)
            if ok:
                registered.append(info)
            else:
                report.append(f"[注册失败] {info}")
                return False, report
            # TRUSTEDPATHS 追加（记录日志）
            append_trusted(v["ver"], product, str(SKILL_DIR),
                           trusted_entries)

    log["trusted_changes"] = trusted_entries
    save_log(log)
    report.append(f"[注册成功] {len(registered)} 个产品键: ")
    for r in registered:
        report.append(f"    {r}")
    report.append(f"[TRUSTEDPATHS] 已追加 {SKILL_DIR}"
                  f"（改动前值记录在 tz3_install.log.json，可回滚）")
    report.append("")
    report.append("[提示] 注册表 demand-load 需重启 AutoCAD 才生效；")
    report.append("       当次会话立即使用：APPLOAD tz3_register.lsp → REGDLL，")
    report.append("       或 NETLOAD 对应 dll 后输 TZ3。")
    append_log("register", {"versions": [v["ver"] for v in versions],
                            "keys": registered})
    return True, report


def unregister():
    """注销并回滚 TRUSTEDPATHS。返回 (ok, report_lines)。"""
    report = []
    versions = enum_acad_versions()
    log = load_log()
    trusted_changes = log.get("trusted_changes", [])
    rollback_ok = True

    for v in versions:
        for product in v["products"]:
            ok, info = delete_app_key(v["ver"], product)
            if not ok:
                report.append(f"[注销失败] {info}")
                rollback_ok = False
            else:
                report.append(f"[已注销] {info}")
            # 回滚 TRUSTEDPATHS（仅回滚本次 skill 追加的）
            for te in trusted_changes:
                if te.get("ver") == v["ver"] and \
                        te.get("product") == product:
                    ok2, st = rollback_trusted(v["ver"], product, te)
                    report.append(f"[TRUSTEDPATHS 回滚] {v['ver']}\\"
                                  f"{product}: {st}")
                    if not ok2:
                        rollback_ok = False

    if not versions:
        report.append("[无版本键] 无可注销内容（注册表为空）")
    report.append(f"[完成] 注销{'成功' if rollback_ok else '部分失败（见上）'}")
    append_log("unregister", {"versions": [v["ver"] for v in versions]})
    return rollback_ok, report


def status():
    """查看注册状态。"""
    lines = []
    versions = enum_acad_versions()
    if not versions:
        lines.append("未找到已安装 AutoCAD 版本键。")
        return lines
    manifest = load_manifest()
    lines.append(f"[清单] {MANIFEST.name} 条目: "
                 f"{list(manifest.keys()) or '(空)'}")
    for v in versions:
        for product in v["products"]:
            key_path = f"{REG_BASE}\\{v['ver']}\\{product}\\Applications\\{APP_KEY}"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                    loader, _ = winreg.QueryValueEx(k, "LOADER")
                lines.append(f"[已注册] {v['ver']}\\{product} → {loader}")
            except FileNotFoundError:
                lines.append(f"[未注册] {v['ver']}\\{product}")
            except OSError as e:
                lines.append(f"[异常] {key_path}: {e}")
            tp = read_trustedpaths(v["ver"], product)
            if tp:
                has = str(SKILL_DIR) in tp
                lines.append(f"    TRUSTEDPATHS {'含' if has else '不含'} "
                             f"skill 目录（现值长度 {len(tp)}）")
    return lines


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "--register":
        ok, report = register()
        for r in report:
            print(r)
        sys.exit(0 if ok else 1)
    elif cmd == "--unregister":
        ok, report = unregister()
        for r in report:
            print(r)
        sys.exit(0 if ok else 1)
    elif cmd == "--status":
        for line in status():
            print(line)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
