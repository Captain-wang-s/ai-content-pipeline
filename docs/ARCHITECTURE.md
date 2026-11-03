# 架构与数据流

## 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        内容生产层                            │
│                                                             │
│  选题CSV(data/topic_history)                                │
│      │                                                      │
│      ▼                                                      │
│  Prompt模板库(prompts/) ──► LLM ──► 文章HTML(articles/)      │
│      运营SOP(docs/SOP.md)约束内容质量与合规                    │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                        配图生产层                            │
│                                                             │
│  gen_mindmap_from_article.py                                │
│    抽取文章标题结构 → 渲染6分支脑图HTML → html2png.py 截图    │
│                                                             │
│  composite_ai_covers.py                                     │
│    AI生成底图 + 标题文案合成封面 / 金句图                     │
│                                                             │
│  crop_illustration_v7.py                                    │
│    裁掉AI出图底部水印带                                       │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                        发布层（publish 脚本）                 │
│                                                             │
│  批次JSON(config/batch_*.json)                               │
│    1. refresh_related_articles()  往期推荐CSV刷新(可降级)     │
│    2. token管理：缓存读取 → 过期重取 → 写回缓存               │
│    3. 每篇文章：脑图/封面/金句图 add_material 上传            │
│    4. inline_css()  CSS→内联样式(公众号限制)                  │
│    5. 组装多图文 → draft/add 单草稿提交                      │
│    6. 输出 draft_media_id → 人工预览群发                     │
└─────────────────────────────────────────────────────────────┘
```

## 关键设计决策

### 1. 批次 JSON 作为发布驱动
一个发布批次 = `config/batch_YYYYMMDD_pX.json`：声明当日 N 篇文章的文件、标题、摘要、
主题色、配图路径。发布脚本只认这个单一真相源，做到「改配置不改代码」。

### 2. 脑图以 PNG 为素材边界
脑图的**生成**走 HTML（浏览器渲染自由度高、样式可控），但进入发布链路的素材统一是
PNG。HTML 只是中间产物，发布脚本上传的是 `add_material(type=image)` 的二进制图片。

### 3. 样式必须内联
公众号编辑器会剥离 `<style>` 标签与 class，因此所有文章 HTML 在上传前经过
`inline_styles.inline_css()` 把 CSS 规则展开为每个元素的 `style` 属性。
文章模板（templates/）因此可以正常用 class 写作，发布时才做转换。

### 4. 凭据与代码分离
- `WX_APPID` / `WX_APP_SECRET` 环境变量优先，其次 `config/wechat_config.json`（gitignore）
- access_token 缓存 `config/wechat_access_token.json`，7200s 内复用，避免重复申请触发限频
- Playwright 登录态 `config/wechat_login_state.json`，一次扫码长期复用

### 5. 优雅降级链
发布链路上所有"锦上添花"步骤（往期推荐刷新、END 尾图、金句图）失败均不阻断主流程：
失败 → 打印告警 → 用降级产物继续 → 保证"文章一定能进草稿箱"这一核心承诺。

## 平台扩展点

`html2png.py` 是通用截图工具（900×1200 viewport + full_page），
配合不同平台的登录自动化脚本即可扩展到 CSDN / 掘金等平台的自动发布；
`--proxy-server=direct://` 已内置，规避 macOS 死系统代理导致的 Chromium 连接失败。
