# MS-1 阶段产物（Phase 1）增量复审意见单

- 复审对象（本轮改动后全文）：`assets/v4/vision_client.py`、`assets/v4/config.default.json`、`assets/v4/orchestrator.py`、`tests/v4/test_ms1_smoke.py`
- 交叉依据（只读定向行区间）：`docs/详细技术设计.md` §4.2/§4.3/§6.4/§6.12、`docs/需求确定书.md` FR-D5/FR-D7/Q12-13/§10、`docs/技术设计文档.md` §3.1
- 权威上轮意见单：`MS1-审查意见单.md`（1 阻断 B1 + 6 严重 S1-S6；轻微/建议归档）
- 复审口径：干净上下文独立子审查，只审「改动 + 关联」，冻结区不重审；逐条核对 7 项是否真正修复、是否引入新阻断/严重。
- 诚实声明：本机无可用 Python 解释器（`python`/`py`/WindowsApps stub 均不可用，exit 9009），**未独立执行** `test_ms1_smoke.py`；「43 处 t.check 全 PASS」为改动方主张，我逐行清点断言并核对了夹具 `tests/vision_shootout/results/batch/page_0001.json`（顶层含 http_status=200、latency_s=0.93、response.md_results/layout_details/usage 齐备），未实跑复验 exit 码。

---

## 一、7 项逐条判定

### B1 缓存命中不阻断真实出域 —— 已修复
- anchor: `vision_client.py:631-633`（`glm_parse_page` 先 `_cached_result` 命中即 return，早于 `_precall`）、`vision_client.py:664-666`（`second_opinion` 同）、`vision_client.py:496-507`（`_cached_result` 写 cache_hit=True/usage=None/cost=0 台账，不调 `budget.register`，直接 `_result_of` 返回）
- basis: 需求书 FR-D5「按指纹缓存、重跑不重复计费」+ 详细设计 §4.3-1「命中即零计费返回」——缓存查询已前移到出域闸/预算闸之前，命中零计费、不出域、不耗预算；未命中才 `_precall`(egress+预算) 后真实出域。
- confidence: 高

### S1 qwen 按 deepseek 价计费 —— 已修复
- anchor: `vision_client.py:200-211`（`price_for` 在 `SECOND_OPINION_CHANNEL` 下 `vendor=="qwen"` 取 qwen flat 价，else 走 deepseek 峰谷/缓存档）、`vision_client.py:515-516`/`535-536`（`_finalize_miss`/`_record_billed` 均透传 `vendor`）
- basis: 需求书 §10（Qwen ¥0.15/¥1.5 与 DeepSeek 峰谷价不同）+ FR-D5 价格集中化——qwen 复核调用现按 qwen 刊例计价，台账/预算不再错价。
- confidence: 高

### S2 _call_openai 端点硬编码 —— 已修复
- anchor: `vision_client.py:693-694`（`vcfg` 按 vendor 取 `models.deepseek`/`models.qwen`，`endp=vcfg.get("endpoint")`）、`config.default.json:12`/`:24`（deepseek/qwen 增 `endpoint` 键）
- basis: 需求书 §10（DeepSeek 独立供应商）+ §8「供应商变更按参数集中化替换」——端点已参数化，vendor=deepseek 不再路由到阿里云 DashScope。
- confidence: 高

### S3 cfg.budget 三键死代码 —— 未修复（峰谷封顶执行路径缺失）
- anchor（已修复部分）: `vision_client.py:231-240`（`BudgetGate.__init__` 读 `cfg["budget"]` 三键，`glm_per_volume_cny`/`second_opinion_per_volume_cny` 入 `limits`、`deepseek_peak_cap_cny` 入 `peak_cap_cny`）
- anchor（未修复部分）: `vision_client.py:462-466`（`_precall` 仅 `self.budget.check(channel)`，未传 `peak`）、`vision_client.py:243-250`（`check` 的峰谷分支仅在 `peak=True` 时生效，且不读 `blocked`）、`vision_client.py:252-260`（`register` 的峰谷超限只 `blocked.add`，`check`/`_precall` 均不消费 `blocked`）
- basis: 需求书 Q13「DeepSeek 峰谷封顶可配置、**超限自动降级**」+ FR-D5——前两键（分通道预算上限）已生效；但 `deepseek_peak_cap_cny` 虽被读取并累计 `peak_spent_cny`，前置闸 `_precall` 从不以 `peak=True` 调 `check`，`blocked` 仅被 `summary()` 读取，故峰谷封顶没有任何拦截路径，超限不触发 `budget_exceeded`→FR-D7 降级。Q13 的「超限自动降级」仍落空。
- confidence: 高

### S4 orchestrator 仅捕 4 kind —— 已修复
- anchor: `orchestrator.py:144-150`（`except VisionError` 全 kind 捕获，`output_length_exceeded`→`unreadable`，其余→`degraded`，写 mark 后 `continue`）
- basis: 需求书 FR-D7「无 key/无额度/超预算/断网自动降级不阻塞全流程」——`network`/`timeout`/`http_4xx`/`http_5xx`/`no_key`/`budget_exceeded`/`egress_blocked` 均落降级标记不再崩溃（`VisionError.__init__` 闭集校验保证 kind 合法）。
- confidence: 高

### S5 返回缺 blocks/http_status/latency_s —— 已修复
- anchor: `vision_client.py:486-493`（`_result_of` 统一返回含 `blocks`/`http_status`/`latency_s`）、`vision_client.py:548-562`（`_blocks_of` 由 `layout_details` 提取块）
- basis: 技术设计文档 §3.1 M4 契约（`md/blocks/page_size/usage/cache_hit/http_status/latency_s`）——三字段已由 `_result_of` 统一接入，`glm_parse_page`/`glm_reparse_crop`/`second_opinion` 均经此返回；`http_status`/`latency_s` 取自 out 顶层，夹具 `http_status=200/latency_s=0.93` 可过断言。
- confidence: 高

### S6 schema_invalid 不落台账/预算 —— 已修复
- anchor: `vision_client.py:678-686`（JSON 解析失败或 `validate_second_opinion` 违规 → `_record_billed` 后 `raise schema_invalid`）、`vision_client.py:530-545`（`_record_billed` 写台账含 `status=schema_invalid` 并 `budget.register`）
- basis: 需求书 FR-D5「台账以实测 usage 为准」——真跑已计费的 schema 非法响应现落入台账与复核预算闸，账实相符；不写缓存（非法结果不入 `cache.put`，正确）。
- confidence: 高

---

## 二、新阻断/严重确认

- **本轮新引入阻断：0；本轮新引入严重：0。**
- 核对清单（均无新增问题）：
  - 缓存优先跳过 schema 校验：**无**——schema_invalid 路径在 `_finalize_miss`/`cache.put` 之前 raise，缓存只存已通过校验的结果，命中即返回的是既往合法响应，不会漏校验。
  - 端点/价格串错：**无**——`_call_openai` 按 vendor 选 vcfg/endpoint/max_tokens，`price_for` 按 vendor 分价，`_api_key_for` 映射 deepseek→deepseek、qwen→dashscope 均一致。
  - 降级吞错：**无**——orchestrator 捕获的全部 `VisionError` kind 均属 FR-D7 降级面；非视觉异常（ValueError/KeyError）仍正常传播。

---

## 三、残留 / 关联严重（非本轮新引入，属「改动+关联」范围，建议进入修复循环）

#### [严重-残留-1] S3 峰谷封顶未执行（`deepseek_peak_cap_cny` 读取但「超限自动降级」不生效）
- anchor: `vision_client.py:462-466` + `vision_client.py:243-250` + `vision_client.py:252-260`
- basis: 需求书 Q13——键已读、`peak_spent_cny` 已累计，但 `_precall` 从不带 `peak` 调 `check`，`register` 的超限仅写 `blocked` 且无任何消费方，封顶判定与降级链路完全未接线。属 S3 未完全关闭（前两键已闭环，第三键只读不执行）。
- confidence: 高

#### [严重-关联-2] output_length_exceeded 已计费调用仍不落台账/预算（S6 同类账实不符）
- anchor: `vision_client.py:712-718`（`_call_openai` 捕获 `output_length_exceeded` 直接 `raise`，未走 `_record_billed`）、`vision_client.py:366-368`（`_extract_openai` 在 finish==length 或空 content 且 usage 存在时抛）
- basis: 需求书 FR-D5「台账含每页 prompt/completion」+ FR-D6「且已计费」——真跑已计费的截断/空输出调用，usage 随异常直接丢失，既不进台账也不进复核预算闸；与 S6 同属「已计费未记账」。**非本轮引入**（旧实现同样在 `_dispatch` 前抛），但位于本轮重写的 `second_opinion` 计费路径内，S6 修复未覆盖此同类路径。
- confidence: 中

---

## 四、轻微 / 建议（归档，非本复审焦点）

#### [轻微-1] `--no-egress` 下缓存命中仍返回云端历史结果（B1 修复副作用）
- anchor: `vision_client.py:631-633`（缓存查询先于 `_check_egress`）、`vision_client.py:456-459`、`orchestrator.py:124`
- basis: 需求书 §8「敏感文档强制本地路径」/「纯本地管线」——缓存查询前移到 egress 闸之前后，`--no-egress` + 同文档指纹已命中缓存时返回既往云端解析结果，与「全阻断/纯本地」语义有张力；仅当该文档先前已出域缓存时触发，无实际出域/计费。
- confidence: 中

#### [轻微-2] S5 返回的 `blocks[]` 条目缺契约 `label` 字段
- anchor: `vision_client.py:557-560`（块条目只含 `bbox_2d`/`native_label`/`content`/`content_ref`）
- basis: 技术设计文档 §3.1 契约块 `{bbox_2d, label, native_label, content}`——顶层三键已补，块内 `label` 未补（GLM 响应本含 `label` 字段）。
- confidence: 中

#### [建议-1] S3 测试仅断言「读入」，未测峰谷封顶 gate 执行
- anchor: `tests/v4/test_ms1_smoke.py:247-252`（只比对 `limits`/`peak_cap_cny` 与 `cfg["budget"]` 相等）
- basis: 需求书 Q13「超限自动降级」应有执行级断言——当前断言在 `deepseek_peak_cap_cny=null` 下恒真，是峰谷封顶缺陷漏网的原因。
- confidence: 高

---

## 五、统计

- 7 项判定：**已修复 6**（B1、S1、S2、S4、S5、S6）；**未修复 1**（S3，峰谷封顶执行路径缺失）
- 本轮新引入：阻断 0；严重 0
- 残留/关联严重（非本轮新引入，改动+关联范围）：2（① S3 峰谷封顶未执行；② output_length_exceeded 已计费不落台账）
- 轻微：2；建议：1
