#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M4 vision_client.py —— 唯一出域点（FR-A2/FR-D4/FR-D5/FR-D7/FR-E6）
=================================================================
职责（设计书 §6.4 / 粗架构 §3.1）：
  * GLM 整页解析        ：glm_parse_page        （layout_parsing，页图 full_page）
  * GLM 裁剪重译        ：glm_reparse_crop      （FR-D4，crop_retranslate）
  * 第二意见窄任务      ：second_opinion        （vendor=deepseek/qwen，narrow_task，
                            strict JSON Schema 校验，不合即 schema_invalid 判失败）
  * KD6 指纹缓存        ：cache_fingerprint（§4.3 定稿，防跨区域/跨任务/重试误命中）
  * usage 台账          ：append_token_ledger（逐调用 prompt/completion/cache_hit/cost/peak）
  * 分通道预算闸        ：BudgetGate（glm 主通道 / second_opinion 复核通道独立累计）

设计依据：详细技术设计 §3.3/§4.1/§4.2/§4.3/§6.4/§10。
诚实声明：本模块为 MS-1 骨架，`_narrow_task_prompt` 为模板（版本号随 config.prompt_version.narrow_task），
         真正窄任务 prompt 在 MS-3 以试点册台账封闭化后定型；strict schema 校验按 FR-D4 全字段实现。
"""
import base64
import hashlib
import json
import os
import sys
import threading
import time
import unicodedata
from pathlib import Path

import requests

# ---------------------------------------------------------------- 常量与异常

VISION_KINDS = {
    "network", "http_4xx", "http_5xx", "timeout", "schema_invalid",
    "output_length_exceeded", "budget_exceeded", "no_key", "egress_blocked",
}

# 任务类型闭集（KD6 缓存指纹隔离维度之一）
TASK_FULL_PAGE = "full_page"
TASK_CROP = "crop_retranslate"
TASK_NARROW = "narrow_task"

GLM_CHANNEL = "glm"
SECOND_OPINION_CHANNEL = "second_opinion"

USER_KEY_FILE = Path.home() / ".config" / "pdf-parse-v3" / "keys.json"

# GLM 单图输入上限（需求书 §10；超限走 render 降采样，M2，MS-1 只用其记账常量）
DEFAULT_MAX_IMAGE_BYTES = 10485760

# 并发纪律（v1.3，2026-09-27）：出域通道改有界并发后，下列共享状态必须加锁。
_LEDGER_LOCK = threading.Lock()      # token 台账逐行追加（防交错/半行）
_CACHE_LOCK = threading.Lock()       # 指纹缓存写入（同指纹并发写防半文件）
# 429 退避序列：索引 i 为第 i 次重试前的等待。默认 max_retries=3 → 实际只经历
# 1s、3s 两档（9s 档需 max_retries>=4；文档据此更正，勿再写"1s/3s/9s"为实际序列）。
_RETRY_429_BACKOFFS = [1.0, 3.0, 9.0]
_RETRY_AFTER_MAX_S = 60.0             # m3 修复：Retry-After 上限，防单次退避睡满小时级


class VisionError(Exception):
    """视觉调用失败（异常码语义见设计书 §10）。kind 为闭集枚举。"""

    def __init__(self, kind, detail="", degrade_hint=None):
        if kind not in VISION_KINDS:
            raise ValueError(f"unknown vision kind: {kind!r}")
        self.kind = kind
        self.detail = detail or ""
        self.degrade_hint = degrade_hint
        super().__init__(f"[{kind}] {self.detail}")


# ---------------------------------------------------------------- 密钥读取（只读）

def load_keys():
    """密钥读取，只读用户级配置目录（需求书 Q12-3 / §8 数据出域条款）。
    优先级：环境变量 > 用户级 keys.json（zhipu/dashscope/deepseek）。
    系统绝不写回 keys.json。路径：%USERPROFILE%\\.config\\pdf-parse-v3\\keys.json
    （keys.local.json 为 shootout 旧通道，本模块不读取，避免密钥散落工作区外；保留环境变量通道。）"""
    keys = {
        "zhipu": os.environ.get("ZHIPU_API_KEY"),
        "dashscope": os.environ.get("DASHSCOPE_API_KEY"),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
    }
    if USER_KEY_FILE.exists():
        try:
            local = json.loads(USER_KEY_FILE.read_text(encoding="utf-8"))
        except Exception:
            local = {}
        for k in ("zhipu", "dashscope", "deepseek"):
            keys[k] = keys[k] or (local.get(k) if isinstance(local, dict) else None)
    return keys


# ---------------------------------------------------------------- 数据 URI / 工具

def data_uri(png: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(png).read_bytes()).decode()


def _sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def sha1_or_none(text):
    """FR-D8 定向重试的 failure-feedback 哈希载体（§4.3 retry.feedback_sha1）。"""
    if not text:
        return None
    return _sha1_bytes(text.encode("utf-8"))


def _norm_num(tok: str) -> str:
    return unicodedata.normalize("NFKC", tok or "").replace(",", "").replace("，", "").strip()


# ---------------------------------------------------------------- KD6 缓存指纹（§4.3 定稿）

def cache_fingerprint(*, doc_sha1: str, page: int, task_type: str,
                      bbox, render_reg: dict, model: str,
                      prompt_ver: str, retry: dict) -> str:
    """KD6 定稿指纹。task_type ∈ {full_page, crop_retranslate, narrow_task}；
    bbox: 整页为 None，裁剪重译/窄任务为像素系 [x1,y1,x2,y2]（已含 pad）；
    retry: {"seq":0, "feedback_sha1":null} —— FR-D8 定向重试携带失败原因反馈时
    seq=1 且 feedback_sha1 为反馈哈希，保证重试不命中首次缓存。
    以 PDF 内容 sha1 + 页图内容哈希（render.render_sha1）为要素，不以路径/mtime 为要素。"""
    payload = {
        "doc": doc_sha1,
        "page": page,
        "task": task_type,
        "bbox": bbox,
        "render": {
            "dpi": render_reg.get("dpi"),
            "pixel": render_reg.get("pixel"),
            "img": render_reg.get("render_sha1"),
        },
        "model": model,
        "prompt": prompt_ver,
        "retry": {"seq": retry.get("seq", 0), "feedback_sha1": retry.get("feedback_sha1")},
    }
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 缓存布局

class VisionCache:
    """work/cache/<channel>/<task_type>/<fingerprint>.json。
    条目 = 完整原始响应 + 首跑台账行；命中零计费返回（usage=null）。"""

    def __init__(self, cache_dir, enabled=True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled

    def _path(self, channel, task_type, fp) -> Path:
        return self.cache_dir / channel / task_type / f"{fp}.json"

    def get(self, channel, task_type, fp):
        if not self.enabled:
            return None
        p = self._path(channel, task_type, fp)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def put(self, channel, task_type, fp, raw_response, first_run_ledger):
        if not self.enabled:
            return
        p = self._path(channel, task_type, fp)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {"raw_response": raw_response, "first_run_ledger": first_run_ledger}
        with _CACHE_LOCK:                  # v1.3：同指纹并发写防半文件
            p.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    def raw_or_none(self, channel, task_type, fp):
        e = self.get(channel, task_type, fp)
        return e.get("raw_response") if e else None


# ---------------------------------------------------------------- 价格与峰谷判定

def _is_peak(ts, cfg) -> bool:
    """按调用时刻判定 DeepSeek 是否高峰档（工作日 9–12/14–18）。"""
    dsk = cfg["models"]["deepseek"]
    if not dsk.get("peak_weekdays_only", True):
        return False
    try:
        t = time.localtime(ts)
        if t.tm_wday >= 5:            # 周末全天空闲
            return False
        for lo, hi in dsk.get("peak_hours", []):
            if lo <= t.tm_hour < hi:
                return True
    except Exception:
        return False
    return False


def price_for(channel, usage, cfg, *, ts=None, cache_hit=False, vendor=None):
    """台账换算：cost = (prompt×price_in + completion×price_out)/1e6。
    DeepSeek：按峰谷档选价；缓存命中时以 cache_hit_in_*（¥0.10/¥0.05）替代 price_in。
    Qwen（复核通道 vendor=qwen）：按 flat 价格（¥0.15/M 入、¥1.5/M 出），不复用 deepseek 价。"""
    if not usage:
        return None
    p = usage.get("prompt", 0) or 0
    c = usage.get("completion", 0) or 0
    if channel == GLM_CHANNEL:
        m = cfg["models"]["glm"]
        pin, pout = m["price_in"], m["price_out"]
    elif channel == SECOND_OPINION_CHANNEL:
        if vendor == "qwen":
            m = cfg["models"]["qwen"]
            pin, pout = m["price_in"], m["price_out"]
        else:  # deepseek（默认）——峰谷 + 缓存命中档
            m = cfg["models"]["deepseek"]
            peak = _is_peak(ts if ts is not None else time.time(), cfg)
            if cache_hit:
                pin = m["cache_hit_in_peak"] if peak else m["cache_hit_in_offpeak"]
            else:
                pin = m["price_in_peak"] if peak else m["price_in_offpeak"]
            pout = m["price_out_peak"] if peak else m["price_out_offpeak"]
    else:
        raise ValueError(f"unknown channel: {channel}")
    return round((p * pin + c * pout) / 1e6, 6)


def peek_channel_peak(cfg, ts=None) -> bool:
    return _is_peak(ts if ts is not None else time.time(), cfg)


# ---------------------------------------------------------------- 分通道预算闸

class BudgetGate:
    """分通道预算累计（Q13/FR-D5）。limit=None 表示不设限。
    cfg['budget'] 提供默认（glm_per_volume_cny / second_opinion_per_volume_cny /
    deepseek_peak_cap_cny）；参数集中化，CLI 可经 limits 覆盖。
    deepseek_peak_cap_cny：DeepSeek 复核通道高峰累计封顶，超限自动降级（Q13）。"""

    def __init__(self, cfg, limits=None):
        self.cfg = cfg
        b = cfg.get("budget", {}) or {}
        self.limits = {
            GLM_CHANNEL: b.get("glm_per_volume_cny", 1.0),
            SECOND_OPINION_CHANNEL: b.get("second_opinion_per_volume_cny", 1.0),
        }
        if limits:
            self.limits.update(limits)
        self.costs = {GLM_CHANNEL: 0.0, SECOND_OPINION_CHANNEL: 0.0}
        self.blocked = set()
        self._lock = threading.RLock()     # v1.3：并发下 check/register 原子化（RLock：register 内调 check）
        self.peak_cap_cny = b.get("deepseek_peak_cap_cny")   # None=未设默认（Q13 仅要求可配）
        self.peak_spent_cny = 0.0

    def check(self, channel, *, peak=False) -> bool:
        with self._lock:
            lim = self.limits.get(channel)
            if lim is not None and self.costs[channel] >= lim:
                return False
            if channel == SECOND_OPINION_CHANNEL and peak and self.peak_cap_cny is not None:
                if self.peak_spent_cny >= self.peak_cap_cny:
                    return False
            return True

    def why_blocked(self, channel, *, peak=False):
        """L2（2026-09-27）：返回阻塞原因 'channel_limit' | 'peak_cap' | None。
        旧实现只回 bool，确认提示一律写"预算超限"——峰谷封顶触发时会误报原因。"""
        with self._lock:
            lim = self.limits.get(channel)
            if lim is not None and self.costs[channel] >= lim:
                return "channel_limit"
            if channel == SECOND_OPINION_CHANNEL and peak and self.peak_cap_cny is not None:
                if self.peak_spent_cny >= self.peak_cap_cny:
                    return "peak_cap"
            return None

    def peak_usage(self):
        """峰谷封顶用量（供确认提示如实展示）。"""
        with self._lock:
            return {"spent": self.peak_spent_cny, "cap": self.peak_cap_cny}

    def register(self, channel, cost, *, peak=False):
        """累计并判定封顶。v1.3 并发注：加锁保证累计不丢（无 lost update）；
        但 check（调用前）与 register（调用后）之间仍有窗口，窗口长度≈单次调用时长，
        **同时在窗口内的调用数即超限调用数**：并发 N 下最多 N 次调用可同时通过 check 而
        尚未 register，故超限上界为 N×单次调用成本；N=1（旧串行行为）亦有 1×单次成本
        的窗口，并非零。该界已写入详细技术设计 §6.4（m1 更正）。"""
        with self._lock:
            self.costs[channel] = round(self.costs.get(channel, 0.0) + (cost or 0.0), 6)
            if channel == SECOND_OPINION_CHANNEL and peak:
                self.peak_spent_cny = round(self.peak_spent_cny + (cost or 0.0), 6)
            if not self.check(channel, peak=peak):
                self.blocked.add(channel)
            elif channel == SECOND_OPINION_CHANNEL and self.peak_cap_cny is not None \
                    and self.peak_spent_cny >= self.peak_cap_cny:
                self.blocked.add(channel)

    def summary(self):
        with self._lock:
            return {k: {"cost": self.costs[k], "limit": self.limits.get(k), "blocked": k in self.blocked}
                    for k in self.costs}


# ---------------------------------------------------------------- token 台账

def append_token_ledger(rec, ledger_path):
    """逐调用落盘 token 台账（FR-D5）。rec = {ts, channel, task_type, page, bbox,
    prompt, completion, cache_hit, cost_cny, peak, ...}。"""
    lp = Path(ledger_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER_LOCK:                     # v1.3：并发下保证整行写入不交错
        with lp.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- HTTP（可注入以便离线测试）

def _retry_after_seconds(resp):
    """解析 Retry-After（仅秒数形态；HTTP-date 形态忽略，返回 None）。
    m3 修复：加**上限** `_RETRY_AFTER_MAX_S`——否则服务器给 Retry-After: 3600
    会让单次退避睡 1 小时（timeout 只管单次请求，管不到退避时长）。"""
    try:
        v = resp.headers.get("Retry-After")
        if v is None:
            return None
        return min(_RETRY_AFTER_MAX_S, max(0.0, float(str(v).strip())))
    except Exception:
        return None


def _http_post_json(model_key, url, headers, body, *, timeout=300, max_retries=3):
    """网络/5xx/timeout 指数退避 ≤3 次（0.5s/2s/8s）；**429 可重试**
    （退避 1s/3s/9s，服务器给出 Retry-After 时取其较大值；退避耗尽仍按 http_4xx 抛错走 FR-D7 降级）；
    其余 4xx 不重试（FR-D5 限流纪律，v1.3 修订 2026-09-27）。"""
    backoffs = [0.5, 2.0, 8.0]
    last_err = None
    for i in range(max_retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 429:          # 限流：并发引入后必须退避重试
                last_err = VisionError("http_4xx",
                                       f"{model_key} HTTP 429 (rate limited): {r.text[:300]}")
                if i < max_retries - 1:
                    wait = _RETRY_429_BACKOFFS[min(i, len(_RETRY_429_BACKOFFS) - 1)]
                    ra = _retry_after_seconds(r)
                    time.sleep(wait if ra is None else max(wait, ra))
                    continue
                raise last_err
            if 400 <= r.status_code < 500:
                raise VisionError("http_4xx", f"{model_key} HTTP {r.status_code}: {r.text[:300]}")
            if r.status_code >= 500:
                last_err = VisionError("http_5xx", f"{model_key} HTTP {r.status_code}: {r.text[:300]}")
                # 5xx 可重试
                if i < max_retries - 1:
                    time.sleep(backoffs[i])
                    continue
                raise last_err
            last_err = VisionError("http_5xx", f"{model_key} HTTP {r.status_code}")
        except VisionError as e:
            raise
        except requests.exceptions.Timeout:
            last_err = VisionError("timeout", f"{model_key} timeout after {timeout}s")
            if i < max_retries - 1:
                time.sleep(backoffs[i])
                continue
        except requests.exceptions.RequestException as e:
            last_err = VisionError("network", f"{model_key} network: {e}")
            if i < max_retries - 1:
                time.sleep(backoffs[i])
                continue
    raise last_err or VisionError("network", f"{model_key} failed")


# ---------------------------------------------------------------- 各厂商原始响应提取

def _extract_glm(resp: dict):
    """GLM layout_parsing 响应 → (md, blocks, page_size, usage)。"""
    md = resp.get("md_results") or ""
    blocks_raw = resp.get("layout_details") or []
    blocks = []
    for page_blocks in blocks_raw:
        if not isinstance(page_blocks, list):
            continue
        for b in page_blocks:
            if not isinstance(b, dict):
                continue
            bb = b.get("bbox_2d") or [0, 0, 0, 0]
            blocks.append({
                "bbox_2d": [int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])],
                "native_label": b.get("native_label") or b.get("label") or "text",
                "content": b.get("content") or "",
                "content_ref": b.get("content_ref") or ("inline" if not tables_in(b.get("content") or "") else "inline"),
            })
    page_size = None
    di = resp.get("data_info") or {}
    pages = di.get("pages") or []
    if pages:
        p0 = pages[0]
        page_size = {"width": int(p0.get("width", 0)), "height": int(p0.get("height", 0))}
    u = resp.get("usage") or {}
    usage = {"prompt": int(u.get("prompt_tokens", 0) or 0),
             "completion": int(u.get("completion_tokens", 0) or 0)}
    return md, blocks, page_size, usage


def tables_in(s: str) -> bool:
    return "<table" in (s or "")


def _extract_openai(resp: dict, model_key: str):
    """OpenAI 兼容 chat/completions 响应 → (content, usage)。
    finish_reason==length 或空 content 且已计费 → 抛 output_length_exceeded（FR-D6）。"""
    try:
        choice = resp["choices"][0]
    except Exception:
        raise VisionError("schema_invalid", f"{model_key}: 无 choices")
    finish = choice.get("finish_reason")
    msg = choice.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(x.get("text", "") for x in content if isinstance(x, dict))
    content = (content or "").strip()
    u = resp.get("usage") or {}
    usage = {"prompt": int(u.get("prompt_tokens", 0) or 0),
             "completion": int(u.get("completion_tokens", 0) or 0)}
    if finish == "length" or (not content and (usage["prompt"] or usage["completion"])):
        raise VisionError("output_length_exceeded", f"{model_key}: finish_reason={finish} content空且已计费",
                          degrade_hint="status=unreadable, reason=output_length_exceeded")
    return content, usage


# ---------------------------------------------------------------- 第二意见 strict schema（FR-D4）

SECOND_OPINION_SCHEMA_KEYS = ("status", "data", "rowspan", "colspan", "header_rows", "confidence", "issues")


def validate_second_opinion(obj) -> list:
    """strict JSON Schema 校验（FR-D4）。返回违规清单；空=通过。
    字段：status/data/rowspan/colspan/header_rows/confidence/issues。"""
    problems = []
    if not isinstance(obj, dict):
        problems.append("root 非 object")
        return problems
    if obj.get("status") not in ("ok", "failed"):
        problems.append(f"status ∈ {{ok,failed}}，得 {obj.get('status')!r}")
    data = obj.get("data")
    if data is None or not isinstance(data, dict):
        problems.append("data 缺失或非 object")
    else:
        rows = data.get("rows")
        if rows is None:
            problems.append("data.rows 缺失")
        else:
            if not isinstance(rows, list):
                problems.append("data.rows 非 list")
            else:
                for r in rows:
                    if not isinstance(r, list) or not all(isinstance(x, str) for x in r):
                        problems.append("data.rows 元素非 list[str]")
                        break
        rs = obj.get("rowspan")
        cs = obj.get("colspan")
        for name, v in (("rowspan", rs), ("colspan", cs)):
            if v is None:
                pages_problem = False
            elif not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(x, int) for k, x in v.items()):
                problems.append(f"{name} 非 {str}->{int} dict")
        hr = obj.get("header_rows")
        if hr is not None and (not isinstance(hr, list) or not all(isinstance(x, int) for x in hr)):
            problems.append("header_rows 非 list[int]")
        conf = obj.get("confidence")
        if conf is not None and not isinstance(conf, (int, float)):
            problems.append("confidence 非 number")
        iss = obj.get("issues")
        if iss is not None and (not isinstance(iss, list) or not all(isinstance(x, str) for x in iss)):
            problems.append("issues 非 list[str]")
    return problems


# ---------------------------------------------------------------- 窄任务 prompt 模板（版本号治理）

def _narrow_task_prompt(task: dict, prompt_ver: str) -> str:
    """第二意见窄任务 prompt。task = {type, target:{rows/cols}}。
    版本号 prompt_ver 由 config.prompt_version.narrow_task 治理。MS-1 为骨架，MS-3 定型。"""
    rows = (task.get("target") or {}).get("rows") or []
    cols = (task.get("target") or {}).get("cols") or []
    ttype = task.get("type", "row-transcribe")
    return (
        f"你是表格复核器（prompt_ver={prompt_ver}）。请只转写图中指定"
        + (f"行 {rows} " if rows else "") + (f"列 {cols} " if cols else "")
        + f"的文本，任务类型={ttype}。\n"
        '严格输出 JSON（不要任何 JSON 以外的文字）：{"status":"ok|failed","data":{"rows":[[str]]},'
        '"rowspan":{"r_c":int},"colspan":{"r_c":int},"header_rows":[int],"confidence":number|null,"issues":[str]}'
    )


# ---------------------------------------------------------------- 主客户端

def _parse_obj(md):
    """md（content JSON 字符串）→ dict；不可解析/空返回 {}。"""
    if not md:
        return {}
    try:
        obj = json.loads(md)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _merge_so_result(obj, base):
    """把窄任务解析对象（status/data/...）叠到 M4 结果上，满足 §3.1 second_opinion 契约。"""
    out = dict(base)
    if isinstance(obj, dict):
        for k in ("status", "data", "rowspan", "colspan", "header_rows", "confidence", "issues"):
            if k in obj:
                out[k] = obj[k]
    return out


class VisionClient:
    """M4 视觉客户端。唯一出域点。config + 密钥加载后构造一次。"""

    def __init__(self, cfg, *, keys=None, ledger_path="work/ledger/token.jsonl",
                 cache=None, budget=None, egress_allow=None, no_cache=False,
                 budget_confirm=None):
        self.cfg = cfg
        self.keys = keys if keys is not None else load_keys()
        self.ledger_path = ledger_path
        en = cfg.get("cache", {}).get("enabled", True)
        cd = cfg.get("cache", {}).get("dir", "work/cache")
        self.cache = cache if cache is not None else VisionCache(cd, enabled=(en and not no_cache))
        self.budget = budget if budget is not None else BudgetGate(cfg)
        # egress_allow 默认取 config.egress.allow；None 表示用配置值，False 即 --no-egress 短路
        self.egress_allow = egress_allow if egress_allow is not None else bool(cfg.get("egress", {}).get("allow", True))
        self.no_cache = no_cache
        # #4（2026-09-27）：预算超限不再静默降级——由编排层注入确认回调；None=旧行为
        self.budget_confirm = budget_confirm
        # S-1 修复（2026-09-27）：确认闸必须有状态机 + 互斥
        self._budget_lock = threading.Lock()
        # L2：放行按 **原因** 记账——{channel: {"channel_limit"/"peak_cap"}}；
        # 旧实现按通道记账，一次"继续"会连带豁免峰谷封顶（提示里也没披露）
        self._budget_ok_exceed = {}
        self._budget_refused = set()        # 已明确"停止该通道"的通道（本运行不再问、直接降级）

    # ---- 出域闸门 ----
    def _check_egress(self):
        if not self.egress_allow:
            raise VisionError("egress_blocked", "--no-egress: 禁止出域",
                              degrade_hint="FR-D7: 本地管线 + 诚实标记")

    # ---- 通道前置（egress + 预算，含 deepseek 峰谷封顶）----
    def _precall(self, channel):
        self._check_egress()
        peak = peek_channel_peak(self.cfg) if channel == SECOND_OPINION_CHANNEL else False
        if self.budget.check(channel, peak=peak):
            return
        # S-1：check→询问→落状态 三步必须原子；否则并发下会重复弹问、且拒绝不被记忆。
        # 持锁期间会阻塞同通道其它线程——这正是"只问一次"所需（它们在等同一次决策）。
        with self._budget_lock:
            if self.budget.check(channel, peak=peak):      # 双检：等锁期间可能已放行/已累计
                return
            reason = self.budget.why_blocked(channel, peak=peak) or "budget"   # L2：如实区分
            if reason in self._budget_ok_exceed.get(channel, set()):
                return                                     # L2：只豁免**同一原因**
            if channel in self._budget_refused:            # 已选"停止该通道"：不再问，直接降级
                raise VisionError("budget_exceeded",
                                  f"{channel} 预算超限（用户已选择停止该通道；reason={reason}）",
                                  degrade_hint=f"degraded:{channel} budget_exceeded")
            if self.budget_confirm is not None:
                pu = self.budget.peak_usage()
                allow = None
                try:
                    allow = bool(self.budget_confirm(
                        channel=channel, reason=reason,
                        spent=self.budget.costs.get(channel),
                        limit=self.budget.limits.get(channel), peak=peak,
                        peak_spent=pu["spent"], peak_cap=pu["cap"]))
                except Exception as e:      # S-1：回调失败＝未获答复 → 不记忆、不静默
                    allow = None
                    try:
                        sys.stderr.write("WARN: 预算确认回调失败（%s: %s），按 FR-D7 降级且不记忆\n"
                                         % (type(e).__name__, e))
                    except Exception:
                        pass
                if allow is True:
                    self._budget_ok_exceed.setdefault(channel, set()).add(reason)   # L2
                    return
                if allow is False:
                    self._budget_refused.add(channel)      # S-1：明确的拒绝才记忆
        raise VisionError("budget_exceeded", f"{channel} 预算超限（reason={reason}, peak={peak}）",
                          degrade_hint=f"degraded:{channel} budget_exceeded")

    def _model_of(self, channel):
        if channel == GLM_CHANNEL:
            return self.cfg["models"]["glm"]["model"]
        # second_opinion vendor 通过 model 选择（deepseek 或 qwen）
        return None

    def _glm_endpoint(self) -> str:
        return self.cfg["models"]["glm"]["endpoint"]

    def _api_key_for(self, vendor):
        name = {"deepseek": "deepseek", "qwen": "dashscope", "zhipu": "zhipu"}.get(vendor, vendor)
        key = self.keys.get(name)
        if not key:
            raise VisionError("no_key", f"缺 {vendor} 密钥（{name.upper()}），无法出域",
                              degrade_hint="FR-D7: 视该通道降级")
        return key

    # ---- 统一结果结构（S5：含 blocks/http_status/latency_s，符合 §3.1 M4 契约）----
    def _result_of(self, channel, fp, raw, *, cache_hit, usage=None, cost=None):
        http_status = raw.get("http_status") if isinstance(raw, dict) else None
        latency_s = raw.get("latency_s") if isinstance(raw, dict) else None
        return {"cache_hit": cache_hit, "usage": usage, "cost_cny": cost,
                "raw_response": raw, "fingerprint": fp,
                "md": self._md_of(channel, raw), "page_size": self._page_size_of(channel, raw),
                "blocks": self._blocks_of(channel, raw),
                "http_status": http_status, "latency_s": latency_s}

    # ---- 缓存命中（B1：先于真实出域调用；零计费、不出域、不耗预算）----
    def _cached_result(self, channel, task_type, fp, *, page, bbox):
        if self.no_cache:
            return None
        cached = self.cache.raw_or_none(channel, task_type, fp)
        if cached is None:
            return None
        led = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "channel": channel,
               "task_type": task_type, "page": page, "bbox": bbox,
               "prompt": None, "completion": None, "cache_hit": True, "cost_cny": 0.0,
               "peak": peek_channel_peak(self.cfg)}
        append_token_ledger(led, self.ledger_path)
        return self._result_of(channel, fp, cached, cache_hit=True, usage=None, cost=0.0)

    # ---- MISS：真实调用后落台账/预算/缓存（约定已确认为 MISS）----
    def _finalize_miss(self, channel, task_type, fp, out, *, model, page, bbox, vendor=None):
        usage = out.get("usage_extracted") if isinstance(out, dict) else None
        if not usage:
            usage = self._usage_of(channel, out)
        peak = peek_channel_peak(self.cfg)
        cost = price_for(channel, usage, self.cfg, ts=time.time(), cache_hit=False,
                         vendor=vendor) if usage else None
        led = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "channel": channel,
               "task_type": task_type, "page": page, "bbox": bbox,
               "prompt": usage.get("prompt") if usage else None,
               "completion": usage.get("completion") if usage else None,
               "cache_hit": False, "cost_cny": cost if cost is not None else None,
               "peak": peak, "latency_s": out.get("latency_s"), "http_status": out.get("http_status"),
               "t_start": out.get("t_start"), "t_end": out.get("t_end"),        # L4
               "model": model, "vendor": vendor}
        append_token_ledger(led, self.ledger_path)
        self.budget.register(channel, cost or 0.0, peak=peak)
        self.cache.put(channel, task_type, fp, out, led)
        return self._result_of(channel, fp, out, cache_hit=False, usage=usage, cost=cost)

    # ---- 已计费但结果不落盘的调用（S6：schema_invalid 仍记账，账实相符）----
    def _record_billed(self, channel, task_type, fp, out, *, model, page, bbox, vendor=None, status):
        usage = out.get("usage_extracted") if isinstance(out, dict) else None
        if not usage:
            usage = self._usage_of(channel, out)
        peak = peek_channel_peak(self.cfg)
        cost = price_for(channel, usage, self.cfg, ts=time.time(), cache_hit=False,
                         vendor=vendor) if usage else None
        led = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "channel": channel,
               "task_type": task_type, "page": page, "bbox": bbox,
               "prompt": usage.get("prompt") if usage else None,
               "completion": usage.get("completion") if usage else None,
               "cache_hit": False, "cost_cny": cost if cost is not None else None,
               "peak": peak, "latency_s": out.get("latency_s"), "http_status": out.get("http_status"),
               "t_start": out.get("t_start"), "t_end": out.get("t_end"),        # L4
               "model": model, "vendor": vendor, "status": status}
        append_token_ledger(led, self.ledger_path)
        self.budget.register(channel, cost or 0.0, peak=peak)

    # ---- blocks（S5：GLM layout_details → 块列表；§3.1 契约字段）----
    def _blocks_of(self, channel, raw):
        resp = raw.get("response") if isinstance(raw, dict) else {}
        if channel == GLM_CHANNEL and isinstance(resp, dict):
            blocks = []
            for page_blocks in (resp.get("layout_details") or []):
                for b in (page_blocks or []):
                    if not isinstance(b, dict):
                        continue
                    bb = b.get("bbox_2d") or [0, 0, 0, 0]
                    blocks.append({"bbox_2d": [int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])],
                                   "native_label": b.get("native_label") or b.get("label") or "text",
                                   "content": b.get("content") or "",
                                   "content_ref": "inline"})
            return blocks
        return []

    def _glm_live(self, png_path):
        """GLM 整页/裁剪真实出域调用：data URI → layout_parsing。返回统一 out dict。"""
        self._check_egress()
        body = {"model": self.cfg["models"]["glm"]["model"], "file": data_uri(png_path)}
        t0 = time.time()
        r = _http_post_json("glm", self._glm_endpoint(),
                            {"Authorization": f"Bearer {self._api_key_for('zhipu')}",
                             "Content-Type": "application/json"}, body)
        dt = round(time.time() - t0, 2)
        out = {"http_status": r.status_code, "latency_s": dt,
               "t_start": round(t0, 3), "t_end": round(time.time(), 3)}      # L4
        try:
            out["response"] = r.json()
        except Exception:
            out["response_text"] = r.text[:4000]
        resp = out.get("response") or {}
        if isinstance(resp, dict):
            u = resp.get("usage") or {}
            out["usage_extracted"] = {"prompt": int(u.get("prompt_tokens", 0) or 0),
                                      "completion": int(u.get("completion_tokens", 0) or 0)}
        return out

    def _md_of(self, channel, raw):
        resp = raw.get("response") if isinstance(raw, dict) else {}
        if channel == GLM_CHANNEL:
            return (resp.get("md_results") or "") if isinstance(resp, dict) else ""
        # OpenAI 通道：content 即 md/转写，block 结构不含 md
        if isinstance(raw, dict):
            resp2 = raw.get("response") or {}
            try:
                return resp2["choices"][0]["message"]["content"] or ""
            except Exception:
                return ""
        return ""

    def _page_size_of(self, channel, raw):
        resp = raw.get("response") if isinstance(raw, dict) else {}
        if channel == GLM_CHANNEL and isinstance(resp, dict):
            di = resp.get("data_info") or {}
            pages = di.get("pages") or []
            if pages:
                return {"width": int(pages[0].get("width", 0)), "height": int(pages[0].get("height", 0))}
        return None

    def _usage_of(self, channel, raw):
        resp = raw.get("response") if isinstance(raw, dict) else {}
        if isinstance(resp, dict):
            u = resp.get("usage") or {}
            return {"prompt": int(u.get("prompt_tokens", 0) or 0),
                    "completion": int(u.get("completion_tokens", 0) or 0)}
        return None

    # ---------- 公开操作 ----------

    def glm_parse_page(self, png_path, *, page, doc_sha1, render_reg,
                       task_type=TASK_FULL_PAGE, bbox=None, retry=None,
                       model=None, cache=True, raw_inject=None) -> dict:
        """GLM 整页解析。png_path → data URI → layout_parsing。
        render_reg = {dpi, pixel:[w,h], render_sha1}（§3.2 变换登记要素，随调用传入）。
        B1：缓存优先——命中即零计费返回，不出域、不耗预算；仅 MISS 才真实出域。"""
        model = model or self.cfg["models"]["glm"]["model"]
        # L4 修正：full_page 用独立稳定版本串（GLM layout_parsing 无本地窄任务 prompt）；crop 用 crop_hint
        prompt_ver = self.cfg.get("prompt_version", {}).get("full_page", "glm-layout-1.0") \
            if task_type == TASK_FULL_PAGE else self.cfg.get("prompt_version", {}).get("crop_hint", "ch-1.0")
        retry = retry or {"seq": 0, "feedback_sha1": None}
        fp = cache_fingerprint(doc_sha1=doc_sha1, page=page, task_type=task_type,
                               bbox=bbox, render_reg=render_reg, model=model,
                               prompt_ver=prompt_ver, retry=retry)
        hit = self._cached_result(GLM_CHANNEL, task_type, fp, page=page, bbox=bbox)
        if hit is not None:
            return hit
        self._precall(GLM_CHANNEL)
        out = raw_inject if raw_inject is not None else self._glm_live(png_path)
        return self._finalize_miss(GLM_CHANNEL, task_type, fp, out,
                                   model=model, page=page, bbox=bbox)

    def glm_reparse_crop(self, png_path, bbox, *, page, doc_sha1, render_reg,
                         hint=None, retry=None, raw_inject=None) -> dict:
        """GLM 裁剪重译（FR-D4）。bbox=像素系 [x1,y1,x2,y2]（设计书 crop_png 输出）。
        hint 在 GLM layout_parsing 端点无 prompt 通道，MS-3（M8）再定义如何携带失败原因反馈。"""
        return self.glm_parse_page(png_path, page=page, doc_sha1=doc_sha1, render_reg=render_reg,
                                   task_type=TASK_CROP, bbox=bbox, retry=retry,
                                   raw_inject=raw_inject)

    def second_opinion(self, png_path, bbox, *, page, doc_sha1, render_reg,
                       vendor="deepseek", task=None, retry=None, raw_inject=None) -> dict:
        """第二意见窄任务（FR-D4）。vendor=deepseek/qwen；strict schema 校验；
        不合即 schema_invalid 判失败（不回写结果表，但 S6：已计费仍记台账/预算）。
        缓存优先；D3 终裁通道。"""
        if vendor not in ("deepseek", "qwen"):
            raise ValueError(f"vendor must be deepseek/qwen, got {vendor!r}")
        channel = SECOND_OPINION_CHANNEL
        model = self.cfg["models"]["deepseek"]["model"] if vendor == "deepseek" \
            else self.cfg["models"]["qwen"]["model"]
        prompt_ver = self.cfg.get("prompt_version", {}).get("narrow_task", "nt-1.0")
        task = task or {"type": "row-transcribe", "target": {"rows": [], "cols": []}}
        prompt = _narrow_task_prompt(task, prompt_ver)
        retry = retry or {"seq": 0, "feedback_sha1": None}
        fp = cache_fingerprint(doc_sha1=doc_sha1, page=page, task_type=TASK_NARROW,
                               bbox=bbox, render_reg=render_reg, model=model,
                               prompt_ver=prompt_ver, retry=retry)
        hit = self._cached_result(channel, TASK_NARROW, fp, page=page, bbox=bbox)
        if hit is not None:
            return _merge_so_result(_parse_obj(hit.get("md")), hit)   # §3.1 契约：返回含 status/data
        self._precall(channel)
        if raw_inject is not None:
            out = {"http_status": 200, "latency_s": 0.0, "response": raw_inject,
                   "usage_extracted": self._usage_of(channel, {"response": raw_inject}),
                   "vendor": vendor}
        else:
            try:
                out = self._call_openai(model, data_uri(png_path), prompt, vendor)
            except VisionError as e:
                if e.kind == "output_length_exceeded":
                    # FR-D6 爆破：仍已计费 → 记台账（账实相符），不回写结果
                    e_out = getattr(e, "_out", None)
                    if e_out:
                        self._record_billed(channel, TASK_NARROW, fp, e_out, model=model, page=page,
                                            bbox=bbox, vendor=vendor, status="output_length_exceeded")
                    raise
                raise
        # strict schema 校验（先于 _finalize_miss；不合则 S6 记账后判失败）
        content = self._md_of(channel, out)
        try:
            obj = json.loads(content) if content else {}
        except Exception as e:
            self._record_billed(channel, TASK_NARROW, fp, out, model=model, page=page,
                                bbox=bbox, vendor=vendor, status="schema_invalid")
            raise VisionError("schema_invalid", f"JSON 解析失败: {e}")
        probs = validate_second_opinion(obj)
        if probs:
            self._record_billed(channel, TASK_NARROW, fp, out, model=model, page=page,
                                bbox=bbox, vendor=vendor, status="schema_invalid")
            raise VisionError("schema_invalid", "第二意见输出不合 strict schema: " + ";".join(probs))
        base = self._finalize_miss(channel, TASK_NARROW, fp, out,
                                   model=model, page=page, bbox=bbox, vendor=vendor)
        return _merge_so_result(obj, base)     # §3.1 契约：返回含 status/data 等

    # ---------- 内部：GLM / OpenAI 注入与调用 ----------

    def _call_openai(self, model, b64uri, prompt, vendor):
        vcfg = self.cfg["models"]["deepseek"] if vendor == "deepseek" else self.cfg["models"]["qwen"]
        endp = vcfg.get("endpoint") or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        key = self._api_key_for(vendor)
        max_tokens = vcfg.get("max_tokens", 4096 if vendor == "deepseek" else 12000)
        body = {"model": model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": b64uri}},
                    {"type": "text", "text": prompt},
                ]}],
                "max_tokens": max_tokens,
                "temperature": 0}
        t0 = time.time()
        r = _http_post_json(f"{vendor}/{model}", endp,
                            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
        out = {"http_status": r.status_code, "latency_s": round(time.time() - t0, 2),
               "t_start": round(t0, 3), "t_end": round(time.time(), 3)}      # L4
        try:
            out["response"] = r.json()
        except Exception:
            out["response_text"] = r.text[:4000]
        # 先提取 usage（即使 length 截断也能记账；FR-D5 以实测 usage 为准）
        resp_u = (out.get("response") or {}).get("usage") if isinstance(out.get("response"), dict) else {}
        out["usage_extracted"] = {"prompt": int(resp_u.get("prompt_tokens", 0) or 0),
                                  "completion": int(resp_u.get("completion_tokens", 0) or 0)} if resp_u else None
        try:
            _, usage = _extract_openai(out["response"], f"{vendor}/{model}")
            out["usage_extracted"] = usage
        except VisionError as e:
            if e.kind == "output_length_exceeded":
                e._out = out            # 携带 usage 供 second_opinion 记账（FR-D6 爆破仍入台账）
                raise
            out["usage_extracted"] = None
        return out


# ---------------------------------------------------------------- CLI 自检（可选，不出域）

def _load_default_config(base):
    p = Path(base) / "assets" / "v4" / "config.default.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    """简单自检：加载 config + 密钥，打印 keys 有无与预算闸初始态（不出域）。"""
    base = Path(__file__).resolve().parents[2]   # .../pdf-parse-v3
    cfg = _load_default_config(base)
    keys = load_keys()
    bg = BudgetGate(cfg)
    print(json.dumps({"keys": {k: bool(v) for k, v in keys.items()},
                      "budget": bg.summary()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
