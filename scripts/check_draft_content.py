#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查草稿内容是否正常显示中文"""

import requests
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(f'{BASE}/config/wechat_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

token = requests.get(f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={config["wechat"]["app_id"]}&secret={config["wechat"]["app_secret"]}').json()['access_token']

# 获取最新5篇草稿
drafts_resp = requests.post(f'https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}', json={'count': 5, 'offset': 0}).json()

print("📋 最新5篇草稿内容检查\n")
print("=" * 60)

for i, item in enumerate(drafts_resp.get('item', [])[:5], 1):
    article = item['content']['news_item'][0]
    title = article['title']
    content = article['content']

    # 检查内容编码状态
    # 方法1: 检查是否有中文（非转义形式）
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in content)

    # 方法2: 检查是否包含转义序列
    has_escape = '\\\\u' in content

    # 方法3: 提取一段文本并打印
    text_sample = content[content.find('<p'):content.find('</p>') + 4] if '<p>' in content else content[:100]

    print(f"\n草稿 {i}:")
    print(f"标题: {title}")
    print(f"中文检测: {'✅ 有中文字符' if has_chinese else '❌ 无中文字符'}")
    print(f"转义检测: {'❌ 含转义序列' if has_escape else '✅ 无转义序列'}")
    print(f"内容样本: {text_sample}")
    print("-" * 60)

print("\n💡 提示:")
print("• 如果显示'含转义序列'，说明中文被转义了")
print("• 正常的中文应该显示为：这周、船长、最低工资等")
print("• 转义的中文会显示为：\\u8fd9\\u5468\\u8239\\u957f等")
