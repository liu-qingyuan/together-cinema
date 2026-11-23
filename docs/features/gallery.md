---
{
  "paths": [
    "index.html",
    "server.py",
    "assets/scenes/v1-sky-*.webp",
    "assets/scenes/v1-galaxy-*.webp",
    "assets/scenes/sources.json",
    "assets/scenes/LICENSE-CC-BY-4.0.txt",
    "test_distribution.py",
    "scripts/gallery_smoke.py",
    "scripts/gallery_visual_smoke.py"
  ],
  "fingerprint": "sha256:b164ac9aeb70b0f66911aae40354d85beca5225dded02416d0cd21170085e717"
}
---

# 展厅与放映室入口

## 当前行为

普通 `/` 展示随部署提供的「动漫天空」封面、陪伴文案、房间码入口和下滑可达的片库区域。可在本页预览「雪山银河」，不保存个人主题或修改全站状态。天空在云间排字；银河桌面图旁排字，手机宽度下在入房表单后保留完整 2:3 竖幅照片，不横裁或遮挡主体。保留会话时可只读浏览私人片单；无授权会话时只显示权限提示。浏览展厅不登录、不建立房间连接、不加载影片。

`/?room=AB` 邀请自动沿用原房间码登录校验，成功后直达对应放映室；无效邀请停在入口并提示，可修改房间码重试，不回退到记住的房间。进入放映室后展厅装饰动画与滚动动画停止，即使影片暂停也不恢复。退出返回普通入口并清除授权会话。

封面图片为 Unicorn Creates 和 oliwok 的 CC BY 4.0 作品，署名、来源及裁切／压缩说明随 `assets/scenes/sources.json` 和许可文件部署，不重标 MIT。只请求当前预设对应的桌面或手机派生图，邀请不下载展厅封面，入房移除封面图片来源。玻璃仅增强入房卡和预览按钮，基础样式不透明；减少透明度或无滤镜增强时保留可用表单，文字、影片、字幕和诗句不叠玻璃。

播放器、聊天、弹幕、语音及房间同步沿用原实现。`scripts/gallery_smoke.py` 在本地 Compose 实例上通过两个独立浏览器进程验证入口、授权隔离和生成短片的同步播放／暂停／跳转，并清理自有测试影片。`scripts/gallery_visual_smoke.py` 验证两种构图的资源选择、焦点和片库滚动，以及减少动态／透明度和基础静态 CSS 下的真实入房；截图与明确未验收项见 `docs/gallery-visual-acceptance.md`。

## 限制与剩余

全站共享封面上传／选用／删除尚未提供；本票预览只影响当前页面，不是共享状态。两种正式素材与响应式构图已提供，但真机美术与实际不支持滤镜的引擎验收仍待人工补齐；本机历史配对 iPhone 当前不可用，因此 #4 保持 open。片库权限仍是受信任好友共享模型；房间码不是密码，也不是房间间的媒体隔离。片单在打开展厅时读取，不实时刷新。

浏览器测试需要可选的 Playwright、Chrome（或已安装的 Chromium）和 ffmpeg；不纳入无浏览器依赖的 unittest 默认命令。390×844／320×568 模拟、偏好模拟及移除可选增强规则的基础 CSS 检查，不构成手机实机或实际无滤镜引擎验收。
