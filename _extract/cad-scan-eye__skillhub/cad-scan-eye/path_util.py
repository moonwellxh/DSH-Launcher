"""路径工具：SMB 盘符 → UNC 转换 + 可写目录探测。

背景（2026-08-18 实测）：SMB 映射盘（如 X:）在部分运行环境（尤其 agent 沙箱）
对盘符路径只读（写报 PermissionError），但其 UNC 形式（\\\\server\\share\\...）可正常
读写。本模块在「输出目录探测」时插入 UNC 候选，避免本可写却误降级到临时目录。

设计红线（§8.3）：输出目录动态探测、禁止硬编码用户目录；任何降级须标注实际路径。
"""
import tempfile
from pathlib import Path

_DRIVE_RE = __import__("re").compile(r"^([A-Za-z]):[\\/]")


def _network_drive_map():
    """读 HKCU\\Network\\* 的 RemotePath，返回 {盘符大写: UNC 路径}；无 winreg 返回 {}。"""
    result = {}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Network") as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if len(sub) != 1 or not sub.isalpha():
                    continue
                try:
                    sk = winreg.OpenKey(k, sub)
                    rp = winreg.QueryValueEx(sk, "RemotePath")[0]
                except OSError:
                    continue
                if isinstance(rp, str) and rp.startswith("\\\\"):
                    result[sub.upper()] = rp
    except Exception:
        pass
    return result


_NET_MAP_CACHE = None


def _net_map():
    global _NET_MAP_CACHE
    if _NET_MAP_CACHE is None:
        _NET_MAP_CACHE = _network_drive_map()
    return _NET_MAP_CACHE


def reset_cache():
    """清空盘符→UNC 缓存（供测试注入 mock 映射后重读）。"""
    global _NET_MAP_CACHE
    _NET_MAP_CACHE = None


def to_unc(path):
    """把盘符路径转 UNC；非盘符路径或查不到映射时返回 None。

    例：to_unc('X:/MyIOTO4/a.dwg') -> '//192.18.20.69/Moosync/MyIOTO4/a.dwg'
    输出统一正斜杠（Windows API 接受 //server/share 形式，等价 \\\\server\\share）。
    """
    s = str(path)
    m = _DRIVE_RE.match(s)
    if not m:
        return None
    drive = m.group(1).upper()
    remote = _net_map().get(drive)
    if not remote:
        return None
    rest = s[2:]                       # 去掉 "X:"：'\\a\\b' 或 '/a/b'
    rest = rest.replace("\\", "/")     # 统一正斜杠
    return remote.replace("\\", "/") + rest


def _is_writable(d):
    """探测目录可写性：mkdir + 写探测文件（探测文件删除失败不影响判定）。"""
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / "._wtest"
        probe.write_text("", encoding="utf-8")
        try:
            probe.unlink()
        except Exception:
            pass
        return True
    except Exception:
        return False


def ensure_writable_dir(preferred=None):
    """探测可写目录：preferred → preferred 的 UNC 形式 → 系统临时目录。

    返回 (dir: Path, mode: str)，mode ∈ {"direct", "unc", "temp"}，
    供调用方在结果 JSON/日志中标注实际落盘路径与降级原因（红线：降级不静默）。
    """
    if preferred:
        p = Path(preferred)
        if _is_writable(p):
            return p, "direct"
        unc = to_unc(preferred)
        if unc and _is_writable(Path(unc)):
            return Path(unc), "unc"
    return Path(tempfile.gettempdir()), "temp"
