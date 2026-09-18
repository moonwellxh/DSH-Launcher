#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic unit tests for pdf2v3.py (Schema v3.0 builder).

Run:  python tests/test_pdf2v3.py    (exit 0 = all pass)
Covered:
  - chapter / article detection (两种条文式样) with page provenance
  - enumerated item splitting incl. cross-page continuation
  - table & figure caption extraction (page container)
  - global noise (repeated header/footer/watermark) removal
  - md A3 count invariants + A6 page-range checks (issues list)
  - load_parts ordering from extract.json fixtures
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"))
from pdf2v3 import drop_global_noise, build_v3, load_parts  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append("%s %s" % (name, detail))
        print("FAIL %s %s" % (name, detail))
    else:
        print("PASS %s" % name)


def synthetic():
    noise = "〕 告 亻 介 者 ． 网 www · zaojiazhe. com"
    pages = [
        (1, [noise, "1", "第一章 总则",
             "第1.0.1条 为了预防火灾，减少火灾危害，制定本规范。",
             "第1.0.2条 本规范适用于下列新建扩建改建工程：",
             "1 厂房、仓库", "2 民用建筑", "（1）住宅", "（2）公共建筑"]),
        (2, ["（3）地下建筑", "表3.3.1 厂房的防火分区面积", "数据行1",
             "图3-2 楼梯栏杆立面详图", "注：图中尺寸单位mm。",
             "第二章 术语",
             "2.1.1 高层建筑：建筑高度大于27m的住宅建筑。"]),
        (3, [noise, "本规范由公安部负责管理。",
             "第三章 防火分区",
             "第3.0.1条 各类建筑的防火分区应符合下表规定。"]),
    ]
    cleaned = drop_global_noise(pages)
    std = {"name": "测试规范", "code": "TEST-1", "year": 2020,
           "document_class": "normative_standard", "type": "正文（OCR提取）"}
    issues = []
    doc, issues = build_v3(cleaned, std, "unit", issues)
    md = doc["metadata"]
    check("total_pages=3", md["total_pages"] == 3, str(md))
    titles = [c["chapter_title"] for c in doc["chapters"]]
    check("chapters 3", len(doc["chapters"]) == 3, str(titles))
    check("ch1 page=1", doc["chapters"][0]["page"] == 1)
    check("ch3 page=3", doc["chapters"][2]["page"] == 3 and doc["chapters"][2]["chapter_title"] == "防火分区")
    nums = [a["article_number"] for a in doc["articles"]]
    check("articles ordered", nums == ["1.0.1", "1.0.2", "2.1.1", "3.0.1"], str(nums))
    a = next(x for x in doc["articles"] if x["article_number"] == "1.0.2")
    check("article page=1", a["page"] == 1)
    check("items split+cont", any("地下建筑" in c for c in a["content"]) and len(a["content"]) >= 6,
          str(a["content"]))
    check("ch1 nested articles=2", len(doc["chapters"][0]["articles"]) == 2)
    check("table caption", len(doc["pages"][1]["tables"]) == 1
          and doc["pages"][1]["tables"][0]["table_no"] == "3.3.1")
    check("figure caption", len(doc["pages"][1]["figures"]) == 1
          and doc["pages"][1]["figures"][0]["figure_no"] == "3-2")
    check("noise removed", "zaojiazhe" not in doc["pages"][0]["text"])
    check("A3 counts", md["chapter_count"] == len(doc["chapters"])
          and md["article_count"] == len(doc["articles"]))
    n_tab = sum(len(p.get("tables", [])) for p in doc["pages"])
    check("A3 table_count", md["table_count"] == n_tab, "%s vs %s" % (md["table_count"], n_tab))
    check("no issues in clean fixture", len(issues) == 0, str(issues))


def adversarial_fixtures():
    """Regression cases found in adversarial review of real GBJ16-87 scan:
    - TOC lines with dot leaders must not create chapters/articles
    - table rows starting with numbers (4.0 0 非燃烧体...) must not become articles
    - article number whose leading component mismatches current chapter is rejected
    - '第x条、第y条、...' TOC clusters must not create articles"""
    noise = "〕 告 亻 介 者 ． 网 www · zaojiazhe. com"
    pages = [
        (1, ["第三章 厂房 ........... 45",          # TOC row
             "第3.1.1条、第3.2.1条、第3.3.1条、",    # TOC cluster
             "第三章 厂房",
             "3.2.2 特殊贵重的机器设备应设在一级耐火等级建筑内。",
             "4.0 0 非燃烧体非燃者体难燃娆体 耐火等级表",  # table row -> no article
             "5.1.3 他章条文混入 -> 不应建条"]),          # prefix mismatch
    ]
    cleaned = drop_global_noise(pages)
    std = {"name": "T", "code": "T-1", "year": 2020,
           "document_class": "normative_standard", "type": "正文（OCR提取）"}
    issues = []
    doc, issues = build_v3(cleaned, std, "unit", issues)
    nums = [a["article_number"] for a in doc["articles"]]
    check("adv: toc rows skipped", len(doc["chapters"]) == 1
          and doc["chapters"][0]["chapter_title"] == "厂房", str(doc["chapters"]))
    check("adv: no toc-cluster article", "3.1.1" not in nums and "3.3.1" not in nums, str(nums))
    check("adv: table row not article", "4.0" not in nums, str(nums))
    check("adv: prefix-mismatch not article", "5.1.3" not in nums, str(nums))
    check("adv: only 3.2.2 kept", nums == ["3.2.2"], str(nums))
    txt = doc["pages"][0]["text"]
    check("adv: toc text still lossless", ("厂房" in txt) and ("耐火等级表" in txt))


def load_parts_fixture():
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for tag, txt in (("a", "X"), ("b", "Y")):
            p = os.path.join(d, "p%s.json" % tag)
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"pages_text": [{"page": 1, "text": txt}]}, f)
            paths.append(p)
        merged = load_parts(paths)
        check("load_parts renumber", [pg for pg, _ in merged] == [1, 2]
              and [ln[0] for _, ln in merged] == ["X", "Y"], str(merged))


def toc_page_fixture():
    pages = [(1, ["第一章 总则 ...... 1", "第二章 术语 ...... 10",
                  "第三章 厂房 ...... 45", "第四章 仓库 ...... 80",
                  "正文未编号行应保留"])]
    cleaned = drop_global_noise(pages)
    std = {"name": "T", "code": "T-2", "year": 2020,
           "document_class": "normative_standard", "type": "正文（OCR提取）"}
    issues = []
    doc, issues = build_v3(cleaned, std, "unit", issues)
    check("toc page: no chapters", len(doc["chapters"]) == 0, str(doc["chapters"]))
    check("toc page: text lossless", "正文未编号行应保留" in doc["pages"][0]["text"])
    check("toc page: flagged in issues", len(issues) >= 1, str(issues))


def separator_and_footer_fixtures():
    """Regression for the two OCR-noise defects fixed 2026-09-19.
    (1) RE_NUM_DOT folds OCR separator forms (. ． · ‧ ∙ ⋅) but must NOT
        fold comma / full-width comma / dun-hao: folding those mints bogus articles
        (5、6 项说明 -> 5.6 ; 1，234 件设备 -> 1.234).
    (2) page-number footers that vary per page (第N页 共M页, - N -) must be dropped;
        N/M must NOT be dropped (real corpus has a bare table-data line 687/891)."""
    from pdf2v3 import clean_line, RE_ARTICLE_A, RE_ARTICLE_B
    std3 = {"name": "T", "code": "T-3", "year": 2020,
            "document_class": "normative_standard", "type": "正文（OCR提取）"}
    # (1a) mid-dot forms become articles (chapter number matches the prefix)
    pages = [(1, ["第一章 总则", "1.1 设备参数"]),
             (2, ["第二章 术语", "2 · 1 术语说明"]),
             (3, ["第三章 防火分区", "3‧1 验收资料清单"])]
    cleaned = drop_global_noise(pages)
    doc, _ = build_v3(cleaned, std3, "unit", [])
    nums = [a["article_number"] for a in doc["articles"]]
    check("sep: mid-dot headings become articles", nums == ["1.1", "2.1", "3.1"], str(nums))
    # (1b) comma / dun-hao are NOT folded at all
    for ln in ["1，1 设备参数", "1,1 设备参数", "1、1 设备参数"]:
        c = clean_line(ln)
        check("sep: not folded %s" % ln,
              not (RE_ARTICLE_A.match(c) or RE_ARTICLE_B.match(c)), repr(c))
    # (1c) and they must not mint articles even when the chapter prefix matches
    pages = [(1, ["第五章 安全疏散", "5，6 项说明", "5、6 项说明"])]
    cleaned = drop_global_noise(pages)
    doc, _ = build_v3(cleaned, std3, "unit", [])
    nums = [a["article_number"] for a in doc["articles"]]
    check("sep: comma/dun-hao mint no articles", nums == [], str(nums))
    # (2a) per-page-varying page footers are dropped
    foot = [(1, ["第 1 页 共 3 页", "正文一"]),
            (2, ["第 2 页 共 3 页", "正文二"]),
            (3, ["第 3 页 共 3 页", "正文三"])]
    out = drop_global_noise(foot)
    check("footer: 第N页共M页 dropped",
          all(len(ls) == 1 and ls[0].startswith("正文") for _, ls in out), str(out))
    foot2 = [(1, ["- 12 -", "正文一"]), (2, ["第2页", "正文二"]),
             (3, ["— 3 —", "正文三"])]
    out2 = drop_global_noise(foot2)
    check("footer: - N - / 第N页 dropped",
          all(len(ls) == 1 and ls[0].startswith("正文") for _, ls in out2), str(out2))
    # (2b) look-alikes must survive
    keep = ["687/891", "3/4", "2026/9", "2026", "4000", "第 3 章 厂房",
            "2. 煤、焦炭、油母页岩的筛分、转运工段"]
    pages = [(1, ["第一章 总则", "1.1 一般规定"] + keep)]
    got = drop_global_noise(pages)[0][1]
    flat = [x.replace(" ", "") for x in got]
    for s in keep:
        check("keep: %s survives" % s, s.replace(" ", "") in flat, str(got))
    # (2c) identical repeated lines must still be dropped (L71 not regressed)
    same = [(1, ["某某规范", "正文一"]),
            (2, ["某某规范", "正文二"]),
            (3, ["某某规范", "正文三"])]
    out3 = drop_global_noise(same)
    check("footer: identical repeated line still dropped",
          all(len(ls) == 1 for _, ls in out3), str(out3))
    # (2d) L71 threshold pinned from BOTH sides (n=4 pages -> threshold 3)
    l71 = [(1, ["\u91cd\u590d\u884c", "\u6b63\u6587\u4e00", "\u53ea\u51fa\u73b0\u4e24\u6b21"]),
           (2, ["\u91cd\u590d\u884c", "\u6b63\u6587\u4e8c", "\u53ea\u51fa\u73b0\u4e24\u6b21"]),
           (3, ["\u91cd\u590d\u884c", "\u6b63\u6587\u4e09"]),
           (4, ["\u6b63\u6587\u56db"])]
    kept71 = [x for _, ls in drop_global_noise(l71) for x in ls]
    check("L71: 3-of-4 repeated line dropped", "\u91cd\u590d\u884c" not in kept71, str(kept71))
    check("L71: 2-of-4 line survives (threshold not weakened)",
          "\u53ea\u51fa\u73b0\u4e24\u6b21" in kept71, str(kept71))
    # (2e) L85 bare-number rule still drops 1-3 digits, still keeps 4 digits
    l85 = [(1, ["1", "\u6b63\u6587\u4e00"]), (2, ["999", "\u6b63\u6587\u4e8c"]),
           (3, ["1000", "\u6b63\u6587\u4e09"])]
    kept85 = [x for _, ls in drop_global_noise(l85) for x in ls]
    check("L85: bare 1-3 digit still dropped",
          "1" not in kept85 and "999" not in kept85, str(kept85))
    check("L85: 4-digit value still kept", "1000" in kept85, str(kept85))


if __name__ == "__main__":
    synthetic()
    adversarial_fixtures()
    toc_page_fixture()
    separator_and_footer_fixtures()
    load_parts_fixture()
    if FAILS:
        print("RESULT fail=%d" % len(FAILS))
        sys.exit(1)
    print("RESULT pass all")
    sys.exit(0)
