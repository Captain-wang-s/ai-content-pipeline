---
name: ai-content-pipeline
description: 一条从选题到微信公众号草稿箱的全自动内容生产线。当需要"写一篇公众号文章并推送草稿箱""生成文章配图/脑图""批量发布内容"时，按本 Skill 的 workflow 执行。
version: 1.0.0
entry: scripts/publish_3hotspot_single_draft.py
---

# AI Content Pipeline Skill

## 何时使用本 Skill

- 用户要求产出公众号文章并推送到草稿箱
- 用户要求为已有文章生成脑图 / 封面 / 金句图
- 用户要求按批次（一个日期 + 多篇文章）批量发布
- 用户要求刷新"往期推荐"数据源

## 前置条件（首次执行检查）

1. `config/wechat_config.json` 存在（从 `config/wechat_config.example.json` 复制并填写），
   **或**环境变量 `WX_APPID` / `WX_APP_SECRET` 已设置 —— 两者满足其一即可
2. `python3 -c "import requests, playwright"` 可用；不可用则 `pip install -r requirements.txt && playwright install chromium`
3. `assets/qrcode_gzh.jpg` 存在（脑图模板引用）

## Workflow：单日一批（1–3 篇文章 → 1 个草稿）

### Step 1 选题与写文
- 参考 `prompts/01-framework-shrink-refine.md`（先缩圈再精选选题框架）确定当日选题
- 复制模板 `templates/article_TEMPLATE_v2_统一.html` 开始写作，遵守 `docs/SOP.md` 的内容规范：
  - 开头第一行固定 `大家好，我是船长。`
  - 数据必须标注来源，不编造数据、不预测股价
  - 关注引导 + 星标提示由发布脚本自动注入，**不要手写进 HTML**

### Step 2 生成脑图（HTML → PNG）
```bash
python3 scripts/gen_mindmap_from_article.py \
  --article articles/article_YYYYMMDD_pX_1_标题.html \
  --out mindmaps/mindmap_YYYYMMDD_pX_1_标题.html
python3 scripts/html2png.py "mindmaps/mindmap_YYYYMMDD_pX_1_标题.html"
```
- 脑图规范：2 列 6 分支、每分支 3 个真实要点、`.tip` 必须非空（脚本自带自检输出）
- 要点可人工提炼：提供 `mindmaps/keypoints_<文章名>.json`（`{"branches": [...]}`）优先级最高

### Step 3 封面 / 金句图（可选，脑图可作默认封面）
```bash
python3 scripts/composite_ai_covers.py --help   # AI 封面合成
python3 scripts/html2png.py examples/*.html     # 通用截图
```

### Step 4 组批次配置
参考 `config/batch.example.json` 创建 `config/batch_YYYYMMDD_pX.json`，每篇文章至少给出：
`file / title / digest / mindmap(PNG) / cover(PNG)`；`theme_color` 与封面文案（cover_main/cover_sub）建议齐全。

### Step 5 推送草稿箱
```bash
python3 scripts/publish_3hotspot_single_draft.py --config config/batch_YYYYMMDD_pX.json
```
脚本自动完成：往期推荐刷新（可 `WX_SKIP_REFRESH=1` 跳过）→ token 获取/缓存 →
素材上传 → 样式内联 → 单草稿多图文 → 输出 draft_media_id。
推送后到 `mp.weixin.qq.com` 草稿箱预览，人工确认后再群发（本 Skill 不自动群发）。

### Step 6 质检
```bash
python3 scripts/check_draft_content.py   # 检查最新草稿中文渲染是否正常
```

## 失败处理

| 现象 | 处置 |
|------|------|
| 40164 IP 白名单 | 把本机出口 IP 加入公众号后台白名单，或改在白名单网络下运行 |
| token 获取失败 | 手动 curl token 接口后把结果写入 `config/wechat_access_token.json`（格式见脚本提示） |
| 往期刷新失败 | 非阻断，脚本自动用旧 CSV 继续；需要时单独跑 `scripts/fetch_wechat_published.py` |
| Chromium ERR_PROXY_CONNECTION_FAILED | html2png 已内置 `--proxy-server=direct://`；其他 Playwright 脚本同样处理 |
| END 图缺失 | 非阻断，自动跳过尾部图 |

## References

- [docs/SOP.md](docs/SOP.md) — 内容规范 / 排版规范 / 脑图规范 / 质检清单（权威，冲突时以 SOP 为准）
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 架构与数据流
- [docs/API_NOTES.md](docs/API_NOTES.md) — 微信公众号 API 踩坑笔记
- [config/batch.example.json](config/batch.example.json) — 批次配置字段说明
