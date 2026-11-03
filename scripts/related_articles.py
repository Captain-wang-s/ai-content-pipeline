#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
往期推荐模块（从 publish_3hotspot_single_draft.py 抽出，单一事实来源）

- load_articles_db:      读取 data/published_articles.csv（最近10篇真实文章，按标题去重）
- get_related_articles:  按发布时间倒序，取最近 N 篇（不混主题匹配）
- generate_related_html: 生成往期推荐区块（标题13px / 列表12px，紧凑容纳最近10篇）

发布脚本(publish_3hotspot_single_draft.py)与本地预览(gen_related_block.py)
共用本模块，避免逻辑重复。

数据源：由 mptext API 刷新（见 SOP §0.1 往期推荐数据源刷新）。
"""

import os
import csv

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 加载往期文章链接库
def load_articles_db():
    """从published_articles.csv加载文章链接库，按标题去重（保留发布时间最晚的）"""
    articles_db = []
    title_map = {}
    csv_path = f'{BASE}/data/published_articles.csv'
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('链接') and row.get('标题'):
                    title = row['标题'].strip()
                    publish_time = row.get('发布时间', '')
                    # 按标题去重，保留发布时间最晚的
                    if title not in title_map or publish_time > title_map[title].get('publish_time', ''):
                        title_map[title] = {
                            'url': row['链接'].strip(),
                            'title': title,
                            'publish_time': publish_time
                        }
        articles_db = list(title_map.values())
    return articles_db

# 根据文章主题分类关键词
def get_topic_keywords():
    """定义各主题的关键词映射"""
    return {
        '职场': ['裁员', '降薪', '跳槽', '面试', '领导', '绩效', '职场', '打工人', '同事', '离职', 'N+1', 'PUA', '背锅', '升职', '加薪', 'offer', '简历', '被裁', '护嫡系', '嫡系', '基层', '老实人', '被耍', '不得已', '毒的饼', '博士后', '工伤', '猝死', '程序员', '工程师', '华人', '留学', '海外', '签证', '盘问', '自杀'],
        'AI科技': ['AI', 'GPT', 'ChatGPT', '大模型', '人工智能', '豆包', 'Claude', 'Cursor', 'Copilot', '编程', '代码', '算法', '机器学习', '深度学习', '具身智能', '机器人', 'Agent', '搜索', 'Google', '谷歌', '百科', '维基', '腾讯', '元宝', '混元', '内容创作', '生成', '博鳌', '亚洲论坛'],
        '数据分析': ['SQL', '数据', '分析师', 'BI', 'Power BI', 'FineBI', '指标体系', 'A/B', '漏斗', '归因', '埋点', '数仓', 'Hive', 'Python', 'Pandas', '分词', '关键字', 'A/Btest', '中位数', '面试', '查询'],
        '投资': ['BTC', '比特币', 'ETH', '以太坊', '加密货币', '币', 'Web3', '美元', '降息', 'USDT', 'Circle', '行情', '抄底', '牛市', '熊市', 'ETF', '微策', '稳定币', '加密', '代币', '金融', '美股', 'CoinGlass', '牛市亏钱'],
        '股票投资': ['量化', '选股', '回测', 'A股', '股票', '炒股', 'K线', '均线', 'MACD', 'RSI', 'KDJ', '布林', '布林带', '止损', '止盈', '建仓', '清仓', '仓位', '信号', '策略', '交易系统', '实盘', '持仓', '买卖时机', '择时', '龙头', '估值', 'PE', 'PB', 'ROE', '资金流', '夏普', '状态机', '选股器', '股票池'],
        '个人成长': ['30岁', '失恋', '牙套', '习惯', '效率', '成长', '焦虑', '迷茫', '人生', '选择', '搭子', '疲惫', '总结', '社保', '保险', '长护险', '医保', '养老', '健康', '猝死', '身体', '年龄', '中年', '父母', '护理']
    }

def classify_article(title, digest=''):
    """根据标题和摘要判断文章主题"""
    text = (title + ' ' + digest).lower()
    topics = get_topic_keywords()
    scores = {}
    for topic, keywords in topics.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[topic] = score
    if scores:
        return max(scores, key=scores.get)
    return '其他'

def get_related_articles(title, digest='', count=10):
    """按发布时间倒序（最新在前）返回往期文章，排除当前文章本身

    纯时间倒序，不混入主题匹配，保证往期推荐列表从新到旧排列。
    publish_time 格式如 2026/07/13 09:00（零填充），字符串倒序即时间倒序。
    """
    articles_db = load_articles_db()
    if not articles_db:
        return []
    sorted_db = sorted(
        articles_db,
        key=lambda x: x.get('publish_time', ''),
        reverse=True
    )
    result = [a for a in sorted_db if a['title'] != title][:count]
    return result

def generate_related_html(title, digest='', manual_related=None):
    """生成往期推荐HTML（标题13px / 列表12px，紧凑容纳最近10篇）

    返回内容自带 <hr> 分隔线，发布脚本据此做幂等裁剪（重发不会重复追加）。
    """
    if manual_related:
        related = manual_related
    else:
        related = get_related_articles(title, digest, count=10)
    if not related:
        return ''

    items_html = ''.join([
        f'<li style="margin: 5px 0; line-height: 1.5;"><a href="{art["url"]}" style="color: #576b95; text-decoration: none;">{art["title"]}</a></li>'
        for art in related
    ])

    # 注意：ul标签内不能有多余换行，否则公众号会渲染出空列表项
    # 在往期推荐上方加细线与正文隔开（自带 <hr>，保证重发幂等）
    related_box = f'<div style="background: #f7f7f7; border-radius: 8px; padding: 12px 16px; margin: 16px 0;"><p style="font-weight: bold; color: #333; margin: 0 0 8px 0; font-size: 13px;">📚 往期精彩推荐</p><ul style="margin: 0; padding-left: 18px; color: #666; font-size: 12px;">{items_html}</ul></div>'
    return f'<hr style="border: none; border-top: 1px solid #e8e8e8; margin: 24px 0 16px 0;" />{related_box}'
