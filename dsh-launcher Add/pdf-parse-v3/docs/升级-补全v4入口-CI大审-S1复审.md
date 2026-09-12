# 升级-补全v4入口：CI 大审 S-1 微增复审意见单（第 8 步后续 · 只核对 S-1 修复增量）

| 字段 | 内容 |
| --- | --- |
| 轮次 | 微增复审（仅核对上轮 S-1 的修复增量，其余不审） |
| 审查类型 | 独立对抗复审（只报告模式，未改任何产物） |
| 审查者 | 独立子审查者（未 fork 编排/作者会话，只喂产物全文+冻结依据+实测输出） |
| 对象 | S-1 修复增量：`tests/v4/test_orchestrator_pdf.py` ①-b 段（raw_resp 钉定守卫，新增） |
| 依据 | ①`docs/升级-补全v4入口-CI大审意见单.md` S-1 描述；②实物 `assets/v4/pipeline.py`（process_page_md/_image_blocks）、`assets/v4/orchestrator.py`（_scan_page_glm/_scan_page_local/run_pdf）；③冻结《详细技术设计.md》§5（:449/:458）；④既有 GLM 夹具 `tests/vision_shootout/results/batch/page_0001/0142/0143/0173.json`（真实 layout_details 结构） |

---

## 0. 实测证据（审查者本机执行，只读）

- `python -X utf8 tests/v4/test_orchestrator_pdf.py`（`PYTHONDONTWRITEBYTECODE=1`）→ `RESULT pass=24 fail=0`（上轮 pass=21，新增 ①-b 三条断言，全部真实通过）：
  - `[PASS] ①-b payload 正确层→images 非空 images=1`
  - `[PASS] ①-b 错层传递→images 恒空（守卫存在） images=0（错层即钉定回归：应恒空）`
  - `[PASS] ①-b _image_blocks 从 payload 提取 image 块 1`
- 与实物交叉核对（只读）：
  - `orchestrator.py:271` `payload = (res.get("raw_response") or {}).get("response") or {}`；`orchestrator.py:278` `raw_resp=payload`。①-b 的「正确层」payload 与「错层」外层包装，正是 `raw_resp` 在该调用点的两个候选值——两值均有真实对应，非虚构。
  - `pipeline.py:34-50` `_image_blocks` 读 `(raw_resp or {}).get("layout_details")`；`pipeline.py:85` `imgs=_image_blocks(raw_resp)`。真实 GLM `layout_details` 为 `[[{...}]]`（页列表嵌套），`_image_blocks` 取 `pages_blk[0]`（单页调用契约）。①-b 合成 payload 用 `[[image_block]]`，与真实结构一致。

---

## 一、S-1 判定：闭合（可放行）

**S-1 已闭合。** 修复新增一条离线可跑的确定性守卫，真实落地于「raw_resp 必须传 response payload（含 layout_details）否则 images 恒空」的核心不变式，实测三条断言全绿，未引入新缺陷，无新严重/阻断项。

### 判定重点逐条

1. **核心不变式验证=通过。** 正确层（`{"layout_details":[[image块]], "md_results":…}`，即 `res["raw_response"]["response"]` 形态）→ `_image_blocks` 读到 `layout_details` → `images` 非空；错层（`{"raw_response":{"response":…}}`，即 `res["raw_response"]` 外层包装形态）→ `.get("layout_details")` 为 None → `_image_blocks` 恒返 `[]` → `images` 恒空。两层结构均与 `_scan_page_glm` 的真实候选值一一对应，非假设空测。
2. **离线可跑=是。** 直接构造合成 payload 调 `pipeline.process_page_md(1, md, {}, ocr_lines=[], ocr_available=False, m4=None, raw_resp=…)`，全程无 GLM key、无网络、无 VisionClient 出域；`html_to_grid` 对不含 `<table` 的 md 直接返回 `[]`，不会因 markdown 表崩溃。实测本机离线通过。
3. **防静默丢失语义=覆盖。** 反例「错层→images 恒空」就是 FR-B6/S6 静默丢失的回归形态；守卫存在意味着一旦把错误层传入 `raw_resp`，该断言立即变红。防丢失语义在契约层（`_image_blocks`/`process_page_md`）被钉住。
4. **反例合理性=是。** 错层=外层包装 `{"raw_response":{…}}`，恰是《简版技术设计》复审 r3「严重-2」的 bug 形态（外层包装上无 `layout_details`）；`_image_blocks(wrapper).get("layout_details")` 恒 None → 恒空，确定性成立。反例断言的是该钉定要防的真实回归，合理。
5. **结构一致性=一致，未见假绿。** 真实 GLM `layout_details` 为 `[[{...}]]`（页列表嵌套，实测夹具 `page_0001/0142/0143/0173` 均含 `"native_label":"image"` 块），`_image_blocks` 读 `pages_blk[0]`（单页调用语义自洽）；①-b 合成 payload 用 `[[image_block]]`，与真实结构一致，非依赖错误结构假绿。合成块额外带 `"type"`/`"content"` 字段，而真实 image 块一般无 `content`；但 `_image_blocks` 用 `content or str(bb)` 兜底取 hash（pipeline.py:46），真实无 content 块仍可提取，因此合成块带这些字段不构成假绿，也不掩盖真实块提取路径。

---

## 二、残余观察（建议级，非阻断/非严重，不构成「未闭合」）

- **守卫在 `process_page_md` 层，未直接钉定 `orchestrator._scan_page_glm`（orchestrator.py:271）的 payload 提取接线。** ①-b 直接向 `process_page_md` 传入正确的合成 payload，绕过了 orchestrator 侧 `payload = (res.get("raw_response") or {}).get("response") or {}` 这行真实语义。若未来该行回退为 `payload = res.get("raw_response")`（外层包装），①-b 仍会全绿，而生产 `<pdf>` 路径将静默丢图——这正是 S-1 深入要防的回归。该残余属「详细技术设计-复审意见单·r3」推荐「确定性单测直接调 process_page_md」这一解的**固有取舍**（同一复审同时让 ① 端到端保留 schema/页数/exit0，未含 images 断言），非本次修复引入的新缺陷；当前生产码（orchestrator.py:271）正确，故不构成严重/阻断。若需彻底钉死生产接线，可另补一条走 GLM 路径的桩（mock `VisionClient.glm_parse_page` 返回含 image 块 payload → 经 `_scan_page_glm`/`run_pdf` 断言组装输出 `pages[i].images` 非空，即原 CI 大审「修复预估」形），属可选加固。
- ① `schema 4.0` 断言仍为 `or` 放宽（上轮已列 L-3 轻微），本次范围外，不重审、不计入此判定。

---

## 三、收敛小结

**S-1 闭合，可放行。** 判据（阻断清零 ∧ 严重清零）：本复审未发现新增阻断级、新增严重级问题；S-1 修复真实落地、离线可跑、核心不变式（raw_resp 必须传 response payload，否则 images 恒空）已被确定性守卫验证，反例覆盖 FR-B6/S6 静默丢失回归语义。唯一残余（process_page_md 层守卫未直接钉定 orchestrator 接线）为建议级可选加固，不影响放行。
