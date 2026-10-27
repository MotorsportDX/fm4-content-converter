from research import *
import sys,io,re,struct,csv
sys.path.insert(0,str(OUT.parent/'shared'))
from stfs_reader import STFS
from stfs_zip_io import STFSFile
import forza_zip
def main():
 base=connect('uc_d1'); evidence={'car_attributes':{},'patches':[],'mlp':{},'surfaces':[]}
 for name in ['ACU_15_ARX01b_08','MAZ_MX5Miata_94','NIS_SkylineGTR_02']:
  p=ROOTS['regular_d1']/'Media/Cars'/f'{name}.zip'
  if not p.exists(): continue
  with zipfile.ZipFile(p) as z:
   info=next(x for x in z.infolist() if x.filename.lower()=='carattribs.xml');b=forza_zip.read(z,info)
   evidence['car_attributes'][name]={'source':str(p),'member':info.filename,'crc32':f'{info.CRC:08x}','sha256':hashlib.sha256(b).hexdigest(),'text':b.decode(errors='replace')}
 for disc in ['regular_d2','uc_d2']:
  for p in (ROOTS[disc]/'Content').rglob('*'):
   if not p.is_file():continue
   with STFS(p) as s:
    for e in s.entries:
     if e['directory'] or not e['name'].lower().endswith('.zip'):continue
     with zipfile.ZipFile(STFSFile(s,e)) as z:
      for m in z.infolist():
       if not m.filename.lower().endswith(('.sql','.slt')):continue
       b=forza_zip.read(z,m);row={'disc':disc,'package':p.name,'zip':e['name'],'member':m.filename,'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),'crc32':f'{m.CRC:08x}'}
       if m.filename.lower().endswith('.sql'):row['text']=b.decode(errors='replace')
       else:
        c=sqlite3.connect(':memory:');c.deserialize(b);c.row_factory=sqlite3.Row;tables={}
        for t in c.execute("select name,sql from sqlite_master where type='table'"):
         name=t['name'];rs=[dict(v) for v in c.execute('select * from '+quote(name))];cols=[dict(v) for v in c.execute('pragma table_info('+quote(name)+')')];pk=[v['name'] for v in base.execute('pragma table_info('+quote(name)+')') if v['pk']]
         tables[name]={'schema':t['sql'],'rows':rs,'columns':cols}
         common=[]
         if pk:
          for v in rs:
           try:old=base.execute('select * from '+quote(name)+' where '+' and '.join(quote(k)+'=?' for k in pk),[v[k] for k in pk]).fetchone()
           except sqlite3.OperationalError:old=None
           if old:
            old=dict(old);common.append({'key':{k:v[k] for k in pk},'changes':{k:{'base':old.get(k),'patch':v[k]} for k in v if v[k]!=old.get(k)}})
         tables[name]['comparison_key_from_base_schema']=pk
         tables[name]['common_with_uc_disc1']=common
        row['tables']=tables;c.close()
       evidence['patches'].append(row)
 for ext in ['geo','irt','pit','seg']:
  p=ROOTS['regular_d1']/('Media/AI/Tracks/lagunaseca_00.'+ext);b=p.read_bytes();end=b.index(b'MLPDataEnd:')
  fields=[]
  for line in b[:end].decode('ascii').splitlines()[1:]:
   name,typ,n1,n2,offset=line.split(':');n=int(n1)*int(n2);off=int(offset);fmt={'float':'f','int32':'i','uint32':'I','int':'i','int8':'b'}.get(typ)
   v=list(struct.unpack_from('>'+str(n)+fmt,b,off)) if fmt else b[off:off+n].decode('ascii',errors='replace')
   fields.append({'name':name,'type':typ,'dimensions':[int(n1),int(n2)],'offset':off,'minimum':min(v) if isinstance(v,list) else None,'maximum':max(v) if isinstance(v,list) else None,'first_values':v[:6]})
  evidence['mlp'][ext]={'path':str(p),'sha256':sha(p),'header':b[:end+12].decode('ascii'),'fields':fields}
 tree=ET.parse(ROOTS['regular_d1']/'Media/Physics/surfaceTypes.xml')
 def element(x):return {'attributes':x.attrib,'children':{y.tag:element(y) for y in x}} if len(x) else x.attrib
 for x in tree.getroot().find('SurfaceTypes'):
  evidence['surfaces'].append({'name':x.tag,'category':x.attrib.get('Category'),'parameters':{n.tag:element(n) for n in x}})
 dump('decoded_assets.json',evidence)
 for k,v in evidence['car_attributes'].items():print('CAR',k,v['text'][:8000])
 print('PATCHES',[(p['disc'],p['package'],p['member'],p.get('text'),{n:len(t['rows']) for n,t in p.get('tables',{}).items()}) for p in evidence['patches']])
if __name__=='__main__':main()
