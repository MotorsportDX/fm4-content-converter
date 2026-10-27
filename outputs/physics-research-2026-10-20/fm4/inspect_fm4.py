"""Offline, read-only research of FM4 disc data. No game execution, no network."""
from pathlib import Path
import sqlite3, json, hashlib, zipfile, collections, xml.etree.ElementTree as ET, csv, struct

OUT = Path(__file__).resolve().parent
ROOT = Path(r'D:\Data\forza-motorsport-4')
JP = ROOT/'Forza Motorsport 4 (Japan, Asia) (Disc 1) (Play Disc)'
USA = ROOT/'USA/Forza Motorsport 4 (USA) (Disc 1) (Play Disc)'
DISC2 = ROOT/'Forza Motorsport 4 (Japan, Asia) (Disc 2) (Content Install Disc)'
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def info(p):
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
def dump(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def xmlobj(e): return {'tag':e.tag,'attributes':e.attrib,'children':[xmlobj(x) for x in e]}
c=sqlite3.connect((JP/'Media/db/gamedb.slt').as_uri()+'?mode=ro',uri=True)
c.row_factory=sqlite3.Row
tables=[x[0] for x in c.execute("select name from sqlite_master where type='table' order by name")]
def rows(t,where='',args=()): return [dict(r) for r in c.execute('select * from "'+t+'"'+(' where '+where if where else ''),args)]
schema={t:{'count':c.execute('select count(*) from "'+t+'"').fetchone()[0],'columns':rows('pragma_table_info(?)','',(t,)) if False else [dict(x) for x in c.execute('pragma table_info("'+t+'")')],'sql':c.execute('select sql from sqlite_master where name=?',(t,)).fetchone()[0]} for t in tables}
dump('schema.json',schema)
sample={}
for ordinal in [247,408,1233]:
    s={'Data_Car':rows('Data_Car','Id=?',(ordinal,))}
    for t in tables:
        cols=[x['name'] for x in schema[t]['columns']]
        if 'Ordinal' in cols and (t.startswith('List_Upgrade') or t in ['CarPartPositions','TireMod_FrictionScale']):
            s[t]=rows(t,'Ordinal=?',(ordinal,))
    for key,field,prefix,base,idfield in [('List_UpgradeCarBody','CarBodyID','List_UpgradeCarBody','Data_CarBody','Id'),('List_UpgradeEngine','EngineID','List_UpgradeEngine','Data_Engine','EngineID'),('List_UpgradeDrivetrain','DrivetrainID','List_UpgradeDrivetrain','Data_Drivetrain','DrivetrainID')]:
        ids={r[field] for r in s[key] if r.get('IsStock')==1}
        for ident in ids:
            s[base]=s.get(base,[])+rows(base,idfield+'=?',(ident,))
            for t in tables:
                cols={x['name'].lower():x['name'] for x in schema[t]['columns']}
                if t.startswith(prefix) and field.lower() in cols:
                    s[t+'_stock_base']=s.get(t+'_stock_base',[])+rows(t,'"'+cols[field.lower()]+'"=?',(ident,))
    refs={
       'List_SpringDamperPhysics':('SpringDamperPhysicsID',['FrontSpringDamperPhysicsID','RearSpringDamperPhysicsID']),
       'List_AntiSwayPhysics':('AntiSwayPhysicsID',['AntiSwayPhysicsID']),
       'List_AeroPhysics':('AeroPhysicsID',['AeroPhysicsID']),
       'List_TorqueCurve':('TorqueCurveID',['TorqueCurveFullThrottleID'])}
    for target,(idcol,fields) in refs.items():
        ids={r[f] for rr in list(s.values()) for r in rr for f in fields if f in r}
        s[target]=[r for ident in sorted(ids) for r in rows(target,idcol+'=?',(ident,))]
    sample[str(ordinal)]=s
dump('sample_cars.json',sample)
tyretables=['List_TireCompound','List_TireFrictionCurve','List_TireFrictionMultiCurve','List_TireAffectCurve','TireMod_FrictionScale','List_SuspensionPhysicsType','List_DriveType','List_EnginePlacement','List_DamageModDef','DamageDiffSettings','AutoSteerOverrides','MultiDiscContentPacks','VersionInfo']
dump('global_physics_tables.json',{t:rows(t) for t in tyretables})
dump('tracks.json',{t:rows(t) for t in ['Tracks','Environments','PittingProfiles','TrackPittingZones','TrackStartingMerges','TurnSections','SplitPoints','StartGridPositions','FlyingStartPositions','TrackSpecificAI','AILineChoices']})
phys={p.name:xmlobj(ET.parse(p).getroot()) for p in (JP/'Media/physics').glob('*.xml')}
phys['PhysicsSettings.ini']={a.strip():b.strip() for l in (JP/'Media/physics/PhysicsSettings.ini').read_text().splitlines() if ' ' in l for a,b in [l.split(' ',1)]}
dump('physics_files.json',phys)
surfaces=ET.parse(JP/'Media/physics/surfaceTypes.xml').getroot().find('SurfaceTypes')
surface_summary=[]
for e in surfaces:
    d={'surface':e.tag,**e.attrib}
    for section in ['Friction','Aerodynamics','Bumpiness','Springiness']:
        n=e.find(section)
        if n is not None:
            for k in n:
                if 'value' in k.attrib:d[section+'.'+k.tag]=k.attrib['value']
    surface_summary.append(d)
dump('surface_summary.json',surface_summary)
zip_inventory=[]
for p in sorted((JP/'Media/cars').glob('*.zip')):
    try:
        z=zipfile.ZipFile(p)
        small=[{'member':n.filename,'bytes':n.file_size,'compressed_bytes':n.compress_size,'method':n.compress_type,'crc32':f'{n.CRC:08x}'} for n in z.infolist() if 'physics' in n.filename.lower() or n.filename.lower() in ['carattribs.xml','versiondata.xml','buildnumber.txt']]
        zip_inventory.append({'file':str(p),'bytes':p.stat().st_size,'members':len(z.infolist()),'physics_metadata':small})
    except Exception as ex:zip_inventory.append({'file':str(p),'error':str(ex)})
dump('car_archive_inventory.json',zip_inventory)
track_files=[]
for p in sorted((JP/'Media/Tracks').rglob('*')):
    if p.is_file():
        d={'path':str(p.relative_to(JP)),'bytes':p.stat().st_size}
        if p.suffix.lower() in ['.col','.sh']:d.update(sha256=digest(p),header_hex=p.read_bytes()[:80].hex())
        track_files.append(d)
dump('track_file_inventory.json',track_files)
hashes=[]
for rel in ['Media/db/gamedb.slt','Media/physics/PhysicsSettings.ini','Media/physics/surfaceTypes.xml','Media/physics/CollObjects.xml','Media/physics/NatalSurfaceTypes.xml','Media/physics/PI.xml','Media/ControllerFFB.ini','Media/Tracks/LagunaSeca/Ribbon_00/lagunaseca_track_00.col','Media/Tracks/LagunaSeca/LagunaSeca_ribbon00.sh','Media/cars/ACU_NSX_97.zip','default.xex']:
    for base in [JP,USA]:
        p=base/rel
        if p.exists():hashes.append(info(p))
disc2=[]
for p in sorted((DISC2/'content').rglob('*')):
    if p.is_file():
        with p.open('rb') as f:b=f.read(0x2000)
        disc2.append({'path':str(p),'bytes':p.stat().st_size,'magic':b[:4].decode('ascii','replace'),'header_prefix_hex':b[:16].hex(),'sha256':digest(p)})
ev={'scope':'Offline static analysis only, source files not modified; no game/emulator execution. DLC excluded here.','root':str(ROOT),'db_integrity_check':c.execute('pragma integrity_check').fetchone()[0],'table_count':len(tables),'hashes':hashes,'disc2_content':disc2,'car_archive_count':len(zip_inventory),'cars_db':len(rows('Data_Car')),'tracks_db':len(rows('Tracks')),'track_files':len(track_files),'track_file_types':dict(collections.Counter(Path(d['path']).suffix.lower() for d in track_files)),'car_ids_in_example':[247,408,1233],'surface_count':len(surface_summary),'data_files':['schema.json','sample_cars.json','global_physics_tables.json','tracks.json','physics_files.json','surface_summary.json','car_archive_inventory.json','track_file_inventory.json']}
dump('evidence.json',ev)
print(json.dumps({k:v for k,v in ev.items() if k not in ['hashes','disc2_content','data_files']},indent=2))
