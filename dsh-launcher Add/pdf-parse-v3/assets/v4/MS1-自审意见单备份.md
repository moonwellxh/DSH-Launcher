# MS-1 产物 —— 自审意见单（A 回退备份）

> **用途说明**：本文件是我的**自审回退备份**（对应裁决选项 A），仅当用户从选项 B 切换为 A 时生效。用户当前选择为 **B（继续等待独立子审查者）**，故本备份不作为阶段 2 的正式门禁——正式门禁以独立子审查者产出为准（其正在运行中）。本备份与独立审查并行、互不覆盖，供用户决策参考。

- 审查对象：`assets/v4/config.default.json`、`assets/v4/vision_client.py`、`assets/v4/orchestrator.py`、`tests/v4/test_ms1_smoke.py`、`assets/v4/MS1-G008-自证声明.md`
- 交叉依据：详细技术设计 §1.2/§2.4/§3.3/§4.1-4.3/§6.4/§6.12/§10；需求书 Q12-13/FR-D5/D7/FR-G2/G4/§8/§10
- 结论先行：**阻断 0 / 严重 0 / 轻微 6 / 建议 2**；五出口全「已覆盖」高置信。MS-1 骨架满足设计契约。

## 阻断
无。

## 严重
无。

## 轻微
| # | anchor | basis | confidence | 说明 |
|---|---|---|---|---|
| L-1 | vision_client.py:574-575 | 设计书 §4.2 prompt_version 仅 {narrow_task,crop_hint}（无 full_page）；§4.3 prompt_ver 应为稳定指纹判别量 | 高 | `glm_parse_page` 对 `TASK_FULL_PAGE` 复用 `prompt_version.narrow_task`（nt-1.0）。整页 GLM layout_parsing 无本地 prompt 模板，复用窄任务版本号语义不准确。建议全页用独立稳定串（如固定 `glm-layout-default`），避免与窄任务模板版本耦合。 |
| L-2 | vision_client.py:298 | 函数未被调用（走 `_glm_live`+`_dispatch` + `_md_of/_usage_of`） | 高 | `_extract_glm` 为死代码。可删（或保留为工具并注明）。 |
| L-3 | vision_client.py:450 | 同上（`_dispatch` 已移除 `_call`） | 高 | `_model_of` 未被调用，死代码。 |
| L-4 | vision_client.py:387 | validate_second_opinion 逻辑 | 中 | `pages_problem=False` 赋值后未使用（死变量）；rowspan/colspan 校验分支有冗余。 |
| L-5 | vision_client.py:632 | 设计书 §4.2 deepseek 无 max_tokens 键 | 高 | `_call_openai` 对 `vendor=deepseek` 也取 `models.qwen.max_tokens`；跨 vendor 参数串用。建议 deepseek 用自身 max_tokens 或 fallback 值。 |
| L-6 | vision_client.py:583 | 设计书 §7.3.2 glm_reparse_crop(hint=...)；§4.3 retry.feedback_sha1 | 中 | `glm_reparse_crop` 接受 `hint` 但未用于出域调用（GLM layout_parsing 端点仅 model+file，无 prompt 通道）。MS-1 保留字段；MS-3（M8 裁剪重译）需明确 hint/失败原因反馈如何携带（retry.feedback_sha1 已承载其一）。 |

## 建议
| # | anchor | basis | confidence | 说明 |
|---|---|---|---|---|
| S-1 | vision_client.py `_dispatch` | 冗余 | 中 | `glm_parse_page`/`second_opinion` 与 `_dispatch` 各调一次 `_precall`（egress+budget 重复检查）。非错误，但可简化为单一前置。 |
| S-2 | vision_client.py `_dispatch` HIT 行 | 审计 | 中 | HIT 台账行建议显式带 `model`/`task_type`（已含 task_type/channel/page），确认审计字段完备。 |

## MS-1 五出口判据覆盖核验（自审）
| 出口 | 判定 | 证据 | confidence |
|---|---|---|---|
| ① 单页 GLM 解析通 + 原始响应落盘 | 已覆盖 | MISS/HIT 两次调用；raw_response 含 md_results/usage；写至 out/glm/page_0001.json；断言含 md_chars>0 | 高 |
| ② 台账逐调用落盘 | 已覆盖 | token.jsonl 两行；MISS 行含 prompt/completion/cache_hit/cost_cny；HIT 行 cache_hit=true cost=0 | 高 |
| ③ 缓存命中零计费 + 隔离不变式 | 已覆盖 | 复跑 HIT cost=0 usage=null；指纹隔离 bbox/task/retry_seq/dpi/pixel/img_hash/doc/model/prompt/task_narrow 全变即异 | 高 |
| ④ --no-egress 短路三厂商有测试 | 已覆盖 | glm_parse_page + second_opinion(deepseek) + second_opinion(qwen) 均抛 egress_blocked；ledger 0 增 | 高 |
| ⑤ 最小闭环（黄金夹具/真实页） | 已覆盖 | page_0001.png（真实页图）+ page_0001.json（真实原始响应）离线重放 MISS→HIT；外加 _glm_live mock 真跑路径（200/5xx重试/4xx不重试） | 高 |

## 与 G-008 自证的呼应
本自审确认 G-008 中「契约级未实现清单」如实（M2/M6/M7/M8/M9/M10/M11/M13/M14 未实现，仅接口层占位）；未发现超出该清单的未实现项。所有轻微项均为非功能阻性（死代码/参数语义/跨 vendor 常量），不涉及「偏离设计契约」「破坏五出口」。
