function charts(){
  const chart=document.getElementById('charts');
  if(!chart)return;

  const reference=dataset.generated_at?new Date(dataset.generated_at):new Date();
  const cutoff=new Date(reference);
  cutoff.setFullYear(cutoff.getFullYear()-1);

  const top=dataset.waters
    .map(w=>{
      const recentDates=(w.stocking_dates||[])
        .map(d=>new Date(`${d}T12:00:00-06:00`))
        .filter(d=>!Number.isNaN(d.getTime())&&d>=cutoff&&d<=reference);
      return{water:w,count:recentDates.length,latest:recentDates.length?Math.max(...recentDates.map(d=>d.getTime())):0};
    })
    .filter(item=>item.count>0)
    .sort((a,b)=>b.count-a.count||b.latest-a.latest||displayName(a.water).localeCompare(displayName(b.water)))
    .slice(0,5);

  if(!top.length){
    chart.innerHTML='<h3>Past year\'s most stocked waters</h3><p class="muted">No stocking events were found in the past year.</p>';
    return;
  }

  const max=Math.max(...top.map(item=>item.count));
  chart.innerHTML=`<h3>Past year's most stocked waters</h3>${top.map(item=>`<div class="bar-row"><span>${esc(displayName(item.water))}</span><i style="--w:${Math.round(item.count/max*100)}%"></i><b>${item.count}</b></div>`).join('')}`;
}
