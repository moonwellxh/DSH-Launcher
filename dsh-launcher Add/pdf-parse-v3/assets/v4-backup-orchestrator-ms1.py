#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M12 orchestrator.py —— 全流程编排（MS-1 其段骨架）
=================================================
职责（设计书 §6.12 / 粗架构 §1.2）：CLI、配置集中、断点续跑（页级落盘）、幂等、
`--no-egress` 短路 M4（三厂商全阻断）、分通道预算闸、启动环境门（FR-G3 占位）。

MS-1 范围声明：本阶段只接 M4（glm_parse_page）最小闭环；M2 渲染/MS-6/MS-7/M8 等在
后续里程碑接入。因此页图来源在本阶段为 `--page-image`（已渲染 PNG）+ `--page N`；
完整 `<pdf> → 页图` 渲染由 M2 提供（MS-4），在此之前若给 `<pdf>` 会明确提示改用
`--page-image`，本模块不做临时内联渲染（设计书 m-08/L-2 处置）。

用法：
  python orchestrator.py --page-image <png> --page 1 --out <dir> [--no-egress]
                         [--no-cache] [--budget-glm X] [--budget-review Y]
                         [--render-reg-json '{"dpi":225,"pixel":[1860,2699],"render_sha1":"..."}']
"""
import argparse
import hashlib
import json
from pathlib import Path

from vision_client import (VisionClient, VisionError, BudgetGate,
                           GLM_CHANNEL, SECOND_OPINION_CHANNEL)


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
    """config.default.json（版本受控）+ 用户级覆盖 config.user.json（deep-merge，用户优先）。"""
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


# ---------------------------------------------------------------- 渲染登记（M2 占位，仅 convenience）

def build_render_reg(png_path, *, dpi=None, target_width=None, page_size=None):
    """从页图推导最小渲染登记（§3.2 要素）。MS-1 的 M2 占位；M2 接入后禁用此推导。
    pixel 优先取实际位图尺寸；dpi 按 target_width/pdf_rect_pt 派生或取默认。
    JSON 不内联全登记，仅取出域/裁剪所需的最小要素。"""
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
    m = out_dir / "marks"
    m.mkdir(parents=True, exist_ok=True)
    (m / f"page_{page:04d}.json").write_text(
        json.dumps({"page": page, "kind": kind, "reason": reason}, ensure_ascii=False),
        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="pdf-parse-v3 v4 管线编排（MS-1 骨架）")
    ap.add_argument("pdf", nargs="?", help="PDF 文件（MS-1 未接 M2 渲染，页图请用 --page-image）")
    ap.add_argument("--page-image", action="append", default=[], help="已渲染页图 PNG（可多个）")
    ap.add_argument("--page", type=int, default=None, help="页号（配合 --page-image；缺省从文件名推导）")
    ap.add_argument("--out", required=True, help="工作区/输出目录")
    ap.add_argument("--no-egress", action="store_true", help="全局短路三厂商出域（FR-D7 降级）")
    ap.add_argument("--no-cache", action="store_true", help="禁用指纹缓存")
    ap.add_argument("--budget-glm", type=float, default=None, help="GLM 主通道预算（CNY）")
    ap.add_argument("--budget-review", type=float, default=None, help="复核通道预算（CNY）")
    ap.add_argument("--render-reg-json", default=None,
                    help="渲染登记 JSON，如 '{\"dpi\":225,\"pixel\":[1860,2699],\"render_sha1\":\"..\"}'")
    ap.add_argument("--doc-sha1", default=None, help="PDF 内容 sha1（缺省用页图 sha1 代理）")
    args = ap.parse_args()

    skill_base = Path(__file__).resolve().parents[2]      # .../pdf-parse-v3
    cfg = load_config(str(skill_base))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if not args.page_image:
        if args.pdf:
            raise SystemExit("MS-1 未接入 M2 渲染：请用 --page-image 提供已渲染页图；或先实现 M2 render.py。")
        raise SystemExit("缺少页图：--page-image <png>")

    # 预算闸接线（分通道）
    limits = {}
    if args.budget_glm is not None:
        limits[GLM_CHANNEL] = args.budget_glm
    if args.budget_review is not None:
        limits[SECOND_OPINION_CHANNEL] = args.budget_review

    client = VisionClient(cfg, egress_allow=(not args.no_egress),
                          no_cache=args.no_cache,
                          budget=BudgetGate(cfg, limits),
                          ledger_path=str(out / "ledger" / "token.jsonl"))

    for img in args.page_image:
        png = Path(img)
        # 页号推导：--page 优先，否则从 filename page_NNNN 提取
        n = args.page if args.page is not None else _page_from_name(png.stem)
        if n is None:
            raise SystemExit(f"无法从 {png.name} 推导页号，请用 --page N")
        # 断点：已处理页跳过（FR-G1）
        rawo = out / "glm" / f"page_{n:04d}.json"
        if rawo.exists():
            print(f"[skip] page {n} 已存在：{rawo}")
            continue
        render_reg = json.loads(args.render_reg_json) if args.render_reg_json else build_render_reg(png)
        doc_sha1 = args.doc_sha1 or render_reg["render_sha1"]
        try:
            res = client.glm_parse_page(png, page=n, doc_sha1=doc_sha1, render_reg=render_reg)
        except VisionError as e:
            # FR-D7：视觉不可用（无key/预算/断网/超时/4xx/5xx/schema_invalid/egress/output_length）
            # → 诚实降级标记，不阻塞全流程；output_length 记 unreadable，其余记 degraded
            kind = "unreadable" if e.kind in ("output_length_exceeded",) else "degraded"
            _marker(out, n, kind, f"{e.kind}: {e.detail}")
            print(f"[degrade] page {n} -> {e.kind}")
            continue
        (out / "glm").mkdir(parents=True, exist_ok=True)
        rawo.write_text(json.dumps(res["raw_response"], ensure_ascii=False), encoding="utf-8")
        print(f"[ok] page {n} cache_hit={res['cache_hit']} cost={res['cost_cny']} "
              f"md_chars={len(res.get('md') or '')}")
    print("DONE.")


def _page_from_name(stem):
    # 形式 page_0001 / page_1 / 0001
    import re
    m = re.search(r"(\d+)$", stem)
    return int(m.group(1)) if m else None


if __name__ == "__main__":
    main()
