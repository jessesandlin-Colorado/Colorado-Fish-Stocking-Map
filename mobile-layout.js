(() => {
  const mobileQuery = window.matchMedia('(max-width: 820px)');
  const layout = document.querySelector('.layout');
  const sidebar = document.querySelector('.sidebar');
  const mapShell = document.querySelector('.map-shell');
  const mapElement = document.getElementById('map');
  const mapAnchor = document.querySelector('.legend');

  if (!layout || !sidebar || !mapShell || !mapElement || !mapAnchor) return;

  function refreshMap() {
    window.setTimeout(() => {
      if (typeof map !== 'undefined' && map && typeof map.invalidateSize === 'function') {
        map.invalidateSize();
      }
    }, 100);
  }

  function configureTouchMap() {
    if (typeof map === 'undefined' || !map) return;

    if (mobileQuery.matches) {
      map.dragging?.enable();
      map.touchZoom?.enable();
      map.doubleClickZoom?.enable();
    } else {
      // Desktop interaction remains managed by app.js.
      map.dragging?.disable();
    }
  }

  function placeMap() {
    if (mobileQuery.matches) {
      if (mapShell.parentElement !== sidebar || mapShell.nextElementSibling !== mapAnchor) {
        sidebar.insertBefore(mapShell, mapAnchor);
      }
    } else if (mapShell.parentElement !== layout || sidebar.nextElementSibling !== mapShell) {
      layout.insertBefore(mapShell, sidebar.nextElementSibling);
    }
    configureTouchMap();
    refreshMap();
  }

  function keepPinchInsideMap(event) {
    if (!mobileQuery.matches || event.touches.length < 2) return;
    event.preventDefault();
  }

  // iOS Safari can promote a two-finger map gesture to page zoom unless both
  // its legacy gesture event and the standard touch event are cancelled.
  mapElement.addEventListener('touchmove', keepPinchInsideMap, { passive: false });
  mapElement.addEventListener('gesturestart', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });
  mapElement.addEventListener('gesturechange', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });

  placeMap();
  mobileQuery.addEventListener?.('change', placeMap);
  window.addEventListener('orientationchange', () => {
    configureTouchMap();
    refreshMap();
  });

  // The existing water-card handler centers and zooms the map. On mobile,
  // bring the map into view first so that movement is visible to the user.
  document.getElementById('results')?.addEventListener('click', event => {
    if (!mobileQuery.matches || !event.target.closest('.water-button')) return;
    mapShell.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, true);
})();
