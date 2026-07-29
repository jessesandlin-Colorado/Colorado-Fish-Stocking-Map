// Display and ordering fixes for imported stocking records.
(function(){
  const placeholder=/^\s*\[?purposely left blank\]?\s*$/i;
  const usable=value=>typeof value==='string'&&value.trim()&&!placeholder.test(value);

  window.displayName=function(w){
    const candidates=[w.canonical_name,w.atlas_name,w.alternate_name,w.property_name,w.name];
    const match=candidates.find(usable);
    if(match)return match.trim();
    if(w.county)return `Unnamed water in ${w.county} County`;
    return 'Unnamed Colorado water';
  };

  window.filtered=function(){
    const q=state.search.trim().toLowerCase();
    return dataset.waters
      .filter(w=>(!q||searchable(w).includes(q))&&daysOld(w.latest_report_date)<=state.age&&(!state.county||w.county===state.county)&&(!state.species||(w.species||[]).includes(state.species))&&(!state.boating||w.boating===state.boating)&&Object.entries(state.flags).every(([k,v])=>!v||w[k]===v))
      .sort((a,b)=>{
        const aTime=a.latest_report_date?Date.parse(`${a.latest_report_date}T12:00:00-06:00`):-Infinity;
        const bTime=b.latest_report_date?Date.parse(`${b.latest_report_date}T12:00:00-06:00`):-Infinity;
        if(bTime!==aTime)return bTime-aTime;
        return displayName(a).localeCompare(displayName(b));
      });
  };
})();
