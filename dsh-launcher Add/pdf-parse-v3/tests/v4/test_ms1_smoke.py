#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/v4/test_ms1_smoke.py —— MS-1 骨架冒烟（五出口，离线不打 API）
==================================================================
覆盖（详细技术设计 §12 MS-1 出口判据）：
  ① 单页 GLM 解析通 + 原始响应落盘（黄金夹具 page_0001.json 离线重放）
  ② 台账逐调用落盘（prompt/completion/cache_hit/cost）
  ③ 缓存命中零计费 + KD6 指纹隔离不变式（同页同bbox同任务同渲染参数命中、跨/域任务/重试不误命中）
  ④ --no-egress 短路三厂商（glm/deepseek/qwen）出域
  ⑤ 最小闭环（真实页图 page_0001.png + 真实原始响应 page_0001.json 离线闭环）

夹具先验（FR-G6）：先验夹具再判产品缺陷。离线、零网络、零费用。
用真实 GLM 响应（results/batch/page_0001.json）作为首跑注入 → MISS → 复跑 → HIT 零计费。

用法：python tests/v4/test_ms1_smoke.py
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[2]          # .../pdf-parse-v3
ASSETS = SKILL / "assets" / "v4"
sys.path.insert(0, str(ASSETS))

from vision_client import (VisionClient, VisionError, VisionCache, BudgetGate,  # noqa: E402
                           cache_fingerprint, load_keys, validate_second_opinion,
                           price_for, peek_channel_peak,
                           GLM_CHANNEL, SECOND_OPINION_CHANNEL,
                           TASK_FULL_PAGE, TASK_CROP, TASK_NARROW)
import orchestrator as orc  # noqa: E402

FIXTURE_JSON = SKILL / "tests" / "vision_shootout" / "results" / "batch" / "page_0001.json"
PAGE_PNG = SKILL / "tests" / "vision_shootout" / "batch_samples" / "page_0001.png"

# 渲染登记（§3.2 要素；pixel 取自夹具 data_info 页宽高，render_sha1=页图内容哈希）
PIXEL = [1860, 2699]
DOC_SHA1 = "ms1_fixture_doc_sha1"      # 夹具 PDF 内容 sha1 的代理（离线口径，跨调用一致）
RENDER_REG = {"dpi": 225, "pixel": PIXEL, "render_sha1": None, "target_width": 1860,
              "downsampled_from": None}


def build_render_reg(png):
    reg = dict(RENDER_REG)
    reg["render_sha1"] = orc.build_render_reg(png, dpi=225, page_size=PIXEL)["render_sha1"]
    return reg


class Tally:
    def __init__(self):
        self.pass_ = 0
        self.fail = 0
        self.failures = []

    def check(self, name, ok, detail=""):
        if ok:
            self.pass_ += 1
            print(f"[PASS] {name} {detail}")
        else:
            self.fail += 1
            self.failures.append(name)
            print(f"[FAIL] {name} {detail}")


def main():
    t = Tally()
    cfg = orc.load_config(str(SKILL))

    # 元素准备
    fixture = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    reg = build_render_reg(PAGE_PNG)
    if reg["render_sha1"] is None:
        raise SystemExit("无法计算页图哈希")
    tmp = Path(tempfile.mkdtemp(prefix="ms1_"))

    # ---------- ① + ⑤：MISS → 落盘 → HIT 零计费（最小闭环） ----------
    client = VisionClient(cfg, egress_allow=True,
                          budget=BudgetGate(cfg, {GLM_CHANNEL: 1.0}),
                          cache=VisionCache(tmp / "cache", enabled=True),
                          ledger_path=str(tmp / "ledger" / "token.jsonl"))
    # 首跑 MISS
    r1 = client.glm_parse_page(PAGE_PNG, page=1, doc_sha1=DOC_SHA1, render_reg=reg,
                               raw_inject=fixture)
    t.check("① 首跑 MISS 返回非命中", r1.get("cache_hit") is False and r1.get("usage") is not None,
            f"cache_hit={r1['cache_hit']} usage={r1['usage']}")
    t.check("① 原始响应含 md 与 usage", ("md_results" in (r1["raw_response"].get("response") or {}))
            and (r1["raw_response"].get("response") or {}).get("usage"),
            f"md_chars={len(r1.get('md') or '')}")
    # 原始响应落盘（模拟 M12 写 work/glm/page_N.json）
    out = tmp / "glm"
    out.mkdir(parents=True, exist_ok=True)
    (out / "page_0001.json").write_text(json.dumps(r1["raw_response"], ensure_ascii=False), encoding="utf-8")
    t.check("① 原始响应落盘", (out / "page_0001.json").exists())
    t.check("① 命中期返回 cache_hit 且零计费",
            (r1["cache_hit"] is False) and (r1["cost_cny"] == 0.000156),
            f"cost={r1['cost_cny']}")
    # S5：返回含 blocks/http_status/latency_s（§3.1 M4 契约）
    t.check("⑤ 返回结构含 blocks/http_status/latency_s",
            isinstance(r1.get("blocks"), list) and r1.get("http_status") == 200
            and isinstance(r1.get("latency_s"), (int, float)),
            f"n_blocks={len(r1.get('blocks') or [])} http={r1.get('http_status')} lat={r1.get('latency_s')}")
    # 复跑 HIT
    r2 = client.glm_parse_page(PAGE_PNG, page=1, doc_sha1=DOC_SHA1, render_reg=reg,
                               raw_inject=fixture)
    t.check("③ 复跑命中零计费", r2.get("cache_hit") is True and r2.get("usage") is None
            and r2.get("cost_cny") == 0.0,
            f"cache_hit={r2['cache_hit']} usage={r2['usage']} cost={r2['cost_cny']}")
    t.check("③ 命中期返回缓存的原始响应", r2["raw_response"] == r1["raw_response"])
    # B1 回归：缓存命中不出域（真实出域调用仅发生在 MISS；复跑 HIT 不再调 requests.post）
    import vision_client as vc
    class _Resp:
        def __init__(self, code, payload, text=""):
            self.status_code = code
            self._payload = payload
            self.text = text
        def json(self):
            return self._payload
    _calls = []
    def _post(*a, **k):
        _calls.append(k)
        return _Resp(200, fixture.get("response"))
    b1client = VisionClient(cfg, egress_allow=True, budget=BudgetGate(cfg),
                            cache=VisionCache(tmp / "b1cache", enabled=True),
                            ledger_path=str(tmp / "ledger" / "b1.jsonl"))
    with mock.patch.object(vc.requests, "post", _post):
        a1 = b1client.glm_parse_page(PAGE_PNG, page=1, doc_sha1="b1doc", render_reg=reg)   # MISS → 1 次真实出域
        a2 = b1client.glm_parse_page(PAGE_PNG, page=1, doc_sha1="b1doc", render_reg=reg)   # HIT → 0 次真实出域
    t.check("B1 缓存命中不出域", a1["cache_hit"] is False and a2["cache_hit"] is True and len(_calls) == 1,
            f"MISS={a1['cache_hit']} HIT={a2['cache_hit']} egress_calls={len(_calls)}")
    # ② 台账逐调用
    led = [json.loads(x) for x in (tmp / "ledger" / "token.jsonl").read_text(encoding="utf-8").splitlines() if x]
    t.check("② 台账两行（MISS+HIT）", len(led) == 2, f"n={len(led)}")
    if len(led) >= 2:
        t.check("② MISSave 台账含 prompt/completion/cost",
                all(k in led[0] for k in ("prompt", "completion", "cache_hit", "cost_cny"))
                and led[0]["cache_hit"] is False and led[0]["prompt"] == 694)
        t.check("② HIT 台账 cache_hit=true 计费为 0",
                led[1]["cache_hit"] is True and led[1]["cost_cny"] == 0.0 and led[1]["prompt"] is None
                and led[1]["completion"] is None)

    # ---------- ③ KD6 指纹隔离不变式 ----------
    def fp(**over):
        d = dict(doc_sha1=DOC_SHA1, page=1, task_type=TASK_FULL_PAGE, bbox=None,
                 render_reg=reg, model=cfg["models"]["glm"]["model"],
                 prompt_ver="nt-1.0", retry={"seq": 0, "feedback_sha1": None})
        d.update(over)
        return cache_fingerprint(**d)

    base = fp()
    t.check("③ 同参指纹稳定", base == fp())
    variants = {
        "bbox": lambda: fp(bbox=[10, 10, 100, 100]),
        "task": lambda: fp(task_type=TASK_CROP),
        "retry_seq": lambda: fp(retry={"seq": 1, "feedback_sha1": "abc"}),
        "dpi": lambda: fp(render_reg={**reg, "dpi": 180}),
        "pixel": lambda: fp(render_reg={**reg, "pixel": [900, 1300]}),
        "img_hash": lambda: fp(render_reg={**reg, "render_sha1": "other"}),
        "doc": lambda: fp(doc_sha1="different_doc"),
        "model": lambda: fp(model="other-model"),
        "prompt": lambda: fp(prompt_ver="ch-2.0"),
        "task_narrow": lambda: fp(task_type=TASK_NARROW),
    }
    for name, fn in variants.items():
        t.check(f"③ 指纹隔离（{name}）", fn() != base)
    # 同任务不同 bbox（裁剪）应互异 —— 跨区域隔离
    t.check("③ 同任务跨区域（full vs crop 同bbox 不同）",
            fp(task_type=TASK_FULL_PAGE, bbox=[0, 0, 10, 10]) != fp(task_type=TASK_CROP, bbox=[0, 0, 10, 10]))

    # ---------- ④ --no-egress 短路三厂商 ----------
    noegress = VisionClient(cfg, egress_allow=False, budget=BudgetGate(cfg),
                            cache=VisionCache(tmp / "cache2", enabled=True),
                            ledger_path=str(tmp / "ledger" / "token2.jsonl"))
    for name, fn in (
        ("glm_parse_page", lambda: noegress.glm_parse_page(PAGE_PNG, page=1, doc_sha1=DOC_SHA1,
                                                           render_reg=reg, raw_inject=fixture)),
        ("second_opinion_deepseek", lambda: noegress.second_opinion(
            PAGE_PNG, [0, 0, 50, 50], page=1, doc_sha1=DOC_SHA1, render_reg=reg,
            vendor="deepseek", raw_inject=_valid_so_response("deepseek"))),
        ("second_opinion_qwen", lambda: noegress.second_opinion(
            PAGE_PNG, [0, 0, 50, 50], page=1, doc_sha1=DOC_SHA1, render_reg=reg,
            vendor="qwen", raw_inject=_valid_so_response("qwen"))),
    ):
        try:
            fn()
            t.check(f"④ no-egress {name} 抛 egress_blocked", False, "未抛错（有出域）")
        except VisionError as e:
            t.check(f"④ no-egress {name} 抛 egress_blocked", e.kind == "egress_blocked",
                    f"kind={e.kind}")
    ledger2 = Path(tmp / "ledger" / "token2.jsonl")
    t.check("④ no-egress 零网络零台账",
            (not ledger2.exists()) or len([l for l in ledger2.read_text(encoding="utf-8").splitlines() if l]) == 0,
            f"ledger2={ledger2.stat().st_size if ledger2.exists() else 0}B")

    # ---------- ④ 真出域实体调用前（egress 允许）指纹缓存仍拦重费 ----------
    # 用 MISS/HIT 已覆盖；此处再验：egress 允许但预算闸置 0 拦截
    zero = VisionClient(cfg, egress_allow=True,
                        budget=BudgetGate(cfg, {GLM_CHANNEL: 0.0}),
                        cache=VisionCache(tmp / "cache3", enabled=True),
                        ledger_path=str(tmp / "ledger" / "token3.jsonl"))
    try:
        zero.glm_parse_page(PAGE_PNG, page=1, doc_sha1=DOC_SHA1, render_reg=reg, raw_inject=fixture)
        t.check("预算闸 0 拦截", False, "未拦截")
    except VisionError as e:
        t.check("预算闸 0 拦截 budget_exceeded", e.kind == "budget_exceeded", f"kind={e.kind}")

    # ---------- ④ + ② 第二意见 strict schema ----------
    so_client = VisionClient(cfg, egress_allow=True, budget=BudgetGate(cfg),
                             cache=VisionCache(tmp / "cache4", enabled=True),
                             ledger_path=str(tmp / "ledger" / "token4.jsonl"))
    ok = so_client.second_opinion(PAGE_PNG, [0, 0, 50, 50], page=1, doc_sha1=DOC_SHA1,
                                  render_reg=reg, vendor="deepseek", raw_inject=_valid_so_response("deepseek"))
    t.check("④ 第二意见 schema 合法通过", ok["cache_hit"] is False and isinstance(ok.get("md"), str),
            f"cache_hit={ok['cache_hit']}")
    # ② 第二意见复跑 → 缓存命中零计费（同任务同bbox同渲染参数）
    ok2 = so_client.second_opinion(PAGE_PNG, [0, 0, 50, 50], page=1, doc_sha1=DOC_SHA1,
                                   render_reg=reg, vendor="deepseek", raw_inject=_valid_so_response("deepseek"))
    t.check("④ 第二意见缓存命中零计费", ok2.get("cache_hit") is True and ok2.get("cost_cny") == 0.0,
            f"cache_hit={ok2['cache_hit']} cost={ok2['cost_cny']}")
    bad = _valid_so_response("deepseek")
    bad["choices"][0]["message"]["content"] = json.dumps({"status": "ok"})   # 缺 data/rowspan 等
    try:
        # 用不同 bbox 使指纹为 MISS（避免命中共之前合法结果缓存而跳过 schema 校验）
        so_client.second_opinion(PAGE_PNG, [60, 0, 100, 50], page=1, doc_sha1=DOC_SHA1,
                                 render_reg=reg, vendor="deepseek", raw_inject=bad)
        t.check("④ 第二意见 schema 非法拒绝", False, "未拒绝")
    except VisionError as e:
        t.check("④ 第二意见 schema 非法拒绝 schema_invalid", e.kind == "schema_invalid", f"kind={e.kind}")
    # validate_second_opinion 直接单测
    t.check("④ validate_second_opinion 空违规",
            validate_second_opinion(json.loads(_valid_so_response("deepseek")["choices"][0]["message"]["content"])) == [])
    t.check("④ validate_second_opinion 检出缺失",
            len(validate_second_opinion({"status": "ok"})) > 0)
    # S6：schema_invalid 已计费仍落台账（账实相符）
    led4 = [json.loads(x) for x in (tmp / "ledger" / "token4.jsonl").read_text(encoding="utf-8").splitlines() if x]
    t.check("S6 schema_invalid 落台账", any(r.get("status") == "schema_invalid" for r in led4),
            f"n_rows={len(led4)}")

    # ---------- S 级修复锁定 ----------
    _u = {"prompt": 1000, "completion": 500}
    t.check("S1 qwen 独立计价（≠deepseek 峰谷价）",
            price_for(SECOND_OPINION_CHANNEL, _u, cfg, vendor="qwen") != price_for(SECOND_OPINION_CHANNEL, _u, cfg, vendor="deepseek"))
    t.check("S2 config 含 deepseek/qwen 端点",
            cfg["models"]["deepseek"]["endpoint"].startswith("https://api.deepseek.com")
            and cfg["models"]["qwen"]["endpoint"].startswith("https://dashscope"))
    _bg = BudgetGate(cfg)
    t.check("S3 BudgetGate 读 cfg.budget 默认",
            _bg.limits[GLM_CHANNEL] == cfg["budget"]["glm_per_volume_cny"]
            and _bg.limits[SECOND_OPINION_CHANNEL] == cfg["budget"]["second_opinion_per_volume_cny"]
            and _bg.peak_cap_cny == cfg["budget"]["deepseek_peak_cap_cny"],
            f"limits={_bg.limits}")
    # S4：orchestrator 对任意 vision kind 均降级（断网/4xx/5xx/timeout 不崩溃）
    import orchestrator as _orc
    class _StubClient:
        def __init__(self, *a, **k):
            pass
        def glm_parse_page(self, *a, **k):
            raise VisionError("network", "mock 断网")
    old_client = _orc.VisionClient
    _orc.VisionClient = _StubClient
    try:
        _ordir = tmp / "s4"
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["orchestrator.py", "--page-image", str(PAGE_PNG), "--page", "1", "--out", str(_ordir)]
        try:
            _orc.main()
            # R-11：MS-1 模式降级 marker 统一落 out/work/marks（处理遗留 C-A3）
            t.check("S4 orchestrator 对 network 降级不崩溃", (_ordir / "work" / "marks" / "page_0001.json").exists(),
                    "network 降级标记写入 work/marks")
        except SystemExit:
            t.check("S4 orchestrator 对 network 降级不崩溃", False, "SystemExit（崩溃）")
        finally:
            _sys.argv = old_argv
    finally:
        _orc.VisionClient = old_client

    # ---------- 配置 + 密钥 ----------
    t.check("config.load_config 含 models.glm.endpoint",
            cfg["models"]["glm"]["endpoint"].startswith("https://open.bigmodel.cn"))
    keys = load_keys()
    t.check("load_keys 三厂商键字段", all(k in keys for k in ("zhipu", "dashscope", "deepseek")),
            f"zhipu={bool(keys['zhipu'])} dashscope={bool(keys['dashscope'])} deepseek={bool(keys['deepseek'])}")

    # ---------- ⑤ _glm_live 真跑路径（mock transport，零网络） ----------
    import vision_client as vc
    class FakeResp:
        def __init__(self, code, payload, text=""):
            self.status_code = code
            self._payload = payload
            self.text = text
        def json(self):
            return self._payload
    live_client = VisionClient(cfg, egress_allow=True, budget=BudgetGate(cfg),
                               cache=VisionCache(tmp / "cache5", enabled=True), keys=load_keys())
    # 成功（200）解析路径：patch 高层 _http_post_json
    def ok_post(*a, **k):
        return FakeResp(200, fixture.get("response"))
    with mock.patch.object(vc, "_http_post_json", ok_post):
        live = live_client._glm_live(PAGE_PNG)
    t.check("⑤ _glm_live 解析成功响应", live["http_status"] == 200
            and live["usage_extracted"] == {"prompt": 694, "completion": 84},
            f"usage={live['usage_extracted']}")
    # 5xx → 重试 → 200：patch 底层 requests.post（真实 _http_post_json 重试逻辑运行）
    calls = []
    def req_post(*a, **k):
        calls.append(k)
        return FakeResp(502, {}, "bad gateway") if len(calls) == 1 else FakeResp(200, fixture.get("response"))
    with mock.patch.object(vc.requests, "post", req_post):
        live2 = live_client._glm_live(PAGE_PNG)
    t.check("⑤ _glm_live 5xx 重试后成功", live2["http_status"] == 200 and len(calls) == 2,
            f"calls={len(calls)}")
    # 4xx：patch 底层 requests.post 返回 400（真实逻辑不重试）
    def bad4_post(*a, **k):
        return FakeResp(400, {}, "bad request")
    try:
        with mock.patch.object(vc.requests, "post", bad4_post):
            live_client._glm_live(PAGE_PNG)
        t.check("⑤ _glm_live 4xx 不重试", False, "未抛错")
    except vc.VisionError as e:
        t.check("⑤ _glm_live 4xx 不重试", e.kind == "http_4xx", f"kind={e.kind}")

    print(f"\nRESULT pass={t.pass_} fail={t.fail}")
    if t.fail:
        print("FAILED:", ", ".join(t.failures))
    return 0 if t.fail == 0 else 1


def _valid_so_response(vendor):
    """构造 OpenAI 兼容响应体（含 strict schema 的合法 content + usage）。
    second_opinion.raw_inject 期望的是 OpenAI response body（choices/usage）。"""
    content = json.dumps({
        "status": "ok",
        "data": {"rows": [["0.45", "非燃烧体"]]},
        "rowspan": {"1_0": 2}, "colspan": {},
        "header_rows": [0], "confidence": 0.95, "issues": [],
    }, ensure_ascii=False)
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 60}}


if __name__ == "__main__":
    sys.exit(main())
