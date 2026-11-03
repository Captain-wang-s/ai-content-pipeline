# 微信公众号 API 踩坑笔记

长期真实运营中踩过的坑，按"现象 → 根因 → 解法"记录。

## 1. access_token 管理

- **现象**：每天多次发布时反复申请 token，偶发 `45009`（接口调用超限）。
- **解法**：token 缓存到 `config/wechat_access_token.json`（`expires_at = now + 7200`），
  剩余有效期 > 60s 直接复用；失效才重新申请并写回。
- **IP 白名单**：`40164` 表示调用 IP 不在白名单。固定出口 IP 并加入后台白名单，
  或在白名单网络下先手动 curl 拿 token 写入缓存文件。

## 2. 草稿接口 draft/add

- **封面校验在 draft/update 阶段**：`draft/add` 创建草稿对封面尺寸几乎不校验，
  但 `draft/update` 修改封面会报 `53401`（封面图片尺寸不合法），且对历史成功过的
  合规尺寸也拒绝——接口层已收紧。
- **正确姿势**：需要换封面时，不要 draft/update，而是**删旧草稿 + draft/add 重建**
  （复用 draft/get 拿到的正文，只换 thumb_media_id）。
- **thumb_media_id 必须先传素材**：封面/正文图都需先走
  `material/add_material?type=image`（永久素材）拿 media_id，再填进草稿。
  2.35:1（900×383）为封面安全比例，单图 <2MB。

## 3. 正文渲染限制

- **外链/内部样式全被剥离**：公众号编辑器只保留元素上的 `style` 内联属性，
  所以必须在上传前做 CSS→inline 转换（见 `scripts/inline_styles.py`）。
- **代码块会被压成一行**：`<pre>` 内的换行在某些客户端丢失，需要把 `\n`
  替换为 `<br>` 或用 `<p>` 模拟代码块（项目内的 fix_codeblock 系列脚本即为此服务）。

## 4. 后台数据爬取（Playwright）

- **appmsgpublish 接口要用"真实页面导航"调用**：用 `page.request` 或脱离页面的
  fetch 会返回 `200009`（cookie/token 不同步）。解法是登录后从跳转 URL 提取
  `token=<数字>`，再用 `page.goto(带token的接口URL)` 让浏览器自动带 cookie 访问。
- **登录态复用**：首次运行弹出二维码截图人工扫码，storage_state 存
  `config/wechat_login_state.json`，之后无需再扫。
- **macOS 死系统代理**：系统代理指向未启动的本地代理端口时，Chromium 全部请求报
  `net::ERR_PROXY_CONNECTION_FAILED`。实测唯一有效解法是
  `chromium.launch(args=["--proxy-server=direct://"])`；
  `NO_PROXY=*`、`--no-proxy-server` 等均无效。

## 5. 素材管理

- **media_id 可长期复用**：END 尾图、二维码等固定素材传一次永久素材即可，
  media_id 记下来重复用，不必每次发布重传。
- **脑图以 PNG 提交**：HTML 脑图先经 Playwright 截图为 PNG（900px 宽、full_page），
  再上传。PNG 过大会拖慢上传，控制在 500KB 以内。

## 6. 草稿与群发的边界

- 本项目**只推送到草稿箱**，群发永远人工在后台确认后执行——自动化负责生产，
  人负责最终把关。
- `draft/count` + `draft/batchget` 可做发布后自检（`check_draft_content.py`），
  重点检查中文是否被转义、图片链接是否可访问。
