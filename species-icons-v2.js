const SPECIES_DIRECTORY={
  'Bass: Largemouth':{displayName:'Largemouth Bass',profileUrl:'https://cpw.state.co.us/species/largemouth-bass'},
  'Bass: Smallmouth':{displayName:'Smallmouth Bass',profileUrl:'https://cpw.state.co.us/species/smallmouth-bass'},
  'Bass: White':{displayName:'White Bass',profileUrl:'https://cpw.state.co.us/species/white-bass'},
  'Bass: Wiper':{displayName:'Wiper',profileUrl:'https://cpw.state.co.us/species/wiper'},
  'Carp: Common':{displayName:'Common Carp',profileUrl:'https://cpw.state.co.us/species/common-carp'},
  'Catfish: Black Bullhead':{displayName:'Black Bullhead Catfish',profileUrl:'https://cpw.state.co.us/species/black-bullhead-catfish'},
  'Catfish: Blue':{displayName:'Blue Catfish',profileUrl:'https://cpw.state.co.us/species/blue-catfish'},
  'Catfish: Channel':{displayName:'Channel Catfish',profileUrl:'https://cpw.state.co.us/species/channel-catfish'},
  'Crappie: Black':{displayName:'Black Crappie',profileUrl:'https://cpw.state.co.us/species/black-crappie'},
  'Crappie: Unspecified':{displayName:'Crappie',profileUrl:'https://cpw.state.co.us/species/white-crappie'},
  'Crappie: White':{displayName:'White Crappie',profileUrl:'https://cpw.state.co.us/species/white-crappie'},
  'Grayling: Arctic':{displayName:'Grayling',profileUrl:'https://cpw.state.co.us/species/grayling-arctic'},
  'Perch: Sauger':{displayName:'Sauger',profileUrl:'https://cpw.state.co.us/species/sauger'},
  'Perch: Saugeye':{displayName:'Saugeye',profileUrl:'https://cpw.state.co.us/species/saugeye'},
  'Perch: Walleye':{displayName:'Walleye',profileUrl:'https://cpw.state.co.us/species/walleye'},
  'Perch: Yellow':{displayName:'Yellow Perch',profileUrl:'https://cpw.state.co.us/species/yellow-perch'},
  'Pike: Northern':{displayName:'Northern Pike',profileUrl:'https://cpw.state.co.us/species/northern-pike'},
  'Pike: Tiger Muskie':{displayName:'Tiger Muskie',profileUrl:'https://cpw.state.co.us/species/tiger-muskie'},
  'Salmon: Kokanee':{displayName:'Kokanee Salmon',profileUrl:'https://cpw.state.co.us/species/kokanee-salmon'},
  'Sunfish: Bluegill':{displayName:'Bluegill Sunfish',profileUrl:'https://cpw.state.co.us/species/bluegill'},
  'Sunfish: Green':{displayName:'Green Sunfish',profileUrl:'https://cpw.state.co.us/species/green-sunfish'},
  'Sunfish: Pumpkinseed':{displayName:'Pumpkinseed Sunfish',profileUrl:'https://cpw.state.co.us/species/pumpkinseed-sunfish'},
  'Sunfish: Redear':{displayName:'Redear Sunfish',profileUrl:'https://cpw.state.co.us/species/redear-sunfish'},
  'Trout: Brook':{displayName:'Brook Trout',profileUrl:'https://cpw.state.co.us/species/brook-trout'},
  'Trout: Brown':{displayName:'Brown Trout',profileUrl:'https://cpw.state.co.us/species/brown-trout'},
  'Trout: Cutbow':{displayName:'Cutbow Trout',profileUrl:'https://cpw.state.co.us/species/cutbow'},
  'Trout: Cutthroat':{displayName:'Cutthroat',profileUrl:'https://cpw.state.co.us/species/greenback-cutthroat-trout'},
  'Trout: Lake':{displayName:'Lake Trout',profileUrl:'https://cpw.state.co.us/species/lake-trout'},
  'Trout: Mountain Whitefish':{displayName:'Mountain Whitefish',profileUrl:'https://cpw.state.co.us/species/mountain-whitefish'},
  'Trout: Rainbow':{displayName:'Rainbow Trout',profileUrl:'https://cpw.state.co.us/species/rainbow-trout'},
  'Trout: Snake River Cutthroat':{displayName:'Snake River Cutthroat',profileUrl:'https://cpw.state.co.us/species/snake-river-cutthroat-trout'},
  'Trout: Splake':{displayName:'Splake',profileUrl:'https://cpw.state.co.us/species/splake'},
  'Trout: Tiger':{displayName:'Tiger Trout',profileUrl:'https://cpw.state.co.us/species/tiger-trout'},
  'Trout: Unspecified':{displayName:'Other',profileUrl:'https://cpw.state.co.us/fish-species-information-list'}
};

function speciesInfo(name){return SPECIES_DIRECTORY[name]||{displayName:String(name||''),profileUrl:'https://cpw.state.co.us/fish-species-information-list'}}
function finalSpeciesKind(name){const s=String(name||'').toLowerCase();const rules=[[['cutbow'],'generic-trout'],[['rainbow smelt'],'rainbow-smelt'],[['rainbow'],'rainbow-trout'],[['brown trout','trout: brown'],'brown-trout'],[['cutthroat'],'cutthroat-trout'],[['brook'],'brook-trout'],[['lake trout','trout: lake','mackinaw'],'lake-trout'],[['kokanee'],'kokanee-salmon'],[['tiger trout','trout: tiger'],'tiger-trout'],[['splake'],'splake'],[['largemouth'],'largemouth-bass'],[['smallmouth'],'smallmouth-bass'],[['hybrid striped','wiper'],'hybrid-striped-bass'],[['white bass','bass: white'],'white-bass'],[['rock bass'],'rock-bass'],[['bluegill'],'bluegill'],[['black crappie','crappie: black'],'black-crappie'],[['white crappie','crappie: white','crappie: unspecified'],'white-crappie'],[['channel catfish','catfish: channel'],'channel-catfish'],[['blue catfish','catfish: blue'],'blue-catfish'],[['yellow bullhead'],'yellow-bullhead'],[['black bullhead','catfish: black bullhead'],'black-bullhead'],[['bullhead'],'bullhead'],[['walleye','perch: walleye'],'walleye'],[['sauger','perch: sauger'],'sauger'],[['saugeye','perch: saugeye'],'saugeye'],[['yellow perch','perch: yellow'],'yellow-perch'],[['green sunfish','sunfish: green'],'green-sunfish'],[['pumpkinseed','sunfish: pumpkinseed'],'pumpkinseed'],[['redear','sunfish: redear'],'redear-sunfish'],[['northern pike','pike: northern'],'northern-pike'],[['tiger muskie','pike: tiger muskie'],'muskellunge'],[['grayling'],'grayling'],[['mountain whitefish'],'mountain-whitefish'],[['common carp','carp: common'],'common-carp']];for(const[needles,kind]of rules)if(needles.some(n=>s.includes(n)))return kind;return'generic-trout'}
function fishIconPath(name){return `assets/species/${finalSpeciesKind(name)}.svg`}
speciesCard=function(name){const info=speciesInfo(name),safeName=esc(info.displayName),safeImported=esc(name),safeUrl=esc(info.profileUrl),src=fishIconPath(name);return `<span class="species-card"><img class="species-fish-icon" src="${src}" alt="${safeName} illustration" loading="lazy" decoding="async" onerror="this.hidden=true"><a class="species-profile-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="View the CPW profile for ${safeImported}">${safeName}<span class="species-link-arrow" aria-hidden="true">↗</span></a></span>`};
speciesVisuals=function(w,extra=''){const items=(w.species||[]).map(speciesCard).join('');return items?`<div class="species-visuals ${extra}">${items}</div>`:'<p class="muted">No species names were exposed by the current Atlas record.</p>'};

function cleanSidebarSpeciesNames(root=document){root.querySelectorAll('.card-species').forEach(el=>{const raw=el.textContent.trim();if(!raw||raw==='Species not exposed')return;el.textContent=raw.split(' · ').map(name=>speciesInfo(name).displayName).join(' · ')})}
function cleanSpeciesSelect(){const select=document.getElementById('species');if(!select||select.options.length<2)return false;for(const option of select.options){if(option.value)option.textContent=speciesInfo(option.value).displayName}return true}
const results=document.getElementById('results');if(results){new MutationObserver(()=>cleanSidebarSpeciesNames(results)).observe(results,{childList:true,subtree:true});cleanSidebarSpeciesNames(results)}
let selectAttempts=0;const selectTimer=setInterval(()=>{selectAttempts+=1;if(cleanSpeciesSelect()||selectAttempts>40)clearInterval(selectTimer)},250);