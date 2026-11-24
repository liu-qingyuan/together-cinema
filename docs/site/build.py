"""Build only public documentation; never publish the application directory."""
from pathlib import Path
import shutil
import sys
from string import Template

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = "https://github.com/liu-qingyuan/together-cinema"
COPY = {
    "en": dict(title="Different places. The same moment.", lead="Turn your own server into a private cinema. Share a film, a conversation and the same pause button with friends.", language="简体中文", host="Host your own cinema", watch="Read the viewer guide", alt="Desktop and mobile screens paused at the same moment in a demo room", caption="Two browsers, one film. A real desktop and mobile-viewport capture from a demo room.", how="Your first screening", first="01 / Send an invitation", join="One person hosts the cinema. Friends open their room link in a browser; guests don’t install Docker or an extension.", second="02 / Pick a film", choose="Choose a library film, or paste an authorized video page or media link. If discovery returns multiple candidates, select the one you want. Not every site is supported.", third="03 / Press play together", sync="Playback follows the host. In direct mode each viewer fetches media from the origin. In relay mode your server delivers it to each viewer, using server bandwidth.", mode="Compare direct and relay", architecture="Explore the architecture", footer="Project documentation, not a public screening room. To watch, use an invitation from your host."),
    "zh-CN": dict(title="不同的地方，同一场电影。", lead="把自己的服务器变成私人放映室。和朋友一起选片、聊天；你按下暂停，两块屏幕停在同一刻。", language="English", host="自己部署放映室", watch="阅读观众指南", alt="演示房间中，桌面和手机视口停在同一帧", caption="两块屏幕，一场电影。图为演示房间的桌面与手机视口实拍。", how="第一次一起看", first="01 / 邀请朋友", join="一人部署，朋友用浏览器打开邀请链接即可入房。受邀者不用安装 Docker 或插件。", second="02 / 选一部片", choose="从共享片库选片，也可以粘贴有权分享的视频网页或媒体链接。解析到多个候选时，自己选定要看的那一个；并非每个网站都能解析。", third="03 / 一起按下播放", sync="播放进度跟随房主。直连时，每个人从原站获取媒体；中转时，由你的服务器向每位观众发送媒体，会消耗服务器流量。", mode="对比直连与中转", architecture="查看系统架构", footer="这里是项目介绍站，不是公共放映室。想加入朋友的放映，请打开对方发给你的邀请链接。"),
}


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Output must be an empty directory")
    assets = out / "assets"
    assets.mkdir()
    for src in (HERE / "site.css", ROOT / "web/assets/guide.css", ROOT / "docs/showcase/hero.webp"):
        shutil.copyfile(src, assets / src.name)
    (out / "help").mkdir()
    (out / "zh-CN").mkdir()
    template = Template((HERE / "index.html.in").read_text())
    for lang, copy in COPY.items():
        en = lang == "en"
        base = "" if en else "../"
        install = REPO + "/blob/main/" + ("README.md#start" if en else "README.zh-CN.md#快速开始")
        arch = REPO + "/blob/main/docs/architecture/" + ("current.en.md" if en else "current.md")
        page = template.substitute(copy, lang=lang, repo=REPO, base=base, other="zh-CN/" if en else "../",
                                   other_lang="zh-CN" if en else "en", install=install, arch=arch, guide=f"{base}help/{lang}.html")
        (out / ("index.html" if en else "zh-CN/index.html")).write_text(page)
        # Guides ship with the app too. Under Pages, their home is this project site,
        # and the in-app gallery CTA would misleadingly imply there is a public room.
        guide = (ROOT / f"web/help/{lang}.html").read_text()
        guide = guide.replace('href="/assets/', 'href="../assets/').replace('href="/help/', 'href="')
        guide = '\n'.join(line for line in guide.splitlines() if '<a class="action" href="/">' not in line)
        guide = guide.replace('href="/"', 'href="../"' if en else 'href="../zh-CN/"')
        (out / f"help/{lang}.html").write_text(guide + '\n')


if __name__ == "__main__":
    build(Path(sys.argv[1]))
