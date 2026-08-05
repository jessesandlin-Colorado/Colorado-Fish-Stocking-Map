(() => {
  let medalData = { waters: {} };
  let dreamStreamData = null;
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  window.cofishGoldMedal = water => medalData.waters?.[water?.key] || '';

  function badge(water) {
    return window.cofishGoldMedal(water)
      ? '<span class="gold-medal-badge">Gold Medal Water</span>'
      : '';
  }

  function ensureDreamStream() {
    if (!dreamStreamData || typeof dataset === 'undefined' || !Array.isArray(dataset.waters)) return;
    if (dataset.waters.some(water => water.key === dreamStreamData.key)) return;
    dataset.waters.push(dreamStreamData);
    dataset.waters.sort((a, b) => String(a.canonical_name || a.name || '').localeCompare(String(b.canonical_name || b.name || '')));
  }

  const originalRender = window.render;
  window.render = function goldMedalRender() {
    ensureDreamStream();
    return originalRender?.();
  };

  const loadJson = url => fetch(url).then(response => response.ok ? response.json() : Promise.reject(new Error(response.statusText)));
  const loaded = Promise.all([loadJson('config/gold_medal_waters.json'), loadJson('data/dream-stream.json')])
    .then(([data, dreamStream]) => {
      medalData = data;
      dreamStreamData = dreamStream;
      ensureDreamStream();
      window.render?.();
      return data;
    })
    .catch(error => { console.warn('Gold Medal Water data unavailable', error); return medalData; });

  const originalDetailHtml = window.detailHtml;
  window.detailHtml = function goldMedalDetailHtml(water) {
    const html = originalDetailHtml(water);
    const section = window.cofishGoldMedal(water);
    if (!section) return html;
    const notice = `<section class="gold-medal-card"><span aria-hidden="true">★</span><div><strong>Colorado Gold Medal Water</strong><small>${escapeHtml(section)}</small></div></section>`;
    return html.replace('</h2>', `</h2>${notice}`);
  };

  const originalShowDetails = window.showDetails;
  window.showDetails = function goldMedalShowDetails(water) {
    originalShowDetails(water);
    const content = document.getElementById('detailContent');
    if (!content || content.querySelector('.gold-medal-card') || !window.cofishGoldMedal(water)) return;
    content.querySelector('h2')?.insertAdjacentHTML('afterend', `<section class="gold-medal-card"><span aria-hidden="true">★</span><div><strong>Colorado Gold Medal Water</strong><small>${escapeHtml(window.cofishGoldMedal(water))}</small></div></section>`);
  };

  window.cofishGoldMedalWaters = { loaded, badge };
})();
