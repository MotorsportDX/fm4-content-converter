from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import sqlite3,json,hashlib,zipfile,collections,xml.etree.ElementTree as ET,difflib
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm3'
OUT.mkdir(parents=True, exist_ok=True)
ROOTS={
 'regular_d1': Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 1) (Play Disc)'),
 'regular_d2': Path(r'D:\Data\FM3\USA\Forza Motorsport 3 (USA) (Disc 2) (Content Install Disc) (1)'),
 'uc_d1': Path(r'D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 1) (Play Disc)'),
 'uc_d2': Path(r'D:\Data\FM3\USA Ultimate Collection\Forza Motorsport 3 - Ultimate Collection (USA) (Disc 2) (Content Install Disc)')}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024): h.update(b)
 return h.hexdigest()
def connect(key):
 con=sqlite3.connect((ROOTS[key]/'Media/DB/gamedb.slt').as_uri()+'?mode=ro',uri=True)
 con.row_factory=sqlite3.Row
 return con
def quote(x): return '"'+x.replace('"','""')+'"'
def dump(name,data): (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str),encoding='utf8')
def main():
 evidence={'roots':{k:str(v) for k,v in ROOTS.items()},'inventories':{},'databases':{},'core_comparison':[]}
 for key,root in ROOTS.items():
  fs=[p for p in root.rglob('*') if p.is_file()]
  evidence['inventories'][key]={'file_count':len(fs),'total_bytes':sum(p.stat().st_size for p in fs),'extensions':dict(collections.Counter(p.suffix for p in fs)),'files':[{'path':str(p.relative_to(root)),'size':p.stat().st_size} for p in fs]}
  if key.endswith('d1'):
   con=connect(key); tables={}
   for r in con.execute("select name,sql from sqlite_master where type='table'"):
    name=r['name']; cols=[dict(c) for c in con.execute('pragma table_info('+quote(name)+')')]
    tables[name]={'schema':r['sql'],'columns':cols,'row_count':con.execute('select count(*) from '+quote(name)).fetchone()[0],'sample':[dict(x) for x in con.execute('select * from '+quote(name)+' limit 2')]}
   evidence['databases'][key]={'path':str(ROOTS[key]/'Media/DB/gamedb.slt'),'sha256':sha(ROOTS[key]/'Media/DB/gamedb.slt'),'tables':tables}; con.close()
 for rel in ['default.xex','Media/DB/gamedb.slt','Media/DB/CarPartsList.xml','Media/Physics/PhysicsSettings.ini','Media/Physics/surfaceTypes.xml','Media/Physics/PI.xml','Media/Physics/CollObjects.xml','Media/ControllerFFB.ini','Media/ControllerRumble.xml','Media/GameTunableSettings/GameTunableSettings.ini','Media/GameTunableSettings/GameOptionPresets.xml','Media/zipmanifest.xml']:
  a,b=[ROOTS[k]/rel for k in ['regular_d1','uc_d1']]
  item={'path':rel,'regular_size':a.stat().st_size,'uc_size':b.stat().st_size,'regular_sha256':sha(a),'uc_sha256':sha(b)}
  item['identical']=item['regular_sha256']==item['uc_sha256'];evidence['core_comparison'].append(item)
  if not item['identical'] and a.suffix in ['.ini','.xml']:
   (OUT/('diff_'+a.name+'.txt')).write_text(''.join(difflib.unified_diff(a.read_text(errors='replace').splitlines(True),b.read_text(errors='replace').splitlines(True),fromfile='regular/'+rel,tofile='uc/'+rel)),encoding='utf8')
 dump('evidence.json',evidence)
 print(json.dumps({'inventories':{k:{x:v[x] for x in ['file_count','total_bytes','extensions']} for k,v in evidence['inventories'].items()},'tables':{k:{n:v['row_count'] for n,v in d['tables'].items()} for k,d in evidence['databases'].items()},'core_comparison':evidence['core_comparison']},indent=2))
if __name__=='__main__':main()
