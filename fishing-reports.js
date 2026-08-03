(() => {
  let reportData = { waters: {} };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const safeUrl = value => /^https:\/\//i.test(String(value || '')) ? escapeHtml(value) : '#';

  function card(water) {
    const reports = reportData.waters?.[water?.key];
    if (!Array.isArray(reports) || !reports.length) return '';
    const links = reports.map(report => `<li><a href="${safeUrl(report.url)}" target="_blank" rel="noopener noreferrer"><span><strong>${escapeHtml(report.source)}</strong><small>${escapeHtml(report.area || water.name)}</small></span><span aria-hidden="true">↗</span></a></li>`).join('');
    return `<section class="fishing-reports-card"><div class="fishing-reports-heading"><span aria-hidden="true">🎣</span><div><p>LOCAL KNOWLEDGE</p><h3>Fishing reports</h3></div></div><ul>${links}</ul><p class="fishing-reports-note">${escapeHtml(reportData.disclaimer || 'Third-party reports may not reflect current closures or access restrictions.')}</p></section>`;
  }

  const loaded = fetch('config/fishing_reports.json')
    .then(response => response.ok ? response.json() : Promise.reject(new Error(response.statusText)))
    .then(data => { reportData = data; window.render?.(); return data; })
    .catch(error => { console.warn('Fishing-report links unavailable', error); return reportData; });

  const originalDetailHtml = window.detailHtml;
  window.detailHtml = function fishingReportsDetailHtml(water) {
    const html = originalDetailHtml(water), reportCard = card(water);
    return reportCard ? html.replace('<h3>Water details</h3>', `${reportCard}<h3>Water details</h3>`) : html;
  };
  const originalShowDetails = window.showDetails;
  window.showDetails = function fishingReportsShowDetails(water) {
    originalShowDetails(water);
    const content = document.getElementById('detailContent');
    if (content && !content.querySelector('.fishing-reports-card')) {
      const reportCard = card(water);
      if (reportCard) {
        const heading = [...content.querySelectorAll('h3')].find(element => element.textContent === 'Water details');
        heading?.insertAdjacentHTML('beforebegin', reportCard);
      }
    }
  };
  window.cofishFishingReports = { loaded, card };
})();
