#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M12 orchestrator.py —— 全流程编排（双模式：<pdf> 真接 + --page-image 兼容）
==================================================================
职责（冻结 §6.12 / 升级详细设计 §3）：CLI、配置集中、断点续跑（页级落盘）、幂等、
`--no-egress` 短路 M4、分通道预算闸、启动环境门（FR-G3）、整管线降级弹选（R-05）。

双模式（D-4/D-5）：
  A) <pdf> 主路径：python orchestrator.py <pdf> --out <dir> [--no-egress] [--md] [--html] ...
     → M1 triage → 逐页路由（text→M3 textlayer；image/pseudo/unknown→scanned→M2+M4(+M5)）
     → pipeline.process_page_md 胶水 → assemble_v4 → v4.0 JSON + [M13 md/html]
  B) --page-image 兼容路径（MS-1 既有单页循环，保留供离线验收/既有测试）

降级弹选（R-05/详细 §3.3）：仅"整管线结构性不可跑"触发；TTY→A/B/C 弹选；
非 TTY→中止+退出码+留痕 work/degrade_choice.json（不产出、不静默降级 v3.0）。
FR-D7（无 key/--no-egress/预算/断网）属页/表级自动兜底，不经过弹选。

作用/输入/输出/复跑（四行 docstring）：
  作用：任意 PDF → v4.0 JSON（+可选 md/html），引擎降级显式化。
  输入：<pdf> --out <dir> [--no-egress --no-cache --md --html --budget-glm X --budget-review Y]
        （兼容 --page-image <png> --page N）
  输出：out/<stem>.v4.json + work/（triage/pages/registry/ledger/...）+ [md/html]
  复跑：python orchestrator.py <pdf> --out <dir>  （幂等，跳过已完成页）
"""
import argparse
import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vision_client import (VisionClient, VisionError, BudgetGate,
                           GLM_CHANNEL, SECOND_OPINION_CHANNEL,
                           TASK_FULL_PAGE)


# ---------------------------------------------------------------- 配置集中

def deep_merge(base, override):
    """递归深度合并：override 值优先。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _default_cfg_path(skill_base):
    return Path(skill_base) / "assets" / "v4" / "config.default.json"


def _user_cfg_path():
    return Path.home() / ".config" / "pdf-parse-v3" / "config.user.json"


def load_config(skill_base):
    """config.default.json + 用户级覆盖 config.user.json（deep-merge，用户优先）。"""
    base = json.loads(_default_cfg_path(skill_base).read_text(encoding="utf-8"))
    up = _user_cfg_path()
    if up.exists():
        try:
            ucfg = json.loads(up.read_text(encoding="utf-8"))
        except Exception:
            ucfg = None
        if ucfg:
            base = deep_merge(base, ucfg)
    return base


# ---------------------------------------------------------------- 渲染登记（M2 占位，兼容保留）

def build_render_reg(png_path, *, dpi=None, target_width=None, page_size=None):
    """从页图推导最小渲染登记（§3.2 要素）。M2 render.py 接入后此函数仅供 --page-image
    兼容路径使用（既有测试依赖）。pixel 优先取实际位图尺寸；dpi 派生。"""
    img_sha = hashlib.sha1(Path(png_path).read_bytes()).hexdigest()
    try:
        from PIL import Image
        with Image.open(png_path) as im:
            pixel = [im.width, im.height]
    except Exception:
        pixel = page_size or [0, 0]
    return {"dpi": dpi or 220, "pixel": pixel, "render_sha1": img_sha,
            "target_width": target_width, "downsampled_from": None,
            "render_sha1_full": img_sha}


# ---------------------------------------------------------------- 页标记（FR-D7 降级留痕）

def _marker(out_dir, page, kind, reason):
    """降级/不可读标记落盘，任务可观测（需求书 §2.2）。"""
    m = Path(out_dir) / "marks"
    m.mkdir(parents=True, exist_ok=True)
    (m / ("page_%04d.json" % page)).write_text(
        json.dumps({"page": page, "kind": kind, "reason": reason}, ensure_ascii=False),
        encoding="utf-8")


# ---------------------------------------------------------------- 结构性自检与降级弹选（R-05）

# 直接 import 名白名单（冻结 §6.12 MAJ-4 口径：按 import 清单，非发行名；beautifulsoup4→bs4）
_WHITELIST = ("pymupdf", "pypdf", "pdfplumber", "rapidocr_onnxruntime",
              "PIL", "numpy", "bs4", "requests")


def _structural_ok(skill_base, ignore_gpu_lib=False) -> bool:
    """结构性自检（FR-G3 启动门）：triage.py/render.py 存在；依赖白名单可 import；
       GPU 库负向探测（处理遗留 R-10/C-A1：默认存在即拒绝；--ignore-gpu-lib 显式放行仅警告）。
       True=可跑 v4。"""
    v4 = Path(skill_base) / "assets" / "v4"
    for name in ("triage.py", "render.py"):
        if not (v4 / name).exists():
            return False
    import importlib
    for mod in _WHITELIST:
        try:
            importlib.import_module(mod)
        except Exception:
            return False
    for bad in ("torch", "tensorflow"):
        try:
            importlib.import_module(bad)
        except Exception:
            continue
        if not ignore_gpu_lib:
            # GPU 库存在：默认拒绝启动（FR-G3 违规，冻结语义）
            return False
        _safe_print("WARN: 检测到 GPU 库 %s，--ignore-gpu-lib 放行（CPU 管线显式声明）" % bad, file=sys.stderr)
    return True


def keys_available(cfg) -> bool:
    """keys.json 存在且含 zhipu/dashscope/deepseek 任一。"""
    try:
        from vision_client import load_keys
        k = load_keys()
        return any(k.get(v) for v in ("zhipu", "dashscope", "deepseek"))
    except Exception:
        return False


_BUDGET_CHOICE_LOCK = threading.Lock()   # S-1：留痕是整文件读-改-写，并发必须互斥


def _write_budget_choice(out, rec):
    """#4 留痕：预算超限的处置记录（追加为 JSON 数组）。
    S-1 修复：加锁——并发下无锁 RMW 会丢记录（8 线程实测只剩 2/8 条）。"""
    f = Path(out) / "work" / "budget_choice.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    with _BUDGET_CHOICE_LOCK:
        prev = []
        if f.exists():
            try:
                prev = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(prev, list):
                    prev = [prev]
            except Exception:
                prev = []
        prev.append(rec)
        f.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")


_RUN_META_LOCK = threading.Lock()


def _write_run_meta(out, argv, t0, *, mode, concurrency):
    """L4（2026-09-27）：把本轮命令与墙钟落盘，使"加速/耗时"结论可自证（不只靠外部计时）。
    口径（建议-3）：`t0` 取自**页处理开始**时刻，`wall_s` **不含 triage 与进程启动**；一次取时。
    不覆盖（建议-4）：`work/run_meta.json` 留最新一轮，同时把同一记录**追加**到
    `work/run_meta.jsonl`，故同一 out 目录的多轮/多模式记录均可追溯。"""
    t1 = time.time()
    rec = {"mode": mode, "argv": list(argv), "concurrency": concurrency,
           "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
           "started_epoch": round(t0, 3), "ended_epoch": round(t1, 3),
           "wall_s": round(t1 - t0, 2), "scope": "page-processing（不含 triage/启动）"}
    d = Path(out) / "work"
    try:
        d.mkdir(parents=True, exist_ok=True)
        with _RUN_META_LOCK:
            (d / "run_meta.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
            with (d / "run_meta.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _stdin_isatty():
    """S-1（2026-09-27）：`sys.stdin` 可能为 None（pythonw/部分宿主）→ 旧实现直接抛
    AttributeError，且被 `_precall` 的 except 吞掉 ⇒ 静默降级。"""
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except Exception:
        return False


def _safe_print(*args, **kw):
    """S-1（2026-09-27）：提示串必须可编码。stdout 可能是 **cp936 管道**（如终端里
    `python orchestrator.py … --budget-glm X > run.log`），此时 `¥`(U+00A5) 会抛
    UnicodeEncodeError —— 旧实现被 `_precall` 的 except 吞掉 ⇒ 不弹问、不留痕、
    还把"拒绝"永久记忆。这里兜底降级输出（调用方另外已把 ¥ 换成「元」）。"""
    try:
        print(*args, **kw)
    except UnicodeEncodeError:
        try:
            # 建议-2：取**目标流**的编码（file=sys.stderr 时拿 sys.stdout 的编码会二次失败）
            tgt = kw.get("file") or sys.stdout
            enc = getattr(tgt, "encoding", None) or "ascii"
            print(*[str(a).encode(enc, "replace").decode(enc, "replace") for a in args], **kw)
        except Exception:
            try:
                sys.stderr.write("WARN: 提示输出编码降级失败\n")
            except Exception:
                pass


def _make_budget_confirm(cfg, out):
    """#4（2026-09-27）：超预算确认闸。
    config.budget.confirm_on_exceed=false → 返回 None（旧行为：直接按 FR-D7 降级）。
    交互环境：弹选「1 继续（超额放行）/ 2 停止该通道（降级）」；非交互：不弹窗，按 FR-D7 降级。
    两种情形都写 work/budget_choice.json 留痕。"""
    if not (cfg.get("budget", {}) or {}).get("confirm_on_exceed", True):
        return None

    def _confirm(*, channel, reason="channel_limit", spent=None, limit=None, peak=False,
                 peak_spent=None, peak_cap=None):
        rec = {"ts": time.time(), "trigger": "budget_exceeded", "channel": channel,
               "reason": reason, "spent_cny": spent, "limit_cny": limit, "peak": peak,
               "peak_spent_cny": peak_spent, "peak_cap_cny": peak_cap,
               "context": "tty" if _stdin_isatty() else "non-tty", "chosen": None}
        if not _stdin_isatty():
            rec["chosen"] = "degrade"
            _write_budget_choice(out, rec)      # S-1：先留痕再打印，打印失败也不丢留痕
            _safe_print("预算超限（非交互环境）：按 FR-D7 降级通道 %s，留痕 work/budget_choice.json"
                        % channel, file=sys.stderr)
            return False
        # S-1：提示串走 _safe_print，且不用 ¥（U+00A5 在 cp936 下不可编码）
        # L2：按**真实原因**提示（峰谷封顶 ≠ 通道预算超限）
        if reason == "peak_cap":
            _safe_print("峰谷封顶超限：通道 %s 高峰段已用 %s 元 / 封顶 %s 元"
                        % (channel, peak_spent, peak_cap))
        else:
            _safe_print("预算超限：通道 %s 已用 %s 元 / 上限 %s 元（peak=%s）"
                        % (channel, spent, limit, peak))
        _safe_print("  1. 继续（超额放行；本次运行该通道不再询问）")
        _safe_print("  2. 停止该通道（按 FR-D7 降级并诚实标记）")
        while True:
            try:
                ans = input("输入 1/2：").strip()
            except EOFError:
                rec["chosen"] = "degrade"
                _write_budget_choice(out, rec)
                return False
            except Exception as e:              # S-1：交互不可用＝未获答复 → 留痕 chosen=error
                rec["chosen"] = "error"
                rec["error"] = "%s: %s" % (type(e).__name__, e)
                _write_budget_choice(out, rec)
                _safe_print("WARN: 预算确认输入失败（%s），按 FR-D7 降级且不记忆"
                            % type(e).__name__, file=sys.stderr)
                raise
            if ans == "1":
                rec["chosen"] = "allow_exceed"
                _write_budget_choice(out, rec)
                return True
            if ans == "2":
                rec["chosen"] = "degrade"
                _write_budget_choice(out, rec)
                return False

    return _confirm


def _write_choice(out, rec):
    f = Path(out) / "work" / "degrade_choice.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def maybe_offer_degrade(reason, cfg, out, tty=True) -> int:
    """整管线结构性不可跑 → 弹选/中止。仅结构性触发；FR-D7 不经过此函数。
        签名对齐冻结设计 §3.3：cfg（配置）为第 2 形参（处理遗留 R-01/R-08）。
        返回：0 选 A（解决依赖重跑 v4）; 1 选 B（显式降级许可，上层凭退出码1+留痕走 v3 流程）;
             2 选 C 取消; 3 非 TTY 中止（不产出、不静默降级）。"""
    offered = ["A: 解决依赖后重跑 v4", "B: 显式降级 v3.0（告知产物差异）", "C: 取消"]
    rec = {"ts": time.time(), "trigger": "structural", "reason": reason,
           "offered": offered, "chosen": None,
           "context": "tty" if tty else "non-tty",
           "note": "整管线结构性不可跑，禁止无感降级 v3.0"}
    if not tty:
        rec["note"] += "；非交互：中止，不产出，不静默降级"
        _write_choice(out, rec)
        _safe_print("结构性不可跑（非交互环境）：中止，未产出 v3.0。请人工处理依赖后重跑。",
                    file=sys.stderr)
        return 3
    _safe_print("v4 管线结构性不可跑。请选择：")
    for i, opt in enumerate(offered, 1):
        _safe_print("  %d. %s" % (i, opt))
    while True:
        try:
            ans = input("输入 1/2/3：").strip()
        except EOFError:
            rec["chosen"] = None
            _write_choice(out, rec)
            return 3
        except Exception as e:
            # 轻微-1：交互不可用（stdin 为 None / 编码失败）→ 按非交互中止，不崩
            # 建议-5：留痕补 error 字段（与预算确认路径对称，便于诊断）
            rec["chosen"] = None
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            rec["note"] = rec.get("note", "") + "；交互不可用：按非交互中止"
            _write_choice(out, rec)
            return 3
        if ans == "1":
            rec["chosen"] = "A"
            _write_choice(out, rec)
            return 0
        if ans == "2":
            rec["chosen"] = "B"
            _write_choice(out, rec)
            _safe_print("已选择显式降级 v3.0。差异告知：v3.0 JSON 无网格表格重建（无 rowspan/colspan 网格）、"
                  "无图片索引块、无 lines[] 坐标层；与原 v3 管线产物一致。"
                  "v3 执行体不内联于 orchestrator（v3 为独立工具链，见 SKILL.md §2/§3）；"
                  "上层调用方收到退出码 1 + work/degrade_choice.json(chosen=B) 后，"
                  "方可按 SKILL.md v3 流程（pdf-inspect/pdf-extract/rapid_ocr → pdf2v3 → finalize_v3）"
                  "产出 v3.0 JSON。", file=sys.stderr)
            return 1
        if ans == "3":
            rec["chosen"] = "C"
            _write_choice(out, rec)
            return 2


# ---------------------------------------------------------------- 扫描页链（R-04/详细 §3.2）

def render_reg_for(rec, cfg, page_rect=None):
    """文字层页最小登记（无 PNG 也可坐标换算）。page_rect=[pdf_w, pdf_h]。"""
    dpi = float(cfg.get("render", {}).get("dpi_default", 220))
    w, h = (page_rect if page_rect else [595.0, 842.0])
    tw = int(round(w * dpi / 72.0))
    return {"page": rec["page"], "pdf_rect_pt": [round(w, 2), round(h, 2)],
            "target_width": tw, "dpi": round(dpi, 4),
            "pixel": [round(w * dpi / 72.0), round(h * dpi / 72.0)],
            "scale": [round(dpi / 72.0, 4), round(dpi / 72.0, 4)],
            "render_sha1": "textlayer-no-png", "downsampled_from": None}


def _ocr_lines_for(pno, work) -> list:
    """读 M5 ocr_pages 产物（单 JSON work/ocr/ocr_pages.json，WBS A2- 修正口径）
       → {page: lines}；无则 []。
       v1.3：加锁读（防读到并发写方的半文件）。**GLM 主路径已不再消费本产物**
       （C-2026-09-27：本地 OCR 为备份/兜底、不参与双源；见 _scan_page_glm），
       产品侧已无调用者（离线夹具走 `pipeline._load_ocr_lines`），保留供诊断与回归测试
       使用；写侧 `_scan_page_local` 仍产出该文件，用于 FR-D7 兜底留痕。"""
    f = Path(work) / "ocr" / "ocr_pages.json"
    with _OCR_STORE_LOCK:
        if not f.exists():
            return []
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    for p in d.get("pages", []):
        if int(p.get("page")) == pno:
            return p.get("lines", [])
    return []


def _scan_page_local(pdf, pno, cfg, work) -> dict:
    """FR-D7 本地兜底：本地 OCR 行级 + 诚实标记（无 GLM 网格重建，tables=[] + note 声明）。
    处理遗留 R-09/C-8：渲染/OCR 解耦——渲染 oversize 时先内部降档重渲（dpi_floor=96，复用 M2）；
    仍超限 → 诚实 part（reason=render_oversize，不落空文本冒充、不仅标记即过）；仅 OCR 层失败才记
    local_ocr_unavailable/local_ocr_failed。"""
    from render import render_page, append_registry, RenderError
    from ocr_channel import OcrUnavailable, _make_engine, ocr_page
    try:
        reg = render_page(pdf, pno, work / "pages", cfg, dpi_floor=96)
    except RenderError as e:
        kind = "oversize" if e.kind == "oversize" else "render_failed"
        _marker(work, pno, "degraded", "render_%s: %s" % (kind, e.detail))
        return {"page_number": pno, "text": "", "lines": [], "blocks": [],
                "tables": [], "images": [],
                "routing": [{"page": pno, "method": "local-ocr-fallback",
                             "note": "render_%s：先降档重渲（dpi_floor=96）仍超限/失败，扫描页无文本可 OCR（不落空文本冒充）" % kind}]}
    append_registry(work / "render" / "registry.jsonl", [reg])
    try:
        engine = _make_engine(cfg)
        ocr = ocr_page(str(work / "pages" / ("page_%04d.png" % pno)), engine, pno)
        lines = ocr.get("lines", [])
    except OcrUnavailable as e:
        _marker(work, pno, "degraded", "local_ocr_unavailable: %s" % e)
        return {"page_number": pno, "text": "", "lines": [], "blocks": [],
                "tables": [], "images": [],
                "routing": [{"page": pno, "method": "local-ocr-fallback",
                             "note": "FR-D7：视觉不可用本地兜底（OCR 通道不可用）"}]}
    except Exception as e:
        _marker(work, pno, "degraded", "local_ocr_failed: %s" % e)
        return {"page_number": pno, "text": "", "lines": [], "blocks": [],
                "tables": [], "images": [],
                "routing": [{"page": pno, "method": "local-ocr-fallback",
                             "note": "FR-D7：本地 OCR 失败：%s" % e}]}
    (work / "ocr").mkdir(parents=True, exist_ok=True)
    f = work / "ocr" / "ocr_pages.json"
    with _OCR_STORE_LOCK:              # B1 修复：整文件读-改-写必须互斥（否则并发丢页）
        prev = []
        if f.exists():
            try:
                prev = json.loads(f.read_text(encoding="utf-8")).get("pages", [])
            except Exception:
                prev = []
        # m-1 修复：落盘前按页号排序——并发到达锁的次序不定，不排序则字节不可复现
        prev = sorted([p for p in prev if int(p.get("page")) != pno] + [ocr],
                      key=lambda p: int(p.get("page")))
        f.write_text(json.dumps({"engine": "rapidocr_onnxruntime", "pages": prev},
                                ensure_ascii=False), encoding="utf-8")
    text = "\n".join(l.get("text", "") for l in lines)
    return {"page_number": pno, "text": text, "lines": lines, "blocks": [],
            "tables": [], "images": [],
            "routing": [{"page": pno, "method": "local-ocr-fallback",
                         "note": "FR-D7：视觉不可用本地兜底，tables 未重建"}]}


def _scan_page_glm(pdf, pno, cfg, client, work, doc_sha1) -> dict:
    """扫描页 GLM 路径（出域允许且有 key）：
       render → registry → glm_parse_page → pipeline.process_page_md（raw_resp=response payload 钉定）。
       client 由 run_pdf 一次性创建并传入（处理遗留 R-08/C-7：不再逐页构建 VisionClient）。
       v1.3（S1 修复）：不消费本地 OCR 行盒（ocr_lines=[], ocr_available=False）——本地 OCR
       为备份/兜底、不参与双源，且该产物无文档标识、跨文档复跑会串页。"""
    from render import render_page, append_registry
    import pipeline
    reg = render_page(pdf, pno, work / "pages", cfg)
    append_registry(work / "render" / "registry.jsonl", [reg])
    png = work / "pages" / ("page_%04d.png" % pno)
    res = client.glm_parse_page(str(png), page=pno, doc_sha1=doc_sha1, render_reg=reg,
                                task_type=TASK_FULL_PAGE)
    payload = (res.get("raw_response") or {}).get("response") or {}   # 严重-2/r3 钉定
    md = payload.get("md_results") or res.get("md") or ""
    # S1 修复（C-2026-09-27）：**不再消费本地 OCR 行盒**。本地 OCR 为备份/兜底、不参与双源；
    # 且 work/ocr/ocr_pages.json 只按页号索引、不含文档标识，跨文档或复跑会把别文档的行盒
    # 当作 ocr_available=True 喂给校验门（hint→第二意见出域）。
    return pipeline.process_page_md(pno, md, cfg,
                                    ocr_lines=[],
                                    ocr_available=False,
                                    m4=client,
                                    raw_resp=payload,
                                    png=str(png),
                                    doc_sha1=doc_sha1,
                                    render_reg=reg)


def _budget_limits(args):
    limits = {}
    if args.budget_glm is not None:
        limits[GLM_CHANNEL] = args.budget_glm
    if args.budget_review is not None:
        limits[SECOND_OPINION_CHANNEL] = args.budget_review
    return limits


# ---------------------------------------------------------------- 并发执行（v1.3，2026-09-27）

# 线程局部 PDF 句柄：PyMuPDF 的 Document 不是线程安全的，每个工作线程各持一份。
_TLS = threading.local()
# B1 修复（2026-09-27）：work/ocr/ocr_pages.json 是整文件读-改-写，并发下会丢页。
_OCR_STORE_LOCK = threading.Lock()
_OPEN_DOCS = []                      # 已打开句柄登记（收尾统一关闭，防 Windows 文件锁残留）
_OPEN_DOCS_LOCK = threading.Lock()


def _thread_doc(pdf_path):
    """取本线程的 PDF 句柄（懒打开）。PyMuPDF Document 不跨线程共享。"""
    doc = getattr(_TLS, "doc", None)
    if doc is None:
        import pymupdf as fitz
        doc = fitz.open(str(pdf_path))
        _TLS.doc = doc
        with _OPEN_DOCS_LOCK:
            _OPEN_DOCS.append(doc)
    return doc


def _close_open_docs():
    """关闭全部已打开句柄（线程池收拢后由主线程统一调用）。
    不关闭会残留文件句柄，在 Windows 上锁住输入 PDF（本测试 ⑦ 曾因此清理失败）。"""
    with _OPEN_DOCS_LOCK:
        for d in _OPEN_DOCS:
            try:
                d.close()
            except Exception:
                pass
        _OPEN_DOCS.clear()
    _TLS.doc = None                  # 调用线程自身的句柄引用一并清空（串行路径复用安全）


_CONCURRENCY_MAX = 32               # A3：并发度硬上限（越界钳制并告警）


def _resolve_concurrency(args, cfg) -> int:
    """页级调度并发度：--concurrency 优先，否则 config.egress.concurrency，默认 6；
    范围 [1, 32]（越界钳制并告警；1=串行）。
    作用域（#1，2026-09-27 更正）：`run_pdf` 与 `--page-image` 兼容模式的**页级调度**都受其管辖——
    出域调用与本地渲染据此并行；本地 RapidOCR 另由 `ocr_channel._ENGINE_LOCK` 串行，
    PDF 后端访问另由 `render.PDF_BACKEND_LOCK` 串行（#12）。"""
    v = getattr(args, "concurrency", None)
    if v is None:
        v = (cfg.get("egress", {}) or {}).get("concurrency", 6)
    try:
        n = int(v)
    except Exception:
        n = 6
    if n > _CONCURRENCY_MAX:            # A3 修复：越界不静默放行（上下界对称告警）
        _safe_print("WARN: 并发度 %d 超上限，钳到 %d" % (n, _CONCURRENCY_MAX), file=sys.stderr)
    elif n < 1:
        _safe_print("WARN: 并发度 %d 非法，钳到 1（串行）" % n, file=sys.stderr)
    return max(1, min(n, _CONCURRENCY_MAX))


def _process_one(rec, *, pdf_path, cfg, client, work, doc_sha1, no_egress):
    """单页处理（原 run_pdf 循环体，语义逐条保留）。返回 (page_no, part|None)。"""
    from textlayer import textlayer_page
    pno = rec["page"]
    v = rec["verdict"]
    part = None
    # 断点：已有 part 落盘则跳过
    partf = work / "pages" / ("page_%04d.part.json" % pno)
    if partf.exists():
        try:
            part = json.loads(partf.read_text(encoding="utf-8"))
            if part.get("degraded"):
                part = None
            else:
                return pno, part
        except Exception:
            part = None
    doc = _thread_doc(pdf_path)
    if v == "text":
        try:
            page = doc[pno - 1]
            reg = render_reg_for(rec, cfg, [page.rect.width, page.rect.height])
            part = textlayer_page(doc, pno, reg, cfg)          # M3
        except Exception as e:
            part = None
            _marker(work, pno, "degraded", "textlayer_failed: %s" % e)
        if part and part.get("routing") and part["routing"][0].get("rerouted"):
            v = "scanned"                                       # FR-A2 重路由
    if v in ("image", "pseudo", "unknown", "scanned"):
        if (not no_egress) and keys_available(cfg):
            try:
                part = _scan_page_glm(doc, pno, cfg, client, work, doc_sha1)
            except VisionError as e:
                print("[degrade] page %d -> %s" % (pno, e.kind), file=sys.stderr)
                _marker(work, pno, "degraded", "vision_%s" % e.kind)
                part = _scan_page_local(doc, pno, cfg, work)   # FR-D7
            except Exception as e:
                print("[degrade] page %d -> %s" % (pno, e), file=sys.stderr)
                _marker(work, pno, "degraded", "glm_failed: %s" % e)
                part = _scan_page_local(doc, pno, cfg, work)
        else:
            part = _scan_page_local(doc, pno, cfg, work)       # --no-egress/无 key
    partf.parent.mkdir(parents=True, exist_ok=True)
    if part:
        partf.write_text(json.dumps(part, ensure_ascii=False), encoding="utf-8")
    else:
        partf.write_text(json.dumps({"page": pno, "degraded": True}), encoding="utf-8")
    return pno, part


def _run_pages(tri_pages, *, pdf_path, cfg, client, work, doc_sha1, no_egress, concurrency):
    """有界并发执行各页 → pages_parts（**按页号升序**，与串行顺序逐页一致）。
    concurrency<=1 退化为原串行路径（行为与 v1.2 相同）。"""
    n = max(1, int(concurrency or 1))
    got = {}
    try:
        if n == 1:
            for rec in tri_pages:
                pno, part = _process_one(rec, pdf_path=pdf_path, cfg=cfg, client=client,
                                         work=work, doc_sha1=doc_sha1, no_egress=no_egress)
                if part is not None:
                    got[pno] = part
        else:
            with ThreadPoolExecutor(max_workers=n) as ex:
                futs = [ex.submit(_process_one, rec, pdf_path=pdf_path, cfg=cfg, client=client,
                                  work=work, doc_sha1=doc_sha1, no_egress=no_egress)
                        for rec in tri_pages]
                try:
                    for fu in futs:
                        pno, part = fu.result()
                        if part is not None:
                            got[pno] = part
                except BaseException:
                    for fu in futs:
                        fu.cancel()
                    raise
    finally:
        _close_open_docs()
    return [got[k] for k in sorted(got)]


# ---------------------------------------------------------------- <pdf> 主路径

_PAGE_TOKEN_RE = re.compile(r"(\d+)(?:-(\d+))?")


def _parse_pages(spec, page_count):
    """→ (list[int]|None, err|None)。None/空串=(None,None) 全量（唯一合法空集形态，处理遗留 R-05/S9-A2）。
    逐 token 截交 [1,page_count] 后再入集（防 '1-999999999' 类合法 range 膨胀，建议-1）；
    任一 token 非法/区间逆序 → 报错（不取子集，'1,abc' 整体无效）；截交后为空 → 报错（整 spec 交集空）。"""
    s = spec.strip() if spec is not None else ""
    if not s:
        return None, None
    out = set()
    for part in s.split(","):
        p = part.strip()
        m = _PAGE_TOKEN_RE.fullmatch(p) if p else None
        if not m:
            return None, "无效页码 token：%r（支持 '1-10'/'1,3,5'）" % p
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if b < a:
            return None, "页码区间逆序：%r" % p
        lo, hi = max(a, 1), min(b, page_count)
        if lo <= hi:
            out.update(range(lo, hi + 1))
    inter = sorted(out)
    if not inter:
        return None, "页码范围 '%s' 与 1..%d 交集为空" % (s, page_count)
    return inter, None


def run_pdf(pdf_path, out, cfg, args) -> int:
    """真接 <pdf>：M1 triage → 逐页路由 → 下游 → v4.0 JSON（+md/html）。
    args.pages 提供页码范围时仅处理该子集（钳制到实际页数；交集空/非法 → 报错非 0 无产物，处理遗留 R-05）。"""
    from triage import triage, TriageError
    import structurer
    from textlayer import textlayer_page
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    # VisionClient 循环前一次性创建（处理遗留 R-08/C-7：扫描页不再逐页重建；ledger 共享）
    client = VisionClient(cfg, egress_allow=(not args.no_egress),
                          no_cache=args.no_cache,
                          budget=BudgetGate(cfg, _budget_limits(args)),
                          budget_confirm=_make_budget_confirm(cfg, out),      # #4
                          ledger_path=str(work / "ledger" / "token.jsonl"))
    try:
        tri = triage(pdf_path, cfg)
    except TriageError as e:
        print("TriageError(%s): %s" % (e.kind, e.detail), file=sys.stderr)
        return 3
    want_pages, perr = _parse_pages(getattr(args, "pages", None), tri["page_count"])
    if perr is not None:
        _safe_print("--pages 错误：" + perr, file=sys.stderr)
        return 2
    (work / "triage.json").write_text(json.dumps(tri, ensure_ascii=False), encoding="utf-8")
    if want_pages is not None:
        want_set = set(want_pages)
        tri["pages"] = [r for r in tri["pages"] if r["page"] in want_set]
    t0 = time.time()                                                       # L4
    doc_sha1 = hashlib.sha1(Path(pdf_path).read_bytes()).hexdigest()
    conc = _resolve_concurrency(args, cfg)
    _safe_print("[concurrency] %d（1=串行；--concurrency 覆盖 config.egress.concurrency）" % conc)
    pages_parts = _run_pages(tri["pages"], pdf_path=str(pdf_path), cfg=cfg, client=client,
                             work=work, doc_sha1=doc_sha1, no_egress=bool(args.no_egress),
                             concurrency=conc)
    v4 = structurer.assemble_v4(
        pages_parts=pages_parts,
        standard_info={"name": Path(pdf_path).stem},
        transform_registry_ref=str(work / "render" / "registry.jsonl"))
    stem = Path(pdf_path).stem
    out_json = out / ("%s.v4.json" % stem)
    out_json.write_text(json.dumps(v4, ensure_ascii=False), encoding="utf-8")
    if args.md:
        from serialize_md import to_md
        (out / ("%s.md" % stem)).write_text(to_md(v4), encoding="utf-8")
    if args.html:
        from serialize_html import to_html
        (out / ("%s.html" % stem)).write_text(to_html(v4), encoding="utf-8")
    _write_run_meta(out, sys.argv, t0, mode="run_pdf", concurrency=conc)   # L4
    print("OK pages=%d -> %s" % (len(pages_parts), out_json))
    return 0


# ---------------------------------------------------------------- MS-1 兼容循环（保留）

def _page_from_name(stem):
    import re
    m = re.search(r"(\d+)$", stem)
    return int(m.group(1)) if m else None


_MS1_PAGE_LOCKS = {}                    # m-1：按页号串行，保住"已存在即跳过"的串行语义
_MS1_PAGE_LOCKS_GUARD = threading.Lock()


def _ms1_page_lock(n):
    with _MS1_PAGE_LOCKS_GUARD:
        lk = _MS1_PAGE_LOCKS.get(n)
        if lk is None:
            lk = threading.Lock()
            _MS1_PAGE_LOCKS[n] = lk
        return lk


def _ms1_page_work(img, ctx):
    """兼容模式单页（原循环体逐字保留）。返回 (page_no, status)。
    m-1 修复：整体按页号加锁——并发分支下同页号多图曾各自通过"文件不存在"检查→重复出域（重复计费）；
    加锁后第二张会看到前一张已落盘并 [skip]，与串行版语义一致。"""
    args, client, out = ctx["args"], ctx["client"], ctx["out"]
    png = Path(img)
    n = args.page if args.page is not None else _page_from_name(png.stem)
    if n is None:
        raise SystemExit("无法从 %s 推导页号，请用 --page N" % png.name)
    with _ms1_page_lock(n):
        return _ms1_page_work_locked(img, n, ctx)


def _ms1_page_work_locked(img, n, ctx):
    args, client, out = ctx["args"], ctx["client"], ctx["out"]
    png = Path(img)
    rawo = out / "glm" / ("page_%04d.json" % n)
    if rawo.exists():
        _safe_print("[skip] page %d 已存在：%s" % (n, rawo))
        return n, "skip"
    render_reg = json.loads(args.render_reg_json) if args.render_reg_json else build_render_reg(png)
    doc_sha1 = args.doc_sha1 or render_reg["render_sha1"]
    try:
        res = client.glm_parse_page(str(png), page=n, doc_sha1=doc_sha1, render_reg=render_reg)
    except VisionError as e:
        kind = "unreadable" if e.kind in ("output_length_exceeded",) else "degraded"
        _marker(out / "work", n, kind, "%s: %s" % (e.kind, e.detail))   # 统一落 out/work/marks（处理遗留 R-11/C-A3）
        print("[degrade] page %d -> %s" % (n, e.kind))
        return n, "degrade"
    (out / "glm").mkdir(parents=True, exist_ok=True)
    rawo.write_text(json.dumps(res["raw_response"], ensure_ascii=False), encoding="utf-8")
    print("[ok] page %d cache_hit=%s cost=%s md_chars=%s" % (
        n, res.get("cache_hit"), res.get("cost_cny"), len(res.get("md") or "")))
    return n, "ok"


def _ms1_page_loop(args, cfg, out) -> int:
    """兼容模式：--page-image 循环（MS-1 既有单页语义整体保留）。
    #1（2026-09-27）：该模式**同样是出域路径**（逐图调 glm_parse_page），故与主路径一样
    受 --concurrency 管辖；concurrency<=1 时退化为原串行行为。"""
    limits = _budget_limits(args)
    client = VisionClient(cfg, egress_allow=(not args.no_egress),
                          no_cache=args.no_cache,
                          budget=BudgetGate(cfg, limits),
                          budget_confirm=_make_budget_confirm(cfg, out),      # #4
                          # L1（2026-09-27）：与主路径统一落 work/ledger（旧为 out/ledger）
                          ledger_path=str(out / "work" / "ledger" / "token.jsonl"))
    conc = _resolve_concurrency(args, cfg)
    t0 = time.time()                                                           # L4
    _safe_print("[concurrency] %d（兼容模式 --page-image；1=串行）" % conc)
    ctx = {"args": args, "client": client, "out": out}
    try:
        if conc <= 1:
            for img in args.page_image:
                _ms1_page_work(img, ctx)
        else:
            with ThreadPoolExecutor(max_workers=conc) as ex:
                futs = [ex.submit(_ms1_page_work, img, ctx) for img in args.page_image]
                try:
                    for fu in futs:
                        fu.result()      # 异常与串行版同样向上抛
                except BaseException:
                    for fu in futs:      # m-1：与主路径 _run_pages 对齐，取消未启动任务
                        fu.cancel()
                    raise
    finally:
        with _MS1_PAGE_LOCKS_GUARD:            # L3：页锁表收尾清空（只增不减 → 有界）
            _MS1_PAGE_LOCKS.clear()
    _write_run_meta(out, sys.argv, t0, mode="ms1_page_loop", concurrency=conc)  # L4
    print("DONE.")
    return 0


# ---------------------------------------------------------------- argparse

def build_argparse():
    ap = argparse.ArgumentParser(description="pdf-parse-v3 v4 管线编排（<pdf> 双模式）")
    ap.add_argument("pdf", nargs="?", help="PDF 文件（主路径；与 --page-image 互斥）")
    ap.add_argument("--out", required=True, help="工作区/输出目录")
    ap.add_argument("--no-egress", action="store_true", help="全局短路三厂商出域（FR-D7）")
    ap.add_argument("--no-cache", action="store_true", help="禁用指纹缓存")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="页级调度并发度（默认 config.egress.concurrency=6；范围 1-32，"
                         "越界钳制并告警；1=串行）。作用于出域调用与本地渲染；"
                         "本地 RapidOCR 与 PDF 后端各自另有串行锁。")
    ap.add_argument("--md", action="store_true", help="额外产出分级 MD（M13）")
    ap.add_argument("--html", action="store_true", help="额外产出自包含 HTML（M13）")
    ap.add_argument("--budget-glm", type=float, default=None, help="GLM 主通道预算（CNY）")
    ap.add_argument("--budget-review", type=float, default=None, help="复核通道预算（CNY）")
    ap.add_argument("--pages", default=None, help="页码范围，如 '1-10' 或 '1,3,5'（默认全部；用于大文件前 N 页验收）")
    ap.add_argument("--ignore-gpu-lib", action="store_true",
                    help="检测到 torch/tensorflow 时显式放行启动（CPU 管线声明；默认仍拒绝，处理遗留 R-10/C-A1）")
    # 兼容保留（MS-1，不进 SKILL.md 示例）：
    ap.add_argument("--page-image", action="append", default=[], help="已渲染页图 PNG（兼容模式）")
    ap.add_argument("--page", type=int, default=None, help="页号（配合 --page-image）")
    ap.add_argument("--render-reg-json", default=None, help="渲染登记 JSON（兼容模式）")
    ap.add_argument("--doc-sha1", default=None, help="PDF 内容 sha1（兼容模式）")
    return ap


def main(argv=None):
    ap = build_argparse()
    args = ap.parse_args(argv)
    skill_base = Path(__file__).resolve().parents[2]
    cfg = load_config(str(skill_base))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not _structural_ok(skill_base, ignore_gpu_lib=args.ignore_gpu_lib):
        return maybe_offer_degrade(
            "structural: M1/M2 missing or deps unsatisfied", cfg, out,
            tty=_stdin_isatty())        # 轻微-1：stdin 为 None 时旧写法抛 AttributeError
    if args.page_image:
        if args.pdf:
            _safe_print("pdf 与 --page-image 互斥：一次只用一种模式。", file=sys.stderr)
            return 2
        return _ms1_page_loop(args, cfg, out)
    if not args.pdf:
        ap.print_usage()
        _safe_print("缺少 PDF：orchestrator.py <pdf> --out <dir>", file=sys.stderr)
        return 2
    return run_pdf(args.pdf, out, cfg, args)


if __name__ == "__main__":
    sys.exit(main())
