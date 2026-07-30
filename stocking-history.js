(() => {
  'use strict';

  const originalDetailHtml = detailHtml;

  function stockingEvents(water) {
    if (Array.isArray(water.stocking_events) && water.stocking_events.length) {
      return water.stocking_events.filter(event => event && event.stocking_date);
    }
    return (water.stocking_dates || []).filter(Boolean).map((stocking_date, index) => ({
      event_id: `legacy-${stocking_date}-${index}`,
      stocking_date
    }));
  }

  function groupEventsByYear(events) {
    const grouped = new Map();
    [...events]
      .sort((a, b) => b.stocking_date.localeCompare(a.stocking_date))
      .forEach(event => {
        const year = String(event.stocking_date).slice(0, 4) || 'Unknown';
        if (!grouped.has(year)) grouped.set(year, []);
        grouped.get(year).push(event);
      });
    return grouped;
  }

  function eventLabel(event) {
    const details = [event.species];
    if (Number.isFinite(Number(event.quantity))) details.push(`${Number(event.quantity).toLocaleString('en-US')} fish`);
    if (Number.isFinite(Number(event.length_inches))) details.push(`${Number(event.length_inches)} in avg.`);
    return [pretty(event.stocking_date), ...details.filter(Boolean)].join(' · ');
  }

  function historyChart(water) {
    const events = stockingEvents(water);
    const grouped = groupEventsByYear(events);
    const total = water.historical_event_count || events.length;

    if (!grouped.size) {
      return `<section class="stocking-history" aria-labelledby="stockingHistoryHeading"><div class="stocking-history-heading"><div><h3 id="stockingHistoryHeading">Stocking history</h3><p>No dated stocking events are available.</p></div><strong>${total} total</strong></div></section>`;
    }

    const rows = [...grouped.entries()].map(([year, yearEvents]) => {
      const bricks = yearEvents.map(event => {
        const label = eventLabel(event);
        return `<button type="button" class="stocking-brick" data-tooltip="${esc(label)}" title="${esc(label)}" aria-label="Stocking event on ${esc(label)}"><span aria-hidden="true"></span></button>`;
      }).join('');
      return `<div class="stocking-year-row"><div class="stocking-year-label"><strong>${esc(year)}</strong><span>${yearEvents.length} event${yearEvents.length === 1 ? '' : 's'}</span></div><div class="stocking-bricks" role="list" aria-label="${yearEvents.length} stocking event${yearEvents.length === 1 ? '' : 's'} in ${esc(year)}">${bricks}</div></div>`;
    }).join('');

    const textRows = [...grouped.entries()].map(([year, yearEvents]) => `<li><strong>${esc(year)}:</strong><ul>${yearEvents.map(event => `<li>${esc(eventLabel(event))}</li>`).join('')}</ul></li>`).join('');

    return `<section class="stocking-history" aria-labelledby="stockingHistoryHeading"><div class="stocking-history-heading"><div><h3 id="stockingHistoryHeading">Stocking history</h3><p>Each brick represents one stocking event. Hover, tap, or focus a brick to see its date.</p></div><strong>${total} total</strong></div><div class="stocking-chart">${rows}</div><details class="stocking-text"><summary>View dates as text</summary><ul>${textRows}</ul></details></section>`;
  }

  detailHtml = function detailWithStockingChart(water) {
    const html = originalDetailHtml(water);

    // Atlas-only waters have a purpose-built explanatory section followed by
    // Fishing Atlas metadata. Do not run the stocked-water HTML replacement
    // over that layout or it removes the Atlas detail rows.
    const hasDatedHistory = Array.isArray(water.stocking_dates) && water.stocking_dates.some(Boolean);
    if (!water.latest_report_date && !hasDatedHistory) return html;

    const start = html.indexOf('<h3>Stocking history</h3>');
    const endMarker = '<div class="detail-links">';
    const end = html.indexOf(endMarker, start);
    if (start === -1 || end === -1) return html;
    return `${html.slice(0, start)}${historyChart(water)}${html.slice(end)}`;
  };
})();
