# 当前代码地图

这是一份源码导航，不是部署迁移方案。首次了解系统请看[现行架构：同步控制与媒体流](architecture/current.md)（[English](architecture/current.en.md)）。第一方后端集中在 `cinema/` Python 包；网页和静态资源集中在 `web/`（`index.html`、`assets/`、可选动效的 `comfort-motion/` 构建输入）。根目录保留安装、Compose 和镜像构建入口；没有新增部署进程。测试和测试素材集中在 `tests/`，不再按测试层级细分。目录整理的历史基线见下方记录；当前播放规则由下列运行入口拥有。

## 怎么运行与验证

- 使用／部署：从仓库根运行 `./install.sh`，细节见[部署指南](deployment.md)。[Compose](../compose.yml) 的 `watch` 从源码构建应用镜像，入口为 `python -m cinema.server`（[`server.py`](../cinema/server.py) 的 `create_app()`）；`converter` 复用该镜像，独立运行 `python -m cinema.conversion`（[`conversion.py`](../cinema/conversion.py)）。可选 `network` profile 以 `python -m cinema.extractor` 启动解析器，`https` profile 启动访问网关。网页由后端的 `WEB_DIR` 定位，不依赖进程 cwd；`/`、`/assets/`、`/scenes/`、`/room-art/` 与 `/data` 挂载不变。
- 贡献／回归：Python 3.13（与 CI 一致）、系统 `ffmpeg`／`ffprobe`，安装 `requirements.txt`。从仓库根运行：

  ```sh
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -r requirements.txt
  python -m unittest discover -v
  ```

  完整执行还需要 Docker 的 Compose v2 CLI；两项 Compose 结构检查只解析配置，不需要 Docker daemon，无 CLI 时原有测试会跳过。安装器测试使用临时目录与假 Docker CLI；真实构建／启动是单独的验收。测试使用临时数据目录，不连接个人部署。
- 聚焦某项职责，例如：`python -m unittest -v tests.test_rooms tests.test_interactive`。`tests/__init__.py` 保证根目录原命令可递归发现测试；无需设置 `PYTHONPATH` 或在测试中修改 `sys.path`。

## 谁拥有规则，从哪验证

| 职责 | 入口与规则归属 | 对应测试 |
| --- | --- | --- |
| 播放与房间同步 | [`web/index.html`](../web/index.html) 的 `control()` 发送操作，`connect()` 接收消息，`apply()` 应用快照；[`server.py`](../cinema/server.py) 的 `Room.update()` 校验房主操作，`snapshot()` 计算进度，`set_rate()`／`set_boost()` 管理基础倍速与临时加速。`invalidate_source()` 统一处理当前片源失效：清片、暂停、进度保持为零，退出临时加速并恢复已选基础倍速；其他片源或重复通知不改变播放。本地删除与网络回收只报告失效，仍各自拥有清理和广播。`create_app()` 内 `websocket()` 是 `/ws` 入口，负责成员、房主交接和广播。 | [`test_server.py`](../tests/test_server.py) 的 `RoomTests` 与 WebSocket 同步／交接；[`test_rooms.py`](../tests/test_rooms.py) 的房间隔离、倍速与清理；[`test_interactive.py`](../tests/test_interactive.py) 的加速、弹幕存储和交互协议；[`test_source_unavailable.py`](../tests/test_source_unavailable.py) 经双成员 WebSocket 验证两条失效路径、迟到／重复通知及跨房间隔离。 |
| 共享片库 | [`server.py`](../cinema/server.py) 的 `files()`／`library()` 列出已发布影片，`stream()` 提供媒体，`publish_upload()` 决定直接入库还是排队，`delete_video()` 删除影片及关联字幕／弹幕并刷新片库。[`parallel_upload.py`](../cinema/parallel_upload.py) 的 `ParallelUploads` 拥有分片校验、组装、容量与到期清理；前端入口是 `index.html` 的 `library()` 和上传处理。片库全站共享，房间码不是媒体权限隔离。 | [`test_server.py`](../tests/test_server.py) 的上传、Range、删除和安全路径；[`test_parallel_upload.py`](../tests/test_parallel_upload.py) 的分片与清理；[`test_room_entry.py`](../tests/test_room_entry.py) 的入房授权与片库访问。 |
| 转码与字幕 | [`conversion.py`](../cinema/conversion.py) 的 `enqueue()`／`work_once()` 管任务队列，`conversion_command()` 决定保留视频、转音轨或视频转码，`process_job()` 运行 FFmpeg 并发布完成品。[`subtitles.py`](../cinema/subtitles.py) 提取和列出字幕、定位原始轨道；`server.py` 的转换路由提供查询／取消。未完成输出不进入片库。 | [`test_mkv.py`](../tests/test_mkv.py)、[`test_avi.py`](../tests/test_avi.py) 从根目录实际启动 `cinema.conversion` 转换子进程并检查输出；[`test_subtitles.py`](../tests/test_subtitles.py)、[`test_original_pgs.py`](../tests/test_original_pgs.py) 验证文字／图片字幕提取及私有 HTTP 读取。PGS 样本随测试保存在 [`fixtures/test.sup`](../tests/fixtures/test.sup)。 |
| 网络片源 | `server.py` 的 `network_resolve()` 等 `/api/network/` 路由连接房间与 [`external_media.py`](../cinema/external_media.py) 的 `ExternalMedia`；后者拥有 URL 安全校验、来源存活／回收、中转和 `SharedFragments` 缓存。可选 [`extractor.py`](../cinema/extractor.py) 通过 `python -m cinema.browser_resolver` 调用 [`browser_resolver.py`](../cinema/browser_resolver.py) 探测动态网页；前端通过 `setPlaybackSource()` 选择本地／网络播放方式。 | [`test_external_media.py`](../tests/test_external_media.py) 的来源、安全与 HTTP 生命周期；[`test_dynamic_media.py`](../tests/test_dynamic_media.py) 的动态解析／网关／子进程；[`test_shared_fragments.py`](../tests/test_shared_fragments.py) 的共享缓存、并发、预算与清理。 |
| 本机界面语言 | [`locale.js`](../web/assets/locale.js) 拥有语言解析、本机偏好、文本绑定与日期格式，[`locale-messages.js`](../web/assets/locale-messages.js) 保存简中／英文词条。页面、导航、手记与风景只调用呈现接缝；切语言不进入房间协议或播放器生命周期。后端错误保留旧正文并附稳定标识。 | [`test_locale.py`](../tests/test_locale.py) 经默认回归检查字典／插值／引用及 HTTP／WS 错误兼容；`node --test tests/locale.test.cjs` 检查选择／回退；`python -m scripts.locale_smoke` 用临时短片、字幕与两独立上下文验证播放中切换，证据见 [`locale.json`](evidence/locale.json)。 |
| 放映记录 | `server.py` 的 `websocket()` 在房主开始播放时调用 [`watch_history.py`](../cinema/watch_history.py) 的 `WatchHistory.record()`；`film_title()` 取得片名，`list()` 按房间读取有界持久记录。[`web/assets/memory-reel.js`](../web/assets/memory-reel.js) 的 `renderMemory` 展示真实片单，无记录时展示明确标注的示例；不从上传时间补历史。 | [`test_watch_history.py`](../tests/test_watch_history.py) 的 `ScreeningLedger` 验证持久化与数量上限，`ScreeningEvents` 经 WebSocket 验证开场、续播、再次观看与房间隔离。 |

其余测试：[`test_covers.py`](../tests/test_covers.py) 验证展厅封面读写、失败清理与播放隔离；[`test_distribution.py`](../tests/test_distribution.py) 验证静态资源与安全头；[`test_install.py`](../tests/test_install.py) 验证真实安装器／卸载入口及 Compose 配置；[`test_release_live.py`](../tests/test_release_live.py) 验证生产发布的验收顺序与定向回收。浏览器验收脚本独立放在 [`scripts/`](../scripts/)，所需额外依赖与运行方式见[贡献入口](../README.zh-CN.md#开发与贡献)，不混入默认 unittest。[`runtime_layout_smoke.py`](../scripts/runtime_layout_smoke.py) 在隔离安装上生成待转换 MKV、等待真实转换，再播放 MP4 并检查原字幕；`--keep-upload` 可种入临时旧卷，更新后 `--existing` 验证同片。只用于本机临时部署，运行证据及未覆盖范围见[目录迁移验证](evidence/runtime-layout.json)。

## 整理后的对照基线

[#8](https://github.com/liu-qingyuan/together-cinema/issues/8) 于 **2026-11-24** 整理目录，来源为父规格固定的 `7b302b203b8dde4a23dcdc7ae5ff06dc1e0b07d1`。迁移前后都从根执行 `python -m unittest discover -v`：**110 项通过，无跳过**。逐项只去掉新增的 `tests.` 模块前缀后比较：无缺失、无新增、无重复。17 个测试文件整体迁移；图片字幕样本字节不变，转换子进程和安装器仍调用根目录真实入口。完整身份清单和环境记录见[机器可读基线](evidence/test-layout.json)。这份日期化证据用于后续播放行为变更的对照，不是永远有效的测试总数。

[CI](../.github/workflows/ci.yml) 保持同一根目录命令；[Docker 构建排除](../.dockerignore) 现在排除整个 `tests/`。弹幕和展厅的[当前功能记录](features/)引用新测试位置；迁移后需复核指纹并执行 `./.feature-docs/run check --staged`（提交后 `check --ref HEAD`）。

上述 #8 历史基线未做浏览器、真机或线上播放验收；当时应用镜像重建因 Docker Hub token 请求 `EOF` 受阻，只完成构建上下文检查。这不是当前构建状态。后端／网页目录迁移的隔离安装与旧卷升级证据见 [#13](https://github.com/liu-qingyuan/together-cinema/issues/13)；不代表线上或真机验收。

## 文档分工

- 当前运行全景：[现行架构](architecture/current.md)（[English](architecture/current.en.md)），区分同步控制、媒体流、后台转换与本机偏好；本地图继续负责源码和测试导航。
- 当前使用方式：[部署指南](deployment.md)、[安全边界](../SECURITY.md)、[兼容性限制](compatibility.md)、[发布流程](releasing.md)。源码版本和变更统一以 [GitHub Releases](https://github.com/liu-qingyuan/together-cinema/releases) 为准；安装器从源码本地构建，不提供预构建应用镜像。
- 当前已实现能力：[feature 记录](features/gallery.md) 与[弹幕记录](features/danmaku.md)，不是每轮补丁日志。
- 历史设计：[首个可分发版本规格](SPEC.md)、[私人部署到可分发项目的迁移设计](architecture.md)。其中 “Current”／“Target” 是设计当时的前后状态。
- 历史验证：[Alpha 发布验收](validation.md)、[共享封面验收](cover-acceptance.md)、[展厅画面与真机待办](gallery-visual-acceptance.md)。保留当时的测试数和画面，不能代替当前回归或未完成的真机验证。
