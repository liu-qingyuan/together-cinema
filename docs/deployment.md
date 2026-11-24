# 部署与日常维护

## 前置条件

- Docker Engine / Docker Desktop 与 Compose v2；需要支持 `up --wait`。
- 安装器不通过 curl管道执行远程脚本，不自动 sudo安装Docker，不改宿主防火墙、SSH、代理或系统sysctl。
- 检查 `docker context show`：命令作用于你选中的 Docker 引擎。我们不会偷偷切换 context。
- 默认从源码构建 Python3.13+FFmpeg。核心镜像支持上游 Python/FFmpeg 提供的平台；解析镜像选择固定校验和的 Node linux-x64/arm64。实测平台以发布验证记录为准，不把双架构源码分支当作双架构实测。

## 本机／公网

`./install.sh` 只发布127.0.0.1:8080。命名数据卷由镜像预建目录初始化成UID10001所有，不需要对宿主目录递归chown。

公网执行 `./install.sh --domain cinema.example.com`：启用Caddy，签发证书并用 Basic Auth保护整个站点（包括媒体和WebSocket握手）。`.env` 的 `WATCH_PASSWORD` 是内部签名/解析器密钥，不是房间密码；`SITE_PASSWORD` 是网关访问口令。二者首次生成后不被重复安装重置。安装器不把它们写进日志。

DNS、80/443端口和证书签发依赖真实网络。显示Ready表示Compose健康检查完成，不保证DNS已经传播或证书签发完成。可查看 `docker compose logs --tail=100 https`。Basic Auth不要用于明文公网HTTP。

已有反向代理时可保留本机监听，由自己的HTTPS代理转发8080，并自行配置访问保护、WebSocket和流式传输。应用与原站中转不能等同于通用开放代理。

## 可选网络解析

`./install.sh --network` 将network加入`.env`的`COMPOSE_PROFILES`。禁用时编辑该字段删除network，然后 `docker compose --profile network stop extractor`，再运行安装器；停止不删除数据。初次下载浏览器镜像可能很慢，核心本地视频不需要它。

Linux须允许Docker内非特权用户命名空间；我们不关闭Chromium沙箱，不使用privileged，不自动改宿主内核安全策略。遇到不支持的宿主环境应拒绝解析，上传/本地播放仍可用。

既有约束：解析一次一个任务，35秒；浏览器单次响应2MiB、总响应预算16MiB、120请求、4并发；提取后关闭上下文并清理子进程。512MiB是解析器整个容器上限，不是永久占用量。空闲不足512MiB时拒绝启动浏览器。动态网页的复杂跳转可能失败关闭；登录、验证码、DRM无绕过支持。

共享分片缓存16MiB是payload/预留预算，不是整个进程RSS；单分片上限2MiB，45秒过期。过大分片直接流式转发；未播放候选源120秒到期。结束、切换、房间无人等释放来源。源站仍可能因签名、Header、地区、编码限制而不可播放。

## 语音（外部TURN）

语音采用WebRTC，公网麦克风需要HTTPS。填写：

```dotenv
WATCH_TURN_URLS=turn:turn.example.com:3478?transport=udp
WATCH_TURN_SECRET=YOUR_TURN_SHARED_SECRET
```

该secret必须与外部TURN服务的 `static-auth-secret` 一致。然后运行 `./install.sh` 更新应用环境。默认未配置TURN，前端会提示语音未启用；不宣称默认能穿透任意运营商网络。本项目不自动安装TURN或开放大量UDP端口，避免不清楚公网IP/NAT时做错误设置。文本聊天不依赖TURN。

## 数据／转换／空间

命名卷`media`存储影片、字幕、转换任务与弹幕历史；房间与在线聊天状态主要在内存。默认预留2GiB不是被占用文件，而是拒绝写满的阈值。转换还需要源文件+输出并存的空间，处理失败的源文件可以从任务中清理。

H.264和常见SDR H.265可能仅换封装/转音轨，兼容视频不会无损变小；其他视频按现有策略最高720p。终端能否解码H.265仍取决于设备。大文件四路分片上传不是跨刷新断点续传，上传中请保持页面打开。

## 升级／卸载

1. 等大家观看结束，查看新版本变化。
2. `git pull --ff-only && ./install.sh`，只更新当前源码，不强制reset用户修改。
3. `docker compose ps` / `docker compose logs --tail=100 watch`检查。

`./uninstall.sh`只停本项目容器，保留数据和`.env`；`./uninstall.sh --purge-data --yes`会永久删除本项目全部命名卷，包括影片和HTTPS证书。无自动备份、镜像导出、全局prune，也不会触碰其他Docker项目。宿主想回收构建镜像时应按项目/ID自行确认，不提供一键清空整台Docker主机的脚本。

### Optional automatic multi-connection uploads

On a long-latency route, several HTTP/1.1 connections can outperform multiple
chunks multiplexed on one HTTP/2 connection. This does not increase the ISP's
bandwidth limit. To enable this **for uploads only**, install
[the Nginx example](../deploy/upload-http1.nginx.example) for your own domain,
certificate and loopback backend. Expose its dedicated TLS port (8443), validate
and reload Nginx, then set `UPLOAD_HTTP1_PORT=8443` and recreate the watch
service **when no upload is active**. This requires direct HTTPS connectivity
to the same hostname on both ports, a secure session cookie and strict origin
matching. Never point it at another service. Without a configured port the
normal single-origin uploader remains unchanged.

普通浏览器选中大文件后会探测高速入口，成功才显示「多连接上传」。选片、登录和
播放仍走原站；高速端口不可用时，同一上传会话退回普通入口，不重传已确认分片。
刷新网页仍不能断点续传。取消配置并重建 watch 即可停用，之后可移除独立监听。
