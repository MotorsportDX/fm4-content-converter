"""Build per-car and per-track research catalog, keeping all values in native units."""
from fm4_converter.paths import PHYSICS_RESEARCH_OUTPUT
from pathlib import Path
import sqlite3,json,csv,sys,zipfile,hashlib,xml.etree.ElementTree as ET
OUT=PHYSICS_RESEARCH_OUTPUT / 'fm4'
OUT.mkdir(parents=True, exist_ok=True)
from fm4_converter.archives.forza_zip import read as zipread
JP=Path(r'D:\Data\forza-motorsport-4\Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)')
c=sqlite3.connect((JP/'Media/db/gamedb.slt').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
def rows(t,w='',a=()):return [dict(x) for x in c.execute('select * from '+t+(' where '+w if w else ''),a)]
def csvout(n,r):
    with (OUT/n).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(r[0]));w.writeheader();w.writerows(r)
sources={};maxdata=[]
for p in (JP/'Media/cars').glob('*.zip'):
    with zipfile.ZipFile(p) as z:
        members=[n for n in z.namelist() if n.lower()=='physics/maxdata.xml']
        if members:
            sources[p.stem.lower()]='Disc1'
            b=zipread(z,members[0]);root=ET.fromstring(b)
            maxdata.append({'MediaName':p.stem,'source':str(p),'member':members[0],'crc32_verified':True,'sha256':hashlib.sha256(b).hexdigest(),'Misc':root.find('Misc').attrib,'collision_spheres':len(root.findall('./Collision/CollSpheres/*')),'BoundingBox':root.find('Collision/BoundingBox').attrib})
for d in json.loads((OUT/'disc2_inventory.json').read_text()):
    for a in d['archives']:
        for e in a['entries']:
            if e['name'].lower().endswith('/physics/maxdata.xml'):
                sources[e['name'].split('/')[2].lower()]='Disc2 / '+d['metadata']['display_name']
carcat=[]
for car in rows('Data_Car'):
    ordinal=car['Id'];body=rows('List_UpgradeCarBody','Ordinal=? AND IsStock=1',(ordinal,));eng=rows('List_UpgradeEngine','Ordinal=? AND IsStock=1',(ordinal,));drive=rows('List_UpgradeDrivetrain','Ordinal=? AND IsStock=1',(ordinal,));tire=rows('List_UpgradeTireCompound','Ordinal=? AND IsStock=1',(ordinal,))
    b=rows('Data_CarBody','Id=?',(body[0]['CarBodyID'],))[0] if body else {}
    mass=rows('List_UpgradeCarBodyWeight','CarBodyId=? AND IsStock=1',(body[0]['CarBodyID'],))[0] if body else {}
    d={k:car[k] for k in ['Id','MediaName','Year','IsDrivable','HasCarExperience','DriveTypeID','EnginePlacementID','CurbWeight','FrontTireWidthMM','FrontTireAspect','FrontWheelDiameterIN','RearTireWidthMM','RearTireAspect','RearWheelDiameterIN','GameTorqueScale','GameDragScale','BodyAeroLongitudinalDrag','BodyAeroForwardDownforceFront','BodyAeroForwardDownforceRear']}
    d.update(physical_asset_source=sources.get(car['MediaName'].lower(),'No maxdata found: check Autovista-only'),stock_body_id=body[0]['CarBodyID'] if body else '',stock_engine_id=eng[0]['EngineID'] if eng else '',stock_drivetrain_id=drive[0]['DrivetrainID'] if drive else '',stock_tire_compound_id=tire[0]['TireCompoundID'] if tire else '',stock_Mass_raw=mass.get('Mass'),stock_CMHeight_raw=mass.get('CMHeight'),stock_CMBackFront_raw=mass.get('CMBackFront'),stock_CMLeftRight_raw=mass.get('CMLeftRight'),ModelWheelbase_raw=b.get('ModelWheelbase'),ModelFrontTrackOuter_raw=b.get('ModelFrontTrackOuter'),ModelRearTrackOuter_raw=b.get('ModelRearTrackOuter'))
    carcat.append(d)
csvout('car_catalog.csv',carcat)
tracks=[]
for t in rows('Tracks'):
    p=JP/'Media/Tracks'/t['MediaName']/('Ribbon_%02d'%t['RibbonIndex'])
    tracks.append({**{k:t[k] for k in ['id','MediaName','RibbonIndex','ReverseIndex','Length','Active','IsHomespace','IsInstalled','IsRealWorld','IsReverse','ContentId','StartLine','FinishLine']},'collision_path':str(next(p.glob('*.col'),'')),'collision_files_here':len(list(p.glob('*.col'))),'collobjs_present':(p/'collobjs.xml').exists(),'tracksettings_path':str(JP/'Media/Tracks'/t['MediaName']/'TrackSettings.xml')})
csvout('track_catalog.csv',tracks)
(OUT/'maxdata_disc1_summary.json').write_text(json.dumps(maxdata,indent=2),encoding='utf-8')
ev=json.loads((OUT/'evidence.json').read_text());ev.update(disc1_maxdata_count=len(maxdata),car_source_counts={s:sum(x['physical_asset_source']==s for x in carcat) for s in sorted(set(x['physical_asset_source'] for x in carcat))},car_maxdata_in_source_but_not_db=sorted(set(sources)-{x['MediaName'].lower() for x in carcat}),catalogue_files=['car_catalog.csv','track_catalog.csv','maxdata_disc1_summary.json','disc2_inventory.json'])
(OUT/'evidence.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
print('Physical car metadata:',len(maxdata),'Disc1; source counts:',ev['car_source_counts']);print('Extra sources:',ev['car_maxdata_in_source_but_not_db'])
