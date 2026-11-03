#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""html2png.py — 脑图/封面 HTML 转 PNG（Playwright 截图通用工具）

用法:
  python3 scripts/html2png.py mindmaps/xxx.html            # 同名 .png 输出
  python3 scripts/html2png.py in.html -o out.png           # 指定输出
  python3 scripts/html2png.py *.html                       # 批量

说明:
  - viewport 900x1200，full_page 截图（与脑图模板 900px 宽度对齐）
  - macOS 系统代理（如 Clash 未启动的死配置）会导致 Chromium 报
    net::ERR_PROXY_CONNECTION_FAILED，这里用 --proxy-server=direct:// 强制直连
"""
import os
import sys
import glob
import argparse

from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(p):
    """相对路径优先按 cwd 解析，不存在时回退到项目根目录（与 gen_mindmap 行为一致）。"""
    if os.path.isabs(p) or os.path.exists(p):
        return p
    cand = os.path.join(BASE, p)
    return cand if os.path.exists(cand) else p


def convert_one(pw, html_path, png_path, width=900, height=1200):
    html_path = os.path.abspath(html_path)
    png_path = os.path.abspath(png_path)
    if not os.path.exists(html_path):
        print(f"❌ HTML 不存在: {html_path}")
        return False
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    try:
        browser = pw.chromium.launch(
            headless=True,
            args=["--proxy-server=direct://"],  # 绕过 macOS 死系统代理
        )
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{html_path}", wait_until="networkidle")
        page.wait_for_selector(".container", timeout=15000)
        page.screenshot(path=png_path, full_page=True)
        browser.close()
        print(f"✅ {os.path.basename(html_path)} → {png_path}")
        return True
    except Exception as e:
        print(f"❌ 转换失败 {html_path}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="HTML → PNG 截图工具")
    ap.add_argument("inputs", nargs="+", help="HTML 文件（支持 glob）")
    ap.add_argument("-o", "--out", default=None, help="输出 PNG 路径（单文件时可用）")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--height", type=int, default=1200)
    args = ap.parse_args()

    files = []
    for pattern in args.inputs:
        matched = sorted(glob.glob(pattern)) or sorted(glob.glob(resolve_path(pattern)))
        files.extend(matched if matched else [resolve_path(pattern)])

    if args.out and len(files) > 1:
        print("❌ 批量模式不支持 -o，请逐个指定或省略（默认同名 .png）")
        sys.exit(1)

    ok = 0
    with sync_playwright() as pw:
        for html in files:
            png = args.out or os.path.splitext(html)[0] + ".png"
            if convert_one(pw, html, png, args.width, args.height):
                ok += 1

    print(f"\n完成 {ok}/{len(files)}")
    sys.exit(0 if ok == len(files) else 1)


if __name__ == "__main__":
    main()
