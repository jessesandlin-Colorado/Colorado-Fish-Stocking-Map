(() => {
  'use strict';

  const originalDetailHtml = detailHtml;

  function groupDatesByYear(dates) {
    const grouped = new Map();
    [...new Set((dates || []).filter(Boolean))]
      .sort((a, b) => b.localeCompare(a))
      .forEach(date => {
        const year = String(date).slice(0, 4) || 'Unknown';
        if (!grouped.has(year)) grouped.set(year, []);
        grouped.get(year).push(date);
      });
    return grouped;
  }

  function historyChart(water) {
    const grouped = groupDatesByYear(water.stocking_dates);
    const total = water.historical_event_count || water.stocking_dates?.length || 0;

    if (!grouped.size) {
      return `<section class="stocking-history" aria-labelledby="stockingHistoryHeading"><div class="stocking-history-heading"><div><h3 id="stockingHistoryHeading">Stocking history</h3><p>No dated stocking events are available.</p></div><strong>${total} total</strong></div></section>`;
    }

    const rows = [...grouped.entries()].map(([year, dates]) => {
      const bricks = dates.map(date => {
        const label = pretty(date);
        return `<button type="button" class="stocking-brick" data-tooltip="${esc(label)}" title="${esc(label)}" aria-label="Stocking event on ${esc(label)}"><span aria-hidden="true"></span></button>`;
      }).join('');
      return `<div class="stocking-year-row"><div class="stocking-year-label"><strong>${esc(year)}</strong><span>${dates.length} event${dates.length === 1 ? '' : 's'}</span></div><div class="stocking-bricks" role="list" aria-label="${dates.length} stocking event${dates.length === 1 ? '' : 's'} in ${esc(year)}">${bricks}</div></div>`;
    }).join('');

    const textRows = [...grouped.entries()].map(([year, dates]) => `<li><strong>${esc(year)}:</strong> ${dates.map(pretty).map(esc).join(' · ')}</li>`).join('');

    return `<section class="stocking-history" aria-labelledby="stockingHistoryHeading"><div class="stocking-history-heading"><div><h3 id="stockingHistoryHeading">Stocking history</h3><p>Each brick represents one stocking event. Hover, tap, or focus a brick to see its date.</p></div><strong>${total} total</strong></div><div class="stocking-chart">${rows}</div><details class="stocking-text"><summary>View dates as text</summary><ul>${textRows}</ul></details></section>`;
  }

  detailHtml = function detailWithStockingChart(water) {
    const html = originalDetailHtml(water);
    const start = html.indexOf('<h3>Stocking history</h3>');
    const endMarker = '<div class="detail-links">';
    const end = html.indexOf(endMarker, start);
    if (start === -1 || end === -1) return html;
    return `${html.slice(0, start)}${historyChart(water)}${html.slice(end)}`;
  };
})();
