#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_wechat_published.py — 爬取微信公众号后台「发表记录」重建文章 CSV

流程：
1. 复用 storage_state 登录态（首次需扫码）
2. 登录后从后台跳转 URL 提取 token，用【浏览器真实导航 page.goto】调
   appmsgpublish 接口翻页抓取（浏览器自动携带 cookie，规避 page.request 不同步导致的 200009）
3. 输出 data/published_articles.csv（格式：链接,标题,主笔人,发布时间）

用法：
  python3 scripts/fetch_wechat_published.py
  WX_HEADLESS=false python3 scripts/fetch_wechat_published.py   # 想看浏览器窗口

说明：
  - 首次运行会在 assets/wechat_login_qr.png 生成登录二维码截图，请微信扫码确认
  - 登录态保存到 config/wechat_login_state.json，后续运行无需再扫
  - 系统代理（FlClash 未启动）已被 --proxy-server=direct:// 绕过
"""
import os
import re
import json
import csv
import time
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(BASE, "config", "wechat_login_state.json")
QR_PATH = os.path.join(BASE, "assets", "wechat_login_qr.png")
OUT_CSV = os.path.join(BASE, "data", "published_articles.csv")

LOGIN_PAGE = "https://mp.weixin.qq.com/"
HOME = "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN"
API_TMPL = ("https://mp.weixin.qq.com/cgi-bin/appmsgpublish?"
            "action=list&begin={begin}&count={count}&type=publish&f=json&lang=zh_CN&token={token}")


def log(msg):
    print(msg, flush=True)


def extract_token(url):
    if not url:
        return None
    m = re.search(r"[?&]token=(\d+)", url)
    return m.group(1) if m else None


def fetch_json(page, url):
    """用浏览器真实导航访问接口并读取 body 文本解析 JSON。返回 dict 或 None。"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.2)
        text = page.evaluate(
            "() => { var b=document.body; return b? b.innerText||b.textContent||'' : ''; }"
        )
        text = (text or "").strip()
        if not text:
            return None
        return json.loads(text)
    except Exception as e:
        return None


def verify_token(pg, tok):
    """用带 token 的那个真实页面导航验证 token 是否真正登录有效（ret==0）。"""
    data = fetch_json(pg, API_TMPL.format(begin=0, count=1, token=tok))
    if data and isinstance(data, dict):
        ret = data.get("base_resp", {}).get("ret", -1)
        if ret == 0:
            return True
        log(f"  (验证 token 无效: ret={ret})")
    else:
        log("  (验证 token: 接口未返回 JSON)")
    return False


def find_valid_token(context):
    """在所有已开页面里找带 token 且验证通过的页面，返回 (page, token) 或 (None, None)。"""
    for pg in context.pages:
        tok = extract_token(pg.url)
        if tok and verify_token(pg, tok):
            return pg, tok
    return None, None


def ensure_qr_page(page):
    """若当前页是'登录超时'页（无二维码），重新加载登录页让二维码出现。"""
    try:
        txt = page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        txt = ""
    if ("登录超时" in txt) or ("请重新登录" in txt):
        try:
            page.goto(LOGIN_PAGE, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2.5)
            log("🔄 已重新加载登录页（原页面超时）")
        except Exception as e:
            log(f"  ⚠️ 重载登录页失败: {e}")


def wait_for_login(page, context):
    log("🔓 请在微信中扫码并确认登录（二维码见 images/wechat_login_qr.png）")
    last_qr = 0
    while True:
        pg, tok = find_valid_token(context)
        if tok:
            try:
                context.storage_state(path=STATE)
                log(f"💾 登录态已保存: {STATE}")
            except Exception as e:
                log(f"⚠️ 保存登录态失败: {e}")
            return pg, tok
        # 每 60s 刷新一次二维码截图（不主动 goto 登录页，让微信前端 JS 自行换码）
        if time.time() - last_qr > 60:
            ensure_qr_page(page)
            try:
                page.screenshot(path=QR_PATH, full_page=False)
                last_qr = time.time()
                log(f"📸 二维码已刷新: {QR_PATH}")
            except Exception as e:
                log(f"  ⚠️ 截图失败: {e}")
        time.sleep(3)


def fetch_published(page, token):
    """翻页抓取发表记录（用主 page 真实导航，浏览器带 cookie）"""
    items = []
    begin = 0
    count = 20
    while True:
        url = API_TMPL.format(begin=begin, count=count, token=token)
        data = fetch_json(page, url)
        if not data or not isinstance(data, dict):
            log("  ⚠️ 接口未返回 JSON（可能登录态失效），停止抓取")
            break
        ret = data.get("base_resp", {}).get("ret", -1)
        if ret != 0:
            log(f"  ⚠️ 接口 ret={ret}: {data.get('base_resp', {}).get('err_msg', '')}")
            break
        lst = data.get("app_msg_list", [])
        if not lst:
            break
        items.extend(lst)
        total = data.get("total_count", 0)
        log(f"  已抓 {len(items)}/{total}")
        begin += len(lst)
        if begin >= total:
            break
        time.sleep(0.6)
    return items


def save_csv(items):
    rows = []
    for it in items:
        ts = it.get("publish_time", 0)
        if ts:
            try:
                dt = datetime.datetime.fromtimestamp(int(ts))
                pub = dt.strftime("%Y/%m/%d %H:%M")
            except Exception:
                pub = ""
        else:
            pub = ""
        url = it.get("url", "") or ""
        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)
        rows.append({
            "链接": url,
            "标题": (it.get("title", "") or "").strip(),
            "主笔人": "CaptainTalk",
            "发布时间": pub,
        })
    rows.sort(key=lambda r: r["发布时间"], reverse=True)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["链接", "标题", "主笔人", "发布时间"])
        w.writeheader()
        w.writerows(rows)
    log(f"✅ 已写入 {len(rows)} 篇到 {OUT_CSV}")
    return rows


def main():
    headless = os.getenv("WX_HEADLESS", "true").lower() != "false"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--proxy-server=direct://", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        if os.path.exists(STATE):
            try:
                context.load_storage_state(STATE)
                log("🔑 已加载历史登录态，尝试直接登录")
            except Exception as e:
                log(f"⚠️ 加载登录态失败: {e}")
        page = context.new_page()
        try:
            page.goto(LOGIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"⚠️ 登录页加载异常: {e}")
        time.sleep(3)

        # 先尝试已存登录态
        pg, token = find_valid_token(context)
        if not token:
            # 出首张二维码
            try:
                page.screenshot(path=QR_PATH, full_page=False)
                log(f"📸 二维码已生成: {QR_PATH}")
            except Exception as e:
                log(f"⚠️ 截图失败: {e}")
            pg, token = wait_for_login(page, context)

        if token:
            items = fetch_published(pg if pg else page, token)
            if not items:
                log("⚠️ 接口未返回数据，请看上方日志")
            else:
                rows = save_csv(items)
                log(f"📊 共 {len(rows)} 篇，最早: {rows[-1]['发布时间']} / 最新: {rows[0]['发布时间']}")
        else:
            log("❌ 未能获取有效登录 token，抓取中止")
        browser.close()
        log("🏁 完成")


if __name__ == "__main__":
    main()
