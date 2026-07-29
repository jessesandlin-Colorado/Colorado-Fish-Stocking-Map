(() => {
  'use strict';

  let userLocation = null;
  let userMarker = null;
  let accuracyCircle = null;

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
    updateControls(`Using ${label}. Open any water to calculate road miles and estimated drive time.`);
    document.getElementById('clearLocation').hidden = false;
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
          updateControls(`Using ${saved.label}. Open any water to calculate road miles and estimated drive time.`);
          clearLocation.hidden = false;
        };
        restore();
      }
    } catch (error) {
      sessionStorage.removeItem('fishMapPlanningLocation');
    }
  }

  initializeLocationTools();
})();
