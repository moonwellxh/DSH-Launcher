# -*- coding: utf-8 -*-
"""
orchestrator.py — CAD 扫描之眼总调度（决策树实现）

依据：《最终设计 rev2》§5 决策树 + 任务书 T11。

流程：
  输入 DWG
   ├─ 文件健康检查（存在/可读/非空）→ 损坏降级链
   ├─ 代理实体检测（离线轨默认；CAD 运行时叠加在线轨）
   │    ├─ 天正代理 → 转 T3（有效 _AiT3 直读；否则需 CAD 转/引导注册）
   │    ├─ 非天正代理 → 不转，输出 proxy_report 警告
   │    └─ 无代理 → 直接提取
   ├─ XREF：默认输出 xrefs[] 清单；--xref 递归（深度≤3、防循环、Overlay 跳过）
   ├─ 提取（读取对象三元判断：有效 _AiT3 → 读 _AiT3；否则读源文件）
   │    ├─ CAD 运行 → A 路 extract.py（COM，弹窗防护+看门狗）
   │    ├─ 离线 → B 路 scan_dwg_structured（LibreDWG+ezdxf）
   │    └─ C 路 scan_dwg_text（双通道二进制，天正文字兜底）
   └─ 归并整合（merge_normalize）→ 统一 JSON → 投影（--summary/--filter/--bbox/--handle）

用法：
    python orchestrator.py <dwg路径> [选项]
    python orchestrator.py "文档名关键词" [选项]   # 连 CAD 定位磁盘路径

选项：
    --full            A 路全量（含标注/表格）
    --xref            递归解析参照（默认只报告清单）
    --out <目录>      输出目录（默认先试图纸同目录）
    --summary         投影：图层×类型计数矩阵+图幅+抽样
    --filter <正则>   投影：内容筛选（可叠加 --layers/--bbox）
    --layers <列表>   投影：图层白名单（逗号分隔）
    --bbox x1,y1,x2,y2 投影：空间范围
    --handle <id>     投影：按句柄取单条
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proxy_detect import detect_offline, detect_online, format_report  # noqa: E402
from merge_normalize import merge_records                            # noqa: E402
from query import summary, filter_texts, get_by_handle               # noqa: E402

AIT3_SUFFIX = "_AiT3.dwg"
META_SUFFIX = "_AiT3.meta.json"
XREF_MAX_DEPTH = 3


# ---------------------------------------------------------------------------
# 基础检查
# ---------------------------------------------------------------------------

def check_file(dwg_path):
    """文件健康检查。返回 (ok, error)。"""
    p = Path(dwg_path)
    if not p.exists():
        return False, f"文件不存在: {p}"
    if not p.is_file():
        return False, f"不是文件: {p}"
    try:
        if p.stat().st_size == 0:
            return False, f"文件为空（0 字节）: {p}"
    except OSError as e:
        return False, f"无法读取: {e}"
    return True, None


def cad_running():
    """AutoCAD 是否在运行（GetActiveObject 探测）。"""
    try:
        import comtypes.client
        comtypes.client.GetActiveObject("AutoCAD.Application", dynamic=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# _AiT3 增量判定（rev2 §4.4 三重核对）
# ---------------------------------------------------------------------------

def quick_hash(path, limit=1024 * 1024):
    """文件前 1MB 快哈希（SHA-256）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()


def t3_paths(dwg_path):
    """返回 (ait3_path, meta_path)。"""
    p = Path(dwg_path)
    return (p.with_name(p.stem + AIT3_SUFFIX),
            p.with_name(p.stem + META_SUFFIX))


def t3_valid(dwg_path):
    """三重判定：mtime + size + 快哈希全一致才算有效。

    返回 (valid, reason)：
      valid=True  → 直接读现有 _AiT3
      valid=False → 需重转（源文件有变化 / .tmp 残留 / 无 meta / 无文件）
    """
    p = Path(dwg_path)
    ait3, meta = t3_paths(p)
    if not ait3.exists():
        return False, "无 _AiT3 文件"
    if Path(str(ait3) + ".tmp").exists():
        return False, "发现 .tmp 残留（上次转换未完成）"
    if not meta.exists():
        return False, "无 sidecar 元数据"
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "sidecar 解析失败"
    try:
        st = p.stat()
        src_mtime = int(st.st_mtime)
        src_size = st.st_size
    except OSError as e:
        return False, f"源文件不可读: {e}"
    if m.get("src_mtime") != src_mtime:
        return False, "源 mtime 变化"
    if m.get("src_size") != src_size:
        return False, "源 size 变化"
    if m.get("src_quick_hash") != quick_hash(p):
        return False, "源快哈希变化"
    return True, "ok"


def write_meta(dwg_path, converter_version="TZ3-1.0"):
    """写 sidecar 元数据。"""
    p = Path(dwg_path)
    _, meta = t3_paths(p)
    st = p.stat()
    meta.write_text(json.dumps({
        "src_path": str(p),
        "src_mtime": int(st.st_mtime),
        "src_size": st.st_size,
        "src_quick_hash": quick_hash(p),
        "converter_version": converter_version,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# XREF 递归解析（rev2 §4.5 ③）
# ---------------------------------------------------------------------------

def resolve_xref_path(xref_path, main_dwg):
    """路径解析链：绝对 → 相对主图目录 → 主图同目录。返回 Path 或 None。"""
    if not xref_path:
        return None
    p = Path(xref_path)
    if p.is_absolute() and p.exists():
        return p
    main_dir = Path(main_dwg).parent
    cands = [main_dir / p, p]
    for c in cands:
        if c.exists():
            return c.resolve()
    return None


def collect_xref_tree(main_dwg, max_depth=XREF_MAX_DEPTH):
    """递归收集参照（Attach 才递归，Overlay 跳过，路径集合防循环）。

    返回 [{name, path, status, ...}]（不含子图内容，内容由调用方按需提取）。
    """
    visited = {str(Path(main_dwg).resolve())}
    out = []

    def walk(dwg, depth, source_file):
        if depth > max_depth or str(Path(dwg).resolve()) in visited:
            return
        visited.add(str(Path(dwg).resolve()))
        # 用 B 路拿 xrefs 清单（离线、快）
        try:
            import scan_dwg_structured as B
            from scan_dwg_structured import pick_output_dir
            import tempfile
            work = pick_output_dir(Path(tempfile.gettempdir()))
            dxf_path = B.dwg_to_dxf(dwg, work)
            import ezdxf
            try:
                doc, _, _ = B._read_fixed_dxf(dxf_path, work)
                xrefs = B._extract_xrefs(doc)
            except Exception:
                return
        except Exception:
            return
        for x in xrefs:
            resolved = resolve_xref_path(x.get("path"), dwg)
            status = "loaded" if resolved else "unresolved"
            rec = {**x, "source_file": source_file,
                   "resolved_path": str(resolved) if resolved else None,
                   "status": status}
            out.append(rec)
            if x.get("type") == "attach" and resolved:
                walk(resolved, depth + 1,
                     f"xref:{x.get('name')}")
    walk(main_dwg, 1, Path(main_dwg).name)
    return out


# ---------------------------------------------------------------------------
# 提取（A/B/C 路调度 + 归并）
# ---------------------------------------------------------------------------

def extract_merged(dwg_path, full=False, out_dir=None, allow_com=True):
    """对单个 DWG 执行多路提取并归并。返回 payload。"""
    p = Path(dwg_path)
    errors = []
    records = []
    dims = []
    attrs = []
    tables = []
    xrefs = []
    proxy_report = None

    use_com = allow_com and cad_running()

    # A 路：COM（CAD 运行时优先，最全结构化）
    if use_com:
        try:
            import comtypes.client
            import extract as A
            app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                                  dynamic=True)
            docs = app.Documents
            target = None
            for i in range(docs.Count):
                d = docs.Item(i)
                if str(d.Name) == p.name or str(d.FullName) == str(p):
                    target = d
                    break
            if target is None:
                # 文件未打开：无法 COM 提取（按设计不自行打开）
                errors.append("目标图纸未在 AutoCAD 中打开，A 路跳过"
                              "（请打开后重试或使用离线模式）")
            else:
                payload_a = A.extract_document(target, full=full,
                                               out_dir=out_dir)
                records.extend(payload_a["texts"])
                attrs.extend(payload_a["attrs"])
                dims.extend(payload_a["dims"])
                tables.extend(payload_a["tables"])
                xrefs = payload_a["xrefs"]
                proxy_report = payload_a["proxy_report"]
                errors.extend(payload_a["errors"])
        except Exception as e:
            errors.append(f"A 路（COM）失败: {type(e).__name__}: {e}")

    # B 路：LibreDWG + ezdxf 离线结构化
    try:
        import scan_dwg_structured as B
        payload_b, _ = B.scan_file(p, out_dir)
        records.extend(payload_b["texts"])
        attrs.extend(payload_b["attrs"])
        dims.extend(payload_b["dims"])
        tables.extend(payload_b["tables"])
        if not xrefs:
            xrefs = payload_b["xrefs"]
        errors.extend(payload_b["errors"])
    except Exception as e:
        errors.append(f"B 路（LibreDWG）失败: {type(e).__name__}: {e}")

    # C 路：双通道二进制扫描（天正文字兜底，编号+中文）
    try:
        import scan_dwg_text as C
        numbers, ctexts, channels = C.extract(str(p))
        for t in ctexts:
            records.append({"content": t, "type": "扫描", "layer": None,
                            "x": None, "y": None, "source": "C"})
        if numbers:
            attrs.append({"tag": "门窗编号", "value": " ".join(numbers),
                          "source": "C"})
        if not proxy_report:
            proxy_report = {"verdict": "unknown",
                            "classes": [], "errors": []}
    except Exception as e:
        errors.append(f"C 路（二进制扫描）失败: {type(e).__name__}: {e}")

    merged = merge_records(records)

    payload = {
        "dwg": p.name,
        "path": str(p),
        "mode": "full" if full else "texts",
        "filter_criteria": "type in [TEXT,MTEXT,ATTRIB,INSERT,DIMENSION,"
                           "ACAD_TABLE,MULTILEADER] and content non-empty",
        "texts": merged,
        "attrs": attrs,
        "dims": dims,
        "tables": tables,
        "xrefs": xrefs,
        "proxy_report": proxy_report or {"verdict": "unknown", "classes": []},
        "errors": errors,
    }
    return payload


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def run(dwg_path, full=False, xref_recursive=False, out_dir=None,
        auto_t3=True):
    """完整决策树。返回 (payload, out_json_path)。

    auto_t3=True 时，检测到天正代理且无有效 _AiT3 会自动转 T3
    （连接/启动 AutoCAD → 打开图 → 发 TZ3 → 轮询产物），无需手动操作。
    """
    t0 = time.time()
    p = Path(dwg_path)

    # 1. 健康检查
    ok, err = check_file(p)
    if not ok:
        raise ValueError(f"文件健康检查失败: {err}")

    # 2. 代理实体检测（离线轨默认）
    proxy = detect_offline(p)
    print(format_report(proxy), flush=True)

    # 3. 转 T3 决策（仅天正代理）
    read_target = p
    t3_note = None
    if proxy.get("verdict") == "convert_t3":
        valid, reason = t3_valid(p)
        if valid:
            ait3, _ = t3_paths(p)
            read_target = ait3
            print(f"[增量判定] 现有 _AiT3 有效（{reason}），直接读取: "
                  f"{read_target.name}", flush=True)
        elif auto_t3:
            # 自动转 T3（连接/启动 CAD → 打开 → TZ3 → 轮询）
            print(f"[自动转 T3] 需重转（{reason}），自动执行...", flush=True)
            try:
                import tz3_convert
                ok_t3, msg = tz3_convert.convert(p, timeout=600)
                if ok_t3 and t3_valid(p)[0]:
                    read_target = t3_paths(p)[0]
                    print(f"[自动转 T3] {msg}", flush=True)
                else:
                    t3_note = (f"自动转 T3 未成功: {msg}。可手动在 CAD 命令行"
                               f"输 TZ3 后重跑")
                    print(f"[提示] {t3_note}", flush=True)
            except Exception as e:
                t3_note = (f"自动转 T3 异常: {type(e).__name__}: {e}。"
                           f"可手动在 CAD 输 TZ3")
                print(f"[提示] {t3_note}", flush=True)
        else:
            print(f"[增量判定] 需重转 T3（{reason}），已禁用自动转，"
                  f"请手动在 CAD 输 TZ3", flush=True)
            t3_note = f"需重转 T3（{reason}）"
        # 即便未转成功，仍继续提取源文件（B/C 路兜底），不阻塞
    elif proxy.get("verdict") == "report_only":
        print("[代理报告] 非天正代理实体：不转 T3，相关文字可能缺失",
              flush=True)

    # 4. XREF
    if xref_recursive:
        xref_tree = collect_xref_tree(p)
        print(f"[XREF] 递归解析 {len(xref_tree)} 个参照", flush=True)
    else:
        xref_tree = None
        print("[XREF] 默认仅报告清单（--xref 递归解析参照内容）", flush=True)

    # 5. 多路提取 + 归并
    payload = extract_merged(read_target, full=full, out_dir=out_dir)
    payload["elapsed_sec"] = round(time.time() - t0, 1)
    if t3_note:
        payload["t3_note"] = t3_note
    payload["proxy_report"] = proxy
    if xref_tree:
        payload["xref_tree"] = xref_tree

    # 6. 落盘
    from scan_dwg_structured import pick_output_dir
    out = pick_output_dir(out_dir or p.parent) / f"{p.stem}_扫描之眼.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload, out


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)

    # 崩溃兜底自检：发现上次崩溃残留的系统变量快照时告警并提示恢复命令
    try:
        import cad_guard
        cad_guard.self_check_and_warn()
    except Exception:
        pass  # 自检失败不阻断主流程

    # 解析参数
    full = "--full" in argv
    xref_recursive = "--xref" in argv
    auto_t3 = "--no-auto-t3" not in argv   # 默认自动转 T3
    summary_flag = "--summary" in argv
    handle_id = None
    if "--handle" in argv:
        handle_id = argv[argv.index("--handle") + 1]
    filter_pat = None
    if "--filter" in argv:
        filter_pat = argv[argv.index("--filter") + 1]
    layers = None
    if "--layers" in argv:
        layers = [s.strip() for s in
                  argv[argv.index("--layers") + 1].split(",") if s.strip()]
    bbox = None
    if "--bbox" in argv:
        bbox = tuple(float(v) for v in
                     argv[argv.index("--bbox") + 1].split(","))
    out_dir = None
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]

    # 修复模式（2026-08-18 新增）
    repair_mode = "--repair" in argv
    repair_t3 = "--repair-t3" in argv
    repair_extract = "--repair-extract" in argv
    repair_rebuild = "--rebuild" in argv  # 直接 XREF 重建（跳过原地修复）

    target = None
    for a in argv:
        if not a.startswith("--"):
            target = a
            break
    if target is None:
        print("[错误] 请提供 DWG 路径或文档名关键词")
        sys.exit(1)

    # 修复模式：先修复，再按需转 T3/提取
    if repair_mode or repair_t3 or repair_extract or repair_rebuild:
        import dwg_repair
        print(f"[修复模式] 开始修复 {target} ...", flush=True)
        ok, fix_file, report = dwg_repair.repair(target, out_dir=out_dir,
                                                 rebuild=repair_rebuild)
        if not ok:
            err = report.get("error")
            if not err:
                # 顶层无 error 时，从步骤记录中找出第一个失败原因
                for s in report.get("steps", []):
                    if s.get("error"):
                        err = f"{s.get('step')}: {s.get('error')}"
                        break
            print(f"[修复失败] {err or '未知原因（无错误详情）'}", flush=True)
            for s in report.get("steps", []):
                status = "✓" if s.get("ok") else "✗"
                detail = f" -- {s.get('error')}" if s.get("error") else ""
                print(f"  [{status}] {s.get('step')}{detail}", flush=True)
            sys.exit(1)
        print(f"[修复成功] {fix_file}", flush=True)
        for s in report.get("steps", []):
            status = "✓" if s.get("ok") else "✗"
            print(f"  [{status}] {s.get('step')}", flush=True)

        if repair_t3:
            # 修复 + 转 T3
            target = str(fix_file)
            print(f"[继续] 转 T3 {target} ...", flush=True)
        elif repair_extract:
            # 修复 + 提取
            target = str(fix_file)
            print(f"[继续] 提取 {target} ...", flush=True)
        else:
            # 仅修复
            print(f"[完成] 修复文件: {fix_file}", flush=True)
            sys.exit(0)

    # 若目标不是磁盘文件（关键词），连 CAD 定位
    if not Path(target).exists():
        # 路径形态启发式：含盘符/路径分隔符或 .dwg 后缀的输入视为路径，
        # 不存在时明确报错（而非误当关键词）
        looks_like_path = (
            (":" in target and len(target) > 2)
            or "\\" in target or "/" in target
            or target.lower().endswith(".dwg"))
        if looks_like_path:
            print(f"[错误] 文件不存在: {target}")
            sys.exit(1)
        if not cad_running():
            print("[未连接] AutoCAD 未运行，无法按关键词定位。"
                  "请提供完整 DWG 路径或先打开 AutoCAD。")
            sys.exit(2)
        import comtypes.client
        app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                              dynamic=True)
        docs = app.Documents
        for i in range(docs.Count):
            d = docs.Item(i)
            if target in str(d.Name):
                target = str(d.FullName)
                print(f"[定位] {d.Name} → {target}", flush=True)
                break
        else:
            print(f"[未找到] 文档名不含「{target}」")
            sys.exit(1)

    payload, out = run(target, full=full, xref_recursive=xref_recursive,
                       out_dir=out_dir, auto_t3=auto_t3)

    print(f"\n[归并结果] 文字 {len(payload['texts'])} 条 / 属性 "
          f"{len(payload['attrs'])} 条 / 标注 {len(payload['dims'])} 条 / "
          f"表格 {len(payload['tables'])} 个 / XREF {len(payload['xrefs'])} 个 "
          f"/ 耗时 {payload.get('elapsed_sec')}s", flush=True)
    if payload["errors"]:
        print(f"[错误与降级] {len(payload['errors'])} 条：")
        for e in payload["errors"][:5]:
            print(f"    - {e}", flush=True)
    print(f"[输出JSON] {out}", flush=True)

    # 投影接口
    if summary_flag:
        print("\n[SUMMARY]")
        print(json.dumps(summary(payload), ensure_ascii=False,
                         separators=(",", ":")), flush=True)
    if handle_id:
        rec = get_by_handle(payload, handle_id)
        print(f"\n[HANDLE {handle_id}]")
        print(json.dumps(rec, ensure_ascii=False, indent=1), flush=True)
    if filter_pat or layers or bbox:
        sub = filter_texts(payload, filter_pat, layers, bbox)
        print(f"\n[FILTER] 命中 {len(sub)} 条")
        print(json.dumps(sub[:200], ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
