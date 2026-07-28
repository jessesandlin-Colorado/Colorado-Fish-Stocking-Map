(() => {
  if (typeof L === 'undefined' || typeof map === 'undefined' || !map || typeof markerLayer === 'undefined') return;

  const RADAR_METADATA_URL = 'https://api.rainviewer.com/public/weather-maps.json';
  const RADAR_REFRESH_INTERVAL_MS = 10 * 60 * 1000;
  const noWeatherLayer = L.layerGroup().addTo(map);
  const radarGroup = L.layerGroup();
  const cloudCoverLayer = L.tileLayer.wms('https://digital.weather.gov/ndfd.conus/wms', {
    layers: 'ndfd.conus.sky',
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    opacity: 0.55,
    zIndex: 340,
    attribution: 'Cloud cover forecast © <a href="https://www.weather.gov/" target="_blank" rel="noreferrer">NOAA/NWS</a>'
  });

  let radarTiles = null;
  let radarRefreshTimer = null;
  let radarLoading = false;
  let cloudErrorShown = false;

  const layerControl = L.control.layers({
    'No weather': noWeatherLayer,
    'Weather radar': radarGroup,
    'Cloud cover forecast': cloudCoverLayer
  }, {
    'Stocked waters': markerLayer
  }, {
    collapsed: true,
    position: 'topright'
  }).addTo(map);

  function latestRadarFrame(metadata) {
    const frames = metadata?.radar?.past;
    return Array.isArray(frames) && frames.length ? frames[frames.length - 1] : null;
  }

  function selectNoWeather() {
    if (map.hasLayer(radarGroup)) map.removeLayer(radarGroup);
    if (map.hasLayer(cloudCoverLayer)) map.removeLayer(cloudCoverLayer);
    if (!map.hasLayer(noWeatherLayer)) noWeatherLayer.addTo(map);
  }

  async function refreshRadar() {
    if (radarLoading || !map.hasLayer(radarGroup)) return;
    radarLoading = true;

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
      selectNoWeather();
    } finally {
      radarLoading = false;
    }
  }

  function startRadarRefresh() {
    refreshRadar();
    window.clearInterval(radarRefreshTimer);
    radarRefreshTimer = window.setInterval(refreshRadar, RADAR_REFRESH_INTERVAL_MS);
  }

  function stopRadarRefresh() {
    window.clearInterval(radarRefreshTimer);
    radarRefreshTimer = null;
  }

  cloudCoverLayer.on('loading', () => {
    cloudErrorShown = false;
  });

  cloudCoverLayer.on('tileerror', error => {
    console.warn('Cloud cover forecast tile could not be loaded.', error);
    if (cloudErrorShown || !map.hasLayer(cloudCoverLayer)) return;
    cloudErrorShown = true;
    window.alert('Cloud cover forecast is temporarily unavailable. Please try again later.');
    selectNoWeather();
  });

  map.on('baselayerchange', event => {
    if (event.layer === radarGroup) {
      startRadarRefresh();
    } else {
      stopRadarRefresh();
    }
  });

  // Stocked waters remain enabled because markerLayer is already on the map.
  // No weather is selected initially, and weather data loads only when requested.
  layerControl.getContainer().setAttribute('aria-label', 'Map layers');
})();