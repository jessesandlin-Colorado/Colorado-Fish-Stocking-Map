from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_mobile_layout_exposes_persistent_app_navigation():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "mobile-bottom-nav" in script
    assert 'data-mobile-view-target="home"' in script
    assert 'data-mobile-view-target="search"' in script
    assert 'data-mobile-view-target="map"' in script
    assert 'data-mobile-view-target="navigate"' in script
    assert 'data-mobile-view-target="about"' in script
    assert "mobile-full-map-button" not in script
    assert "data-mobile-view='map'" in styles
    assert "map.invalidateSize" in script
    assert "100dvh" in styles
    assert "env(safe-area-inset-bottom)" in styles


def test_mobile_home_and_content_views_are_separated():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "mobile-app-intro" in script
    assert "Choose an option below to get started" in script
    assert "mobile-search-view" in script
    assert "mobile-navigate-heading" in script
    assert "data-mobile-view='home'" in styles
    assert "data-mobile-view='search'" in styles
    assert "data-mobile-view='navigate'" in styles
    assert "data-mobile-view='about'" in styles


def test_mobile_about_view_explains_layers_and_includes_feedback():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "How to use the map" in script
    assert "USGS Topo" in script
    assert "Bathymetry / depth contours" in script
    assert "weather radar, cloud cover, wind forecasts" in script
    assert "feedbackCard" in script
    assert "mobile-about-guide" in styles
    assert "grid-template-columns: repeat(5, 1fr)" in styles


def test_mobile_legends_are_collapsible_and_desktop_remains_open():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "legendDisclosure.open = !mobileQuery.matches" in script
    assert "weather-layer-legend, .bathymetry-legend, .map-symbol-legend" in script
    assert "aria-expanded" in script
    assert ".mobile-map-legend[hidden]" in styles
    assert "@media (max-width: 820px)" in styles


def test_mobile_details_use_a_draggable_non_modal_bottom_sheet():
    script = (ROOT / "mobile-layout.js").read_text(encoding="utf-8")
    styles = (ROOT / "mobile-layout.css").read_text(encoding="utf-8")

    assert "detailsDialog.show()" in script
    assert "detailsDialog.showModal()" not in script
    assert "['peek', 'half', 'full']" in script
    assert "setPointerCapture" in script
    assert "pointermove" in script
    assert "mobile-sheet-handle" in script
    assert "data-sheet-state='peek'" in styles
    assert "data-sheet-state='half'" in styles
    assert "data-sheet-state='full'" in styles
    assert "height * .54" in script
    assert "--mobile-sheet-top: 54dvh" in styles
    assert "touch-action: none" in styles
