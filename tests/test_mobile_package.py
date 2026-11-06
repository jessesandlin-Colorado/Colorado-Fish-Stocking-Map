import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_capacitor_identity_and_scripts_are_stable():
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    config = (ROOT / 'capacitor.config.ts').read_text(encoding='utf-8')
    assert package['scripts']['mobile:sync']
    assert package['dependencies']['@capacitor/core'] == '8.5.0'
    assert "appId: 'app.cofish.mobile'" in config
    assert "appName: 'COFish'" in config
    assert "webDir: 'mobile-web'" in config


def test_mobile_build_excludes_credentials_and_injects_native_bridge():
    builder = (ROOT / 'scripts' / 'prepare_mobile_web.mjs').read_text(encoding='utf-8')
    guide = (ROOT / 'MOBILE_APP.md').read_text(encoding='utf-8')
    assert "webDirectories = ['assets', 'config', 'data']" in builder
    assert 'native-bridge.js' in builder
    assert 'vendor/leaflet/leaflet.js' in builder
    assert 'vendor/leaflet/leaflet.css' in builder
    assert 'signing certificates' in guide
    assert 'must never be committed' in guide
    native_config = (ROOT / 'scripts' / 'configure_native_projects.mjs').read_text(encoding='utf-8')
    assert 'NSLocationWhenInUseUsageDescription' in native_config
    assert 'ITSAppUsesNonExemptEncryption' in native_config


def test_native_location_and_share_are_wired():
    location = (ROOT / 'location-tools.js').read_text(encoding='utf-8')
    sharing = (ROOT / 'share-links.js').read_text(encoding='utf-8')
    assert 'Capacitor?.Plugins?.Geolocation' in location
    assert 'nativeGeolocation.getCurrentPosition' in location
    assert 'Capacitor?.Plugins?.Share' in sharing
    assert 'nativeShare.share' in sharing
