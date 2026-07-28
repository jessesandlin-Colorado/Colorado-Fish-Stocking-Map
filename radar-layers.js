(() => {
  if (typeof L === 'undefined' || typeof map === 'undefined' || !map || typeof markerLayer === 'undefined') return;

  const RADAR_METADATA_URL = 'https://api.rainviewer.com/public/weather-maps.json';
  const REFRESH_INTERVAL_MS = 10 * 60 * 1000;
  const radarGroup = L.layerGroup();
  let radarTiles = null;
  let refreshTimer = null;
  let loading = false;

  const layerControl = L.control.layers(null, {
    'Stocked waters': markerLayer,
    'Weather radar': radarGroup
  }, {
    collapsed: true,
    position: 'topright'
  }).addTo(map);

  function latestRadarFrame(metadata) {
    const frames = metadata?.radar?.past;
    return Array.isArray(frames) && frames.length ? frames[frames.length - 1] : null;
  }

  async function refreshRadar() {
    if (loading || !map.hasLayer(radarGroup)) return;
    loading = true;

    try {
      const response = await fetch(RADAR_METADATA_URL, { cache: 'no-store' });
      if (!response.ok) throw new Error(`RainViewer metadata request failed (${response.status})`);

      const metadata = await response.json();
      const frame = latestRadarFrame(metadata);
      if (!metadata.host || !frame?.path) throw new Error('RainViewer returned no current radar frame');

      const tileUrl = `${metadata.host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`;
      const nextTiles = L.tileLayer(tileUrl, {
        tileSize: 256,
        opacity: 0.62,
        maxNativeZoom: 7,
        maxZoom: 18,
        zIndex: 350,
        attribution: 'Weather radar © <a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">RainViewer</a>'
      });

      nextTiles.addTo(radarGroup);
      if (radarTiles) radarGroup.removeLayer(radarTiles);
      radarTiles = nextTiles;
    } catch (error) {
      console.warn('Weather radar could not be loaded.', error);
      window.alert('Weather radar is temporarily unavailable. Please try again in a few minutes.');
      if (map.hasLayer(radarGroup)) map.removeLayer(radarGroup);
    } finally {
      loading = false;
    }
  }

  function startRadarRefresh() {
    refreshRadar();
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(refreshRadar, REFRESH_INTERVAL_MS);
  }

  function stopRadarRefresh() {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }

  map.on('overlayadd', event => {
    if (event.layer === radarGroup) startRadarRefresh();
  });

  map.on('overlayremove', event => {
    if (event.layer === radarGroup) stopRadarRefresh();
  });

  // Stocked waters remain enabled because markerLayer is already on the map.
  // Weather radar begins disabled and is fetched only after the user selects it.
  layerControl.getContainer().setAttribute('aria-label', 'Map layers');
})();
