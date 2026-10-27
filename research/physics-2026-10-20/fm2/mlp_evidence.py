from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import struct,re,json,math,statistics,csv
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm2'
OUT.mkdir(parents=True, exist_ok=True)
BASE=Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)')
ev=json.loads((OUT/'evidence.json').read_text(encoding='utf8'))
def parse(data):
 end=data.find(b'MLPDataEnd:');assert end>=0
 header=data[:end].decode('ascii');res={};fields=[]
 for name,typ,n,m,off in re.findall(r'^([^:\r\n]+):([^:\r\n]+):(\d+):(\d+):\s*(\d+)',header,re.M):
  n,m,off=int(n),int(m),int(off);fmt={'int32':'i','uint32':'I','float':'f','int8':'b','int':'i','char':'c'}[typ]
  count=n*m;size=struct.calcsize(fmt)*count;assert off+size<=len(data)
  vals=struct.unpack('>'+str(count)+fmt,data[off:off+size])
  if typ=='char':vals=b''.join(vals).split(b'\0')[0].decode('ascii',errors='replace')
  res[name]=vals;fields.append({'name':name,'type':typ,'rows':n,'cols':m,'offset':off,'bytes':size})
 return res,fields
ev['mlp']={'method':'Field descriptors from ASCII MLP header; big-endian scalar decoding; bounds checked for each field. Geometric arclength is derived, coordinate units not proven.' ,'track_geo':[],'sample':{}}
for p in (BASE/'Media/AI/Tracks').glob('*.geo'):
 data,fields=parse(p.read_bytes());coords=list(zip(data['fWaypointX'],data['fWaypointY'],data['fWaypointZ']))
 distances=[math.dist(a,b) for a,b in zip(coords,coords[1:])]
 item={'name':p.name,'iLength':data['iLength'][0],'iType':data['iType'][0],'coordinate_count':len(coords),'min_xyz':[min(c[j] for c in coords) for j in range(3)],'max_xyz':[max(c[j] for c in coords) for j in range(3)],'polyline_open_length_raw':sum(distances),'mean_step_raw':statistics.mean(distances),'first_last_distance_raw':math.dist(coords[0],coords[-1])}
 ev['mlp']['track_geo'].append(item)
 if p.name=='lagunaseca_00.geo':
  ev['mlp']['sample'][p.name]={'fields':fields,'summary':item,'values':{k:list(v[:5]) if isinstance(v,tuple) else v for k,v in data.items()}}
for ext in ['seg','pit','irt']:
 p=BASE/f'Media/AI/Tracks/lagunaseca_00.{ext}';data,fields=parse(p.read_bytes());ev['mlp']['sample'][p.name]={'fields':fields,'values':{k:list(v[:5]) if isinstance(v,tuple) else v for k,v in data.items()}}
(OUT/'evidence.json').write_text(json.dumps(ev,ensure_ascii=False,indent=2),encoding='utf8')
with (OUT/'track_geometry_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=ev['mlp']['track_geo'][0]);w.writeheader();w.writerows(ev['mlp']['track_geo'])
print(json.dumps(ev['mlp']['sample'],indent=2))
