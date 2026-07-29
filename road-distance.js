(() => {
  'use strict';

  const CACHE_PREFIX = 'fishMapRoadRoute:v2:';
  const OSRM_BASE = 'https://router.project-osrm.org/route/v1/driving/';
  const routeCache = new Map();
  const pendingRoutes = new Map();

  const originalPopup = popup;
  const originalDetailHtml = detailHtml;
  const originalShowDetails = showDetails;
  const originalLoadPopupWeather = loadPopupWeather;

  function planningLocation() {
    try {
      const saved = JSON.parse(sessionStorage.getItem('fishMapPlanningLocation'));
      if (!saved || !Number.isFinite(Number(saved.lat)) || !Number.isFinite(Number(saved.lng))) return null;
      return {
        lat: Number(saved.lat),
        lng: Number(saved.lng),
        label: saved.label || 'your planning location'
      };
    } catch (error) {
      return null;
    }
  }

  function waterKey(water) {
    return String(water.watercode || water.water_code || water.id || water.key || `${water.name}|${water.lat}|${water.lng}`);
  }

  function routeKey(location, water) {
    return `${location.lat.toFixed(5)},${location.lng.toFixed(5)}:${waterKey(water)}`;
  }

  function formatRoadMiles(meters) {
    const miles = meters / 1609.344;
    if (miles < 10) return `${miles.toFixed(1)} road mi`;
    return `${Math.round(miles)} road mi`;
  }

  function formatDuration(seconds) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    if (!hours) return `${minutes} min`;
    if (!remainder) return `${hours} hr`;
    return `${hours} hr ${remainder} min`;
  }

  function routeLabel(route) {
    return `${formatRoadMiles(route.distance)} · about ${formatDuration(route.duration)}`;
  }

  function directionsUrl(location, water) {
    const origin = encodeURIComponent(`${location.lat},${location.lng}`);
    const destination = encodeURIComponent(`${water.lat},${water.lng}`);
    return `https://www.google.com/maps/dir/?api=1&origin=${origin}&destination=${destination}`;
  }

  function readStoredRoute(key) {
    try {
      const stored = JSON.parse(sessionStorage.getItem(`${CACHE_PREFIX}${key}`));
      if (!stored || !Number.isFinite(stored.distance) || !Number.isFinite(stored.duration)) return null;
      return stored;
    } catch (error) {
      return null;
    }
  }

  function saveRoute(key, route) {
    routeCache.set(key, route);
    try {
      sessionStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(route));
    } catch (error) {
      // Routing still works when browser storage is unavailable.
    }
  }

  async function requestRoute(location, water) {
    const coordinates = `${location.lng},${location.lat};${Number(water.lng)},${Number(water.lat)}`;
    const url = `${OSRM_BASE}${coordinates}?overview=false&alternatives=false&steps=false`;
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Routing service returned ${response.status}`);
    const data = await response.json();
    const route = data.routes?.[0];
    if (data.code !== 'Ok' || !Number.isFinite(route?.distance) || !Number.isFinite(route?.duration)) {
      throw new Error(data.message || 'A driving route was unavailable');
    }
    return { distance: route.distance, duration: route.duration };
  }

  function routeFor(water) {
    const location = planningLocation();
    if (!location) return null;
    const key = routeKey(location, water);
    return routeCache.get(key) || readStoredRoute(key);
  }

  function loadRoute(water) {
    const location = planningLocation();
    if (!location || !Number.isFinite(Number(water.lat)) || !Number.isFinite(Number(water.lng))) {
      return Promise.resolve(null);
    }

    const key = routeKey(location, water);
    const cached = routeCache.get(key) || readStoredRoute(key);
    if (cached) {
      routeCache.set(key, cached);
      return Promise.resolve(cached);
    }
    if (pendingRoutes.has(key)) return pendingRoutes.get(key);

    const promise = requestRoute(location, water)
      .then(route => {
        saveRoute(key, route);
        return route;
      })
      .finally(() => pendingRoutes.delete(key));

    pendingRoutes.set(key, promise);
    return promise;
  }

  function routePanel(water, mode, status = 'idle', route = null) {
    const location = planningLocation();
    if (!location) return '';
    const className = mode === 'popup' ? 'popup-route-estimate' : 'detail-route-estimate';
    const link = `<a href="${directionsUrl(location, water)}" target="_blank" rel="noreferrer">Open directions ↗</a>`;

    if (status === 'loading') {
      return `<div class="road-distance ${className}" data-route-water="${esc(waterKey(water))}"><span>Drive estimate</span><strong>Calculating route…</strong>${link}</div>`;
    }
    if (status === 'ready' && route) {
      return `<div class="road-distance ${className}" data-route-water="${esc(waterKey(water))}"><span>Drive estimate from ${esc(location.label)}</span><strong>${routeLabel(route)}</strong>${link}</div>`;
    }
    if (status === 'error') {
      return `<div class="road-distance ${className} route-error" data-route-water="${esc(waterKey(water))}"><span>Drive estimate</span><strong>Route unavailable</strong>${link}</div>`;
    }
    return `<div class="road-distance ${className}" data-route-water="${esc(waterKey(water))}"><span>Drive estimate from ${esc(location.label)}</span><strong>Open this water to calculate</strong>${link}</div>`;
  }

  function replaceRoutePanels(water, status, route = null) {
    const key = waterKey(water);
    document.querySelectorAll(`[data-route-water="${CSS.escape(key)}"]`).forEach(panel => {
      const mode = panel.classList.contains('popup-route-estimate') ? 'popup' : 'detail';
      const wrapper = document.createElement('div');
      wrapper.innerHTML = routePanel(water, mode, status, route);
      panel.replaceWith(wrapper.firstElementChild);
    });
  }

  function calculateAndRender(water) {
    const cached = routeFor(water);
    if (cached) {
      replaceRoutePanels(water, 'ready', cached);
      return Promise.resolve(cached);
    }

    replaceRoutePanels(water, 'loading');
    return loadRoute(water)
      .then(route => {
        if (route) replaceRoutePanels(water, 'ready', route);
        return route;
      })
      .catch(error => {
        replaceRoutePanels(water, 'error');
        console.warn('Road route lookup failed:', error);
        return null;
      });
  }

  popup = function popupWithOnDemandRoute(water) {
    const html = originalPopup(water);
    const panel = routePanel(water, 'popup', routeFor(water) ? 'ready' : 'idle', routeFor(water));
    if (!panel) return html;
    return html.replace('<div class="popup-weather', `${panel}<div class="popup-weather`);
  };

  detailHtml = function detailWithOnDemandRoute(water) {
    const html = originalDetailHtml(water);
    const cached = routeFor(water);
    const panel = routePanel(water, 'detail', cached ? 'ready' : 'loading', cached);
    if (!panel) return html;
    return html.replace('</h2>', `</h2>${panel}`);
  };

  showDetails = function showDetailsWithOnDemandRoute(water) {
    originalShowDetails(water);
    calculateAndRender(water);
  };

  loadPopupWeather = async function loadPopupWeatherAndRoute(water, marker) {
    const weatherPromise = originalLoadPopupWeather(water, marker);
    calculateAndRender(water);
    return weatherPromise;
  };
})();
