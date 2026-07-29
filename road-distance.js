(() => {
  'use strict';

  const MAX_ROUTED_WATERS = 24;
  const CACHE_PREFIX = 'fishMapRoadMatrix:v1:';
  const OSRM_BASE = 'https://router.project-osrm.org/table/v1/driving/';

  let routeOriginKey = '';
  let routeByWater = new Map();
  let loadingPromise = null;
  let lastObservedLocation = '';

  const originalFiltered = filtered;
  const originalRender = render;
  const originalPopup = popup;
  const originalDetailHtml = detailHtml;

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
    return String(water.watercode || water.water_code || water.id || `${water.name}|${water.lat}|${water.lng}`);
  }

  function originKey(location) {
    return `${location.lat.toFixed(4)},${location.lng.toFixed(4)}`;
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
    return `${formatRoadMiles(route.distance)} · ${formatDuration(route.duration)}`;
  }

  function routeFor(water) {
    return routeByWater.get(waterKey(water)) || null;
  }

  function setPlannerStatus(message, isError = false) {
    const status = document.getElementById('locationStatus');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('error', isError);
  }

  function validWaterCoordinates(water) {
    return Number.isFinite(Number(water.lat)) && Number.isFinite(Number(water.lng));
  }

  function candidateWaters() {
    return originalFiltered().filter(validWaterCoordinates).slice(0, MAX_ROUTED_WATERS);
  }

  function cacheKey(location, candidates) {
    const ids = candidates.map(waterKey).join(',');
    return `${CACHE_PREFIX}${originKey(location)}:${ids}`;
  }

  function restoreCache(location, candidates) {
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey(location, candidates)));
      if (!cached || !Array.isArray(cached.routes)) return false;
      routeByWater = new Map(cached.routes.map(item => [String(item.key), item]));
      routeOriginKey = originKey(location);
      return true;
    } catch (error) {
      return false;
    }
  }

  function saveCache(location, candidates) {
    try {
      sessionStorage.setItem(cacheKey(location, candidates), JSON.stringify({
        savedAt: Date.now(),
        routes: [...routeByWater.entries()].map(([key, route]) => ({ key, ...route }))
      }));
    } catch (error) {
      // Browsing still works if storage is unavailable.
    }
  }

  async function requestRoadMatrix(location, candidates) {
    const coordinates = [
      `${location.lng},${location.lat}`,
      ...candidates.map(water => `${Number(water.lng)},${Number(water.lat)}`)
    ].join(';');
    const destinations = candidates.map((water, index) => index + 1).join(';');
    const url = `${OSRM_BASE}${coordinates}?sources=0&destinations=${destinations}&annotations=duration,distance`;
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Routing service returned ${response.status}`);
    const data = await response.json();
    if (data.code !== 'Ok' || !Array.isArray(data.durations?.[0]) || !Array.isArray(data.distances?.[0])) {
      throw new Error(data.message || 'Road routes were unavailable');
    }

    const routes = new Map();
    candidates.forEach((water, index) => {
      const duration = data.durations[0][index];
      const distance = data.distances[0][index];
      if (Number.isFinite(duration) && Number.isFinite(distance)) {
        routes.set(waterKey(water), { duration, distance });
      }
    });
    return routes;
  }

  async function loadRoadDistances(force = false) {
    const location = planningLocation();
    if (!location) {
      routeOriginKey = '';
      routeByWater.clear();
      loadingPromise = null;
      return;
    }

    const nextOriginKey = originKey(location);
    const candidates = candidateWaters();
    if (!candidates.length) return;
    if (!force && nextOriginKey === routeOriginKey && routeByWater.size) return;
    if (!force && restoreCache(location, candidates)) {
      setPlannerStatus(`Using ${location.label}. Showing road distance and estimated drive time for the ${routeByWater.size} nearest waters.`);
      render();
      return;
    }
    if (loadingPromise) return loadingPromise;

    routeOriginKey = nextOriginKey;
    routeByWater.clear();
    setPlannerStatus(`Using ${location.label}. Calculating road distance and drive time for the ${candidates.length} nearest waters…`);
    originalRender();

    loadingPromise = requestRoadMatrix(location, candidates)
      .then(routes => {
        routeByWater = routes;
        saveCache(location, candidates);
        setPlannerStatus(`Using ${location.label}. Showing road distance and estimated drive time for the ${routes.size} nearest waters. Routes: OSRM/OpenStreetMap.`);
        render();
      })
      .catch(error => {
        routeByWater.clear();
        setPlannerStatus(`Using ${location.label}. Road estimates are temporarily unavailable, so results remain sorted by straight-line distance.`, true);
        console.warn('Road distance lookup failed:', error);
        originalRender();
      })
      .finally(() => {
        loadingPromise = null;
      });

    return loadingPromise;
  }

  filtered = function filteredByRoadTime() {
    const waters = originalFiltered();
    if (!routeByWater.size) return waters;
    return [...waters].sort((a, b) => {
      const aRoute = routeFor(a);
      const bRoute = routeFor(b);
      if (aRoute && bRoute) return aRoute.duration - bRoute.duration;
      if (aRoute) return -1;
      if (bRoute) return 1;
      return 0;
    });
  };

  popup = function popupWithRoadDistance(water) {
    const html = originalPopup(water);
    const route = routeFor(water);
    const location = planningLocation();
    if (!route || !location) return html;
    const replacement = `<p class="location-distance road-distance"><strong>${routeLabel(route)}</strong> from ${esc(location.label)}</p>`;
    if (html.includes('<p class="location-distance">')) {
      return html.replace(/<p class="location-distance">[\s\S]*?<\/p>/, replacement);
    }
    return html.replace('<div class="popup-weather', `${replacement}<div class="popup-weather`);
  };

  detailHtml = function detailWithRoadDistance(water) {
    const html = originalDetailHtml(water);
    const route = routeFor(water);
    const location = planningLocation();
    if (!route || !location) return html;
    const directions = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(`${location.lat},${location.lng}`)}&destination=${encodeURIComponent(`${water.lat},${water.lng}`)}`;
    const replacement = `<p class="detail-distance road-distance"><strong>${routeLabel(route)}</strong> from ${esc(location.label)}. <a href="${directions}" target="_blank" rel="noreferrer">Open directions ↗</a></p>`;
    if (html.includes('<p class="detail-distance">')) {
      return html.replace(/<p class="detail-distance">[\s\S]*?<\/p>/, replacement);
    }
    return html.replace('</h2>', `</h2>${replacement}`);
  };

  render = function renderWithRoadDistances() {
    originalRender();
    if (!routeByWater.size) return;
    const visible = filtered();
    document.querySelectorAll('#results .water-card').forEach((card, index) => {
      const water = visible[index];
      const route = routeFor(water);
      const meta = card.querySelector('.card-meta');
      if (!meta || !route) return;
      meta.textContent = meta.textContent.replace(/ · [\d.]+ mi away$/, '');
      meta.textContent += ` · 🚗 ${routeLabel(route)}`;
      card.dataset.roadRouted = 'true';
    });
    const count = document.getElementById('count');
    const location = planningLocation();
    if (count && location) count.title = `The routed candidates are sorted by estimated drive time from ${location.label}; remaining waters follow by straight-line distance.`;
  };

  function observePlanningLocation() {
    const location = planningLocation();
    const serialized = location ? `${originKey(location)}|${location.label}` : '';
    if (serialized === lastObservedLocation) return;
    lastObservedLocation = serialized;
    if (!location) {
      routeOriginKey = '';
      routeByWater.clear();
      render();
      return;
    }
    window.setTimeout(() => loadRoadDistances(), 0);
  }

  document.getElementById('clearLocation')?.addEventListener('click', () => {
    window.setTimeout(observePlanningLocation, 0);
  });
  document.getElementById('zipForm')?.addEventListener('submit', () => {
    window.setTimeout(observePlanningLocation, 500);
    window.setTimeout(observePlanningLocation, 1500);
  });
  document.getElementById('useMyLocation')?.addEventListener('click', () => {
    window.setTimeout(observePlanningLocation, 500);
    window.setTimeout(observePlanningLocation, 2000);
    window.setTimeout(observePlanningLocation, 5000);
  });

  window.setInterval(observePlanningLocation, 1000);
  observePlanningLocation();
})();
