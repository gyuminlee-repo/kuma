"""Machine-value coverage for guide capture generation and publication."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SLUG = "kuro-06-export"


@pytest.fixture
def publisher():
    spec = importlib.util.spec_from_file_location("help_pages", ROOT / "docs/site/help_pages.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guide(tmp_path: Path):
    figures = tmp_path / "docs/site/en/figures"
    captures = tmp_path / "docs/site/captures/en"
    figures.mkdir(parents=True)
    captures.mkdir(parents=True)
    config = SimpleNamespace(
        config_file_path=str(tmp_path / "mkdocs.yml"),
        docs_dir=str(figures.parent),
        theme={"language": "en"},
    )
    page = SimpleNamespace(file=SimpleNamespace(src_uri=f"{SLUG}.md"), title=SLUG)
    return figures, captures, config, page


def test_generation_removes_only_stale_numbered_artifacts(tmp_path: Path, monkeypatch) -> None:
    # Given: two current shots, two obsolete extras, and unrelated figures.
    captures = tmp_path / "docs/site/captures/en"
    figures = tmp_path / "docs/site/en/figures"
    captures.mkdir(parents=True)
    figures.mkdir(parents=True)
    for suffix, label in [("", "1"), ("-2", "2")]:
        Image.new("RGB", (16, 12)).save(captures / f"{SLUG}{suffix}.png")
        (captures / f"{SLUG}{suffix}.regions.json").write_text(
            json.dumps([{"label": label, "bbox": [0.1, 0.1, 0.5, 0.5]}]), encoding="utf-8",
        )
    (captures / f"{SLUG}-4.regions.json").write_text("[]", encoding="utf-8")
    (captures / "other.regions.json").write_text("[]", encoding="utf-8")
    for name in (SLUG, f"{SLUG}-2", f"{SLUG}-3", f"{SLUG}-4", f"{SLUG}-legend", "other", "other-2"):
        (figures / f"{name}.svg").write_text("<svg/>", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("annotate_guide", ROOT / "scripts/annotate-guide-captures.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "CAPTURES", captures.parent)
    monkeypatch.setattr(sys, "argv", ["annotate-guide-captures.py"])

    # When: the existing generation entry point runs on the remaining inputs.
    status = module.main()

    # Then: no obsolete extra survives and the base is regenerated.
    assert status == 0
    assert {p.name for p in figures.iterdir()} == {
        f"{SLUG}.svg", f"{SLUG}-2.svg", f"{SLUG}-legend.svg", "other.svg", "other-2.svg",
    }
    svg = ElementTree.parse(figures / f"{SLUG}.svg")
    assert [node.text for node in svg.findall("{http://www.w3.org/2000/svg}text")] == ["1"]
    extra = ElementTree.parse(figures / f"{SLUG}-2.svg")
    assert [node.text for node in extra.findall("{http://www.w3.org/2000/svg}text")] == ["2"]


@pytest.mark.parametrize(
    ("svg_shots", "region_shots", "error"),
    [
        (["", "-2"], [""], FileNotFoundError),
        (["", "-3"], ["", "-3"], ValueError),
        (["-2"], ["-2"], FileNotFoundError),
        ([], ["-2"], FileNotFoundError),
        ([""], ["", "-2"], FileNotFoundError),
        (["", "-2"], ["", "-2", "-3"], FileNotFoundError),
    ],
)
def test_publication_rejects_incomplete_artifact_sets(publisher, guide, svg_shots, region_shots, error) -> None:
    # Given: a stale or incomplete shot sequence.
    figures, captures, config, page = guide
    for suffix in svg_shots:
        (figures / f"{SLUG}{suffix}.svg").write_text("<svg/>", encoding="utf-8")
    for index, suffix in enumerate(region_shots, start=1):
        (captures / f"{SLUG}{suffix}.regions.json").write_text(
            json.dumps([{"label": str(index), "ref": "control"}]), encoding="utf-8",
        )

    # When / Then: publication stops rather than emitting an obsolete SVG URL.
    with pytest.raises(error):
        publisher.on_page_markdown("# Guide\n", page, config, [])


@pytest.mark.parametrize("labels", [[], [""], ["1", "1"], ["1", "3"], ["2"], [1]])
def test_publication_rejects_invalid_labels(publisher, guide, labels) -> None:
    # Given: labels that cannot identify a nonempty consecutive set of marks.
    figures, captures, config, page = guide
    (figures / f"{SLUG}.svg").write_text("<svg/>", encoding="utf-8")
    (captures / f"{SLUG}.regions.json").write_text(
        json.dumps([{"label": label, "ref": "control"} for label in labels]), encoding="utf-8",
    )

    # When / Then: invalid machine labels reject the page.
    with pytest.raises(ValueError):
        publisher.on_page_markdown("# Guide\n", page, config, [])


@pytest.mark.parametrize("second_label", ["1", "3", ""])
def test_publication_rejects_discontinuous_multishot_labels(publisher, guide, second_label: str) -> None:
    # Given: a complete artifact pair whose second shot breaks the numbering.
    figures, captures, config, page = guide
    for suffix, label in [("", "1"), ("-2", second_label)]:
        (figures / f"{SLUG}{suffix}.svg").write_text("<svg/>", encoding="utf-8")
        (captures / f"{SLUG}{suffix}.regions.json").write_text(
            json.dumps([{"label": label, "ref": "control"}]), encoding="utf-8",
        )

    # When / Then: numbering must continue between shots, not restart.
    with pytest.raises(ValueError):
        publisher.on_page_markdown("# Guide\n", page, config, [])


def test_publication_accepts_valid_multishot_sequence(publisher, guide) -> None:
    # Given: three shots with consecutive labels and unrelated page artifacts.
    figures, captures, config, page = guide
    for suffix, labels in [("", ["1", "2"]), ("-2", ["3"]), ("-3", ["4", "5"])]:
        (figures / f"{SLUG}{suffix}.svg").write_text("<svg/>", encoding="utf-8")
        (captures / f"{SLUG}{suffix}.regions.json").write_text(
            json.dumps([{"label": label, "ref": "control"} for label in labels]), encoding="utf-8",
        )
    (figures / f"{SLUG}-legend.svg").write_text("<svg/>", encoding="utf-8")
    (captures / f"{SLUG}-legend.regions.json").write_text("[]", encoding="utf-8")

    # When: the hook renders the page without invoking MkDocs or a browser.
    markdown = publisher.on_page_markdown("# Guide\n", page, config, [])

    # Then: the published machine URLs and label order match the input sequence.
    assert re.findall(r"\]\((figures/[^)]+)\)", markdown) == [
        f"figures/{SLUG}.svg", f"figures/{SLUG}-2.svg", f"figures/{SLUG}-3.svg",
    ]
    assert re.findall(r"\*\*(\d+)\*\*", markdown) == ["1", "2", "3", "4", "5"]


def test_publication_leaves_uncaptured_pages_alone(publisher, guide) -> None:
    # Given: a help page without capture artifacts.
    _, _, config, page = guide
    markdown = "# Guide\n"

    # When: the page hook runs.
    rendered = publisher.on_page_markdown(markdown, page, config, [])

    # Then: there are no injected figure URLs.
    assert re.findall(r"\]\((figures/[^)]+)\)", rendered) == []
