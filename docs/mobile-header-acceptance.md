# 手机房间顶部验收

Ticket #16，基线 `6b327b0`。顶部保持房间号与在线状态可见，复制邀请直接可用；1140 CSS 像素及以下将切换房间与退出移入有名称的「房间操作／Room actions」菜单。桌面恢复原有按钮与主导航。没有修改房间授权、同步或邀请协议。

## 回归与复现

```sh
python -m unittest discover -v
node --test tests/locale.test.cjs
# 可选依赖：Playwright 与本机 Chrome，不需要 ffmpeg
python -m scripts.mobile_header_smoke --artifacts /tmp/mobile-header --output /tmp/mobile-header.json
```

Python 121 项、Node 2 项通过。浏览器机器可读结果见 [`evidence/mobile-header.json`](evidence/mobile-header.json)。测试启动临时 loopback 应用，以 `MOBILE16` 合成房间、合成昵称和第二位观众检查较长的英文 `2 online · Following`，使用真实词条，不替换占位英文。

- 中英文分别覆盖 320×740、390×844、844×390 横屏和 1440×900 桌面；房号、在线状态、复制邀请及菜单入口均在首屏内，无文本截断、控件重叠或首屏标题遮挡。横屏额外留白避免操作盖住标题上方小字。
- 移动复制邀请、菜单入口、切换和退出按钮均至少 44×44 CSS 像素。实际点击复制并读取剪贴板，验证邀请保留当前房号；切换后再次复制对应新房号。结果文件与截图不包含端口或邀请 URL。
- 触摸开合、外部触摸关闭；键盘 Enter／Space 开合、Tab／Shift+Tab 顺序、Tab 离开关闭、Escape 关闭并返回入口。打开原房间对话框后取消、提交切换均恢复入口焦点。退出独立分隔并用警示色区分。
- 实际切到新合成房间后成为房主，原房间人数回落；实际退出返回展厅，片库请求重新返回 401。桌面房间对话框、平铺退出按钮及中央主导航仍可达。无浏览器脚本错误。

## 前后对照

截图只包含自建临时房间及合成数据。以下链接为完整首屏，使用 WebP 压缩；不是逐像素快照比较，装饰场景和本机自动外观可能随时间变化。

| 语言／视口 | Before (`6b327b0`) | After |
| --- | --- | --- |
| 简中 320×740 | [前](evidence/mobile-header/before/zh-CN-320x740.webp) | [后](evidence/mobile-header/after/zh-CN-320x740.webp) |
| 简中 390×844 | [前](evidence/mobile-header/before/zh-CN-390x844.webp) | [后](evidence/mobile-header/after/zh-CN-390x844.webp) |
| 简中 844×390 横屏 | [前](evidence/mobile-header/before/zh-CN-844x390.webp) | [后](evidence/mobile-header/after/zh-CN-844x390.webp) |
| 简中 1440×900 | [前](evidence/mobile-header/before/zh-CN-1440x900.webp) | [后](evidence/mobile-header/after/zh-CN-1440x900.webp) |
| English 320×740 | [Before](evidence/mobile-header/before/en-US-320x740.webp) | [After](evidence/mobile-header/after/en-US-320x740.webp) |
| English 390×844 | [Before](evidence/mobile-header/before/en-US-390x844.webp) | [After](evidence/mobile-header/after/en-US-390x844.webp) |
| English 844×390 landscape | [Before](evidence/mobile-header/before/en-US-844x390.webp) | [After](evidence/mobile-header/after/en-US-844x390.webp) |
| English 1440×900 | [Before](evidence/mobile-header/before/en-US-1440x900.webp) | [After](evidence/mobile-header/after/en-US-1440x900.webp) |

菜单展开：[简中](evidence/mobile-header/after/zh-CN-320-menu.webp) · [English](evidence/mobile-header/after/en-US-320-menu.webp)。

## 限制

使用本机 Chrome 视口、触摸与剪贴板权限模拟，不代表 iOS／Android 真机、屏幕阅读器或生产部署验收；没有发布个人邀请、真实观众昵称或个人截屏。浏览器测试为可选命令，不增加默认 Python 套件的浏览器依赖。
