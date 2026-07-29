/* Updated stocking recency bands for map markers. */
recency=function(d){
  const x=daysOld(d);
  return x<=14?'fresh':x<=30?'recent':x<=60?'older':'stale';
};
