"""Build only public documentation; never publish the application directory."""
from pathlib import Path
import json
import shutil
import sys
from string import Template

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = "https://github.com/liu-qingyuan/together-cinema"
COPY = json.loads((HERE / "copy.json").read_text())
SKY = ("v1-sky-mobile.webp", "v1-sky-desktop.webp")
SHOTS = ("entry", "library", "direct", "relay")


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError("Output must be an empty directory")
    assets = out / "assets"
    assets.mkdir()
    for src in (HERE / "site.css", ROOT / "web/assets/guide.css", *(ROOT / "web/assets/scenes" / name for name in SKY),
                *(HERE / "shots" / f"{lang}-{shot}.webp" for lang in COPY for shot in SHOTS)):
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
