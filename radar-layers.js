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
  const windLayer = L.tileLayer.wms('https://digital.weather.gov/ndfd.conus/wms', {
    layers: 'ndfd.conus.windspd',
    format: 'image/png',
    transparent: true,
    version: '1.3.0',
    opacity: 0.68,
    zIndex: 345,
    attribution: 'Wind speed forecast © <a href="https://www.weather.gov/" target="_blank" rel="noreferrer">NOAA/NWS</a>'
  });

  let radarTiles = null;
  let radarRefreshTimer = null;
  let radarLoading = false;
  let cloudErrorShown = false;
  let windErrorShown = false;

  const overlays = {
    'Stocked waters': markerLayer
  };

  const layerControl = L.control.layers({
    'No weather': noWeatherLayer,
    'Weather radar': radarGroup,
    'Cloud cover forecast': cloudCoverLayer,
    'Wind speed forecast': windLayer
  }, overlays, {
    collapsed: true,
    position: 'topright'
  }).addTo(map);

  const legendControl = L.control({ position: 'bottomright' });
  legendControl.onAdd = () => {
    const container = L.DomUtil.create('div', 'weather-layer-legend');
    container.hidden = true;
    container.setAttribute('aria-live', 'polite');
    L.DomEvent.disableClickPropagation(container);
    return container;
  };
  legendControl.addTo(map);
  const legendContainer = legendControl.getContainer();

  Object.assign(legendContainer.style, {
    background: 'rgba(255, 255, 255, 0.94)',
    border: '1px solid rgba(0, 0, 0, 0.18)',
    borderRadius: '6px',
    boxShadow: '0 1px 5px rgba(0, 0, 0, 0.25)',
    color: '#222',
    font: '12px/1.35 system-ui, sans-serif',
    maxWidth: '190px',
    padding: '8px 10px'
  });

  function latestRadarFrame(metadata) {
    const frames = metadata?.radar?.past;
    return Array.isArray(frames) && frames.length ? frames[frames.length - 1] : null;
  }

  function hideLegend() {
    legendContainer.hidden = true;
    legendContainer.replaceChildren();
  }

  function showLegend(title, rows, note = '') {
    legendContainer.replaceChildren();

    const heading = document.createElement('strong');
    heading.textContent = title;
    heading.style.display = 'block';
    heading.style.marginBottom = '5px';
    legendContainer.appendChild(heading);

    rows.forEach(row => {
      const item = document.createElement('div');
      item.style.alignItems = 'center';
      item.style.display = 'flex';
      item.style.gap = '6px';
      item.style.marginTop = '3px';

      const swatch = document.createElement('span');
      swatch.setAttribute('aria-hidden', 'true');
      Object.assign(swatch.style, {
        background: row.color,
        border: '1px solid rgba(0, 0, 0, 0.2)',
        display: 'inline-block',
        flex: '0 0 18px',
        height: '9px'
      });

      const label = document.createElement('span');
      label.textContent = row.label;
      item.append(swatch, label);
      legendContainer.appendChild(item);
    });

    if (note) {
      const caption = document.createElement('small');
      caption.textContent = note;
      Object.assign(caption.style, {
        display: 'block',
        marginTop: '6px',
        opacity: '0.75'
      });
      legendContainer.appendChild(caption);
    }

    legendContainer.hidden = false;
  }

  function updateLegend(activeLayer) {
    if (activeLayer === windLayer) {
      showLegend('Wind speed forecast', [
        { color: 'rgba(255,255,204,0.9)', label: 'Light wind' },
        { color: 'rgba(161,218,180,0.9)', label: 'Moderate wind' },
        { color: 'rgba(65,182,196,0.9)', label: 'Strong wind' },
        { color: 'rgba(37,52,148,0.95)', label: 'Very strong wind' }
      ], 'NOAA/NWS sustained 10-meter wind-speed forecast.');
    } else if (activeLayer === cloudCoverLayer) {
      showLegend('Cloud cover forecast', [
        { color: 'rgba(255,255,255,0.45)', label: 'Mostly clear' },
        { color: 'rgba(205,205,205,0.55)', label: 'Partly cloudy' },
        { color: 'rgba(145,145,145,0.65)', label: 'Mostly cloudy' },
        { color: 'rgba(80,80,80,0.75)', label: 'Overcast' }
      ], 'NOAA forecast percentage of opaque sky cover.');
    } else if (activeLayer === radarGroup) {
      showLegend('Weather radar', [
        { color: '#7cc96f', label: 'Light precipitation' },
        { color: '#f1d04b', label: 'Moderate precipitation' },
        { color: '#d95a4e', label: 'Heavy precipitation' }
      ], 'Latest available radar image.');
    } else {
      hideLegend();
    }
  }

  function selectNoWeather() {
    if (map.hasLayer(radarGroup)) map.removeLayer(radarGroup);
    if (map.hasLayer(cloudCoverLayer)) map.removeLayer(cloudCoverLayer);
    if (map.hasLayer(windLayer)) map.removeLayer(windLayer);
    if (!map.hasLayer(noWeatherLayer)) noWeatherLayer.addTo(map);
    hideLegend();
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

  windLayer.on('loading', () => {
    windErrorShown = false;
  });

  windLayer.on('tileerror', error => {
    console.warn('Wind-speed forecast tile could not be loaded.', error);
    if (windErrorShown || !map.hasLayer(windLayer)) return;
    windErrorShown = true;
    window.alert('The NOAA wind-speed forecast layer is temporarily unavailable. Please try again later.');
    selectNoWeather();
  });

  map.on('baselayerchange', event => {
    if (event.layer === radarGroup) {
      startRadarRefresh();
    } else {
      stopRadarRefresh();
    }
    updateLegend(event.layer);
  });

  // Stocked waters remain enabled because markerLayer is already on the map.
  // No weather is selected initially, and weather data loads only when requested.
  layerControl.getContainer().setAttribute('aria-label', 'Map layers');
})();
