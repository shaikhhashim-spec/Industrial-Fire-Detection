"""The Pages site is the Overview at the root and the globe under /globe/."""
import pytest

from scripts.assemble_pages_site import assemble


@pytest.fixture()
def dirs(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("overview")
    (site / "dashboard.js").write_text("js")
    (site / "overview.test.mjs").write_text("tests do not ship")
    globe = tmp_path / "globe"
    (globe / "assets").mkdir(parents=True)
    (globe / "index.html").write_text("globe")
    (globe / "assets" / "app.js").write_text("js")
    (globe / ".gateway-build").write_text("{}")
    return site, globe, tmp_path / "_site"


def test_overview_at_the_root_and_globe_under_globe(dirs):
    site, globe, out = dirs
    assemble(site, globe, out)
    assert (out / "index.html").read_text() == "overview"
    assert (out / "globe" / "index.html").read_text() == "globe"
    assert (out / "globe" / "assets" / "app.js").is_file()
    assert (out / ".nojekyll").is_file()


def test_tests_and_local_build_markers_do_not_ship(dirs):
    site, globe, out = dirs
    assemble(site, globe, out)
    assert not (out / "overview.test.mjs").exists()
    assert not (out / "globe" / ".gateway-build").exists()


def test_a_stale_output_folder_is_replaced_not_merged(dirs):
    site, globe, out = dirs
    out.mkdir()
    (out / "old.txt").write_text("left over")
    assemble(site, globe, out)
    assert not (out / "old.txt").exists()


def test_a_missing_globe_build_is_reported(dirs):
    site, globe, out = dirs
    (globe / "index.html").unlink()
    with pytest.raises(FileNotFoundError, match="build the globe first"):
        assemble(site, globe, out)
