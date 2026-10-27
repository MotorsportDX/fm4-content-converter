from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import sys,json,hashlib,sqlite3,zipfile,io
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm2'
OUT.mkdir(parents=True, exist_ok=True)
from fm4_converter.archives.stfs_reader import STFS
BONUS=Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA) (Bonus Disc)')
ev=json.loads((OUT/'evidence.json').read_text(encoding='utf8'))
reports=[]
for path in [p for p in (BONUS/'content').rglob('*') if p.is_file()]+[BONUS/'title_update.bin']:
 try:
  with STFS(path) as p:
   result={'metadata':p.meta,'entries':p.entries,'selected_payloads':[]}
   for e in p.entries:
    if e['directory']:continue
    n=e['name'].lower()
    if not (n.endswith(('.slt','.ini','.xml','.txt','.csv')) or 'manifest' in n or e['size']<2048):continue
    if e['size']>20*1024*1024:continue
    item={'name':e['name'],'bytes':e['size']}
    try:
     data=p.read(e);item.update({'sha256':hashlib.sha256(data).hexdigest(),'stfs_block_sha1_verified':True,'magic_hex':data[:16].hex()})
     if data.startswith(b'SQLite format 3'):
      dest=OUT/'bonus_metadata'/path.name/e['name'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
      d=sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
      item['local_copy']=str(dest);item['sqlite_integrity']=d.execute('PRAGMA integrity_check').fetchone()[0];item['tables']={}
      for r in d.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"):
       t=r['name'];safe='"'+t.replace('"','""')+'"';cols=[x[1] for x in d.execute('PRAGMA table_info('+safe+')')]
       item['tables'][t]={'rows':d.execute('SELECT COUNT(*) FROM '+safe).fetchone()[0],'columns':cols,'sql':r['sql'],'samples':[dict(x) for x in d.execute('SELECT * FROM '+safe+' LIMIT 2')]}
       if t in ['Data_Car','Tracks']:item['tables'][t]['all_rows']=[dict(x) for x in d.execute('SELECT * FROM '+safe)]
      d.close()
     elif len(data)<250000:
      if b'\0' in data:
       stop=data.find(b'MLPDataEnd:')
       item['ascii_header']=data[:stop+11 if stop>=0 else 100].decode('ascii',errors='replace')
       item['binary_payload_not_text']=True
      else:item['text']=data.decode('utf8',errors='replace')
    except Exception as err:item['error']=str(err)
    result['selected_payloads'].append(item)
   reports.append(result)
 except Exception as err:reports.append({'path':str(path),'error':str(err)})
ev['bonus_analysis']=reports
(OUT/'evidence.json').write_text(json.dumps(ev,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'bonus_inventory.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf8')
for r in reports:
 print(json.dumps({'metadata':r.get('metadata'), 'error':r.get('error'),'entries':[{'name':x['name'],'size':x['size']} for x in r.get('entries',[])],'payloads':[{'name':x['name'],'tables':{n:v['rows'] for n,v in x.get('tables',{}).items()},'error':x.get('error'),'text':x.get('text','')[:1000]} for x in r.get('selected_payloads',[])]},ensure_ascii=True))
