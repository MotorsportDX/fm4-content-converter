"""Validate research artifacts and cross-file counts, without running game code."""
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import json,csv,re,collections
ROOT=PHYSICS_RESEARCH_OUTPUT
checks=[]
def check(name,condition,detail=None):
 checks.append({'check':name,'passed':bool(condition),'detail':detail})
 if not condition:print('FAILED',name,detail)
parsed={}
for p in ROOT.rglob('*.json'):
 if p.name=='validation.json':continue
 try:parsed[p.relative_to(ROOT).as_posix()]=json.loads(p.read_text(encoding='utf-8-sig'))
 except Exception as e:check('JSON '+str(p),False,repr(e))
check('All JSON artifacts parse',not any(not c['passed'] for c in checks),len(parsed))
for rel,n in [('fm2/cars_physics_map.csv',310),('fm2/tracks_map.csv',50),('fm2/bonus_cars_map.csv',39),('fm2/bonus_tracks_map.csv',5),('fm3/cars_map.csv',925),('fm3/tracks_map.csv',254),('fm4/car_catalog.csv',503),('fm4/track_catalog.csv',127),('dlc/cars_catalog.csv',112),('dlc/tracks_catalog.csv',18)]:
 with (ROOT/rel).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 check('Catalog count '+rel,len(rows)==n,{'actual':len(rows),'expected':n})
for rel in ['REPORT.md','METHODS.md','fm2/report.md','fm3/report.md','fm4/report.md','dlc/report.md']:
 p=ROOT/rel;check('Report exists '+rel,p.is_file() and p.stat().st_size>1000)
 if p.is_file():
  text=p.read_text(encoding='utf-8')
  for target in re.findall(r'\]\(([^)]+)\)',text):
   if ':' in target or target.startswith('#'):continue
   check('Report link '+rel+' '+target,(p.parent/target.split('#')[0]).exists())
d=parsed['dlc/evidence.json'];check('FM4 package count',len(d)==11)
dlcs=[p for p in d if p['category']=='DLC'];check('FM4 DLC count',len(dlcs)==8)
newcars=[];newtracks=[];xmlcount=0
for p in dlcs:
 files=[e['name'] for e in p['entries'] if not e['directory']]+[m['name'] for z in p['zips'] for m in z['members']]
 check('No executable payloads in DLC '+p['metadata']['display_name'],not any(n.lower().endswith(('.xex','.xexp')) for n in files))
 for z in p['zips']:
  check('No selected metadata decode errors '+z['path'],not z['errors'])
  xmlcount+=len(z['physics_xml'])
  for db in z['databases']:
   check('DLC database integrity '+db['path'],db['quick_check']=='ok')
   check('No global tire replacement '+db['path'],not set(['List_TireCompound','List_TireFrictionCurve','List_TireFrictionMultiCurve','List_TireAffectCurve'])&set(db['tables']))
   newcars.extend(r['Id'] for r in db['tables'].get('Data_Car',{}).get('data',[]))
   newtracks.extend(r['id'] for r in db['tables'].get('Tracks',{}).get('data',[]))
check('DLC unique car IDs and all XML decoded',len(newcars)==len(set(newcars))==xmlcount==112)
check('DLC unique track IDs',len(newtracks)==len(set(newtracks))==18)
cross=parsed['cross_version.json'];uc=next(x for x in cross['comparisons'] if x['to']=='FM3 Ultimate')
check('FM3 UC tire tables exactly equal',all(not x['changes'] and not x['new_ids'] and x['old_count']==x['new_count'] for x in uc['tires'].values()))
check('FM3 UC PhysicsSettings equal',not uc['settings_changed'] and not uc['settings_added'])
for v,expected in [('FM2',239),('FM3',359),('FM3 Ultimate',359),('FM4',359)]:
 check('Configured Hz '+v,int(cross['versions'][v]['physics_settings']['CarPhysicsUpdateHz'])==expected)
result={'date':'2026-10-20','scope':'Offline artifact consistency validation; no game execution or source writes','checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks)}
(ROOT/'validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':result['failed'],'json_files':len(parsed)}))
raise SystemExit(1 if result['failed'] else 0)
