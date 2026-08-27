# -*- coding: utf-8 -*-
"""
cad_text_clean.py — 表驱动 MTEXT / 单行文字格式码清洗器（纯标准库，零依赖）

依据：《CAD读取skill最终设计_修订版rev2》§6.1(a) 完整清洗表 + 优化意见 P0-1.1。

处理顺序（顺序敏感，勿调换）：
  1. 转义保护：'\\\\' → 私用区占位符（防止字面反斜杠被后续规则误处理）
  2. %% 特殊字符：%%d→° %%p→± %%c→⌀ %%u/%%o→删除 %%%→%
  3. 堆叠分数还原：\\S上^下;  \\S上/下;  \\S上#下;  → 可读分式（不得整段删除）
  4. 字段 %<…>%：原样保留并置 is_field 标志（不按普通格式码删除）
  5. 换段：\\P \\N \\X → 换行符（不得删除，否则多行粘连）
  6. 字体/颜色/字高/宽度/字距/倾斜/对齐格式码（分号定界）→ 删除
  7. 分组括号 { } → 删除
  8. 不换行空格 \\~ → 普通空格
  9. 占位符还原 → 反斜杠

用法：
    from cad_text_clean import clean_mtext, clean_text, has_field
    s, is_field = clean_mtext("{\\\\H0.7x;{\\\\C3;文字}}")   # -> ("文字", False)
    s = clean_text(...)                                      # 便捷函数，仅返回 str
"""
import re

# 转义保护占位符（Unicode 私用区，图纸文字中不会出现）
_ESC_BACKSLASH = "\ue000"   # \\ → 字面反斜杠
_ESC_LBRACE = "\ue001"      # \{ → {
_ESC_RBRACE = "\ue002"      # \} → }

# ---------------------------------------------------------------------------
# 规则表：按顺序执行 (pattern, replacement, flags)
# ---------------------------------------------------------------------------
_PERCENT_RULES = [
    (re.compile(r"%%[dD]"), "\u00b0"),   # 度符号 °
    (re.compile(r"%%[pP]"), "\u00b1"),   # 正负号 ±
    (re.compile(r"%%[cC]"), "\u2300"),   # 直径符号 ⌀
    (re.compile(r"%%[uUoO]"), ""),       # 下划线/上划线开关
    (re.compile(r"%%%"), "%"),
]

# 换段/换行（转义为字面反斜杠的已在第 1 步被占位符保护）
_NEWLINE_RULES = [
    (re.compile(r"\\[PX]"), "\n"),       # \P 段结束、\X 标注内换行
    (re.compile(r"\\N"), "\n"),          # \N 换行
]

# 字体/颜色/字高/宽度/字距/倾斜/对齐等分号定界格式码 → 删除
# 排除 { } 防止跨界吞噬嵌套分组（如 {\H0.7x;{\C3;文字}}）
_FORMATCODE_RE = re.compile(r"\\(?:f|C|H|W|T|Q|A)[^;{}]*;")

# 堆叠分数：\S{分子}{^|/|#}{分母};
_STACK_RE = re.compile(r"\\S([^;]*);")

# 字段：%<…>%（内含任意字符，非贪婪）
_FIELD_RE = re.compile(r"%<.*?>%")


def _unstack(m: "re.Match") -> str:
    """堆叠分数还原为可读分式。

    \\S1/2;   → 1/2
    \\S上^下; → 上^下（公差堆叠，保留 ^ 符号）
    \\S上#下; → 上/下（斜分式）
    """
    inner = m.group(1)
    # 依次尝试三种分隔符（^ 最优先，其次 #，最后 /）
    for sep in ("^", "#", "/"):
        if sep in inner:
            up, down = inner.split(sep, 1)
            if sep == "#":
                sep = "/"
            return f"{up}{sep}{down}"
    # 无分隔符：删除 \S 标记保留内容（罕见畸形输入）
    return inner


def clean_mtext(s):
    """清洗 MTEXT/单行文字格式码。

    返回 (text, is_field)：
      text     清洗后纯文本
      is_field 是否含 %<…>% 字段（字段已原样保留在 text 中，调用方自行决定取舍）
    """
    if s is None:
        return "", False
    s = str(s)

    is_field = _FIELD_RE.search(s) is not None

    # 1. 转义保护（顺序：先双反斜杠，再花括号——保证 \\{ 字面量不被误伤）
    s = s.replace(r"\\", _ESC_BACKSLASH)
    s = s.replace(r"\{", _ESC_LBRACE)
    s = s.replace(r"\}", _ESC_RBRACE)

    # 2. %% 特殊字符
    for pat, rep in _PERCENT_RULES:
        s = pat.sub(rep, s)

    # 3. 堆叠分数还原（必须先于格式码删除，否则 \S…; 会被整段吞掉）
    s = _STACK_RE.sub(_unstack, s)

    # 4. 字段：原样保留（不删除、不求值，由调用方依据 is_field 处理）
    #    （此处不替换内容，仅记录标志）

    # 5. 换段/换行
    for pat, rep in _NEWLINE_RULES:
        s = pat.sub(rep, s)

    # 6. 格式码删除
    s = _FORMATCODE_RE.sub("", s)

    # 7. 分组括号删除
    s = s.replace("{", "").replace("}", "")

    # 8. 不换行空格 → 普通空格
    s = s.replace(r"\~", " ")

    # 9. 占位符还原
    s = s.replace(_ESC_BACKSLASH, "\\")
    s = s.replace(_ESC_LBRACE, "{")
    s = s.replace(_ESC_RBRACE, "}")

    return s.strip(), is_field


def clean_text(s):
    """便捷函数：仅返回清洗后文本。"""
    return clean_mtext(s)[0]


def has_field(s):
    """检测字符串是否含 %<…>% 字段。"""
    return bool(_FIELD_RE.search(str(s))) if s is not None else False


if __name__ == "__main__":
    # 快速自检（完整用例见 tests/test_clean.py）
    cases = [
        r"{\H0.7x;{\C3;文字}}",
        r"KL7(3)\P300x600",
        r"%%c8@100",
        r"厚度{\S1/2;}砖",
        r"{\S+0.02^-0.01;}",
        r"C:\Program Files",
    ]
    for c in cases:
        print(repr(c), "->", repr(clean_text(c)))
