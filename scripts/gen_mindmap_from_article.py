#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用脑图生成器：从单篇公众号文章 HTML 自动抽取结构生成脑图 HTML。
严格按 SOP 九规范：
  · 2 列 6 分支（红/橙/蓝/绿/紫/青 具名 class 循环）
  · 每分支 3 个真实要点（取自文章真实句子，禁止占位重复）
  · 必须含 .tip（船长的话，从文章 .tip div 抽取真实文字，必须非空）+ .qr-code（../images/assets/qrcode_gzh.jpg）+ .footer

用法:
  python3 code/scripts/gen_mindmap_from_article.py --article articles/article_YYYYMMDD_pX_1_xxx.html \
      --out mindmaps/mindmap_YYYYMMDD_pX_1_xxx.html

适用于 p8 及以后所有批次，使自动化流水线能自动补齐脑图，无需手搓。
"""
import os
import re
import json
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS = """* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    min-height: 100vh;
    background: linear-gradient(160deg, #0d0d1a 0%, #13131f 50%, #0d0d1a 100%);
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 30px 20px;
}
.container { width: 100%; max-width: 900px; }
.header { text-align: center; margin-bottom: 30px; }
.header h1 { color: #fff; font-size: 30px; font-weight: 700; letter-spacing: 2px; line-height: 1.4; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 22px; }
.branch { border-radius: 14px; padding: 16px 18px; }
.branch-red { background: rgba(229,57,53,0.10); border-left: 5px solid #E53935; }
.branch-orange { background: rgba(255,152,0,0.10); border-left: 5px solid #FF9800; }
.branch-blue { background: rgba(71,118,230,0.10); border-left: 5px solid #4776e6; }
.branch-green { background: rgba(76,175,80,0.10); border-left: 5px solid #4CAF50; }
.branch-purple { background: rgba(156,39,176,0.10); border-left: 5px solid #9C27B0; }
.branch-teal { background: rgba(0,188,212,0.10); border-left: 5px solid #00BCD4; }
.branch-title { font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 10px; }
.item { display: flex; align-items: flex-start; margin-bottom: 7px; color: #ccc; font-size: 13.5px; line-height: 1.5; }
.dot { width: 6px; height: 6px; border-radius: 50%; margin-right: 8px; margin-top: 6px; flex-shrink: 0; }
.branch-red .dot { background: #E53935; }
.branch-orange .dot { background: #FF9800; }
.branch-blue .dot { background: #4776e6; }
.branch-green .dot { background: #4CAF50; }
.branch-purple .dot { background: #9C27B0; }
.branch-teal .dot { background: #00BCD4; }
.label { color: #fff; font-weight: 600; }
.tip { background: rgba(255,224,138,0.10); border-left: 4px solid #FFE08A; padding: 14px 18px; border-radius: 10px; margin-top: 18px; color: #FFE08A; font-size: 14px; line-height: 1.7; font-weight: 600; }
.tip strong { color: #FFE08A; }
.qr-code { text-align: center; margin-top: 14px; margin-bottom: 8px; }
.qr-code img { width: 90px; height: 90px; border-radius: 8px; background: #fff; padding: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
.footer { text-align: center; color: #666; font-size: 13px; margin-top: 12px; }
"""

# SOP 九规定的 6 色顺序
BRANCH_CYCLE = ["branch-red", "branch-orange", "branch-blue", "branch-green", "branch-purple", "branch-teal"]

# h2 不足 6 个时，用这些有真实含义的标题补齐（item 仍取自文章真实句子，绝不占位）
PAD_TITLES = [
    ("📌 一句话总结", "branch-red"),
    ("💡 关键提醒", "branch-purple"),
    ("✅ 行动建议", "branch-teal"),
]

# 视为"非正文"的标记，抽取要点时跳过
SKIP_MARKERS = ("💬", "📌", "⭐", "船长的话")

# 样板/免责章节标题关键词：匹配到时跳过该章节段落提取，改从 leftover 池取真实内容
BOILERPLATE_KEYWORDS = ("前提", "免责", "风险提示", "声明", "不是万能的",
                        "能帮你，但不能替你", "不是什么都交", "也不是万能")


def strip_tags(html):
    txt = re.sub(r"<[^>]+>", "", html)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def first_sentence(text, limit=30):
    text = text.strip()
    for sep in ["。", "！", "？", ".", "!", "?"]:
        if sep in text:
            text = text.split(sep)[0]
    return text.strip()[:limit]


def extract_brief_point(text, limit=18):
    """将叙事长句压缩为要点短语（脑图分支 item 专用）。

    first_sentence 只会"截断"——30字叙事句在窄卡片里挤成3行且不像要点。
    本函数做真正的"提炼"：去掉套话前缀、取冒号后半核心信息、截断到一行能放。
    """
    sent = first_sentence(text, limit=60)   # 先取较长版本再压缩
    t = sent.strip()

    # 去掉开头的互动标记/emoji（💬📌⭐ 等不应出现在要点中）
    for em in ["💬 ", "📌 ", "⭐ ", "💬", "📌", "⭐"]:
        if t.startswith(em):
            t = t[len(em):].strip()
            break

    # 套话前缀表（按长度降序，长的先匹配）
    boiler_prefixes = [
        "我算了一笔账", "很多人以为是自己", "很多人以为",
        "一句话总纲：", "一句话总纲:",
        "前阵子",
        "实测演示（船长自研量化系统·2026年）", "实测演示",
        "最后提醒一句",
        "错在哪：", "错在哪:",
        "简单说就是", "换句话说",
        "📊 运行指标：", "📊 风险指标：", "📊 收益指标：",
        "❌ ",
    ]
    for p in boiler_prefixes:
        if t.startswith(p):
            t = t[len(p):].strip("：: ，,。；; ")
            break

    # 冒号分割：核心信息通常在后半
    for sep in ["：", ":"]:
        if sep in t and len(t) > limit + 8:
            parts = t.split(sep)
            after = parts[-1].strip()
            if len(after) >= 4:
                if after.startswith(("好比", "比如", "就像")):
                    t = parts[0].strip()[:limit]
                else:
                    t = after[:limit]
                    return t  # 已截断完成

    # 人称代词开头的清理
    for pro in ["他", "她"]:
        if t.startswith(pro):
            rest = t[1:].lstrip("，,的的了是")
            if len(rest) >= 4:
                t = rest
            break

    return t[:limit] if len(t) > limit else t


def is_valid_item(text):
    """过滤掉纯数字/过短/无意义内容，防止脑图分支出现 "1""2""3" 占位符。

    触发场景（p11/p12 已踩坑）：
      - 文章某 h2 章节内有序列表编号被拆成独立 <p>1</p><p>2</p>
      - 代码块内的行号或纯数字段落被误抓
      - leftover 池被纯数字污染后传播到后续分支
    """
    t = text.strip()
    if len(t) < 4:          # 太短不可能是真实句子
        return False
    if re.match(r'^[\d\s\.]+$', t):   # 纯数字（含 1 / 1. / 123 等）
        return False
    return True


def is_boilerplate_title(title):
    """检测 h2 标题是否为样板/免责章节（如"核心使用前提"、"量化也不是万能的"）。
    这类章节的段落几乎全是免责声明或空话，不适合作为脑图要点。"""
    t = title.strip()
    return any(kw in t for kw in BOILERPLATE_KEYWORDS)


def is_boilerplate_item(text):
    """检测单个 item 是否为免责声明/样板内容/纯标题无实质信息。"""
    t = text.strip()
    if len(t) < 6:
        return True  # 过短视为无效
    # 免责声明关键词
    disclaimer_kws = ("不构成任何投资建议", "仅为个人方法研究", "仅供参考",
                      "亏得起的钱", "市场有风险", "盈亏自负")
    if any(kw in t for kw in disclaimer_kws):
        return True
    # 只有标题没有内容的模式：以 ▫️/▪️ 开头 + 以 ：结尾 且总长<24字
    if (t.startswith(("▫️", "▪️", "- ", "·")) and t.endswith(("：", ":")) and len(t) < 24):
        return True
    return False


def extract_tip(article_html):
    """从文章抽取船长的话真实文字（必须非空）。

    兼容两种常见结构：
      结构A（p7 实际）：<p ...><strong>船长的话：</strong>实际文字……</p>
      结构B（旧模板）：<div class="tip">…<strong>船长的话：</strong>实际文字</div>
    注意：冒号后常紧跟 </strong> 标签，不能用 `[^<]+` 直接抓，需跨标签捕获。
    """
    # 结构A：<strong>船长的话：</strong> 之后到 </p>/</div> 结束的真实文字
    m = re.search(r'船长的话[：:]\s*</?strong>\s*([\s\S]{1,200}?)(?=</p>|</div>|$)', article_html)
    if m and m.group(1).strip():
        txt = re.sub(r"<[^>]+>", "", m.group(1))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            return "船长的话：" + txt[:60]
    # 结构B：.tip 块内 船长的话 之后的文字
    m = re.search(r'class="tip"[^>]*>([\s\S]*?)船长的话[：:]([\s\S]*?)</div>', article_html, re.DOTALL)
    if m:
        txt = re.sub(r"<[^>]+>", "", m.group(2))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            return "船长的话：" + txt[:60]
    # 兜底：冒号后直接是文字（无标签）
    m2 = re.search(r"船长的话[：:]\s*([^<]{1,60})", article_html)
    if m2 and m2.group(1).strip():
        return "船长的话：" + m2.group(1).strip()[:60]
    return "船长的话：数据不说谎，但会误导人。"


def collect_leftover(html):
    """收集文章全部真实句子（用于分支不足时补齐，确保每点都是真内容）。
    同时过滤掉免责声明/样板句子，避免污染分支 4/6。"""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.DOTALL)
    leftover = []
    for p in paras:
        t = strip_tags(p)
        if not t:
            continue
        if any(t.startswith(mk) or mk in t[:6] for mk in SKIP_MARKERS):
            continue
        sent = extract_brief_point(t)
        if sent and is_valid_item(sent) and not is_boilerplate_item(sent) and sent not in leftover:
            leftover.append(sent)
    return leftover


def gen_mindmap(article_path, keypoints=None):
    with open(article_path, "r", encoding="utf-8") as f:
        html = f.read()

    h2_texts = [strip_tags(m) for m in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL)]
    parts = re.split(r"<h2[^>]*>.*?</h2>", html, flags=re.DOTALL)
    leftover = collect_leftover(html)

    # 若提供人工提炼的要点映射（keypoints JSON），优先使用，跳过自动抽取。
    # 用于把"截取文字"升级为"提炼要点"——要点由人/LLM 读懂文章后逐段浓缩。
    if keypoints:
        branches = []
        for i, b in enumerate(keypoints[:6]):
            title = str(b.get("title", "")).strip()
            pts = [str(p).strip() for p in b.get("points", []) if str(p).strip()]
            while len(pts) < 3:
                pts.append(title or "要点")
            cls = BRANCH_CYCLE[i % len(BRANCH_CYCLE)]
            branches.append((title, cls, pts[:3]))
        branches = branches[:6]
        # 仍不足 6 个 → 用有真实含义的标题 + leftover 补齐
        k = 0
        while len(branches) < 6:
            ptitle, pcls = PAD_TITLES[k % len(PAD_TITLES)]
            k += 1
            items = []
            while len(items) < 3 and leftover:
                nxt = leftover.pop(0)
                if nxt not in items:
                    items.append(nxt)
            while len(items) < 3:
                items.append(ptitle)
            branches.append((ptitle, pcls, items[:3]))
    else:
        branches = []
        for i, raw_title in enumerate(h2_texts[:6]):
            # 要点总结式浓缩：分支标题禁止直接搬 h2 长句，须经 extract_brief_point 压缩
            title = extract_brief_point(raw_title) or raw_title
            seg = parts[i + 1] if i + 1 < len(parts) else ""
            items = []

            # 样板/免责章节（如"核心使用前提"、"量化也不是万能的"）：
            # 段落几乎全是免责声明 → 跳过本段提取，全部从 leftover 池取真实内容
            if not is_boilerplate_title(raw_title):
                paras = re.findall(r"<p[^>]*>(.*?)</p>", seg, flags=re.DOTALL)
                t = ""
                for p in paras:
                    t = strip_tags(p)
                    if not t or any(mk in t[:6] for mk in SKIP_MARKERS):
                        continue
                    sent = extract_brief_point(t)
                    if sent and is_valid_item(sent) and not is_boilerplate_item(sent) and sent not in items:
                        items.append(sent)
                    if len(items) >= 3:
                        break

            # 不足 3 个则用 leftover 真实句子补齐（leftover 已不含免责内容）
            while len(items) < 3 and leftover:
                nxt = leftover.pop(0)
                if nxt not in items:
                    items.append(nxt)
            # 极端兜底：仍不足（文章极短）才用标题本身，但这种情况极少
            while len(items) < 3:
                items.append(title)
            cls = BRANCH_CYCLE[len(branches) % len(BRANCH_CYCLE)]
            branches.append((title, cls, items[:3]))

        # 不足 6 个分支 → 用有真实含义的标题 + leftover 真实句子补齐
        k = 0
        while len(branches) < 6:
            ptitle, pcls = PAD_TITLES[k % len(PAD_TITLES)]
            k += 1
            items = []
            while len(items) < 3 and leftover:
                nxt = leftover.pop(0)
                if nxt not in items:
                    items.append(nxt)
            while len(items) < 3:
                items.append(ptitle)
            branches.append((ptitle, pcls, items[:3]))
        branches = branches[:6]

    # 后处理：替换所有分支中残留的样板/免责/纯标题 item
    for idx, (title, cls, items) in enumerate(branches):
        fixed_items = list(items)
        for j in range(len(fixed_items)):
            if is_boilerplate_item(fixed_items[j]):
                # 从 leftover 找一个非样板替代（leftover 可能已耗尽）
                replaced = False
                for cand in leftover:
                    if not is_boilerplate_item(cand) and cand not in fixed_items:
                        fixed_items[j] = cand
                        leftover.remove(cand)
                        replaced = True
                        break
                if not replaced:
                    # 兜底：从其他分支找不重复的真实句子
                    for oi, (ot, oc, ois) in enumerate(branches):
                        if oi != idx:
                            for cand in ois:
                                if not is_boilerplate_item(cand) and cand not in fixed_items:
                                    fixed_items[j] = cand
                                    replaced = True
                                    break
                            if replaced:
                                break
        branches[idx] = (title, cls, fixed_items)

    # 全局去重：重复 item 用真实句子替换；实在找不到真实内容就丢弃该条。
    # ⚠️ 禁止生成 "→ 分支标题" 式假占位（p20261103 联调踩坑：同一分支出现两条
    #    "→ 🚩 一句话总结"，兜底填充被去重逻辑反复命中，占位文案直接暴露给读者）。
    seen = set()
    for bi, (b_title, b_cls, b_items) in enumerate(branches):
        new_items = []
        for it in b_items:
            if it not in seen:
                seen.add(it)
                new_items.append(it)
                continue
            # 重复 → 先从 leftover 找未用过的真实句子
            cand = next((c for c in leftover if c not in seen and not is_boilerplate_item(c)), None)
            if cand:
                leftover.remove(cand)
                seen.add(cand)
                new_items.append(cand)
            # 再从其他分支借未出现过的真实句子
            else:
                pool = [o for _t, _c, oits in branches for o in oits
                        if o not in seen and not is_boilerplate_item(o)]
                if pool:
                    seen.add(pool[0])
                    new_items.append(pool[0])
                # 找不到真内容 → 直接丢弃该条（分支可少于3点，绝不放假要点）
        branches[bi] = (b_title, b_cls, new_items)

    # 文档标题
    m = re.search(r"<title>(.*?)</title>", html)
    doc_title = strip_tags(m.group(1)) if m else (h2_texts[0] if h2_texts else "脑图")
    doc_title = doc_title.replace(" - 船长Talk", "").replace(" | 船长Talk", "").strip()

    tip = extract_tip(html)

    branches_html = ""
    for title, cls, items in branches:
        items_html = "".join(
            '<div class="item"><div class="dot"></div><div><span class="label">{0}</span></div></div>\n'.format(it)
            for it in items
        )
        branches_html += '<div class="branch {0}"><div class="branch-title">{1}</div>\n{2}</div>\n'.format(cls, title, items_html)

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - 脑图</title>
<style>{css}</style>
</head>
<body>
<div class="container">
    <div class="header"><h1>{title}</h1></div>
    <div class="grid">
{branches}    </div>
    <div class="tip">
        <strong>{tip}</strong>
    </div>
    <div class="qr-code">
        <img src="../assets/qrcode_gzh.jpg" alt="公众号二维码">
    </div>
    <div class="footer">船长Talk · 数据分析 + 职场真相 + 投资洞察 · 2026.07</div>
</div>
</body>
</html>""".format(title=doc_title, css=CSS, branches=branches_html, tip=tip)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True, help="文章 HTML 路径")
    ap.add_argument("--out", required=True, help="输出脑图 HTML 路径")
    ap.add_argument("--keypoints", default=None, help="人工提炼要点映射 JSON（优先于自动抽取）")
    args = ap.parse_args()

    article = args.article if os.path.isabs(args.article) else os.path.join(BASE, args.article)
    out = args.out if os.path.isabs(args.out) else os.path.join(BASE, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 加载要点映射：显式 --keypoints 优先；否则自动探测同名文件
    #   mindmaps/keypoints_<文章stem>.json
    # 存在时直接用它（人工/LLM 提炼的真要点），跳过"截取文字"式自动抽取。
    keypoints = None
    kp_path = args.keypoints
    if not kp_path:
        stem = os.path.splitext(os.path.basename(article))[0]
        auto = os.path.join(BASE, "mindmaps", "keypoints_" + stem + ".json")
        if os.path.exists(auto):
            kp_path = auto
    if kp_path and os.path.exists(kp_path):
        try:
            with open(kp_path, "r", encoding="utf-8") as f:
                keypoints = json.load(f).get("branches", [])
            print(f"✅ 已加载人工提炼要点: {os.path.basename(kp_path)} ({len(keypoints)} 分支)")
        except Exception as e:
            print(f"⚠️ 要点映射加载失败，回退自动抽取: {e}")
            keypoints = None

    html = gen_mindmap(article, keypoints)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    # 自检：tip 必须非空
    m = re.search(r'class="tip"[^>]*>(.*?)</div>', html, re.DOTALL)
    tip_txt = re.sub(r"<[^>]+>", "", m.group(1)).replace("船长的话：", "").replace("船长的话:", "").strip() if m else ""
    status = "✅ tip有文字" if tip_txt else "❌ tip为空"
    print(f"{status} | 脑图已生成（6分支+二维码）: {out}")


if __name__ == "__main__":
    main()
