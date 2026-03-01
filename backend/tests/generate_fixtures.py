"""Generate test fixture PDFs with metadata.

Can be run standalone (for e2e setup) or imported by conftest.py.
Usage: python generate_fixtures.py [output_dir]
  Defaults to backend/tests/fixtures/ if no argument given.
"""
import sys
from pathlib import Path

import pikepdf


SHEEETZ_NS = "http://sheeetz.app/meta/1.0/"


def _generate_fixture_pdf(
    path: Path,
    title: str = "",
    author: str = "",
    subject: str = "",
    keywords: str = "",
    custom: dict[str, str] | None = None,
) -> None:
    """Generate a minimal valid PDF with metadata using pikepdf."""
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))  # Letter size
    with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
        if title:
            xmp["dc:title"] = title
        if author:
            xmp["dc:creator"] = author
        if subject:
            xmp["dc:subject"] = subject
        if keywords:
            xmp["pdf:Keywords"] = keywords
        for key, value in (custom or {}).items():
            xmp[f"{{{SHEEETZ_NS}}}{key}"] = value
    pdf.save(path)


def generate(fixtures_dir: Path) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    subfolder = fixtures_dir / "subfolder"
    subfolder.mkdir(parents=True, exist_ok=True)

    _generate_fixture_pdf(
        fixtures_dir / "sample.pdf",
        title="Sonata No. 14",
        author="Ludwig van Beethoven",
        subject="Classical",
        keywords="piano, sonata, moonlight",
        custom={"genre": "Classical", "key": "C# Minor"},
    )
    _generate_fixture_pdf(
        subfolder / "nested.pdf",
        title="Prelude in C Major",
        author="Johann Sebastian Bach",
        subject="Baroque",
        keywords="keyboard, prelude",
        custom={"genre": "Baroque"},
    )


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "fixtures"
    generate(out_dir)
    print(f"Generated fixtures in {out_dir}")
