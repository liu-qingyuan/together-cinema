# 公开双语观众指南验收

Ticket #15，基线 `1754920`。公开入口为部署站点的 `/help/zh-CN.html`、`/help/en.html`；不提供独立托管地址，也不把仓库文件预览当作部署站点。指南无需房间会话；部署者的站点级访问密码仍适用于整个站点。

## 自动回归

```sh
python -m unittest discover -v
node --test tests/locale.test.cjs
# 可选：Playwright、Chrome 与 ffmpeg
python -m scripts.guide_smoke --output docs/evidence/guide.json
python -m scripts.locale_smoke
```

根套件 121 个测试通过，Node 2 个测试通过。`tests/test_help.py` 验证匿名中英页面／样式、互链、白名单、无会话副作用与展厅／放映室新标签页入口。解析服务连接失败的回归测试先复现 500，再验证已有 `network_resolve_failed` 标识及当前房间影片和进度不变；仅补捕获 `aiohttp.ClientError`，不改变解析协议。

## 双端网络片源与帮助

机器可读结果见 [`evidence/guide.json`](evidence/guide.json)，使用两个独立 Chrome 上下文（English／简中），全部为临时生成、自有可共同播放的素材：第一段红色／440Hz，第二段蓝色／660Hz，网页以两个 `<video>` 显式给出顺序和标题。

- 公开展厅打开英文帮助、切中文后仍未入房；进入同一房间播放本地样片后打开帮助，原页零媒体重载、重连或控片指令，进度继续，两端语言不变。
- 直连解析返回两个候选，不自动改片；房主先暂停原片，明确点击第二段并播放，两端片名为原始「网页视频 2」并显示本机模式文字，暂停／续播一致。两端浏览器请求 `https://media.example/two.mp4`，未取第一段。
- 阻断成员浏览器访问该 origin，并用实际浏览器 fetch 确认失败；服务器仍可取流。重新解析为中转、再次明确选第二段，两端媒体请求均为本站 `/api/network/<source>/play`，无成员原站请求，仍可播放和同步暂停／续播。
- 可选解析服务关闭、启用但无候选时，显示对应本机语言的下一步提示，结果列表为空且当前影片和播放不变。额度不足／过期用真实 HTTP 探针验证 429／410 和稳定错误标识，不改当前选片；指南给出等待、重解析、改合法直连或上传自有文件的路径。
- 本地影片的语言／原文字幕／聊天／弹幕不变复用 `scripts.locale_smoke` 回归，结果通过。

测试只把保留域名 `media.example` 的传输映射到本地 HTTP fixture，真实解析、候选、播放和中转仍走应用；公开 HTTPS 地址校验不放宽。结果不代表公开 origin 的 DNS／TLS、外网 provider 或生产部署。未验证播放途中耗尽额度；指南未承诺自动恢复或自动换模式。切片前先暂停，避免把自动续播行为当作选片确认。

## 干净安装与原路径升级

结果见 [`evidence/guide-distribution.json`](evidence/guide-distribution.json)。在两个临时目录使用独立 Compose project、仅绑定本机的独立端口和临时数据卷；没有触碰现有站点。清除进程中会覆盖 `.env` 的部署环境变量后执行原 `./install.sh --port <port>`：

1. 干净源码加本次变更，从新卷安装，匿名请求两种帮助和样式，核对返回字节与源码一致；从展厅点击新标签页帮助可用。
2. 另从基线 `1754920` 安装（帮助页为 404），通过公开上传入口写入合成影片，并放入带原文 cue 的 VTT／tracks 数据，记录媒体字节及 `.env` 的校验值。
3. 原目录替换为本次源码，仍用原 `./install.sh` 重建；保留同一 project、卷和 `.env`。两种帮助与样式可匿名读取，影片字节和原字幕不变、`.env` 不变。
4. Chrome 实际进入升级后的房间，播放原影片、显示原文字幕，再打开房间内帮助，零媒体重载且播放／字幕继续。
5. 两种指南在 320 CSS 像素宽下切换检查，无页面横向溢出。该检查不是放映室顶部导航或手机真机验收。
6. 只对两个本次创建的 Compose project 执行 `down --volumes`，不做全局 prune，不删除其他项目数据。

没有验证线上发布、外部 HTTPS 网关或手机真机；中英仓库首页读者路径和手机房间导航分别由后续 Tickets 交付。
