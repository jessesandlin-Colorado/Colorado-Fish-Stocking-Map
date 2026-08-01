from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_mobile_marker_popup_is_compact_without_changing_desktop_width():
    styles = (ROOT / "popup-weather.css").read_text(encoding="utf-8")

    assert "width: 520px !important" in styles
    assert "@media (max-width: 600px)" in styles
    assert "width: min(310px, calc(100vw - 88px)) !important" in styles
    assert "min-height: 44px" in styles
    assert ".popup-species .species-fish-icon" in styles
