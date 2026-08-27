# -*- coding: utf-8 -*-
"""
test_clean.py — cad_text_clean 清洗器单元测试

依据：任务书 T1 验收标准（≥20 条用例，含堆叠/换段/嵌套/字段/转义等边界）。
运行：venv python tests/test_clean.py  或  python -m pytest tests/test_clean.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_text_clean import clean_mtext, clean_text, has_field

PASS = 0
FAIL = 0
FAILED = []


def check(no, desc, got, expect):
    global PASS, FAIL
    if got == expect:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append((no, desc, got, expect))


# ---------------------------------------------------------------- %% 转换
check(1, "%%d→°", clean_text("%%dC"), "°C")
check(2, "%%p→±", clean_text("%%p0.000"), "±0.000")
check(3, "%%c→⌀（结构/机电高频）", clean_text("%%c8@100"), "⌀8@100")
check(4, "%%%→%", clean_text("100%%%"), "100%")
check(5, "%%u/%%o 开关删除", clean_text("%%u文字%%u"), "文字")
check(6, "小写 %%c", clean_text("%%c16"), "⌀16")

# ---------------------------------------------------------------- 堆叠分数
check(7, "{\\S1/2;}→1/2（不得整段删除）", clean_text("厚度{\\S1/2;}砖"), "厚度1/2砖")
check(8, "{\\S上^下;} 公差堆叠保留", clean_text("{\\S+0.02^-0.01;}"), "+0.02^-0.01")
check(9, "{\\S上#下;} 斜分式→/", clean_text("{\\S1#2;}"), "1/2")
check(10, "无括号堆叠", clean_text("\\S3/4;"), "3/4")

# ---------------------------------------------------------------- 换段/换行
check(11, "\\P→换行（KL7 用例）", clean_text("KL7(3)\\P300x600"), "KL7(3)\n300x600")
check(12, "\\X→换行（标注内）", clean_text("3600\\X(复核)"), "3600\n(复核)")
check(13, "\\N→换行", clean_text("第一行\\N第二行"), "第一行\n第二行")
check(14, "多行不粘连（无空格插入）", clean_text("A\\PB"), "A\nB")

# ---------------------------------------------------------------- 格式码删除
check(15, "嵌套 {\\H0.7x;{\\C3;文字}}", clean_text("{\\H0.7x;{\\C3;文字}}"), "文字")
check(16, "\\C3; 颜色", clean_text("\\C3;文字"), "文字")
check(17, "\\W0.8; 宽度", clean_text("\\W0.8;文字"), "文字")
check(18, "\\T1.2; 字距", clean_text("\\T1.2;文字"), "文字")
check(19, "\\Q30; 倾斜", clean_text("\\Q30;文字"), "文字")
check(20, "\\A1; 对齐", clean_text("\\A1;文字"), "文字")
check(21, "\\f 字体完整描述", clean_text("\\fSimSun|b0|i0|c134|p2;文字"), "文字")
check(22, "{} 分组括号删除", clean_text("{文字}"), "文字")

# ---------------------------------------------------------------- 空格/转义
check(23, "\\~→普通空格", clean_text("不换行\\~空格"), "不换行 空格")
check(24, "字面反斜杠路径不被当格式码（DXF 中字面 \\\\ 写作双反斜杠）", clean_text("C:\\\\Program Files"), "C:\\Program Files")
check(25, "\\{ 转义花括号", clean_text("\\{1\\}"), "{1}")

# ---------------------------------------------------------------- 字段
check(26, "字段原样保留+标志", clean_mtext("面积%<\\AcObjProp.16.2 Object(%<\\_ObjId 123>%).Area \\f \"%lu2\">%㎡"),
       ("面积%<\\AcObjProp.16.2 Object(%<\\_ObjId 123>%).Area \\f \"%lu2\">%㎡", True))
check(27, "无字段时 is_field=False", clean_mtext("普通文字")[1], False)
check(28, "has_field 检测", has_field("%<abc>%"), True)

# ---------------------------------------------------------------- 空值/组合
check(29, "None→空串", clean_text(None), "")
check(30, "组合：字体+直径+换段", clean_text("{\\f宋体|b0|i0;%%c8@100\\P梁下净高4.5m}"),
       "⌀8@100\n梁下净高4.5m")
check(31, "首尾空白剥离", clean_text("  文字  "), "文字")
check(32, "混合文字+堆叠", clean_text("{1\\S2/3;}"), "12/3")

# ---------------------------------------------------------------- 汇总
print(f"通过 {PASS} / {PASS + FAIL}")
if FAILED:
    print(f"失败 {FAIL} 条：")
    for no, desc, got, expect in FAILED:
        print(f"  #{no} {desc}\n    got   ={got!r}\n    expect={expect!r}")
    sys.exit(1)
print("test_clean.py 全部通过 ✓")
