(() => {
  if (typeof L === 'undefined' || typeof map === 'undefined' || !map) return;
  const control = L.control({ position: 'topleft' });
  control.onAdd = () => {
    const element = L.DomUtil.create('section', 'map-symbol-legend');
    element.setAttribute('aria-label', 'Map marker legend');
    element.innerHTML = `<strong>Map key</strong>
      <div class="map-key-section"><b>Fill · stocking recency</b>
        <span><i class="key-dot fresh"></i>Green · 0–14 days</span>
        <span><i class="key-dot recent"></i>Yellow · 15–30 days</span>
        <span><i class="key-dot older"></i>Red · 31–60 days</span>
        <span><i class="key-dot stale"></i>Gray · 61+ days</span>
        <span><i class="key-dot unknown-stock"></i>Dark gray · no history found</span>
      </div>
      <div class="map-key-section"><b>Marker type</b>
        <span><i class="key-outline lake"></i>Blue pointer · lake or pond</span>
        <span><i class="key-outline river"></i>Green pointer · river or stream</span>
        <span><i class="key-gold"></i>Gold ring · Gold Medal Water</span>
        <span><i class="key-gauge"><svg viewBox="0 0 16 16"><path d="M2.5 10a5.5 5.5 0 0 1 11 0"></path><path d="m8 10 3-3"></path><circle cx="8" cy="10" r="1"></circle></svg></i>Gauge · stream-flow data</span>
      </div>`;
    L.DomEvent.disableClickPropagation(element);
    L.DomEvent.disableScrollPropagation(element);
    return element;
  };
  control.addTo(map);
})();
