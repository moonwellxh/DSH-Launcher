# -*- coding: utf-8 -*-
"""
scan_dwg_text.py — C 路：双通道二进制扫描兜底（不依赖 AutoCAD / LibreDWG）

依据：《最终设计 rev2》§3 第 1 条 + 任务书 T6。

提取：
  1) 门窗编号（M1025、C2114a 这类，M/C+数字+可选字母）
  2) 中文文字（样式名、图层名、标注、配置等）

双通道编码策略（按文件头 6 字节版本串分流）：
  - AC1021（2007）及更高：文本在文件内部以 Unicode 存储 → 并行执行
    GBK 与 UTF-16LE 双通道扫描后归并去重（纯 GBK 会漏报/乱码）；
  - AC1021 以下（AC1015/AC1018 等）：仅 GBK 单通道（历史版本按
    ANSI/$DWGCODEPAGE 存储，中文 Windows 主流为 GBK）。

降噪策略（实测调优，原样保留）：
  - 门窗编号：正则精确匹配，无噪音；
  - 中文文字：连续中文片段 + 三级过滤：
      a) 常用词白名单命中，或 常用字占比 ≥ 0.9；
      b) 汉字数 ≥ 2；
      c) 排除含 GBK 二级区生僻字（D8-F7）的片段。
    DWG 二进制随机字节会被 GBK 误解码成生僻字组合，三级过滤可滤掉。

大文件保护：>200MB 分块扫描（1MB 块 + 64B 重叠防跨块截断）。

用法：
    python scan_dwg_text.py "关键词" ...          # 连 AutoCAD 拿目标文档路径
    python scan_dwg_text.py --file "D:/xx.dwg"   # 直接给路径，不依赖 AutoCAD

输出：JSON（numbers + texts 清单，source:"C"）+ stdout
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 分块扫描阈值（字节）与块大小/重叠
_CHUNK_THRESHOLD = 200 * 1024 * 1024
_CHUNK_SIZE = 4 * 1024 * 1024
_CHUNK_OVERLAP = 64

# 建筑/CAD 常用词白名单（片段命中任一词即认为是有意义的真实文字）
COMMON_WORDS = set("""
墙体 外墙 内墙 隔墙 剪力墙 填充墙 幕墙 门窗 门 窗 凸窗 飘窗 阳台 楼梯 电梯 扶梯 自动扶梯
柱 梁 板 楼板 屋面板 屋面 屋顶 地下室 机房 水泵房 锅炉房 制冷机房 配电房 配电室 变电所 变配电
强电间 弱电间 管井 风井 排烟井 送风井 集水坑 降板 反坎 栏板 栏杆 扶手 龙骨 吊顶 踢脚 门槛
过梁 圈梁 构造柱 雨篷 挑檐 女儿墙 散水 坡道 台阶 车道 车位 防火门 防火卷帘 人防 掩蔽 电站
比例 高度 宽度 长度 面积 尺寸 标高 标注 注释 说明 图名 编号 样式 字体 字高 图例 索引 剖面
大样 详图 平面图 立面图 总图 名称 颜色 图层 线型 线宽 配置 参数 界限 控制线 出图 布图 图框
普通 单行 多行 文字 默认 设置 样式名 字体样式 数字字体 中文字体 宽度系数 楼栋 地铁 高压 河道
交通 消防 给排水 暖通 电气 结构 材料 规格 型号 说明 备注 卫生间 厨房 卧室 客厅 餐厅 书房
设备 管线 桥架 母线 风管 水管 烟囱 泄爆 洞口 预留 洞口 开洞 净高 挑高 层高 门洞 出口 入口
构架 辅助 划分线 外参 存放 建筑 间距 楼栋 市政 物业 垃圾 回收点 示意 地形图 分区 构筑 围墙 其它
红线 道路 用地 出入口 箭头 中心线 界外 轮廓 层数 景观 场地 绿化 水景 雨水口 退让线 低层 多层
高层 总图 室外 非机动车 首层 新建 填充 坐标 道路红线 用地红线 垃圾回收 物业与 楼栋编号 市政标高
建筑尺寸 说明与文字 栏杆围墙 道路中心线 出入口箭头 场地填充 绿化填充 水景 排水 道路 分析 界线
界线 退让 界限 界限比例 幕墙样式 单行文字 多行文字 中文字体 数字字体 字体样式 宽度系数 凸窗
""".split())


def pick_output_dir(preferred=None):
    """动态输出目录（§8.3）：图纸同目录 → 同目录 UNC 形式（SMB 盘符只读兜底）→ 临时目录。"""
    from path_util import ensure_writable_dir
    d, _mode = ensure_writable_dir(preferred)
    return d


def read_version(path):
    """读 DWG 文件头 6 字节版本串（AC1015/AC1018/AC1021/...）。"""
    try:
        with open(path, "rb") as f:
            return f.read(6).decode("ascii", errors="replace").strip("\x00")
    except Exception:
        return None


def needs_utf16_channel(version):
    """AC1021（2007）及以上需要 UTF-16LE 通道。"""
    if not version or not version.startswith("AC"):
        return True   # 未知版本保守双通道
    try:
        return int(version[2:]) >= 1021
    except ValueError:
        return True


# GBK 二级区（生僻字）判定：一级区 0xB0-0xD7，二级区 0xD8-0xF7
def is_gb1(ch):
    """GB2312 一级常用汉字"""
    b = ch.encode("gbk", errors="ignore")
    return len(b) == 2 and 0xB0 <= b[0] <= 0xD7 and 0xA1 <= b[1] <= 0xFE


def is_gb2(ch):
    """GB2312 二级生僻字（DWG 二进制误解码多落入此区）"""
    b = ch.encode("gbk", errors="ignore")
    return len(b) == 2 and 0xD8 <= b[0] <= 0xF7


def common_ratio(s):
    hans = [c for c in s if '\u4e00' <= c <= '\u9fff']
    if not hans:
        return 0
    return sum(is_gb1(c) for c in hans) / len(hans)


def scan_numbers(txt):
    """门窗编号：M/C + 数字 + 可选字母，后紧跟 \\x00，前非 A"""
    pat = re.compile(r"[MC]\d{3,4}[a-z]?\x00")
    nums = []
    for m in pat.finditer(txt):
        num = m.group().rstrip("\x00")
        if txt[m.start() - 1:m.start()] == "A":
            continue
        if num not in nums:
            nums.append(num)
    return nums


def scan_chinese(txt):
    """中文文字：连续中文片段，词表命中或高常用字占比才保留，排除生僻字噪音"""
    pat = re.compile(r"[\u4e00-\u9fff][\u4e00-\u9fff0-9\-\.×、，。:：()（）\s]{1,}")
    out = []
    for m in pat.finditer(txt):
        s = m.group().strip()
        hans = [c for c in s if '\u4e00' <= c <= '\u9fff']
        if len(hans) < 2:
            continue
        # 含生僻字（GBK 二级区）→ 多为二进制误解码，丢弃
        if any(is_gb2(c) for c in hans):
            continue
        # 含英文字母 → 随机噪音（编号已单独提取）
        if re.search(r"[a-zA-Z]", s):
            continue
        # 词表命中（任意长度）；未命中则需较长(≥4字)且常用字占比极高
        hit = any(w in s for w in COMMON_WORDS)
        if hit or (len(hans) >= 4 and common_ratio(s) >= 0.9):
            if s not in out:
                out.append(s)
    return out


def _scan_chunk(blob, enc):
    """对一块字节做单编码通道扫描，返回 (numbers, texts)。"""
    txt = blob.decode(enc, errors="ignore")
    return scan_numbers(txt), scan_chinese(txt)


def extract(path):
    """双通道提取。返回 (numbers, texts, channels_used)。"""
    version = read_version(path)
    size = os.path.getsize(path)
    dual = needs_utf16_channel(version)

    channels = ["gbk"]
    if dual:
        channels.append("utf-16-le")

    numbers, texts = [], []
    if size <= _CHUNK_THRESHOLD:
        data = open(path, "rb").read()
        for enc in channels:
            ns, ts = _scan_chunk(data, enc)
            for n in ns:
                if n not in numbers:
                    numbers.append(n)
            for t in ts:
                if t not in texts:
                    texts.append(t)
    else:
        # 大文件分块扫描（1MB 块 + 64B 重叠防跨块截断）
        for enc in channels:
            with open(path, "rb") as f:
                carry = b""
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    blob = carry + chunk
                    if len(chunk) == _CHUNK_SIZE:
                        carry = blob[-_CHUNK_OVERLAP:]
                        blob = blob[:-_CHUNK_OVERLAP]
                    else:
                        carry = b""
                    ns, ts = _scan_chunk(blob, enc)
                    for n in ns:
                        if n not in numbers:
                            numbers.append(n)
                    for t in ts:
                        if t not in texts:
                            texts.append(t)
                if carry:
                    ns, ts = _scan_chunk(carry, enc)
                    for n in ns:
                        if n not in numbers:
                            numbers.append(n)
                    for t in ts:
                        if t not in texts:
                            texts.append(t)
    return numbers, texts, channels


def main():
    args = sys.argv[1:]
    out_dir = None
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        args = args[:i] + args[i + 2:]

    if args and args[0] == "--file":
        paths = [Path(args[1])]
        if not paths[0].exists():
            print(f"[失败] 文件不存在: {paths[0]}")
            sys.exit(1)
    else:
        try:
            import comtypes
            import comtypes.client
            app = comtypes.client.GetActiveObject("AutoCAD.Application",
                                                  dynamic=True)
        except Exception:
            print("[未连接] AutoCAD 未运行。请用 --file <路径> 直读磁盘文件，"
                  "或先打开 AutoCAD。")
            sys.exit(2)
        docs = app.Documents
        keywords = args
        if not keywords:
            paths = [Path(docs.Item(0).FullName)]
        else:
            paths = [Path(docs.Item(i).FullName) for i in range(docs.Count)
                     if any(k in docs.Item(i).Name for k in keywords)]

    for p in paths:
        print(f"\n[扫描] {p.name}", flush=True)
        t0 = time.time()
        numbers, texts, channels = extract(str(p))
        out_dir_p = pick_output_dir(out_dir or p.parent)
        payload = {
            "dwg": p.name, "path": str(p),
            "mode": "binary_scan",
            "filter_criteria": ("door/window number pattern [MC]NNNN[a-z] "
                                "+ Chinese fragments with 3-level denoise"),
            "channels": channels,
            "version": read_version(str(p)),
            "numbers": numbers,
            "texts": [{"content": t, "source": "C"} for t in texts],
            "elapsed_sec": round(time.time() - t0, 1),
            "errors": [],
        }
        print(f"  [通道] {'+'.join(channels)}  [编号] {len(numbers)} 个 "
              f"[中文文字] {len(texts)} 条", flush=True)
        for n in numbers[:12]:
            print(f"    编号 {n}", flush=True)
        for t in texts[:12]:
            print(f"    {t}", flush=True)
        out = out_dir_p / f"{p.stem}_天正文字.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print(f"  [输出JSON] {out}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[失败] {type(e).__name__}: {e}")
        sys.exit(1)
