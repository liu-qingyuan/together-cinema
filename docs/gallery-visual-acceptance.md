# 展厅视觉验收：历史证据与真机待办

记录于 **2026-11-23**，对应提交 `4a21274`；以下画面和“已实现”描述是当时快照（包括原六套个人主题），不代表当前全部外观。当前代码与测试见[代码地图](code-map.md)，待办状态以关联 issue 为准。

对应 [#4](https://github.com/liu-qingyuan/together-cinema/issues/4)。**尚未完成真机验收，不应据此关闭 Ticket。**

## 已实现

- 「动漫天空」用蓝天云间排字；「雪山银河」桌面在完整 2:3 照片旁排字，手机宽度下先提供入房表单，再展示完整竖幅山峰和帐篷，不横裁、不用文字遮挡主体。
- 顶部两按钮只在本页预览内置封面，不保存个人主题、不修改全站状态。全站共享封面属于 #5；原六套放映室个人主题仍独立。
- 玻璃只增强入房卡和预览按钮。默认是有边框的不透明表面，仅支持滤镜且未请求减少透明度时开启模糊。标题、陪伴文字、影片、字幕和诗句不加玻璃。
- 图片随 Docker 部署，不访问外部图库。`picture` 在 ≤800 CSS px 选手机派生图，其余选桌面图；只加载当前选中的预设。入房移除图片来源，避免播放中因旋转屏幕再请求展厅图。邀请不下载展厅图。
- 作品归属与改动：[素材清单](../web/assets/scenes/sources.json)、[第三方说明](../THIRD_PARTY_NOTICES.md)、[CC BY 4.0](../web/assets/scenes/LICENSE-CC-BY-4.0.txt)。天空来自 Unicorn Creates；银河照片来自 oliwok。不得把它们标成 MIT。

## 实际浏览器画面

本地专用 Compose `cinema-ticket4`，Chrome，桌面 1440×1000；手机列为 **390×844 模拟视口**，不是实机。均为整页截图，显示入房链接的键盘焦点。PNG 经 WebP quality 90 压缩，未裁切或拼接。画面含上述 CC BY 4.0 作品，署名与改动同素材清单；截图框架由 Together Cinema contributors 添加。

| 预设 | 桌面实际浏览器 | 手机视口模拟（不能替代实机） |
|---|---|---|
| 动漫天空 | [桌面画面](evidence/gallery/sky-desktop-focus.webp) | [模拟画面](evidence/gallery/sky-mobile-emulation-focus.webp) |
| 雪山银河 | [桌面画面](evidence/gallery/galaxy-desktop-focus.webp) | [模拟画面](evidence/gallery/galaxy-mobile-emulation-focus.webp) |

[浏览器断言结果](evidence/gallery/report.json)：四个组合的可见焦点、无横向溢出、下滑片库、视口对应资源；两套亮／暗表面均在减少动态、减少透明度和基础静态 CSS 下实际入房。静态检查通过删除可选 `@supports` 增强规则验证基础样式，**不等同于使用不支持滤镜的真实引擎**。另有 320×568 窄视口检查。没有 mock 本站请求。

可重现命令（本地专用实例；不要在真实用户房间执行）：

```sh
pip install -r requirements.txt playwright
python -m unittest discover -v
python scripts/gallery_visual_smoke.py http://127.0.0.1:18884 --artifacts /tmp/gallery-visual
python scripts/gallery_smoke.py http://127.0.0.1:18884 --artifacts /tmp/gallery-playback
```

两脚本分别触发多次真实入房，连续运行可能触发原有登录限流；等窗口结束或只重启专用测试实例再跑，不关闭限流。后者用两个独立浏览器播放自己生成的短片，验证同步播放／暂停／跳转及展厅不请求影片，结束后清理自有测试影片。

## 待人工完成

环境检查有一台历史配对的 iPhone 15，但 `xcrun devicectl list devices` 为 `unavailable`，USB 也未连接手机。因此没有手机实机截图，未冒充通过四组正式画面验收。

1. 连接可用手机，以实际 Safari／Chrome 打开维护者授权的测试部署；不要为了截图将默认仅本机部署擅自暴露公网。
2. 分别选择两预设。记录手机型号、系统、浏览器版本、方向、URL 对应提交与日期，提交两组**实机**画面（首屏和必要的下滑画面），替换上表的待验收依据。
3. 检查文字、输入和键盘焦点清楚；入口明显；山峰／云层主体未被遮挡；屏幕键盘弹出和旋转后能继续输入，下滑到片库。银河完整照片在表单下方，需要真实滚动检查。
4. 开启设备减少动态／降低透明度，分别在亮、暗预设入房；在不支持 `backdrop-filter` 的实际环境核实不透明回退。自动化仅证明静态设计和偏好分支，不代替此兼容性记录。
5. 进入放映室播放／暂停影片，确认展厅动效不恢复、原同步正常。若发现视觉缺陷，记录截图和最小修改要求，再交回 agent。

在上述真实设备证据补齐并获确认前，#4 保持 open。
