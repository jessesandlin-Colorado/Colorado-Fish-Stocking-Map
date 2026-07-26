#!/usr/bin/env python3
"""Download the CPW report, resolve Fishing Atlas IDs, and build web-ready JSON."""
import argparse, json, re, sys, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import requests
from bs4 import BeautifulSoup

CPW='https://cpw.state.co.us/activities/fishing/fishing-awards-and-records/fish-stocking-report'
ATLAS_BASE='https://ndismaps.nrel.colostate.edu/arcgis/rest/services/FishingAtlas/FishingAtlas_Main_Map/MapServer'
ATLAS_LAYERS=(59,61,63,65,67)
DATE_RE=re.compile(r'\b(\d{1,2}/\d{1,2}/\d{4})\b')

def clean(x): return re.sub(r'\s+',' ',x or '').strip()
def atlas_id(url):
    try:return int(parse_qs(urlparse(url).query).get('value',[None])[0])
    except:return None

def parse_report(html):
    soup=BeautifulSoup(html,'html.parser'); rows=[]
    for a in soup.select('a[href*="fishingatlas"][href*="value="]'):
        tr=a.find_parent('tr')
        if not tr: continue
        cells=[clean(c.get_text(' ',strip=True)) for c in tr.find_all(['td','th'])]
        text=' | '.join(cells); m=DATE_RE.search(text)
        if not m: continue
        date=datetime.strptime(m.group(1),'%m/%d/%Y').date().isoformat()
        region=next((x.lower() for x in cells if x.lower() in {'northeast','northwest','southeast','southwest'}),'unknown')
        name=next((x for x in cells if x and x.lower() not in {'atlas',region} and not DATE_RE.fullmatch(x)),cells[0] if cells else 'Unknown')
        url=a.get('href');
        if url.startswith('/'): url='https://cpw.state.co.us'+url
        rows.append({'name':name,'region':region,'report_date':date,'atlas_url':url,'atlas_id':atlas_id(url)})
    # preserve distinct event rows, remove exact webpage duplicates only
    unique=[]; seen=set()
    for r in rows:
        k=(r['name'],r['region'],r['report_date'],r['atlas_id'])
        if k not in seen: seen.add(k); unique.append(r)
    return unique

def query_atlas(session, uid):
    params={'where':f'UNI_ID={uid}','outFields':'*','returnGeometry':'true','outSR':'4326','f':'json'}
    errors=[]
    for layer_id in ATLAS_LAYERS:
        url=f'{ATLAS_BASE}/{layer_id}/query'
        try:
            response=session.get(url,params=params,timeout=45)
            response.raise_for_status()
            data=response.json()
        except (requests.RequestException, ValueError) as exc:
            errors.append(f'layer {layer_id}: {exc}')
            continue
        features=data.get('features',[])
        if not features:
            continue
        f=features[0]; a=f.get('attributes',{}); g=f.get('geometry',{})
        return {'lat':g.get('y'),'lng':g.get('x'),'watercode':a.get('WATERCODE'),'atlas_name':a.get('FA_NAME'),'alternate_name':a.get('FA_NAME2'),'county':a.get('COUNTYNAME'),'location_type':a.get('LOC_TYPE'),'elevation_ft':a.get('ELEV_FT'),'boating':a.get('BOATING'),'access_ease':a.get('ACCESS_EASE'),'fishing_pressure':a.get('FISH_PRESSURE'),'survey_url':a.get('SURVEY_URL'),'driving_url':a.get('DRIVING_URL'),'atlas_layer':layer_id}
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=str(Path(__file__).parents[1]/'data'));ap.add_argument('--limit',type=int);args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    s=requests.Session();s.headers['User-Agent']='ColoradoFishMap/3.0 contact: project-maintainer'
    print('Downloading CPW report…');html=s.get(CPW,timeout=45).text;events=parse_report(html)
    if args.limit:events=events[:args.limit]
    if not events:sys.exit('No stocking rows found. CPW markup may have changed.')
    by_id=defaultdict(list)
    for e in events:by_id[e['atlas_id']].append(e)
    matched=[];unmatched=[]
    for i,(uid,group) in enumerate(by_id.items(),1):
        print(f'[{i}/{len(by_id)}] Atlas ID {uid}: {group[0]["name"]}')
        info=query_atlas(s,uid) if uid is not None else None
        if not info or info['lat'] is None: unmatched.extend(group);continue
        dates=sorted({e['report_date'] for e in group},reverse=True);base=group[0]
        matched.append({'key':f'atlas-{uid}','atlas_id':uid,'name':base['name'],'region':base['region'],'atlas_url':base['atlas_url'],'latest_report_date':dates[0],'stocking_dates':dates,'event_count':len(group),'match_method':'atlas-id','match_score':1.0,'species':[],**info});time.sleep(.03)
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'source_url':CPW,'summary':{'stocking_events':len(events),'unique_atlas_ids':len(by_id),'matched_waters':len(matched),'unmatched_events':len(unmatched)},'waters':sorted(matched,key=lambda x:(x['latest_report_date'],x['name']),reverse=True)}
    (out/'waters.json').write_text(json.dumps(payload,indent=2),encoding='utf-8');(out/'unmatched.json').write_text(json.dumps(unmatched,indent=2),encoding='utf-8')
    rows=''.join(f"<tr><td>{x['name']}</td><td>{x['region']}</td><td>{x['latest_report_date']}</td><td>{x['atlas_id']}</td><td>{x.get('atlas_name') or ''}</td><td>100%</td></tr>" for x in matched)
    report=f'''<!doctype html><meta charset="utf-8"><title>Atlas Match Report</title><style>body{{font:16px system-ui;margin:2rem;max-width:1200px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.45rem;text-align:left}}th{{position:sticky;top:0;background:white}}</style><h1>Atlas Match Report</h1><p>Generated {payload['generated_at']}. {len(matched)} matched waters; {len(unmatched)} unmatched report rows.</p><table><thead><tr><th>Report name</th><th>Region</th><th>Latest</th><th>Atlas ID</th><th>Atlas name</th><th>Confidence</th></tr></thead><tbody>{rows}</tbody></table>'''
    (out/'match-report.html').write_text(report,encoding='utf-8');print(json.dumps(payload['summary'],indent=2))
if __name__=='__main__':main()
