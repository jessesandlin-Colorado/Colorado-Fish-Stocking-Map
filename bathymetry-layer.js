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
      dataUrl: 'data/bathymetry/blue-mesa-2019.geojson',
      bounds: [[38.37, -107.39], [38.58, -106.93]]
    }
  ];
  const loading = new Map();
  const legend = L.control({ position: 'bottomleft' });

  legend.onAdd = () => {
    const element = L.DomUtil.create('div', 'bathymetry-legend');
    element.innerHTML = [
      '<strong>Bathymetry / depth contours</strong>',
      '<span><i class="bathymetry-line-sample"></i>25-foot intervals</span>',
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
    sources.forEach(loadSource);
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
      loadSource(source);
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
      `<p>Explore 25-foot contours from the ${source.surveyYear} ${source.water} survey. Depths are relative to full pool, not today’s water level.</p>`,
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
