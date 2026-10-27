"""Offline read-only catalog and physics metadata extraction of supplied FM4 DLC/TUs."""
from pathlib import Path
import sys, io, json, zipfile, sqlite3, hashlib, collections, re
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'shared'))
from stfs_reader import STFS
from stfs_zip_io import STFSFile
import forza_zip
ROOT=Path(r'D:\Data\forza-motorsport-4')
BASE=ROOT/'Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)'/'Media'/'DB'/'gamedb.slt'
base=sqlite3.connect(BASE.as_uri()+'?mode=ro&immutable=1',uri=True)
base.row_factory=sqlite3.Row
out=OUT/'dlc';out.mkdir(exist_ok=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()
def table_rows(conn,t):return [dict(r) for r in conn.execute('select * from "'+t.replace('"','""')+'"')]
def db_info(data):
 db=sqlite3.connect(':memory:');db.deserialize(data);db.row_factory=sqlite3.Row
 tables=[r[0] for r in db.execute("select name from sqlite_master where type='table' order by name")]
 result={'quick_check':db.execute('pragma quick_check').fetchone()[0],'sha256':hashlib.sha256(data).hexdigest(),'tables':{}}
 for t in tables:
  cols=[dict(r) for r in db.execute('pragma table_info("'+t.replace('"','""')+'")')]
  rows=table_rows(db,t); v={'rows':len(rows),'columns':cols}
  if t in ['Data_Car','Data_Engine','Data_CarBody','Tracks','CarTrack','Version']:v['data']=rows
  pks=[x['name'] for x in cols if x['pk']]
  if not pks:
   basecols=[dict(r) for r in base.execute('pragma table_info("'+t.replace('"','""')+'")')]
   pks=[x['name'] for x in sorted(basecols,key=lambda x:x['pk']) if x['pk']]
  if not pks:
   pks=[x['name'] for x in cols if x['name'].lower()=='id']
  try: oldrows=table_rows(base,t)
  except sqlite3.OperationalError:oldrows=[]
  if pks and oldrows and all(k in oldrows[0] for k in pks):
   old={tuple(r[k] for k in pks):r for r in oldrows};newids=[];changes=[];count=0;col_counts=collections.Counter()
   for r in rows:
    k=tuple(r[x] for x in pks)
    if k not in old:newids.append(k);continue
    diff={c:{'base':old[k].get(c),'patch':val} for c,val in r.items() if c in old[k] and val!=old[k][c]}
    if diff:
     count+=1;col_counts.update(diff.keys())
     if len(changes)<4:changes.append({'key':k,'changes':diff})
   v['comparison_with_base']={'key':pks,'new_keys':newids,'overlap_rows':len(rows)-len(newids),'changed_overlap_rows':count,'changed_columns':dict(col_counts),'examples':changes}
  result['tables'][t]=v
 db.close();return result

def zip_info(z,label):
 result={'path':label,'members':[],'databases':[],'sql':[],'physics_xml':[],'other_physics_files':[],'errors':[]}
 for info in z.infolist():
  name=info.filename;low=name.lower()
  result['members'].append({'name':name,'size':info.file_size,'compressed_size':info.compress_size,'method':info.compress_type,'crc32':f'{info.CRC:08x}'})
  wanted=low.endswith(('.slt','.sql')) or low.endswith('physics/maxdata.xml') or any(x in low for x in ('physicssettings.ini','surfacetypes.xml','zipmount.xml'))
  if not wanted:continue
  try:
   data=forza_zip.read(z,info)
   if low.endswith('.slt'):result['databases'].append({'path':name,**db_info(data)})
   elif low.endswith('.sql'):result['sql'].append({'path':name,'text':data.decode('utf-8-sig',errors='replace'),'sha256':hashlib.sha256(data).hexdigest()})
   elif low.endswith('physics/maxdata.xml'):
    import xml.etree.ElementTree as ET
    root=ET.fromstring(data);misc=root.find('Misc');box=root.find('./Collision/BoundingBox');spheres=root.find('./Collision/CollSpheres')
    result['physics_xml'].append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'misc':misc.attrib if misc is not None else {},'bounding_box':box.attrib if box is not None else {},'collision_spheres':len(spheres) if spheres is not None else 0})
   else:result['other_physics_files'].append({'path':name,'text':data.decode('utf-8-sig',errors='replace')})
  except Exception as exc:result['errors'].append({'path':name,'error':repr(exc)})
 return result

results=[]
for category in ['DLC','Title Update']:
 for path in sorted((ROOT/category).rglob('*')):
  if not path.is_file():continue
  with path.open('rb') as f:magic=f.read(4)
  if magic not in (b'LIVE',b'PIRS',b'CON '):continue
  with STFS(path) as p:
   item={'category':category,'metadata':p.meta,'sha256':sha(path),'entries':p.entries,'zips':[],'loose_metadata':[]}
   for e in p.entries:
    if e['directory']:continue
    if e['name'].lower().endswith('.zip'):
     with zipfile.ZipFile(STFSFile(p,e)) as z:item['zips'].append(zip_info(z,e['name']))
    elif e['size']<100000 and e['name'].lower().endswith(('.xml','.ini','.sql')):
     item['loose_metadata'].append({'path':e['name'],'text':p.read(e).decode('utf-8-sig',errors='replace')})
   results.append(item)
   print(category,p.meta['display_name'],[(d['path'], d['tables'].get('Data_Car',{}).get('rows'),d['tables'].get('Tracks',{}).get('rows')) for z in item['zips'] for d in z['databases']], 'errors',sum(len(z['errors']) for z in item['zips']),flush=True)
(out/'evidence.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
summary=[]
for p in results:
 cars={};tracks={};changes={};physics=0
 for z in p['zips']:
  physics+=len(z['physics_xml'])
  for d in z['databases']:
   for t,target in [('Data_Car',cars),('Tracks',tracks)]:
    for r in d['tables'].get(t,{}).get('data',[]):target[r.get('Id',r.get('ID',r.get('id')))]=r
   for t,v in d['tables'].items():
    c=v.get('comparison_with_base',{})
    if c.get('changed_overlap_rows'):changes[t]=c
 summary.append({'category':p['category'],'name':p['metadata']['display_name'],'path':p['metadata']['path'],'car_rows':len(cars),'track_rows':len(tracks),'cars':list(cars.values()),'tracks':list(tracks.values()),'maxdata_xml_count':physics,'changed_base_tables':changes,'sql':[s for z in p['zips'] for s in z['sql']],'errors':[e for z in p['zips'] for e in z['errors']]})
(out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
print('DONE',len(results),'packages')
