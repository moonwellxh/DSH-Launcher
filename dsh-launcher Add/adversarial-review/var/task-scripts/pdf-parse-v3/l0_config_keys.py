#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L0 确定性检查：cfg 键路径一致性（config.default.json vs 代码取键）。
作用：检出代码引用而 config 未定义/缺结构子键的键路径。
输入：被审对象根目录（pdf-parse-v3），其下 assets/v4/config.default.json 与 *.py。
输出：MISSING_TOP=… / MISSING_SUB=…（一行可 grep）。
复跑：python l0_config_keys.py <被审对象根>；依赖：仅标准库。"""
import json
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("usage: python l0_config_keys.py <被审对象根(如 …/pdf-parse-v3)>")
        return 2
    root = Path(sys.argv[1]).resolve()
    v4 = root / "assets" / "v4"
    cfg = json.loads((v4 / "config.default.json").read_text(encoding="utf-8"))
    missing_top, missing_sub = [], []
    for f in ["vision_client.py", "orchestrator.py", "gate.py", "quality.py", "pipeline.py",
              "textlayer.py", "ocr_channel.py", "defect_ladder.py", "table_adapter.py",
              "figures.py", "structurer.py"]:
        txt = (v4 / f).read_text(encoding="utf-8")
        for m in re.finditer(r"\bcfg\.(?:get\(\s*)?\[?\s*['\"]([^'\"]+)['\"]", txt):
            if m.group(1) not in cfg:
                missing_top.append(f"{f}:{m.group(1)}")
    # 结构性子键（models/budget/render/egress/cache/prompt_version）
    expect = {
        "models.glm": ["model", "endpoint", "price_in", "price_out", "max_image_bytes"],
        "models.deepseek": ["model", "endpoint", "price_in_peak", "price_in_offpeak",
                            "price_out_peak", "price_out_offpeak", "cache_hit_in_peak",
                            "cache_hit_in_offpeak", "peak_hours", "peak_weekdays_only"],
        "models.qwen": ["model", "endpoint", "price_in", "price_out", "max_tokens"],
        "budget": ["glm_per_volume_cny", "second_opinion_per_volume_cny", "deepseek_peak_cap_cny"],
        "egress": ["allow"], "cache": ["dir", "enabled"],
        "prompt_version": ["narrow_task", "crop_hint"],
    }
    for path, keys in expect.items():
        node = cfg
        for k in path.split("."):
            node = node.get(k, {}) if isinstance(node, dict) else {}
        for k in keys:
            if k not in node:
                missing_sub.append(f"{path}.{k}")
    print("MISSING_TOP=" + ",".join(sorted(set(missing_top))) if missing_top else "MISSING_TOP=none")
    print("MISSING_SUB=" + ",".join(sorted(missing_sub)) if missing_sub else "MISSING_SUB=none")
    return 1 if (missing_top or missing_sub) else 0


if __name__ == "__main__":
    sys.exit(main())
