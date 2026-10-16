"""MkDocs hook: publish the in-app help pages as the user guide.

The app bundles every ``docs/help/<lang>/*.md`` file (``src/help/content.ts``),
so site-only pages cannot live in that folder. The site keeps its own pages in
``docs/site/<lang>/`` and this hook adds the help pages of the same language at
build time. ``extra.help_dir`` in the config names the folder, relative to the
config file.

A help page with an annotated capture (``figures/<page>.svg`` in the site
folder, made by ``scripts/annotate-guide-captures.py``) gets that figure under
its title, with a caption naming each numbered mark. The figure is added here
rather than in the help markdown so the app help panel stays text only.
"""

import html
import json
from pathlib import Path

from mkdocs.structure.files import File

CAPTION_LEAD = {"en": "Numbered marks", "ko": "번호 표시"}


def on_files(files, config):
    root = Path(config.config_file_path).parent
    help_dir = root / config.extra["help_dir"]
    for page in sorted(help_dir.glob("*.md")):
        files.append(
            File(
                page.name,
                str(help_dir),
                config.site_dir,
                config.use_directory_urls,
            )
        )
    return files


def on_page_markdown(markdown, page, config, files):
    stem = Path(page.file.src_uri).stem
    lang = config.theme["language"]
    figures_dir = Path(config.docs_dir) / "figures"
    # A page can have several shots: <page>.svg, then <page>-2.svg, <page>-3.svg
    # for controls below the fold. Numbering runs on across them, so they are
    # placed in order, each with the caption for its own marks.
    if not (figures_dir / f"{stem}.svg").exists():
        return markdown
    names = [stem]
    while (figures_dir / f"{stem}-{len(names) + 1}.svg").exists():
        names.append(f"{stem}-{len(names) + 1}")
    root = Path(config.config_file_path).parent
    lead = CAPTION_LEAD.get(lang, CAPTION_LEAD["en"])
    blocks = []
    for name in names:
        regions_file = root / "docs" / "site" / "captures" / lang / f"{name}.regions.json"
        if not regions_file.exists():
            raise FileNotFoundError(f"figures/{name}.svg has no regions file at {regions_file}")
        regions = json.loads(regions_file.read_text(encoding="utf-8"))
        # ref is markdown from the repo; escape HTML so it cannot open tags in the caption.
        marks = "; ".join(
            f"**{html.escape(str(r['label']))}** {html.escape(r['ref'], quote=False)}" for r in regions
        )
        blocks.append(f"![{page.title}](figures/{name}.svg)\n\n<small>{lead}: {marks}</small>\n")
    block = "\n".join(blocks)
    head, sep, rest = markdown.partition("\n")
    if not head.startswith("# "):
        return f"{block}\n{markdown}"
    return f"{head}\n\n{block}{sep}{rest}"
