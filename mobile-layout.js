(() => {
  const mobileQuery = window.matchMedia('(max-width: 820px)');
  const layout = document.querySelector('.layout');
  const sidebar = document.querySelector('.sidebar');
  const mapShell = document.querySelector('.map-shell');
  const mapElement = document.getElementById('map');
  const legend = document.querySelector('.legend');
  const detailsDialog = document.getElementById('details');
  const detailContent = document.getElementById('detailContent');
  const locationPlanner = document.querySelector('.location-planner');
  const searchInput = document.getElementById('search');
  const results = document.getElementById('results');

  if (!layout || !sidebar || !mapShell || !mapElement || !legend || !detailsDialog ||
      !detailContent || !locationPlanner || !searchInput || !results) return;

  const mobileStyles = document.createElement('link');
  mobileStyles.rel = 'stylesheet';
  mobileStyles.href = 'mobile-layout.css';
  document.head.appendChild(mobileStyles);

  const appIntro = document.createElement('section');
  appIntro.className = 'mobile-app-intro';
  appIntro.innerHTML = [
    '<p class="mobile-app-eyebrow">COLORADO FISHING, IN YOUR POCKET</p>',
    '<h2>Find your next water.</h2>',
    '<p>Search Colorado waters and stocking history, explore the statewide map, or plan a drive from your location.</p>',
    '<div class="mobile-app-features" aria-label="COFish features">',
    '<span>Recent stocking</span><span>Species</span><span>Weather</span><span>Bathymetry</span>',
    '</div>',
    '<p class="mobile-app-prompt">Choose an option below to get started.</p>'
  ].join('');
  sidebar.insertBefore(appIntro, sidebar.firstChild);

  const searchView = document.createElement('section');
  searchView.className = 'mobile-search-view';
  searchView.setAttribute('aria-labelledby', 'mobileSearchHeading');
  const searchHeading = document.createElement('div');
  searchHeading.className = 'mobile-view-heading';
  searchHeading.innerHTML = '<p>FIND A WATER</p><h2 id="mobileSearchHeading">Search and filter</h2>';
  const searchLabel = searchInput.closest('label');
  const controlGrid = sidebar.querySelector('.control-grid');
  const filterFieldsets = [...sidebar.querySelectorAll(':scope > fieldset')];
  const resultsHeader = sidebar.querySelector('.results-header');
  sidebar.insertBefore(searchView, searchLabel);
  searchView.append(searchHeading, searchLabel, controlGrid, ...filterFieldsets, resultsHeader, results);

  const navigateHeading = document.createElement('div');
  navigateHeading.className = 'mobile-view-heading mobile-navigate-heading';
  navigateHeading.innerHTML = '<p>PLAN YOUR DRIVE</p><h2>Start from your location</h2>';
  locationPlanner.insertBefore(navigateHeading, locationPlanner.firstChild);

  const legendDisclosure = document.createElement('details');
  legendDisclosure.className = 'mobile-sidebar-legend';
  legendDisclosure.open = !mobileQuery.matches;
  const legendSummary = document.createElement('summary');
  legendSummary.textContent = 'Map legend';
  legend.parentNode.insertBefore(legendDisclosure, legend);
  legendDisclosure.append(legendSummary, legend);

  const icons = {
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.4"></circle><path d="m16 16 4.2 4.2"></path></svg>',
    map: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3.5 5.5 5-2.2 7 2.2 5-2.2v15.2l-5 2.2-7-2.2-5 2.2z"></path><path d="M8.5 3.3v15.2M15.5 5.5v15.2"></path></svg>',
    navigate: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m20.5 3.5-7.2 17-2.4-7.4-7.4-2.4z"></path></svg>'
  };
  const bottomNav = document.createElement('nav');
  bottomNav.className = 'mobile-bottom-nav';
  bottomNav.setAttribute('aria-label', 'Mobile app navigation');
  bottomNav.innerHTML = [
    `<button type="button" data-mobile-view-target="search">${icons.search}<span>Search</span></button>`,
    `<button type="button" class="mobile-map-tab" data-mobile-view-target="map">${icons.map}<span>Map</span></button>`,
    `<button type="button" data-mobile-view-target="navigate">${icons.navigate}<span>Navigate</span></button>`
  ].join('');
  document.body.appendChild(bottomNav);
  const navButtons = [...bottomNav.querySelectorAll('button')];

  let currentMobileView = 'home';
  const sheetStates = ['peek', 'half', 'full'];
  let sheetState = 'half';
  let dragStartY = 0;
  let dragStartTop = 0;
  let dragLastY = 0;
  let dragLastTime = 0;
  let sheetMoved = false;

  function refreshMap(delay = 100) {
    window.setTimeout(() => {
      if (typeof map !== 'undefined' && map && typeof map.invalidateSize === 'function') {
        map.invalidateSize();
      }
    }, delay);
  }

  function setMobileView(view, { push = true, focus = true } = {}) {
    if (!mobileQuery.matches || !['home', 'search', 'map', 'navigate'].includes(view)) return;
    if (view === currentMobileView && document.body.dataset.mobileView === view) return;
    currentMobileView = view;
    document.body.dataset.mobileView = view;

    navButtons.forEach(button => {
      const active = button.dataset.mobileViewTarget === view;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });

    if (detailsDialog.open && view !== 'map') detailsDialog.close();
    if (view === 'map') {
      refreshMap(50);
      refreshMap(300);
    } else if (view === 'search' && focus) {
      window.setTimeout(() => searchInput.focus({ preventScroll: true }), 80);
    }

    window.scrollTo({ top: 0, behavior: 'auto' });
    if (push) history.pushState({ ...history.state, cofishMobileView: view }, '');
  }

  navButtons.forEach(button => {
    button.addEventListener('click', () => setMobileView(button.dataset.mobileViewTarget));
  });
  window.addEventListener('popstate', event => {
    if (!mobileQuery.matches) return;
    setMobileView(event.state?.cofishMobileView || 'home', { push: false, focus: false });
  });

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
    if (state === 'half') return Math.max(0, height * .54);
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
    const nextTop = Math.min(
      sheetTopForState('peek'),
      Math.max(sheetTopForState('full'), dragStartTop + event.clientY - dragStartY)
    );
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
    setMobileView('map');
    detailContent.innerHTML = window.detailHtml(water);
    if (!detailsDialog.open) detailsDialog.show();
    setSheetState('half');
    window.loadWeather(water);
  };
  detailsDialog.addEventListener('close', () => setSheetState('half'));

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
      setMobileView(currentMobileView, { push: false, focus: false });
    } else {
      delete document.body.dataset.mobileView;
      if (detailsDialog.open) detailsDialog.close();
      legendDisclosure.open = true;
      navButtons.forEach(button => button.removeAttribute('aria-current'));
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
    if (mobileQuery.matches && event.touches.length >= 2) event.preventDefault();
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && detailsDialog.open) detailsDialog.close();
  });
  mapElement.addEventListener('touchmove', keepPinchInsideMap, { passive: false });
  mapElement.addEventListener('gesturestart', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });
  mapElement.addEventListener('gesturechange', event => {
    if (mobileQuery.matches) event.preventDefault();
  }, { passive: false });

  new MutationObserver(discoverMapLegends).observe(mapShell, { childList: true, subtree: true });
  results.addEventListener('click', event => {
    if (!mobileQuery.matches || !event.target.closest('.water-button')) return;
    setMobileView('map');
  }, true);

  document.body.dataset.mobileView = mobileQuery.matches ? 'home' : '';
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
})();
