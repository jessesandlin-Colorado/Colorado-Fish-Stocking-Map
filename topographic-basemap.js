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

  const usgsAttribution = 'Map services © <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noreferrer">USGS The National Map</a>';
  const usgsTiles = service => `https://basemap.nationalmap.gov/arcgis/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`;
  const layerOptions = {
    maxZoom: 16,
    attribution: usgsAttribution
  };

  const usgsTopo = L.tileLayer(usgsTiles('USGSTopo'), layerOptions);
  const usgsImagery = L.tileLayer(usgsTiles('USGSImageryOnly'), layerOptions);
  const usgsImageryTopo = L.tileLayer(usgsTiles('USGSImageryTopo'), layerOptions);

  if (streetLayer && map.hasLayer(streetLayer)) map.removeLayer(streetLayer);
  usgsTopo.addTo(map);
  usgsTopo.bringToBack();

  const baseMaps = {
    '🏔 USGS Topo': usgsTopo,
    '🛰 USGS Imagery': usgsImagery,
    '🛰 USGS Imagery + Topo': usgsImageryTopo
  };
  if (streetLayer) baseMaps['🗺 Street map'] = streetLayer;

  const control = L.control.layers(baseMaps, null, {
    collapsed: true,
    position: 'topleft'
  }).addTo(map);

  control.getContainer().setAttribute('aria-label', 'Base map');
})();
