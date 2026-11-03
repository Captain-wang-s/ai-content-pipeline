#!/usr/bin/env python3
"""通用封面合成：AI 无字视觉图 + HTML 中文标题 → Playwright 截 900×383 封面 PNG。

用法（单张）:
  python3 composite_ai_covers.py "相关性分散" "别把鸡蛋放一个板块" \
    covers_visual/cover_p19_1_visual.png covers/cover_p19_1.png blue

用法（批量，--config）:
  python3 composite_ai_covers.py --config config/batch_YYYYMMDD_pX.json

批量模式从 config 读 articles[].cover_main/cover_sub/theme，并自动匹配
covers_visual/ 下以 {article_id}_visual 结尾的 PNG 作为视觉原图。
"""
import asyncio
import json
import glob
import os
import sys
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_cover_html(cover_main, cover_sub, visual_path, theme):
    if theme == "blue":
        overlay = "linear-gradient(135deg, rgba(21,101,192,0.55) 0%, rgba(21,101,192,0.25) 100%)"
    elif theme == "red":
        overlay = "linear-gradient(135deg, rgba(183,28,28,0.55) 0%, rgba(229,57,53,0.25) 100%)"
    else:  # green
        overlay = "linear-gradient(135deg, rgba(27,94,32,0.55) 0%, rgba(76,175,80,0.25) 100%)"

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{cover_main}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 900px; height: 383px;
    background: url('file://{visual_path}') center/cover no-repeat, {overlay};
    background-blend-mode: multiply;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}}
.main-title {{
    font-size: 72px; font-weight: 900; color: #fff;
    letter-spacing: 8px; text-shadow: 0 4px 20px rgba(0,0,0,0.5);
    margin-bottom: 20px;
}}
.sub-title {{
    font-size: 36px; font-weight: 700; color: #fff;
    letter-spacing: 4px; text-shadow: 0 2px 10px rgba(0,0,0,0.4);
}}
</style></head>
<body>
<div class="main-title">{cover_main}</div>
<div class="sub-title">{cover_sub}</div>
</body></html>'''


async def screenshot_cover(html_path, png_path, width=900, height=383):
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--proxy-server=direct://"])
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(f"file://{html_path}")
        await page.wait_for_timeout(800)
        await page.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()


async def composite_one(main, sub, visual, output, theme):
    visual = os.path.abspath(visual)
    output = os.path.abspath(output)
    html_path = output.replace(".png", "_ai.html")
    html = generate_cover_html(main, sub, visual, theme)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    await screenshot_cover(html_path, output)
    return output


async def composite_from_config(config_path):
    cfg = json.load(open(config_path, encoding="utf-8"))
    date = cfg["date"]
    visual_dir = os.path.join(BASE, "covers_visual")

    for art in cfg["articles"]:
        aid = art["id"]
        main = art.get("cover_main", "")
        sub = art.get("cover_sub", "")
        theme = art["theme"]

        # 自动匹配 visual：covers_visual/*_{aid}_visual.png
        pattern = os.path.join(visual_dir, f"*_{aid}_visual.png")
        matches = glob.glob(pattern)
        if not matches:
            pattern2 = os.path.join(visual_dir, f"cover_{date}_{aid}_visual.png")
            matches = glob.glob(pattern2)
        if not matches:
            print(f"⚠️ {aid}: 找不到 visual 文件 ({pattern})，跳过")
            continue
        visual = matches[0]

        output = os.path.join(BASE, "covers", f"cover_{date}_{aid}.png")
        await composite_one(main, sub, visual, output, theme)
        print(f"✅ {aid}: {output}")


async def main():
    if sys.argv[1] == "--config":
        await composite_from_config(sys.argv[2])
    else:
        # 单张模式: main sub visual output theme
        if len(sys.argv) < 6:
            print("用法: composite_ai_covers.py <主标题> <副标题> <visual路径> <输出路径> <blue|red|green>")
            print("  或: composite_ai_covers.py --config <config.json>")
            sys.exit(1)
        main_t, sub_t, visual, output, theme = sys.argv[1:6]
        result = await composite_one(main_t, sub_t, visual, output, theme)
        print(f"✅ 封面合成: {result}")


if __name__ == "__main__":
    asyncio.run(main())
