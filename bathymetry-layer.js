(() => {
  'use strict';
  if (typeof L === 'undefined' || typeof map === 'undefined' || !map) return;

  const SOURCE_URL = 'https://www.usbr.gov/tsc/techreferences/reservoir.html';
  const layer = L.layerGroup();
  const sources = [
    {
      atlasId: 152,
      water: 'Blue Mesa Reservoir',
      surveyYear: 2019,
      fullPoolElevationFt: 7519,
      contourIntervalFt: 25,
      dataUrl: 'data/bathymetry/blue-mesa-2019.geojson',
      bounds: [[38.37, -107.39], [38.58, -106.93]]
    },
    {
      atlasId: 475,
      water: 'Navajo Reservoir',
      surveyYear: 2019,
      fullPoolElevationFt: 6085,
      contourIntervalFt: 25,
      dataUrl: 'data/bathymetry/navajo-2019.geojson',
      bounds: [[36.79, -107.63], [37.05, -107.34]]
    },
    {
      atlasId: 79,
      water: 'Flatiron Reservoir',
      surveyYear: 2012,
      fullPoolElevationFt: 5478.34,
      contourIntervalFt: 10,
      dataUrl: 'data/bathymetry/flatiron-2012.geojson',
      bounds: [[40.364, -105.237], [40.375, -105.228]]
    },
    {
      atlasId: 795,
      water: 'Lake Estes',
      surveyYear: 2001,
      fullPoolElevationFt: 7475,
      contourIntervalFt: 10,
      dataUrl: 'data/bathymetry/lake-estes-2001.geojson',
      bounds: [[40.37, -105.507], [40.379, -105.487]]
    },
    {
      atlasId: 265,
      water: 'Lake Isabel',
      surveyYear: 2012,
      fullPoolElevationFt: 8477.7,
      contourIntervalFt: 10,
      dataUrl: 'data/bathymetry/lake-isabel-2012.geojson',
      bounds: [[37.982, -105.057], [37.988, -105.048]]
    },
    {
      atlasId: 284,
      water: 'Pinewood Reservoir',
      surveyYear: 2012,
      fullPoolElevationFt: 6580,
      contourIntervalFt: 10,
      dataUrl: 'data/bathymetry/pinewood-2012.geojson',
      bounds: [[40.359, -105.293], [40.369, -105.278]]
    }
  ];
  const loading = new Map();
  const legend = L.control({ position: 'bottomleft' });

  legend.onAdd = () => {
    const element = L.DomUtil.create('div', 'bathymetry-legend');
    element.innerHTML = [
      '<strong>Bathymetry / depth contours</strong>',
      '<span><i class="bathymetry-line-sample"></i>10–25-foot intervals</span>',
      '<small>Historical surveys · depth relative to each water’s stated reference elevation</small>',
      `<small><a href="${SOURCE_URL}" target="_blank" rel="noreferrer">U.S. Bureau of Reclamation ↗</a></small>`
    ].join('');
    L.DomEvent.disableClickPropagation(element);
    return element;
  };

  async function loadSource(source) {
    if (loading.has(source.atlasId)) return loading.get(source.atlasId);
    const promise = fetch(source.dataUrl)
      .then(response => {
        if (!response.ok) throw new Error(`Bathymetry request failed (${response.status})`);
        return response.json();
      })
      .then(data => {
        const contours = L.geoJSON(data, {
          style(feature) {
            const major = feature.properties.major;
            return {
              color: major ? '#064e73' : '#0b78a5',
              opacity: major ? 0.95 : 0.75,
              weight: major ? 2.6 : 1.35
            };
          },
          onEachFeature(feature, contour) {
            const { depth_ft: depth, elevation_ft: elevation } = feature.properties;
            contour.bindTooltip(
              `${source.water} · ${depth} ft below full pool · elevation ${elevation.toLocaleString()} ft`,
              { sticky: true }
            );
          }
        });
        contours.addTo(layer);
        return contours;
      })
      .catch(error => {
        loading.delete(source.atlasId);
        console.warn(`${source.water} bathymetry could not be loaded.`, error);
        window.alert(`${source.water} depth contours could not be loaded. Please try again later.`);
        throw error;
      });
    loading.set(source.atlasId, promise);
    return promise;
  }

  layer.on('add', () => {
    sources.forEach(source => loadSource(source).catch(() => {}));
    if (!legend.getContainer()) legend.addTo(map);
  });
  layer.on('remove', () => {
    if (legend.getContainer()) legend.remove();
  });

  window.cofishBathymetry = {
    layer,
    sources,
    show(source, { zoom = false } = {}) {
      layer.addTo(map);
      loadSource(source).catch(() => {});
      if (zoom) map.fitBounds(source.bounds, { padding: [24, 24] });
    }
  };

  const originalDetailHtml = detailHtml;
  detailHtml = function detailWithBathymetry(water) {
    const html = originalDetailHtml(water);
    const source = sources.find(item => item.atlasId === Number(water.atlas_id));
    if (!source) return html;
    const card = [
      '<section class="bathymetry-card">',
      '<h3>Depth contours available</h3>',
      `<p>Explore ${source.contourIntervalFt}-foot contours from the ${source.surveyYear} ${source.water} survey. Depths are relative to full pool, not today’s water level.</p>`,
      `<button class="bathymetry-button" type="button" onclick="window.showWaterBathymetry(${source.atlasId})">Show depth contours</button>`,
      '</section>'
    ].join('');
    return html.replace('<h3>Water details</h3>', `${card}<h3>Water details</h3>`);
  };

  window.showWaterBathymetry = atlasId => {
    const source = sources.find(item => item.atlasId === Number(atlasId));
    if (!source) return;
    window.cofishBathymetry.show(source, { zoom: true });
    const dialog = document.getElementById('details');
    if (dialog?.open) dialog.close();
  };
})();
