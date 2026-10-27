from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import sys,json,hashlib,sqlite3,zipfile,io,collections,csv
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm2'
OUT.mkdir(parents=True, exist_ok=True)
from fm4_converter.archives.stfs_reader import STFS
ev=json.loads((OUT/'evidence.json').read_text(encoding='utf8'))
base=sqlite3.connect(Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)\Media\DB\gamedb.slt').as_uri()+'?mode=ro',uri=True);base.row_factory=sqlite3.Row
car_catalog=[];track_catalog=[]
for pack in ev['bonus_analysis']:
 pack['zip_archives']=[]
 with STFS(pack['metadata']['path']) as p:
  for entry in p.entries:
   if entry['directory']:continue
   if entry['name'].endswith('.sql'):
    data=p.read(entry);pack.setdefault('license_scripts',[]).append({'name':entry['name'],'sha256':hashlib.sha256(data).hexdigest(),'text':data.decode('utf-8-sig')})
   if not entry['name'].endswith('.zip'):continue
   if entry['size']>128*1024*1024:
    pack['zip_archives'].append({'name':entry['name'],'skipped':'large graphics archive; no extraction'});continue
   data=p.read(entry);z=zipfile.ZipFile(io.BytesIO(data));zi={'name':entry['name'],'sha256':hashlib.sha256(data).hexdigest(),'stfs_block_sha1_verified':True,'members':[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()],'metadata':[]}
   for item in z.infolist():
    n=item.filename.lower()
    if not (n.endswith(('.sql','.slt')) or 'physics/' in n):continue
    data=z.read(item);result={'name':item.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    dest=OUT/'bonus_metadata'/Path(pack['metadata']['path']).name/item.filename;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);result['local_copy']=str(dest)
    if data.startswith(b'SQLite format 3'):
     d=sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;result['sqlite_integrity']=d.execute('PRAGMA integrity_check').fetchone()[0];result['tables']={}
     for r in d.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
      t=r['name'];safe='"'+t.replace('"','""')+'"';cols=[x[1] for x in d.execute('PRAGMA table_info('+safe+')')];rs=[dict(x) for x in d.execute('SELECT * FROM '+safe)]
      result['tables'][t]={'rows':len(rs),'columns':cols,'sql':r['sql'],'samples':rs[:1]}
      if t in ['Data_Car','Tracks']:result['tables'][t]['all_rows']=rs
      if t=='Data_Car':
       for c in rs:car_catalog.append({'Package':pack['metadata']['display_name'],**{k:c.get(k) for k in ['Id','Year','MediaName','CurbWeight','ContentId','IsDLC','GameTorqueScale','GameDragScale']}})
      if t=='Tracks':
       for c in rs:track_catalog.append({'Package':pack['metadata']['display_name'],**{k:c.get(k) for k in ['id','MediaName','RibbonIndex','ReverseIndex','Length','Active','ContentId']}})
     d.close()
    else:result['text']=data.decode('utf-8-sig',errors='replace')
    zi['metadata'].append(result)
   pack['zip_archives'].append(zi)
for name,rs in [('bonus_cars_map.csv',car_catalog),('bonus_tracks_map.csv',track_catalog)]:
 with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=rs[0]);w.writeheader();w.writerows(rs)
ev['bonus_totals']={'merge_car_rows':len(car_catalog),'merge_unique_car_ids':len(set(c['Id'] for c in car_catalog)),'merge_track_rows':len(track_catalog),'merge_unique_track_ids':len(set(c['id'] for c in track_catalog))}
(OUT/'evidence.json').write_text(json.dumps(ev,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'bonus_inventory.json').write_text(json.dumps(ev['bonus_analysis'],ensure_ascii=False,indent=2),encoding='utf8')
for p in ev['bonus_analysis']:
 print('PACKAGE',p['metadata']['display_name'])
 for z in p['zip_archives']:
  for i in z.get('metadata',[]):
   if i['name'].endswith('.sql'):print(i['name'],i['text'])
   if 'tables' in i:print(i['name'],{k:v['rows'] for k,v in i['tables'].items()})
print(ev['bonus_totals'])
