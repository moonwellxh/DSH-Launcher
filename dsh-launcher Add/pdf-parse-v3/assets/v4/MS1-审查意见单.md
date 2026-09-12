# MS-1 阶段产物（Phase 1）对抗性审查意见单

- 审查对象：`assets/v4/config.default.json`、`assets/v4/vision_client.py`、`assets/v4/orchestrator.py`、`tests/v4/test_ms1_smoke.py`、`assets/v4/MS1-G008-自证声明.md`
- 交叉依据：`docs/详细技术设计.md`、`docs/需求确定书.md`、`docs/技术设计文档.md`
- 审查方式：干净上下文独立子审查，仅基于上述文件全文与交叉依据逐条代码走查；已实体核验夹具 `tests/vision_shootout/results/batch/page_0001.json`（http_status=200、usage prompt=694/completion=84、md_results/layout_details 齐备）与 `tests/vision_shootout/batch_samples/page_0001.png` 均存在。
- 诚实声明：本轮为代码走查口径，**未独立执行** `test_ms1_smoke.py`；「35/35 PASS」为自证声明主张，经我逐行清点 `t.check` 调用点确为 35 处，断言内部自洽（cost=0.000156=(694×0.20+84×0.20)/1e6 四舍五入、prompt=694 取自 fixture），但未实跑复验 exit 码与零网络。

---

## 一、分级意见

### 阻断

#### [阻断-1] 指纹缓存查询发生在真实出域调用之后，真跑路径「缓存命中复跑零计费」落空，且命中时实测 usage 被丢弃致台账/预算少计
- anchor: `vision_client.py:576`（`glm_parse_page` 先 `inject = raw_inject if ... else self._glm_live(png_path)` 真实出域，再进 `_dispatch`）；`vision_client.py:602-607`（`second_opinion` 先 `out = raw_inject if ... else self._call_openai(...)` 真实出域）；`vision_client.py:477-486`（缓存查询 `raw_or_none` 与命中返回均在 `_dispatch` 内，晚于上述调用）
- basis: 需求书 FR-D5「按指纹缓存结果，重跑不重复计费」+ 详细设计 §4.3「命中即零计费返回」+ 粗架构 KD6——真跑（raw_inject=None）路径下，`_glm_live`/`_call_openai` 先发起并计费，`_dispatch` 才查缓存，命中仅做到「台账记 0、不记预算」，而非「不重复计费」；且命中分支（478-486）丢弃刚发生的实测 usage，违反 FR-D5「以实测 usage 为准」并令分通道预算少计。测试全程 `raw_inject` 绕过网络，未暴露此缺陷。
- confidence: 高

---

### 严重

#### [严重-1] `price_for` 未按 vendor 区分，qwen 第二意见调用按 DeepSeek 价格计费（台账/预算错价，qwen 价格键死代码）
- anchor: `vision_client.py:199-206`（`elif channel == SECOND_OPINION_CHANNEL` 分支恒取 `cfg["models"]["deepseek"]` 价格）+ `vision_client.py:589-590`（`second_opinion` 允许 `vendor="deepseek"/"qwen"`）+ `config.default.json:21-26`（`models.qwen.price_in/price_out` 全代码无读取）
- basis: 需求书 FR-D5「台账以实测 usage 为准、价格参数集中化」+ §10（Qwen ¥0.15/¥1.5 与 DeepSeek 峰谷价不同）——qwen 复核调用的 cost 会按 DeepSeek 峰谷价换算，台账与复核通道预算数值错误。
- confidence: 高

#### [严重-2] `_call_openai` 端点硬编码 DashScope，DeepSeek 第二意见路由到错误端点；deepseek/qwen 端点未参数化
- anchor: `vision_client.py:625`（`endp` 恒为 `dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，与 vendor 无关）+ `config.default.json:10-26`（`models.deepseek`/`models.qwen` 均无 `endpoint` 键）
- basis: 需求书 §10（DeepSeek 为独立供应商）+ §8「供应商变更按参数集中化替换」+ FR-D5 参数集中化——vendor=deepseek 真跑会把 deepseek key + 型号发往阿里云端点，key 与端点不匹配必失败；端点未入 config，无法按设计替换。
- confidence: 高

#### [严重-3] `config.budget.*` 三键完全未被读取，预算上限硬编码于代码，`deepseek_peak_cap_cny` 峰谷封顶未实现
- anchor: `config.default.json:28-32`（`glm_per_volume_cny`/`second_opinion_per_volume_cny`/`deepseek_peak_cap_cny`）+ `vision_client.py:220-231`（`BudgetGate` 用硬编码 `DEFAULT_LIMITS`，`__init__` 从不读 `cfg["budget"]`，全文无 `cfg["budget"]` 取键）
- basis: 需求书 FR-D5「参数集中化（…预算上限）」+ Q13（复核通道独立上限、DeepSeek 峰谷封顶可配置超限自动降级）+ 详细设计 §4.1「config.user.json 用户级覆盖」/§6.12——config 声明的预算参数是死键，用户级覆盖预算不生效，峰谷封顶判定与超限降级完全缺失。
- confidence: 高

#### [严重-4] orchestrator 降级仅捕获 4 种 kind，断网/无额度(4xx)/5xx/timeout 会未捕获崩溃，违反 FR-D7
- anchor: `orchestrator.py:144-151`（`if e.kind in ("egress_blocked","budget_exceeded","no_key","output_length_exceeded")` 之外一律 `raise`）
- basis: 需求书 FR-D7「视觉不可用时（无 key/无额度/超预算/断网）自动降级、不阻塞全流程」——`network`/`timeout`/`http_4xx`（含额度耗尽 429/402）/`http_5xx`/`schema_invalid` 均不在捕获清单，会未捕获传播导致整次运行崩溃、不落降级标记。
- confidence: 高

#### [严重-5] `glm_parse_page` 返回结构缺 `blocks`/顶层 `http_status`/`latency_s`，不符粗架构 §3.1 M4 契约
- anchor: `vision_client.py:484-486`、`vision_client.py:510-512`（`_dispatch` 返回键为 `cache_hit/usage/cost_cny/raw_response/fingerprint/md/page_size`）+ 对比 `docs/技术设计文档.md:432-438`（契约含 `md/blocks/page_size/usage/cache_hit/http_status/latency_s`）
- basis: 技术设计文档 §3.1 M4 契约签名——返回缺 `blocks`（`_extract_glm` 存在但无任何调用点，块级坐标提取未接线）、`http_status`/`latency_s` 被下沉到 `raw_response`；此形状偏差未列入自证声明「契约级未实现清单」。
- confidence: 中（`raw_response` 落盘保留 layout_details，可后置再生，故不阻断 MS-1 但属契约偏离）

#### [严重-6] `second_opinion` 的 schema_invalid 路径先于 `_dispatch` 抛错，真实计费不入台账/预算
- anchor: `vision_client.py:609-616`（schema 校验失败即 `raise VisionError("schema_invalid", …)`，先于 617 行 `_dispatch`）+ `vision_client.py:498-508`（台账落盘与 `budget.register` 均在 `_dispatch` 内）
- basis: 需求书 FR-D5「台账以实测 usage 为准、含每页 prompt/completion tokens」——真跑路径 `_call_openai` 已计费，schema 非法直接抛错，本次 usage 既不进台账也不进复核预算闸，形成真实资金账实不符（设计 §10「不回写」指不回写结果表，不豁免台账）。
- confidence: 中

---

### 轻微

#### [轻微-1] 缓存路径 channel 用 `second_opinion`，与 §4.3 规定 `{glm,deepseek,qwen}` 不符
- anchor: `vision_client.py:42`（`SECOND_OPINION_CHANNEL="second_opinion"`）+ `vision_client.py:143-144`（`_path`）+ 详细设计 §4.3-1（`docs/详细技术设计.md:234`「channel ∈ {glm, deepseek, qwen}」）
- basis: 本设计 §4.3 缓存布局纪律规定 channel 取厂商名——deepseek/qwen 缓存现落 `work/cache/second_opinion/narrow_task/…`，channel 语义与 §4.3 冲突（隔离由指纹 model 维度兜底，非阻断）。
- confidence: 高

#### [轻微-2] `_extract_glm` 的 `content_ref` 恒为 `"inline"`（同值三元），且 `_extract_glm`/`_model_of` 为死代码
- anchor: `vision_client.py:314`（`("inline" if not tables_in(...) else "inline")` 两分支同值）+ `vision_client.py:298-325`（`_extract_glm` 无调用）+ `vision_client.py:450-454`（`_model_of` 无调用）
- basis: 详细设计 §5.3 `blocks[].content_ref ∈ {inline|table:N|image:N}`——该分支永无法产出 `table:N/image:N`，函数未接线，属未完成残留。
- confidence: 高

#### [轻微-3] 重试退避 `8.0s` 永不触发，实际最多 2 次重试
- anchor: `vision_client.py:262-264`（`max_retries=3` + `backoffs=[0.5,2.0,8.0]`，循环 3 次仅 2 次 sleep）
- basis: 详细设计 §6.4「网络/5xx/timeout 指数退避 ≤3 次（0.5s/2s/8s）」与自证声明 D8 同口径——现实现 3 次尝试=2 次重试，第三档 8s 为死值。
- confidence: 高

#### [轻微-4] `_is_peak` 对 `peak_weekdays_only=false` 语义反转（恒返回非高峰）
- anchor: `vision_client.py:172-186`（175 行 `if not dsk.get("peak_weekdays_only", True): return False`）
- basis: config 默认 `peak_weekdays_only:true` 下行为正确；该开关为 false 时逻辑等价「永不高峰」，与「仅工作日高峰」语义相反，边界未定义（本设计 §4.2 只给 true、未定义 false 语义）。
- confidence: 中

#### [轻微-5] `_call_openai` 对 deepseek 也读取 `qwen.max_tokens`（跨厂商配置串扰）
- anchor: `vision_client.py:632`（`"max_tokens": self.cfg["models"]["qwen"].get("max_tokens", 12000)`，不分 vendor）+ `config.default.json:10-20`（`models.deepseek` 无 `max_tokens`）
- basis: 需求书 FR-D5 参数集中化与厂商隔离——deepseek 请求被注入 qwen 的 max_tokens，deepseek 截断上限未参数化。
- confidence: 高

#### [轻微-6] `price_for` 的 cache_hit 价格档为死代码；DeepSeek API 级 `cached_tokens` 未提取、未按缓存价计
- anchor: `vision_client.py:202-203`（cache_hit 分档定价，唯一调用点 496 行恒传 `cache_hit=False`）+ `vision_client.py:557-563`（`_usage_of` 不提取 `prompt_tokens_details.cached_tokens`）
- basis: 需求书 §10（DeepSeek 缓存命中 ¥0.10/¥0.05）+ FR-D5——KD6 本地缓存命中恒零成本与 DeepSeek API 级缓存命中是两回事；后者未实现 token 提取，API 返回的缓存 token 会按全价计入，账实不符。
- confidence: 高

#### [轻微-7] `_call_openai` 的 `latency_s` 恒为 0.0
- anchor: `vision_client.py:636`（`out = {"http_status": r.status_code, "latency_s": 0.0}`）对比 `vision_client.py:518-522`（`_glm_live` 有真实计时）
- basis: 详细设计 §4.3（首跑台账行含 latency）——第二意见台账 latency 恒 0，数据失真。
- confidence: 高

#### [轻微-8] GLM 通道台账的 `peak` 字段误用 DeepSeek 峰谷判定
- anchor: `vision_client.py:482`、`vision_client.py:504`（对 GLM 通道 ledger 也写 `"peak": peek_channel_peak(self.cfg, …)`，该函数内部取 deepseek 峰谷档）
- basis: 台账字段语义一致性——GLM 无峰谷定价，peak 字段对 GLM 通道无意义且具误导性。
- confidence: 中

#### [轻微-9] `_http_post_json` 对 2xx(非200)/3xx 误标为 `http_5xx` 且无退避重试
- anchor: `vision_client.py:280`（非 200 且 <400 落入 `last_err = VisionError("http_5xx", …)`，无 sleep 直接进入下一轮循环）
- basis: 详细设计 §6.4 异常面闭集 kind 语义须准确——301/302/204 等会被误标 5xx 并连重 3 次无退避。
- confidence: 中

#### [轻微-10] `validate_second_opinion` 不强制 rowspan/colspan/header_rows/confidence/issues 必填（「strict 全字段」不符）
- anchor: `vision_client.py:383-398`（上述字段为 `None` 即通过，仅 `status` 与 `data.rows` 必填）
- basis: 详细设计 §6.4「status/data/rowspan/colspan/header_rows/confidence/issues 全字段」+ 需求书 FR-D4——缺 rowspan/colspan/confidence 等字段的响应会被判通过，与 strict schema 全字段语义不符。
- confidence: 中

#### [轻微-11] `glm_parse_page` 的 full_page 指纹绑定 `narrow_task` 版号（prompt 维度语义错配）
- anchor: `vision_client.py:574-575`（`task_type==TASK_FULL_PAGE` 取 `prompt_version.narrow_task`，crop 取 `crop_hint`）
- basis: 详细设计 §4.3（prompt 维度各任务独立版本）——full_page 走 layout_parsing 本无窄任务 prompt，却以 narrow_task 版号入指纹，MS-3 窄任务 prompt 定型改版会误失效全部 full_page 缓存（浪费而非错误）。
- confidence: 中

#### [轻微-12] orchestrator 多 `--page-image` 配单 `--page` 时复用同一页号，后续页图被断点静默跳过
- anchor: `orchestrator.py:95-96`（`--page-image` 为 append 可多个）+ `orchestrator.py:132`（`args.page` 单值，循环内所有页图共用 `n`）
- basis: CLI 正确性——传多页图且显式 `--page N` 时各图均以 N 处理，首图写盘后余图命中断点被静默跳过。
- confidence: 中

#### [轻微-13] 测试断言名「命中期…零计费」与其实为 MISS cost 校验不符
- anchor: `tests/v4/test_ms1_smoke.py:95-96`（名称含「命中期…零计费」，断言却是 `cache_hit is False and cost_cny==0.000156`）
- basis: 一致性（命名须反映断言）——该条实为验证首跑 MISS 的 cost 换算，名称误导（命中零计费真断言在 101-103 行）。
- confidence: 高

---

### 建议

#### [建议-1] 测试未端到端调用 `orchestrator.main()`，M12 的 CLI/断点/落盘/FR-D7 降级标记路径未被覆盖
- anchor: `tests/v4/test_ms1_smoke.py`（全文件仅 `orc.load_config`/`orc.build_render_reg`，无 `orc.main()` 调用）+ `orchestrator.py:92-156`（含 144-150 行降级标记、152-153 行落盘）
- basis: 详细设计 §12/粗架构 §10 MS-1 出口「原始响应落盘」应由编排层真实写盘验证——现「落盘」由测试 91-94 行手动 `write_text` 模拟，非执行 orchestrator 落盘路径。
- confidence: 高

#### [建议-2] `BudgetGate.check` 对未知 channel 直接索引会 KeyError，与 `register` 的 `.get` 兜底不一致
- anchor: `vision_client.py:237`（`self.costs[channel]` 直接索引）vs `vision_client.py:240`（`self.costs.get(channel, 0.0)`）
- basis: 异常面健壮性——未来新增通道时 `check` 先于 `register` 调用会抛 KeyError 而非返回 False。
- confidence: 中

#### [建议-3] `no_cache` 只禁读不禁写（显式注入 enabled 缓存 + `no_cache=True` 时 MISS 仍写缓存）
- anchor: `vision_client.py:478`（读判 `not self.no_cache`）vs `vision_client.py:509`（`self.cache.put` 无 no_cache 判断）
- basis: 代码边界一致性——默认路径（enabled 由 no_cache 派生）无碍，但显式注入 enabled 缓存时出现「读禁用、写启用」不一致。
- confidence: 中

#### [建议-4] `DEFAULT_MAX_IMAGE_BYTES`/`models.glm.max_image_bytes` 定义未用，>10MB 边界未在 MS-1 强制
- anchor: `vision_client.py:47` + `config.default.json:8`（全文零读取）
- basis: 需求书 §8（单页渲染图 >10MB 需降采样重渲染，仍超限诚实标记）——已声明 M2 处理，但常量与配置键目前是死代码。
- confidence: 高

#### [建议-5] `glm_parse_page` 的 `cache` 参数未使用（死参数）
- anchor: `vision_client.py:568`（签名 `cache=True`，函数体 570-580 未引用）
- basis: 代码正确性——参数名为 cache 却从不生效，调用方易误以为可开关缓存。
- confidence: 高

#### [建议-6] orchestrator 断点仅查 glm 输出文件，降级页（仅落 marks）重跑会重复出域计费
- anchor: `orchestrator.py:136-139`（断点判 `out/glm/page_N.json` 存在）vs `orchestrator.py:83-89`（降级仅落 `out/marks/page_N.json`）
- basis: 需求书 FR-G1 断点续跑/幂等——降级页无 glm 产物，重跑会被再次出域尝试，可能重复计费。
- confidence: 中

#### [建议-7] `build_render_reg` 缺 `scale`/`pdf_rect_pt`（FR-B2 坐标换算依赖 §3.3 scale）
- anchor: `orchestrator.py:65-78`（返回无 `scale`/`pdf_rect_pt`）+ `docs/详细技术设计.md:130-137`（`px_to_pt`/`pt_to_px` 依赖 `reg["scale"]`）
- basis: 需求书 FR-B2（坐标可换算）——属 M2 范围外且自证声明已明示，仅建议：M2 接入时须补齐，否则 FR-B2 无法验收。
- confidence: 高

---

## 二、MS-1 五出口判据覆盖核验

① 单页解析通 + 原始响应落盘 —— **部分覆盖**
- 证据：M4 层 MISS 返回 md/usage 已断言（`test_ms1_smoke.py:85-89`）；但「原始响应落盘」由测试 90-94 行手工 `write_text` 复刻，未走 `orchestrator.py:152-153` 真实写盘路径（`orchestrator.main()` 全程未被测试调用）。
- confidence: 高

② 台账逐调用落盘 —— **部分覆盖**
- 证据：MISS 行 prompt=694/completion/cost 全断言（`test_ms1_smoke.py:107-111`）；HIT 行零计费断言被三元短路（`test_ms1_smoke.py:112-114`，HIT 台账行 479-483 无 `usage` 键，`"usage" in led[1]` 恒 False → 只断言 `cache_hit is True`，`cost_cny==0.0` 与 `usage is None` 为死断言）。
- confidence: 高

③ 缓存命中零计费 + 隔离不变式 —— **部分覆盖**
- 证据：命中 `usage=None/cost=0` 真实断言（`test_ms1_smoke.py:101-103`）+ 10 变异与跨任务指纹隔离（126-142 行）覆盖 §4.3-2 不变式；**但零计费仅在 `raw_inject` 路径成立**，真跑路径缓存查询晚于真实出域调用（见 [阻断-1]），「重跑不重复计费」这一出口真意未被测试触及。
- confidence: 高

④ `--no-egress` 短路三厂商有测试 —— **部分覆盖**
- 证据：三入口（glm/deepseek/qwen）在 M4 层均抛 `egress_blocked`（`test_ms1_smoke.py:148-163`）、零台账断言（165 行）；但 CLI `--no-egress`→`egress_allow=False` 接线（`orchestrator.py:124`）未测试（测试直接构造 `egress_allow=False`），且「零网络」无 `requests.post` 未调用断言。
- confidence: 高

⑤ 最小闭环（黄金夹具或真实页）—— **部分覆盖**
- 证据：真实 `page_0001.json` + 真实 PNG 离线重放（`test_ms1_smoke.py:34-35,78-104`），`_glm_live` 用 `mock.patch` 走 200/5xx 重试/4xx 不重试（210-246 行），无真实 API 调用；但未端到端运行 `orchestrator.main()`，断点跳过、降级标记 `_marker`、页号推导 `_page_from_name`、`--page-image` 循环均无断言。
- confidence: 高

---

## 三、统计

- 阻断：1
- 严重：6
- 轻微：13
- 建议：7
