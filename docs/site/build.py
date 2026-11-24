"""Build only public documentation; never publish the application directory."""
from pathlib import Path
import json
import re
import shutil
import sys
from string import Template

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = "https://github.com/liu-qingyuan/together-cinema"
COPY = json.loads((HERE / "copy.json").read_text())
SKY = ("v1-sky-mobile.webp", "v1-sky-desktop.webp")
SHOTS = ("entry", "library", "direct", "relay")


def template(name):
    return Template((HERE / (name + ".html.in")).read_text())


def routes(lang, kind):
    en = lang == "en"
    root = "" if en and kind == "home" else "../"
    alt = "zh-CN" if en else "en"
    return dict(home=root + ("./" if en else "zh-CN/"), guide=f"{root}help/{lang}.html",
                install=f"{root}deploy/{lang}.html", base=root, other_lang=alt,
                other=(("zh-CN/" if en else "../") if kind == "home" else f"{alt}.html"))


def manual(lang, kind, nav, mast):
    en = lang == "en"
    deploy = kind == "deploy"
    if deploy:
        source = (HERE / "deploy" / f"{lang}.html").read_text()
    else:
        source = (ROOT / "web/help" / f"{lang}.html").read_text()
    # The shipped viewer guide owns these sections and permanent deep links.
    # Only the public documentation shell differs from the application.
    blocks = re.findall(r'<section id="([\w-]+)">\s*<h2>([^<]+)</h2>(.*?)</section>', source, re.S)
    if not blocks:
        raise ValueError(f"No chapters for {lang}/{kind}")
    contents = "On this page" if en else "本页目录"
    toc, chapters = [], []
    for n, (anchor, heading, text) in enumerate(blocks, 1):
        if not deploy:
            text = re.sub(r'<a class="action" href="/">[^<]+</a>', '', text)
            text = text.replace(f'https://liu-qingyuan.github.io/together-cinema/deploy/{lang}.html', nav["install"])
            text = re.sub(r'<dt>(.*?)</dt><dd>(.*?)</dd>', r'<details><summary>\1</summary><p>\2</p></details>', text)
            text = text.replace('<dl>', '<div class="questions">').replace('</dl>', '</div>')
        num = f"{n:02}"
        toc.append(f'<a href="#{anchor}"><small>{num}</small>{heading}</a>')
        if not deploy and anchor in ("start", "library"):
            shot = "entry" if anchor == "start" else anchor
            url = f'../assets/{lang}-{shot}.webp'
            text += f'<figure><a href="{url}"><img src="{url}" alt="{COPY[lang][shot+"Alt"]}" loading="lazy"></a></figure>'
        chapters.append(f'<section id="{anchor}"><p class="chapter-number">{num} / {len(blocks):02}</p><h2>{heading}</h2>{text}<a class="to-contents" href="#contents">{contents} ↑</a></section>')
    label = DOC_LABELS[lang]
    return template("manual").substitute(
        lang=lang, mast=mast, title=label[kind], summary=label[kind+"_summary"],
        audience=label[kind+"_audience"], first=blocks[0][0], begin=label["begin"],
        contents=contents, toc="".join(toc), body="".join(chapters), home=nav["home"],
        home_label=label["home_label"], top=label["top"],
        next_url=nav["guide" if deploy else "install"], next_label=label["viewer" if deploy else "deploy"])


DOC_LABELS = {
    "en": dict(home_label="Overview", viewer="Viewer guide", deploy="Host your own",
               nav_label="Project navigation", top="Back to top", begin="Start here",
               viewer_summary="Join a friend, choose a film, and check that both screens follow the host. You only need a browser.",
               deploy_summary="Start locally with Docker. Once the first room works, add HTTPS and invite a friend.",
               viewer_audience="For viewers", deploy_audience="For hosts"),
    "zh-CN": dict(home_label="项目介绍", viewer="观众指南", deploy="自己部署",
                  nav_label="项目导航", top="回到顶部", begin="从第一步开始",
                  viewer_summary="打开朋友的邀请，选一部影片，再确认两个屏幕同步。你只需要浏览器，不用安装 Docker。",
                  deploy_summary="先用 Docker 在本机开一间放映室。确认能播放后，再配置 HTTPS，邀请异地的朋友。",
                  viewer_audience="给一起看的人", deploy_audience="给搭建放映室的人"),
}


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Output must be an empty directory")
    for folder in ("assets", "help", "deploy", "zh-CN"):
        (out / folder).mkdir()
    for src in (HERE / "site.css", *(ROOT / "web/assets/scenes" / name for name in SKY),
                *(HERE / "shots" / f"{lang}-{shot}.webp" for lang in COPY for shot in SHOTS)):
        shutil.copyfile(src, out / "assets" / src.name)
    for lang, copy in COPY.items():
        for kind in ("home", "viewer", "deploy"):
            links = routes(lang, kind)
            current = {page+"_current": 'aria-current="page"' if kind == page else "" for page in ("home", "viewer", "deploy")}
            mast = template("header").substitute({**copy, **links, **DOC_LABELS[lang], **current})
            if kind == "home":
                arch = REPO + "/blob/main/docs/architecture/" + ("current.en.md" if lang == "en" else "current.md")
                page = template("index").substitute(copy, lang=lang, repo=REPO, arch=arch, mast=mast, **links)
                path = "index.html" if lang == "en" else "zh-CN/index.html"
            else:
                page = manual(lang, kind, links, mast)
                path = ("help" if kind == "viewer" else "deploy") + f"/{lang}.html"
            (out / path).write_text(page)


if __name__ == "__main__":
    build(Path(sys.argv[1]))
