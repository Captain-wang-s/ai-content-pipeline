# AI Content Pipeline — AI 驱动的多平台内容自动化发布流水线

> 一条从「选题 → AI 写作 → 配图生成 → 排版 → 自动推送草稿箱」的全自动内容生产线，
> 让一个运营账号的内容产出从"靠灵感的手工活"变成"可复用的工程流程"。

[![Python](https://img.shields.io/badge/Python-3.9+-blue)]()
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-green)]()
[![WeChat MP API](https://img.shields.io/badge/微信公众号-草稿箱API-red)]()

## 项目定位

个人独立开发并长期真实运营的内容基建项目：以微信公众号为主发布渠道，
覆盖**热点选题、AI 内容生成、脑图/封面自动合成、HTML 排版组件化、草稿箱 API 推送、
往期推荐自维护**的完整闭环，并以 SOP 文档 + Skill 式操作手册沉淀为可复用资产。

## 核心链路

```
选题CSV ──► Prompt模板库 ──► 文章HTML(组件化模板)
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼              ▼
            脑图自动抽取    AI封面/金句图合成    CSS→内联样式
            (6分支结构图)   (Playwright截图)    (公众号不支持外链CSS)
                    └─────────────┼──────────────┘
                                  ▼
                    publish 脚本：token缓存 → 素材上传 → 单草稿多图文
                                  ▼
                    草稿箱 (mp.weixin.qq.com 人工预览后群发)
```

## 技术亮点

| 模块 | 做法 | 价值 |
|------|------|------|
| **一键发布** | 批次 JSON 驱动：一次运行完成 N 篇文章的素材上传 + 单草稿多图文推送 | 从成稿到草稿箱 < 2 分钟 |
| **Token 管理** | access_token 本地缓存（7200s 有效期内复用），失效自动重取；凭据走环境变量/本地配置，与代码分离 | 避免 API 限频；密钥零泄漏 |
| **脑图自动生成** | 从文章 HTML 抽取标题结构 → 渲染 6 分支深色脑图 HTML → Playwright 截图成 PNG | 配图零手工 |
| **样式内联** | 自研 CSS→inline 转换器，解决公众号编辑器不支持外链/内部样式表的问题 | 保证任何浏览器/客户端渲染一致 |
| **往期推荐自维护** | 发布前自动用 Playwright（storage_state 登录态复用）爬取后台已发表记录，刷新推荐数据源 CSV | 老文章的引流位永远指向最新内容 |
| **优雅降级** | 往期刷新失败/END 图缺失/凭据缺失，全部不阻断主流程，逐级跳过并告警 | 自动化链路稳定性优先 |
| **跨平台自动化** | Playwright 无头浏览器多平台发布（`--proxy-server=direct://` 绕过 macOS 死系统代理） | 可扩展到 CSDN/掘金等平台 |

## 目录结构

```
ai-content-pipeline/
├── README.md                    # 本文件
├── SKILL.md                     # ⭐ Skill 式操作手册（agent/新人按此执行）
├── requirements.txt
├── .gitignore                   # 凭据、登录态、运行时产物全部排除
├── scripts/                     # 核心脚本
│   ├── publish_3hotspot_single_draft.py   # 主发布脚本（批次JSON → 草稿箱）
│   ├── gen_mindmap_from_article.py        # 文章 → 脑图 HTML 自动生成
│   ├── html2png.py                        # HTML → PNG 截图通用工具
│   ├── composite_ai_covers.py             # AI 封面/金句图合成
│   ├── crop_illustration_v7.py            # 配图水印带裁切
│   ├── inline_styles.py                   # CSS → 内联样式转换
│   ├── fetch_wechat_published.py          # Playwright 爬后台已发表记录
│   ├── related_articles.py                # 往期推荐生成
│   └── check_draft_content.py             # 草稿质检
├── templates/                   # 文章 HTML 组件化模板（按主题分）
├── prompts/                     # Prompt 模板库（选题框架/配图提示词/写作风格）
├── config/
│   ├── wechat_config.example.json         # 公众号凭据模板（真实配置不入库）
│   └── batch.example.json                 # 发布批次配置示例
├── data/                        # 选题历史 / 已发表文章索引
├── examples/                    # 成品样例（脑图/封面/金句图）
├── articles/                    # 文章 HTML 工作目录
├── assets/                      # 二维码等静态资源
└── docs/
    ├── SOP.md                   # 完整运营 SOP（内容规范/排版规范/发布流程/踩坑清单）
    ├── ARCHITECTURE.md          # 架构与数据流详解
    └── API_NOTES.md             # 微信公众号 API 踩坑笔记
```

## 运营成果

- 系统支撑下实现**连续日更**，单日 3 篇热点文章合并为一个草稿推送
- 累计产出 60+ 篇图文，篇均打开率 20%–30%
- 单篇内容生产耗时从 2–3 小时压缩至 30 分钟以内

## 快速开始

```bash
pip install -r requirements.txt
playwright install chromium

# 1. 配置凭据（或直接设置环境变量 WX_APPID / WX_APP_SECRET）
cp config/wechat_config.example.json config/wechat_config.json
vim config/wechat_config.json

# 2. 写文章（参考 templates/ 模板与 prompts/ 提示词）
cp templates/article_TEMPLATE_v2_统一.html articles/article_YYYYMMDD_pX_1_标题.html

# 3. 生成脑图 → 截图成 PNG
python3 scripts/gen_mindmap_from_article.py --article articles/article_sample.html --out mindmaps/sample.html
python3 scripts/html2png.py mindmaps/sample.html

# 4. 组批次配置 → 推送草稿箱
cp config/batch.example.json config/batch_YYYYMMDD_pX.json
python3 scripts/publish_3hotspot_single_draft.py --config config/batch_YYYYMMDD_pX.json
```

> 详细操作步骤见 `SKILL.md`；内容/排版/发布规范见 `docs/SOP.md`。

## 安全设计

- 所有凭据通过 `config/wechat_config.json`（gitignore）或环境变量注入，仓库内只有脱敏模板
- 登录态（storage_state）、access_token 缓存同样不入库
- `.gitignore` 对运行时产物（脑图/封面输出目录）统一排除

## License

MIT
