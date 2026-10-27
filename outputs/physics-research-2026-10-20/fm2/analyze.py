from pathlib import Path
from collections import Counter
import sqlite3,json,hashlib,zipfile,re,struct
ROOT=Path(r'D:\Data\FM2')
OUT=Path(__file__).parent
BASE=ROOT/'USA'/'Forza Motorsport 2 (USA)'
BONUS=ROOT/'USA'/'Forza Motorsport 2 (USA) (Bonus Disc)'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
ev={'root':str(ROOT),'scope':'Offline static; no game or emulator executed; source read only.'}
ev['inventory']={}
for name,root in [('base',BASE),('bonus',BONUS)]:
 files=[p for p in root.rglob('*') if p.is_file()]
 ev['inventory'][name]={'files':len(files),'bytes':sum(p.stat().st_size for p in files),'extensions':dict(Counter(p.suffix.lower() or '<none>' for p in files))}
ev['files']={}
important=[BASE/'default.xex',BASE/'Media/DB/gamedb.slt',BASE/'Media/physics/PhysicsSettings.ini',BASE/'Media/physics/surfaceTypes.xml',BASE/'Media/physics/CollObjects.ini',BASE/'Media/GameTunableSettings/GameTunableSettings.ini',BASE/'Media/ControllerFFB.ini',BONUS/'default.xex',BONUS/'title_update.bin',BONUS/'ExpansionInstaller.ini']
for p in important:ev['files'][str(p)]={'bytes':p.stat().st_size,'sha256':sha(p),'magic_hex':p.read_bytes()[:16].hex()}
db=sqlite3.connect((BASE/'Media/DB/gamedb.slt').as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
schema={}
for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
 name=r['name'];safe='"'+name.replace('"','""')+'"'
 schema[name]={'sql':r['sql'],'rows':db.execute('SELECT COUNT(*) FROM '+safe).fetchone()[0],'columns':[dict(x) for x in db.execute('PRAGMA table_info('+safe+')')],'samples':[dict(x) for x in db.execute('SELECT * FROM '+safe+' LIMIT 2')]}
ev['database']={'path':str(BASE/'Media/DB/gamedb.slt'),'table_count':len(schema),'tables':schema}
ev['archives']={}
for folder in ['cars','wheels','brakes']:
 ps=list((BASE/'Media'/folder).glob('*.zip'))
 ev['archives'][folder]={'count':len(ps)}
 if ps:
  p=ps[0]
  try:
   z=zipfile.ZipFile(p);ev['archives'][folder].update({'sample':str(p),'members':[{'name':x.filename,'bytes':x.file_size,'compression':x.compress_type} for x in z.infolist()]})
  except Exception as e:ev['archives'][folder]['error']=str(e)
ev['bonus_packages']=[]
for p in (BONUS/'content').rglob('*'):
 if not p.is_file():continue
 with p.open('rb') as f:header=f.read(0xA000)
 ev['bonus_packages'].append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'magic':repr(header[:4]),'header_hex':header[:32].hex(),'text_utf16be':re.findall(r'[ -~]{8,}',header.decode('utf-16-be',errors='ignore')),'text_ascii':re.findall(rb'[ -~]{8,}',header)[:30]})
def clean(x):
 if isinstance(x,bytes):return x.hex()
 raise TypeError(type(x).__name__)
(OUT/'evidence.json').write_text(json.dumps(ev,indent=2,ensure_ascii=False,default=clean),encoding='utf-8')
(OUT/'schema.txt').write_text('\n\n'.join(f"{k} ({v['rows']} rows)\n{v['sql']}" for k,v in schema.items()),encoding='utf-8')
print(json.dumps({'inventory':ev['inventory'],'database_tables':len(schema),'archives':ev['archives'],'bonus_packages':ev['bonus_packages']},indent=2,default=clean))
