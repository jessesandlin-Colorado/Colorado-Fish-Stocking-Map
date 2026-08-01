(() => {
  const mobileQuery = window.matchMedia('(max-width: 820px)');
  const layout = document.querySelector('.layout');
  const sidebar = document.querySelector('.sidebar');
  const mapShell = document.querySelector('.map-shell');
  const mapElement = document.getElementById('map');
  const legend = document.querySelector('.legend');
  const detailsDialog = document.getElementById('details');
  const detailContent = document.getElementById('detailContent');

  if (!layout || !sidebar || !mapShell || !mapElement || !legend || !detailsDialog || !detailContent) return;

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
  const sheetStates = ['peek', 'half', 'full'];
  let sheetState = 'half';
  let dragStartY = 0;
  let dragStartTop = 0;
  let dragLastY = 0;
  let dragLastTime = 0;
  let sheetMoved = false;

  const sheetHandle = document.createElement('button');
  sheetHandle.className = 'mobile-sheet-handle';
  sheetHandle.type = 'button';
  sheetHandle.innerHTML = '<span aria-hidden="true"></span><b>Water details</b>';
  detailsDialog.insertBefore(sheetHandle, detailContent);

  function viewportHeight() {
    return window.visualViewport?.height || window.innerHeight;
  }

  function sheetTopForState(state) {
    const height = viewportHeight();
    if (state === 'peek') return Math.max(0, height - 150);
    if (state === 'half') return Math.max(0, height * .48);
    return Math.max(0, 12 + (window.visualViewport?.offsetTop || 0));
  }

  function updateSheetHandleLabel() {
    const action = sheetState === 'full' ? 'Collapse' : 'Expand';
    sheetHandle.setAttribute('aria-label', `${action} water details`);
    sheetHandle.setAttribute('aria-expanded', String(sheetState === 'full'));
  }

  function setSheetState(state, { focus = false } = {}) {
    if (!sheetStates.includes(state)) return;
    sheetState = state;
    detailsDialog.dataset.sheetState = state;
    detailsDialog.classList.remove('is-dragging');
    detailsDialog.style.removeProperty('--mobile-sheet-top');
    updateSheetHandleLabel();
    if (focus) sheetHandle.focus({ preventScroll: true });
  }

  function cycleSheetState() {
    setSheetState(sheetState === 'peek' ? 'half' : sheetState === 'half' ? 'full' : 'half');
  }

  function beginSheetDrag(event) {
    if (!mobileQuery.matches || !detailsDialog.open || event.button !== 0) return;
    dragStartY = event.clientY;
    dragLastY = event.clientY;
    dragLastTime = performance.now();
    dragStartTop = detailsDialog.getBoundingClientRect().top;
    sheetMoved = false;
    detailsDialog.classList.add('is-dragging');
    sheetHandle.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveSheet(event) {
    if (!detailsDialog.classList.contains('is-dragging')) return;
    const minTop = sheetTopForState('full');
    const maxTop = sheetTopForState('peek');
    const nextTop = Math.min(maxTop, Math.max(minTop, dragStartTop + event.clientY - dragStartY));
    if (Math.abs(event.clientY - dragStartY) > 5) sheetMoved = true;
    detailsDialog.style.setProperty('--mobile-sheet-top', `${nextTop}px`);
    dragLastY = event.clientY;
    dragLastTime = performance.now();
    event.preventDefault();
  }

  function finishSheetDrag(event) {
    if (!detailsDialog.classList.contains('is-dragging')) return;
    const elapsed = Math.max(1, performance.now() - dragLastTime);
    const velocity = (event.clientY - dragLastY) / elapsed;
    const currentTop = detailsDialog.getBoundingClientRect().top;
    const currentIndex = sheetStates.indexOf(sheetState);
    let nextState;

    if (Math.abs(velocity) > .35) {
      const nextIndex = velocity < 0
        ? Math.min(sheetStates.length - 1, currentIndex + 1)
        : Math.max(0, currentIndex - 1);
      nextState = sheetStates[nextIndex];
    } else {
      nextState = sheetStates.reduce((closest, state) => (
        Math.abs(sheetTopForState(state) - currentTop) < Math.abs(sheetTopForState(closest) - currentTop)
          ? state
          : closest
      ), sheetStates[0]);
    }

    setSheetState(nextState);
    if (sheetHandle.hasPointerCapture(event.pointerId)) sheetHandle.releasePointerCapture(event.pointerId);
  }

  sheetHandle.addEventListener('click', event => {
    if (sheetMoved) {
      event.preventDefault();
      sheetMoved = false;
      return;
    }
    cycleSheetState();
  });
  sheetHandle.addEventListener('pointerdown', beginSheetDrag);
  sheetHandle.addEventListener('pointermove', moveSheet);
  sheetHandle.addEventListener('pointerup', finishSheetDrag);
  sheetHandle.addEventListener('pointercancel', finishSheetDrag);

  const originalShowDetails = window.showDetails;
  window.showDetails = function mobileAwareDetails(water) {
    if (!mobileQuery.matches) {
      originalShowDetails(water);
      return;
    }
    detailContent.innerHTML = window.detailHtml(water);
    if (!detailsDialog.open) detailsDialog.show();
    setSheetState('half');
    window.loadWeather(water);
  };

  detailsDialog.addEventListener('close', () => setSheetState('half'));

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
      if (detailsDialog.open) detailsDialog.close();
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
    if (event.key !== 'Escape') return;
    if (detailsDialog.open) detailsDialog.close();
    else if (fullMapOpen) setFullMap(false);
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
  window.visualViewport?.addEventListener('resize', () => {
    refreshMap(50);
    if (detailsDialog.open) setSheetState(sheetState);
  });
  window.addEventListener('orientationchange', () => {
    configureTouchMap();
    refreshMap(150);
  });

  document.getElementById('results')?.addEventListener('click', event => {
    if (!mobileQuery.matches || !event.target.closest('.water-button')) return;
    mapShell.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, true);
})();
