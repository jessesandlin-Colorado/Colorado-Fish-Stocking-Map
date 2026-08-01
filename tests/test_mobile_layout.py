from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_mobile_layout_exposes_fullscreen_map_controls():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "Full-screen map" in script
    assert "Exit full map" in script
    assert "mobile-map-fullscreen" in script
    assert "map.invalidateSize" in script
    assert "100dvh" in styles
    assert "env(safe-area-inset-bottom)" in styles


def test_mobile_legends_are_collapsible_and_desktop_remains_open():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "legendDisclosure.open = !mobileQuery.matches" in script
    assert "weather-layer-legend, .bathymetry-legend" in script
    assert "aria-expanded" in script
    assert ".mobile-map-legend[hidden]" in styles
    assert "@media (max-width: 820px)" in styles
