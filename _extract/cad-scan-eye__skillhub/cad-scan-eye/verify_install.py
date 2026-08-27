# -*- coding: utf-8 -*-
"""cad-scan-eye 四层完整性自检（skill-install-ops 规范）
L1 导入验证 / L2 探测验证 / L3 自带测试 / L4 真实冒烟(离线 B/C 路)

用法:  python <本文件>    （用技能环境的 python 运行）
"""
import subprocess, sys, pathlib, json, tempfile

SKILL = pathlib.Path(__file__).resolve().parent
PY = pathlib.Path(r"C:\Users\雍远\.workbuddy\binaries\python\versions\3.13.12\python.exe")
results = []

def report(layer, name, ok, detail=""):
    results.append((layer, name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] L{layer} {name}  {detail}")

# ---------- L1 导入验证 ----------
try:
    import comtypes, ezdxf, pyautocad, numpy  # noqa
    import win32com.client  # noqa
    report(1, "依赖包导入", True,
           f"comtypes {getattr(comtypes,'__version__','?')}, ezdxf {ezdxf.__version__}, numpy {numpy.__version__}")
except Exception as e:
    report(1, "依赖包导入", False, str(e))

# ---------- L2 探测验证 ----------
sys.path.insert(0, str(SKILL))
try:
    from proxy_detect import find_libredwg_dir
    d = find_libredwg_dir()
    ok = d is not None and (pathlib.Path(d) / "dwgread.exe").exists()
    report(2, "LibreDWG 探测", bool(ok), str(d) if d else "None")
except Exception as e:
    report(2, "LibreDWG 探测", False, str(e))

if d:
    try:
        r = subprocess.run([str(pathlib.Path(d) / "dwgread.exe"), "--version"],
                           capture_output=True, text=True, errors="replace", timeout=30)
        report(2, "dwgread 自检", r.returncode == 0, (r.stdout or r.stderr).strip()[:40])
    except Exception as e:
        report(2, "dwgread 自检", False, str(e))

required = ["SKILL.md", "orchestrator.py", "extract.py", "dwg_repair.py",
            "proxy_detect.py", "tz3_convert.py", "TZ3Converter.fx48.dll",
            "references/troubleshooting.md", "tests/run_regression.py"]
missing = [f for f in required if not (SKILL / f).exists()]
report(2, "技能目录结构", not missing, f"缺失={missing or '无'}")

# ---------- L3 自带测试 ----------
tests = ["test_clean.py", "test_merge.py", "test_proxy.py", "test_query.py",
         "test_structured.py", "test_xref.py", "test_path_util.py", "test_guard.py"]
env = dict(__import__('os').environ)
env["PYTHONIOENCODING"] = "utf-8"
for t in tests:
    try:
        r = subprocess.run([str(PY), str(SKILL / "tests" / t)], capture_output=True,
                           text=True, errors="replace", cwd=str(SKILL / "tests"), env=env, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        passed = "PASS" in out or "通过" in out or "OK" in out
        report(3, f"测试 {t}", r.returncode == 0 or passed, f"rc={r.returncode}")
    except Exception as e:
        report(3, f"测试 {t}", False, str(e))

# ---------- L4 真实冒烟（离线 B/C 路，端到端产出验证） ----------
tmp = pathlib.Path(tempfile.mkdtemp(prefix="cse_smoke_"))
smoke_ok, detail = False, ""
try:
    import ezdxf
    dxf = tmp / "smoke.dxf"
    doc = ezdxf.new("R2000")
    msp = doc.modelspace()
    msp.add_text("HELLO_CAD_SCAN_EYE", dxfattribs={"height": 350.0}).set_placement((1000, 2000))
    doc.saveas(dxf)
    d = find_libredwg_dir()
    dwg = tmp / "smoke.dwg"
    r = subprocess.run([str(pathlib.Path(d) / "dxf2dwg.exe"), "-o", str(dwg), str(dxf)],
                       capture_output=True, text=True, errors="replace", timeout=60)
    if not dwg.exists():
        detail = f"dxf2dwg 失败: {(r.stdout or r.stderr)[:120]}"
    else:
        r2 = subprocess.run([str(PY), str(SKILL / "orchestrator.py"), str(dwg), "--no-auto-t3"],
                            capture_output=True, text=True, errors="replace", env=env, timeout=180)
        out2 = (r2.stdout or "") + (r2.stderr or "")
        traceback = "Traceback" in out2
        json_files = list(tmp.glob("*扫描之眼.json")) + list(tmp.glob("*.json"))
        if traceback:
            detail = f"orchestrator Traceback: {out2[:150]}"
        elif json_files:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            ok_keys = {"dwg", "texts", "errors", "proxy_report"} <= set(data.keys())
            smoke_ok = ok_keys
            detail = f"JSON 产出 OK: dwg={data.get('dwg')} texts={len(data.get('texts', []))} errors={len(data.get('errors', []))}"
        else:
            detail = f"未产出 JSON: {out2[:150]}"
except Exception as e:
    detail = str(e)
report(4, "真实冒烟(离线端到端)", smoke_ok, detail)

# ---------- 汇总 ----------
fails = [r for r in results if not r[1]]
print("\n========== 汇总 ==========")
print(f"总计 {len(results)} 项: PASS {len(results)-len(fails)} / FAIL {len(fails)}")
for r in fails:
    print(f"  FAIL: L{r[0]} {r[1]} -> {r[3]}")
sys.exit(1 if fails else 0)
