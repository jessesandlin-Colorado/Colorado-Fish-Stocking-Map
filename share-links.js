(() => {
  'use strict';

  const WATER_PARAM = 'water';
  const originalShowDetails = showDetails;
  let activeWater = null;
  let restoredInitialLink = false;

  function waterKey(water) {
    return String(water?.key || water?.watercode || water?.water_code || water?.id || '');
  }

  function urlForWater(water) {
    const url = new URL(window.location.href);
    url.searchParams.set(WATER_PARAM, waterKey(water));
    url.hash = '';
    return url;
  }

  function setUrlForWater(water, replace = true) {
    const url = urlForWater(water);
    history[replace ? 'replaceState' : 'pushState']({ water: waterKey(water) }, '', url);
    return url;
  }

  function clearWaterFromUrl() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has(WATER_PARAM)) return;
    url.searchParams.delete(WATER_PARAM);
    history.replaceState({}, '', url);
  }

  function sharePanel(water) {
    return `<section class="share-water" aria-labelledby="shareWaterHeading">
      <div>
        <p class="share-water-eyebrow">SHARE THIS WATER</p>
        <h3 id="shareWaterHeading">Send this exact map result</h3>
      </div>
      <button type="button" class="share-water-button" data-share-water="${esc(waterKey(water))}">Copy shareable link</button>
      <p class="share-water-status" role="status" aria-live="polite"></p>
    </section>`;
  }

  function addSharePanel(water) {
    const content = document.getElementById('detailContent');
    if (!content || content.querySelector('.share-water')) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = sharePanel(water);
    const heading = content.querySelector('h2');
    if (heading) heading.insertAdjacentElement('afterend', wrapper.firstElementChild);
    else content.prepend(wrapper.firstElementChild);
  }

  async function copyShareLink(water, button) {
    const url = setUrlForWater(water);
    const status = button.closest('.share-water')?.querySelector('.share-water-status');
    const copiedText = 'Link copied. Anyone opening it will see this water.';

    try {
      await navigator.clipboard.writeText(url.toString());
    } catch (error) {
      const input = document.createElement('textarea');
      input.value = url.toString();
      input.setAttribute('readonly', '');
      input.style.position = 'fixed';
      input.style.opacity = '0';
      document.body.appendChild(input);
      input.select();
      const copied = document.execCommand('copy');
      input.remove();
      if (!copied) {
        if (status) status.textContent = 'Copy failed. Use your browser address bar to copy the link.';
        return;
      }
    }

    const previous = button.textContent;
    button.textContent = 'Link copied ✓';
    if (status) status.textContent = copiedText;
    window.setTimeout(() => {
      if (button.isConnected) button.textContent = previous;
    }, 2200);
  }

  showDetails = function showDetailsWithShareLink(water) {
    activeWater = water;
    setUrlForWater(water);
    originalShowDetails(water);
    addSharePanel(water);
  };

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-share-water]');
    if (!button) return;
    const key = button.dataset.shareWater;
    const water = dataset.waters.find(item => waterKey(item) === key) || activeWater;
    if (water) copyShareLink(water, button);
  });

  document.getElementById('details')?.addEventListener('close', () => {
    activeWater = null;
    clearWaterFromUrl();
  });

  function restoreSharedWater() {
    if (restoredInitialLink || !Array.isArray(dataset?.waters) || !dataset.waters.length) return false;
    const key = new URL(window.location.href).searchParams.get(WATER_PARAM);
    if (!key) {
      restoredInitialLink = true;
      return true;
    }

    const water = dataset.waters.find(item => waterKey(item) === key);
    if (!water) {
      restoredInitialLink = true;
      clearWaterFromUrl();
      return true;
    }

    restoredInitialLink = true;
    if (map && Number.isFinite(Number(water.lat)) && Number.isFinite(Number(water.lng))) {
      map.setView([Number(water.lat), Number(water.lng)], 10);
      const marker = markers.get(water.key);
      if (marker) marker.openPopup();
    }
    showDetails(water);
    return true;
  }

  const restoreTimer = window.setInterval(() => {
    if (restoreSharedWater()) window.clearInterval(restoreTimer);
  }, 100);
  window.setTimeout(() => window.clearInterval(restoreTimer), 15000);

  window.addEventListener('popstate', () => {
    restoredInitialLink = false;
    restoreSharedWater();
  });
})();
