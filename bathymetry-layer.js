(() => {
  'use strict';
  if (typeof L === 'undefined' || typeof map === 'undefined' || !map) return;

  const DATA_URL = 'data/bathymetry/blue-mesa-2019.geojson';
  const SOURCE_URL = 'https://www.usbr.gov/tsc/techreferences/reservoir.html';
  const layer = L.layerGroup();
  let loadingPromise = null;
  const legend = L.control({ position: 'bottomleft' });

  legend.onAdd = () => {
    const element = L.DomUtil.create('div', 'bathymetry-legend');
    element.innerHTML = [
      '<strong>Blue Mesa depth contours</strong>',
      '<span><i class="bathymetry-line-sample"></i>25-foot intervals</span>',
      '<small>Depth below 7,519-ft full pool · 2019 survey</small>',
      `<small><a href="${SOURCE_URL}" target="_blank" rel="noreferrer">U.S. Bureau of Reclamation ↗</a></small>`
    ].join('');
    L.DomEvent.disableClickPropagation(element);
    return element;
  };

  async function loadContours() {
    if (loadingPromise) return loadingPromise;
    loadingPromise = fetch(DATA_URL)
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
              `${depth} ft below full pool · elevation ${elevation.toLocaleString()} ft`,
              { sticky: true }
            );
          }
        });
        contours.addTo(layer);
        return contours;
      })
      .catch(error => {
        loadingPromise = null;
        if (map.hasLayer(layer)) map.removeLayer(layer);
        console.warn('Bathymetry could not be loaded.', error);
        window.alert('The Blue Mesa depth contours could not be loaded. Please try again later.');
        throw error;
      });
    return loadingPromise;
  }

  layer.on('add', () => {
    loadContours();
    if (!legend.getContainer()) legend.addTo(map);
  });
  layer.on('remove', () => {
    if (legend.getContainer()) legend.remove();
  });

  window.cofishBathymetry = {
    layer,
    show({ zoom = false } = {}) {
      layer.addTo(map);
      if (zoom) map.fitBounds([[38.37, -107.39], [38.58, -106.93]], { padding: [24, 24] });
    }
  };

  const originalDetailHtml = detailHtml;
  detailHtml = function detailWithBathymetry(water) {
    const html = originalDetailHtml(water);
    if (Number(water.atlas_id) !== 152) return html;
    const card = [
      '<section class="bathymetry-card">',
      '<h3>Depth contours available</h3>',
      '<p>Explore 25-foot contours from the 2019 Blue Mesa reservoir survey. Depths are relative to full pool, not today’s water level.</p>',
      '<button class="bathymetry-button" type="button" onclick="window.showBlueMesaBathymetry()">Show depth contours</button>',
      '</section>'
    ].join('');
    return html.replace('<h3>Water details</h3>', `${card}<h3>Water details</h3>`);
  };

  window.showBlueMesaBathymetry = () => {
    window.cofishBathymetry.show({ zoom: true });
    const dialog = document.getElementById('details');
    if (dialog?.open) dialog.close();
  };
})();
