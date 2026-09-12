"""Tests for scripts/build_site.py's static site generation.

scripts/ isn't a package, so the module is loaded by file path rather than
imported normally (same pattern as tests/test_split_collections.py).

Run with:  python -m pytest tests/test_build_site.py
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_spec = importlib.util.spec_from_file_location(
    "build_site", os.path.join(ROOT, "scripts", "build_site.py")
)
build_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_site)


def test_build_writes_index_and_cname(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        count = build_site.build(tmp_path)
    finally:
        os.chdir(original_cwd)

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "CNAME").read_text().strip() == "wayproof.dev"
    # The real dataset has known unconfirmed items (see wayproof/reports.py's
    # open_questions()); a build against it should surface at least one.
    assert count > 0

    index_html = (tmp_path / "index.html").read_text()
    assert f"({count} open)" in index_html
    assert "github.com/asideofkorn/wayproof/issues/new" in index_html


def test_issue_url_is_prefilled_and_escaped():
    url = build_site._issue_url(
        "data/peaks.csv", "Mount Carillon", "Isn't in the dataset at all",
    )
    assert url.startswith("https://github.com/asideofkorn/wayproof/issues/new?")
    assert "title=%5Bdata%5D%20Mount%20Carillon" in url
    assert "labels=data" in url
    # The apostrophe in the question must be percent-encoded, not raw --
    # otherwise it isn't a valid URL query value.
    assert "Isn't" not in url
    assert "Isn%27t" in url


def test_no_open_questions_renders_a_friendly_placeholder():
    html_out = build_site._render_questions_html([])
    assert "No open questions on file" in html_out
