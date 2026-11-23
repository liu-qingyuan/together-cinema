# 共享展厅封面：当前验收证据

对应 [#5](https://github.com/liu-qingyuan/together-cinema/issues/5)。全站封面与房间播放、字幕、语音和个人主题独立。

## 自动化验证

- `python -m unittest discover -v`：96 项通过。其中 `test_covers.py` 经公开 HTTP／WebSocket 验证访客读取、活动成员写入、登录 cookie 单独写入被拒、连接关闭凭据撤销、同源限制、跨应用重启读取、失败清理、选用、删除回退和房间播放隔离。
- 上传可接受静态 JPEG／PNG／WebP，至多 8 MiB、800 万像素。校验失败、上传过大、磁盘不足、发布目录状态失败均保留原图，并清理本次源图、派生图及临时目录。内置预设不可删除。
- 专用本地 Compose `cinema-ticket5`（watch + converter，非真实用户部署）成功构建并启动非 root 容器；`scripts/covers_smoke.py` 使用两独立 Chrome 进程和额外无会话访客，上传生成的带真实文字字幕的 MKV，经正常转换后播放。
- 双成员先建立 WebRTC 通话，再执行上传并选用、切到预设、切回已有图、第二次上传、失败上传、删除非当前图和删除当前图。每步断言两个播放器 `currentSrc` 不变、`loadstart/emptied` 为零、仍在播放且进度增长、字幕选择及实际字幕 cue 保留、个人主题不变；每个既有 RTCPeerConnection 保持同一对象及 connected 状态，音轨保持 live，操作前后实际接收音频字节增长。最后一次运行双端进度差为 0.018～0.023 秒，零页面运行错误。
- 无会话写入返回 401；仅登录但不连接房间返回 403。独立访客刷新读取同一自定义图，删除当前图后刷新可加载天空预设；没有假造本站请求。
- 自定义图片在桌面及 390×844 模拟视口无横向溢出，入房链接可见。`gallery_smoke.py` 原入口／同步播放回归和 `gallery_visual_smoke.py` 两种内置预设／静态回退／邀请不下载封面回归均通过。

[机器可读结果](evidence/covers/report.json)，[操作后放映室](evidence/covers/screening-after-cover-delete.webp)，[自定义封面桌面](evidence/covers/custom-desktop.webp)，[手机视口模拟](evidence/covers/custom-mobile-emulation.webp)。图片来自脚本生成的测试图和测试片，PNG 仅压缩为 WebP（quality 90），不裁切、拼接。

## 重现

仅在隔离的本地测试实例执行，避免改动真实用户的封面。依赖 ffmpeg、Chrome 和可选的 Playwright：

```sh
pip install -r requirements.txt playwright
# 启动 watch + converter；本地测试环境配置非空 WATCH_TURN_SECRET，
# WATCH_TURN_URLS=stun:127.0.0.1:9 可使用本机 host candidate，非生产 TURN 配置。
python scripts/covers_smoke.py http://127.0.0.1:18885 --artifacts /tmp/covers-smoke
python scripts/gallery_smoke.py http://127.0.0.1:18885
python scripts/gallery_visual_smoke.py http://127.0.0.1:18885 --artifacts /tmp/gallery-regression
```

脚本仅清理自己生成的影片和封面并恢复原选择；登录限流保持启用。连续大量重跑需等待限流窗口，或只重启专用测试实例。浏览器测试不进入默认 unittest 命令。

## 明确限制

语音使用 Chrome 模拟测试麦克风提供音源，实际协商与音频传输未 mock；不声称验证了真实麦克风、异地网络或生产 TURN。手机列是视口模拟，不是实机，#4 的正式美术与真机待办不因此完成。封面更新不推送已打开的访客页，访客需要刷新；不提供图片编辑器、动画封面或原图公开下载。
