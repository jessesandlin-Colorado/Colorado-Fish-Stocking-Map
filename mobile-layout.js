(() => {
  const mobileQuery = window.matchMedia('(max-width: 820px)');
  const layout = document.querySelector('.layout');
  const sidebar = document.querySelector('.sidebar');
  const mapShell = document.querySelector('.map-shell');
  const mapElement = document.getElementById('map');
  const legend = document.querySelector('.legend');

  if (!layout || !sidebar || !mapShell || !mapElement || !legend) return;

  const mobileStyles = document.createElement('link');
  mobileStyles.rel = 'stylesheet';
  mobileStyles.href = 'mobile-layout.css';
  document.head.appendChild(mobileStyles);

  const legendDisclosure = document.createElement('details');
  legendDisclosure.className = 'mobile-sidebar-legend';
  legendDisclosure.open = !mobileQuery.matches;
  const legendSummary = document.createElement('summary');
  legendSummary.textContent = 'Map legend';
  legend.parentNode.insertBefore(legendDisclosure, legend);
  legendDisclosure.append(legendSummary, legend);

  const fullMapButton = document.createElement('button');
  fullMapButton.className = 'mobile-full-map-button';
  fullMapButton.type = 'button';
  fullMapButton.setAttribute('aria-controls', 'map');
  fullMapButton.setAttribute('aria-pressed', 'false');
  fullMapButton.innerHTML = '<span aria-hidden="true">⛶</span> Full-screen map';
  mapShell.appendChild(fullMapButton);

  let fullMapOpen = false;
  let pageScrollY = 0;

  function refreshMap(delay = 100) {
    window.setTimeout(() => {
      if (typeof map !== 'undefined' && map && typeof map.invalidateSize === 'function') {
        map.invalidateSize();
      }
    }, delay);
  }

  function setFullMap(open) {
    const nextOpen = Boolean(open && mobileQuery.matches);
    if (nextOpen === fullMapOpen) return;
    fullMapOpen = nextOpen;

    if (fullMapOpen) {
      pageScrollY = window.scrollY;
      document.body.classList.add('mobile-map-fullscreen');
      mapShell.setAttribute('role', 'dialog');
      mapShell.setAttribute('aria-label', 'Full-screen fishing map');
      fullMapButton.innerHTML = '<span aria-hidden="true">×</span> Exit full map';
    } else {
      document.body.classList.remove('mobile-map-fullscreen');
      mapShell.removeAttribute('role');
      mapShell.removeAttribute('aria-label');
      fullMapButton.innerHTML = '<span aria-hidden="true">⛶</span> Full-screen map';
      window.scrollTo(0, pageScrollY);
    }

    fullMapButton.setAttribute('aria-pressed', String(fullMapOpen));
    refreshMap(50);
    refreshMap(300);
  }

  function configureTouchMap() {
    if (typeof map === 'undefined' || !map) return;

    if (mobileQuery.matches) {
      map.dragging?.enable();
      map.touchZoom?.enable();
      map.doubleClickZoom?.enable();
    } else {
      map.dragging?.disable();
    }
  }

  function placeMap() {
    if (mobileQuery.matches) {
      legendDisclosure.open = false;
      if (mapShell.parentElement !== sidebar || mapShell.nextElementSibling !== legendDisclosure) {
        sidebar.insertBefore(mapShell, legendDisclosure);
      }
    } else {
      setFullMap(false);
      legendDisclosure.open = true;
      if (mapShell.parentElement !== layout || sidebar.nextElementSibling !== mapShell) {
        layout.insertBefore(mapShell, sidebar.nextElementSibling);
      }
    }
    configureTouchMap();
    discoverMapLegends();
    refreshMap();
  }

  function makeMapLegendCollapsible(element) {
    if (!mobileQuery.matches || element.dataset.mobileLegendReady === 'true') return;
    element.dataset.mobileLegendReady = 'true';
    element.classList.add('mobile-map-legend');
    element.setAttribute('role', 'button');
    element.setAttribute('tabindex', '0');
    element.setAttribute('aria-label', 'Show map legend');
    element.setAttribute('aria-expanded', 'false');

    const toggle = event => {
      if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
      if (event.target.closest('a') && element.classList.contains('is-expanded')) return;
      event.preventDefault();
      const expanded = element.classList.toggle('is-expanded');
      element.setAttribute('aria-expanded', String(expanded));
      element.setAttribute('aria-label', expanded ? 'Hide map legend' : 'Show map legend');
    };
    element.addEventListener('click', toggle);
    element.addEventListener('keydown', toggle);
  }

  function discoverMapLegends() {
    mapShell.querySelectorAll('.weather-layer-legend, .bathymetry-legend')
      .forEach(makeMapLegendCollapsible);
  }

  function keepPinchInsideMap(event) {
    if (!mobileQuery.matches || event.touches.length < 2) return;
    event.preventDefault();
  }

  fullMapButton.addEventListener('click', () => setFullMap(!fullMapOpen));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && fullMapOpen) setFullMap(false);
  });

  mapElement.addEventListener('touchmove', keepPinchInsideMap, { passive: false });
  mapElement.addEventListener('gesturestart', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });
  mapElement.addEventListener('gesturechange', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });

  new MutationObserver(discoverMapLegends).observe(mapShell, {
    childList: true,
    subtree: true
  });

  placeMap();
  discoverMapLegends();
  mobileQuery.addEventListener?.('change', placeMap);
  window.visualViewport?.addEventListener('resize', () => refreshMap(50));
  window.addEventListener('orientationchange', () => {
    configureTouchMap();
    refreshMap(150);
  });

  document.getElementById('results')?.addEventListener('click', event => {
    if (!mobileQuery.matches || !event.target.closest('.water-button')) return;
    mapShell.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, true);
})();
