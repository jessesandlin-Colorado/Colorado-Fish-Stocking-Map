import json


def test_manifest_is_installable_and_preview_safe():
    manifest = json.load(open('site.webmanifest', encoding='utf-8'))
    assert manifest['display'] == 'standalone'
    assert manifest['id'] == './'
    assert manifest['start_url'] == './'
    assert manifest['scope'] == './'
    assert {shortcut['short_name'] for shortcut in manifest['shortcuts']} == {'Map', 'Search', 'Navigate'}
    assert any('maskable' in icon.get('purpose', '') for icon in manifest['icons'])


def test_service_worker_has_offline_and_update_lifecycle():
    worker = open('service-worker.js', encoding='utf-8').read()
    installer = open('app-install.js', encoding='utf-8').read()
    assert 'offline.html' in worker
    assert "self.clients.claim()" in worker
    assert "SKIP_WAITING" in worker
    assert 'beforeinstallprompt' in installer
    assert 'controllerchange' in installer
    assert "data-mobile-view-target" in installer
