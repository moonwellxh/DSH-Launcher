# 模型价格系数表（pricing-models.md）

> 本文件是**说明文＋唯一一个 ```json 代码块**。脚本只解析该 JSON 块（规避 Markdown 解析脆弱性），维护者不得新增第二个 json 代码块。
> λ = cache_hit ÷ cache_miss。输出价＝未命中输入价 ×3，永不打折。
> **归一化费用公式：费用 = 输出token×3 ＋ 未命中输入token×1 ＋ 命中输入token×λ（单位：未命中输入价）**。
> 峰谷窗口按模型行读取（`days`/`windows`）；换算固定 Asia/Shanghai（UTC+8），不依赖宿主时区与 tz 数据库。
> 由 sediment_run.py S4 每 >30 天提示核对一次官方定价后更新 `updated_at` 与各行数值。

```json
{
  "updated_at": "2026-09-05",
  "currency": "CNY/1M tokens",
  "timezone": "Asia/Shanghai",
  "models": [
    {"id": "deepseek-v4-flash", "cache_hit": 0.10, "cache_miss": 3.0, "output": 9.0,
     "peak": {"days": "weekday", "windows": [["09:00","12:00"],["14:00","18:00"]]},
     "offpeak_factor": 0.5},
    {"id": "deepseek-v4-pro", "cache_hit": 0.30, "cache_miss": 9.0, "output": 27.0,
     "peak": {"days": "weekday", "windows": [["09:00","12:00"],["14:00","18:00"]]},
     "offpeak_factor": 0.5},
    {"id": "default", "cache_hit": null, "cache_miss": null, "output": null,
     "lambda_assumed": 0.0333,
     "note": "未识别模型按 DeepSeek 比例估算并明示"}
  ]
}
```

字段说明：`cache_hit`/`cache_miss`/`output` 单位 CNY/1M tokens；`peak.days` 取值 `weekday|weekend|*`（`weekday`＝周一至周五），`windows` 为闭区间时段 `[HH:MM, HH:MM]`；`offpeak_factor` 为闲时输入折扣系数（提示用，不参与 λ 计算）。`default` 行供模型识别失败时兜底：`lambda_assumed = 0.0333 ≈ 1/30`。
