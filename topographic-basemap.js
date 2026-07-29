(() => {
  'use strict';

  if (typeof L === 'undefined' || typeof map === 'undefined' || !map) return;

  // Reuse the street layer created by app.js so visitors can switch back to it.
  let streetLayer = null;
  map.eachLayer(layer => {
    if (!streetLayer && layer instanceof L.TileLayer && !(layer instanceof L.TileLayer.WMS)) {
      streetLayer = layer;
    }
  });

  const topographicLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
    subdomains: 'abc',
    maxZoom: 17,
    attribution: 'Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>, SRTM | Map style © <a href="https://opentopomap.org" target="_blank" rel="noreferrer">OpenTopoMap</a> (CC-BY-SA)'
  });

  if (streetLayer && map.hasLayer(streetLayer)) map.removeLayer(streetLayer);
  topographicLayer.addTo(map);
  topographicLayer.bringToBack();

  const baseMaps = {
    'Topographic': topographicLayer
  };
  if (streetLayer) baseMaps['Street map'] = streetLayer;

  const control = L.control.layers(baseMaps, null, {
    collapsed: true,
    position: 'topleft'
  }).addTo(map);

  control.getContainer().setAttribute('aria-label', 'Base map');
})();
