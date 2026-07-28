(() => {
  const mobileQuery = window.matchMedia('(max-width: 820px)');
  const layout = document.querySelector('.layout');
  const sidebar = document.querySelector('.sidebar');
  const mapShell = document.querySelector('.map-shell');
  const mapAnchor = document.querySelector('.legend');

  if (!layout || !sidebar || !mapShell || !mapAnchor) return;

  function refreshMap() {
    window.setTimeout(() => {
      if (window.map && typeof window.map.invalidateSize === 'function') {
        window.map.invalidateSize();
      }
    }, 80);
  }

  function placeMap() {
    if (mobileQuery.matches) {
      if (mapShell.parentElement !== sidebar || mapShell.nextElementSibling !== mapAnchor) {
        sidebar.insertBefore(mapShell, mapAnchor);
      }
    } else if (mapShell.parentElement !== layout || sidebar.nextElementSibling !== mapShell) {
      layout.insertBefore(mapShell, sidebar.nextElementSibling);
    }
    refreshMap();
  }

  placeMap();
  mobileQuery.addEventListener?.('change', placeMap);
  window.addEventListener('orientationchange', refreshMap);

  // The existing water-card handler centers and zooms the map. On mobile,
  // bring the map into view first so that movement is visible to the user.
  document.getElementById('results')?.addEventListener('click', event => {
    if (!mobileQuery.matches || !event.target.closest('.water-button')) return;
    mapShell.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, true);
})();
