"""MkDocs hook: publish the in-app help pages as the user guide.

The app bundles every ``docs/help/<lang>/*.md`` file (``src/help/content.ts``),
so site-only pages cannot live in that folder. The site keeps its own pages in
``docs/site/<lang>/`` and this hook adds the help pages of the same language at
build time. ``extra.help_dir`` in the config names the folder, relative to the
config file.
"""

from pathlib import Path

from mkdocs.structure.files import File


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
