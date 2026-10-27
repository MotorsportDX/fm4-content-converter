"""Read STFS / inner ZIP directory only, plus selected small metadata. No extraction of bulk assets."""
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
import io,sys,json,hashlib,zipfile,collections
from pathlib import Path
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm4'
OUT.mkdir(parents=True, exist_ok=True)
from fm4_converter.archives.stfs_reader import STFS
from fm4_converter.archives.stfs_zip_io import STFSFile
from fm4_converter.archives.forza_zip import read as zipread

result=[]
root=Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 2) (Content Install Disc)\content')
for f in root.rglob('*'):
    if not f.is_file():continue
    with STFS(f) as p:
        d={'metadata':p.meta,'entries':p.entries,'archives':[],'verified_small_files':[]}
        for e in p.entries:
            if e['directory']:continue
            if e['size']<200000 and Path(e['name']).suffix.lower() in ['.xml','.ini','.txt']:
                b=p.read(e);d['verified_small_files'].append({'name':e['name'],'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),'text':b.decode('utf-8','replace')})
            if e['name'].endswith('_65.zip'):
                reader=STFSFile(p,e)
                with zipfile.ZipFile(reader) as z:
                    entries=[{'name':n.filename,'bytes':n.file_size,'method':n.compress_type,'crc32':f'{n.CRC:08x}'} for n in z.infolist()]
                    a={'name':e['name'],'entries':entries,'member_count':len(entries),'method_counts':dict(collections.Counter(x['method'] for x in entries))}
                    a['read_verification']='STFSFile SHA1 verifies each accessed block; ZIP metadata decoded below uses CRC32.'
                    small=[x for x in z.infolist() if x.filename.lower().endswith('/physics/maxdata.xml')][:1]
                    a['sample_physics']=[]
                    for x in small:
                        b=zipread(z,x)
                        dest=OUT/(f.name+'_'+x.filename.split('/')[2]+'_maxdata.xml')
                        dest.write_bytes(b)
                        a['sample_physics'].append({'member':x.filename,'sha256':hashlib.sha256(b).hexdigest(),'output':dest.name,'crc32_verified':True})
                    d['archives'].append(a)
                    print(p.meta['display_name'],len(entries),a['method_counts'])
                    print('DB/PHYSICS',[(x['name'],x['bytes']) for x in entries if any(s in x['name'].lower() for s in ['.slt','physics','maxdata','carattribs'])][:12])
        result.append(d)
(OUT/'disc2_inventory.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
