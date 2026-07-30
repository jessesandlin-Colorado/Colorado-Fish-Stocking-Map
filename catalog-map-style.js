/* Full Fishing Atlas catalog presentation.
 * Fill = stocking recency; outline = water type.
 */
(function(){
  const originalDetailHtml=detailHtml;
  state.onlyStocked=false;

  daysOld=function(date){
    if(!date)return Infinity;
    const parsed=new Date(`${date}T12:00:00-06:00`);
    if(Number.isNaN(parsed.getTime()))return Infinity;
    return Math.max(0,Math.floor((asOf()-parsed)/86400000));
  };

  recency=function(date){
    if(!date)return'unknown-stock';
    const x=daysOld(date);
    return x<=14?'fresh':x<=30?'recent':x<=60?'older':'stale';
  };

  function waterTypeClass(w){
    const text=String(w.location_type||w.name||'').toLowerCase();
    return /(stream|river|creek|fork)/.test(text)?'water-river':'water-lake';
  }

  function hasStockingHistory(w){
    return Boolean(w.latest_report_date||(Array.isArray(w.stocking_dates)&&w.stocking_dates.length)||(w.historical_event_count>0));
  }

  function hasMappedLocation(w){
    return Number.isFinite(Number(w.lat))&&Number.isFinite(Number(w.lng));
  }

  function firstValue(...values){
    return values.find(value=>value!==null&&value!==undefined&&value!=='');
  }

  function elevationFeet(w){
    const feet=Number(firstValue(w.elevation_ft,w.elevation_feet));
    if(Number.isFinite(feet))return `${Math.round(feet).toLocaleString('en-US')} ft`;
    const meters=Number(firstValue(w.elevation_m,w.elevation_meters));
    if(Number.isFinite(meters))return `${Math.round(meters*3.28084).toLocaleString('en-US')} ft`;
    return null;
  }

  filtered=function(){
    const q=state.search.trim().toLowerCase();
    return dataset.waters.filter(w=>{
      const stocked=hasStockingHistory(w);
      const ageMatches=state.age===9999||Boolean(w.latest_report_date&&daysOld(w.latest_report_date)<=state.age);
      return (!state.onlyStocked||stocked)&&(!q||searchable(w).includes(q))&&ageMatches&&(!state.county||w.county===state.county)&&(!state.species||(w.species||[]).includes(state.species))&&(!state.boating||w.boating===state.boating)&&Object.entries(state.flags).every(([k,v])=>!v||w[k]===v);
    });
  };

  function stockingLabel(w){
    return w.latest_report_date?`Last stocking date: ${pretty(w.latest_report_date)}`:'No matching stocking history';
  }

  detailHtml=function(w){
    if(w.stocking_status==='location-not-matched'&&!hasMappedLocation(w)){
      return originalDetailHtml(w)
        .replace(
          '<h3>Water details</h3>',
          `<p class="warning"><strong>Location not yet mapped.</strong> ${esc(w.location_warning||'These stocking records have not yet been matched to a unique Fishing Atlas location.')}</p><h3>Available details</h3>`
        )
        .replace('<a href="" target="_blank" rel="noreferrer">Fishing Atlas ↗</a>','');
    }
    if(w.latest_report_date)return originalDetailHtml(w);
    const stockingDescription=firstValue(w.stocked_description,w.atlas_stocked_description,w.stocked);
    const rows=[
      ['County',firstValue(w.county,w.county_name)],
      ['Property name',firstValue(w.property_name,w.property,w.prop_name)],
      ['Water type',firstValue(w.location_type,w.water_type,w.loc_type)],
      ['Fishery type',firstValue(w.fishery_type,w.fishery)],
      ['Elevation',elevationFeet(w)],
      ['Ease of access',firstValue(w.access_ease,w.ease_of_access,w.access)],
      ['Boating',w.boating],
      ['Fishing pressure',firstValue(w.fishing_pressure,w.pressure)],
      ['Atlas stocking description',stockingDescription],
      ['Family friendly',firstValue(w.family_friendly,w.opp_family)],
      ['More remote fly fishing',firstValue(w.rustic,w.more_remote_fly_fishing,w.opp_rustic)],
      ['Ice fishing',firstValue(w.ice_fishing,w.opp_ice)],
      ['Accessible pier',firstValue(w.accessible_pier,w.handi_pier)]
    ].filter(([,v])=>v!=null&&v!=='').map(([k,v])=>`<dt>${k}</dt><dd>${esc(v)}</dd>`).join('');
    return `<h2>${esc(displayName(w))}</h2><p class="catalog-badge">Official Fishing Atlas catalog water</p><h3>Species listed by Fishing Atlas</h3>${speciesVisuals(w)}${weatherSkeleton()}<section class="stocking-unknown"><h3>Stocking history</h3><p><strong>No matching stocking record was found in this project's historical database.</strong></p><p>This does not mean the water has never been stocked. It means no matching record was found in the available 2014–present project archive.</p>${stockingDescription?`<p><strong>Fishing Atlas stocking description:</strong> ${esc(stockingDescription)}</p>`:''}</section><h3>Fishing Atlas details</h3>${rows?`<dl>${rows}</dl>`:'<p class="muted">No additional Fishing Atlas details were available for this record.</p>'}<div class="detail-links"><a href="${esc(w.atlas_url)}" target="_blank" rel="noreferrer">Fishing Atlas ↗</a>${w.driving_url?`<a href="${esc(w.driving_url)}" target="_blank" rel="noreferrer">Directions ↗</a>`:''}${w.property_url?`<a href="${esc(w.property_url)}" target="_blank" rel="noreferrer">Property page ↗</a>`:''}${w.survey_url?`<a href="${esc(w.survey_url)}" target="_blank" rel="noreferrer">Survey/report ↗</a>`:''}</div><p class="warning">Always verify public access, closures, and fishing regulations with CPW and the land manager.</p>`;
  };

  popup=function(w){
    return `<div class="popup"><h3>${esc(displayName(w))}</h3><p>${esc(stockingLabel(w))} · ${esc(w.county||'County unavailable')}</p>${speciesVisuals(w,'popup-species')}<div class="popup-weather weather-loading" aria-live="polite" aria-label="Loading weather summary">${['High','Precip.','Wind'].map(label=>`<div class="popup-weather-item"><span>${label}</span><b class="skeleton">—</b></div>`).join('')}</div><button class="popup-detail" onclick="window.openWater('${esc(w.key)}')">Full details</button></div>`;
  };

  render=function(){
    const visible=filtered();
    $('count').textContent=`${visible.length} of ${dataset.waters.length}`;
    $('results').innerHTML='';
    visible.forEach(w=>{
      const n=$('waterCardTemplate').content.cloneNode(true);
      n.querySelector('.card-name').textContent=displayName(w);
      n.querySelector('.card-meta').textContent=w.latest_report_date?`${pretty(w.latest_report_date)} · ${w.county||'County unavailable'} · ${w.historical_event_count||w.stocking_dates?.length||0} stocking event(s)`:`No matching stocking history · ${w.county||'County unavailable'}`;
      n.querySelector('.card-species').textContent=w.species?.length?w.species.join(' · '):'Species not exposed';
      n.querySelector('button').addEventListener('click',()=>{const m=markers.get(w.key);if(m&&map){map.setView([w.lat,w.lng],10);m.openPopup()}showDetails(w)});
      $('results').appendChild(n);
    });
    if(markerLayer){
      markerLayer.clearLayers();markers.clear();
      visible.filter(w=>Number.isFinite(Number(w.lat))&&Number.isFinite(Number(w.lng))).forEach(w=>{
        const icon=L.divIcon({className:'',html:`<div class="marker-pin ${recency(w.latest_report_date)} ${waterTypeClass(w)}"></div>`,iconSize:[20,20],iconAnchor:[10,10]});
        const m=L.marker([Number(w.lat),Number(w.lng)],{icon}).bindPopup(popup(w),{maxWidth:360});
        m.on('popupopen',()=>loadPopupWeather(w,m));markerLayer.addLayer(m);markers.set(w.key,m);
      });
    }
  };

  const onlyStocked=$('onlyStocked');
  if(onlyStocked){
    onlyStocked.addEventListener('change',event=>{
      state.onlyStocked=event.target.checked;
      render();
    });
  }
})();
