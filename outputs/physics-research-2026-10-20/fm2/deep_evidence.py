from pathlib import Path
from collections import Counter
import sqlite3,json,csv,zipfile,hashlib,xml.etree.ElementTree as ET,re
OUT=Path(__file__).parent
BASE=Path(r'D:\Data\FM2\USA\Forza Motorsport 2 (USA)')
ev=json.loads((OUT/'evidence.json').read_text(encoding='utf8'))
d=sqlite3.connect((BASE/'Media/DB/gamedb.slt').as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
def rows(sql,args=()):return [dict(x) for x in d.execute(sql,args)]
def csvout(name,data):
 if not data:return
 with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def flat(e,p=''):
 out={}
 for c in e:
  k=p+c.tag
  out.update({k+'/'+a:v for a,v in c.attrib.items()})
  out.update(flat(c,k+'/'))
 return out
surfaces=ET.parse(BASE/'Media/physics/surfaceTypes.xml').getroot()
ev['surfaces']=[{'name':s.tag,**flat(s)} for s in surfaces]
csvout('surfaces.csv',[{'name':s['name'],**{k:s.get(k,'') for k in ['Friction/FrictionScale/value','Friction/HeatTireScale/value','Friction/OffRoadness/value','Bumpiness/MaxAmplitude/value','Bumpiness/Frequency/value','CollElasticity/value','CarDamageScalar/value']}} for s in ev['surfaces']])
ev['physics_settings']={}
for ln,line in enumerate((BASE/'Media/physics/PhysicsSettings.ini').read_text().splitlines(),1):
 p=line.split(None,1)
 if len(p)==2:ev['physics_settings'][p[0]]={'value':p[1],'line':ln}
ev['car_geometry']=[]
for p in (BASE/'Media/cars').glob('*.zip'):
 z=zipfile.ZipFile(p)
 match=next((n for n in z.namelist() if n.lower()=='physics/maxdata.xml'),None)
 item={'path':str(p),'members':len(z.namelist()),'has_maxdata':bool(match)}
 if match:
  data=z.read(match);root=ET.fromstring(data)
  item.update({'member':match,'sha256':hashlib.sha256(data).hexdigest(),'misc':root.find('Misc').attrib,'bounding_box':root.find('Collision/BoundingBox').attrib,'spheres':len(root.find('Collision/CollSpheres'))})
  if p.name=='acu_42_nsx_02.zip':
   (OUT/'sample_acu_42_nsx_02_MAXData.xml').write_bytes(data)
 ev['car_geometry'].append(item)
car_sql='''SELECT c.Id,c.Year,c.MediaName,c.IsDLC,c.ContentId,c.IsUnicorn,c.CurbWeight,c."FrontWeight-pct",c."Wheelbase-m",c."FrontTrack-m",c."RearTrack-m",c.SteerMaxAngle,c.SteerMaxAngleFiltered,c.GameTorqueScale,c.GameDragScale,p.DrivetrainId,p.EnginePlacementId,w.Mass,w.CMHeight,w.CMBackFront,w.CMLeftRight,w.BlockDimX,w.BlockDimY,w.BlockDimZ,e.EngineID,t.TireCompoundID,s.FrontSpringDamperPhysicsID,s.RearSpringDamperPhysicsID,a.FrontAntiSwayPhysicsID,a.RearAntiSwayPhysicsID FROM Data_Car c LEFT JOIN Powertrains p ON p.Id=c.PowertrainID LEFT JOIN List_UpgradeWeight w ON w.Ordinal=c.Id AND w.IsStock=1 LEFT JOIN List_UpgradeEngine e ON e.Ordinal=c.Id AND e.IsStock=1 LEFT JOIN List_UpgradeTireCompound t ON t.Ordinal=c.Id AND t.IsStock=1 LEFT JOIN List_UpgradeSpringDamper s ON s.Ordinal=c.Id AND s.IsStock=1 LEFT JOIN List_UpgradeAntiSway a ON a.Ordinal=c.Id AND a.IsStock=1 ORDER BY c.Id'''
cars=rows(car_sql);csvout('cars_physics_map.csv',cars)
ev['car_map_summary']={'rows':len(cars),'unique_ids':len(set(x['Id'] for x in cars)),'no_stock_weight':sum(x['Mass'] is None for x in cars),'no_stock_engine':sum(x['EngineID'] is None for x in cars),'no_stock_tirecompound':sum(x['TireCompoundID'] is None for x in cars),'is_dlc':dict(Counter(str(x['IsDLC']) for x in cars)),'sample_cars':cars[:3]}
tracks=rows('SELECT * FROM Tracks');csvout('tracks_map.csv',tracks)
ev['tracks_summary']={'rows':len(tracks),'active':sum(x['Active']==1 for x in tracks),'active_environments':sorted(set(x['MediaName'] for x in tracks if x['Active']==1)),'binary_collision_files':len(list((BASE/'Media/tracks').rglob('*.col'))),'ai_file_counts':dict(Counter(p.suffix for p in (BASE/'Media/AI/Tracks').glob('*') if p.is_file()))}
ev['track_samples']={}
for rel in ['Media/tracks/LagunaSeca/Ribbon_00/lagunaseca_track_00.col','Media/AI/Tracks/lagunaseca_00.geo','Media/AI/Tracks/lagunaseca_00.irt','Media/AI/Tracks/lagunaseca_00.seg','Media/AI/Tracks/lagunaseca_00.pit']:
 p=BASE/rel
 if p.exists():
  data=p.read_bytes();ev['track_samples'][rel]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'first_64_hex':data[:64].hex(),'ascii_strings_sample':[s.decode('ascii') for s in re.findall(rb'[ -~]{8,}',data)[:20]]}
ev['sample_stock_build']={'Data_Car':rows('SELECT * FROM Data_Car WHERE Id=247')[0]}
for name in ev['database']['tables']:
 cols=[x['name'] for x in ev['database']['tables'][name]['columns']]
 if name.startswith('List_Upgrade') and 'Ordinal' in cols:
  ev['sample_stock_build'][name]=rows('SELECT * FROM "'+name+'" WHERE Ordinal=247 AND IsStock=1')
for name,key,ids in [('List_SpringDamperPhysics','SpringDamperPhysicsID',[1,5]),('List_AntiSwayPhysics','AntiSwayPhysicsID',[1,5]),('List_TireCompound','TireCompoundID',[1,2,3,4,5,6,7]),('List_TireFrictionMultiCurve','FrictionMultiCurveID',list(range(1,17)))]:
 ev.setdefault('complete_small_physics_tables',{})[name]=rows('SELECT * FROM '+name)
ev['sample_stock_build']['engine']=rows('SELECT * FROM Data_Engine WHERE EngineID=1')[0]
ev['sample_stock_build']['engine_cam']=rows('SELECT * FROM List_UpgradeEngineCamValves WHERE EngineID=1 AND IsStock=1')[0]
ev['database_integrity']=d.execute('PRAGMA integrity_check').fetchone()[0]
(OUT/'evidence.json').write_text(json.dumps(ev,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps({k:ev[k] for k in ['car_map_summary','tracks_summary','database_integrity']},indent=2))
print('Surface count',len(ev['surfaces']));print('Car MAXData',sum(x['has_maxdata'] for x in ev['car_geometry']))
