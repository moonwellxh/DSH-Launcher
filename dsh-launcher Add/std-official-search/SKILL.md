---
name: std-official-search
description: 国家标准官方源直连检索。触发词：查标准/查国标/规范状态/现行废止/GB 检索/标准号/标准全文/采标/替代关系/行业标准/标准官方来源。
version: 1.0.0
---

# std-official-search：国家标准官方源直连检索

从官方平台直接取**权威真值**，不给模型编造机会：

| 场景 | 命令 |
|---|---|
| 权威状态登记（GB 库：多版本/现行/废止/即将实施并列） | `powershell -File assets\std-search.ps1 -Mode samr -Query "GB/T 14253"` |
| openstd 全文库检索（返回 hcno） | `... -Mode openstd -Query "电动自行车" -Status PUBLISHED` |
| 元数据详情（是否收录/可否预览下载） | `... -Mode info -Hcno <32位hex>` |
| openstd 全文扫描页图（尽力而为） | `... assets\openstd-pages.ps1 -Hcno <32位hex> [-OutDir dir]` |

输出 UTF-8 JSON（`rows[]`：std_code/name/state/date/hcno/source/note）；控制台 ASCII 摘要、中文走文件。

**边界（防误导）**：samr/openstd 只覆盖 GB 库与 openstd 收录范围（非工程建设 GB5xxxx、食安环保）；工程建设/行标(JGJ、DL)/团标/企标状态真值在各归口平台 → 用 AnySearch `web_search`(site:) + `web_fetch` 核验，**不得**凭记忆断言现行/废止。全文拿到 PDF/页图后如需解析→调用 **`pdf-parse-v3`** 技能。

## 环境与测试
- 依赖：curl.exe（系统自带）。
- 测试：`tests\run-tests.ps1`（语法 3 项 + 官方源实网冒烟 3 项，网络失败自动 SKIP）。
- PDF 解析/结构化（含产出 JSON 的标准）→ 用 **`pdf-parse-v3`** 技能。
- 与 `pdf-parse-v3` 拆分自原 `gb-standard-direct`（2026-09）。

## 故障
| 症状 | 处理 |
|---|---|
| openstd 全文图档全被拦 | pages.json 里 viewer_url 浏览器手动打开 |
| samr/openstd 0 命中 | 编号带分隔符（GB/T 14253）或按名称搜；工程/行业类见上文边界 |
