# PDF 解析输出 JSON 制作规范（Schema v3.0）

> 适用范围：**pdf-parse-v3** 等 PDF 解析（含扫描件 OCR 提取）产出的结构化 JSON；
> 触发词：PDF 转 JSON、分章节分条文、读扫描版规范。
> 版本：v3.0（锚点重构：以"准确表达 PDF 内容"为第一性原理）
> 日期：2026-09-04
> 历史：v1.0 初版 → v2.0 公理化+首次对抗审查 → **v3.0 内容模型重构**
> （原文件名《JSON制作规范.md》；随技能拆分并入 pdf-parse-v3 时改名以准确表达适用范围）

---

## 〇、第一性原理：准确表达 PDF 内容

### 0.1 锚点陈述

**JSON 的唯一使命：完整、忠实、可溯源地表达源 PDF 承载的内容。** 检索便利、结构美观、体积小巧都是派生目标；当它们与"准确表达"冲突时，一律让位。

### 0.2 由锚点推导的内容模型

PDF 任意一页的内容，按信息形态只有三类：

| 内容形态 | 例子 | v2.0 的表达 | 缺陷 |
|---------|------|------------|------|
| **文字** | 条文、说明、图说 | page_texts + articles | 条文与页码脱节，无法溯源 |
| **表格** | 防火分区面积表 | tables（顶层游离数组） | 丢了"表格属于哪一页"的位置关系 |
| **图** | 图集节点大样、图示 | **完全缺失** | 图集类 PDF 约半数信息在图上，等于没表达 |

由此得到 v3.0 的三条结构修正，全部服务于锚点：

1. **溯源闭环**：条文、章、图、表都必须带物理页码，任意内容可双向定位（内容→页、页→内容）。
2. **位置归位**：表格移回所属页内，图以"图说（caption）"形式入档——图集的核心检索词正是图号图名。
3. **类型显式**：新增文档类别声明，使用方（人或 AI）据此判断该查条文还是查图说，避免拿图集当规范检索条文。

### 0.3 保留的五条公理（v2.0 继承）

A1 忠实性 · A2 无损性 · A3 可验证性 · A4 幂等性 · A5 诚实性。
v3.0 增加公理 **A6 可溯源性**：任何结构化元素必须能定位到 PDF 物理页。

---

## 一、数据模式（Schema v3.0）

### 1.0 顶层结构

```jsonc
{
  "schema_version": "3.0",            // ★ 新增：模式版本（旧文件无此字段，按 1.0 读取）
  "standard_info":  { ... },          // 身份信息（含文档类别）
  "metadata":       { ... },          // 质量与提取参数
  "chapters":       [ ... ],          // 章节（每条带 page）
  "articles":       [ ... ],          // 条文（每条带 page，跨页给首页）
  "pages":          [ ... ],          // ★ 逐页容器：文本+表格+图说（取代 v2 的 page_texts + tables）
  "text_blocks":    [ ... ]           // 兼容遗留，新文件不生成
}
```

**v2 → v3 字段变更对照：**

| v2.0 | v3.0 | 说明 |
|------|------|------|
| `page_texts: [{page_number, text}]` | `pages: [{page_number, text, tables, figures}]` | 平铺数组升级为页容器 |
| `tables: [{page_number, ...}]`（顶层） | `pages[i].tables` | 归位到所属页 |
| — | `pages[i].figures` | 新增：图说 |
| `articles: [{article_number, content}]` | 追加 `page` | 新增：溯源页码 |
| `chapters: [{chapter_number, chapter_title, articles}]` | 追加 `page` | 新增：溯源页码 |

**向后兼容**：读取 `pages[i].text` 即等价于 v2 的 `page_texts[i].text`。旧文件（无 `schema_version`、有顶层 `tables`）按 v1/v2 规则读取，不要求回填迁移。

### 1.1 standard_info

| 字段 | 类型 | 必填 | 规则 |
|------|------|:---:|------|
| `name` | string | ✅ | 规范全称，不含编号前缀 |
| `code` | string | ✅ | 编号，目标紧凑无空格 `GB50016-2014(2018年版)`；历史带空格值允许存在 |
| `year` | number | ✅ | **版次年份**（2018年版取 2018，TJ16-74 取 1974） |
| `document_class` | string | ✅ | ★ 文档类别，见 1.1a |
| `type` | string | ✅ | 数据质量类别（正文/OCR/占位），枚举同 v2 |
| `source_pdf` / `source_files` | string / array | — | 单源/多源（合并本） |

**1.1a `document_class` 枚举（泛化核心）：**

| 值 | 含义 | 主要检索入口 |
|----|------|------------|
| `normative_standard` | 条文型规范（GB 50016 等） | `articles` |
| `atlas` | 图集（02J503-1、22J403-1 等） | `pages[].figures` + `pages[].tables` |
| `document` | 通知/函件/纪要（无条文编号） | `pages[].text` 全文 |
| `compilation` | 汇编/合订本（GBJ16-87 合并） | `pages[].text` |
| `guideline` | 指南/解读/问答 | `pages[].text` + `articles`（若有编号） |

**现有 9 个文件映射**：GB50016-2006/2014、GB55037、GB50045-95 → `normative_standard`；条文说明与图示版 → `normative_standard`（type=条文说明与图示）；**GBJ16-87_合并（含 OCR 版）→ `compilation`**（多 PDF 合并本，用 `source_files` 登记来源）；GBJ45-82、TJ16-74 → `normative_standard`；政府文件类 → `document`。

### 1.2 metadata

| 字段 | 规则 |
|------|------|
| `total_pages` | 源 PDF 总页数 |
| `chapter_count` / `article_count` | **必须等于对应数组长度**（A3） |
| `table_count` | 等于 **所有 `pages[].tables` 数量之和**（v3 语义变化） |
| `figure_count` | ★ 等于所有 `pages[].figures` 之和（图集类应 >0，为 0 时 note 说明） |
| `page_layout` | ★ 排版标记：`single`（单栏）/ `double`（双栏）/ `mixed`。双栏必须填写，提示结构层可能失效 |
| `extracted_at` | ISO 日期 |
| `note` | 残缺声明、坏页记录、OCR 警示 |

### 1.3 chapters / articles（溯源增强）

```jsonc
{
  "chapter_number": "3",
  "chapter_title": "厂房和仓库",
  "page": 45,                    // ★ 章标题所在物理页（A6）
  "articles": [
    {
      "article_number": "3.3.1",
      "page": 45,                // ★ 条文首现物理页
      "content": ["本条是……", "1 甲类厂房……", "2 乙类厂房……"]
    }
  ]
}
```

规则：
- 列项（`1` `2` `3` / `①②③`）拆为独立数组元素（同 v2）。
- **条文跨页**：`page` 取首现页；跨页条文在 `metadata.note` 不逐条记录（低价值），但 `pages[].text` 保留了全部原文，无损（A2）。
- 解析失败的条文不进 `articles`，仅存在 `pages[].text`——**禁止为凑结构而错拆**（A1）。

### 1.4 pages[]（页容器，核心字段）

```jsonc
{
  "page_number": 12,             // PDF 物理页码（≠ 印刷页码，同 v2）
  "text": "该页完整纯文本\n行间用\\n",
  "tables": [
    {
      "table_index": 0,          // 页内序号
      "rows": 5, "cols": 4,
      "data": [["表头1", "..."], ["数据1", "..."]],
      "caption": "表3.3.1 厂房的防火分区面积"   // ★ 表题，无则省略
    }
  ],
  "figures": [                   // ★ 图集类关键字段
    {
      "figure_index": 0,
      "caption": "图3-2 楼梯栏杆立面详图",       // 图号+图名
      "figure_no": "3-2",                        // 单独提取图号，便于检索
      "note": "图内附注文字（材料表等，OCR/文本提取所得）"
    }
  ]
}
```

**图说提取规则（caption）**：
- 图集图号行正则：`^(图\s*)?(\d{1,2}[-–—]\d{1,3})[\s\.、]*(.*)$`（覆盖"图3-2 栏杆立面"、"3-2.栏杆立面"）
- 表题行正则：`^表\s*([\d\.]+)\s*(.*)$`
- 一图一说；图号提取失败时 `figure_no` 省略、caption 保留原文。
- `figure_no` 含后缀字母（如 `3-2a`）时，字母留在 caption 内、no 只取 `3-2`（检索以主图号为准，不丢信息）。
- **图的像素数据不入 JSON**（体积失控且无检索价值）；图的可视内容以页码+图说锚定，需要看图时回 PDF 物理页（A1 溯源）。

### 1.5 文种泛化：五类 PDF 的字段使用策略

| 类型 | document_class | 结构层 | 页容器重点 | 备注 |
|------|---------------|--------|-----------|------|
| 条文规范 | normative_standard | articles 全量 | text 为主 | 现状主流 |
| 图集 | atlas | articles 可空 | **figures + tables 全量**，text 保留图说上下文 | 表题图题必抓 |
| 政府文件 | document | 不生成（无条文编号） | text 全量 | 红头格式文字保留原样 |
| 条文说明版 | normative_standard（type=条文说明与图示） | articles 分节即可 | text 全量 | 正文与说明的区分靠原文版式，不强拆 |
| 扫描老规范 | normative_standard + type=扫描版/OCR | OCR 后不强制生成 | OCR 的 text；figures 从 OCR 文本抓图说 | OCR 数值必须回查原件 |

---

## 二、命名与编码（继承 v2）

- 命名 `编号_规范名称.json`、清洗规则、冲突加 `_2`：同 v2.2/2.3。
- 编码 UTF-8 无 BOM：同 v2.4。
- **存储与备份（§2.5 v2 新增，继续有效）**：JSON 与源 PDF 同目录、重要规范异地副本。v3 补充：**OCR/占位 JSON 与成品 JSON 可共存**（如 `X.json` 占位 + `X_OCR.json` 成品），成品文件名加 `_OCR` 后缀，不覆盖占位文件（A4 幂等）。

## 三、制作 SOP（v3 更新）

流程总图在 v2 §3.1 基础上增加：

```
④ 页容器组装：每页 → text + tables（页内）+ figures（caption 正则）
⑤ 溯源标注：articles/chapters 回填 page（记录条文首现行页码）
⑥ document_class 判定：按 §1.5 表登记
```

**条文-页码回填算法**（v3 核心新增）：

```python
# 逐页扫描 all_lines 时已记录每行所属页
# 条文起始行命中正则时，该页即 article.page
current_article = None
for line, pno in lines_with_page:      # lines_with_page: [(text, page_number)]
    m = ARTICLE_RE.match(line)
    if m:
        current_article = {"article_number": m.group(1), "page": pno, "content": [m.group(2)]}
        articles.append(current_article)
    elif current_article:
        current_article["content"].append(line)
```

**figures 提取**（note 边界规则：图名后续行**仅收以空格/全角空格缩进的行**，遇空行、下一图号行或顶格正文行即停——防止把正文吞进图说）：

```python
FIG_RE = re.compile(r'^(图\s*)?(\d{1,2}[-–—]\d{1,3})[\s\.、]*(.*)$')
for i, line in enumerate(page_lines):
    m = FIG_RE.match(line.strip())
    if m:
        note_lines = []
        for nxt in page_lines[i+1:]:
            s = nxt.strip()
            if not s or FIG_RE.match(s) or not (nxt.startswith(' ') or nxt.startswith('　')):
                break
            note_lines.append(s)
        figures.append({"figure_index": len(figures),
                        "figure_no": m.group(2),
                        "caption": line.strip(),
                        "note": "\n".join(note_lines)})
```

OCR 流程参数：DPI 300（v2 审查修正，继续有效）；OCR 产物 `type=正文（OCR提取）`、note 警示数值回查。

## 四、质检与验收（v3 扩展）

```python
def validate_v3(d):
    errs = []
    si, md = d["standard_info"], d["metadata"]
    ver = d.get("schema_version", "1.0")
    # 身份（同 v2：code 非空、year 1950–2100、type 枚举）
    ...
    if ver == "3.0":
        if not d.get("pages"):  errs.append("v3 文件 pages 为空")
        # A3 计数
        n_tab = sum(len(p.get("tables", [])) for p in d["pages"])
        n_fig = sum(len(p.get("figures", [])) for p in d["pages"])
        if md.get("table_count") != n_tab:  errs.append(f"table_count≠实际{n_tab}")
        if md.get("figure_count", n_fig) != n_fig:  errs.append("figure_count 不符")
        # A6 溯源
        for a in d.get("articles", []):
            if not (1 <= a.get("page", 0) <= md["total_pages"]):
                errs.append(f"条文{a.get('article_number')} 页码越界")
        # 图集类健康检查
        if si["document_class"] == "atlas" and n_fig == 0:
            errs.append("atlas 类 figure_count=0，图说提取失败？")
    return errs
```

人工抽检（v2 三条继续有效）+ 新增：
4. 图集类抽 2 个图号，回 PDF 物理页核对图与图说是否对应。

## 五、故障与已知文件

v2 §6.1 矩阵继续有效，补充：

| 现象 | 原因 | 处置 |
|------|------|------|
| `figure_count=0` 的 atlas 文件 | 图号格式非标（如"详图 A"） | 放宽正则或人工补录；至少 text 无损 |
| pages[].text 双栏串行 | 双栏排版 | `page_layout=double` 已声明；结构层可能失效属预期 |
| OCR 文件 figures 错乱 | OCR 把图说识别进正文流 | 接受 caption 噪声，图号检索命中率下降但不丢原文 |

**当前目录文件按 v3 的归类处置**（无需立即重生成，读取方按兼容规则处理）：

| 文件 | schema | 读取方式 |
|------|:---:|------|
| GB50016-2006 / 2014 / GB55037 / GB50045-95 | 1.x（隐式） | 顶层 tables + page_texts |
| 条文说明与图示版 | 1.x | 同上 |
| GBJ16-87_合并.json | 旧格式（title/pages） | §6.4 v2 迁移映射 |
| GBJ16-87_合并_OCR.json | 1.x，type=正文（OCR提取） | page_texts；数值回查原件 |
| GBJ45-82 / TJ16-74 | 占位 | 不可检索，待 OCR |

新增/重生成文件一律用 v3.0。

## 六、对抗性审查记录（v3.0 两轮）

### 第一轮（v2.0 → 已修补，v2 附录存档）

发现 5 处：正则 `\|` 假修复、无备份规则、OCR DPI 200、validate 缺身份校验、_index 无说明。已全部修补。

### 第二轮（v3.0 设计自查，本文档发布前）

针对 v3 新结构逐条攻击：

| # | 攻击点 | 裁定 | 文档中的应对 |
|---|--------|:---:|------|
| 1 | "pages 取代 page_texts，旧文件全部失效？" | 🟡 | §1.0 明确向后兼容：读 `pages[i].text`≡旧 `page_texts[i].text`；旧文件不强制迁移，渐进过渡 |
| 2 | "条文跨页时 page=首页，算不算违反准确表达？" | 🟡 | §1.3：跨页条文页码取首现页+原文在 pages 无损保留，位置近似+内容精确，锚点优先内容 |
| 3 | "图集图号格式千奇百怪，正则抓不全反而误导" | 🟡 | §1.4 提取失败时省略 figure_no、保留 caption 原文；§5 故障表要求 figure_count=0 的 atlas 必须 note 说明——宁缺毋滥（A5） |
| 4 | "图的像素不入 JSON，图集信息还是不全" | 🟢 | 锚点=页码+图说，看图回 PDF 原件（A1 溯源）；像素入档体积失控且零检索增益，两害相权取锚点 |
| 5 | "document_class 是主观判定，不同人归类不一致" | 🟢 | §1.1a 按"主要检索入口"定义，判定规则=看内容主体是条文还是图；五类已覆盖现有全部文件并逐一映射（§1.5） |
| 6 | "schema_version 引入后，读取方要写两套逻辑" | 🟢 | 变更仅两处（页容器、表格归位），text 读取路径不变；validate 按版本分支，旧文件校验规则冻结 |
| 7 | "metadata.table_count 语义变了（顶层→页内求和），旧文件校验会误报" | 🔴 | §1.2 显式声明 v3 语义 + validate_v3 仅在 `schema_version="3.0"` 时启用新语义；旧文件走 v2 校验 |
| 8 | "figures 的 note 取下一行，可能抓到无关文字" | 🟢 | §1.4：note 仅为辅助，主字段是 caption；噪声可容忍且原文在 pages.text 可核 |

**复核结论**：8 项攻击全部有明确应对或已修补；v3 结构与锚点（准确表达）无抵触；与目录现有文件兼容闭环。未发现高严重度遗留缺陷。

### 发布前终审追加（v3.0 初稿 → 本版）

初稿落盘后复读，发现 3 处新缺陷，已修补：

| # | 审查发现 | 严重度 | 修补 |
|---|---------|:---:|------|
| 9 | §1.1a 文件映射写"normative_standard **或** compilation"——GBJ16-87 归类含糊，读取方无法确定主入口 | 🟡 中 | 明确 GBJ16-87（合并本）固定为 `compilation`，并指明用 `source_files` 登记多源 |
| 10 | figures 提取代码 `note = 下一行`——图集正文与图说混排时会把正文段落吞进图说，污染检索 | 🟡 中 | 改缩进边界规则：仅收缩进行，遇空行/新图号/顶格正文即停 |
| 11 | 图号尾字母（`3-2a` 等派生详图）未定义行为，figure_no 与 caption 可能不一致 | 🟢 低 | §1.4 补充：字母留 caption、no 取主图号 |

终审复核：3 处修补后，正则、代码示例、字段语义、文件映射四者交叉一致；文档无自相矛盾。

---

## 附录：版本历史

- **v1.0**（2026-08-31）：初版。
- **v2.0**（2026-09-04）：五条公理化；首次对抗审查修补 5 处（详见 v2 附录）。
- **v3.0**（2026-09-04）：锚点重构——内容三形态模型 → 溯源闭环（条文/章带页码）、表格归位页内、figures 图说入档、document_class 文种泛化、schema_version 版本治理；二次对抗审查 8 项攻击全部应对。
