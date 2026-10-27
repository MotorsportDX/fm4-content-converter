"""Cross-version comparisons from original game files, SQLite read-only."""
from pathlib import Path
import sqlite3,json,re,collections,hashlib
OUT=Path(__file__).resolve().parent
ROOTS={'FM2':Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)'),
 'FM3':Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)'),
 'FM3 Ultimate':Path(r'D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 1) (Play Disc)'),
 'FM4':Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)')}
TABLES=['List_TireCompound','List_TireFrictionMultiCurve','List_TireFrictionCurve','List_TireAffectCurve']
data={}
for game,root in ROOTS.items():
 dbpath=root/'Media/DB/gamedb.slt'; c=sqlite3.connect(dbpath.as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
 tabs=[r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
 settings={};lines={}
 for i,line in enumerate((root/'Media/Physics/PhysicsSettings.ini').read_text(encoding='utf-8-sig').splitlines(),1):
  clean=line.split('//')[0].strip()
  if not clean or clean[0] in '#;[':continue
  pair=clean.split(None,1)
  if len(pair)==2:settings[pair[0]]=pair[1];lines[pair[0]]=i
 d={'root':str(root),'database':str(dbpath),'database_sha256':hashlib.sha256(dbpath.read_bytes()).hexdigest(),
    'table_count':len(tabs),'counts':{t:c.execute('select count(*) from "'+t+'"').fetchone()[0] for t in tabs},
    'tracks_active':{str(r[0]):r[1] for r in c.execute('select Active,count(*) from Tracks group by Active')},
    'physics_settings':settings,'physics_setting_lines':lines,
    'tires':{t:[dict(r) for r in c.execute('select * from '+t)] for t in TABLES},
    'schema':{t:[dict(r) for r in c.execute('pragma table_info("'+t+'")')] for t in tabs}}
 car=dict(c.execute("select * from Data_Car where MediaName='TOY_2000GT_69'").fetchone())
 if game=='FM2':weight=dict(c.execute('select * from List_UpgradeWeight where Ordinal=? and IsStock=1',(car['Id'],)).fetchone())
 else:
  bodies=[dict(r) for r in c.execute('select * from List_UpgradeCarBody where Ordinal=? and IsStock=1',(car['Id'],))]
  if len(bodies)!=1:raise ValueError('Ambiguous stock body for Toyota example')
  rows=[dict(r) for r in c.execute('select * from List_UpgradeCarBodyWeight where CarBodyId=? and IsStock=1',(bodies[0]['CarBodyID'],))]
  if len(rows)!=1:raise ValueError('Ambiguous stock weight for Toyota example')
  weight=rows[0]
 d['toyota_2000gt_example']={'car':car,'stock_weight':weight}
 data[game]=d;c.close()
diffs=[]
for a,b in [('FM2','FM3'),('FM3','FM3 Ultimate'),('FM3','FM4')]:
 diff={'from':a,'to':b,'settings_changed':{k:{'old':v,'new':data[b]['physics_settings'].get(k)} for k,v in data[a]['physics_settings'].items() if data[b]['physics_settings'].get(k)!=v},
       'settings_added':{k:v for k,v in data[b]['physics_settings'].items() if k not in data[a]['physics_settings']},'tires':{}}
 for table in TABLES:
  old=data[a]['tires'][table];new=data[b]['tires'][table];pk=next(k for k in old[0] if k.endswith('ID'))
  oi={r[pk]:r for r in old};ni={r[pk]:r for r in new};changed=[];cols=collections.Counter()
  for key in sorted(set(oi)&set(ni)):
   delta={k:{'old':v,'new':ni[key].get(k)} for k,v in oi[key].items() if ni[key].get(k)!=v}
   if delta:changed.append({'id':key,'changes':delta});cols.update(delta.keys())
  diff['tires'][table]={'primary_key':pk,'old_count':len(old),'new_count':len(new),'common':len(set(oi)&set(ni)),'new_ids':sorted(set(ni)-set(oi)),'changed_common':len(changed),'changed_columns':dict(cols),'changes':changed}
 diffs.append(diff)
result={'versions':data,'comparisons':diffs}
(OUT/'cross_version.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for game,d in data.items():
 print(game,'tables',d['table_count'],'cars',d['counts']['Data_Car'],'tracks',d['counts']['Tracks'],d['tracks_active'],'Hz',d['physics_settings'].get('CarPhysicsUpdateHz'),'tires',d['counts']['List_TireCompound'])
for d in diffs:print(d['from'],'->',d['to'],'settings changed',len(d['settings_changed']),'new',len(d['settings_added']),'tires',[(t,v['changed_common'],v['new_ids']) for t,v in d['tires'].items()])
