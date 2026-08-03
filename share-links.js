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

  function applySiteBranding() {
    document.title = 'COFish – Colorado Fishing Map, Stocking History & Fishing Atlas';

    const eyebrow = document.querySelector('.topbar .eyebrow');
    if (eyebrow) eyebrow.textContent = 'COFISH';

    if (!document.querySelector('link[rel="icon"]')) {
      const favicon = document.createElement('link');
      favicon.rel = 'icon';
      favicon.type = 'image/svg+xml';
      favicon.href = 'favicon.svg';
      document.head.appendChild(favicon);
    }

    if (document.querySelector('.site-footer')) return;
    const footer = document.createElement('footer');
    footer.className = 'site-footer';
    footer.innerHTML = `<div class="site-footer-main">
      <span>© 2026 COFish</span>
      <nav aria-label="Site information">
        <a href="https://cpw.state.co.us/activities/fishing" target="_blank" rel="noreferrer">Data Sources</a>
        <details><summary>Privacy</summary><p>COFish does not require an account or collect personal information. Location and ZIP-code tools are used in your browser to plan routes. Third-party map, weather, and routing services may receive ordinary web requests needed to provide those features.</p></details>
        <details><summary>Disclaimer</summary><p>COFish is an unofficial planning tool. Stocking records, access, regulations, closures, weather, and road conditions can change. Always confirm current information with Colorado Parks and Wildlife and the applicable land manager.</p></details>
        <a href="https://github.com/jessesandlin-Colorado/Colorado-Fish-Stocking-Map/issues" target="_blank" rel="noreferrer">Contact</a>
      </nav>
    </div>`;
    document.body.appendChild(footer);
  }

  applySiteBranding();
})();

// Stream-flow is kept in its own small bundle so the core map remains usable
// if Colorado DWR data is temporarily unavailable.
const streamflowStyles = document.createElement('link');
streamflowStyles.rel = 'stylesheet';
streamflowStyles.href = 'streamflow.css';
document.head.appendChild(streamflowStyles);
const streamflowScript = document.createElement('script');
streamflowScript.src = 'streamflow.js';
document.body.appendChild(streamflowScript);
const symbolLegendStyles = document.createElement('link');
symbolLegendStyles.rel = 'stylesheet';
symbolLegendStyles.href = 'map-symbol-legend.css';
document.head.appendChild(symbolLegendStyles);
const symbolLegendScript = document.createElement('script');
symbolLegendScript.src = 'map-symbol-legend.js';
document.body.appendChild(symbolLegendScript);
