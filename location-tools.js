(() => {
  'use strict';

  let userLocation = null;
  let userMarker = null;
  let accuracyCircle = null;

  const originalFiltered = filtered;
  const originalRender = render;
  const originalPopup = popup;
  const originalDetailHtml = detailHtml;

  function milesBetween(lat1, lng1, lat2, lng2) {
    const toRadians = value => value * Math.PI / 180;
    const earthRadiusMiles = 3958.7613;
    const dLat = toRadians(lat2 - lat1);
    const dLng = toRadians(lng2 - lng1);
    const a = Math.sin(dLat / 2) ** 2
      + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2))
      * Math.sin(dLng / 2) ** 2;
    return 2 * earthRadiusMiles * Math.asin(Math.sqrt(a));
  }

  function distanceToWater(water) {
    const lat = Number(water.lat);
    const lng = Number(water.lng);
    if (!userLocation || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return milesBetween(userLocation.lat, userLocation.lng, lat, lng);
  }

  function formatDistance(miles) {
    if (!Number.isFinite(miles)) return '';
    if (miles < 1) return `${miles.toFixed(1)} mi`;
    if (miles < 10) return `${miles.toFixed(1)} mi`;
    return `${Math.round(miles)} mi`;
  }

  filtered = function filteredByLocation() {
    const waters = originalFiltered();
    if (!userLocation) return waters;
    return [...waters].sort((a, b) => {
      const aDistance = distanceToWater(a);
      const bDistance = distanceToWater(b);
      if (aDistance == null) return 1;
      if (bDistance == null) return -1;
      return aDistance - bDistance;
    });
  };

  popup = function popupWithDistance(water) {
    const html = originalPopup(water);
    const distance = distanceToWater(water);
    if (distance == null) return html;
    return html.replace(
      '<div class="popup-weather',
      `<p class="location-distance"><strong>${formatDistance(distance)}</strong> straight-line from ${esc(userLocation.label)}</p><div class="popup-weather`
    );
  };

  detailHtml = function detailWithDistance(water) {
    const html = originalDetailHtml(water);
    const distance = distanceToWater(water);
    if (distance == null) return html;
    const summary = `<p class="detail-distance"><strong>${formatDistance(distance)}</strong> straight-line from ${esc(userLocation.label)}. <a href="https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(`${userLocation.lat},${userLocation.lng}`)}&destination=${encodeURIComponent(`${water.lat},${water.lng}`)}" target="_blank" rel="noreferrer">Route from this location ↗</a></p>`;
    return html.replace('</h2>', `</h2>${summary}`);
  };

  render = function renderWithDistances() {
    originalRender();
    if (!userLocation) return;
    const visible = filtered();
    document.querySelectorAll('#results .water-card').forEach((card, index) => {
      const water = visible[index];
      const distance = distanceToWater(water);
      const meta = card.querySelector('.card-meta');
      if (meta && distance != null) meta.textContent += ` · ${formatDistance(distance)} away`;
    });
    const count = document.getElementById('count');
    if (count) count.title = `Sorted nearest to ${userLocation.label}`;
  };

  function updateControls(message, isError = false) {
    const status = document.getElementById('locationStatus');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('error', isError);
  }

  function drawLocation() {
    if (!map || !userLocation) return;
    if (userMarker) map.removeLayer(userMarker);
    if (accuracyCircle) map.removeLayer(accuracyCircle);

    const icon = L.divIcon({
      className: '',
      html: '<div class="user-location-pin" aria-hidden="true"><span></span></div>',
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });
    userMarker = L.marker([userLocation.lat, userLocation.lng], { icon, zIndexOffset: 1000 })
      .addTo(map)
      .bindPopup(`<div class="location-popup"><strong>${esc(userLocation.label)}</strong><br>Your planning location</div>`);

    if (Number.isFinite(userLocation.accuracy) && userLocation.accuracy > 0) {
      accuracyCircle = L.circle([userLocation.lat, userLocation.lng], {
        radius: userLocation.accuracy,
        className: 'user-accuracy-circle',
        interactive: false
      }).addTo(map);
    }
  }

  function setPlanningLocation(lat, lng, label, accuracy = null) {
    userLocation = { lat: Number(lat), lng: Number(lng), label, accuracy };
    sessionStorage.setItem('fishMapPlanningLocation', JSON.stringify(userLocation));
    drawLocation();
    map.setView([userLocation.lat, userLocation.lng], 9);
    updateControls(`Using ${label}. Waters are sorted by straight-line distance.`);
    document.getElementById('clearLocation').hidden = false;
    render();
  }

  function clearPlanningLocation() {
    userLocation = null;
    sessionStorage.removeItem('fishMapPlanningLocation');
    if (userMarker && map) map.removeLayer(userMarker);
    if (accuracyCircle && map) map.removeLayer(accuracyCircle);
    userMarker = null;
    accuracyCircle = null;
    const input = document.getElementById('zipCode');
    if (input) input.value = '';
    document.getElementById('clearLocation').hidden = true;
    updateControls('No planning location selected.');
    render();
  }

  async function lookupColoradoZip(zip) {
    const response = await fetch(`https://api.zippopotam.us/us/${encodeURIComponent(zip)}`);
    if (!response.ok) throw new Error('ZIP code not found');
    const result = await response.json();
    const place = result.places?.find(item => item['state abbreviation'] === 'CO');
    if (!place) throw new Error('Please enter a Colorado ZIP code');
    return {
      lat: Number(place.latitude),
      lng: Number(place.longitude),
      label: `${place['place name']}, CO ${zip}`
    };
  }

  function initializeLocationTools() {
    const useLocation = document.getElementById('useMyLocation');
    const zipForm = document.getElementById('zipForm');
    const clearLocation = document.getElementById('clearLocation');

    useLocation?.addEventListener('click', () => {
      if (!navigator.geolocation) {
        updateControls('This browser does not support location services.', true);
        return;
      }
      useLocation.disabled = true;
      updateControls('Requesting your location…');
      navigator.geolocation.getCurrentPosition(
        position => {
          useLocation.disabled = false;
          setPlanningLocation(
            position.coords.latitude,
            position.coords.longitude,
            'your current location',
            position.coords.accuracy
          );
        },
        error => {
          useLocation.disabled = false;
          const messages = {
            1: 'Location permission was denied. You can still enter a ZIP code.',
            2: 'Your location could not be determined. Try a ZIP code instead.',
            3: 'The location request timed out. Try again or enter a ZIP code.'
          };
          updateControls(messages[error.code] || 'Your location could not be determined.', true);
        },
        { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 }
      );
    });

    zipForm?.addEventListener('submit', async event => {
      event.preventDefault();
      const input = document.getElementById('zipCode');
      const zip = input.value.trim();
      if (!/^\d{5}$/.test(zip)) {
        updateControls('Enter a five-digit Colorado ZIP code.', true);
        input.focus();
        return;
      }
      const submit = zipForm.querySelector('button[type="submit"]');
      submit.disabled = true;
      updateControls(`Looking up ${zip}…`);
      try {
        const location = await lookupColoradoZip(zip);
        setPlanningLocation(location.lat, location.lng, location.label);
      } catch (error) {
        updateControls(error.message || 'That ZIP code could not be found.', true);
      } finally {
        submit.disabled = false;
      }
    });

    clearLocation?.addEventListener('click', clearPlanningLocation);

    try {
      const saved = JSON.parse(sessionStorage.getItem('fishMapPlanningLocation'));
      if (saved && Number.isFinite(saved.lat) && Number.isFinite(saved.lng)) {
        const restore = () => {
          if (!map) return setTimeout(restore, 50);
          userLocation = saved;
          drawLocation();
          updateControls(`Using ${saved.label}. Waters are sorted by straight-line distance.`);
          clearLocation.hidden = false;
          render();
        };
        restore();
      }
    } catch (error) {
      sessionStorage.removeItem('fishMapPlanningLocation');
    }
  }

  initializeLocationTools();
})();
