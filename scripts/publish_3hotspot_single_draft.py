#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
船长Talk公众号发布脚本 - 标准SOP v9.0
支持单篇/多篇发布为草稿（v9.0：爆款单发，普通同批；已移除文首关注引导）

使用方法:
1. 准备3篇HTML文章文件
2. 为每篇文章生成专属脑图PNG
3. 创建/修改 config/batch_YYYYMMDD_pX.json 配置文件
4. 运行: python3 scripts/publish_3hotspot_single_draft.py --config config/batch_YYYYMMDD_pX.json

# 尾部格式(固化):
# 分隔线 → 品牌信息 → END图
"""

import requests
import json
import os
import time
import sys
import re
import csv
import random
import argparse

# 项目根目录：scripts/ 的上一级（工程内不出现机器相关绝对路径，clone 即可用）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from related_articles import generate_related_html, get_related_articles, load_articles_db

# 导入CSS转内联工具
sys.path.insert(0, SCRIPT_DIR)
from inline_styles import inline_css

# ===== 往期推荐自动刷新（2026-07-16 接入）=====
# 根因：往期推荐数据源 published_articles.csv 原来只靠手动两步生成，发布脚本从不刷新，
#       导致已发文章里往期推荐永远停在旧快照（详见项目记忆 2026-07-16）。
# 现改为：每次发布前自动从 mptext API 拉取船长Talk最近10篇 → 刷新 CSV。
# 失败（网络/密钥过期）时优雅降级：保留旧 CSV 继续发布，绝不影响主流程。
# 可用环境变量 WX_SKIP_REFRESH=1 跳过（离线/测试场景）。
import subprocess

def refresh_related_articles():
    """发布前自动刷新往期推荐数据源（published_articles.csv）。

    注意 fetcher 把 mptext_articles.json 写到「当前工作目录」，而 refresh 脚本从
    项目根目录读取，因此两个子进程都必须以项目根目录为 cwd 运行，否则位置对不上。
    """
    if os.environ.get('WX_SKIP_REFRESH') == '1':
        print("⏭️  [往期刷新] 检测到 WX_SKIP_REFRESH=1，跳过刷新（使用现有 CSV）")
        return
    # 项目根目录：publish 脚本位于 <root>/scripts/，上溯 1 级
    project_root = BASE
    fetcher = os.path.join(SCRIPT_DIR, 'fetch_wechat_published.py')
    if not os.path.exists(fetcher):
        print(f"⚠️  [往期刷新] 刷新脚本缺失（{fetcher}），跳过，使用现有 CSV")
        return
    print("🔄 [往期刷新] 拉取公众号最近已发布文章，刷新往期推荐数据源...")
    try:
        r1 = subprocess.run(
            [sys.executable, fetcher],
            cwd=project_root, capture_output=True, text=True, timeout=120
        )
        if r1.returncode != 0:
            print(f"⚠️  [往期刷新] 拉取文章失败（返回码 {r1.returncode}），保留旧 CSV。\n{(r1.stderr or r1.stdout).strip()[:300]}")
            return
        print(f"✅ [往期刷新] {r1.stdout.strip()[-120:]}")
    except subprocess.TimeoutExpired:
        print("⚠️  [往期刷新] 超时，保留旧 CSV 继续发布")
    except Exception as e:
        print(f"⚠️  [往期刷新] 异常：{e}，保留旧 CSV 继续发布")


# 解析命令行参数
parser = argparse.ArgumentParser(description='发布公众号文章')
parser.add_argument('--config', type=str, required=True, help='配置文件路径 (如: config/batch_20260407_p20.json)')
args = parser.parse_args()

# 加载配置文件
config_path = args.config if args.config.startswith('/') else f'{BASE}/{args.config}'
if not os.path.exists(config_path):
    print(f"❌ 配置文件不存在: {config_path}")
    print(f"💡 请创建配置文件，参考: config/batch_YYYYMMDD_pX.json")
    exit(1)

with open(config_path, 'r', encoding='utf-8') as f:
    batch_config = json.load(f)

# ===== 版本闸门（预写-升级机制 · SOP §21 新增）=====
# 当前 SOP 版本。每次 SOP 升版时同步修改此常量。
CURRENT_SOP_VERSION = "v9.0"
_cfg_ver = batch_config.get('sop_version', 'UNSET')
if _cfg_ver != CURRENT_SOP_VERSION:
    print(f"⛔ [版本闸门] 拦截推送：config 的 sop_version='{_cfg_ver}' 与当前 SOP 版 '{CURRENT_SOP_VERSION}' 不一致。")
    print(f"   该批次为预写态 / 旧策略文章。请先按当前 SOP 升级重写，并将 config 的 sop_version 改为 '{CURRENT_SOP_VERSION}' 后再发布。")
    sys.exit(1)
print(f"✅ [版本闸门] config sop_version='{_cfg_ver}' 与当前 SOP 版一致，放行。")

# 从配置生成ARTICLES
ARTICLES = []
for art in batch_config['articles']:
    ARTICLES.append({
        "file": art['file'],
        "title": art['title'],
        "author": art.get('author', 'CaptainTalk'),
        "digest": art['digest'][:120],  # 微信 description 上限 120 字，截断兜底防 45004
        "mindmap": art.get('mindmap', f"mindmaps/mindmap_{batch_config['date']}_{art['id']}.png"),
        "cover": art.get('cover', f"covers/cover_{batch_config['date']}_{art['id']}.png"),
        "quote": f"covers/quote_{batch_config['date']}_{art['id']}.png",
        "related": art.get('related', None),  # 可选：手动指定往期推荐
    })

# 兼容旧版本：如果直接运行脚本（无--config），使用内嵌配置（已废弃）
ARTICLES_BACKUP = []

# END尾部图

print("=" * 70)
print(f"🚀 发布{len(ARTICLES)}篇热点文章为单个草稿")
print("=" * 70)
print()

# 0. 发布前自动刷新往期推荐数据源（失败优雅降级，不影响主流程）
refresh_related_articles()
print()

# 1. 获取access_token（优先从缓存读取，有效则直接用）
# 凭据来源优先级：环境变量 WX_APPID / WX_APP_SECRET > config/wechat_config.json
# ⚠️ 真实密钥严禁写进仓库，wechat_config.example.json 是唯一入库模板
print("🔑 正在获取access_token...")
app_id = os.environ.get('WX_APPID')
app_secret = os.environ.get('WX_APP_SECRET')
if not (app_id and app_secret):
    _cfg_path = f'{BASE}/config/wechat_config.json'
    if os.path.exists(_cfg_path):
        with open(_cfg_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        app_id = app_id or config['wechat']['app_id']
        app_secret = app_secret or config['wechat']['app_secret']
if not (app_id and app_secret):
    print("❌ 缺少微信公众号凭据：请设置环境变量 WX_APPID / WX_APP_SECRET，")
    print("   或复制 config/wechat_config.example.json 为 config/wechat_config.json 并填写")
    exit(1)

TOKEN_CACHE = f'{BASE}/config/wechat_access_token.json'
access_token = None

# 优先读取缓存Token
if os.path.exists(TOKEN_CACHE):
    with open(TOKEN_CACHE, 'r', encoding='utf-8') as f:
        cached = json.load(f)
    if cached.get('access_token') and cached.get('expires_at', 0) > time.time() + 60:
        access_token = cached['access_token']
        print(f"✅ 使用缓存Token（剩余 {int(cached['expires_at'] - time.time())} 秒）: {access_token[:20]}...\n")

# 缓存无效则重新获取
if not access_token:
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    response = requests.get(url)
    result = response.json()

    if 'access_token' not in result:
        print(f"❌ 获取access_token失败: {result}")
        print(f"\n💡 提示：当前IP不在白名单，请在本地执行以下命令获取Token后重试：")
        print(f"curl 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}'")
        print(f"\n然后把返回的 access_token 写入：{TOKEN_CACHE}")
        print(f'格式：{{"access_token": "TOKEN值", "expires_at": {int(time.time()) + 7200}}}')
        exit(1)

    access_token = result['access_token']
    # 保存到缓存
    with open(TOKEN_CACHE, 'w', encoding='utf-8') as f:
        json.dump({'access_token': access_token, 'expires_at': time.time() + 7200}, f, ensure_ascii=False, indent=2)
    print(f"✅ Token获取成功（已缓存）: {access_token[:20]}...\n")

# 2. 上传END尾部图（所有文章共用；图缺失时优雅跳过，不阻断发布）
END_IMAGE = "assets/end_image.png"
end_media_id = None
print(f"📤 上传END尾部图...")
end_image_path = f'{BASE}/{END_IMAGE}'
if not os.path.exists(end_image_path):
    print(f"⏭️  END图不存在（{END_IMAGE}），跳过尾部图")
else:
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"

    with open(end_image_path, 'rb') as f:
        files = {'media': f}
        response = requests.post(url, files=files)
        result = response.json()

    if 'media_id' in result:
        end_media_id = result['media_id']
        end_url = result.get('url', '')
        print(f"✅ END图上传成功，URL: {end_url[:60]}...\n")
    else:
        print(f"❌ END图上传失败: {result}")
        exit(1)

# 3. 处理所有文章内容
print("📝 处理文章内容...")
articles_list = []

for i, article_config in enumerate(ARTICLES, 1):
    print(f"   处理第{i}篇: {article_config['title']}")

    # 上传脑图（如果有）
    mindmap_media_id = None
    mindmap_url = ''
    if article_config.get('mindmap'):
        print(f"      上传脑图...")
        mindmap_path = f'{BASE}/{article_config["mindmap"]}'
        if os.path.exists(mindmap_path) and os.path.isfile(mindmap_path):
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
            with open(mindmap_path, 'rb') as f:
                files = {'media': f}
                response = requests.post(url, files=files)
                result = response.json()

            if 'media_id' in result:
                mindmap_media_id = result['media_id']
                mindmap_url = result.get('url', '')
                print(f"      ✅ 脑图上传成功")
            else:
                print(f"      ⚠️ 脑图上传失败: {result}")
        else:
            print(f"      ⚠️ 脑图文件不存在，跳过")
    else:
        print(f"      ⏭️ 无脑图配置，跳过")

    # 上传封面图（如果有）
    cover_media_id = mindmap_media_id  # 默认使用脑图作为封面
    if 'cover' in article_config and article_config['cover']:
        print(f"      上传封面图...")
        cover_path = f'{BASE}/{article_config["cover"]}'
        if os.path.exists(cover_path):
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
            with open(cover_path, 'rb') as f:
                files = {'media': f}
                response = requests.post(url, files=files)
                result = response.json()
            
            if 'media_id' in result:
                cover_media_id = result['media_id']
                print(f"      ✅ 封面图上传成功")
            else:
                print(f"      ⚠️ 封面图上传失败，使用脑图: {result}")
        else:
            print(f"      ⚠️ 封面图文件不存在: {cover_path}")

    # 上传金句图（如果有）
    quote_url = ''
    if 'quote' in article_config and article_config['quote']:
        print(f"      上传金句图...")
        quote_path = f'{BASE}/{article_config["quote"]}'
        if os.path.exists(quote_path):
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
            with open(quote_path, 'rb') as f:
                files = {'media': f}
                response = requests.post(url, files=files)
                result = response.json()
            if 'media_id' in result:
                quote_url = result.get('url', '')
                print(f"      ✅ 金句图上传成功")
            else:
                print(f"      ⚠️ 金句图上传失败: {result}")
        else:
            print(f"      ⚠️ 金句图文件不存在: {quote_path}")

    # 读取文章HTML并处理
    article_file = f'{BASE}/articles/{article_config["file"]}'
    with open(article_file, 'r', encoding='utf-8') as f:
        article_content = f.read()

    # ★ 关键步骤：将CSS类样式转为内联样式（公众号会剥离<style>标签）
    article_content = inline_css(article_content)

    # ★ 上传文章正文中的本地图片并替换URL
    print(f"      处理正文图片...")
    img_pattern = r'<img[^>]+src="([^"]+)"'
    img_urls = re.findall(img_pattern, article_content)
    
    # 将相对路径转换为绝对路径（基于BASE目录）
    def resolve_img_path(img_src):
        if img_src.startswith('http'):
            return None  # 外部URL，不需要上传
        # 如果是相对路径，基于BASE目录解析
        if not img_src.startswith('/'):
            full_path = os.path.join(BASE, img_src)
        else:
            full_path = img_src
        return full_path if os.path.exists(full_path) else None
    
    local_images = [(url, resolve_img_path(url)) for url in img_urls]
    local_images = [(src, full) for src, full in local_images if full is not None]
    
    for img_src, img_full_path in local_images:
        try:
            url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
            with open(img_full_path, 'rb') as f:
                files = {'media': f}
                response = requests.post(url, files=files)
                result = response.json()
            if 'url' in result:
                article_content = article_content.replace(f'src="{img_src}"', f'src="{result["url"]}"')
                print(f"         ✅ 上传: {os.path.basename(img_full_path)}")
            else:
                print(f"         ⚠️ 上传失败: {os.path.basename(img_full_path)} - {result}")
        except Exception as e:
            print(f"         ⚠️ 上传异常: {os.path.basename(img_full_path)} - {e}")

    # ★ v9.0 变更：移除"文首关注引导"注入（与 SOP §11.3/11.4 一致）。
    #   涨粉钩子改由「文章正文自带 + 文末品牌尾部」承担，不再在开头硬塞。
    #   故也不再剥离文章内的星标行——保留作者写在文末的星标/转发提示。

    # 在第二个h2之后插入脑图（让读者先看一段内容再看到脑图）
    # 如果没有第二个h2，则在第3个段落之后插入
    h2_matches = list(re.finditer(r'(<h2\s)', article_content))
    if len(h2_matches) >= 2:
        # 有第二个h2，在第二个h2前插入
        insert_pos = h2_matches[1].start()
        article_content = article_content[:insert_pos] + f'<img src="{mindmap_url}" style="width:100%; margin: 20px 0;"/>\n\n' + article_content[insert_pos:]
    else:
        # 没有第二个h2，在第3个<p>标签后插入
        p_matches = list(re.finditer(r'(<p[^>]*>.*?</p>)', article_content))
        if len(p_matches) >= 3:
            insert_pos = p_matches[2].end()
            article_content = article_content[:insert_pos] + f'\n\n<img src="{mindmap_url}" style="width:100%; margin: 20px 0;"/>' + article_content[insert_pos:]
        else:
            # 段落数量也不够，插入到第一个h2后（兜底方案）
            article_content = re.sub(
                r'(<h2\s)',
                f'<img src="{mindmap_url}" style="width:100%; margin: 20px 0;"/>\n\n\\1',
                article_content,
                count=1
            )

    # ★ 尾部处理：截掉最后一个<hr>及其之后的所有内容（旧品牌文字），替换为完整的 往期推荐+品牌+END图
    # 移除 </body></html>
    article_content = re.sub(r'\s*</body>\s*</html>\s*$', '\n', article_content)
    # 找到最后一个<hr...>，删除它及之后的所有内容
    last_hr = article_content.rfind('<hr')
    if last_hr >= 0:
        article_content = article_content[:last_hr]
    # 清理尾部空白
    article_content = article_content.rstrip() + '\n'

    # ★ 在结尾处插入金句图（在品牌区块前）
    if quote_url:
        article_content += f'\n<p style="text-align:center; margin: 20px 0;"><img src="{quote_url}" style="width:100%;"/></p>\n'

    # ★ 生成往期推荐（优先用ARTICLES里手动指定的related，没有则自动匹配）
    if article_config.get('related'):
        # 手动指定：related = [{"title": "...", "url": "..."}, ...]
        related_html = generate_related_html(
            article_config['title'],
            article_config.get('digest', ''),
            manual_related=article_config['related']
        )
    else:
        related_html = generate_related_html(article_config['title'], article_config.get('digest', ''))

    # 追加往期推荐 + 品牌信息 + END图
    tail_html = f'''{related_html}
<hr style="border: none; border-top: 1px solid #e0e0e0; margin: 25px 0;" />

<p style="text-align: center; color: #999; font-size: 14px; margin: 10px 0 5px 0;">— 船长Talk —</p>

<p style="text-align: center; color: #999; font-size: 13px; margin: 5px 0 5px 0;">数据分析 + 职场真相 + 投资洞察</p>

<p style="text-align: center; color: #999; font-size: 13px; margin: 5px 0 15px 0;">欢迎公众号后台回复"进群"一起交流<br>一起进步</p>

<p style="text-align: center; margin: 15px 0;"><img src="{end_url}" /></p>'''

    article_content += tail_html

    print(f"      ✅ 文章内容处理完成")

    # 添加到文章列表
    articles_list.append({
        "title": article_config['title'],
        "author": article_config['author'],
        "digest": article_config['digest'][:120],  # 微信 description 上限 120 字，截断兜底防 45004
        "content": article_content,
        "content_source_url": article_config.get('source_url', ''),  # 阅读原文链接（量化篇配落地页 URL）
        "thumb_media_id": cover_media_id,  # 使用封面图（如果没有则用脑图）
        "show_cover_pic": 1,
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    })

    time.sleep(1)

print(f"\n✅ 共处理{len(articles_list)}篇文章\n")

# 4. 检查文章内容是否有重复
print("🔍 检查文章内容是否重复...")
import difflib

duplicates_found = False
for i in range(len(articles_list)):
    for j in range(i + 1, len(articles_list)):
        title1 = articles_list[i]['title']
        title2 = articles_list[j]['title']
        content1 = articles_list[i]['content']
        content2 = articles_list[j]['content']

        # 计算相似度
        similarity = difflib.SequenceMatcher(None, content1, content2).ratio()

        if similarity > 0.9:  # 相似度超过90%认为重复
            print(f"   ⚠️  警告: 「{title1}」和「{title2}」内容高度相似（相似度: {similarity:.2%}）")
            duplicates_found = True
        elif similarity > 0.7:
            print(f"   ℹ️  提示: 「{title1}」和「{title2}」内容有一定相似（相似度: {similarity:.2%}）")

if not duplicates_found:
    print(f"   ✅ 未发现高度重复的文章")

print()

# 5. 创建单个草稿包含3篇文章
print("📝 创建草稿...")
url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"

data = {
    "articles": articles_list
}

# 手动json.dumps并使用data参数发送，避免requests自动转义中文
json_data = json.dumps(data, ensure_ascii=False)
headers = {'Content-Type': 'application/json; charset=utf-8'}
response = requests.post(url, data=json_data.encode('utf-8'), headers=headers)
result = response.json()

if 'media_id' in result:
    draft_id = result.get('media_id', '')
    print(f"✅ 草稿创建成功！")
    print(f"   草稿ID: {draft_id}")
    print(f"   包含{len(articles_list)}篇文章\n")

    # 保存草稿信息（存到 _archive/draft_info/ 避免污染根目录）
    ts = int(time.time())
    import os as _os
    _os.makedirs(f'{BASE}/_archive/draft_info', exist_ok=True)
    info_path = f'{BASE}/_archive/draft_info/draft_info_热点3篇_单草稿_{ts}.txt'

    with open(info_path, 'w', encoding='utf-8') as f:
        f.write(f"热点文章发布（3篇合1草稿） - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"草稿ID: {draft_id}\n")
        f.write(f"END图URL: {end_url}\n\n")

        for i, article in enumerate(articles_list, 1):
            f.write(f"--- 第{i}篇 ---\n")
            f.write(f"标题: {article['title']}\n")
            f.write(f"作者: {article['author']}\n")
            f.write(f"摘要: {article['digest']}\n\n")

    print("=" * 70)
    print(f"✅ 发布完成！{len(articles_list)}篇文章已作为单个草稿上传")
    print()
    print("📱 立即操作指南:")
    print("   1. 登录 mp.weixin.qq.com")
    print("   2. 进入「草稿箱」")
    print(f"   3. 查看草稿（包含{len(articles_list)}篇文章）")
    print("   4. 预览每篇文章后发布")
    print()
    print(f"📄 草稿信息已保存: {info_path}")
    print("=" * 70)
else:
    print(f"❌ 草稿创建失败: {result}")
    exit(1)
